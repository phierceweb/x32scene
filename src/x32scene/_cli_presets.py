"""CLI glue for a preset folder: `presets-diff` and `extract-preset --all`."""

from __future__ import annotations

import os

from pf_core.exceptions import InvalidInputError

from . import _json
from . import _views_presets as _vpresets
from ._cli_files import (load_checked, read_listed, refuse_not_directory, refuse_overwrite_all,
                         write_all)
from .services import preset_library as _lib


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
    refuse_not_directory(args.out, "-o")
    presets, skipped, shared = _lib.extract_library(load_checked(args.scene), args.scope,
                                                    header=args.header)
    if not presets and shared:
        raise InvalidInputError(f"{args.scene}: every named channel shares a preset file name, "
                                "nothing written: "
                                + "; ".join(_vpresets.shared_name(s) for s in shared))
    if not presets:
        raise InvalidInputError(f"{args.scene}: no channel has a scribble name; nothing to write")
    paths = [os.path.join(args.out, p.file) for p in presets]
    refuse_overwrite_all(paths, args.scene, force=args.force)
    try:
        os.makedirs(args.out, exist_ok=True)
    except OSError as e:
        raise InvalidInputError(f"-o {args.out}: {e.strerror or e}") from None
    write_all([(path, p.text.encode("utf-8")) for p, path in zip(presets, paths, strict=True)],
              args.out)
    _vpresets.cmd_extract_library(presets, skipped, shared, paths)
    return 0
