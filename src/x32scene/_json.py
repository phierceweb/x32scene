"""JSON rendering for the CLI — presentation layer, like _views but for machines."""

from __future__ import annotations

import json
import math

from . import _views
from . import _views_ports as _ports
from .model import Scene
from .services import describe as _describe
from .services import fx as _fx
from .services.console import console_sections
from .services.desk import DeskInfo, state_words
from .services.meters import Peaks, slot_names, to_db
from .services import history as _history
from .services.matrix import Matrix
from .services import groups as _groups
from .services import routing as _routing
from .services.diff import Change
from .services.preflight import Finding
from .tables import ROUTING_BLOCKS, SOURCE_DOMAINS, decode_tap, routing_block_names, routing_vocab
from .tables_fx import FX_DISPLAY_TYPE, FX_SIDE_RACK_TYPES, FX_TYPES, decode_fx
from .services.show import Show


def dump(doc: dict) -> None:
    print(json.dumps(doc, indent=2))


def preflight_doc(findings: list[Finding], checked: dict[str, int] | None = None) -> dict:
    return {"ok": not any(f.severity == "FAIL" for f in findings),
            "findings": [{"severity": f.severity, "area": f.area,
                          "message": f.message, "path": f.path} for f in findings],
            "checked": dict(checked or {})}


def ports_doc(scene: Scene, bank: str = "main", stage: dict | None = None) -> dict:
    return {"outputs": _ports.ports_rows(scene, bank, stage)}


def diff_doc(changes: list[Change], scene: Scene | None = None) -> dict:
    """Path-level changes; with the after-side ``scene``, each also carries its group,
    what it is, and the named fields that moved."""
    if scene is None:
        return {"changes": [{"path": c.path, "before": c.before, "after": c.after}
                            for c in changes]}
    by_path = {c.path: c for c in changes}
    return {"changes": [
        {"path": d.path, "before": by_path[d.path].before, "after": by_path[d.path].after,
         "group": d.group, "label": d.label, "what": d.what, "note": d.note,
         "fields": [{"name": n, "before": b, "after": a} for n, b, a in d.fields]}
        for d in _describe.describe_all(scene, changes)]}


def history_doc(lib: list[tuple[str, Scene]], paths: list[str]) -> dict:
    return {"paths": {p: [{"scene": name, "line": raw} for name, raw in _history.history(lib, p)]
                      for p in paths}}


def inputs_doc(scene: Scene) -> dict:
    return {"channels": [{"ch": cs.ch, "name": cs.name, "slot": cs.slot, "source": cs.source}
                         for cs in _routing.channel_sources(scene)]}


def record_map_doc(scene: Scene) -> dict:
    return {"tracks": [{"track": n, "source": src} for n, src in _routing.record_map(scene)],
            "card_sourced": [{"ch": cs.ch, "name": cs.name, "source": cs.source}
                             for cs in _routing.card_sourced_channels(scene)]}


def fx_doc(scene: Scene) -> dict:
    return {"slots": [{"slot": f.slot, "code": f.code, "name": f.name,
                       "source": f.source, "params": f.params, "verified": f.verified}
                      for f in _fx.read_fx(scene)]}


def groups_doc(scene: Scene) -> dict:
    names = _groups.dca_names(scene)
    return {"dca": [{"n": n, "name": names.get(n, ""), "members": members}
                    for n, members in _groups.dca_members(scene).items()],
            "mute_groups": [{"n": g, "members": members}
                            for g, members in _groups.mute_members(scene).items()]}


def _finite(level: float):
    """JSON has no Infinity token; represent a non-finite send level as the string "-oo"."""
    return level if math.isfinite(level) else "-oo"


def iem_doc(scene: Scene, bus: int) -> dict:
    return {"bus": bus, "sends": [{"strip": strip, "name": name,
                                   "level_db": _finite(level), "args": args}
                                  for level, strip, name, args in _views.iem_rows(scene, bus)]}


def iem_matrix_doc(m: Matrix) -> dict:
    return {"compare": m.compare,
            "columns": [{"bus": c.bus, "buses": list(c.buses), "label": c.label}
                        for c in m.columns],
            "rows": [{"strip": r.strip, "label": r.label,
                      "cells": {str(bus): {"level": c.level, "asym": c.asym,
                                           "before": c.before, "changed": c.changed}
                                for bus, c in r.cells.items()}}
                     for r in m.rows]}


def show_doc(show: Show) -> dict:
    return {"name": show.name, "writer": show.writer,
            "entries": [{"kind": e.kind, "index": e.index, "name": e.name, "args": e.args,
                         **e.decoded} for e in show.entries]}


def fx_types_doc(code: str | None) -> dict:
    codes = [code] if code else list(FX_TYPES)
    return {"types": [{"code": c, "name": decode_fx(c),
                       "slots": "1-8" if c in FX_SIDE_RACK_TYPES else "1-4",
                       "display_type": FX_DISPLAY_TYPE[c],
                       "params": [{"name": n, "default": d} for n, d in
                                  zip(_fx.param_names(c), _fx.fx_defaults(c), strict=False)]}
                      for c in codes if c in FX_TYPES]}


def vocab_doc(what: str, key: str | None) -> dict:
    if what == "routing":
        keys = [key] if key else list(ROUTING_BLOCKS)
        return {"routing": {k: {label: routing_vocab(k, label) for label in routing_block_names(k)}
                            for k in keys}}
    if what == "taps":
        return {"taps": [{"number": i, "name": decode_tap(i)} for i in range(77)]}
    return {"sources": [{"from": lo, "to": hi, "label": label} for lo, hi, label in SOURCE_DOMAINS]
            + [{"from": 167, "to": 168, "label": "Talkback"}]}


def console_doc(scene: Scene) -> dict:
    return {"sections": [{"title": sec.title, "rows": [{"name": k, "value": v} for k, v in sec.rows]}
                         for sec in console_sections(scene)]}


def desk_doc(info: DeskInfo) -> dict:
    return {"ip": info.ip, "name": info.name, "model": info.model, "firmware": info.firmware,
            "state": state_words(info.stat), "stat": info.stat, "prefs": info.prefs,
            "show": info.show,
            "slots": {k: [{"index": i, "name": n, "fields": e} for i, n, e in v]
                      for k, v in info.slots.items()}}


def meters_doc(peaks: Peaks, scene: Scene | None) -> dict:
    return {"meter": peaks.meter, "frames": peaks.frames,
            "slots": [{"slot": k, "name": slot_names(scene, k), "peak": v,
                       "db": None if v <= 0 else round(to_db(v), 1)}
                      for k, v in peaks.peak.items()]}
