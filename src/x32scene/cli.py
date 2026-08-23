"""Command-line interface for the X32 scene toolkit (argparse).

Read-only display commands live in _views.py and the file-writing edit commands in
_cli_edits.py; this module is dispatch plus the exception boundary. Invoked as
`x32scene <subcommand>` (or `python -m x32scene.cli`).
"""

from __future__ import annotations

import os
import sys

from pf_core.exceptions import FlowException, InvalidInputError
from pf_core.log import get_logger, setup_logging

from . import _json
from . import _views
from . import _views_ports as _ports
from . import _views_desk as _vdesk
from . import _views_report as _report
from ._cli_edits import EDIT_COMMANDS, apply_edit, clean, parse_edit, refuse_overwrite, run_edit
from ._parsers import _build_parser
from .model import Scene
from .services import audit as _audit
from .services import desk as _desk
from .services import headers as _headers
from .services import matrix as _matrix
from .services import meters as _meters
from .services import show as _show
from .services import snippets as _snippets
from .services import osc as _osc
from .services import preflight as _preflight
from .services import stage as _stage
from .services import transplant as _transplant
from .services.diff import diff as _diff


_VIEWS = {
    "info": _views.cmd_info,
    "console": _vdesk.cmd_console,
    "buses": _views.cmd_buses,
    "inputs": _views.cmd_inputs,
    "record-map": _views.cmd_record_map,
    "fx": _views.cmd_fx,
    "dca": _views.cmd_dca,
    "explain": _views.cmd_explain,
}

_JSON_DOCS = {
    "console": _json.console_doc,
    "inputs": _json.inputs_doc,
    "record-map": _json.record_map_doc,
    "fx": _json.fx_doc,
    "dca": _json.groups_doc,
}

def _run(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "set-fader":
        # argparse reads a positional "-oo" as "-o o"; let the documented alias through
        argv = ["oo" if a == "-oo" else a for a in argv]
    args = _build_parser(__doc__).parse_args(argv)
    if args.cmd == "audit" and not args.dir:
        raise InvalidInputError("no scene directory: pass DIR or set X32SCENE_CORPUS")
    if args.cmd in ("pull", "live-diff", "desk", "meters") and not args.ip:
        raise InvalidInputError("no console IP: pass --ip or set X32SCENE_IP")
    if args.cmd in EDIT_COMMANDS:
        return run_edit(args)

    if args.cmd == "audit":
        lib, errors = _audit.load_library(args.dir)
        if not lib and not errors:
            raise InvalidInputError(f"no .scn files found in {args.dir}")
        print(_audit.report(lib, args.dir, errors))
        return 1 if errors or _audit.check_invariants(lib) else 0
    if args.cmd == "preflight":
        if not args.config:
            raise InvalidInputError("preflight needs --config or X32SCENE_CONFIG")
        expected = _preflight.load_expected(args.config)
        stage = _stage.load_stage(args.stage) if args.stage else None
        findings = _preflight.preflight(Scene.load(args.scene), expected, stage=stage)
        checked = _preflight.coverage(expected, stage)
        if args.json:
            _json.dump(_json.preflight_doc(findings, checked))
        else:
            print(_preflight.report(findings, checked))
        return 1 if any(f.severity == "FAIL" for f in findings) else 0
    if args.cmd == "meters":
        try:
            peaks = _meters.read_meters(args.ip, _meters.WHAT[args.what], seconds=args.seconds)
        except _osc.OscError as e:
            print(f"meters failed: {e}", file=sys.stderr)
            return 2
        sc = Scene.load(args.scene) if args.scene else None
        if args.json:
            _json.dump(_json.meters_doc(peaks, sc))
        else:
            _vdesk.cmd_meters(peaks, sc, show_all=args.all)
        return 0
    if args.cmd == "desk":
        try:
            info = _desk.read_desk(args.ip, timeout=args.timeout, library=not args.no_library)
        except _osc.OscError as e:
            print(f"desk read failed: {e}", file=sys.stderr)
            return 2
        if args.json:
            _json.dump(_json.desk_doc(info))
        else:
            _vdesk.cmd_desk(info)
        return 0
    if args.cmd in ("pull", "live-diff"):
        if args.cmd == "pull":
            refuse_overwrite(args.out, args.reference)
        ref = Scene.load(args.reference if args.cmd == "pull" else args.scene)
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
        else:
            _views.cmd_diff(ref, live)
        return 0
    if args.cmd == "ports":
        sc = Scene.load(args.scene)
        physical = (_preflight.physical_outputs(_preflight.load_expected(args.config))
                    if args.config else None)
        stage = _stage.load_stage(args.stage) if args.stage else None
        if args.json:
            _json.dump(_json.ports_doc(sc, args.bank, stage))
        else:
            _ports.cmd_ports(sc, physical, bank=args.bank, stage=stage)
        return 0
    if args.cmd == "iem":
        sc = Scene.load(args.scene)
        if args.json:
            _json.dump(_json.iem_doc(sc, args.bus))
        else:
            _views.cmd_iem(sc, args.bus)
        return 0
    if args.cmd == "diff":
        a, b = Scene.load(args.a), Scene.load(args.b)
        if args.json:
            _json.dump(_json.diff_doc(_diff(a, b), b))
        elif args.by_strip:
            _views.cmd_diff_by_strip(a, b)
        else:
            _views.cmd_diff(a, b)
        return 0
    if args.cmd == "report":
        physical = (_preflight.physical_outputs(_preflight.load_expected(args.config))
                    if args.config else None)
        stage = _stage.load_stage(args.stage) if args.stage else None
        _report.cmd_report(Scene.load(args.scene), physical, stage)
        return 0
    if args.cmd == "iem-matrix":
        sc = Scene.load(args.scene)
        if args.compare:
            m = _matrix.compare(sc, Scene.load(args.compare), args.buses)
        else:
            m = _matrix.iem_matrix(sc, args.buses, all_rows=args.all)
        if args.json:
            _json.dump(_json.iem_matrix_doc(m))
        else:
            _report.cmd_iem_matrix(m)
        return 0
    if args.cmd == "history":
        if not args.dir:
            raise InvalidInputError("no scene directory: pass --dir or set X32SCENE_CORPUS")
        lib, errors = _audit.load_library(args.dir)
        if not lib and not errors:
            raise InvalidInputError(f"no .scn files found in {args.dir}")
        for err in errors:
            print(f"skipped {err}", file=sys.stderr)
        if args.json:
            _json.dump(_json.history_doc(lib, args.paths))
        else:
            _views.cmd_history(lib, args.paths)
        return 0
    if args.cmd == "snippet":
        absolute = len(args.scenes) == 1 and not args.edit and (args.bus or args.only)
        if len(args.scenes) != (1 if args.edit or absolute else 2):
            raise InvalidInputError("snippet takes two scenes (a delta), one scene with --edit, "
                                    "or one scene with --bus/--only (those lines as they are)")
        refuse_overwrite(args.out, *args.scenes)
        name = args.name or os.path.splitext(os.path.basename(args.out))[0]
        base = Scene.load(args.scenes[0])
        if absolute:
            base = Scene([base.lines[0]], True)   # every selected line, not just what moved
        if args.edit:
            edited = Scene.load(args.scenes[0])
            for text in args.edit:
                print(apply_edit(edited, parse_edit(text, args.scenes[0])))
        else:
            edited = Scene.load(args.scenes[-1])
        only = None
        if args.bus or args.only:
            keep = set()
            for bus in args.bus:
                keep.update(_transplant.bus_mix_paths(edited, bus))
            keep.update(_transplant.glob_paths(edited, args.only))
            only = keep.__contains__
        snip = _snippets.make_snippet(base, edited, name, only)
        if len(snip.scene.lines) == 1:
            raise InvalidInputError("no changes to write")
        snip.scene.save(args.out)
        _views.cmd_snippet(snip, args.out)
        return 0
    if args.cmd == "vocab":
        if args.json:
            _json.dump(_json.vocab_doc(args.what, args.key))
        else:
            _vdesk.cmd_vocab(args.what, args.key)
        return 0
    if args.cmd == "fx-types":
        if args.json:
            _json.dump(_json.fx_types_doc(args.code))
        else:
            _vdesk.cmd_fx_types(args.code)
        return 0
    if args.cmd == "header":
        with open(args.file, encoding="utf-8", newline="") as fh:
            text = fh.read()
        doc = _headers.decode_header(text)
        if doc is None:
            raise InvalidInputError(f"{args.file}: no header line")
        if args.json:
            _json.dump(doc)
        else:
            _views.cmd_header(doc)
        return 0
    if args.cmd == "show":
        with open(args.file, encoding="utf-8", newline="") as fh:
            show = _show.read_show(fh.read())
        if args.json:
            _json.dump(_json.show_doc(show))
        else:
            _views.cmd_show(show)
        return 0
    if args.cmd in _JSON_DOCS:
        sc = Scene.load(args.scene)
        if args.json:
            _json.dump(_JSON_DOCS[args.cmd](sc))
        else:
            _VIEWS[args.cmd](sc)
        return 0
    _VIEWS[args.cmd](Scene.load(args.scene))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: pf-core logging + exception boundary. Console stays quiet
    (runs log at debug); set ``LOG_FILE=path`` for a JSON-lines audit trail."""
    setup_logging(app_logger_name="x32scene")
    log = get_logger("x32scene")
    argv = list(sys.argv[1:] if argv is None else argv)
    log.debug("invoke", argv=argv)
    try:
        rc = _run(argv)
        sys.stdout.flush()  # surface a closed pipe here, not at interpreter shutdown
    except BrokenPipeError:
        # reader closed early (`| head`): drop the shutdown flush so it can't tail
        # a traceback onto otherwise clean output
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except (FlowException, OSError, ValueError, KeyError, IndexError) as e:
        log.debug("error", error=str(e), exc_info=True)
        print(f"x32scene: {clean(e)}", file=sys.stderr)
        return 1
    log.debug("done", rc=rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
