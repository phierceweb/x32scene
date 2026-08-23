"""preflight family ``outputs``: the five /outputs banks.

Line shape runs with no config — a wrong field count round-trips clean while the desk
reads the wrong field. Per-output ``src``/``bus``, ``pos`` and ``invert`` pins compare
the raw tokens against the config, never a decoded label.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import OUTPUT_BANKS, bus_to_tap, decode_tap
from .preflight_config import (Finding, fail_unknown, mapping, numbered_items, spec,
                               want_bool, want_index, want_str)

SECTIONS = frozenset({"outputs"})
_KEYS = frozenset({"src", "bus", "pos", "invert"})
_REC_KEYS = frozenset({"src", "bus", "pos"})   # a rec line carries no invert field
_SRC_MAX = 76   # the published /outputs src enumeration ends at Talkback


def out_path(bank: str, n: int) -> str:
    return f"/outputs/{bank}/{n:02d}"


def _src_label(src: int) -> str:
    return f"{src} ({decode_tap(src)})" if src <= _SRC_MAX else str(src)


def _shape(scene: Scene, out: list[Finding]) -> None:
    for bank, (size, fields) in OUTPUT_BANKS.items():
        missing = []
        for n in range(1, size + 1):
            path = out_path(bank, n)
            ln = scene.get(path)
            if ln is None:
                missing.append(path)
            elif len(ln.args) != fields:
                out.append(Finding("FAIL", f"out {bank} {n:02d}",
                                   f"carries {len(ln.args)} field(s), not {fields}", path))
        if missing:
            out.append(Finding("FAIL", f"out {bank}",
                               f"{len(missing)} line(s) missing — cannot verify "
                               f"({missing[0]} …)"))


def _check_entry(scene: Scene, bank: str, n: int, exp: dict, out: list[Finding]) -> None:
    area = f"out {bank} {n:02d}"
    fields = OUTPUT_BANKS[bank][1]
    fail_unknown(exp, _REC_KEYS if fields == 2 else _KEYS, area, out)
    path = out_path(bank, n)
    ln = scene.get(path)
    if ln is None or len(ln.args) != fields:
        out.append(Finding("FAIL", area, "line missing or malformed — cannot verify", path))
        return
    src = want_index(exp, "src", area, out, lo=0, hi=_SRC_MAX)
    bus = want_index(exp, "bus", area, out, lo=1, hi=16)
    want = label = None
    if "src" in exp and "bus" in exp:
        out.append(Finding("FAIL", area, "declare src or bus, not both"))
    elif bus is not None:
        want, label = bus_to_tap(bus), f"{bus_to_tap(bus)} (bus {bus})"
    elif src is not None:
        want, label = src, str(src)
    if want is not None:
        if ln.args[0].isdigit():
            got = int(ln.args[0])
            if got != want:
                out.append(Finding("FAIL", area,
                                   f"src {_src_label(got)} != expected {label}", path))
        else:
            out.append(Finding("FAIL", area, f"src token {ln.args[0]!r} is not a number", path))
    pos = want_str(exp, "pos", area, out)
    if pos is not None and ln.args[1] != pos:
        out.append(Finding("FAIL", area, f"pos {ln.args[1]} != expected {pos}", path))
    if fields == 3:
        inv = want_bool(exp, "invert", area, out)
        if inv is not None and (ln.args[2] == "ON") is not inv:
            out.append(Finding("FAIL", area,
                               f"invert {ln.args[2]} != expected {'ON' if inv else 'OFF'}",
                               path))


def check(scene: Scene, expected: dict, out: list[Finding]) -> None:
    _shape(scene, out)
    section = mapping(expected, "outputs", "config", out)
    fail_unknown(section, OUTPUT_BANKS, "outputs", out)
    for bank, (size, _) in OUTPUT_BANKS.items():
        entries = mapping(section, bank, "outputs", out)
        for n, exp in numbered_items(entries, f"out {bank}", out, lo=1, hi=size):
            entry = spec(exp, f"out {bank} {n:02d}", out)
            if entry is not None:
                _check_entry(scene, bank, n, entry, out)
