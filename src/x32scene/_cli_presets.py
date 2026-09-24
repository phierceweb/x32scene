"""CLI glue for a preset folder: `presets-diff` and `extract-preset --all`."""

from __future__ import annotations

import os

from pf_core.exceptions import InvalidInputError

from . import _json
from . import _views_presets as _vpresets
from ._cli_files import load_checked, read_lf, read_listed, write_into
from .model import Scene
from .services import preset_library as _lib
from .services.channelfx import pair_linked
from .services import presets as _presets


def apply_preset_edit(sc: Scene, args) -> str:
    text = read_lf(args.preset)
    mirrored = _presets.mirrored_sends(sc, args.ch, text, args.scope)
    n = _presets.apply_preset(sc, args.ch, text, args.scope)
    skipped = _presets.unflagged_scopes(text, args.scope)
    notes = [f"skipped {', '.join(skipped)}: the preset header does not flag them present"
             ] if skipped else []
    own = f"/ch/{args.ch:02d}/"
    across = [(p, src) for p, src in mirrored if p.startswith(own)]
    if across:
        notes.append("mirrored " + ", ".join(f"{p} from {src}" for p, src in across)
                     + " across a stereo-linked bus pair")
    partner = pair_linked(sc, f"/ch/{args.ch:02d}")
    other = int(partner.rsplit("/", 1)[1]) if partner else None
    onto = [(p, src) for p, src in mirrored if not p.startswith(own)]
    if onto:
        notes.append("mirrored " + ", ".join(f"{p} from {src}" for p, src in onto)
                     + f" onto the stereo-linked ch{other:02d}")
    if partner and _presets.writes_beyond_sends(text, args.scope):
        notes.append(f"ch{other:02d} keeps its own processing: a load that reconciles the pair "
                     f"can end at ch{max(args.ch, other):02d}'s, so apply the preset to "
                     f"ch{other:02d} too")
    return f"applied {n} line(s) to ch{args.ch:02d}" + "".join(f"; {note}" for note in notes)


def run_presets_diff(args) -> int:
    """Exit 1 when any preset drifts or cannot be read; one that matches no single channel
    does not count."""
    results = _lib.check_library(load_checked(args.scene), args.dir, args.scope,
                                 read=read_listed)
    if not results:
        raise InvalidInputError(f"no .chn files found in {args.dir}")
    if args.json:
        _json.dump(_json.presets_diff_doc(results))
    else:
        _vpresets.cmd_presets_diff(results)
    return 0 if _json.presets_ok(results) else 1


def run_extract_library(args) -> int:
    presets, skipped, shared = _lib.extract_library(load_checked(args.scene), args.scope,
                                                    header=args.header)
    if not presets and shared:
        raise InvalidInputError(f"{args.scene}: every named channel shares a preset file name, "
                                "nothing written: "
                                + "; ".join(_vpresets.shared_name(s) for s in shared))
    if not presets:
        raise InvalidInputError(f"{args.scene}: no channel has a scribble name; nothing to write")
    paths = [os.path.join(args.out, p.file) for p in presets]
    write_into(args.out, [(path, p.text.encode("utf-8"))
                          for p, path in zip(presets, paths, strict=True)],
               args.scene, force=args.force)
    _vpresets.cmd_extract_library(presets, skipped, shared, paths)
    return 0
