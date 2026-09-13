"""Watch the running desk: every scene change another client or the surface makes, as it
happens. Read-only — the only messages sent are ``/xremote`` and ``/node``.

After ``/xremote`` the desk pushes one message per changed leaf (``/ch/29/mix/fader``) for
ten seconds. Each leaf marks the reference node that owns it dirty; a dirty node is asked
for its whole scene-format line with ``/node`` at most once per debounce window, and a
change is reported when that line differs from the last one reported for the node. A node
whose read-back gets no answer is kept as unanswered, asked again at the end, and reported.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from ..model import Line, Scene
from .diff import Change, diff
from .osc import (
    _RECV_BUF, X32_PORT, OscError, decode_message, desk_address, encode_message, node_line,
)

RENEW = 8.0        # /xremote lapses after 10 s
DEBOUNCE = 0.15
MAX_WAIT = 0.5     # a blocked recv delays a Ctrl-C by up to this long on some platforms


class Transport(Protocol):
    def send(self, addr: str, args: Sequence[str | int | float] = ()) -> None: ...

    def recv(self, timeout: float) -> tuple[str, list] | None: ...

    def drain(self) -> list[tuple[str, list]]: ...


@dataclass(frozen=True)
class Changed:
    at: float       # wall-clock epoch seconds of the first push that reported it
    path: str
    before: str
    after: str


@dataclass
class Summary:
    net: list[Change]     # start snapshot -> end, path by path
    logged: int           # changes reported while watching
    transient: int        # paths that changed and came back to their start line
    ignored: int          # pushed addresses with no watched node
    unanswered: list[str]  # last change never read back, in scene order; not in net


def owner(addr: str, nodes: set[str] | dict[str, str]) -> str | None:
    """The longest '/'-prefix of ``addr`` that is a node, or None."""
    path = addr
    while path:
        if path in nodes:
            return path
        path = path.rpartition("/")[0]
    return None


class Subscription:
    """``/xremote`` sent on creation. Calling it renews the subscription once ``RENEW`` has
    passed and keeps every push already waiting, stamped (monotonic, wall) when kept — call
    it between the queries of a start pull, then hand ``backlog`` to ``Watch.run``."""

    def __init__(self, transport: Transport, *, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time):
        self._transport, self._clock, self._wall = transport, clock, wall
        self.backlog: list[tuple[str, list, float, float]] = []
        transport.send("/xremote")
        self._last = clock()

    def __call__(self) -> None:
        now = self._clock()
        if now - self._last >= RENEW:
            self._transport.send("/xremote")
            self._last = now
        at = self._wall()
        self.backlog.extend((addr, args, now, at) for addr, args in self._transport.drain())


def subscribe(transport: Transport, *, clock: Callable[[], float] = time.monotonic,
              wall: Callable[[], float] = time.time) -> Subscription:
    return Subscription(transport, clock=clock, wall=wall)


class Watch:
    """One watch session. ``reference`` names the nodes a leaf may belong to; ``start`` is
    the desk's state for them, and only nodes it holds are queried."""

    def __init__(self, reference: Scene, start: Scene, *, debounce: float = DEBOUNCE,
                 renew: float = RENEW, reply_timeout: float = 0.5):
        self._nodes = {ln.path for ln in reference.lines if ln.path.startswith("/")}
        self._start_scene = start
        self._start = {ln.path: ln.raw for ln in start.lines if ln.path.startswith("/")}
        self._lines = dict(self._start)
        self._dirty: dict[str, float] = {}               # node -> first leaf since its query
        self._since: dict[str, float] = {}   # node -> wall time of its first leaf since queried
        self._asked: dict[str, float] = {}   # node -> that time, for the query now out
        self._pending: dict[str, tuple[float, int]] = {}  # node -> (sent at, tries)
        self._debounce, self._renew, self._reply_timeout = debounce, renew, reply_timeout
        self._touched: set[str] = set()
        self._unanswered: set[str] = set()
        self.logged = 0
        self.ignored = 0

    def run(self, transport: Transport, *, seconds: float | None = None,
            clock: Callable[[], float] = time.monotonic,
            wall: Callable[[], float] = time.time,
            backlog: Sequence[tuple[str, list, float, float]] = ()) -> Iterator[Changed]:
        """Subscribe and yield each change until ``seconds`` pass (forever when None).
        ``backlog`` is a ``Subscription``'s pushes from before the start snapshot finished."""
        for addr, _, kept, at in backlog:
            if addr not in ("node", "/node"):
                self._leaf(addr, kept, at)
        began = clock()
        end = None if seconds is None else began + seconds
        transport.send("/xremote")
        renewed = began
        while True:
            now = clock()
            if end is not None and now >= end:
                yield from self.flush(transport, clock=clock, wall=wall)
                return
            if now - renewed >= self._renew:
                transport.send("/xremote")
                renewed = now
            self._ask(transport, now, self._debounce)
            wake = [renewed + self._renew, *(t + self._debounce for t in self._dirty.values()),
                    *(t + self._reply_timeout for t, _ in self._pending.values())]
            if end is not None:
                wake.append(end)
            msg = transport.recv(min(max(min(wake) - now, 0.001), MAX_WAIT))
            if msg is None:
                continue
            addr, args = msg
            if addr in ("node", "/node"):
                changed = self._reply(args, wall())
                if changed is not None:
                    yield changed
            else:
                self._leaf(addr, clock(), wall())

    def flush(self, transport: Transport, *, clock: Callable[[], float] = time.monotonic,
              wall: Callable[[], float] = time.time) -> Iterator[Changed]:
        """Read back every node a leaf marked that has not been read since, and every node
        still unanswered, without waiting out a debounce — call it after an interrupted
        ``run``. Pushes arriving now are past the end and dropped. Bounded by two reply
        timeouts; a node still unread then stays unanswered."""
        deadline = clock() + 2 * self._reply_timeout
        for node in self._unanswered - self._pending.keys():
            self._dirty.setdefault(node, clock())
        try:
            while self._dirty or self._pending:
                now = clock()
                if now >= deadline:
                    break
                self._ask(transport, now, 0.0)
                wake = [deadline, *(t + self._reply_timeout for t, _ in self._pending.values())]
                msg = transport.recv(min(max(min(wake) - now, 0.001), MAX_WAIT))
                if msg is not None and msg[0] in ("node", "/node"):
                    changed = self._reply(msg[1], wall())
                    if changed is not None:
                        yield changed
        finally:
            self._unanswered |= self._dirty.keys() | self._pending.keys()
            self._dirty.clear()
            self._pending.clear()

    def _leaf(self, addr: str, now: float, at: float) -> None:
        node = owner(addr, self._nodes)
        if node is None or node not in self._lines:
            self.ignored += 1
            return
        self._since.setdefault(node, at)
        if node not in self._dirty:
            self._dirty[node] = now

    def _ask(self, transport: Transport, now: float, debounce: float) -> None:
        for node, since in list(self._dirty.items()):
            if now - since >= debounce:
                del self._dirty[node]
                if node in self._since:
                    self._asked[node] = self._since.pop(node)
                self._pending[node] = (now, 1)   # before the send, so a failed send stays pending
                transport.send("/node", [node.lstrip("/")])
        for node, (sent, tries) in list(self._pending.items()):
            if now - sent >= self._reply_timeout:
                if tries > 1:
                    del self._pending[node]
                    self._unanswered.add(node)
                else:
                    self._pending[node] = (now, tries + 1)
                    transport.send("/node", [node.lstrip("/")])

    def _reply(self, args: list, at: float) -> Changed | None:
        line = node_line(args)
        path = None if line is None else line.split(" ", 1)[0]
        if path not in self._lines:
            return None
        self._pending.pop(path, None)
        self._unanswered.discard(path)
        at = self._asked.pop(path, at)
        before = self._lines[path]
        if line == before:
            return None
        self._lines[path] = line
        self._touched.add(path)
        self.logged += 1
        return Changed(at, path, before, line)

    def end_scene(self) -> Scene:
        """The start snapshot with every node's latest line: the desk as the watch last saw it."""
        start = self._start_scene
        return Scene([ln if not ln.path.startswith("/") or self._lines[ln.path] == ln.raw
                      else Line.parse(self._lines[ln.path]) for ln in start.lines],
                     start.trailing_newline)

    def summary(self) -> Summary:
        """An unanswered node's last line may be stale, so it is in neither ``net`` nor
        ``transient``."""
        unknown = self._unanswered | self._dirty.keys() | self._pending.keys()
        transient = sum(1 for p in self._touched - unknown if self._lines[p] == self._start[p])
        net = [c for c in diff(self._start_scene, self.end_scene()) if c.path not in unknown]
        return Summary(net, self.logged, transient, self.ignored,
                       [ln.path for ln in self._start_scene.lines if ln.path in unknown])


class UdpTransport:
    """The watch's socket. ``/xremote`` pushes and ``/node`` replies both come back to the
    port that asked, so one socket carries the whole session."""

    def __init__(self, ip: str, port: int = X32_PORT):
        self._to = (ip, port)
        self._peer = desk_address(ip)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __enter__(self) -> UdpTransport:
        return self

    def __exit__(self, *exc) -> None:
        self._sock.close()

    def send(self, addr: str, args: Sequence[str | int | float] = ()) -> None:
        self._sock.sendto(encode_message(addr, args), self._to)

    def recv(self, timeout: float) -> tuple[str, list] | None:
        """The next message from the desk within ``timeout``; anyone else's is dropped."""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            self._sock.settimeout(remaining)
            try:
                data, sender = self._sock.recvfrom(_RECV_BUF)
            except socket.timeout:
                return None
            if sender[0] != self._peer:
                continue
            try:
                return decode_message(data)
            except OscError:
                continue
        return None

    def drain(self) -> list[tuple[str, list]]:
        """Every message from the desk already waiting, without blocking."""
        waiting = []
        self._sock.setblocking(False)
        try:
            while True:
                try:
                    data, sender = self._sock.recvfrom(_RECV_BUF)
                except (BlockingIOError, InterruptedError):
                    return waiting
                if sender[0] != self._peer:
                    continue
                try:
                    waiting.append(decode_message(data))
                except OscError:
                    continue
        finally:
            self._sock.setblocking(True)
