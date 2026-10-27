"""Live X32 state over OSC/UDP — ``/node`` queries against the running desk.

A ``/node`` reply carries one line in exactly the scene-file format, so a live pull
assembles ``.scn`` text and the whole toolkit (Scene, diff, preflight, audit) applies
unchanged. Unanswered paths are reported, not raised — consoles skip /node paths their
firmware lacks, so absence is normal, not an error.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Sequence

from ..model import HEADER_RE, Scene
from .osc import (
    RECV_BUF, X32_PORT, OscError, decode_message, desk_address, encode_message, node_line,
)

_BETWEEN_EVERY = 0.5
GIVE_UP = 8       # unanswered paths in a row before a scene pull checks the desk is still there
PROBE = "ch/01/config"   # a path every X32 and M32 firmware answers


def pull_lines(ip: str, paths: Sequence[str], *, port: int = X32_PORT,
               timeout: float = 0.5, retries: int = 1, fail_fast: int | None = None,
               give_up: int | None = None, asked: dict[str, float] | None = None,
               round_trips: list[float | None] | None = None,
               between: Callable[[], object] | None = None,
               confirm: bool = True) -> tuple[list[str], list[str]]:
    """Query each path via /node. Returns (scene-format lines, unanswered paths).

    A reply line starts with its own path, so late replies land in the right slot rather
    than desynchronizing the capture. ``fail_fast=N`` raises once N paths have gone
    unanswered with nothing received, instead of timing out over every remaining path.
    ``give_up=N`` raises after N unanswered paths in a row unless a late reply landed during
    them or the last path that answered answers again. With ``confirm``, a desk that has
    answered no path yet is asked for ``PROBE`` before either gives up, and one that answers
    is read on: its firmware lacks those paths. A device that answers no ``/node`` answers
    ``/xinfo`` or nothing, and the error says which. ``asked`` is filled with each
    ``/path``'s first send time (``time.monotonic``). ``round_trips`` gets, in reply order,
    each answered path's round trip, or None when it had been asked again before its reply
    came. ``between`` is called at least every half second while a reply is awaited.
    """
    if not paths:
        return [], []
    got: dict[str, str] = {}  # "/path" -> scene-format line
    first: dict[str, float] = asked if asked is not None else {}
    sends: dict[str, int] = {}
    timed: set[str] = set()
    peer = desk_address(ip)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        xinfo, replies = False, 0

        def listen(done: Callable[[], bool]) -> None:
            nonlocal xinfo, replies
            deadline = time.monotonic() + timeout
            while not done():
                if between is not None:
                    between()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                sock.settimeout(min(remaining, _BETWEEN_EVERY))
                try:
                    data, sender = sock.recvfrom(RECV_BUF)
                except socket.timeout:
                    continue
                if sender[0] != peer:
                    continue      # someone else on the network, not the desk
                try:
                    addr, args = decode_message(data)
                except OscError:
                    continue  # one malformed datagram must not abort the pull
                xinfo = xinfo or addr in ("/xinfo", "xinfo")
                line = node_line(args) if addr == "node" else None
                if line is not None:
                    replies += 1
                    key = line.split(" ", 1)[0]
                    if round_trips is not None and key in sends and key not in timed:
                        timed.add(key)
                        round_trips.append(time.monotonic() - first[key]
                                           if sends[key] == 1 else None)
                    got[key] = line

        def query(path: str) -> bool:
            want = "/" + path
            for _ in range(retries + 1):
                if want in got:
                    break
                sock.sendto(encode_message("/node", [path]), (ip, port))
                first.setdefault(want, time.monotonic())
                sends[want] = sends.get(want, 0) + 1
                listen(lambda: want in got)
            return want in got

        def present() -> bool:
            """The desk answers ``/node`` for ``PROBE``, or a late reply lands meanwhile.
            Replies are counted, not paths: an earlier probe's reply already holds its key."""
            heard = replies
            sock.sendto(encode_message("/node", [PROBE]), (ip, port))
            listen(lambda: replies > heard)
            return replies > heard

        def absent(queries: str) -> OscError:
            nonlocal xinfo
            xinfo = False
            sock.sendto(encode_message("/xinfo"), (ip, port))
            listen(lambda: xinfo)
            why = ("answers /xinfo but no /node — not an X32/M32, or not ready?" if xinfo
                   else "desk off or unreachable?")
            return OscError(f"no reply from {ip}:{port} {queries} — {why}")

        def still_there(since: int) -> bool:
            """A reply landed since the run of misses began, or the last path that answered
            answers again."""
            if len(got) > since:
                return True
            if answered is None:
                return confirm and present()
            kept = got.pop("/" + answered)   # or query() answers from memory
            if query(answered) or len(got) >= since:
                got.setdefault("/" + answered, kept)
                return True
            return False

        answered, misses, since, confirmed = None, 0, 0, False
        for n_tried, path in enumerate(paths, start=1):
            heard = len(got)
            if query(path):
                answered, misses = path, 0
                continue
            since = since if misses else heard
            misses += 1
            if fail_fast is not None and not got and n_tried >= fail_fast and not confirmed:
                if not (confirm and present()):
                    raise absent(f"after {n_tried} queries")
                confirmed = True
            if give_up is not None and misses >= give_up:
                if not still_there(since):
                    raise absent(f"to {misses} queries in a row")
                misses = 0
    wanted = ["/" + p for p in paths]
    lines = [got[w] for w in wanted if w in got]
    missing = [p for p, w in zip(paths, wanted, strict=True) if w not in got]
    return lines, missing


def pull_scene_like(reference: Scene, ip: str, *, port: int = X32_PORT,
                    timeout: float = 0.5, retries: int = 1, fail_fast: int | None = 3,
                    give_up: int | None = GIVE_UP, asked: dict[str, float] | None = None,
                    round_trips: list[float | None] | None = None,
                    between: Callable[[], object] | None = None) -> tuple[Scene, list[str]]:
    """Pull the running desk's state for every path the reference scene has.

    The reference's header line is carried over verbatim (the desk has no
    header node), so the pulled Scene diffs cleanly against saved scenes.
    """
    paths = [ln.path.lstrip("/") for ln in reference.lines if ln.path.startswith("/")]
    lines, missing = pull_lines(ip, paths, port=port, timeout=timeout,
                                retries=retries, fail_fast=fail_fast, give_up=give_up,
                                asked=asked, round_trips=round_trips, between=between)
    header = [reference.lines[0].raw] if (
        reference.lines and HEADER_RE.match(reference.lines[0].path)) else []
    return Scene.parse("\n".join(header + lines) + "\n"), missing
