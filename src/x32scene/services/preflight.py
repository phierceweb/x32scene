"""Semantic rig preflight — check a scene against an expected-state config (JSON, see
``config/example-preflight.json``). Gain checks are WARN with a tolerance (record gains
drift by design); every other mismatch — and any unknown or malformed config key — is FAIL.

Every section is optional. ``coverage`` says which sections a config declared, so a clean
report never claims more than what actually ran.

``in_main``: True = audibly in the Main L/R blend (ON, LR assigned, fader above −∞);
False = silenced any way (muted, LR unassigned, or fader at −∞).
"""

from __future__ import annotations

import json

from ..model import Scene
from . import (preflight_groups, preflight_links, preflight_monitor, preflight_outputs,
               preflight_routing, preflight_sends, preflight_stage)
from .preflight_config import (Finding, fail_unknown, mapping, numbered_items, spec,
                               want_bool, want_number, want_str)
from .routing import channel_headamp_index, record_map, resolve_in_slot
from .stage import stage_entries

__all__ = ["Finding", "coverage", "load_expected", "physical_outputs", "preflight", "report"]

# section -> range of its numbered keys, for the families checked in this module
_SECTIONS: dict[str, tuple[int, int]] = {"channels": (1, 32), "record": (1, 32), "fx": (1, 8)}
# one module per family; each exports SECTIONS (its config keys) and check(). The
# top-level allowlist is derived from them, so a section cannot exist without its check.
_MODULES = (preflight_outputs, preflight_monitor, preflight_routing, preflight_links,
            preflight_sends, preflight_groups)
_ALL_SECTIONS = (*_SECTIONS, *(s for m in _MODULES for s in sorted(m.SECTIONS)))
_TOP_KEYS = frozenset({"gain_tolerance_db", *_ALL_SECTIONS})
_CH_KEYS = frozenset({"name", "source", "in_main", "phantom", "gain"})
_AREA_WIDTH = 14


def load_expected(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: expected-config must be a JSON object, "
                         f"got {type(doc).__name__}")
    return doc


def _in_main(mix_args: list[str]) -> bool:
    """Audibly in the Main L/R blend: ON, LR assigned, fader above -oo."""
    return (len(mix_args) > 2 and mix_args[0] == "ON"
            and mix_args[1] != "-oo" and mix_args[2] == "ON")


def _check_channel(scene: Scene, ch: int, exp: dict, tol: float, out: list[Finding]) -> None:
    area = f"ch {ch:02d}"
    fail_unknown(exp, _CH_KEYS, area, out)
    cfg_path = f"/ch/{ch:02d}/config"
    cfg = scene.get(cfg_path)
    if cfg is None or not cfg.args:
        out.append(Finding("FAIL", area, "channel missing from scene", cfg_path))
        return
    name = cfg.args[0].strip('"')
    want = want_str(exp, "name", area, out)
    if want is not None and name != want:
        out.append(Finding("FAIL", area, f'name "{name}" != expected "{want}"', cfg_path))
    want = want_str(exp, "source", area, out)
    if want is not None:
        src = resolve_in_slot(scene, int(cfg.args[-1]))
        if src != want:
            out.append(Finding("FAIL", area, f"source {src} != expected {want}", cfg_path))
    want_main = want_bool(exp, "in_main", area, out)
    if want_main is not None:
        mix_path = f"/ch/{ch:02d}/mix"
        mix = scene.get(mix_path)
        if mix is None or len(mix.args) < 3:
            # absence of the line is not evidence the channel is out of the blend
            out.append(Finding("FAIL", area, "/mix line missing — cannot verify main blend",
                               mix_path))
        else:
            actual = _in_main(mix.args)
            if actual is not want_main:
                got, want_s = ("in", "out of") if actual else ("out of", "in")
                out.append(Finding("FAIL", area,
                                   f"{got} the main blend, expected {want_s} it", mix_path))
    phantom = want_bool(exp, "phantom", area, out)
    gain = want_number(exp, "gain", area, out)
    if phantom is None and gain is None:
        return
    idx = channel_headamp_index(scene, ch)
    ha_path = f"/headamp/{idx:03d}" if idx is not None else None
    ha = scene.get(ha_path) if ha_path else None
    if ha is None or len(ha.args) < 2:
        out.append(Finding("FAIL", area, "no head amp for source (gain/phantom expected)",
                           ha_path))
        return
    if phantom is not None:
        actual = ha.args[1] == "ON"
        if actual is not phantom:
            out.append(Finding(
                "FAIL", area,
                f"phantom {'ON' if actual else 'OFF'} != expected "
                f"{'ON' if phantom else 'OFF'}", ha_path))
    if gain is not None:
        actual_gain = float(ha.args[0])
        drift = actual_gain - gain
        if abs(drift) > tol:
            out.append(Finding(
                "WARN", area,
                f"gain {actual_gain:+.1f} is {drift:+.1f} dB off expected "
                f"{gain:+.1f} (tolerance ±{tol:g})", ha_path))


def preflight(scene: Scene, expected: dict, *, stage: dict | None = None) -> list[Finding]:
    """All deviations of ``scene`` from the expected-config (and from the stage sidecar,
    when one is given). Empty list == preflight OK."""
    out: list[Finding] = []
    fail_unknown(expected, _TOP_KEYS, "config", out)
    tol = want_number(expected, "gain_tolerance_db", "config", out)
    tol = 3.0 if tol is None else tol
    lo, hi = _SECTIONS["channels"]
    for ch, exp in numbered_items(mapping(expected, "channels", "config", out),
                                  "channels", out, lo=lo, hi=hi):
        entry = spec(exp, f"ch {ch:02d}", out)
        if entry is not None:
            _check_channel(scene, ch, entry, tol, out)
    lo, hi = _SECTIONS["record"]
    record = numbered_items(mapping(expected, "record", "config", out), "record", out,
                            lo=lo, hi=hi)
    if record:
        actual = dict(record_map(scene))
        for trk, want in record:
            got = actual.get(trk)
            if got != want:
                out.append(Finding(
                    "FAIL", f"record {trk:02d}",
                    f"record track {trk} sources {got} != expected {want}",
                    "/config/userrout/out"))
    lo, hi = _SECTIONS["fx"]
    for fx_n, want in numbered_items(mapping(expected, "fx", "config", out), "fx", out,
                                     lo=lo, hi=hi):
        path = f"/fx/{fx_n}"
        ln = scene.get(path)
        got = ln.args[0] if ln and ln.args else None
        if got != want:
            out.append(Finding("FAIL", f"fx {fx_n}",
                               f"fx slot {fx_n} type {got} != expected {want}", path))
    for module in _MODULES:
        module.check(scene, expected, out)
    if stage is not None:
        preflight_stage.check(scene, expected, stage, out)
    return out


def physical_outputs(expected: dict) -> int | None:
    """The declared jack count (``monitor.physical_outputs``), when the config carries a
    valid one."""
    mon = expected.get("monitor")
    v = mon.get("physical_outputs") if isinstance(mon, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 16 else None


def coverage(expected: dict, stage: dict | None = None) -> dict[str, int]:
    """The sections the config declared and how many entries each carries, plus the
    sidecar's entries when one was supplied — what a clean report is a claim about."""
    out: dict[str, int] = {}
    for name in _ALL_SECTIONS:
        sec = expected.get(name)
        if isinstance(sec, dict):
            n = sum(1 for k in sec if not str(k).startswith("_"))
            if n:
                out[name] = n
    if stage is not None and stage_entries(stage):
        out["stage"] = len(stage_entries(stage))
    return out


def _checked_line(checked: dict[str, int]) -> str:
    if not checked:
        return "no expected-config sections declared; nothing was checked"
    return "checked: " + " ".join(f"{k}({v})" for k, v in checked.items())


def report(findings: list[Finding], checked: dict[str, int] | None = None) -> str:
    tail = None if checked is None else _checked_line(checked)
    if not findings:
        return "PREFLIGHT OK — " + (tail or "scene matches the expected config.")
    lines = [f"  {f.severity}  {f.area:{_AREA_WIDTH}s} {f.message}" for f in findings]
    nfail = sum(1 for f in findings if f.severity == "FAIL")
    nwarn = len(findings) - nfail
    lines.append(f"\n{nfail} FAIL / {nwarn} WARN"
                 + ("" if nfail else " — warnings only, no blockers"))
    if tail:
        lines.append(tail)
    return "\n".join(lines)
