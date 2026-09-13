"""argparse construction for the commands that edit a strip, move a preset around or move
inputs to a stage box — presentation. One file per command family, as _parsers_live.py is
for the live desk."""

from __future__ import annotations

import argparse

from .services.scopes import SCOPES


def _move_arg(s: str) -> tuple[int, int]:
    """One stage-box move on the CLI: ``CH:IN``."""
    ch, sep, aes = s.partition(":")
    if not (sep and ch.isdigit() and aes.isdigit()):
        raise argparse.ArgumentTypeError(f"a move is CH:IN, like 1:13 — got {s!r}")
    return int(ch), int(aes)


def _folded(fold, *choices: str):
    """A choice typed in any case, refused quoting what was typed rather than its fold."""
    def parse(s: str) -> str:
        if fold(s) not in choices:
            raise argparse.ArgumentTypeError(
                f"invalid choice: {s!r} (choose from {', '.join(choices)})")
        return fold(s)
    return parse


def _add_edits(sub, _out, _strip_arg) -> None:
    s = sub.add_parser("move-inputs", help="re-source channels from AES50 stage-box inputs, "
                                           "head-amp gain and phantom travelling with them")
    s.add_argument("scene")
    s.add_argument("moves", nargs="+", type=_move_arg, metavar="CH:IN",
                   help="channel 1-32 : stage-box input 1-48 on the --to port")
    s.add_argument("--to", required=True, type=_folded(str.upper, "A", "B"), choices=("A", "B"),
                   help="the AES50 port the stage box is on; no default")
    _out(s)
    s.add_argument("--no-gain", action="store_true",
                   help="leave the new inputs' head-amp gain and phantom as they are")
    s = sub.add_parser("extract-preset", help="one channel as a channel preset (.chn), or "
                                              "every named channel into a folder with --all")
    s.add_argument("scene")
    s.add_argument("ch", type=int, nargs="?", help="channel 1-32; omit with --all")
    _out(s, help="OUT.chn, or with --all a directory (created if missing)")
    s.add_argument("--all", action="store_true",
                   help="one <scribble name>.chn per named channel; channels sharing "
                        "a file name are skipped")
    s.add_argument("--scope", action="append", choices=SCOPES,
                   help="limit to these scopes (repeatable); default = all")
    s.add_argument("--header", action="store_true",
                   help="write a #4.0# header naming the preset after the channel "
                        "(opt-in: the flag bit order is inferred, LOAD-TEST it)")
    s = sub.add_parser("apply-preset", help="load a channel preset (.chn) onto a channel")
    s.add_argument("scene")
    s.add_argument("ch", type=int)
    s.add_argument("preset")
    _out(s)
    s.add_argument("--scope", action="append", choices=SCOPES)
    s = sub.add_parser("presets-diff", help="which channel presets in a folder no longer "
                                            "match the channel they are named for")
    s.add_argument("dir", metavar="DIR", help="folder of .chn files (not recursive)")
    s.add_argument("scene")
    s.add_argument("--scope", action="append", choices=SCOPES,
                   help="compare only these scopes (repeatable); default = all")
    s.add_argument("--json", action="store_true")
    nolink_help = "edit only this strip, even on a stereo-linked pair"
    s = sub.add_parser("set-eq", help="set an EQ band: type, frequency, gain, Q")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    s.add_argument("band", type=int)
    _out(s)
    s.add_argument("--type")
    s.add_argument("--freq", type=float)
    s.add_argument("--gain", type=float)
    s.add_argument("--q", type=float)
    s.add_argument("--no-link", action="store_true", help=nolink_help)
    # knobs: the flags _require_a_knob demands at least one of (flag -> args dest)
    s.set_defaults(knobs={"--type": "type", "--freq": "freq", "--gain": "gain", "--q": "q"})
    s = sub.add_parser("set-comp", help="set the compressor: threshold, ratio, makeup, attack, release")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    _out(s)
    s.add_argument("--thr", type=float)
    s.add_argument("--ratio")
    s.add_argument("--makeup", type=float)
    s.add_argument("--attack", type=float)
    s.add_argument("--release", type=float)
    s.add_argument("--no-link", action="store_true", help=nolink_help)
    s.set_defaults(knobs={"--thr": "thr", "--ratio": "ratio", "--makeup": "makeup",
                          "--attack": "attack", "--release": "release"})
    s = sub.add_parser("set-gate", help="set the gate: threshold, range, attack, release")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    _out(s)
    s.add_argument("--thr", type=float)
    s.add_argument("--range", type=float, dest="rng")
    s.add_argument("--attack", type=float)
    s.add_argument("--release", type=float)
    s.add_argument("--no-link", action="store_true", help=nolink_help)
    s.set_defaults(knobs={"--thr": "thr", "--range": "rng", "--attack": "attack",
                          "--release": "release"})
    s = sub.add_parser("set-lowcut", help="switch a strip's low cut on/off and set its frequency")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    _out(s)
    onoff = s.add_mutually_exclusive_group()
    onoff.add_argument("--on", action="store_true")
    onoff.add_argument("--off", action="store_true")
    s.add_argument("--freq", type=float)
    s.add_argument("--no-link", action="store_true", help=nolink_help)
    s.set_defaults(knobs={"--on": "on", "--off": "off", "--freq": "freq"})
    s = sub.add_parser("set-fader",
                       help="set a strip's fader level (dB, or oo for -infinity)")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    s.add_argument("level", help="dB, or oo (also -oo) for -infinity")
    _out(s)
    s.add_argument("--no-link", action="store_true", help=nolink_help)
    s = sub.add_parser("set-mute", help="mute/unmute a strip")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    s.add_argument("state", choices=["on", "off"], help="on = muted")
    _out(s)
    s.add_argument("--no-link", action="store_true", help=nolink_help)
    s = sub.add_parser("set-pan", help="set a strip's pan/balance (-100..+100)")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    s.add_argument("pan", type=int, help="-100 (L) .. +100 (R)")
    _out(s)
    s = sub.add_parser("set-bus-link", help="link or unlink a stereo mix-bus pair as the desk "
                                            "does: linking copies the odd bus onto the even")
    s.add_argument("scene")
    s.add_argument("bus", type=int, metavar="BUS", help="either bus of the pair, 1-16")
    s.add_argument("state", type=_folded(str.lower, "on", "off"), choices=("on", "off"),
                   help="on = linked")
    _out(s)
    s = sub.add_parser("rename", help="rename a strip (channel, bus, DCA, etc.)")
    s.add_argument("scene")
    s.add_argument("strip", type=_strip_arg)
    s.add_argument("name")
    _out(s)
