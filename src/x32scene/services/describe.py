"""Name what changed in a scene line, grouped by the strip it belongs to — the semantic
layer over the path-level diff. Values stay the console's own tokens; only an output
source and an effect type get a label beside them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model import HEADER_RE, Line, Scene
from ..tables import decode_tap, line_fields
from ..tables_fx import decode_fx, geq_param_names
from .diff import Change
from .fx import FX_PARAMS
from .routing import channel_headamp_index

_STRIP = re.compile(r"^(/(?:ch|auxin|fxrtn|bus|mtx)/\d+|/main/(?:st|m)|/dca/\d)(/.*)?$")
_FAMILIES = ("ch", "auxin", "fxrtn", "bus", "mtx", "main", "dca")
_SECTIONS = ("scene", "headamp", "outputs", "routing", "config", "fx", "other")


@dataclass
class Described:
    path: str
    group: str        # a strip path, or one of _SECTIONS
    label: str        # 'ch 23 "Vox 1"', 'bus 09 "Vox L"', 'outputs'
    what: str         # 'send -> bus 09', 'headamp 022', 'main 05', 'AES50A'
    fields: list[tuple[str, str, str]] = field(default_factory=list)   # (name, before, after)
    note: str = ""    # 'added', 'removed', '2 -> 5 field(s)'


def _strip_what(bare: str) -> str:
    if bare == "":
        return "level"
    if bare == "/config":
        return "config"
    m = re.match(r"^/mix/(\d\d)$", bare)
    if m:
        return f"send -> bus {m.group(1)}"
    m = re.match(r"^/eq/(\d)$", bare)
    if m:
        return f"eq {m.group(1)}"
    return bare.strip("/").replace("/", " ").replace("grp", "groups")


def _label(scene: Scene, group: str) -> str:
    if not group.startswith("/"):
        return group
    parts = group.split("/")[1:]
    cfg = scene.get(f"{group}/config")
    name = cfg.args[0].strip('"') if cfg and cfg.args else ""
    return " ".join(parts) + (f' "{name}"' if name else "")


def _headamp_owners(scene: Scene) -> dict[int, int]:
    owners: dict[int, int] = {}
    for ch in range(32, 0, -1):   # the lowest channel wins a shared head amp
        idx = channel_headamp_index(scene, ch)
        if idx is not None:
            owners[idx] = ch
    return owners


def _place(scene: Scene, path: str, owners: dict[int, int]) -> tuple[str, str]:
    """(group, what) for a path."""
    m = _STRIP.match(path)
    if m:
        return m.group(1), _strip_what(m.group(2) or "")
    if HEADER_RE.match(path):
        return "scene", "header"
    m = re.match(r"^/headamp/(\d+)$", path)
    if m:
        ch = owners.get(int(m.group(1)))
        return (f"/ch/{ch:02d}" if ch else "headamp"), f"headamp {m.group(1)}"
    m = re.match(r"^/outputs/([a-z0-9]+)/(\d\d)(?:/(\w+))?$", path)
    if m:
        return "outputs", f"{m.group(1)} {m.group(2)}" + (f" {m.group(3)}" if m.group(3) else "")
    if path == "/config/routing" or path.startswith("/config/routing/"):
        return "routing", path.rpartition("/")[2] if path != "/config/routing" else "mode"
    if path.startswith("/config/userrout/"):
        return "routing", "user-" + path.rpartition("/")[2]
    if path.startswith("/config/"):
        return "config", path[len("/config/"):]
    m = re.match(r"^/fx/(\d)(?:/(\w+))?$", path)
    if m:
        kind = {None: "type", "source": "source", "par": "params"}.get(m.group(2), m.group(2))
        return "fx", f"fx {m.group(1)} {kind}"
    return "other", path


def _names(scene: Scene, path: str, nargs: int) -> list[str]:
    m = re.match(r"^/fx/(\d)/par$", path)
    if m:
        tline = scene.get(f"/fx/{m.group(1)}")
        code = tline.args[0] if tline and tline.args else ""
        names = (FX_PARAMS.get(code)
                 or {"GEQ": geq_param_names(False), "GEQ2": geq_param_names(True),
                     "TEQ": geq_param_names(False), "TEQ2": geq_param_names(True)}.get(code))
    elif HEADER_RE.match(path):
        names = ["name", "note", "safes", "flag"]
    else:
        names = line_fields(path, nargs)
    names = list(names or [])
    return names + [f"field {i + 1}" for i in range(len(names), nargs)]


def _value(path: str, name: str, tok: str) -> str:
    if name == "src" and path.startswith("/outputs/") and tok.isdigit():
        return f"{tok} ({decode_tap(int(tok))})"
    if name == "type" and re.match(r"^/fx/\d$", path):
        return f"{tok} ({decode_fx(tok)})"
    return tok


def describe(scene: Scene, change: Change, owners: dict[int, int] | None = None) -> Described:
    """What ``change`` did, in field names. ``scene`` is the after side (it supplies strip
    names and effect types); ``owners`` caches the head-amp -> channel map."""
    owners = _headamp_owners(scene) if owners is None else owners
    group, what = _place(scene, change.path, owners)
    d = Described(change.path, group, _label(scene, group), what)
    if change.before is None or change.after is None:
        d.note = "added" if change.before is None else "removed"
        return d
    a, b = Line.parse(change.before).args, Line.parse(change.after).args
    names = _names(scene, change.path, max(len(a), len(b)))
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            d.fields.append((names[i], _value(change.path, names[i], a[i]),
                             _value(change.path, names[i], b[i])))
    if len(a) != len(b):
        d.note = f"{len(a)} -> {len(b)} field(s)"
    return d


def _rank(group: str) -> tuple:
    if group.startswith("/"):
        parts = group.split("/")[1:]
        num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return (0, _FAMILIES.index(parts[0]), num, parts[1] if len(parts) > 1 else "")
    return (1, _SECTIONS.index(group) if group in _SECTIONS else len(_SECTIONS), 0, "")


def describe_all(scene: Scene, changes: list[Change]) -> list[Described]:
    """Every change described, strips in console order, then the console-wide sections."""
    owners = _headamp_owners(scene)
    out = [describe(scene, c, owners) for c in changes]
    return sorted(out, key=lambda d: (_rank(d.group), d.path))
