"""Channel and bus names, and the 16 mix buses' links, FX feeds and send taps."""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Scene
from .iem import send_taps


@dataclass(frozen=True)
class BusRow:
    bus: int
    name: str
    linked: bool
    fx_slot: int | None
    fx_type: str | None
    taps: dict[str, int]


def _names(scene: Scene, family: str) -> dict[int, str]:
    names = {}
    for ln in scene.find(f"/{family}/"):
        if ln.path.endswith("/config"):
            names[int(ln.path.split("/")[2])] = ln.args[0].strip('"') if ln.args else ""
    return names


def channel_names(scene: Scene) -> dict[int, str]:
    return _names(scene, "ch")


def bus_names(scene: Scene) -> dict[int, str]:
    return _names(scene, "bus")


def bus_rows(scene: Scene) -> list[BusRow]:
    """``linked`` is the pair's link, on both buses; ``fx_type`` is "?" for a slot fed by the
    bus that has no type line."""
    names = bus_names(scene)
    bl = scene.get("/config/buslink")
    linked = {2 * i + 1: bl.args[i] == "ON" for i in range(min(8, len(bl.args)))} if bl else {}
    fx_src: dict[int, int] = {}
    for ln in scene.find("/fx/"):
        if ln.path.endswith("/source") and ln.args and ln.args[0].startswith("MIX"):
            fx_src[int(ln.args[0][3:])] = int(ln.path.split("/")[2])
    fx_type = {int(ln.path.split("/")[2]): ln.args[0]
               for ln in scene.find("/fx/") if len(ln.path.split("/")) == 3 and ln.args}
    rows = []
    for n in range(1, 17):
        slot = fx_src.get(n)
        rows.append(BusRow(n, names.get(n, ""), linked.get(n - (n % 2 == 0), False), slot,
                           None if slot is None else fx_type.get(slot, "?"),
                           send_taps(scene, n)))
    return rows
