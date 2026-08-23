"""The processing, FX, routing and output-patch sections of a band-setup plan: validate,
apply, and name every path each is allowed to touch. ``band_swap`` owns the stage order
and the verify step; this module keeps those two files under the size guard."""

from __future__ import annotations

from pathlib import Path

from ..model import Scene
from ..services import channelfx as _cfx
from ..services import fx as _fx
from ..services import routing_edit as _rt
from ..services import transforms as T
from ..tables import OUTPUT_BANKS, OUTPUT_POS, ROUTING_BLOCKS, routing_block_names, routing_vocab
from ..tables_fx import FX_SIDE_RACK_TYPES, FX_TYPES

CHANNEL_PROC_KEYS = {"eq", "comp", "gate", "lowcut", "pan", "source"}
_EQ_KEYS = {"type", "freq", "gain", "q"}
_COMP_KEYS = {"thr", "ratio", "makeup", "attack", "release"}
_GATE_KEYS = {"thr", "range", "attack", "release"}
_LOWCUT_KEYS = {"on", "freq"}
FX_KEYS = {"type", "source", "params", "preset"}
ROUTING_KEYS = {"switch", "preset", "banks", *ROUTING_BLOCKS}
OUTPUT_KEYS = {"src", "pos", "invert"}


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _obj(where: str, v: object) -> dict:
    if not isinstance(v, dict):
        raise ValueError(f"{where}: must be an object, got {type(v).__name__}")
    return v


def _only(where: str, spec: dict, keys: set[str]) -> None:
    bad = [k for k in spec if k not in keys]
    if bad:
        raise ValueError(f"{where}: unknown key(s): {', '.join(sorted(bad))}")


def _read(plan: dict, rel: str) -> str:
    p = Path(rel)
    if not p.is_absolute():
        p = Path(plan.get("_dir", ".")) / p
    try:
        return p.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"preset {p}: {e.strerror}") from e


# ---- validation --------------------------------------------------------------------
def validate_channel_proc(ch: int, spec: dict) -> None:
    w = f"channel {ch}"
    for band_s, band in _obj(f"{w}: eq", spec.get("eq", {})).items():
        if not str(band_s).isdigit() or not 1 <= int(band_s) <= 6:
            raise ValueError(f"{w}: eq band must be 1-6, got {band_s!r}")
        _only(f"{w}: eq {band_s}", _obj(f"{w}: eq {band_s}", band), _EQ_KEYS)
        for k in ("freq", "gain", "q"):
            if k in band and not _num(band[k]):
                raise ValueError(f"{w}: eq {band_s}: {k} must be a number, got {band[k]!r}")
    if "comp" in spec:
        _only(f"{w}: comp", _obj(f"{w}: comp", spec["comp"]), _COMP_KEYS)
        for k, v in spec["comp"].items():
            if k != "ratio" and not _num(v):
                raise ValueError(f"{w}: comp: {k} must be a number, got {v!r}")
    if "gate" in spec:
        _only(f"{w}: gate", _obj(f"{w}: gate", spec["gate"]), _GATE_KEYS)
        for k, v in spec["gate"].items():
            if not _num(v):
                raise ValueError(f"{w}: gate: {k} must be a number, got {v!r}")
    if "lowcut" in spec:
        _only(f"{w}: lowcut", _obj(f"{w}: lowcut", spec["lowcut"]), _LOWCUT_KEYS)
        if "on" in spec["lowcut"] and not isinstance(spec["lowcut"]["on"], bool):
            raise ValueError(f"{w}: lowcut: on must be true or false")
        if "freq" in spec["lowcut"] and not _num(spec["lowcut"]["freq"]):
            raise ValueError(f"{w}: lowcut: freq must be a number")
    if "pan" in spec and not (_num(spec["pan"]) and -100 <= spec["pan"] <= 100):
        raise ValueError(f"{w}: pan must be -100..+100, got {spec['pan']!r}")
    if "source" in spec:
        try:
            _rt.encode_input_source(spec["source"])
        except ValueError as e:
            raise ValueError(f"{w}: source: {e}") from None


def validate_fx(plan: dict) -> None:
    for slot_s, spec in _obj("fx", plan.get("fx", {})).items():
        if not str(slot_s).isdigit() or not 1 <= int(slot_s) <= 8:
            raise ValueError(f"fx: slot must be 1-8, got {slot_s!r}")
        slot, w = int(slot_s), f"fx {slot_s}"
        _only(w, _obj(w, spec), FX_KEYS)
        if not spec:
            raise ValueError(f"{w}: needs type, source, params or preset, or it does nothing")
        if "type" in spec:
            if spec["type"] not in FX_TYPES:
                raise ValueError(f"{w}: unknown type {spec['type']!r} (see `x32scene fx-types`)")
            if slot >= 5 and spec["type"] not in FX_SIDE_RACK_TYPES:
                raise ValueError(f"{w}: {spec['type']} cannot go in FX{slot} (slots 5-8 take "
                                 "the insert-style types only)")
            for name in _obj(f"{w}: params", spec.get("params", {})):
                if name not in _fx.param_names(spec["type"]):
                    raise ValueError(f"{w}: {name!r} is not a {spec['type']} parameter")
        else:
            _obj(f"{w}: params", spec.get("params", {}))
        if "source" in spec:
            toks = _source_tokens(spec["source"])
            for t in toks:
                if t not in _fx.FX_SOURCES:
                    raise ValueError(f"{w}: source {t!r} must be INS, MIX1..MIX16 or M/C")
            if slot >= 5:
                raise ValueError(f"{w}: FX{slot} has no source (slots 5-8 are inserts)")


def _source_tokens(v: object) -> list[str]:
    if isinstance(v, str):
        return [t.strip() for t in v.split(",")][:2]
    if isinstance(v, list) and 1 <= len(v) <= 2 and all(isinstance(t, str) for t in v):
        return list(v)
    raise ValueError(f"fx source must be \"MIX13\" or \"MIX15,MIX16\", got {v!r}")


def validate_routing(plan: dict) -> None:
    spec = _obj("routing", plan.get("routing", {}))
    _only("routing", spec, ROUTING_KEYS)
    if "switch" in spec and spec["switch"] not in ("REC", "PLAY"):
        raise ValueError(f"routing: switch must be REC or PLAY, got {spec['switch']!r}")
    if "banks" in spec and ("preset" not in spec or not isinstance(spec["banks"], list)):
        raise ValueError("routing: banks is a list of banks to take from preset")
    for key in ROUTING_BLOCKS:
        for label, value in _obj(f"routing {key}", spec.get(key, {})).items():
            if label not in routing_block_names(key):
                raise ValueError(f"routing {key}: blocks are "
                                 f"{', '.join(routing_block_names(key))}, not {label!r}")
            if value not in routing_vocab(key, label):
                raise ValueError(f"routing {key}/{label}: {value!r} is not a console token "
                                 f"(`x32scene vocab routing {key}`)")


def validate_output_patch(plan: dict) -> None:
    for bank, outs in _obj("output_patch", plan.get("output_patch", {})).items():
        if bank not in OUTPUT_BANKS:
            raise ValueError(f"output_patch: bank must be one of {', '.join(OUTPUT_BANKS)}, "
                             f"got {bank!r}")
        size, nfields = OUTPUT_BANKS[bank]
        for n_s, spec in _obj(f"output_patch {bank}", outs).items():
            if not str(n_s).isdigit() or not 1 <= int(n_s) <= size:
                raise ValueError(f"output_patch {bank}: outputs run 1-{size}, got {n_s!r}")
            w = f"output_patch {bank} {n_s}"
            _only(w, _obj(w, spec), OUTPUT_KEYS)
            if not spec:
                raise ValueError(f"{w}: needs src, pos or invert")
            if "pos" in spec and spec["pos"] not in OUTPUT_POS:
                raise ValueError(f"{w}: pos must be one of {', '.join(OUTPUT_POS)}")
            if "invert" in spec and (not isinstance(spec["invert"], bool) or nfields < 3):
                raise ValueError(f"{w}: invert must be true or false, and {bank} has a "
                                 "polarity field" if nfields >= 3 else f"{w}: {bank} has no invert")
            if "src" in spec:
                try:
                    _rt.encode_tap(spec["src"])
                except ValueError as e:
                    raise ValueError(f"{w}: {e}") from None


# ---- apply ---------------------------------------------------------------------------
def apply_channel_proc(scene: Scene, ch: int, spec: dict) -> None:
    if "source" in spec:
        _rt.set_input(scene, ch, spec["source"])
    if "pan" in spec:
        T.set_pan(scene, ch, int(spec["pan"]))
    if "lowcut" in spec:
        _cfx.set_lowcut(scene, ch, on=spec["lowcut"].get("on"), freq=spec["lowcut"].get("freq"),
                        linked=False)
    for band_s, band in spec.get("eq", {}).items():
        _cfx.set_eq_band(scene, ch, int(band_s), type=band.get("type"), freq=band.get("freq"),
                         gain=band.get("gain"), q=band.get("q"), linked=False)
    if "comp" in spec:
        c = spec["comp"]
        _cfx.set_comp(scene, ch, thr=c.get("thr"), ratio=c.get("ratio"), makeup=c.get("makeup"),
                      attack=c.get("attack"), release=c.get("release"), linked=False)
    if "gate" in spec:
        g = spec["gate"]
        _cfx.set_gate(scene, ch, thr=g.get("thr"), rng=g.get("range"), attack=g.get("attack"),
                      release=g.get("release"), linked=False)


def apply_fx(scene: Scene, plan: dict) -> None:
    for slot_s, spec in sorted(plan.get("fx", {}).items(), key=lambda kv: int(kv[0])):
        slot = int(slot_s)
        if "preset" in spec:
            _fx.apply_fx(scene, slot, _read(plan, spec["preset"]))
        elif "type" in spec:
            _fx.set_fx_type(scene, slot, spec["type"])
        if "source" in spec:
            _fx.set_fx_source(scene, slot, *_source_tokens(spec["source"]))
        if spec.get("params"):
            _fx.set_fx_params(scene, slot, spec["params"])


def apply_routing(scene: Scene, plan: dict) -> None:
    spec = plan.get("routing", {})
    if "preset" in spec:
        _rt.apply_routing(scene, _read(plan, spec["preset"]), spec.get("banks"))
    for key in ROUTING_BLOCKS:
        if spec.get(key):
            _rt.set_routing(scene, key, spec[key])
    if "switch" in spec:
        _rt.set_routswitch(scene, spec["switch"])


def apply_output_patch(scene: Scene, plan: dict) -> None:
    for bank, outs in plan.get("output_patch", {}).items():
        for n_s, spec in sorted(outs.items(), key=lambda kv: int(kv[0])):
            _rt.set_output(scene, bank, int(n_s), src=spec.get("src"), pos=spec.get("pos"),
                           invert=spec.get("invert"))


# ---- whitelist ---------------------------------------------------------------------
def allowed_channel_proc(ch: int, spec: dict) -> set[str]:
    p = f"/ch/{ch:02d}"
    out: set[str] = set()
    if "source" in spec:
        out.add(f"{p}/config")
    if "pan" in spec:
        out.add(f"{p}/mix")
    if "lowcut" in spec:
        out.add(f"{p}/preamp")
    out.update(f"{p}/eq/{int(b)}" for b in spec.get("eq", {}))
    if "comp" in spec:
        out.add(f"{p}/dyn")
    if "gate" in spec:
        out.add(f"{p}/gate")
    return out


def allowed_sections(plan: dict) -> set[str]:
    out: set[str] = set()
    for slot_s, spec in plan.get("fx", {}).items():
        if "preset" in spec or "type" in spec or spec.get("params"):
            out.update({f"/fx/{slot_s}", f"/fx/{slot_s}/par"})
        if "source" in spec:
            out.add(f"/fx/{slot_s}/source")
    spec = plan.get("routing", {})
    if "switch" in spec:
        out.add("/config/routing")
    out.update(f"/config/routing/{k}" for k in ROUTING_BLOCKS if spec.get(k))
    if "preset" in spec:
        banks = spec.get("banks") or list(_rt.ROUTING_PRESET_KEYS)
        out.update(f"/config/routing/{k}" for k in banks)
    for bank, outs in plan.get("output_patch", {}).items():
        out.update(f"/outputs/{bank}/{int(n):02d}" for n in outs)
    return out
