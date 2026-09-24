"""Watch the running desk: every scene change another client or the surface makes, as it
happens. Read-only — the only messages sent are ``/xremote`` and ``/node``.

After ``/xremote`` the desk pushes one message per changed leaf (``/ch/29/mix/fader``) for
ten seconds. Each leaf marks the reference node that owns it dirty; a dirty node is asked
for its whole scene-format line with ``/node`` at most once per debounce window, and a
change is reported when that line differs from the last one reported for the node. A
read-back with no reply within the retry interval is asked once more; a node silent to both
is kept as unanswered, asked again at the end, and reported. The retry interval and which
read-back a reply answers are ``watch_readback``'s.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ..model import Line, Scene
from .diff import Change, diff
from .osc import node_line
from .watch_readback import LATE as LATE, Readbacks, RoundTrip

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
    the desk's state for them, and only nodes it holds are queried. ``reply_timeout`` is the
    retry interval's floor; ``round_trips``, from ``pull_scene_like(..., round_trips=)``,
    starts it from what the start pull measured."""

    def __init__(self, reference: Scene, start: Scene, *, debounce: float = DEBOUNCE,
                 renew: float = RENEW, reply_timeout: float = 0.5,
                 round_trips: Sequence[float | None] = ()):
        self._nodes = {ln.path for ln in reference.lines if ln.path.startswith("/")}
        self._start_scene = start
        self._start = {ln.path: ln.raw for ln in start.lines if ln.path.startswith("/")}
        self._lines = dict(self._start)
        self._dirty: dict[str, float] = {}               # node -> first leaf since its query
        self._since: dict[str, float] = {}   # node -> wall time of its first leaf since queried
        self._asked: dict[str, float] = {}   # node -> that time, for the query now out
        self._pending: dict[str, tuple[float, int, float]] = {}  # node -> (due, tries, its timer)
        self._seq: dict[str, int] = {}                        # node -> leaves seen
        self._debounce, self._renew = debounce, renew
        self._timer = RoundTrip(reply_timeout)
        self._timer.seed(round_trips)
        self._readbacks = Readbacks(self._timer)
        self._touched: set[str] = set()
        self._unanswered: set[str] = set()
        self.logged = 0
        self.ignored = 0

    def run(self, transport: Transport, *, seconds: float | None = None,
            clock: Callable[[], float] = time.monotonic,
            wall: Callable[[], float] = time.time,
            backlog: Sequence[tuple[str, list, float, float]] = (),
            pulled: Mapping[str, float] | None = None) -> Iterator[Changed]:
        """Subscribe and yield each change until ``seconds`` pass (forever when None).
        ``backlog`` is a ``Subscription``'s pushes from before the start snapshot finished;
        ``pulled`` maps a node to when that snapshot first asked for it, on ``clock``, and a
        push kept before then is already in the start."""
        pulled = pulled or {}
        for addr, _, kept, at in backlog:
            node = owner(addr, self._nodes)
            if addr in ("node", "/node") or kept < pulled.get(node, kept):
                continue
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
            wake = [renewed + self._renew, *(p[0] for p in self._pending.values()),
                    *(max(t + self._debounce, self._pending.get(n, (0.0,))[0])
                      for n, t in self._dirty.items())]
            if end is not None:
                wake.append(end)
            msg = transport.recv(min(max(min(wake) - now, 0.001), MAX_WAIT))
            if msg is None:
                continue
            addr, args = msg
            if addr in ("node", "/node"):
                changed = self._reply(args, clock(), wall())
                if changed is not None:
                    yield changed
            else:
                self._leaf(addr, clock(), wall())

    def flush(self, transport: Transport, *, clock: Callable[[], float] = time.monotonic,
              wall: Callable[[], float] = time.time) -> Iterator[Changed]:
        """Read back every node a leaf marked that has not been read since, and every node
        still unanswered, without waiting out a debounce — call it after an interrupted
        ``run``. Pushes arriving now are past the end and dropped. Bounded by two round-trip
        estimates, and a read-back still out waits one at most; a node still unread then
        stays unanswered."""
        start = clock()
        deadline = start + 2 * self._timer.estimate
        for node, (due, tries, sent_with) in self._pending.items():
            if tries:
                self._pending[node] = (min(due, start + self._timer.estimate), tries, sent_with)
        for node in self._unanswered - self._pending.keys():
            self._dirty.setdefault(node, start)
        try:
            while self._dirty or self._pending:
                now = clock()
                if now >= deadline:
                    break
                self._ask(transport, now, 0.0, end=True)
                wake = [deadline, *(p[0] for p in self._pending.values())]
                msg = transport.recv(min(max(min(wake) - now, 0.001), MAX_WAIT))
                if msg is not None and msg[0] in ("node", "/node"):
                    changed = self._reply(msg[1], clock(), wall())
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
        self._seq[node] = self._seq.get(node, 0) + 1
        if node not in self._dirty:
            self._dirty[node] = now

    def _ask(self, transport: Transport, now: float, debounce: float, *,
             end: bool = False) -> None:
        for node, since in list(self._dirty.items()):
            due, tries, sent_with = self._pending.get(node, (now, 0, 0.0))
            if now - since >= debounce and now >= due:
                if tries:
                    self._timer.timed_out(sent_with)
                del self._dirty[node]
                if node in self._since:
                    self._asked[node] = self._since.pop(node)
                self._query(transport, node, now, 1, end=end)
        for node, (due, tries, sent_with) in list(self._pending.items()):
            if now >= due:
                if tries:
                    self._timer.timed_out(sent_with)
                if tries > 1:
                    del self._pending[node]
                    self._unanswered.add(node)
                else:
                    if node in self._since:   # the retry reads these leaves; an unsettled date stays
                        self._asked.setdefault(node, self._since.pop(node))
                    self._query(transport, node, now, tries + 1, end=end)

    def _query(self, transport: Transport, node: str, now: float, tries: int, *,
               end: bool = False) -> None:
        # the end read-back waits out the round trip, not a back-off that loss can cause
        timer = self._timer.estimate if end else self._timer.rto
        self._pending[node] = (now + timer, tries, timer)  # first: a failed send stays pending
        self._readbacks.sent(node, now, self._seq.get(node, 0))
        transport.send("/node", [node.lstrip("/")])

    def _reply(self, args: list, now: float, at: float) -> Changed | None:
        line = node_line(args)
        path = None if line is None else line.split(" ", 1)[0]
        if path not in self._lines:
            return None
        settles, again = self._readbacks.credit(path, line, self._lines[path], now)
        if again is not None:
            self._pending[path] = (again, 0, 0.0)
        if not settles:
            if again is None and line != self._lines[path]:
                # after a reply later than its lapse, each reply answers the read-back before
                # the one it is credited to, and the last answers nothing asked for
                self._dirty.setdefault(path, now)
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
