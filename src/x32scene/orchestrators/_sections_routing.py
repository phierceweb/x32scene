"""The routing section and the channel sources of a band-setup plan. Both apply before any
other stage, so a head amp the plan or a preset sets is the one the channel reads in the
finished scene."""

from __future__ import annotations

from ..model import Scene
from ..services import routing_edit as _rt
from ..tables import ROUTING_BLOCKS, routing_block_names, routing_vocab
from ._sections import _check_preset_path, _obj, _only, _read

ROUTING_KEYS = {"switch", "preset", "banks", *ROUTING_BLOCKS}


def validate_routing(plan: dict) -> None:
    spec = _obj("routing", plan.get("routing", {}))
    _only("routing", spec, ROUTING_KEYS)
    if "switch" in spec and spec["switch"] not in ("REC", "PLAY"):
        raise ValueError(f"routing: switch must be REC or PLAY, got {spec['switch']!r}")
    _check_preset_path("routing", spec)
    if "banks" in spec and ("preset" not in spec or not isinstance(spec["banks"], list)):
        raise ValueError("routing: banks is a list of banks to take from preset")
    for bank in spec.get("banks") or []:
        # unchecked, a typo'd or wrong-cased bank applies nothing and still exits 0
        if bank not in _rt.ROUTING_PRESET_KEYS:
            raise ValueError(f"routing: banks must be from "
                             f"{', '.join(_rt.ROUTING_PRESET_KEYS)}, got {bank!r}")
    for key in ROUTING_BLOCKS:
        for label, value in _obj(f"routing {key}", spec.get(key, {})).items():
            if label not in routing_block_names(key):
                raise ValueError(f"routing {key}: blocks are "
                                 f"{', '.join(routing_block_names(key))}, not {label!r}")
            if value not in routing_vocab(key, label):
                raise ValueError(f"routing {key}/{label}: {value!r} is not a console token "
                                 f"(`x32scene vocab routing {key}`)")


def apply_routing(scene: Scene, plan: dict) -> None:
    spec = plan.get("routing", {})
    if "preset" in spec:
        _rt.apply_routing(scene, _read(plan, spec["preset"]), spec.get("banks"))
    for key in ROUTING_BLOCKS:
        if spec.get(key):
            _rt.set_routing(scene, key, spec[key])
    if "switch" in spec:
        _rt.set_routswitch(scene, spec["switch"])


def apply_sources(scene: Scene, plan: dict) -> None:
    """Channel ``source`` keys, after ``routing``: a name resolves through the plan's IN blocks."""
    for ch_s, spec in plan.get("channels", {}).items():
        if "source" in spec:
            _rt.set_input(scene, int(ch_s), spec["source"])


def routed(template: Scene, plan: dict) -> Scene:
    """``template`` with only the plan's routing and sources applied: the scene whose head
    amps a channel's ``gain_db``, ``phantom`` and preset land on."""
    sourced = any("source" in s for s in plan.get("channels", {}).values())
    if not plan.get("routing") and not sourced:
        return template
    scene = Scene.parse(template.dump())
    apply_routing(scene, plan)
    apply_sources(scene, plan)
    return scene


def allowed_routing(plan: dict) -> set[str]:
    spec, out = plan.get("routing", {}), set()
    if "switch" in spec:
        out.add("/config/routing")
    out.update(f"/config/routing/{k}" for k in ROUTING_BLOCKS if spec.get(k))
    if "preset" in spec:
        banks = spec.get("banks") or list(_rt.ROUTING_PRESET_KEYS)
        out.update(f"/config/routing/{k}" for k in banks)
    return out
