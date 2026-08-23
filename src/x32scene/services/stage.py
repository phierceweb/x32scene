"""The stage sidecar: what happens past the console's own connectors — which output lands
on which jack, in which box, feeding which device, worn by whom. A ``.scn`` cannot hold any
of it, so the document is an operator's assertion: preflight checks the scene against it
and never verifies a cable.

Keyed like the expected-config's ``outputs`` section — bank, then output number — so the
two documents join on the one handle a scene offers. Validated whole on load, like a
band-swap plan; a malformed document raises before anything is checked.
"""

from __future__ import annotations

import json

from ..tables import OUTPUT_BANKS

STAGE_KEYS = frozenset({"outputs"})
ENTRY_KEYS = frozenset({"jack", "box", "device", "wearer", "bus", "confirmed", "notes"})
_STRINGS = ENTRY_KEYS - {"bus"}


def load_stage(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    validate_stage(doc)
    return doc


def _keys(d: dict) -> list:
    return [k for k in d if not str(k).startswith("_")]


def validate_stage(doc: object) -> None:
    """Raise ValueError naming the first problem; a usable document passes silently."""
    if not isinstance(doc, dict):
        raise ValueError(f"stage sidecar must be an object, got {type(doc).__name__}")
    unknown = [k for k in _keys(doc) if k not in STAGE_KEYS]
    if unknown:
        raise ValueError(f"stage sidecar: unknown key {unknown[0]!r} (expected: outputs)")
    outputs = doc.get("outputs", {})
    if not isinstance(outputs, dict):
        raise ValueError("stage sidecar: outputs must be an object, got "
                         f"{type(outputs).__name__}")
    claimed: dict[tuple[str, str], str] = {}
    for bank in _keys(outputs):
        if bank not in OUTPUT_BANKS:
            raise ValueError(f"stage sidecar: unknown bank {bank!r} "
                             f"(expected: {', '.join(OUTPUT_BANKS)})")
        entries = outputs[bank]
        if not isinstance(entries, dict):
            raise ValueError(f"stage sidecar: outputs.{bank} must be an object, got "
                             f"{type(entries).__name__}")
        size = OUTPUT_BANKS[bank][0]
        seen: dict[int, str] = {}
        for key in _keys(entries):
            where = f"stage sidecar: {bank} {key!r}"
            try:
                n = int(key)
            except (TypeError, ValueError):
                raise ValueError(f"{where} is not a number 1-{size}") from None
            if not 1 <= n <= size:
                raise ValueError(f"{where} out of range 1-{size}")
            if n in seen:
                raise ValueError(f"stage sidecar: {bank} keys {seen[n]!r} and {key!r} "
                                 f"both name {n}")
            seen[n] = key
            _validate_entry(entries[key], f"stage sidecar: {bank} {n:02d}", claimed)


def _validate_entry(entry: object, where: str, claimed: dict[tuple[str, str], str]) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{where}: must be an object, got {type(entry).__name__}")
    unknown = [k for k in _keys(entry) if k not in ENTRY_KEYS]
    if unknown:
        raise ValueError(f"{where}: unknown key {unknown[0]!r} "
                         f"(expected: {', '.join(sorted(ENTRY_KEYS))})")
    for k in sorted(_STRINGS):
        if k in entry and not isinstance(entry[k], str):
            raise ValueError(f"{where}: {k} must be a string, got {entry[k]!r}")
    if "bus" in entry:
        b = entry["bus"]
        if isinstance(b, bool) or not isinstance(b, int) or not 1 <= b <= 16:
            raise ValueError(f"{where}: bus must be a whole number 1-16, got {b!r}")
    if "jack" in entry:
        key = (entry.get("box", ""), entry["jack"])
        if key in claimed:
            on = f" on {key[0]!r}" if key[0] else ""
            raise ValueError(f"{where} and {claimed[key]} claim the same jack "
                             f"{entry['jack']!r}{on}")
        claimed[key] = where


def stage_entries(doc: dict) -> dict[tuple[str, int], dict]:
    """``{(bank, n): entry}`` for a validated document."""
    out: dict[tuple[str, int], dict] = {}
    outputs = doc.get("outputs", {})
    for bank in _keys(outputs):
        for key in _keys(outputs[bank]):
            out[(bank, int(key))] = outputs[bank][key]
    return out


def owner_label(entry: dict) -> str:
    """The human side of an entry for a message: wearer, else device, else jack."""
    return entry.get("wearer") or entry.get("device") or entry.get("jack") or "?"
