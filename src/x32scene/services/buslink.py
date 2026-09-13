"""Link or unlink a stereo mix-bus pair the way the console does when its link key is
pressed — not what a recall reconciles. What the desk copies and resets is in
``docs/console-behavior.md``."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import zip_longest

from ..model import Line, Scene
from ..tables import LINKCFG, SEND_STRIPS

_FIELD = re.compile(r'(?:^| )( *(?:"[^"]*"|[^ ]+))')
_LINK, _PREFS = "/config/buslink", "/config/linkcfg"
_PAN, _MTX_PAN, _MTX_TAP, _COLOUR = 3, 2, 3, 2
_MATRIX = tuple(range(1, 7))
_BUS_OF = re.compile(r"/(?:bus/(\d\d)|(?:ch|auxin|fxrtn)/\d\d/mix/(\d\d))(?:/|$)")
# strip lines a link copies whole, keyed by the /config/linkcfg preference that gates them
_GATED = {"eq": ("eq", *(f"eq/{b}" for b in range(1, 7))), "dyn": ("dyn", "insert"),
          "fdrmute": ("grp",)}


@dataclass
class BusLinkEdit:
    """The pair toggled, the direction, and every path rewritten, in scene order."""

    odd: int
    even: int
    on: bool
    changed: list[str] = field(default_factory=list)


def _fields(ln: Line) -> list[str]:
    return _FIELD.findall(ln.raw[len(ln.path) + 1:])


def _put(fields: list[str], i: int, tok: str) -> None:
    """Replace a field's token, keeping the padding the desk wrote in front of it."""
    fields[i] = fields[i][:len(fields[i]) - len(fields[i].lstrip(" "))] + tok


def _pan(fields: list[str], i: int, path: str) -> int:
    try:
        return int(fields[i])
    except (IndexError, ValueError):
        raise ValueError(f"{path}: no pan in field {i + 1}") from None


class _Plan:
    """New fields per line, checked against the scene before anything is written."""

    def __init__(self, scene: Scene, verb: str):
        self.scene, self.verb, self.fields, self.read = scene, verb, {}, {}

    def get(self, path: str) -> list[str]:
        if path not in self.fields:
            ln = self.scene.get(path)
            if ln is None:
                raise KeyError(f"no {path}: cannot {self.verb} the pair")
            self.read[path] = _fields(ln)
            self.fields[path] = list(self.read[path])
        return self.fields[path]

    def copy(self, src: str, dst: str, idxs: range | tuple[int, ...] | None = None) -> None:
        s, d = self.get(src), self.get(dst)
        if idxs is None:
            if len(s) != len(d):
                raise ValueError(f"{src} and {dst} carry {len(s)} and {len(d)} fields")
            idxs = range(len(s))
        if max(idxs, default=-1) >= min(len(s), len(d)):
            raise ValueError(f"{src} or {dst} is too short to copy field {max(idxs) + 1}")
        for i in idxs:
            d[i] = s[i]

    def apply(self) -> list[str]:
        changed = set()
        for path, fields in self.fields.items():
            if fields == self.read[path]:
                continue
            ln = self.scene.get(path)
            raw = f"{path} {' '.join(fields)}"
            if raw != ln.raw:
                ln.raw, ln.args, ln.dirty = raw, Line.parse(raw).args, True
                changed.add(path)
        return [ln.path for ln in self.scene.lines if ln.path in changed]


def _link_prefs(scene: Scene) -> dict[str, bool]:
    ln = scene.get(_PREFS)
    if ln is None:
        raise KeyError(f"no {_PREFS}: cannot tell what the link copies")
    if len(ln.args) < len(LINKCFG):
        raise ValueError(f"{_PREFS} carries {len(ln.args)} of {len(LINKCFG)} fields")
    return {pref: ln.args[i] == "ON" for pref, i in LINKCFG.items()}


def set_bus_link(scene: Scene, bus: int, on: bool) -> BusLinkEdit:
    """Link (``on``) or unlink the pair holding ``bus``, either side named.

    Link: every sender's even-bus send takes the odd send's on and level; the even strip
    takes the odd strip's colour, key filter and matrix sends, plus — per ``/config/linkcfg``
    — EQ (``eq``), dynamics and insert (``dyn``), groups and mix but pan (``fdrmute``);
    matrix-send pans spread to -100/+100, and main pans too when both are centred.
    Unlink: the token, matrix-send pans centred, and main pans centred from -100/+100.

    Raises:
        ValueError: bus outside 1-16, the pair already in that state, a malformed line.
        KeyError: ``/config/buslink``, ``/config/linkcfg`` (link only) or a line the edit
            writes is missing.
    """
    if not 1 <= bus <= 16:
        raise ValueError(f"bus must be 1-16, got {bus}")
    odd = bus if bus % 2 else bus - 1
    even = odd + 1
    verb = "link" if on else "unlink"
    plan = _Plan(scene, verb)
    if scene.get(_LINK) is None:
        raise KeyError(f"no {_LINK}: cannot tell stereo bus pairs apart")
    link = plan.get(_LINK)
    k = (odd - 1) // 2
    if k >= len(link):
        raise ValueError(f"{_LINK} has no token for bus {odd}/{even}")
    if (link[k].strip() == "ON") == on:
        raise ValueError(f"bus {odd}/{even} is already {verb}ed")
    _put(link, k, "ON" if on else "OFF")
    b1, b2 = f"/bus/{odd:02d}", f"/bus/{even:02d}"
    main1, main2 = plan.get(f"{b1}/mix"), plan.get(f"{b2}/mix")
    pans = (_pan(main1, _PAN, f"{b1}/mix"), _pan(main2, _PAN, f"{b2}/mix"))
    if on:
        prefs = _link_prefs(scene)
        for s in SEND_STRIPS:
            plan.copy(f"{s}/mix/{odd:02d}", f"{s}/mix/{even:02d}", (0, 1))
        plan.copy(f"{b1}/config", f"{b2}/config", (_COLOUR,))
        plan.copy(f"{b1}/dyn/filter", f"{b2}/dyn/filter")
        for pref, subs in _GATED.items():
            for sub in subs if prefs[pref] else ():
                plan.copy(f"{b1}/{sub}", f"{b2}/{sub}")
        if prefs["fdrmute"]:
            plan.copy(f"{b1}/mix", f"{b2}/mix",
                      tuple(i for i in range(len(main1)) if i != _PAN))
        for m in _MATRIX:
            plan.copy(f"{b1}/mix/{m:02d}", f"{b2}/mix/{m:02d}",
                      (0, 1, _MTX_TAP) if m % 2 else (0, 1))
        spread = pans == (0, 0)
    else:
        spread = pans == (-100, 100)
    for m in _MATRIX[::2]:
        for path, tok in ((f"{b1}/mix/{m:02d}", "-100"), (f"{b2}/mix/{m:02d}", "+100")):
            fields = plan.get(path)
            _pan(fields, _MTX_PAN, path)
            _put(fields, _MTX_PAN, tok if on else "+0")
    if spread:
        _put(main1, _PAN, "-100" if on else "+0")
        _put(main2, _PAN, "+100" if on else "+0")
    return BusLinkEdit(odd, even, on, plan.apply())


def relinked_pairs(a: Scene, b: Scene, paths: Iterable[str]) -> list[tuple[int, int]]:
    """The bus pairs whose link differs from ``a`` to ``b`` that ``paths`` hold a line of —
    a strip line or a send to either bus. Empty when either scene lacks ``/config/buslink``."""
    la, lb = a.get(_LINK), b.get(_LINK)
    if la is None or lb is None:
        return []
    flipped = {k for k, (x, y) in enumerate(zip_longest(la.args, lb.args)) if x != y}
    hit = {(int(m.group(1) or m.group(2)) - 1) // 2
           for m in map(_BUS_OF.match, paths) if m} & flipped
    return [(2 * k + 1, 2 * k + 2) for k in sorted(hit)]
