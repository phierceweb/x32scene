"""One decoder for every X32 file header: scene safes, snippet filters, preset flags.

The first line says which kind of file this is; ``decode_header`` names it and turns its
bitmasks into words (``docs/format.md`` has each shape).
"""

from __future__ import annotations

import re

from ..model import Line
from .presets import header_sections
from .snippets import read_header as _snippet_header

SCENE_SAFES = ("Talkback", "Effects", "Mix Buses", "Chan Process", "Configuration",
               "Preamp (HA)", "Output Patch", "Routing I/O")  # bits 1-8; bit 0 unused
PRESET_KINDS = {"0": "channel", "1": "effect", "2": "routing", "3": "monitor"}

_VERSION = re.compile(r"^#(\d+\.\d+)#$")


def scene_safes(mask: str) -> list[str]:
    """Names of the safe groups set in a scene's ``%`` mask, read right to left."""
    bits = mask.lstrip("%")[::-1]
    return [n for i, n in enumerate(SCENE_SAFES, start=1) if i < len(bits) and bits[i] == "1"]


def decode_header(text: str) -> dict | None:
    """``{"kind": ..., "version": ..., "name": ..., ...}`` for the first line of a file,
    or None for a headerless file (a bare ``.chn``)."""
    first = text.split("\n", 1)[0]
    ln = Line.parse(first)
    m = _VERSION.match(ln.path)
    if not m or not ln.args:
        return None
    out: dict = {"version": m.group(1)}
    a = ln.args
    if a[0].startswith('"'):
        if len(a) >= 4 and a[1].startswith('"') and a[2].startswith("%"):
            out.update(kind="scene", name=a[0].strip('"'), note=a[1].strip('"'),
                       safes=scene_safes(a[2]))
            return out
        snip = _snippet_header(first)
        if snip is not None:
            out.update(kind="snippet", **snip.describe())
            return out
        return out | {"kind": "unknown", "name": a[0].strip('"')}
    if len(a) >= 5 and a[0].isdigit() and a[1].startswith('"'):
        kind = PRESET_KINDS.get(a[2], "unknown")
        out.update(kind=f"{kind} preset", slot=int(a[0]), name=a[1].strip('"'))
        if kind == "channel":
            out["sections"] = header_sections(first)
        elif kind == "effect":
            out["display_type"] = a[3]
        return out
    return out | {"kind": "unknown"}
