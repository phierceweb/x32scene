"""--json documents for info, buses, explain, audit and live-diff."""

from __future__ import annotations

from . import _json
from .model import Scene
from .services import audit as _audit
from .services import buses as _buses
from .services.diff import diff
from .tables_fx import decode_fx


def info_doc(scene: Scene) -> dict:
    return {"title": scene.name, "lines": len(scene.lines),
            "channels": [{"ch": n, "name": nm}
                         for n, nm in sorted(_buses.channel_names(scene).items())],
            "buses": [{"bus": n, "name": nm}
                      for n, nm in sorted(_buses.bus_names(scene).items())]}


def buses_doc(scene: Scene) -> dict:
    return {"buses": [{"bus": r.bus, "name": r.name, "linked": r.linked,
                       "fx": None if r.fx_slot is None else
                       {"slot": r.fx_slot, "type": r.fx_type, "name": decode_fx(r.fx_type)},
                       "sends": r.taps} for r in _buses.bus_rows(scene)]}


def explain_doc(scene: Scene) -> dict:
    return {"title": scene.name, "inputs": _json.inputs_doc(scene), "buses": buses_doc(scene),
            "outputs": _json.ports_doc(scene, "all"),
            "record_map": _json.record_map_doc(scene), "fx": _json.fx_doc(scene),
            "groups": _json.groups_doc(scene)}


def audit_doc(lib: list[tuple[str, Scene]], scenes_dir: str, load_errors: list[str],
              violations: list[str]) -> dict:
    return {"ok": not load_errors and not violations, "dir": scenes_dir, "scenes": len(lib),
            "load_errors": list(load_errors), "violations": list(violations),
            "routing": [{"scene": name, **banks} for name, banks in _audit.routing_drift(lib)],
            "record_patch": [{"scene": name, "slots": slots}
                             for name, slots in _audit.record_patch_drift(lib)]}


def live_diff_doc(reference: Scene, live: Scene, unanswered: list[str]) -> dict:
    return {**_json.diff_doc(diff(reference, live), live), "unanswered": list(unanswered)}
