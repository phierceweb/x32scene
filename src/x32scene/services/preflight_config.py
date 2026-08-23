"""The expected-config document layer for preflight: the ``Finding`` record and the guards
that turn a malformed config into a named FAIL instead of a traceback or a silent pass.

Imports nothing from the package, so every ``preflight_*`` check module can use it without
an import cycle through ``preflight.py``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass
class Finding:
    severity: str  # "FAIL" | "WARN"
    area: str
    message: str
    path: str | None = None  # the scene line the finding is about, when there is one


def unknown_keys(d: dict, allowed: Iterable[str]) -> list[str]:
    """Keys not in ``allowed``; '_'-prefixed keys are comments."""
    return [k for k in d if k not in allowed and not str(k).startswith("_")]


def fail_unknown(d: dict, allowed: Iterable[str], area: str, out: list[Finding]) -> None:
    for k in unknown_keys(d, allowed):
        out.append(Finding("FAIL", area, f"unknown config key {k!r} — check spelling"))


def mapping(parent: dict, key: str, area: str, out: list[Finding]) -> dict:
    """A section that must be a JSON object. Anything else is one FAIL and reads as empty,
    so the rest of the report still runs."""
    v = parent.get(key, {})
    if isinstance(v, dict):
        return v
    out.append(Finding("FAIL", area, f"{key} must be an object, got {type(v).__name__}"))
    return {}


def spec(v: object, area: str, out: list[Finding]) -> dict | None:
    """One numbered entry that must be an object; None (after one FAIL) when it is not."""
    if isinstance(v, dict):
        return v
    out.append(Finding("FAIL", area, f"must be an object, got {type(v).__name__}"))
    return None


def numbered_items(d: dict, area: str, out: list[Finding], *,
                   lo: int, hi: int) -> list[tuple[int, object]]:
    """Sorted ``(n, value)`` pairs for a section keyed by number.

    '_'-keys are comments. A non-numeric key, one outside ``lo``-``hi``, and a second
    spelling of one number ("9" beside "09") are each one FAIL rather than a silent skip
    or an arbitrary last-wins.
    """
    items: list[tuple[int, object]] = []
    seen: dict[int, str] = {}
    for k, v in d.items():
        ks = str(k)
        if ks.startswith("_"):
            continue
        try:
            n = int(ks)
        except ValueError:
            out.append(Finding("FAIL", area, f"non-numeric key {ks!r}"))
            continue
        if not lo <= n <= hi:
            out.append(Finding("FAIL", area, f"key {ks!r} out of range {lo}-{hi}"))
            continue
        if n in seen:
            out.append(Finding("FAIL", area, f"keys {seen[n]!r} and {ks!r} both name {n}"))
            continue
        seen[n] = ks
        items.append((n, v))
    return sorted(items)


def _is_number(v: object) -> bool:
    # bool passes isinstance(int), so True would otherwise read as 1
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def want_bool(d: dict, key: str, area: str, out: list[Finding]) -> bool | None:
    """The JSON boolean under ``key``; None when absent (silent) or not a boolean (FAIL)."""
    if key not in d:
        return None
    v = d[key]
    if isinstance(v, bool):
        return v
    out.append(Finding("FAIL", area, f"{key} must be true or false, got {v!r}"))
    return None


def want_number(d: dict, key: str, area: str, out: list[Finding]) -> float | None:
    if key not in d:
        return None
    v = d[key]
    if _is_number(v):
        return float(v)
    out.append(Finding("FAIL", area, f"{key} must be a number, got {v!r}"))
    return None


def want_str(d: dict, key: str, area: str, out: list[Finding]) -> str | None:
    if key not in d:
        return None
    v = d[key]
    if isinstance(v, str):
        return v
    out.append(Finding("FAIL", area, f"{key} must be a string, got {v!r}"))
    return None


def want_index(d: dict, key: str, area: str, out: list[Finding], *,
               lo: int, hi: int) -> int | None:
    """A whole number ``lo``..``hi`` naming a bus, output or group — not a bool, not 3.0."""
    if key not in d:
        return None
    v = d[key]
    if _is_number(v) and not isinstance(v, float) and lo <= v <= hi:
        return int(v)
    out.append(Finding("FAIL", area, f"{key} must be a whole number {lo}-{hi}, got {v!r}"))
    return None
