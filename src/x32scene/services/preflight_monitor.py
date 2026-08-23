"""preflight family ``monitor``: derived monitor-path checks that need no per-value
declaration — where the console's physical jacks end, stereo output pairing, whether a
virtual output leaves the console at all, and whether a routed bus has anyone in it.

Every one is declared, never assumed: the jack count is not in the file, p16 carries direct
outs in user order, and a template scene legitimately routes empty buses.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import OUTPUT_BANKS, SEND_STRIPS, decode_tap, send_is_live, tap_to_bus
from .preflight_config import Finding, fail_unknown, mapping, want_bool, want_index
from .routing import output_reach, output_sources, routing_blocks, userrout

SECTIONS = frozenset({"monitor"})
_KEYS = frozenset({"physical_outputs", "stereo_pairs", "require_reachable",
                   "require_live_senders"})
_PAIR_BANKS = ("main", "aux")


def check(scene: Scene, expected: dict, out: list[Finding]) -> None:
    mon = mapping(expected, "monitor", "config", out)
    fail_unknown(mon, _KEYS, "monitor", out)
    physical = want_index(mon, "physical_outputs", "monitor", out, lo=1, hi=16)
    if want_bool(mon, "require_reachable", "monitor", out):
        _reachable(scene, physical, out)
    for bank in _pair_banks(mon, out):
        _pairs(scene, bank, out)
    if want_bool(mon, "require_live_senders", "monitor", out):
        _live_senders(scene, out)


def _pair_banks(mon: dict, out: list[Finding]) -> list[str]:
    banks = mon.get("stereo_pairs", [])
    if not isinstance(banks, list):
        out.append(Finding("FAIL", "monitor",
                           f"stereo_pairs must be a list of banks, got {banks!r}"))
        return []
    ok = []
    for b in banks:
        if b in _PAIR_BANKS:
            ok.append(b)
        else:
            out.append(Finding("FAIL", "monitor", f"stereo_pairs: {b!r} is not a pairable "
                               f"bank ({', '.join(_PAIR_BANKS)})"))
    return ok


def _reachable(scene: Scene, physical: int | None, out: list[Finding]) -> None:
    if physical is None:
        out.append(Finding("FAIL", "monitor", "require_reachable needs physical_outputs — "
                           "the console model is not in the scene"))
        return
    if not (routing_blocks(scene, "AES50A") or routing_blocks(scene, "AES50B")
            or userrout(scene, "out")):
        out.append(Finding("FAIL", "monitor", "cannot verify reachability: no "
                           "/config/routing/AES50A, AES50B or /config/userrout/out"))
        return
    reach = output_reach(scene)
    srcs = output_sources(scene, "main")
    for n in range(physical + 1, OUTPUT_BANKS["main"][0] + 1):
        path, area = f"/outputs/main/{n:02d}", f"out main {n:02d}"
        src = srcs.get(n)
        if src is None:
            out.append(Finding("FAIL", area, "line missing — cannot verify it leaves the "
                               "console", path))
        elif src != 0 and n not in reach:
            out.append(Finding("FAIL", area, f"carries {decode_tap(src)} but no AES50/card "
                               f"block or user-out slot carries output {n} off the console",
                               path))


def _pairs(scene: Scene, bank: str, out: list[Finding]) -> None:
    srcs = output_sources(scene, bank)
    for odd in range(1, OUTPUT_BANKS[bank][0], 2):
        even = odd + 1
        area = f"out {bank} {odd:02d}"
        a, b = srcs.get(odd), srcs.get(even)
        if a is None or b is None:
            out.append(Finding("FAIL", area,
                               f"out {odd:02d}/{even:02d}: line missing — cannot verify the pair"))
            continue
        bus = tap_to_bus(a)
        if bus is None:
            continue   # not a bus feed: nothing to pair
        if bus % 2 == 0 or tap_to_bus(b) != bus + 1:
            out.append(Finding("FAIL", area,
                               f"out {odd:02d}/{even:02d} carry {decode_tap(a)} / "
                               f"{decode_tap(b)} — not a stereo pair (an odd bus, then its "
                               "partner)", f"/outputs/{bank}/{odd:02d}"))


def _bus_name(scene: Scene, bus: int) -> str:
    ln = scene.get(f"/bus/{bus:02d}/config")
    name = ln.args[0].strip('"') if ln and ln.args else ""
    return f" ({name})" if name else ""


def _live_senders(scene: Scene, out: list[Finding]) -> None:
    routed: dict[int, list[str]] = {}
    for bank in OUTPUT_BANKS:
        for n, src in output_sources(scene, bank).items():
            bus = tap_to_bus(src)
            if bus:
                routed.setdefault(bus, []).append(f"/outputs/{bank}/{n:02d}")
    for bus in sorted(routed):
        area, where = f"bus {bus:02d}", ", ".join(routed[bus])
        lines = [ln for ln in (scene.get(f"{s}/mix/{bus:02d}") for s in SEND_STRIPS) if ln]
        if not lines:
            out.append(Finding("FAIL", area, f"cannot verify — no send lines for bus {bus}, "
                               f"which feeds {where}"))
        elif not any(send_is_live(ln.args) for ln in lines):
            out.append(Finding("FAIL", area, f"bus {bus}{_bus_name(scene, bus)} feeds {where} "
                               "but has no sender ON above -oo", f"/bus/{bus:02d}"))
