"""The strip-reorder subcommands: swap-strips, move-strip, reorder-strips. Each writes a new
scene and never overwrites its input."""

from __future__ import annotations

from collections import Counter

from pf_core.exceptions import InvalidInputError

from ._cli_files import file_kind, load_checked, refuse_overwrite
from .model import Scene
from .services import stripmove as _sm
from .tables import line_fields

STRIP_COMMANDS = frozenset({"swap-strips", "move-strip", "reorder-strips"})
NOT_IN_SNIPPET = ("a snippet cannot carry /config/chlink or /config/userctrl, and its channel "
                  "mask would not follow the strips")


def _mapping(args) -> dict[int, int]:
    if args.cmd == "swap-strips":
        return _sm.swap_mapping(args.a, args.b)
    if args.cmd == "move-strip":
        if not (1 <= args.frm <= _sm.CHANNELS and 1 <= args.to <= _sm.CHANNELS):
            raise InvalidInputError(f"move-strip takes channels 1-{_sm.CHANNELS}, got "
                                    f"{args.frm} --to {args.to}")
        return _sm.move_mapping(args.frm, args.to)
    twice = sorted(frm for frm, n in Counter(frm for frm, _ in args.moves).items() if n > 1)
    if twice:
        raise InvalidInputError("each channel moves once: "
                                + ", ".join(f"ch{c:02d} is given twice" for c in twice))
    return dict(args.moves)


def _report(scene: Scene, move: _sm.StripMove, out: str) -> None:
    print(f"moved {len(move.moves)} strip(s):")
    for old, new in move.moves:
        cfg = scene.get(f"/ch/{new:02d}/config")
        name = cfg.args[0] if cfg is not None and cfg.args else '""'
        print(f"  ch{old:02d} {name} -> ch{new:02d}")
    if not move.remapped:
        print("no reference outside the strips names a moved channel")
    else:
        print(f"remapped {len(move.remapped)} reference(s):")
    for r in move.remapped:
        ln = scene.get(r.path)
        names = line_fields(r.path, len(ln.args)) if ln is not None else None
        label = f" ({names[r.field - 1]})" if names and r.field <= len(names) else ""
        print(f"  {r.path} field {r.field}{label}: {r.before} -> {r.after}")
    print(f"wrote {out}")
    print("LOAD-TEST on the console before a gig.")


def run_strips(args) -> int:
    """Run one of STRIP_COMMANDS: exit 0 having written OUT; a refusal raises, nothing written."""
    refuse_overwrite(args.out, args.scene, force=args.force)
    if file_kind(args.scene) != "scn":
        raise InvalidInputError(f"{args.cmd} reads a scene (.scn) only, not {args.scene}: "
                                "snippet and show channel masks are not rewritten")
    mapping = _mapping(args)
    if not _sm.moved_channels(mapping):
        raise InvalidInputError("nothing to move: every named strip is already in place")
    sc = load_checked(args.scene)
    move = _sm.permute_channels(sc, mapping)
    sc.save(args.out)
    _report(sc, move, args.out)
    return 0
