"""The file-writing subcommands: every one writes a new file and never overwrites an
input. cli.py dispatches here; the read-only commands stay there."""

from __future__ import annotations

import contextlib
import io
import os
import shlex
import sys
from pathlib import Path

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

from . import _views
from .model import Scene
from .orchestrators import band_swap as _band_swap
from .services import channelfx as _cfx
from .services import fx as _fx
from .services import routing_edit as _rt
from .services import show as _show
from .services import snippets as _snippets
from .services import transplant as _transplant
from .services import presets as _presets
from .services import transforms as T

EDIT_COMMANDS = frozenset({"set-comp", "set-gate", "set-lowcut", "set-eq", "set-fader",
                           "set-mute", "set-pan", "rename", "extract-preset", "apply-preset",
                           "band-setup", "port-iem", "set-fx", "extract-fx", "apply-fx",
                           "set-routing", "set-input", "set-output", "extract-routing",
                           "apply-routing", "show-build", "transplant"})


def clean(e: Exception) -> str:
    """KeyError stringifies to its repr, which shows the message in stray quotes."""
    return e.args[0] if isinstance(e, KeyError) and e.args else str(e)


def _mirrored(paths: list[str]) -> str:
    """Name the partner strip a stereo link added, so a 2-line edit never reads as 1."""
    return f" (mirrored to {paths[1]})" if len(paths) > 1 else ""


def refuse_overwrite(out: str, *inputs: str) -> None:
    """Edit commands never overwrite in place — reject -o pointing at an input file.

    samefile catches aliases Path.resolve() misses (case variants on macOS/Windows,
    hardlinks); the resolve comparison covers a not-yet-existing out path.
    """
    for p in inputs:
        try:
            same = os.path.exists(out) and os.path.samefile(out, p)
        except OSError:
            same = False
        if same or Path(out).resolve() == Path(p).resolve():
            raise InvalidInputError(
                f"-o {out} would overwrite the input {p}; write a new file instead")


def cmd_port_iem(src: Scene, dst: Scene, out: str) -> None:
    n = T.port_output_routing(src, dst)
    dst.save(out)
    print(f"ported {n} output line(s); wrote {out}")
    print("LOAD-TEST on the console before a gig.")


def require_a_knob(args) -> None:
    """Refuse a zero-flag edit — args.knobs (flag -> dest) is declared per editor in
    _parsers.py. `is` checks: 0.0 == False, and a zero-valued knob is a real edit."""
    if all(getattr(args, dest) is None or getattr(args, dest) is False
           or getattr(args, dest) == [] for dest in args.knobs.values()):
        raise InvalidInputError(
            f"nothing to set: pass at least one of {' '.join(args.knobs)}")


IN_PLACE = frozenset({"set-comp", "set-gate", "set-lowcut", "set-eq", "set-fader",
                      "set-mute", "set-pan", "rename", "apply-preset", "set-fx", "apply-fx",
                      "set-routing", "set-input", "set-output", "apply-routing"})


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
        with open(args.preset, encoding="utf-8", newline="") as fh:
            n = _presets.apply_preset(sc, args.ch, fh.read(), args.scope)
        return f"applied {n} line(s) to ch{args.ch:02d}"
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
            _fx.set_fx_params(sc, args.slot, values)
            did.append(", ".join(f"{k}={v}" for k, v in values.items()))
        return f"FX{args.slot}: " + "; ".join(did)
    elif args.cmd == "apply-fx":
        with open(args.preset, encoding="utf-8", newline="") as fh:
            code = _fx.apply_fx(sc, args.slot, fh.read(), source=args.source)
        return f"loaded {code} preset into FX{args.slot}"
    elif args.cmd == "set-routing":
        if args.key == "switch":
            _rt.set_routswitch(sc, args.blocks[0])
            return f"routing switch {args.blocks[0]}"
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
    elif args.cmd == "apply-routing":
        with open(args.preset, encoding="utf-8", newline="") as fh:
            keys = _rt.apply_routing(sc, fh.read(), args.bank)
        return f"applied routing banks {', '.join(keys)}"
    else:
        raise InvalidInputError(f"{args.cmd} does not edit a scene in place")
    return f"edited {args.strip}{_mirrored(edited)}"


def parse_edit(text: str, scene: str):
    """Parse one ``--edit`` string ("set-eq 5 2 --gain 3") as the matching edit command,
    with the scene and a placeholder output supplied here rather than by the user."""
    from ._parsers import _build_parser   # local: _parsers imports nothing from here
    words = shlex.split(text)
    if not words or words[0] not in IN_PLACE:
        raise InvalidInputError(f"--edit must start with one of {sorted(IN_PLACE)}: {text!r}")
    if "-o" in words or "--out" in words:
        raise InvalidInputError(f"--edit takes no -o; the snippet is the output: {text!r}")
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            args = _build_parser(None).parse_args([words[0], scene, *words[1:], "-o", "-"])
    except SystemExit:
        raise InvalidInputError(f"bad --edit {text!r}: {err.getvalue().strip().splitlines()[-1]}") from None
    return args


def run_edit(args) -> int:
    """Run one of EDIT_COMMANDS; the exit code is the command's."""
    if args.cmd == "transplant":
        refuse_overwrite(args.out, args.src, args.dst)
        if not (args.bus or args.path or args.ch):
            raise InvalidInputError("nothing to carry: pass --bus, --path or --ch")
        src, dst = Scene.load(args.src), Scene.load(args.dst)
        changed = _transplant.transplant(src, dst, buses=args.bus, globs=args.path,
                                         channels=args.ch, scopes=args.scope)
        dst.save(args.out)
        print(f"carried {len(changed)} line(s) from {args.src} into {args.dst}; wrote {args.out}")
        for p in changed[:40]:
            print(f"  {p}")
        if len(changed) > 40:
            print(f"  … {len(changed) - 40} more")
        print("LOAD-TEST on the console before a gig.")
        return 0
    if args.cmd == "show-build":
        def read(p):
            with open(p, encoding="utf-8", newline="") as fh:
                return p, fh.read()
        cues = [_show.parse_cue(c) for c in args.cue]
        files = _show.build_show(args.name, [read(p) for p in args.scene],
                                 [read(p) for p in args.snippet], cues)
        os.makedirs(args.dir, exist_ok=True)
        for fname in files:
            if os.path.exists(os.path.join(args.dir, fname)):
                raise InvalidInputError(f"{os.path.join(args.dir, fname)} exists; "
                                        "write a new directory or name")
        for fname, text in files.items():
            atomic_write_bytes(os.path.join(args.dir, fname), text.encode("utf-8"))
        print(f"wrote {args.name}.shw with {len(cues)} cue(s), {len(args.scene)} scene(s), "
              f"{len(args.snippet)} snippet(s) -> {args.dir}")
        return 0
    if args.cmd == "extract-routing":
        refuse_overwrite(args.out, args.scene)
        name = args.name or os.path.splitext(os.path.basename(args.out))[0]
        rou = _rt.extract_routing(Scene.load(args.scene), name)
        atomic_write_bytes(args.out, rou.encode("utf-8"))
        print(f"wrote routing preset -> {args.out}")
        return 0
    if args.cmd == "extract-fx":
        refuse_overwrite(args.out, args.scene)
        name = args.name or os.path.splitext(os.path.basename(args.out))[0]
        efx = _fx.extract_fx(Scene.load(args.scene), args.slot, name)
        atomic_write_bytes(args.out, efx.encode("utf-8"))
        print(f"wrote FX{args.slot} preset -> {args.out}")
        return 0
    if args.cmd in IN_PLACE:
        inputs = ([args.scene, args.preset]
                  if args.cmd in ("apply-preset", "apply-fx", "apply-routing") else [args.scene])
        refuse_overwrite(args.out, *inputs)
        sc = Scene.load(args.scene)
        msg = apply_edit(sc, args)
        sc.save(args.out)
        print(f"{msg}; wrote {args.out}\nLOAD-TEST on the console before a gig.")
        return 0
    if args.cmd == "extract-preset":
        refuse_overwrite(args.out, args.scene)
        chn = _presets.extract_preset(Scene.load(args.scene), args.ch, args.scope,
                                      header=args.header)
        atomic_write_bytes(args.out, chn.encode("utf-8"))   # LF-only, as Scene.save
        print(f"wrote preset for ch{args.ch:02d} -> {args.out}")
        return 0
    if args.cmd == "band-setup":
        refuse_overwrite(args.out, args.template, args.plan)
        if args.snippet:
            refuse_overwrite(args.snippet, args.template, args.plan, args.out)
        # every plan-level problem is one class of user error: exit 2, write nothing
        try:
            plan = _band_swap.load_plan(args.plan)
            rep = _band_swap.run(args.template, plan, args.out)
        except (KeyError, ValueError, OSError) as e:
            print(f"plan failed, nothing written: {clean(e)}", file=sys.stderr)
            return 2
        print(f"applied plan: {rep['lines_changed']} line(s) over "
              f"{len(rep['changed'])} path(s); wrote {args.out}")
        if args.snippet:
            name = os.path.splitext(os.path.basename(args.snippet))[0]
            snip = _snippets.make_snippet(Scene.load(args.template), Scene.load(args.out), name)
            snip.scene.save(args.snippet)
            _views.cmd_snippet(snip, args.snippet)
        print("LOAD-TEST on the console before a gig.")
        return 0
    if args.cmd == "port-iem":
        refuse_overwrite(args.out, args.src, args.dst)
        cmd_port_iem(Scene.load(args.src), Scene.load(args.dst), args.out)
        return 0
    raise InvalidInputError(f"not an edit command: {args.cmd}")
