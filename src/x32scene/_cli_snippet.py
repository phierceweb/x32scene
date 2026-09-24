"""The snippet subcommand: a delta between two scenes, edits applied to one, or one mix as
it is."""

from __future__ import annotations

import contextlib
import io
import os
import shlex

from pf_core.exceptions import InvalidInputError

from . import _views
from ._cli_files import load_checked, refuse_overwrite
from ._cli_inplace import IN_PLACE, apply_edit
from ._cli_strips import NOT_IN_SNIPPET, STRIP_COMMANDS
from .model import Scene
from .services import buslink as _buslink
from .services import snippets as _snippets
from .services import transplant as _transplant


def parse_edit(text: str, scene: str):
    """Parse one ``--edit`` string ("set-eq 5 2 --gain 3") as the matching edit command,
    with the scene and a placeholder output supplied here rather than by the user."""
    from ._parsers import _build_parser   # local: _parsers imports nothing from here
    words = shlex.split(text)
    if words[:1] == ["set-bus-link"]:
        raise InvalidInputError(
            "--edit cannot run set-bus-link: a snippet cannot carry /config/buslink, so it "
            "would load the reshaped sends and pans onto a pair whose link state has not "
            f"changed; run set-bus-link SCENE BUS on|off -o OUT.scn and load that scene: {text!r}")
    if words[:1] and words[0] in STRIP_COMMANDS:
        raise InvalidInputError(f"--edit cannot run {words[0]}: {NOT_IN_SNIPPET}; run it on "
                                f"the scene with -o OUT.scn and load that scene: {text!r}")
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


def _carried_edit(sc: Scene, text: str, parsed) -> str:
    """apply_edit, refused when it changes a line a snippet cannot carry: the snippet would
    load the edit's other lines without it."""
    before = Scene.parse(sc.dump())
    row = apply_edit(sc, parsed)
    lost = _snippets.make_snippet(before, sc, "").skipped
    if lost:
        scope = ", or leave that scope out with --scope" if parsed.cmd == "apply-preset" else ""
        raise InvalidInputError(
            f"--edit {text!r} writes {', '.join(lost)}, which a snippet cannot carry; run "
            f"{parsed.cmd} on the scene with -o OUT.scn and load that scene{scope}")
    return row


def run_snippet(args) -> int:
    """Write the snippet; a refusal raises, nothing written."""
    absolute = len(args.scenes) == 1 and not args.edit and (args.bus or args.only)
    if len(args.scenes) != (1 if args.edit or absolute else 2):
        raise InvalidInputError("snippet takes two scenes (a delta), one scene with --edit, "
                                "or one scene with --bus/--only (those lines as they are)")
    # an --edit can name a preset to load: an input the arguments do not reveal, so
    # every edit is parsed before the guard runs
    edits = [parse_edit(text, args.scenes[0]) for text in args.edit]
    presets = [e.preset for e in edits if getattr(e, "preset", None)]
    refuse_overwrite(args.out, *args.scenes, *presets, force=args.force)
    name = args.name or os.path.splitext(os.path.basename(args.out))[0]
    base = load_checked(args.scenes[0])
    if absolute:
        base = Scene([base.lines[0]], True)   # every selected line, not just what moved
    rows = []
    if args.edit:
        edited = Scene.load(args.scenes[0])   # same file as base, already checked
        rows = [_carried_edit(edited, text, parsed)
                for text, parsed in zip(args.edit, edits, strict=True)]
    else:
        edited = load_checked(args.scenes[-1])
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
    for row in rows:
        print(row)
    _views.cmd_snippet(snip, args.out)
    _views.warn_relinked(
        _buslink.relinked_pairs(base, edited, [ln.path for ln in snip.scene.lines]))
    return 0
