"""The values outside ``/ch/NN`` that name a channel by number, for ``stripmove``: the ones
a permutation rewrites, and the ones that refuse it."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..model import Scene, put_field
from ..tables import LINK_WIDTHS, channel_to_tap, line_fields, tap_to_channel
from .userctrl import retarget, strip_index

CHLINK = "/config/chlink"
_OUTPUT = re.compile(r"^/outputs/(?:main|aux|p16|aes|rec)/\d\d$")
_USERCTRL = re.compile(r"^/config/userctrl/[ABC]/(enc|btn)$")
_AUTOMIX_CHANNELS = 8


@dataclass(frozen=True)
class RemappedRef:
    """One rewritten value: its line, its 1-based field, and the token before and after."""

    path: str
    field: int
    before: str
    after: str


def _linked(scene: Scene) -> list[bool]:
    return [tok.strip() == "ON" for tok in scene.get(CHLINK).padded_fields()]


def reference_problems(scene: Scene, perm: dict[int, int]) -> list[str]:
    """Every reason the references refuse ``perm`` (moved channels only, old -> new)."""
    problems = []
    width = LINK_WIDTHS[CHLINK]
    link = scene.get(CHLINK)
    if link is None:
        problems.append(f"no {CHLINK}: cannot tell linked channel pairs apart")
    elif len(link.args) < width:
        problems.append(f"{CHLINK} carries {len(link.args)} of {width} pairs")
    else:
        for k, on in enumerate(_linked(scene)[:width]):
            a, b = 2 * k + 1, 2 * k + 2
            pa, pb = perm.get(a, a), perm.get(b, b)
            if on and not (pa % 2 and pb == pa + 1):
                problems.append(f"channels {a}/{b} are stereo-linked and would land on "
                                f"{pa}/{pb}; move a linked pair whole, in order, onto a pair")
    for ln in scene.lines:
        if not ln.path.endswith(("/gate", "/dyn")):
            continue
        names = line_fields(ln.path, len(ln.args)) or []
        if "keysrc" not in names:
            continue
        v = ln.args[names.index("keysrc")]
        if v.isdigit() and int(v) in perm:
            problems.append(f"{ln.path} key source {v} names ch{int(v):02d}, which moves; "
                            "whether a key source names a channel or an input slot is not "
                            "desk-verified")
    for old, new in sorted(perm.items()):
        mix = scene.get(f"/ch/{old:02d}/automix")
        group = mix.args[0] if mix is not None and mix.args else ""
        if group in ("X", "Y") and (old <= _AUTOMIX_CHANNELS) != (new <= _AUTOMIX_CHANNELS):
            problems.append(f"ch{old:02d} is in automix group {group} and would move to "
                            f"ch{new:02d}; automix acts on channels 1-{_AUTOMIX_CHANNELS} only")
    return problems


def remap_references(scene: Scene, perm: dict[int, int]) -> list[RemappedRef]:
    """Rewrite in place every value naming a channel in ``perm``, once
    ``reference_problems`` found none; the rewrites in scene order."""
    inverse = {new: old for old, new in perm.items()}
    linked = _linked(scene)
    out: list[RemappedRef] = []
    for ln in scene.lines:
        userctrl = _USERCTRL.match(ln.path)
        if not (_OUTPUT.match(ln.path) or ln.path == CHLINK or userctrl):
            continue
        fields = ln.padded_fields()
        edits: dict[int, str] = {}
        if ln.path == CHLINK:
            for k in range(min(len(fields), LINK_WIDTHS[CHLINK])):
                s1, s2 = inverse.get(2 * k + 1, 2 * k + 1), inverse.get(2 * k + 2, 2 * k + 2)
                if (s1, s2) != (2 * k + 1, 2 * k + 2):
                    on = s1 % 2 == 1 and s2 == s1 + 1 and linked[(s1 - 1) // 2]
                    edits[k] = "ON" if on else "OFF"
        elif userctrl:
            for i, tok in enumerate(fields):
                xx = strip_index(tok.strip(), button=userctrl.group(1) == "btn")
                if xx is not None and xx + 1 in perm:
                    edits[i] = retarget(tok.strip(), perm[xx + 1] - 1)
        elif fields and fields[0].strip().isdigit():
            ch = tap_to_channel(int(fields[0]))
            if ch in perm:
                edits[0] = str(channel_to_tap(perm[ch]))
        before = list(fields)
        for i, tok in edits.items():
            put_field(fields, i, tok)
        if edits and ln.set_fields(fields):
            out += [RemappedRef(ln.path, i + 1, b.strip(), a.strip())
                    for i, (b, a) in enumerate(zip(before, fields, strict=True)) if a != b]
    return out
