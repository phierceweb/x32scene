"""Snippets: the subset of a scene the console recalls without touching the rest.

The header's four filter masks name the parameter families and strips the file touches;
the body is scene lines, except that the console splits a strip's main-mix line, a DCA
line and the routing banks into one sub-path per field (``docs/format.md``).
``make_snippet`` turns an a→b delta into one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model import HEADER_RE, HEADER_WIDTH, Line, Scene
from .diff import diff

EVENTTYP_BITS = ("Preamp HA", "Config", "EQ", "Gate & Comp", "Insert", "Groups", "Fader, Pan",
                 "Mute", "Send 1-8", "Send 9-12", "Send 13-16", "Send M/C, LR", "Send Matrix",
                 "FX 1", "FX 2", "FX 3", "FX 4", "FX 5", "FX 6", "FX 7", "FX 8",
                 "Monitor", "Talkback", "Routing", "Out Patch", "User In", "User Out")

# strip family -> (mask name, bit offset of strip 1)
_STRIP_MASK = {"ch": ("channels", 0), "auxin": ("auxbuses", 0), "fxrtn": ("auxbuses", 8),
               "bus": ("auxbuses", 16), "mtx": ("maingrps", 0), "dca": ("maingrps", 8)}
_MAIN_MASK = {"st": 6, "m": 7}
_MASK_LABELS = {"channels": [("ch", 1, 32)],
                "auxbuses": [("auxin", 1, 8), ("fxrtn", 9, 16), ("bus", 17, 32)],
                "maingrps": [("mtx", 1, 6), ("main/st", 7, 7), ("main/m", 8, 8), ("dca", 9, 16)]}

# combined scene lines -> the sub-paths a snippet writes, in the console's order
_SPLIT_MIX = {"ch": ["fader", "pan", "on", "st", "mono", "mlevel"], "auxin": None,
              "fxrtn": None, "bus": None, "mtx": ["fader", "on"]}
_SPLIT_MIX["auxin"] = _SPLIT_MIX["fxrtn"] = _SPLIT_MIX["bus"] = _SPLIT_MIX["ch"]
_MIX_FIELD = {"on": 0, "fader": 1, "st": 2, "pan": 3, "mono": 4, "mlevel": 5}
_SPLIT_MAIN = {"st": ["fader", "pan", "on"], "m": ["fader", "on"]}
_SPLIT_ROUTING = {"IN": ["1-8", "9-16", "17-24", "25-32", "AUX"],
                  "AES50A": ["1-8", "9-16", "17-24", "25-32", "33-40", "41-48"],
                  "AES50B": ["1-8", "9-16", "17-24", "25-32", "33-40", "41-48"],
                  "CARD": ["1-8", "9-16", "17-24", "25-32"],
                  "OUT": ["1-4", "5-8", "9-12", "13-16"],
                  "PLAY": ["1-8", "9-16", "17-24", "25-32", "AUX"]}


@dataclass
class SnippetHeader:
    name: str
    eventtyp: int = 0
    channels: int = 0
    auxbuses: int = 0
    maingrps: int = 0

    def line(self) -> str:
        masks = " ".join(str(_signed32(m)) for m in
                         (self.eventtyp, self.channels, self.auxbuses, self.maingrps))
        return f'#4.0# "{self.name}" {masks} 1'.ljust(HEADER_WIDTH)

    def describe(self) -> dict:
        """The masks as names: filters, and the strips per mask."""
        out: dict = {"name": self.name,
                     "filters": [n for i, n in enumerate(EVENTTYP_BITS) if self.eventtyp >> i & 1]}
        for mask, ranges in _MASK_LABELS.items():
            bits = getattr(self, mask)
            out[mask] = [f"{fam}{n - lo + 1:02d}" if fam in _STRIP_MASK else fam
                         for fam, lo, hi in ranges for n in range(lo, hi + 1)
                         if bits >> (n - 1) & 1]
        return out


def _signed32(n: int) -> int:
    return n - (1 << 32) if n & (1 << 31) else n


def read_header(text: str) -> SnippetHeader | None:
    """The header of a `.snp`, or None when the first line is not one."""
    ln = Line.parse(text.split("\n", 1)[0])
    if not re.match(r"^#\d+\.\d+#$", ln.path) or len(ln.args) != 6:
        return None
    if not ln.args[0].startswith('"'):
        return None
    try:
        masks = [int(a) & 0xFFFFFFFF for a in ln.args[1:5]]
    except ValueError:
        return None
    return SnippetHeader(ln.args[0].strip('"'), *masks)


# ---- classifying a body line -------------------------------------------------------
def _event_bit(family: str, rest: list[str]) -> int | None:
    head = rest[0] if rest else ""
    if head == "preamp":
        return 0
    if head in ("config", "delay"):
        return 1
    if head == "eq":
        return 2
    if head in ("gate", "dyn"):
        return 3
    if head == "insert":
        return 4
    if head == "grp":
        return 5
    if head == "mix" and len(rest) == 2:
        sub = rest[1]
        if sub in ("fader", "pan"):
            return 6
        if sub == "on":
            return 7
        if sub in ("st", "mono", "mlevel"):
            return 11
        if sub.isdigit():
            n = int(sub)
            if family in ("bus", "main"):
                return 12
            return 8 if n <= 8 else 9 if n <= 12 else 10
    if family == "dca":
        return {"fader": 6, "on": 7}.get(head)
    return None


def classify(path: str) -> tuple[int, str | None, int | None] | None:
    """(eventtyp bit, mask name, mask bit) for a snippet body path, or None when the
    console does not carry that path in a snippet (a combined ``/ch/NN/mix`` line, the
    link and mute-group config, automix, …)."""
    parts = path.strip("/").split("/")
    fam = parts[0]
    if fam == "headamp" and len(parts) == 2:
        return (0, None, None)
    if fam == "fx" and 2 <= len(parts) <= 3 and parts[1].isdigit():
        return (12 + int(parts[1]), None, None)
    if fam == "outputs" and parts[1] != "rec":
        return (24, None, None)
    if path.startswith("/config/userrout/") and len(parts) == 3:
        return (25 if parts[2] == "in" else 26, None, None)
    if path.startswith("/config/routing/") and len(parts) == 4:
        return (23, None, None)
    if path == "/config/solo" or fam == "config" and len(parts) >= 2 and parts[1] == "dp48":
        return (21, None, None)
    if fam == "config" and len(parts) >= 2 and parts[1] == "talk":
        return (22, None, None)
    if fam == "main" and len(parts) >= 3 and parts[1] in _MAIN_MASK:
        bit = _event_bit("main", parts[2:])
        return None if bit is None else (bit, "maingrps", _MAIN_MASK[parts[1]])
    if fam in _STRIP_MASK and len(parts) >= 3 and parts[1].isdigit():
        bit = _event_bit(fam, parts[2:])
        if bit is None:
            return None
        mask, base = _STRIP_MASK[fam]
        return (bit, mask, base + int(parts[1]) - 1)
    return None


def _padded_fields(ln: Line) -> list[str]:
    """Each field with the padding the console wrote in front of it, so a split line
    keeps the source's spacing byte for byte."""
    return re.findall(r"(?:^| )( *[^ ]+)", ln.raw[len(ln.path) + 1:])


def snippet_lines(ln: Line) -> list[str]:
    """The raw snippet line(s) for one scene line: verbatim, or split per field."""
    parts = ln.path.strip("/").split("/")
    fam = parts[0]
    subs: list[str] | None = None
    if fam in _SPLIT_MIX and len(parts) == 3 and parts[2] == "mix":
        subs = _SPLIT_MIX[fam]
        fields = _padded_fields(ln)
        return [f"{ln.path}/{s} {fields[_MIX_FIELD[s]]}" for s in subs
                if _MIX_FIELD[s] < len(fields)]
    if fam == "main" and len(parts) == 3 and parts[2] == "mix" and parts[1] in _SPLIT_MAIN:
        subs = _SPLIT_MAIN[parts[1]]
    elif fam == "dca" and len(parts) == 2:
        subs = ["fader", "on"]
        fields = _padded_fields(ln)
        return [f"{ln.path}/fader {fields[1]}", f"{ln.path}/on {fields[0]}"][:len(fields)]
    elif fam == "config" and len(parts) == 3 and parts[1] == "routing" and parts[2] in _SPLIT_ROUTING:
        subs = _SPLIT_ROUTING[parts[2]]
    elif ln.path == "/config/routing":
        return [f"{ln.path}/routswitch {f}" for f in _padded_fields(ln)[:1]]
    if subs is None:
        return [ln.raw]
    fields = _padded_fields(ln)
    if fam == "main":  # fields are on, fader[, pan]; emitted fader, pan, on
        order = {"on": 0, "fader": 1, "pan": 2}
        return [f"{ln.path}/{s} {fields[order[s]]}" for s in subs if order[s] < len(fields)]
    return [f"{ln.path}/{s} {f}" for s, f in zip(subs, fields, strict=False)]


@dataclass
class Snippet:
    scene: Scene
    header: SnippetHeader
    skipped: list[str] = field(default_factory=list)  # paths a snippet cannot carry


def make_snippet(a: Scene, b: Scene, name: str, only=None) -> Snippet:
    """The lines of ``b`` that differ from ``a`` as a snippet: masks derived from the
    body. Removed lines and paths outside the snippet grammar go to ``skipped``.
    ``only(path)`` keeps the delta to the paths it accepts."""
    header = SnippetHeader(name)
    body: list[Line] = []
    skipped: list[str] = []
    for ch in diff(a, b):
        if HEADER_RE.match(ch.path):
            continue   # the snippet writes its own header; a retitle is not a body change
        if only is not None and not only(ch.path):
            continue
        if ch.after is None:
            skipped.append(ch.path)
            continue
        raws = snippet_lines(b.get(ch.path))
        if ch.before is not None:  # a split line carries only the fields that moved
            before = {" ".join(r.split()) for r in snippet_lines(Line.parse(ch.before))}
            raws = [r for r in raws if " ".join(r.split()) not in before]
        for raw in raws:
            ln = Line.parse(raw)
            scope = classify(ln.path)
            if scope is None:
                skipped.append(ln.path)
                continue
            bit, mask, mbit = scope
            header.eventtyp |= 1 << bit
            if mask is not None:
                setattr(header, mask, getattr(header, mask) | 1 << mbit)
            body.append(ln)
    return Snippet(Scene([Line.parse(header.line()), *body], True), header, skipped)
