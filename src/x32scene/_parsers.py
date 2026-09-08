"""argparse construction for the CLI — presentation layer."""

from __future__ import annotations

import argparse

from pf_core.utils.env import resolve_str

from . import __version__
from .services.scopes import SCOPES
from ._parsers_edit import _add_edits
from ._parsers_live import _add_live
from .tables import OUTPUT_BANKS


def _strip_arg(s: str):
    """A strip target on the CLI: a bare number (channel) or a path like /bus/01, /main/st."""
    return int(s) if s.isdigit() else s


# the views registered in a loop; every other command carries help= at its add_parser
_VIEW_HELP = {
    "info": "the scene at a glance: title, line count, channel and bus names",
    "buses": "the 16 mix buses: stereo pairs, names, FX assignment, send tap",
    "explain": "a whole scene read out in words, for troubleshooting",
    "inputs": "each channel resolved to the physical jack feeding it",
    "record-map": "the USB card tracks a DAW receives, and the channels fed back from it",
    "fx": "the eight FX slots: type, source and parameters",
    "dca": "DCA and mute-group membership",
}


def _out(s, **kw) -> None:
    """The output path an edit command writes, and the flag that lets it land on a file
    that is already there. Every writer takes both, so the guard is impossible to omit."""
    s.add_argument("-o", "--out", required=True, **kw)
    s.add_argument("--force", action="store_true", help="overwrite OUT if it already exists")


def _bus_list(s: str) -> list[int]:
    """A comma-separated bus list on the CLI: ``1,3,9``."""
    try:
        return [int(x) for x in s.split(",") if x.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(f"buses must be numbers like 1,3,9 — got {s!r}") from None


def _build_parser(description: str | None) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="x32scene", description=description)
    p.add_argument("--version", action="version", version=f"x32scene {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # resolved once: every subparser reading them shares it, and a malformed value warns once
    config_default = resolve_str(None, "X32SCENE_CONFIG", default=None)
    stage_default = resolve_str(None, "X32SCENE_STAGE", default=None)
    stage_help = "stage sidecar JSON, or set X32SCENE_STAGE (start from config/example-stage.json)"
    for name in ("info", "buses", "explain"):
        sub.add_parser(name, help=_VIEW_HELP[name]).add_argument("scene")
    s = sub.add_parser("ports", help="outputs -> source per bank; a sidecar adds jack/wearer")
    s.add_argument("scene")
    s.add_argument("--bank", choices=(*OUTPUT_BANKS, "all"), default="main")
    s.add_argument("--config", default=config_default,
                   help="preflight config, read for monitor.physical_outputs "
                        "(or set X32SCENE_CONFIG)")
    s.add_argument("--stage", default=stage_default, help=stage_help)
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("console", help="the console-wide settings in words: monitor, talkback, "
                                       "oscillator, recorder, DP48, delays, iQ, user assign")
    s.add_argument("scene")
    s.add_argument("--json", action="store_true")
    for name in ("inputs", "record-map", "fx", "dca"):
        s = sub.add_parser(name, help=_VIEW_HELP[name])
        s.add_argument("scene")
        s.add_argument("--json", action="store_true")
    s = sub.add_parser("iem", help="one monitor bus: the sends feeding it, loud to quiet")
    s.add_argument("scene")
    s.add_argument("bus", type=int, choices=range(1, 17), metavar="BUS",
                   help="mix bus 1-16")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("report", help="the scene as a markdown snapshot")
    s.add_argument("scene")
    s.add_argument("--config", default=config_default,
                   help="preflight config, read for monitor.physical_outputs "
                        "(or set X32SCENE_CONFIG)")
    s.add_argument("--stage", default=stage_default, help=stage_help)
    s = sub.add_parser("iem-matrix", help="every monitor mix at once: senders x buses")
    s.add_argument("scene")
    s.add_argument("--buses", type=_bus_list, default=None, metavar="1,3,9",
                   help="columns (default: every bus that is not an FX send)")
    s.add_argument("--all", action="store_true", help="every send strip, silent ones too")
    s.add_argument("--compare", metavar="OTHER", help="show before>after against another scene")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("diff", help="what changed between two files, path by path")
    s.add_argument("a")
    s.add_argument("b")
    s.add_argument("--by-strip", action="store_true",
                   help="group changes by strip and name the fields that moved")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("history", help="one path's timeline across a scene library")
    s.add_argument("paths", nargs="+", metavar="PATH")
    s.add_argument("--dir", default=resolve_str(None, "X32SCENE_CORPUS", default=None),
                   help="directory of .scn files (or set X32SCENE_CORPUS)")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("snippet", help="a .snp the console recalls in place: the delta "
                                       "between two scenes, or edits applied to one")
    s.add_argument("scenes", nargs="+", metavar="SCENE",
                   help="A B for a delta; one scene with --edit, or with --bus/--only to take "
                        "those lines as they are")
    _out(s, metavar="OUT.snp")
    s.add_argument("--edit", action="append", default=[], metavar='"set-eq 5 2 --gain 3"',
                   help="an edit command without its scene and -o, applied in memory "
                        "(repeatable; set-*, rename, apply-preset)")
    s.add_argument("--name", help="snippet name (default: the output file's stem)")
    s.add_argument("--bus", type=int, action="append", default=[], metavar="N",
                   help="keep only bus N's monitor mix: its strip and every send to it, "
                        "both sides of a pair (repeatable)")
    s.add_argument("--only", action="append", default=[], metavar="GLOB",
                   help="keep only paths matching, e.g. '/ch/01/*' (repeatable)")
    s = sub.add_parser("fx-types", help="every effect type, or one type's parameters and "
                                        "their default tokens")
    s.add_argument("code", nargs="?", metavar="CODE")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("set-fx", help="change an FX slot: type (params reset to the desk's "
                                      "defaults), source, parameters by name")
    s.add_argument("scene")
    s.add_argument("slot", type=int, choices=range(1, 9), metavar="SLOT")
    _out(s)
    s.add_argument("--type", metavar="CODE")
    s.add_argument("--source", metavar="L[,R]", help="INS, MIX1..MIX16 or M/C (slots 1-4)")
    s.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                   help='a parameter by name, e.g. --set Decay=2.1 --set "Hi Cut=8000"')
    s.set_defaults(knobs={"--type": "type", "--source": "source", "--set": "set"})
    s = sub.add_parser("extract-fx", help="one FX slot as an effect preset (.efx)")
    s.add_argument("scene")
    s.add_argument("slot", type=int, choices=range(1, 9), metavar="SLOT")
    _out(s, metavar="OUT.efx")
    s.add_argument("--name", help="preset name (default: the output file's stem)")
    s = sub.add_parser("apply-fx", help="load an effect preset (.efx) into an FX slot")
    s.add_argument("scene")
    s.add_argument("slot", type=int, choices=range(1, 9), metavar="SLOT")
    s.add_argument("preset")
    _out(s)
    s.add_argument("--source", action="store_true", help="also take the preset's source")
    s = sub.add_parser("vocab", help="the words the console accepts: routing bank tokens, "
                                     "output sources (taps), input sources")
    s.add_argument("what", choices=("routing", "taps", "sources"))
    s.add_argument("key", nargs="?", help="routing: IN, AES50A, AES50B, CARD, OUT or PLAY")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("set-routing", help="set routing bank blocks: KEY BLOCK=TOKEN …")
    s.add_argument("scene")
    s.add_argument("key", choices=("IN", "AES50A", "AES50B", "CARD", "OUT", "PLAY", "switch"),
                   help="a bank, or `switch` with REC|PLAY")
    s.add_argument("blocks", nargs="+", metavar="BLOCK=TOKEN",
                   help="e.g. 1-8=A1-8 AUX=AUX1-4 (for switch: REC or PLAY)")
    _out(s)
    s = sub.add_parser("set-input", help="point a channel at an input source")
    s.add_argument("scene")
    s.add_argument("ch", type=int)
    s.add_argument("source", help='"local 5", "aes50-a 3", "card 7", "aux 2", off, or 0-168')
    _out(s)
    s = sub.add_parser("set-output", help="an output's source, tap point and polarity")
    s.add_argument("scene")
    s.add_argument("bank", choices=tuple(OUTPUT_BANKS))
    s.add_argument("n", type=int, metavar="N")
    _out(s)
    s.add_argument("--src", help='"bus 9", "main l", "matrix 2", "direct out ch 5", off, 0-76')
    s.add_argument("--pos", help="tap point: IN/LC, <-EQ, EQ->, PRE, POST, each also with +M")
    s.add_argument("--invert", choices=("on", "off"))
    s.set_defaults(knobs={"--src": "src", "--pos": "pos", "--invert": "invert"})
    s = sub.add_parser("extract-routing", help="the input routing banks as a routing preset (.rou)")
    s.add_argument("scene")
    _out(s, metavar="OUT.rou")
    s.add_argument("--name", help="preset name (default: the output file's stem)")
    s = sub.add_parser("apply-routing", help="load a routing preset (.rou) into a scene")
    s.add_argument("scene")
    s.add_argument("preset")
    _out(s)
    s.add_argument("--bank", action="append", choices=("IN", "AES50A", "AES50B", "CARD"),
                   help="only these banks (repeatable); default: all the preset carries")
    s = sub.add_parser("transplant", help="carry lines from SRC into DST and touch nothing "
                                          "else: a monitor bus, path patterns, channel sections")
    s.add_argument("src")
    s.add_argument("dst")
    _out(s)
    s.add_argument("--bus", type=int, action="append", default=[], metavar="N",
                   help="bus N's whole monitor mix (strip + every send), pair-aware (repeatable)")
    s.add_argument("--path", action="append", default=[], metavar="GLOB",
                   help="paths matching a pattern, e.g. /headamp/000 or '/ch/03/eq/*' (repeatable)")
    s.add_argument("--ch", type=int, action="append", default=[], metavar="N",
                   help="a channel's sections as a preset load would (repeatable)")
    s.add_argument("--scope", action="append", choices=SCOPES,
                   help="with --ch: limit to these sections (default: all)")
    s = sub.add_parser("header", help="decode a file's header: scene safes, snippet filters, "
                                      "preset flags")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("show", help="list a .shw index: scenes, snippets, cues")
    s.add_argument("file")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("show-build", help="write a show (.shw plus companions) from scenes, "
                                          "snippets and cues, the way X32-Edit imports one")
    s.add_argument("-o", "--dir", required=True, metavar="DIR", help="directory to write into")
    s.add_argument("--force", action="store_true",
                   help="overwrite show files that already exist in DIR")
    s.add_argument("--name", required=True, help="show name; files are NAME.shw, NAME.NNN.scn …")
    s.add_argument("--scene", action="append", default=[], metavar="FILE.scn",
                   help="scene slot in order given (repeatable)")
    s.add_argument("--snippet", action="append", default=[], metavar="FILE.snp",
                   help="snippet slot in order given (repeatable)")
    s.add_argument("--cue", action="append", default=[], metavar='"1 Opener scene=0 snippet=1"',
                   help="a cue: number, name words, scene=N, snippet=N, skip (repeatable)")
    s = sub.add_parser("port-iem",
                       help="copy SRC's main and aux output patch onto DST")
    s.add_argument("src")
    s.add_argument("dst")
    _out(s)
    s = sub.add_parser("audit", help="check a scene library's invariants and surface rig drift over time")
    s.add_argument("dir", nargs="?", default=resolve_str(None, "X32SCENE_CORPUS", default=None),
                   help="directory of .scn files (or set X32SCENE_CORPUS)")
    s = sub.add_parser("preflight",
                       help="check a scene against the documented rig (FAIL/WARN report)")
    s.add_argument("scene")
    s.add_argument("--config", default=config_default,
                   help="expected-config JSON, or set X32SCENE_CONFIG "
                        "(start from config/example-preflight.json)")
    s.add_argument("--stage", default=stage_default, help=stage_help)
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("band-setup",
                       help="re-skin a template scene for another band from a JSON plan")
    s.add_argument("template")
    s.add_argument("plan")
    _out(s)
    s.add_argument("--snippet", metavar="OUT.snp",
                   help="also write the plan's delta against the template as a snippet")
    _add_edits(sub, _out, _strip_arg)
    _add_live(sub)
    return p
