"""The inverse of preflight: the expected-config a scene checks clean against. Sections come
from the checker's own list, so a new family must be inverted here or named in
``_NOT_INVERTIBLE``. A value its check could not verify is left out, never guessed.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import date

from ..model import Scene
from ..tables import (LINK_LINES, LINK_WIDTHS, LINKCFG, MUTE_GROUPS, OUTPUT_BANKS,
                      ROUTING_BLOCKS, SEND_STRIPS, USERROUT_SLOTS, send_is_live, tap_to_bus)
from . import preflight_links, preflight_monitor, preflight_sends
from .groups import GROUP_STRIPS, dca_members, dca_names, mute_members
from .preflight import _ALL_SECTIONS, _SECTIONS, GAIN_TOLERANCE_DB, _in_main
from .preflight_outputs import _SRC_MAX, out_path
from .routing import (channel_headamp_index, output_sources, record_map, resolve_in_slot,
                      routing_blocks, uin_in_index)

__all__ = ["dumps", "regenerate"]

# every section inverts today; name one here, with why, before leaving it out
_NOT_INVERTIBLE: frozenset[str] = frozenset()
_NOT_INVERTED_KEYS = {
    # the jack count is the console model, which no scene line records; reachability needs it
    "monitor": frozenset({"physical_outputs", "require_reachable"}),
}
_GAIN = re.compile(r"[+-]?\d+(\.\d+)?")
_SWITCH = ("ON", "OFF")


def _holds(module, scene: Scene, section: str, body: dict) -> bool:
    """Does declaring ``body`` add no finding to what the family reports with no config?"""
    base: list = []
    trial: list = []
    module.check(scene, {}, base)
    module.check(scene, {section: body}, trial)
    return trial == base


def _numeric(scene: Scene, path: str) -> bool:
    """routing.userrout reads every slot as an int, so one bad token breaks every lookup."""
    ln = scene.get(path)
    return ln is None or all(tok.isdigit() for tok in ln.args)


def _resolvable(scene: Scene, slot: int) -> bool:
    """Is every routing line the input slot resolves through present and readable? The
    resolver fills an absent one with a default the desk need not hold."""
    if not 1 <= slot <= 40:
        return True
    if (slot - 1) // 8 >= len(routing_blocks(scene, "IN")):
        return False
    idx = uin_in_index(scene, slot)
    uin = scene.get("/config/userrout/in")
    return idx is None or (uin is not None and idx < len(uin.args)
                           and _numeric(scene, "/config/userrout/in"))


def _numbered(section: str) -> range:
    lo, hi = _SECTIONS[section]
    return range(lo, hi + 1)


def _channels(scene: Scene) -> dict:
    out = {}
    for ch in _numbered("channels"):
        cfg = scene.get(f"/ch/{ch:02d}/config")
        if cfg is None or not cfg.args:
            continue
        entry: dict = {"name": cfg.args[0].strip('"')}
        mix = scene.get(f"/ch/{ch:02d}/mix")
        if mix is not None and len(mix.args) >= 3:
            entry["in_main"] = _in_main(mix.args)
        slot = cfg.args[-1]
        if len(cfg.args) > 1 and slot.isdigit() and _resolvable(scene, int(slot)):
            entry["source"] = resolve_in_slot(scene, int(slot))
            _headamp(scene, ch, entry)
        out[str(ch)] = entry
    return out


def _headamp(scene: Scene, ch: int, entry: dict) -> None:
    idx = channel_headamp_index(scene, ch)
    ha = scene.get(f"/headamp/{idx:03d}") if idx is not None else None
    if ha is None or len(ha.args) < 2:
        return
    if _GAIN.fullmatch(ha.args[0]):
        entry["gain"] = float(ha.args[0])
    if ha.args[1] in _SWITCH:
        entry["phantom"] = ha.args[1] == "ON"


def _record(scene: Scene) -> dict:
    # record_map assumes the factory card blocks when /config/routing/CARD is absent
    if scene.get("/config/routing/CARD") is None or not _numeric(scene, "/config/userrout/out"):
        return {}
    tracks = _numbered("record")
    # "?" is record_map's word for a slot past the end of a short user-out line
    return {str(trk): src for trk, src in record_map(scene) if trk in tracks and src != "?"}


def _fx(scene: Scene) -> dict:
    lines = {n: scene.get(f"/fx/{n}") for n in _numbered("fx")}
    return {str(n): ln.args[0] for n, ln in lines.items() if ln is not None and ln.args}


def _outputs(scene: Scene) -> dict:
    out: dict = {}
    for bank, (size, fields) in OUTPUT_BANKS.items():
        entries = out[bank] = {}
        for n in range(1, size + 1):
            ln = scene.get(out_path(bank, n))
            if ln is None or len(ln.args) != fields:
                continue
            entry: dict = {"pos": ln.args[1]}
            tok = ln.args[0]
            if tok.isdigit() and int(tok) <= _SRC_MAX:
                bus = tap_to_bus(int(tok))
                entry.update({"bus": bus} if bus else {"src": int(tok)})
            if fields == 3 and ln.args[2] in _SWITCH:
                entry["invert"] = ln.args[2] == "ON"
            entries[str(n)] = entry
    return out


def _monitor(scene: Scene) -> dict:
    pairs = [b for b in preflight_monitor._PAIR_BANKS
             if _holds(preflight_monitor, scene, "monitor", {"stereo_pairs": [b]})]
    # with an output line missing, a bus it routes goes unchecked and passes vacuously
    complete = all(len(output_sources(scene, bank)) == size
                   for bank, (size, _) in OUTPUT_BANKS.items())
    live = complete and _holds(preflight_monitor, scene, "monitor",
                               {"require_live_senders": True})
    return {"stereo_pairs": pairs, "require_live_senders": live}


def _routing(scene: Scene) -> dict:
    out: dict = {}
    ln = scene.get("/config/routing")
    if ln is not None and ln.args:
        out["mode"] = ln.args[0]
    out["blocks"] = {key: {str(i): tok for i, tok in
                           enumerate(routing_blocks(scene, key)[:width], start=1)}
                     for key, width in ROUTING_BLOCKS.items()}
    userrout = out["userrout"] = {}
    for which, slots in USERROUT_SLOTS.items():
        ln = scene.get(f"/config/userrout/{which}")
        toks = ln.args[:slots] if ln else []
        userrout[which] = {str(i): int(t) for i, t in enumerate(toks, start=1) if t.isdigit()}
    return out


def _links(scene: Scene) -> dict:
    out: dict = {}
    for fam, size in preflight_links._FAMILIES.items():
        ln = scene.get(LINK_LINES[f"/{fam}"])
        toks = ln.args if ln else []
        out[fam] = {str(2 * i + 1): tok == "ON" for i, tok in enumerate(toks)
                    if 2 * i + 1 <= size and tok in _SWITCH}
    cfg = scene.get("/config/linkcfg")
    out["linkcfg"] = {name: cfg.args[idx] == "ON" for name, idx in LINKCFG.items()
                      if cfg is not None and idx < len(cfg.args) and cfg.args[idx] in _SWITCH}
    buslink = scene.get("/config/buslink")
    shaped = (buslink is not None and len(buslink.args) == LINK_WIDTHS["/config/buslink"]
              and all(tok in _SWITCH for tok in buslink.args))
    out["require_send_symmetry"] = shaped and _holds(preflight_links, scene, "links",
                                                     {"require_send_symmetry": True})
    return out


def _majority(taps: list[str]) -> str:
    counts = Counter(taps)
    return min(counts, key=lambda t: (-counts[t], t))


def _rules_under(tap: str, taps: dict[str, str]) -> dict[str, str]:
    """A family rule only where it saves rules, then each strip that still disagrees."""
    rules: dict[str, str] = {}
    for fam in preflight_sends._FAMILIES:
        own = [t for s, t in taps.items() if s.rpartition("/")[0] == fam]
        others = [t for t in own if t != tap]
        if others:
            alt = _majority(others)
            if 1 + sum(t != alt for t in own) < len(others):
                rules[fam] = alt
    for strip, t in taps.items():
        if t != rules.get(strip.rpartition("/")[0], tap):
            rules[strip] = t
    return rules


def _tap_rules(taps: dict[str, str]) -> dict:
    """The bus tap with the fewest except rules; a tie goes to the commoner tap."""
    counts = Counter(taps.values())
    tap = min(counts, key=lambda t: (len(_rules_under(t, taps)), -counts[t], t))
    rules = _rules_under(tap, taps)
    return {"tap": tap, "except": rules} if rules else {"tap": tap}


def _sends(scene: Scene) -> dict:
    out = {}
    for bus in range(1, 17):
        lines = {s: scene.get(f"{s}/mix/{bus:02d}") for s in SEND_STRIPS}
        entry: dict = {}
        if bus % 2 and all(lines.values()):
            taps = {s: ln.args[3] for s, ln in lines.items() if len(ln.args) >= 4}
            if taps:
                entry.update(_tap_rules(taps))
        if any(lines.values()):
            entry["present"] = [s for s, ln in lines.items() if ln and send_is_live(ln.args)]
            entry["absent"] = [s for s, ln in lines.items() if ln and not send_is_live(ln.args)]
        out[str(bus)] = entry
    return out


def _masks_known(scene: Scene, arg: int) -> bool:
    """Any strip could belong to any group, so one unreadable mask hides every group's
    membership."""
    lines = (scene.get(f"{p}/grp") for p in GROUP_STRIPS)
    return all(ln is not None and len(ln.args) > arg for ln in lines)


def _groups(scene: Scene) -> dict:
    names = dca_names(scene)
    dca_known = _masks_known(scene, 0)
    out: dict = {"dca": {}}
    for n, members in dca_members(scene).items():
        out["dca"][str(n)] = {**({"members": members} if dca_known else {}),
                              **({"name": names[n]} if n in names else {})}
    if _masks_known(scene, 1):
        out["mute"] = {str(n): {"members": members} for n, members in mute_members(scene).items()}
    ln = scene.get("/config/mute")
    if ln is not None and len(ln.args) == MUTE_GROUPS:
        out["mute_engaged"] = [g for g, tok in enumerate(ln.args, start=1) if tok == "ON"]
    return out


_INVERTERS = {"channels": _channels, "record": _record, "fx": _fx, "outputs": _outputs,
              "monitor": _monitor, "routing": _routing, "links": _links, "sends": _sends,
              "groups": _groups}


def regenerate(scene: Scene, source: str, generated: date) -> dict:
    """The expected-config ``scene`` satisfies. ``source`` is the scene's file, named in the
    comment by its base name only."""
    doc: dict = {
        "_comment": (f"Written by `x32scene preflight --regenerate` from "
                     f"{os.path.basename(source)} on {generated.isoformat()}. Regenerate "
                     "rather than hand-edit. A scene does not record the console's jack "
                     "count, so monitor.physical_outputs and require_reachable are not "
                     "written."),
        "gain_tolerance_db": GAIN_TOLERANCE_DB,
    }
    for section in _ALL_SECTIONS:
        body = None if section in _NOT_INVERTIBLE else _pruned(_INVERTERS[section](scene))
        if body:
            doc[section] = body
    return doc


def _pruned(v: object) -> object:
    """Without the empty objects a sparse scene leaves, so coverage counts only what checks."""
    if not isinstance(v, dict):
        return v
    kept = {k: _pruned(x) for k, x in v.items()}
    return {k: x for k, x in kept.items() if x != {}}


def _order(k: str) -> tuple:
    """Comments first, then numbered keys by number, then names."""
    return (not k.startswith("_"), not k.isdigit(), int(k) if k.isdigit() else 0, k)


def _sorted(v: object) -> object:
    if isinstance(v, dict):
        return {k: _sorted(v[k]) for k in sorted(v, key=_order)}
    if isinstance(v, list):
        return [_sorted(x) for x in v]
    return v


def dumps(doc: dict) -> str:
    """The config as written to disk: keys sorted, two-space indent, one trailing newline."""
    return json.dumps(_sorted(doc), indent=2, ensure_ascii=False) + "\n"
