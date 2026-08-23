"""preflight family ``routing``: REC/PLAY mode, the routing block lines pinned by 1-based
block index with each destination's own width, and /config/userrout slots compared raw.

Line widths are checked with no config; ``OUT9-16`` and ``UOUT9-16`` are different signals,
so a pinned token is compared whole, never by prefix or by digits alone.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import ROUTING_BLOCKS, USERROUT_SLOTS, decode_out_source, decode_source
from .preflight_config import Finding, fail_unknown, mapping, numbered_items, want_str
from .routing import routing_blocks

SECTIONS = frozenset({"routing"})
_KEYS = frozenset({"mode", "blocks", "userrout"})
_DECODE = {"in": decode_source, "out": decode_out_source}


def _shape(scene: Scene, out: list[Finding]) -> None:
    ln = scene.get("/config/routing")
    if ln is None:
        out.append(Finding("FAIL", "routing", "/config/routing missing — cannot verify REC/PLAY",
                           "/config/routing"))
    elif len(ln.args) != 1:
        out.append(Finding("FAIL", "routing", f"/config/routing carries {len(ln.args)} "
                           "token(s), not 1", "/config/routing"))
    for key, width in ROUTING_BLOCKS.items():
        path, area = f"/config/routing/{key}", f"routing {key}"
        toks = routing_blocks(scene, key)
        if not toks:
            out.append(Finding("FAIL", area, f"{path} missing — cannot verify", path))
        elif len(toks) != width:
            out.append(Finding("FAIL", area, f"carries {len(toks)} block(s), not {width}", path))
    for which, slots in USERROUT_SLOTS.items():
        path, area = f"/config/userrout/{which}", f"userrout {which}"
        ln = scene.get(path)
        if ln is None:
            out.append(Finding("FAIL", area, f"{path} missing — cannot verify", path))
        elif len(ln.args) != slots:
            out.append(Finding("FAIL", area, f"carries {len(ln.args)} slot(s), not {slots}", path))
        elif not all(a.isdigit() for a in ln.args):
            out.append(Finding("FAIL", area, "carries a non-numeric slot", path))


def _check_blocks(scene: Scene, blocks: dict, out: list[Finding]) -> None:
    fail_unknown(blocks, ROUTING_BLOCKS, "routing", out)
    for key, width in ROUTING_BLOCKS.items():
        path, area = f"/config/routing/{key}", f"routing {key}"
        pins = numbered_items(mapping(blocks, key, area, out), area, out, lo=1, hi=width)
        if not pins:
            continue
        toks = routing_blocks(scene, key)
        for idx, want in pins:
            if not isinstance(want, str):
                out.append(Finding("FAIL", area, f"block {idx}: expected token must be a "
                                   f"string, got {want!r}"))
            elif idx > len(toks):
                out.append(Finding("FAIL", area, f"block {idx}: line "
                                   f"{'missing' if not toks else f'carries only {len(toks)} block(s)'}"
                                   " — cannot verify", path))
            elif toks[idx - 1] != want:
                out.append(Finding("FAIL", area, f"block {idx} is {toks[idx - 1]}, "
                                   f"expected {want}", path))


def _check_userrout(scene: Scene, ur: dict, out: list[Finding]) -> None:
    fail_unknown(ur, USERROUT_SLOTS, "routing", out)
    for which, slots in USERROUT_SLOTS.items():
        path, area = f"/config/userrout/{which}", f"userrout {which}"
        pins = numbered_items(mapping(ur, which, area, out), area, out, lo=1, hi=slots)
        if not pins:
            continue
        ln = scene.get(path)
        toks = ln.args if ln else []
        for slot, want in pins:
            if isinstance(want, bool) or not isinstance(want, int):
                out.append(Finding("FAIL", area, f"slot {slot}: expected value must be a "
                                   f"whole number, got {want!r}"))
            elif slot > len(toks):
                out.append(Finding("FAIL", area, f"slot {slot}: line "
                                   f"{'missing' if not toks else f'carries only {len(toks)} slot(s)'}"
                                   " — cannot verify", path))
            elif not toks[slot - 1].isdigit():
                out.append(Finding("FAIL", area, f"slot {slot} holds {toks[slot - 1]!r}, not "
                                   "a number", path))
            elif int(toks[slot - 1]) != want:
                got = int(toks[slot - 1])
                out.append(Finding("FAIL", area, f"slot {slot} holds {got} "
                                   f"({_DECODE[which](got)}), expected {want} "
                                   f"({_DECODE[which](want)})", path))


def check(scene: Scene, expected: dict, out: list[Finding]) -> None:
    _shape(scene, out)
    r = mapping(expected, "routing", "config", out)
    fail_unknown(r, _KEYS, "routing", out)
    mode = want_str(r, "mode", "routing", out)
    if mode is not None:
        ln = scene.get("/config/routing")
        if ln is not None and ln.args and ln.args[0] != mode:
            out.append(Finding("FAIL", "routing", f"mode {ln.args[0]} != expected {mode}",
                               "/config/routing"))
    _check_blocks(scene, mapping(r, "blocks", "routing", out), out)
    _check_userrout(scene, mapping(r, "userrout", "routing", out), out)
