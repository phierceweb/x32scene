"""CLI glue for `show`: list a .shw index, or check its cues and companion files."""

from __future__ import annotations

import os

from . import _json
from . import _views
from ._cli_files import read_checked
from .model import read_file
from .services import show as _show
from .services import show_check as _check


def run_show(args) -> int:
    """With --check, exit 1 when any cue or companion fails."""
    show = _show.read_show(read_checked(args.file))
    if not args.check:
        if args.json:
            _json.dump(_json.show_doc(show))
        else:
            _views.cmd_show(show)
        return 0
    folder = os.path.dirname(args.file)
    stem = os.path.splitext(os.path.basename(args.file))[0]
    findings = _check.check_show(show, stem, lambda name: read_file(os.path.join(folder, name)))
    if args.json:
        _json.dump(_json.preflight_doc(findings, _check.counts(show)))
    else:
        print(_check.report(show, findings))
    return 1 if findings else 0
