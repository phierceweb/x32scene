"""Decoding tables for X32 scene values."""

from __future__ import annotations

import re

# Strips that can send to a mix bus, in console order — a monitor mix is not only channels.
SEND_STRIPS = (
    [f"/ch/{n:02d}" for n in range(1, 33)]
    + [f"/auxin/{n:02d}" for n in range(1, 9)]
    + [f"/fxrtn/{n:02d}" for n in range(1, 9)]
)


def send_line_fields(bus: int) -> int:
    """Tokens a ``<strip>/mix/<bus>`` line carries. Parity decides it, not link state: the
    odd bus of each pair holds pan and tap point, the even bus holds on/level alone and
    inherits the rest from its partner — true of the unlinked FX buses 13-16 as well."""
    return 5 if bus % 2 else 2


# the file's number width per family: two digits everywhere except /dca/N
_STRIP_WIDTH = {"/ch": 2, "/bus": 2, "/auxin": 2, "/fxrtn": 2, "/mtx": 2, "/dca": 1}


def strip_path(strip: int | str) -> str:
    """A strip target: an int channel (-> /ch/NN) or a path ('/bus/01', '/main/st').
    Number width is canonicalized per family ('/bus/1' -> '/bus/01', '/dca/03' -> '/dca/3')."""
    if isinstance(strip, int):
        return f"/ch/{strip:02d}"
    path = strip.rstrip("/")
    fam, _, num = path.rpartition("/")
    width = _STRIP_WIDTH.get(fam)
    if width and num.isdigit():
        return f"{fam}/{int(num):0{width}d}"
    return path


# /headamp/NNN is indexed by physical input, NOT channel number:
#   000-031 Local 1-32, 032-079 AES50-A 1-48, 080-127 AES50-B 1-48.
def headamp_index(kind: str, n: int) -> int:
    """kind in {'local','aesa','aesb'}, n is 1-based physical input number."""
    base, hi = {"local": (0, 32), "aesa": (32, 48), "aesb": (80, 48)}[kind]
    if not 1 <= n <= hi:
        raise ValueError(f"{kind} input must be 1-{hi}, got {n}")
    return base + (n - 1)


SOURCE_DOMAINS = [
    (0, 0, "OFF"),
    (1, 32, "Local input"),
    (33, 80, "AES50-A input"),
    (81, 128, "AES50-B input"),
    (129, 160, "USB Card (DAW)"),
    (161, 166, "Aux In"),
]

_TALKBACK = {167: "Talkback Int", 168: "Talkback Ext"}

# The aux bank's last two channel-source slots are the console's USB player. They are not
# routed inputs, so no number in the input enumeration names them.
AUX_BANK_USB = {39: "USB player L", 40: "USB player R"}


def decode_source(num: int) -> str:
    """Decode an INPUT source number (0-168). /out values use decode_out_source instead."""
    for lo, hi, label in SOURCE_DOMAINS:
        if lo <= num <= hi:
            if label == "OFF":
                return "OFF"
            return f"{label} {num - lo + 1}"
    return _TALKBACK.get(num, f"?{num}")


# /config/userrout/out extends the input enumeration with the console's own outputs. A
# value in 169-184 names an OUTPUT SLOT: what a DAW track then carries is whatever
# /outputs/main/NN assigns to that output.
_OUT_DOMAINS = [(169, 184, "Output"), (185, 200, "P16"), (201, 206, "Aux Out")]
_OUT_SINGLE = {207: "Monitor L", 208: "Monitor R"}


def decode_out_source(num: int) -> str:
    """Decode a /config/userrout/out value (0-208)."""
    if num == 0:
        return "OFF"
    if 129 <= num <= 160:
        return f"Card {num - 128}"
    if 1 <= num <= 168:
        return decode_source(num)
    for lo, hi, label in _OUT_DOMAINS:
        if lo <= num <= hi:
            return f"{label} {num - lo + 1}"
    return _OUT_SINGLE.get(num, f"out-src {num}")


def tap_to_bus(tap: int) -> int | None:
    """Return 1-based mix-bus number for an output tap, or None if not a bus tap."""
    if 4 <= tap <= 19:
        return tap - 3
    return None


def bus_to_tap(bus: int) -> int:
    """Output-tap value that routes a physical output from mix bus ``bus`` (1-16)."""
    if not 1 <= bus <= 16:
        raise ValueError(f"bus must be 1-16, got {bus}")
    return bus + 3


# the published /outputs source enumeration, 0-76, one list for all five banks
_TAP_SINGLE = {0: "OFF", 1: "Main L", 2: "Main R", 3: "Main M/C",
               74: "Monitor L", 75: "Monitor R", 76: "Talkback"}
_TAP_DOMAINS = [(4, 19, "Bus"), (20, 25, "Matrix"), (26, 57, "Direct Out Ch"),
                (58, 65, "Direct Out Aux")]
_TAP_FX = {66 + i: f"Direct Out FX {1 + i // 2}{'LR'[i % 2]}" for i in range(8)}


def decode_tap(tap: int) -> str:
    """Name an output source; a value past the enumeration renders as the raw tap."""
    if tap in _TAP_SINGLE:
        return _TAP_SINGLE[tap]
    for lo, hi, label in _TAP_DOMAINS:
        if lo <= tap <= hi:
            return f"{label} {tap - lo + 1}"
    return _TAP_FX.get(tap, f"tap {tap}")


# the <pos> token of an output line and the tap token of an odd bus send, in the console's
# enumeration order (index 9 of the output enum reads back as POST)
OUTPUT_POS = ("IN/LC", "IN/LC+M", "<-EQ", "<-EQ+M", "EQ->", "EQ->+M", "PRE", "PRE+M", "POST")
SEND_TAPS = ("IN/LC", "<-EQ", "EQ->", "PRE", "POST", "GRP")

# /outputs banks: (size, fields per line). A rec line carries <src> <pos> only — no invert.
OUTPUT_BANKS = {"main": (16, 3), "aux": (6, 3), "p16": (16, 3), "aes": (2, 3), "rec": (2, 2)}

# /config/routing/<KEY> block counts. OUT's four blocks are 4 wide with their own
# vocabulary; the rest are 8 wide, and IN/PLAY end with an AUX-bank block.
ROUTING_BLOCKS = {"IN": 5, "PLAY": 5, "AES50A": 6, "AES50B": 6, "CARD": 4, "OUT": 4}
USERROUT_SLOTS = {"in": 32, "out": 48}


def userrout_out_to_output(num: int) -> int | None:
    """The output slot 1-16 a /config/userrout/out value names, else None."""
    return num - 168 if 169 <= num <= 184 else None


def send_is_live(args: list[str]) -> bool:
    """A send line is audible: ON and above -oo."""
    return len(args) >= 2 and args[0] == "ON" and args[1] != "-oo"


# one ON/OFF token per odd/even strip pair, per family that the console pairs
LINK_LINES = {"/ch": "/config/chlink", "/bus": "/config/buslink", "/auxin": "/config/auxlink",
              "/fxrtn": "/config/fxlink", "/mtx": "/config/mtxlink"}
LINK_WIDTHS = {"/config/chlink": 16, "/config/buslink": 8, "/config/auxlink": 4,
               "/config/fxlink": 4, "/config/mtxlink": 3, "/config/linkcfg": 4}
# /config/linkcfg token order: what a stereo link mirrors (head amp + delay, eq, dynamics,
# fader + mute)
LINKCFG = {"hadly": 0, "eq": 1, "dyn": 2, "fdrmute": 3}
# /config/mute: one positional ON/OFF per mute group, left to right — the opposite
# convention from a strip's /grp masks
MUTE_GROUPS = 6


# ---- field names per line, the console's own order (docs/format.md) --------------------
_STRIP_LINE = re.compile(r"^(/(?:ch|auxin|fxrtn|bus|mtx)/\d+|/main/(?:st|m)|/dca/\d)(/.*)?$")
_DYN = ["on", "mode", "det", "env", "thr", "ratio", "knee", "makeup", "attack", "hold",
        "release", "pos", "keysrc", "mix", "auto"]
_STRIP_FIELDS = {
    "/mix/NN": ["on", "level", "pan", "tap", "pan follow"],
    "/preamp": ["trim", "polarity", "lowcut", "slope", "lowcut freq"],
    "/gate": ["on", "mode", "thr", "range", "attack", "hold", "release", "keysrc"],
    "/gate/filter": ["on", "type", "freq"], "/dyn/filter": ["on", "type", "freq"],
    "/eq": ["on"], "/eq/N": ["type", "freq", "gain", "q"],
    "/delay": ["on", "time"], "/insert": ["on", "pos", "sel"],
    "/automix": ["group", "weight"], "/grp": ["dca", "mute"],
}
_SOLO = ["level", "source", "source trim", "ch mode", "bus mode", "dca mode", "exclusive",
         "follow select", "follow solo", "dim att", "dim", "mono", "delay", "delay time",
         "master ctrl", "mute", "dim pfl"]
_CONSOLE_FIELDS = {
    "/config/routing": ["mode"], "/config/linkcfg": list(LINKCFG),
    "/config/mono": ["mode", "link"], "/config/solo": _SOLO,
    "/config/talk": ["enable", "source"], "/config/talk/A": ["level", "dim", "latch", "dest"],
    "/config/talk/B": ["level", "dim", "latch", "dest"],
    "/config/osc": ["level", "f1", "f2", "f sel", "type", "dest"],
    "/config/tape": ["gain L", "gain R", "autoplay"], "/config/amixenable": ["X", "Y"],
    "/config/dp48": ["scope", "broadcast", "aes port"],
    "/config/userctrl/A": ["colour"], "/config/userctrl/B": ["colour"],
    "/config/userctrl/C": ["colour"],
    "/headamp": ["gain", "phantom"], "/fx/source": ["left", "right"], "/fx": ["type"],
    "/outputs/delay": ["on", "time"], "/outputs/iQ": ["group", "speaker", "eq", "model"],
}
_NUMBERED = {   # one field per numbered thing: (label, first number)
    "/config/dp48/assign": ("ch", 1), "/config/dp48/link": ("pair", 1),
    "/config/dp48/grpname": ("group", 1), "/config/userctrl/A/enc": ("enc", 1),
    "/config/userctrl/B/enc": ("enc", 1), "/config/userctrl/C/enc": ("enc", 1),
    "/config/userctrl/A/btn": ("btn", 5), "/config/userctrl/B/btn": ("btn", 5),
    "/config/userctrl/C/btn": ("btn", 5),
}


def line_fields(path: str, nargs: int) -> list[str] | None:
    """Field names for a scene line, or None when x32scene knows no layout for it
    (``/fx/N/par`` names depend on the effect type — see ``services.fx``)."""
    m = _STRIP_LINE.match(path)
    if m:
        strip, bare = m.group(1), m.group(2) or ""
        fam = strip.split("/")[1]
        if bare == "":
            return ["on", "fader"]   # /dca/N
        if bare == "/config":
            return ["name", "icon", "colour"] + (["source"] if fam in ("ch", "auxin") else [])
        if bare == "/mix":
            return {6: ["on", "fader", "lr", "pan", "mono", "mono level"],
                    3: ["on", "fader", "balance"]}.get(nargs, ["on", "fader"])
        if bare == "/dyn":
            return _DYN if nargs == 15 else [f for f in _DYN if f != "keysrc"]
        key = re.sub(r"/mix/\d\d$", "/mix/NN", re.sub(r"/eq/\d$", "/eq/N", bare))
        names = _STRIP_FIELDS.get(key)
        return names[:nargs] if names else None
    if path.startswith("/config/routing/"):
        return [f"block {i + 1}" for i in range(nargs)]
    if path.startswith("/config/userrout/"):
        return [f"slot {i + 1}" for i in range(nargs)]
    if path in LINK_WIDTHS and path != "/config/linkcfg":
        return [f"pair {2 * i + 1}/{2 * i + 2}" for i in range(nargs)]
    if path == "/config/mute":
        return [f"group {i + 1}" for i in range(nargs)]
    if re.match(r"^/outputs/[a-z0-9]+/\d\d$", path):
        return ["src", "pos", "invert"][:nargs]
    if path in _NUMBERED:
        label, first = _NUMBERED[path]
        return [f"{label} {first + i}" for i in range(nargs)]
    key = re.sub(r"/\d+", "", path)   # /headamp/022 -> /headamp, /fx/1/source -> /fx/source
    key = re.sub(r"^/outputs/[a-z0-9]+/", "/outputs/", key)   # bank-independent delay / iQ
    return _CONSOLE_FIELDS.get(key)


# ---- routing bank vocabulary (protocol enumerations, spelled as the console writes them)
_ROUTING_RANGES = {"AN": 4, "A": 6, "B": 6, "CARD": 4, "UIN": 4}   # 8-wide blocks per prefix
_AUX_BLOCK = ["AUX1-4", "AN1-2", "AN1-4", "AN1-6", "A1-2", "A1-4", "A1-6", "B1-2", "B1-4",
              "B1-6", "CARD1-2", "CARD1-4", "CARD1-6", "UIN1-2", "UIN1-4", "UIN1-6"]


def _eights(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{8 * i + 1}-{8 * i + 8}" for i in range(n)]


def routing_vocab(key: str, block: str) -> list[str]:
    """Every token the console accepts on ``/config/routing/<key>`` at ``block``
    (``1-8``, ``AUX``, ``5-8`` …), in enumeration order."""
    if key not in ROUTING_BLOCKS:
        raise ValueError(f"routing key must be one of {', '.join(ROUTING_BLOCKS)}, got {key!r}")
    if key in ("IN", "PLAY"):
        if block == "AUX":
            return list(_AUX_BLOCK)
        return [t for p, n in _ROUTING_RANGES.items() for t in _eights(p, n)]
    if key == "OUT":
        lo = int(block.split("-")[0])
        half = 0 if lo in (1, 9) else 4   # 1-4/9-12 take the low halves, 5-8/13-16 the high
        out = []
        for p, n in (("AN", 4), ("A", 6), ("B", 6), ("CARD", 4), ("OUT", 2), ("P16", 2)):
            out += [f"{p}{8 * i + 1 + half}-{8 * i + 4 + half}" for i in range(n)]
        out += ["AUX/CR", "AUX/TB"]
        for p, n in (("UOUT", 6), ("UIN", 4)):
            out += [f"{p}{8 * i + 1 + half}-{8 * i + 4 + half}" for i in range(n)]
        return out
    out = [t for p, n in (("AN", 4), ("A", 6), ("B", 6), ("CARD", 4)) for t in _eights(p, n)]
    out += ["OUT1-8", "OUT9-16", "P161-8", "P169-16", "AUX/CR", "AUX/TB"]
    return out + _eights("UOUT", 6) + _eights("UIN", 4)


def routing_block_names(key: str) -> list[str]:
    """The block labels of a routing line, in field order (``1-8`` … ``AUX``)."""
    n = ROUTING_BLOCKS[key]
    if key == "OUT":
        return ["1-4", "5-8", "9-12", "13-16"]
    names = _eights("", 4)
    return names[:n] if n <= 4 else names + (["AUX"] if key in ("IN", "PLAY") else _eights("", 6)[4:])
