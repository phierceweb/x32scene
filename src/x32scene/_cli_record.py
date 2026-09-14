"""The set-record subcommand, run on a scene or as a snippet --edit."""

from __future__ import annotations

from ._cli_files import load_checked, refuse_overwrite
from .model import Scene
from .services import routing as _routing
from .services import routing_edit as _rt

RECORD_COMMANDS = frozenset({"set-record"})


def record_lines(row: dict) -> list[str]:
    """A ``routing_edit.record_row`` in words: the track's old and new source and slot, then
    every other destination that slot feeds."""
    lines = [f"track {row['track']}: {row['before']} -> {row['after']} "
             f"(user-out slot {row['slot']})"]
    if row["also_feeds"]:
        lines.append(f"  user-out slot {row['slot']} also feeds {', '.join(row['also_feeds'])}")
    return lines


def record_edit(sc: Scene, args) -> str:
    """Apply set-record to ``sc`` and say what it changed."""
    _rt.record_slot(sc, args.track)
    before = dict(_routing.record_map(sc))[args.track]
    _rt.set_record(sc, args.track, args.source)
    return "\n".join(record_lines(_rt.record_row(sc, args.track, before)))


def run_record(args) -> int:
    """Run set-record: exit 0 having written OUT; a refusal raises, nothing written."""
    refuse_overwrite(args.out, args.scene, force=args.force)
    sc = load_checked(args.scene)
    msg = record_edit(sc, args)
    sc.save(args.out)
    print(f"{msg}\nwrote {args.out}\nLOAD-TEST on the console before a gig.")
    return 0
