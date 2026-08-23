"""preflight family ``stage``: the scene against the stage sidecar — every documented
output exists, carries something, carries the bus it was documented for, and agrees with
the expected-config where both name a bus. The sidecar records an operator's assertion
about cabling; none of this verifies a cable.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import decode_tap, tap_to_bus
from .preflight_config import Finding
from .stage import owner_label, stage_entries


def _pinned(expected: dict, bank: str, n: int) -> dict | None:
    """The expected-config's outputs entry for (bank, n), if it is a usable object."""
    outputs = expected.get("outputs")
    entries = outputs.get(bank) if isinstance(outputs, dict) else None
    if not isinstance(entries, dict):
        return None
    for key, entry in entries.items():
        if str(key).isdigit() and int(key) == n and isinstance(entry, dict):
            return entry
    return None


def check(scene: Scene, expected: dict, stage: dict, out: list[Finding]) -> None:
    for (bank, n), entry in sorted(stage_entries(stage).items()):
        area, path = f"stage {bank} {n:02d}", f"/outputs/{bank}/{n:02d}"
        who = owner_label(entry)
        ln = scene.get(path)
        if ln is None or not ln.args or not ln.args[0].isdigit():
            out.append(Finding("FAIL", area, f"documented ({who}) but the scene has no such "
                               "line", path))
            continue
        src = int(ln.args[0])
        if src == 0:
            out.append(Finding("FAIL", area, f"documented as feeding {who} but carries "
                               "nothing (src 0)", path))
            continue
        bus = entry.get("bus")
        if bus is None:
            continue
        if tap_to_bus(src) != bus:
            out.append(Finding("FAIL", area, f"carries {decode_tap(src)}, documented as "
                               f"bus {bus} ({who})", path))
        pin = _pinned(expected, bank, n)
        if pin is None:
            continue
        cfg_bus = pin.get("bus")
        if cfg_bus is None and isinstance(pin.get("src"), int):
            cfg_bus = tap_to_bus(pin["src"])
        if isinstance(cfg_bus, int) and cfg_bus != bus:
            out.append(Finding("FAIL", area, f"sidecar says bus {bus}, expected-config says "
                               f"bus {cfg_bus} — the two documents disagree"))
