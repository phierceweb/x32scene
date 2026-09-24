"""The in-place edits: the set-* commands and the preset loads that change lines of one scene,
shared by the edit commands and `snippet --edit`."""

from __future__ import annotations

from pf_core.exceptions import InvalidInputError

from ._cli_files import read_lf
from ._cli_presets import apply_preset_edit
from ._cli_record import RECORD_COMMANDS, record_edit
from ._cli_sends import SEND_COMMANDS, send_tap_edit
from .model import Scene
from .services import channelfx as _cfx
from .services import fx as _fx
from .services import routing_edit as _rt
from .services import transforms as T


def _mirrored(paths: list[str]) -> str:
    """Name the partner strip a stereo link added, so a 2-line edit never reads as 1."""
    return f" (mirrored to {paths[1]})" if len(paths) > 1 else ""


def require_a_knob(args) -> None:
    """Refuse a zero-flag edit — args.knobs (flag -> dest) is declared per editor in
    _parsers.py. `is` checks: 0.0 == False, and a zero-valued knob is a real edit."""
    if all(getattr(args, dest) is None or getattr(args, dest) is False
           or getattr(args, dest) == [] for dest in args.knobs.values()):
        raise InvalidInputError(
            f"nothing to set: pass at least one of {' '.join(args.knobs)}")


IN_PLACE = frozenset({"set-comp", "set-gate", "set-lowcut", "set-eq", "set-fader",
                      "set-mute", "set-pan", "rename", "apply-preset", "set-fx", "apply-fx",
                      "set-routing", "set-input", "set-output", "apply-routing"}) | SEND_COMMANDS | RECORD_COMMANDS


def apply_edit(sc: Scene, args) -> str:
    """Apply one IN_PLACE edit command to ``sc`` and say what changed."""
    linked = False if getattr(args, "no_link", False) else None
    if args.cmd in ("set-comp", "set-gate", "set-lowcut", "set-eq", "set-fx", "set-output"):
        require_a_knob(args)
    if args.cmd == "set-comp":
        edited = _cfx.set_comp(sc, args.strip, thr=args.thr, ratio=args.ratio,
                               makeup=args.makeup, attack=args.attack,
                               release=args.release, linked=linked)
    elif args.cmd == "set-gate":
        edited = _cfx.set_gate(sc, args.strip, thr=args.thr, rng=args.rng,
                               attack=args.attack, release=args.release, linked=linked)
    elif args.cmd == "set-lowcut":
        on = True if args.on else (False if args.off else None)
        edited = _cfx.set_lowcut(sc, args.strip, on=on, freq=args.freq, linked=linked)
    elif args.cmd == "set-eq":
        edited = _cfx.set_eq_band(sc, args.strip, args.band, type=args.type, freq=args.freq,
                                  gain=args.gain, q=args.q, linked=linked)
        return f"set {args.strip} EQ band {args.band}{_mirrored(edited)}"
    elif args.cmd == "set-fader":
        edited = T.set_fader(sc, args.strip, T.parse_level(args.level), linked=linked)
    elif args.cmd == "set-mute":
        edited = T.set_mute(sc, args.strip, args.state == "on", linked=linked)
    elif args.cmd == "set-pan":
        edited = T.set_pan(sc, args.strip, args.pan)
    elif args.cmd == "rename":
        edited = T.rename_strip(sc, args.strip, args.name)
    elif args.cmd == "apply-preset":
        return apply_preset_edit(sc, args)
    elif args.cmd == "set-fx":
        did = []
        if args.type:
            _fx.set_fx_type(sc, args.slot, args.type)
            did.append(f"type {args.type} (params reset to defaults)")
        if args.source:
            _fx.set_fx_source(sc, args.slot, *args.source.split(",", 1))
            did.append(f"source {args.source}")
        if args.set:
            values = {}
            for item in args.set:
                name, sep, value = item.partition("=")
                if not sep:
                    raise InvalidInputError(f"--set wants NAME=VALUE, got {item!r}")
                values[name.strip()] = value.strip()
            written = _fx.set_fx_params(sc, args.slot, values)
            did.append(", ".join(f"{k}={v}" for k, v in written.items()))
        return f"FX{args.slot}: " + "; ".join(did)
    elif args.cmd == "apply-fx":
        code = _fx.apply_fx(sc, args.slot, read_lf(args.preset), source=args.source)
        return f"loaded {code} preset into FX{args.slot}"
    elif args.cmd == "set-routing":
        if args.key == "switch":
            return f"routing switch {_rt.set_routswitch(sc, args.blocks[0])}"
        blocks = {}
        for item in args.blocks:
            label, sep, value = item.partition("=")
            if not sep:
                raise InvalidInputError(f"want BLOCK=TOKEN, got {item!r}")
            blocks[label] = value
        _rt.set_routing(sc, args.key, blocks)
        return f"routing {args.key}: " + ", ".join(f"{k}={v}" for k, v in blocks.items())
    elif args.cmd == "set-input":
        return f"ch{args.ch:02d} source -> {_rt.set_input(sc, args.ch, args.source)}"
    elif args.cmd == "set-output":
        inv = None if args.invert is None else args.invert == "on"
        words = _rt.set_output(sc, args.bank, args.n, src=args.src, pos=args.pos, invert=inv)
        return f"{args.bank} {args.n:02d}: {words}"
    elif args.cmd in SEND_COMMANDS:
        return send_tap_edit(sc, args, linked)
    elif args.cmd in RECORD_COMMANDS:
        return record_edit(sc, args)
    elif args.cmd == "apply-routing":
        keys = _rt.apply_routing(sc, read_lf(args.preset), args.bank)
        return f"applied routing banks {', '.join(keys)}"
    else:
        raise InvalidInputError(f"{args.cmd} does not edit a scene in place")
    return f"edited {args.strip}{_mirrored(edited)}"
