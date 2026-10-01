"""CLI glue for `load`: a scene or snippet onto the running desk, read back until it holds."""

from __future__ import annotations

import os
import sys

from pf_core.exceptions import InvalidInputError

from . import _json
from . import _views_desk as _vdesk
from ._cli_files import file_kind, load_checked
from .services import load as _load
from .services import osc as _osc


def run_load(args) -> int:
    """Exit 2 when the desk does not answer, 1 when a line is not read back as written,
    130 on Ctrl-C; after writes went out, both say the desk may hold part of the file."""
    kind = file_kind(args.file)
    if kind not in (None, "scn", "snp"):
        raise InvalidInputError(f"{args.file}: load takes a scene or a snippet, not a .{kind}")
    target = load_checked(args.file)
    try:
        _load.refuse_unloadable(target)
    except ValueError as e:
        raise InvalidInputError(f"{args.file}: {e}; nothing written") from None
    name = os.path.basename(args.file)
    try:
        result = _load.load_scene(target, args.ip, port=_osc.X32_PORT, timeout=args.timeout,
                                  passes=args.passes)
    except _osc.OscError as e:
        print(f"load failed: {e}; nothing was written", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("stopped before anything was written", file=sys.stderr)
        return 130
    if args.json:
        _json.dump(_json.load_doc(args.file, result))
    else:
        _vdesk.cmd_load(result, target, name, args.passes)
    partial = f"the desk may hold part of {name}; run load again to finish"
    if result.interrupted:
        print(f"stopped: {partial}", file=sys.stderr)
        return 130
    if result.error:
        print(f"load failed: {result.error}; {partial}", file=sys.stderr)
        return 2
    return 0 if result.ok else 1
