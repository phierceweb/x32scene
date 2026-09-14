"""The send-tap subcommand, run on a scene or as a snippet --edit."""

from __future__ import annotations

from ._cli_files import load_checked, refuse_overwrite
from .model import Scene
from .services import iem as _iem

SEND_COMMANDS = frozenset({"set-send-tap"})


def send_tap_edit(sc: Scene, args, linked: bool | None) -> str:
    """Apply set-send-tap to ``sc`` and say which buses it sets and every line it wrote."""
    odd = _iem.tap_bus(args.bus)
    old = {}
    for strip in _iem.send_strip_group(sc, args.strip, linked=linked):
        line = sc.get(f"{strip}/mix/{odd:02d}")
        if line is not None and len(line.args) >= 4:
            old[line.path] = line.args[3]
    written = _iem.set_send_tap(sc, args.strip, args.bus, args.tap, linked=linked)
    head = (f"bus {odd}'s tap sets buses {odd} and {odd + 1}" if args.bus == odd else
            f"bus {args.bus}'s tap lives on bus {odd}'s line: sets buses {odd} and {odd + 1}")
    rows = [f"  {path} tap {old[path]} -> {args.tap}" + (" (stereo-linked partner)" if i else "")
            for i, path in enumerate(written)]
    return "\n".join([head, *rows])


def run_send_tap(args) -> int:
    """Run set-send-tap: exit 0 having written OUT; a refusal raises, nothing written."""
    refuse_overwrite(args.out, args.scene, force=args.force)
    sc = load_checked(args.scene)
    msg = send_tap_edit(sc, args, False if args.no_link else None)
    sc.save(args.out)
    print(f"{msg}\nwrote {args.out}\nLOAD-TEST on the console before a gig.")
    return 0
