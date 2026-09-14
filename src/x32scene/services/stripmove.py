"""Move channel strips as one permutation of channels 1-32: every ``/ch/NN`` line travels
whole, and each value outside the strips that names a channel by number follows it. The
references and what is refused are in ``docs/format.md`` (Channel references)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from ..model import Line, Scene
from .diff import diff
from .stripmove_refs import RemappedRef, reference_problems, remap_references

CHANNELS = 32
_CH = re.compile(r"^/ch/(\d\d)(?=/|$)")


@dataclass
class StripMove:
    """The strips moved as (old, new), every reference rewritten, and each changed path in
    scene order."""

    moves: list[tuple[int, int]] = field(default_factory=list)
    remapped: list[RemappedRef] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)


def swap_mapping(a: int, b: int) -> dict[int, int]:
    """Channels ``a`` and ``b`` trade places."""
    return {a: b, b: a}


def move_mapping(frm: int, to: int) -> dict[int, int]:
    """Channel ``frm`` lands on ``to``; the strips between shift one place toward ``frm``."""
    if frm < to:
        return {frm: to, **{k: k - 1 for k in range(frm + 1, to + 1)}}
    return {frm: to, **{k: k + 1 for k in range(to, frm)}}


def moved_channels(mapping: dict[int, int]) -> dict[int, int]:
    """``mapping`` without its identity entries, once it is a permutation of the channels
    it names. Raises ValueError naming every way it is not."""
    problems = []
    outside = sorted({c for c in (*mapping, *mapping.values()) if not 1 <= c <= CHANNELS})
    if outside:
        problems.append(f"channel(s) outside 1-{CHANNELS}: {', '.join(map(str, outside))}")
    for ch, n in sorted(Counter(mapping.values()).items()):
        if n > 1:
            problems.append(f"{n} strips would land on ch{ch:02d}")
    gaps = [f"ch{c:02d} would be left empty" for c in sorted(set(mapping) - set(mapping.values()))]
    gaps += [f"ch{c:02d}'s own strip is not moved anywhere"
             for c in sorted(set(mapping.values()) - set(mapping))]
    if gaps:
        problems.append("not a permutation of the channels it names: " + ", ".join(gaps))
    if problems:
        raise ValueError("cannot move the strips: " + "; ".join(problems))
    return {o: n for o, n in mapping.items() if o != n}


def _strip_lines(scene: Scene) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for i, ln in enumerate(scene.lines):
        m = _CH.match(ln.path)
        if m:
            out.setdefault(int(m.group(1)), []).append(i)
    return out


def _strip_problems(scene: Scene, perm: dict[int, int], lines: dict[int, list[int]]) -> list[str]:
    problems = [f"no /ch/{c:02d}/config" for c in sorted(perm)
                if scene.get(f"/ch/{c:02d}/config") is None]
    seen = set()
    for old, new in sorted(perm.items()):
        subs = [[scene.lines[i].path[6:] for i in lines.get(c, [])] for c in (old, new)]
        if subs[0] != subs[1] and frozenset((old, new)) not in seen:
            seen.add(frozenset((old, new)))
            problems.append(f"ch{old:02d} and ch{new:02d} carry different lines")
    return problems


def permute_channels(scene: Scene, mapping: dict[int, int]) -> StripMove:
    """Move each channel ``old`` of ``{old: new}`` to ``new``, in place.

    The mapping must be a permutation of the channels it names; identity entries are
    ignored. Every check runs before a line changes.

    Raises:
        ValueError: naming every problem — not a permutation, a channel outside 1-32, strips
            carrying different lines, a missing ``/ch/NN/config`` or ``/config/chlink``, a
            stereo-linked pair split or reversed, a key source naming a moving channel, an
            automix group crossing channels 1-8. The scene is untouched.
        RuntimeError: the rebuilt scene differs outside the report (a bug).
    """
    perm = moved_channels(mapping)
    if not perm:
        return StripMove()
    lines = _strip_lines(scene)
    problems = _strip_problems(scene, perm, lines) + reference_problems(scene, perm)
    if problems:
        raise ValueError("cannot move the strips: " + "; ".join(problems))
    raws = {i: ln.raw for i, ln in enumerate(scene.lines)}
    for old, new in perm.items():
        for src, dst in zip(lines[old], lines[new], strict=True):
            raws[dst] = f"/ch/{new:02d}{scene.lines[src].raw[6:]}"
    candidate = Scene([Line.parse(r) for r in raws.values()], scene.trailing_newline)
    remapped = remap_references(candidate, perm)
    changed = [b.path for a, b in zip(scene.lines, candidate.lines, strict=True) if a.raw != b.raw]
    move = StripMove(sorted(perm.items()), remapped, changed)
    bad = unexpected_changes(scene, candidate, move)
    if bad:
        raise RuntimeError(f"strip move rebuilt lines outside its report: {', '.join(bad)}")
    for ln, new_ln in zip(scene.lines, candidate.lines, strict=True):
        if ln.raw != new_ln.raw:
            ln.raw, ln.args, ln.dirty = new_ln.raw, new_ln.args, True
    return move


def unexpected_changes(before: Scene, after: Scene, move: StripMove) -> list[str]:
    """Paths whose change ``move`` does not account for: a strip line that is not its source
    strip's line, a reference line whose changed fields differ from the report, or a
    reported reference that did not change."""
    inverse = {new: old for old, new in move.moves}
    fields: dict[str, dict[int, tuple[str, str]]] = {}
    for r in move.remapped:
        fields.setdefault(r.path, {})[r.field] = (r.before, r.after)
    bad, seen = set(), set()
    for c in diff(before, after):
        seen.add(c.path)
        m = _CH.match(c.path)
        if m and int(m.group(1)) in inverse:
            src = before.get(f"/ch/{inverse[int(m.group(1))]:02d}{c.path[6:]}")
            if src is None or c.after != f"{c.path[:6]}{src.raw[6:]}":
                bad.add(c.path)
            continue
        if c.path not in fields or c.before is None or c.after is None:
            bad.add(c.path)
            continue
        a, b = Line.parse(c.before).args, Line.parse(c.after).args
        if len(a) != len(b) or fields[c.path] != {
                i + 1: (x, y) for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y}:
            bad.add(c.path)
    bad.update(p for p in fields if p not in seen)
    return sorted(bad)
