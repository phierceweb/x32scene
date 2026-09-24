"""argparse construction for the FX and routing commands — presentation. One file per
command family, as _parsers_live.py is for the live desk."""

from __future__ import annotations

from ._parsers_edit import _choice
from .tables import OUTPUT_BANKS


def _add_fx_routing(sub, _out) -> None:
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
    s.add_argument("what", **_choice("routing", "taps", "sources"))
    s.add_argument("key", nargs="?", help="routing: IN, AES50A, AES50B, CARD, OUT or PLAY")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("set-routing", help="set routing bank blocks: KEY BLOCK=TOKEN …")
    s.add_argument("scene")
    s.add_argument("key", **_choice("IN", "AES50A", "AES50B", "CARD", "OUT", "PLAY", "switch"),
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
    s.add_argument("bank", **_choice(*OUTPUT_BANKS))
    s.add_argument("n", type=int, metavar="N")
    _out(s)
    s.add_argument("--src", help='"bus 9", "main l", "matrix 2", "direct out ch 5", off, 0-76')
    s.add_argument("--pos", help="tap point: IN/LC, <-EQ, EQ->, PRE, POST; the first four "
                                 "also as +M")
    s.add_argument("--invert", **_choice("on", "off"))
    s.set_defaults(knobs={"--src": "src", "--pos": "pos", "--invert": "invert"})
    s = sub.add_parser("set-record", help="point a USB card record track at a source, "
                                          "through the user-out slot its CARD block reads")
    s.add_argument("scene")
    s.add_argument("track", type=int, metavar="TRACK", help="card record track 1-32")
    s.add_argument("source", metavar="SRC", help='the words record-map prints ("Output 9", '
                   '"P16 5", "Aux Out 2", "Monitor L"), "local 5", "card 7", off, or 0-208')
    _out(s)
    s = sub.add_parser("extract-routing", help="the input routing banks as a routing preset (.rou)")
    s.add_argument("scene")
    _out(s, metavar="OUT.rou")
    s.add_argument("--name", help="preset name (default: the output file's stem)")
    s = sub.add_parser("apply-routing", help="load a routing preset (.rou) into a scene")
    s.add_argument("scene")
    s.add_argument("preset")
    _out(s)
    s.add_argument("--bank", action="append", **_choice("IN", "AES50A", "AES50B", "CARD"),
                   help="only these banks (repeatable); default: all the preset carries")
