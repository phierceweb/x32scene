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
from . import osc, osc_pull
from .diff import Change
from .headers import decode_header
from .load_keep import Keep
from .snippets import read_header

GAP = 0.01        # between writes, doubled each pass
SETTLE = 0.5      # after a line the desk answers with writes of its own (an FX type resets
                  # the slot's par; a link copies and pans the pair for ~0.1 s), before ours
READ_BACK = 0.2   # after the last write of a pass, before the desk is asked
_SETTLES = re.compile(r"^/(fx/[1-8]|config/(ch|aux|fx|bus|mtx)link)$")
SCENE_ROOTS = frozenset({"config", "ch", "auxin", "fxrtn", "bus", "mtx", "main", "dca", "fx",
                         "outputs", "headamp"})


class Unloadable(ValueError):
    """A file, or what it keeps, that ``load_scene`` refuses before anything is written."""


def refuse_unloadable(target: Scene) -> None:
    """Raise ValueError when ``target`` is not a file to put on a desk: not a scene or a
    snippet, a body line that is not a scene or snippet parameter, no parameter lines, a
    group its header marks safe, a snippet line outside its own masks, or a last line
    without its newline (a copy cut mid-token)."""
    head = decode_header(target.lines[0].raw) if target.lines else None
    if head is None or head["kind"] not in ("scene", "snippet"):
        what = "no header" if head is None else f"a {head['kind']} header"
        raise Unloadable(f"load takes a scene or a snippet; this has {what}")
    body = [(n, ln) for n, ln in enumerate(target.lines[1:], start=2) if ln.raw.strip()]
    for n, ln in body:
        if not ln.path.startswith("/"):
            raise Unloadable(f"line {n} is not a parameter line: {ln.raw!r}")
        if ln.path.split("/")[1] not in SCENE_ROOTS:
            raise Unloadable(f"line {n}: {ln.path} is not a scene or snippet parameter, and "
                             "load writes nothing else")
    if not body:
        raise Unloadable("nothing to load, no parameter lines")
    if head.get("safes"):
        raise Unloadable(f"the header marks {', '.join(head['safes'])} safe, which the "
                         "desk's recall skips and a load would not")
    snip = read_header(target.lines[0].raw) if head["kind"] == "snippet" else None
    for n, ln in body:
        if snip is not None and snip.covers(ln.path) is False:
            raise Unloadable(f"line {n}: {ln.path} is outside the snippet's own masks, which "
                             "the desk's recall skips and a load would not")
    if not target.trailing_newline:
        raise Unloadable("the last line has no newline, so the file may be cut short")


@dataclass
class LoadResult:
    passes: list[list[str]] = field(default_factory=list)   # the paths written, per pass
    stuck: list[Change] = field(default_factory=list)       # file line -> the desk's, after the last pass
    unanswered: list[str] = field(default_factory=list)     # not verified: a read missed it
    kept: list[tuple[str, list[str]]] = field(default_factory=list)   # (what, paths) left as the desk holds them
    moved: list[Change] = field(default_factory=list)       # kept paths that changed during the load
    error: str | None = None      # the desk stopped answering, or a send failed, after writes went out
    interrupted: bool = False     # Ctrl-C after writes went out

    @property
    def written(self) -> int:
        return sum(len(p) for p in self.passes)

    @property
    def ok(self) -> bool:
        return not (self.stuck or self.unanswered or self.error or self.interrupted
                    or self.moved)


def holds(desk: Line | None, want: Line) -> bool:
    """The desk's line carries the file's values; the padding is the desk's own."""
    return desk is not None and desk.args == want.args


def _resolve_keep(keep: Keep, target: Scene, live: Scene, ip: str, port: int,
                  timeout: float) -> list[tuple[str, list[str]]]:
    more, _ = osc_pull.pull_lines(ip, [p.lstrip("/") for p in keep.desk_paths(target)
                                  if live.get(p) is None], port=port, timeout=timeout)
    desk = Scene([ln for ln in live.lines if ln.path.startswith("/")]
                 + [Line.parse(raw) for raw in more])
    if silent := [p for p in Keep.REQUIRED if desk.get(p) is None]:
        raise osc.OscError(f"the desk did not answer {', '.join(silent)}, which --keep "
                           "needs to know what a write mirrors")
    try:
        return keep.resolve(target, desk)
    except ValueError as e:
        raise Unloadable(str(e)) from None


def load_scene(target: Scene, ip: str, *, port: int = osc.X32_PORT, timeout: float = 0.5,
               passes: int = 3, sleep: Callable[[float], None] | None = None,
               keep: Keep | None = None) -> LoadResult:
    """Write ``target`` onto the desk at ``ip`` until a read-back of every line holds it,
    ``passes`` times at most. Every path is read back after each pass, since a write can
    change another (a linked pair's mirror, an FX type resetting its parameters). A path the
    desk did not answer at the start is written and read back once: one it never answers is
    unanswered, not written or asked again. ``keep`` names paths left as the desk holds them:
    never written, read back with the rest, one that changed during the load ``moved`` and
    one the first read or the last missed ``unanswered``. Raises Unloadable, before the desk
    is contacted, for a target ``refuse_unloadable`` refuses or what ``Keep.check`` refuses, and
    before any write for what ``Keep.resolve`` refuses; OscError when the desk does not
    answer the first read, or with ``keep`` a line of ``Keep.REQUIRED``; a desk that stops
    answering, a failed send or Ctrl-C after writes went out ends the load with ``error``
    or ``interrupted`` set on the result, its passes kept."""
    sleep = sleep or time.sleep
    try:
        refuse_unloadable(target)
        if keep is not None:
            keep.check(target)
    except ValueError as e:
        raise Unloadable(str(e)) from None
    want = {ln.path: ln for ln in target.lines if ln.path.startswith("/")}
    # fail_fast=1: a single silent path probes the desk, so a one-line file never writes blind
    live, missing = osc_pull.pull_scene_like(target, ip, port=port, timeout=timeout, fail_fast=1)
    unknown = {"/" + p for p in missing}
    result = LoadResult()
    kept: set[str] = set()
    if keep is not None:
        result.kept = _resolve_keep(keep, target, live, ip, port, timeout)
        kept = {p for _, ps in result.kept for p in ps}
    todo = [p for p in want if p not in kept and not holds(live.get(p), want[p])]
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
                    sleep(SETTLE if _SETTLES.match(path) else gap)
                sleep(READ_BACK)
                ask = [p.lstrip("/") for p in want if p not in result.unanswered]
                lines, _ = osc_pull.pull_lines(ip, ask, port=port, timeout=timeout, fail_fast=1,
                                          give_up=osc_pull.GIVE_UP)
                got = {ln.path: ln for ln in map(Line.parse, lines)}
                result.unanswered += [p for p in todo if p in unknown and p not in got]
                unknown -= set(todo)
                todo = [p for p in want if p not in kept and p not in result.unanswered
                        and not holds(got.get(p), want[p])]
                gap *= 2
    except (osc.OscError, OSError) as e:
        result.error = str(e)
        return result
    except KeyboardInterrupt:
        result.interrupted = True
        return result
    result.stuck = [Change(p, want[p].raw, got[p].raw) for p in todo if p in got]
    last = got if result.passes else {p: ln for p in kept if (ln := live.get(p)) is not None}
    result.moved = [Change(p, was.raw, last[p].raw) for p in want
                    if p in kept and p in last and (was := live.get(p)) is not None
                    and not holds(last[p], was)]
    result.unanswered += [p for p in todo if p not in got]
    result.unanswered += [p for p in want if p in kept
                          and (p not in last or live.get(p) is None)]
    return result
