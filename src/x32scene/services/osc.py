"""Live X32 state over OSC/UDP — ``/node`` queries against the running desk.

A ``/node`` reply carries one line in exactly the scene-file format, so a live pull
assembles ``.scn`` text and the whole toolkit (Scene, diff, preflight, audit) applies
unchanged. The desk answers on UDP 10023; unanswered paths are reported, not raised —
consoles skip /node paths their firmware lacks, so absence is normal, not an error.
"""

from __future__ import annotations

import socket
import struct
import time
from collections.abc import Callable, Sequence

from ..model import HEADER_RE, Scene

X32_PORT = 10023
_RECV_BUF = 65536
_BETWEEN_EVERY = 0.5
GIVE_UP = 8       # unanswered paths in a row before a scene pull checks the desk is still there


class OscError(RuntimeError):
    """Malformed OSC datagram."""


def desk_address(ip: str) -> str:
    """The numeric address a reply has to come from. Accepts a hostname.

    An unconnected UDP socket hears whatever the network hands it, and a reply here
    becomes console state. Address only, not port: the reply port is a firmware detail
    not pinned down across models, and rejecting a real desk would be worse.
    """
    return socket.gethostbyname(ip)


def _pad(b: bytes) -> bytes:
    return b + b"\x00" * (4 - len(b) % 4)


def encode_message(addr: str, args: Sequence[str | int | float] = ()) -> bytes:
    tags = ","
    payload = b""
    for a in args:
        if isinstance(a, bool):
            raise OscError("bool args are not part of the X32 dialect")
        if isinstance(a, int):
            tags += "i"
            payload += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"
            payload += struct.pack(">f", a)
        else:
            tags += "s"
            payload += _pad(str(a).encode("utf-8"))
    return _pad(addr.encode("ascii")) + _pad(tags.encode("ascii")) + payload


def _read_padded_string(data: bytes, pos: int) -> tuple[str, int]:
    end = data.index(b"\x00", pos)
    s = data[pos:end].decode("utf-8", "replace")
    return s, pos + ((end - pos) // 4 + 1) * 4


def decode_message(data: bytes) -> tuple[str, list]:
    try:
        addr, pos = _read_padded_string(data, 0)
        tags, pos = _read_padded_string(data, pos)
    except ValueError as e:
        raise OscError(f"truncated OSC datagram: {data[:32]!r}") from e
    args: list = []
    try:
        for t in tags.lstrip(","):
            if t == "s":
                s, pos = _read_padded_string(data, pos)
                args.append(s)
            elif t == "i":
                args.append(struct.unpack_from(">i", data, pos)[0])
                pos += 4
            elif t == "f":
                args.append(struct.unpack_from(">f", data, pos)[0])
                pos += 4
            elif t == "b":   # blob: big-endian length, then the bytes, padded to 4
                n = struct.unpack_from(">i", data, pos)[0]
                args.append(bytes(data[pos + 4:pos + 4 + n]))
                pos += 4 + ((n + 3) // 4) * 4
            else:
                raise OscError(f"unsupported OSC type tag {t!r}")
    except (ValueError, struct.error) as e:
        raise OscError(f"truncated OSC datagram: {data[:32]!r}") from e
    return addr, args


def node_line(args: list) -> str | None:
    """The scene-format line a ``/node`` reply carries, or None when it is not one line."""
    if not args:
        return None
    line = str(args[0]).removesuffix("\n")
    return None if "\n" in line or "\r" in line else line


def pull_lines(ip: str, paths: Sequence[str], *, port: int = X32_PORT,
               timeout: float = 0.5, retries: int = 1, fail_fast: int | None = None,
               give_up: int | None = None, asked: dict[str, float] | None = None,
               between: Callable[[], object] | None = None) -> tuple[list[str], list[str]]:
    """Query each path via /node. Returns (scene-format lines, unanswered paths).

    A reply line starts with its own path, so late replies land in the right slot rather
    than desynchronizing the capture. ``fail_fast=N`` raises once N paths have gone
    unanswered with nothing received, instead of timing out over every remaining path.
    ``give_up=N`` raises after N unanswered paths in a row unless a late reply landed during
    them or the last path that answered answers again. ``asked`` is filled with each ``/path``'s first send time
    (``time.monotonic``). ``between`` is called at least every half second while a reply is
    awaited.
    """
    if not paths:
        return [], []
    got: dict[str, str] = {}  # "/path" -> scene-format line
    peer = desk_address(ip)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        def query(path: str) -> bool:
            want = "/" + path
            for _ in range(retries + 1):
                if want in got:
                    break
                sock.sendto(encode_message("/node", [path]), (ip, port))
                if asked is not None:
                    asked.setdefault(want, time.monotonic())
                deadline = time.monotonic() + timeout
                while want not in got:
                    if between is not None:
                        between()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    sock.settimeout(min(remaining, _BETWEEN_EVERY))
                    try:
                        data, sender = sock.recvfrom(_RECV_BUF)
                    except socket.timeout:
                        continue
                    if sender[0] != peer:
                        continue      # someone else on the network, not the desk
                    try:
                        addr, args = decode_message(data)
                    except OscError:
                        continue  # one malformed datagram must not abort the pull
                    line = node_line(args) if addr == "node" else None
                    if line is not None:
                        got[line.split(" ", 1)[0]] = line
            return want in got

        def still_there(since: int) -> bool:
            """A reply landed since the run of misses began, or the last path that answered
            answers again."""
            if len(got) > since:
                return True
            if answered is None:
                return False
            kept = got.pop("/" + answered)   # or query() answers from memory
            if query(answered) or len(got) >= since:
                got.setdefault("/" + answered, kept)
                return True
            return False

        answered, misses, since = None, 0, 0
        for n_tried, path in enumerate(paths, start=1):
            heard = len(got)
            if query(path):
                answered, misses = path, 0
                continue
            since = since if misses else heard
            misses += 1
            if fail_fast is not None and not got and n_tried >= fail_fast:
                raise OscError(f"no reply from {ip}:{port} after {n_tried} queries "
                               "— desk off or unreachable?")
            if give_up is not None and misses >= give_up:
                if not still_there(since):
                    raise OscError(f"no reply from {ip}:{port} to {misses} queries in a row "
                                   "— desk off or unreachable?")
                misses = 0
    wanted = ["/" + p for p in paths]
    lines = [got[w] for w in wanted if w in got]
    missing = [p for p, w in zip(paths, wanted, strict=True) if w not in got]
    return lines, missing


def pull_scene_like(reference: Scene, ip: str, *, port: int = X32_PORT,
                    timeout: float = 0.5, retries: int = 1, fail_fast: int | None = 3,
                    give_up: int | None = GIVE_UP, asked: dict[str, float] | None = None,
                    between: Callable[[], object] | None = None) -> tuple[Scene, list[str]]:
    """Pull the running desk's state for every path the reference scene has.

    The reference's header line is carried over verbatim (the desk has no
    header node), so the pulled Scene diffs cleanly against saved scenes.
    """
    paths = [ln.path.lstrip("/") for ln in reference.lines if ln.path.startswith("/")]
    lines, missing = pull_lines(ip, paths, port=port, timeout=timeout,
                                retries=retries, fail_fast=fail_fast, give_up=give_up,
                                asked=asked, between=between)
    header = [reference.lines[0].raw] if (
        reference.lines and HEADER_RE.match(reference.lines[0].path)) else []
    return Scene.parse("\n".join(header + lines) + "\n"), missing


class UdpTransport:
    """The socket of a ``watch`` session. ``/xremote`` pushes and ``/node`` replies both come
    back to the port that asked, so one socket carries the whole session."""

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
