"""CLI glue for `preflight`: check a scene against an expected-config, or write one from it."""

from __future__ import annotations

from datetime import date

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

from . import _json
from ._cli_files import load_checked, refuse_overwrite, refuse_unwritable
from .services import preflight as _preflight
from .services import preflight_regen as _regen
from .services import stage as _stage
from .services import validate as _validate


def run_preflight(args) -> int:
    """Exit 1 when any finding is a FAIL."""
    if args.regenerate is not None:
        return _run_regenerate(args)
    if args.force:
        raise InvalidInputError("--force only applies with --regenerate")
    config = args.config if args.config is not None else args.config_env
    stage_path = args.stage if args.stage is not None else args.stage_env
    if not config:
        raise InvalidInputError(
            "preflight needs --config or X32SCENE_CONFIG; write one from a scene you trust "
            "with `x32scene preflight GOOD.scn --regenerate rig.json`")
    expected = _preflight.load_expected(config)
    stage = _stage.load_stage(stage_path) if stage_path else None
    findings = _preflight.preflight(load_checked(args.scene), expected, stage=stage)
    checked = _preflight.coverage(expected, stage)
    if args.json:
        _json.dump(_json.preflight_doc(findings, checked))
    else:
        print(_preflight.report(findings, checked))
    return 1 if any(f.severity == "FAIL" for f in findings) else 0


def _run_regenerate(args) -> int:
    # a check reads a config and a sidecar and reports; a regenerate writes and checks nothing
    typed = [flag for flag, given in (("--config", args.config is not None),
                                      ("--stage", args.stage is not None),
                                      ("--json", args.json)) if given]
    if typed:
        raise InvalidInputError(f"--regenerate writes a config and checks nothing; "
                                f"drop {', '.join(typed)}")
    kind = _validate.kind_of(args.scene)
    if kind not in (None, "scn"):
        raise InvalidInputError(f"--regenerate describes a whole console and needs a scene; "
                                f"{args.scene} is a .{kind} file")
    refuse_unwritable(args.regenerate, "--regenerate")
    refuse_overwrite(args.regenerate, args.scene, force=args.force, flag="--regenerate")
    out_kind = _validate.kind_of(args.regenerate)
    if out_kind is not None:
        raise InvalidInputError(f"--regenerate writes a JSON config; {args.regenerate} is named "
                                f"as a .{out_kind} console file")
    doc = _regen.regenerate(load_checked(args.scene), args.scene, date.today())
    try:
        atomic_write_bytes(args.regenerate, _regen.dumps(doc).encode("utf-8"))
    except OSError as e:
        raise InvalidInputError(f"--regenerate {args.regenerate}: {e.strerror or e}") from None
    sections = " ".join(f"{k}({v})" for k, v in _preflight.coverage(doc).items())
    print(f"wrote {args.regenerate} from {args.scene}: {sections}")
    return 0
