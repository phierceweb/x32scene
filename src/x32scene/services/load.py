"""Load a scene or snippet onto the running desk: write each line the desk does not hold,
read the file back, and write again until the desk holds it.

A ``/`` root write sets any node from its scene line, the desk's actions and preferences
included, and ignores every recall scope. So only the parameters a scene or snippet carries
are written, never a group the file's own header leaves out. A line can go missing on the
way, and the desk keeps some values on its own grid, so nothing is believed until it is read
back.
"""

from __future__ import annotations

import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..model import Line, Scene
from . import osc
from .diff import Change
from .headers import decode_header
from .snippets import read_header

GAP = 0.01        # between writes, doubled each pass
SETTLE = 0.5      # after an FX type line: the change resets the slot, and its par line follows
READ_BACK = 0.2   # after the last write of a pass, before the desk is asked
_FX_TYPE = re.compile(r"^/fx/[1-8]$")
SCENE_ROOTS = frozenset({"config", "ch", "auxin", "fxrtn", "bus", "mtx", "main", "dca", "fx",
                         "outputs", "headamp"})


def refuse_unloadable(target: Scene) -> None:
    """Raise ValueError when ``target`` is not a file to put on a desk: not a scene or a
    snippet, a body line that is not a scene or snippet parameter, no parameter lines, a
    group its header marks safe, a snippet line outside its own masks, or a last line
    without its newline (a copy cut mid-token)."""
    head = decode_header(target.lines[0].raw) if target.lines else None
    if head is None or head["kind"] not in ("scene", "snippet"):
        what = "no header" if head is None else f"a {head['kind']} header"
        raise ValueError(f"load takes a scene or a snippet; this has {what}")
    body = [(n, ln) for n, ln in enumerate(target.lines[1:], start=2) if ln.raw.strip()]
    for n, ln in body:
        if not ln.path.startswith("/"):
            raise ValueError(f"line {n} is not a parameter line: {ln.raw!r}")
        if ln.path.split("/")[1] not in SCENE_ROOTS:
            raise ValueError(f"line {n}: {ln.path} is not a scene or snippet parameter, and "
                             "load writes nothing else")
    if not body:
        raise ValueError("nothing to load, no parameter lines")
    if head.get("safes"):
        raise ValueError(f"the header marks {', '.join(head['safes'])} safe, which the "
                         "desk's recall skips and a load would not")
    snip = read_header(target.lines[0].raw) if head["kind"] == "snippet" else None
    for n, ln in body:
        if snip is not None and snip.covers(ln.path) is False:
            raise ValueError(f"line {n}: {ln.path} is outside the snippet's own masks, which "
                             "the desk's recall skips and a load would not")
    if not target.trailing_newline:
        raise ValueError("the last line has no newline, so the file may be cut short")


@dataclass
class LoadResult:
    passes: list[list[str]] = field(default_factory=list)   # the paths written, per pass
    stuck: list[Change] = field(default_factory=list)       # file line -> the desk's, after the last pass
    unanswered: list[str] = field(default_factory=list)     # never read back: not verified
    error: str | None = None      # the desk stopped answering, or a send failed, after writes went out
    interrupted: bool = False     # Ctrl-C after writes went out

    @property
    def written(self) -> int:
        return sum(len(p) for p in self.passes)

    @property
    def ok(self) -> bool:
        return not (self.stuck or self.unanswered or self.error or self.interrupted)


def holds(desk: Line | None, want: Line) -> bool:
    """The desk's line carries the file's values; the padding is the desk's own."""
    return desk is not None and desk.args == want.args


def load_scene(target: Scene, ip: str, *, port: int = osc.X32_PORT, timeout: float = 0.5,
               passes: int = 3, sleep: Callable[[float], None] | None = None) -> LoadResult:
    """Write ``target`` onto the desk at ``ip`` until a read-back of every line holds it,
    ``passes`` times at most. Every path is read back after each pass, since a write can
    change another (a linked pair's mirror, an FX type resetting its parameters). A path the
    desk did not answer at the start is written and read back once: one it never answers is
    unanswered, not written or asked again. Raises ValueError, before the desk is contacted,
    for a target ``refuse_unloadable`` refuses, and OscError when the desk does not answer
    the first read; a desk that stops answering,
    a failed send or Ctrl-C after writes went out ends the load with ``error`` or
    ``interrupted`` set on the result, its passes kept."""
    sleep = sleep or time.sleep
    refuse_unloadable(target)
    want = {ln.path: ln for ln in target.lines if ln.path.startswith("/")}
    # fail_fast=1: a single silent path probes the desk, so a one-line file never writes blind
    live, missing = osc.pull_scene_like(target, ip, port=port, timeout=timeout, fail_fast=1)
    unknown = {"/" + p for p in missing}
    todo = [p for p in want if not holds(live.get(p), want[p])]
    result = LoadResult()
    got: dict[str, Line] = {}
    gap = GAP
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for _ in range(passes):
                if not todo:
                    break
                sent: list[str] = []
                result.passes.append(sent)   # grows per write, so a failure keeps what went out
                for path in todo:
                    sock.sendto(osc.encode_message("/", [want[path].raw]), (ip, port))
                    sent.append(path)
                    sleep(SETTLE if _FX_TYPE.match(path) else gap)
                sleep(READ_BACK)
                ask = [p.lstrip("/") for p in want if p not in result.unanswered]
                lines, _ = osc.pull_lines(ip, ask, port=port, timeout=timeout, fail_fast=1,
                                          give_up=osc.GIVE_UP)
                got = {ln.path: ln for ln in map(Line.parse, lines)}
                result.unanswered += [p for p in todo if p in unknown and p not in got]
                unknown -= set(todo)
                todo = [p for p in want if p not in result.unanswered
                        and not holds(got.get(p), want[p])]
                gap *= 2
    except (osc.OscError, OSError) as e:
        result.error = str(e)
        return result
    except KeyboardInterrupt:
        result.interrupted = True
        return result
    result.stuck = [Change(p, want[p].raw, got[p].raw) for p in todo if p in got]
    result.unanswered += [p for p in todo if p not in got]
    return result
