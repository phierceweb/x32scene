"""preflight family ``sends``: monitor-send line parity (always on), the tap point per bus
with family and per-strip exceptions, and which strips must be audible or silent in a bus.

The tap token lives only on the odd bus of a pair and governs both; ``on`` and ``level`` are
per line. Levels are deliberately not checked — they would need a second tolerance.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import SEND_STRIPS, send_is_live, strip_path
from .iem import send_shape_errors
from .preflight_config import Finding, fail_unknown, mapping, numbered_items, spec, want_str

SECTIONS = frozenset({"sends"})
_KEYS = frozenset({"tap", "except", "present", "absent"})
_FAMILIES = ("/ch", "/auxin", "/fxrtn")
_SEND_SET = frozenset(SEND_STRIPS)


def _shape(scene: Scene, out: list[Finding]) -> None:
    paths = [f"{s}/mix/{b:02d}" for b in range(1, 17) for s in SEND_STRIPS]
    for err in send_shape_errors(scene, paths):
        path, msg = err.split(" ", 1)
        bus = int(path.rsplit("/", 1)[1])
        out.append(Finding("FAIL", f"send bus {bus:02d}", msg, path))


def _strip(v: object, area: str, out: list[Finding]) -> str | None:
    """A send strip from config — a channel number or a path; None after one FAIL."""
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        out.append(Finding("FAIL", area, f"{v!r} is not a send strip (channel number, "
                           "/auxin/NN or /fxrtn/NN)"))
        return None
    path = strip_path(v)
    if path not in _SEND_SET:
        out.append(Finding("FAIL", area, f"{path} is not a send strip (channel, /auxin/NN "
                           "or /fxrtn/NN)"))
        return None
    return path


def _rules(exc: dict, area: str, out: list[Finding]) -> dict[str, str]:
    rules: dict[str, str] = {}
    for k, v in exc.items():
        if str(k).startswith("_"):
            continue
        key = k if k in _FAMILIES else (strip_path(k) if isinstance(k, str) else None)
        if key not in _FAMILIES and key not in _SEND_SET:
            out.append(Finding("FAIL", area, f"except key {k!r} is neither a strip family "
                               f"({', '.join(_FAMILIES)}) nor a send strip"))
        elif not isinstance(v, str):
            out.append(Finding("FAIL", area, f"except {k!r}: expected tap must be a string, "
                               f"got {v!r}"))
        else:
            rules[key] = v
    return rules


def _tap(scene: Scene, bus: int, entry: dict, out: list[Finding]) -> None:
    area = f"send bus {bus:02d}"
    tap = want_str(entry, "tap", area, out)
    if tap is None:
        return
    if bus % 2 == 0:
        out.append(Finding("FAIL", area, f"bus {bus} has no tap of its own — it is stored on "
                           f"bus {bus - 1} and governs both; declare it there"))
        return
    rules = _rules(mapping(entry, "except", area, out), area, out)
    missing = []
    for strip in SEND_STRIPS:
        want = rules.get(strip) or rules.get(strip.rpartition("/")[0]) or tap
        ln = scene.get(f"{strip}/mix/{bus:02d}")
        if ln is None:
            missing.append(strip)
        elif len(ln.args) >= 4 and ln.args[3] != want:   # a short line is a shape finding
            out.append(Finding("FAIL", area, f"{strip} tap {ln.args[3]} != expected {want}",
                               ln.path))
    if missing:
        out.append(Finding("FAIL", area, f"{len(missing)} send line(s) missing — cannot "
                           f"verify tap ({missing[0]} …)"))


def _audible(scene: Scene, bus: int, entry: dict, key: str, want_live: bool,
             out: list[Finding]) -> None:
    area = f"send bus {bus:02d}"
    lst = entry.get(key)
    if lst is None:
        return
    if not isinstance(lst, list):
        out.append(Finding("FAIL", area, f"{key} must be a list of strips, got {lst!r}"))
        return
    for v in lst:
        strip = _strip(v, area, out)
        if strip is None:
            continue
        path = f"{strip}/mix/{bus:02d}"
        ln = scene.get(path)
        if ln is None:
            out.append(Finding("FAIL", area, f"{path} missing — cannot verify", path))
            continue
        live, state = send_is_live(ln.args), " ".join(ln.args[:2])
        if live and not want_live:
            out.append(Finding("FAIL", area, f"{strip} is audible in bus {bus} ({state}) — "
                               "expected silent", path))
        elif want_live and not live:
            out.append(Finding("FAIL", area, f"{strip} is not audible in bus {bus} ({state}) — "
                               "OFF or -oo", path))


def check(scene: Scene, expected: dict, out: list[Finding]) -> None:
    _shape(scene, out)
    section = mapping(expected, "sends", "config", out)
    for bus, exp in numbered_items(section, "sends", out, lo=1, hi=16):
        area = f"send bus {bus:02d}"
        entry = spec(exp, area, out)
        if entry is None:
            continue
        fail_unknown(entry, _KEYS, area, out)
        _tap(scene, bus, entry, out)
        _audible(scene, bus, entry, "present", True, out)
        _audible(scene, bus, entry, "absent", False, out)
