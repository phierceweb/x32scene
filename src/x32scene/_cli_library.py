"""CLI glue for `audit` and `history`: commands that read a directory of scenes."""

from __future__ import annotations

import sys

from pf_core.exceptions import InvalidInputError

from . import _json
from . import _json_views
from . import _views
from .services import audit as _audit


def _load(scenes_dir: str):
    lib, errors = _audit.load_library(scenes_dir)
    if not lib and not errors:
        raise InvalidInputError(f"no .scn files found in {scenes_dir}")
    return lib, errors


def run_audit(args) -> int:
    """Exit 1 when a file does not load or an invariant is violated."""
    lib, errors = _load(args.dir)
    violations = _audit.check_invariants(lib)
    if args.json:
        _json.dump(_json_views.audit_doc(lib, args.dir, errors, violations))
    else:
        print(_audit.report(lib, args.dir, errors))
    return 1 if errors or violations else 0


def run_history(args) -> int:
    if not args.dir:
        raise InvalidInputError("no scene directory: pass --dir or set X32SCENE_CORPUS")
    lib, errors = _load(args.dir)
    for err in errors:
        print(f"skipped {err}", file=sys.stderr)
    if args.json:
        _json.dump(_json.history_doc(lib, args.paths))
    else:
        _views.cmd_history(lib, args.paths)
    return 0
