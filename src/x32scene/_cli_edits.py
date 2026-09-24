"""The file-writing subcommands: every one writes a new file and never overwrites an
input. cli.py dispatches here; the read-only commands stay there."""

from __future__ import annotations

import os
import sys

from pf_core.exceptions import InvalidInputError

from ._cli_files import (clean, load_checked, read_checked, refuse_overwrite, write_all,
                         write_into)
from ._cli_inplace import IN_PLACE, apply_edit
from ._cli_presets import run_extract_library
from ._cli_record import RECORD_COMMANDS, run_record
from ._cli_sends import SEND_COMMANDS, run_send_tap

from . import _views, _views_band
from . import _views_ports as _ports
from .model import Scene, write_file
from .orchestrators import band_swap as _band_swap
from .services import buslink as _buslink
from .services import fx as _fx
from .services import routing_edit as _rt
from .services import show as _show
from .services import snippets as _snippets
from .services import stagebox as _stagebox
from .services import transplant as _transplant
from .services import presets as _presets
from .services import transforms as T

EDIT_COMMANDS = frozenset({"set-comp", "set-gate", "set-lowcut", "set-eq", "set-fader",
                           "set-mute", "set-pan", "rename", "extract-preset", "apply-preset",
                           "band-setup", "port-iem", "set-fx", "extract-fx", "apply-fx",
                           "set-routing", "set-input", "set-output", "extract-routing",
                           "apply-routing", "show-build", "transplant", "move-inputs",
                           "set-bus-link"}) | SEND_COMMANDS | RECORD_COMMANDS


def cmd_port_iem(src: Scene, dst: Scene, out: str) -> None:
    n = T.port_output_routing(src, dst)
    dst.save(out)
    print(f"ported {n} output line(s); wrote {out}")
    print("LOAD-TEST on the console before a gig.")


def run_edit(args) -> int:
    """Run one of EDIT_COMMANDS; the exit code is the command's."""
    if args.cmd == "transplant":
        refuse_overwrite(args.out, args.src, args.dst, force=args.force)
        if not (args.bus or args.path or args.ch):
            raise InvalidInputError("nothing to carry: pass --bus, --path or --ch")
        src, dst = load_checked(args.src), load_checked(args.dst)
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
            return p, read_checked(p)
        cues = [_show.parse_cue(c) for c in args.cue]
        files = _show.build_show(args.name, [read(p) for p in args.scene],
                                 [read(p) for p in args.snippet], cues)
        # a show is written into the layout it reads from, so an input can be one of
        # the names about to be written
        write_into(args.dir, [(os.path.join(args.dir, fname), text.encode("utf-8"))
                              for fname, text in files.items()],
                   *args.scene, *args.snippet, force=args.force)
        print(f"wrote {args.name}.shw with {len(cues)} cue(s), {len(args.scene)} scene(s), "
              f"{len(args.snippet)} snippet(s) -> {args.dir}")
        return 0
    if args.cmd == "extract-routing":
        refuse_overwrite(args.out, args.scene, force=args.force)
        name = args.name or os.path.splitext(os.path.basename(args.out))[0]
        rou = _rt.extract_routing(load_checked(args.scene), name)
        write_file(args.out, rou.encode("utf-8"))
        print(f"wrote routing preset -> {args.out}")
        return 0
    if args.cmd == "extract-fx":
        refuse_overwrite(args.out, args.scene, force=args.force)
        name = args.name or os.path.splitext(os.path.basename(args.out))[0]
        efx = _fx.extract_fx(load_checked(args.scene), args.slot, name)
        write_file(args.out, efx.encode("utf-8"))
        print(f"wrote FX{args.slot} preset -> {args.out}")
        return 0
    if args.cmd == "set-bus-link":
        refuse_overwrite(args.out, args.scene, force=args.force)
        sc = load_checked(args.scene)
        edit = _buslink.set_bus_link(sc, args.bus, args.state == "on")
        sc.save(args.out)
        _ports.cmd_set_bus_link(sc, edit, args.out)
        return 0
    if args.cmd in SEND_COMMANDS:
        return run_send_tap(args)
    if args.cmd in RECORD_COMMANDS:
        return run_record(args)
    if args.cmd in IN_PLACE:
        inputs = ([args.scene, args.preset]
                  if args.cmd in ("apply-preset", "apply-fx", "apply-routing") else [args.scene])
        refuse_overwrite(args.out, *inputs, force=args.force)
        sc = load_checked(args.scene)
        msg = apply_edit(sc, args)
        sc.save(args.out)
        print(f"{msg}; wrote {args.out}\nLOAD-TEST on the console before a gig.")
        return 0
    if args.cmd == "extract-preset":
        if (args.ch is None) != args.all:
            raise InvalidInputError("extract-preset takes CH or --all, not both" if args.all
                                    else "extract-preset needs a channel CH, or --all")
        if args.all:
            return run_extract_library(args)
        refuse_overwrite(args.out, args.scene, force=args.force)
        chn = _presets.extract_preset(load_checked(args.scene), args.ch, args.scope,
                                      header=args.header)
        write_file(args.out, chn.encode("utf-8"))   # LF-only, as Scene.save
        print(f"wrote preset for ch{args.ch:02d} -> {args.out}")
        return 0
    if args.cmd == "band-setup":
        # every plan-level problem is one class of user error: exit 2, write nothing
        try:
            plan = _band_swap.load_plan(args.plan)
        except (KeyError, IndexError, TypeError, ValueError, OSError) as e:
            print(f"plan failed, nothing written: {clean(e)}", file=sys.stderr)
            return 2
        # the plan names presets it reads: inputs the arguments alone do not reveal
        inputs = [args.template, args.plan, *_band_swap.plan_inputs(plan)]
        refuse_overwrite(args.out, *inputs, force=args.force)
        if args.snippet:
            refuse_overwrite(args.snippet, *inputs, args.out, force=args.force, flag="--snippet")
        forced = {p for p in (args.out, args.snippet) if p and os.path.lexists(p)}
        try:
            template = load_checked(args.template)   # shape-checked here; build() loads its own
            edited, rep = _band_swap.build(args.template, plan)
        except (KeyError, IndexError, TypeError, ValueError, OSError) as e:
            print(f"plan failed, nothing written: {clean(e)}", file=sys.stderr)
            return 2
        files = [(args.out, edited.dump().encode("utf-8"))]
        snip = None
        if args.snippet:
            name = os.path.splitext(os.path.basename(args.snippet))[0]
            snip = _snippets.make_snippet(template, edited, name)
            if len(snip.scene.lines) > 1:
                files.append((args.snippet, snip.scene.dump().encode("utf-8")))
        write_all(files, forced)
        _views_band.cmd_band_setup(template, edited, rep, args.out)
        if snip is not None and len(files) > 1:
            _views.cmd_snippet(snip, args.snippet)
        elif snip is not None:
            lost = f" ({', '.join(snip.skipped)})" if snip.skipped else ""
            if args.snippet in forced and os.path.lexists(args.snippet):   # a stale one goes
                os.remove(args.snippet)
                print(f"the plan changes nothing a snippet can carry{lost}; removed the old "
                      f"{args.snippet}")
            else:
                print(f"the plan changes nothing a snippet can carry{lost}; nothing written "
                      f"to {args.snippet}")
        print("LOAD-TEST on the console before a gig.")
        return 0
    if args.cmd == "port-iem":
        refuse_overwrite(args.out, args.src, args.dst, force=args.force)
        cmd_port_iem(load_checked(args.src), load_checked(args.dst), args.out)
        return 0
    if args.cmd == "move-inputs":
        refuse_overwrite(args.out, args.scene, force=args.force)
        sc = load_checked(args.scene)
        moves = _stagebox.move_to_stagebox(sc, args.moves, port=args.to,
                                           move_gain=not args.no_gain)
        sc.save(args.out)
        _views.cmd_move_inputs(sc, moves, args.out, move_gain=not args.no_gain)
        return 0
    raise InvalidInputError(f"not an edit command: {args.cmd}")
