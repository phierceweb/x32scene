"""CLI glue for `pull` and `live-diff`: one read of the desk against a reference scene."""

from __future__ import annotations

import sys

from . import _json
from . import _json_views
from . import _views
from ._cli_files import load_checked, refuse_overwrite
from .services import osc as _osc


def run_pull(args) -> int:
    """Exit 2 when the desk read fails; unanswered paths warn on stderr."""
    if args.cmd == "pull":
        refuse_overwrite(args.out, args.reference, force=args.force)
    ref = load_checked(args.reference if args.cmd == "pull" else args.scene)
    try:
        live, unanswered = _osc.pull_scene_like(ref, args.ip, timeout=args.timeout)
    except _osc.OscError as e:
        print(f"pull failed: {e}", file=sys.stderr)
        return 2
    if unanswered:
        head = ", ".join(unanswered[:8]) + (" …" if len(unanswered) > 8 else "")
        print(f"unanswered paths ({len(unanswered)}): {head}", file=sys.stderr)
    if args.cmd == "pull":
        live.save(args.out)
        print(f"pulled {len(live.lines)} line(s) from {args.ip}; wrote {args.out}")
    elif args.json:
        _json.dump(_json_views.live_diff_doc(ref, live, unanswered))
    else:
        _views.cmd_diff(ref, live)
    return 0
