"""argparse construction for the commands that talk to a running desk — presentation."""

from __future__ import annotations

import argparse
import math
import sys

from pf_core.utils.env import resolve_float, resolve_str


def _bounded(v: float, default: float = 0.5) -> float:
    """The same bounds as the flag, for a value that came from the environment: argparse's
    type= validates what is typed, never a default."""
    if math.isfinite(v) and 0 < v <= 3600:
        return v
    print(f"x32scene: warning: X32SCENE_TIMEOUT={v!r} out of range; using {default}",
          file=sys.stderr)
    return default


def _timeout(s: str) -> float:
    """settimeout() raises OverflowError for inf or a huge float — an ArithmeticError the
    CLI boundary does not catch, so the value is bounded here instead."""
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"timeout must be a number, got {s!r}") from None
    if not math.isfinite(v) or not 0 < v <= 3600:
        raise argparse.ArgumentTypeError(f"timeout must be between 0 and 3600 seconds, got {s}")
    return v


def _add_live(sub) -> None:
    # resolved once: both live subparsers share it, and a malformed value warns once
    timeout_default = _bounded(resolve_float(None, "X32SCENE_TIMEOUT", default=0.5))
    timeout_help = "seconds to wait for each path's reply (or set X32SCENE_TIMEOUT)"
    s = sub.add_parser("pull",
                       help="pull the running desk's state via OSC (paths from a reference scene)")
    s.add_argument("reference", help="scene whose paths define what to pull")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--force", action="store_true", help="overwrite OUT if it already exists")
    s.add_argument("--ip", default=resolve_str(None, "X32SCENE_IP", default=None),
                   help="console IP (or set X32SCENE_IP)")
    s.add_argument("--timeout", type=_timeout, default=timeout_default, help=timeout_help)
    s = sub.add_parser("desk", help="read the running desk: identity, state, preferences and "
                                    "what its memory holds (read-only)")
    s.add_argument("--ip", default=resolve_str(None, "X32SCENE_IP", default=None))
    s.add_argument("--timeout", type=_timeout, default=timeout_default, help=timeout_help)
    s.add_argument("--no-library", action="store_true", help="skip the 700 slot queries")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("meters", help="what the desk is hearing: each slot's peak over a "
                                      "short window (read-only)")
    s.add_argument("what", nargs="?", default="inputs",
                   choices=("inputs", "buses", "outputs", "sends", "fx", "monitor", "recorder"))
    s.add_argument("--ip", default=resolve_str(None, "X32SCENE_IP", default=None))
    s.add_argument("--seconds", type=_timeout, default=1.0, help="window to watch (default 1.0)")
    s.add_argument("--scene", help="a scene to name the strips from")
    s.add_argument("--all", action="store_true", help="show silent slots too")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("live-diff",
                       help="diff the running desk against a saved scene (what got twiddled)")
    s.add_argument("scene")
    s.add_argument("--ip", default=resolve_str(None, "X32SCENE_IP", default=None),
                   help="console IP (or set X32SCENE_IP)")
    s.add_argument("--timeout", type=_timeout, default=timeout_default, help=timeout_help)
