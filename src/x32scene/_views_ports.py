"""Output views for the CLI: ``ports`` across the five /outputs banks, with the stage
sidecar's jack / device / wearer columns when one is supplied. Presentation only."""

from __future__ import annotations

from .model import Scene
from .services import routing as _routing
from .services.stage import stage_entries
from .tables import OUTPUT_BANKS, decode_tap, tap_to_bus

BANKS = (*OUTPUT_BANKS, "all")


def bus_names(scene: Scene) -> dict[int, str]:
    names = {}
    for ln in scene.find("/bus/"):
        if ln.path.endswith("/config"):
            n = int(ln.path.split("/")[2])
            names[n] = ln.args[0].strip('"') if ln.args else ""
    return names


def ports_rows(scene: Scene, bank: str = "main", stage: dict | None = None) -> list[dict]:
    """One dict per output line of ``bank`` (every bank for "all"): bank, n, src, label,
    bus, pos, invert, mirrors, and the sidecar entry (or None)."""
    if bank not in BANKS:
        raise ValueError(f"bank must be one of {', '.join(BANKS)}, got {bank!r}")
    names = bus_names(scene)
    mirrors = _routing.output_aes_mirrors(scene)
    entries = stage_entries(stage) if stage else {}
    rows = []
    for b, (size, fields) in OUTPUT_BANKS.items():
        if bank != "all" and b != bank:
            continue
        for n in range(1, size + 1):
            ln = scene.get(f"/outputs/{b}/{n:02d}")
            if ln is None or not ln.args:
                continue
            src = int(ln.args[0]) if ln.args[0].isdigit() else None
            bus = tap_to_bus(src) if src is not None else None
            label = decode_tap(src) if src is not None else ln.args[0]
            if bus is not None and bus in names:
                label += f" ({names[bus]})"
            rows.append({"bank": b, "n": n, "src": src, "label": label, "bus": bus,
                         "pos": ln.args[1] if len(ln.args) > 1 else None,
                         "invert": ln.args[2] if fields == 3 and len(ln.args) > 2 else None,
                         "mirrors": mirrors.get(n, []) if b == "main" else [],
                         "stage": entries.get((b, n))})
    return rows


def _stage_text(entry: dict) -> str:
    who = " / ".join(x for x in (entry.get("device"), entry.get("wearer")) if x)
    place = entry.get("jack", "?")
    if entry.get("box"):
        place += f" ({entry['box']})"
    when = f"confirmed {entry['confirmed']}" if entry.get("confirmed") else "unconfirmed"
    return f"@ {place} -> {who or '?'} [{when}]"


def cmd_ports(scene: Scene, physical: int | None = None, *, bank: str = "main",
              stage: dict | None = None) -> None:
    """Outputs -> source. ``physical`` (the console's jack count, from a preflight config's
    ``monitor.physical_outputs``) labels main outputs physical or virtual — the scene file
    cannot say which is which. A stage sidecar adds where each output lands and who hears it."""
    if physical is None:
        print("Outputs (declare monitor.physical_outputs in a preflight config to label "
              "physical vs virtual):")
    else:
        print(f"Outputs (main 1-{physical} = physical jacks; {physical + 1}-16 = virtual, "
              "mirrored via AES50):")
    for r in ports_rows(scene, bank, stage):
        kind = ""
        if physical is not None and r["bank"] == "main":
            kind = "[XLR ] " if r["n"] <= physical else "[virt] "
        pos = f" {r['pos']}" if r["pos"] and r["pos"] != "POST" else ""
        mtxt = f"  [{' + '.join(r['mirrors'])} -> stagebox]" if r["mirrors"] else ""
        print(f"  {r['bank']} {r['n']:02d} {kind}-> {r['label']:<22}{pos}{mtxt}")
        if r["stage"]:
            print(f"      {_stage_text(r['stage'])}")
