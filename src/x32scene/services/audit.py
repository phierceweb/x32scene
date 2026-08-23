"""Verify scene-format assumptions across an entire scene library.

Asserts the structural invariants every X32 scene should satisfy, then surfaces drift
(routing topology, recording patch) chronologically across the library — useful for
spotting when a rig was repatched.
"""

from __future__ import annotations

import glob
import os
import re

from ..model import HEADER_RE, Scene


def _datekey(path: str) -> tuple[str, str]:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    return (m.group(1) if m else "0000-00-00", os.path.basename(path))


def load_library(scenes_dir: str) -> tuple[list[tuple[str, Scene]], list[str]]:
    """(loaded scenes, per-file load errors) — one bad file must not abort the audit."""
    paths = sorted(glob.glob(os.path.join(scenes_dir, "*.scn")), key=_datekey)
    out: list[tuple[str, Scene]] = []
    errors: list[str] = []
    for p in paths:
        try:
            out.append((os.path.basename(p), Scene.load(p)))
        except ValueError as e:
            errors.append(f"{os.path.basename(p)}: {e}")
    return out, errors


def check_invariants(lib: list[tuple[str, Scene]]) -> list[str]:
    """Return a list of assumption violations (empty == all assumptions hold).

    Line count is checked for *agreement across the library*, not against a fixed
    number: it varies with console model and firmware, so an outlier is the signal.
    """
    viol: list[str] = []
    for name, sc in lib:
        if not sc.lines:
            viol.append(f"{name}: empty scene file")
            continue
        h = sc.lines[0]
        if not HEADER_RE.match(h.path):
            viol.append(f"{name}: no firmware header")
        if len(h.raw) != 127:
            viol.append(f"{name}: header width {len(h.raw)} != 127")
        nch = sum(1 for ln in sc.find("/ch/") if ln.path.endswith("/config"))
        nha = len(sc.find("/headamp/"))
        nbus = sum(1 for ln in sc.find("/bus/") if ln.path.endswith("/config"))
        if (nch, nha, nbus) != (32, 128, 16):
            viol.append(f"{name}: ch/ha/bus={nch}/{nha}/{nbus} != 32/128/16")
    counts: dict[int, list[str]] = {}
    for name, sc in lib:
        counts.setdefault(len(sc.lines), []).append(name)
    if len(counts) > 1:
        common = max(counts, key=lambda k: len(counts[k]))
        for n, names in sorted(counts.items()):
            if n != common:
                for name in names:
                    viol.append(f"{name}: {n} lines, library majority is {common}")
    return viol


def _sig_changes(lib, keyfn):
    """Yield (name, value) only when keyfn's value changes down the chronology."""
    last = object()
    for name, sc in lib:
        v = keyfn(sc)
        if v != last:
            yield name, v
            last = v


def report(lib: list[tuple[str, Scene]], scenes_dir: str,
           load_errors: list[str] | None = None) -> str:
    out = [f"### {len(lib)} scenes in {scenes_dir}\n"]

    out.append("## Structural invariants")
    viol = list(load_errors or []) + check_invariants(lib)
    out.append("  ALL OK" if not viol else "\n".join("  " + v for v in viol))

    out.append("\n## AES50 routing topology (chronological; stage-box footprint)")
    def aes_sig(sc):
        return tuple(
            tuple(sc.get(k).args) if sc.get(k) else ()
            for k in ("/config/routing/IN", "/config/routing/AES50A", "/config/routing/AES50B")
        )
    for name, sig in _sig_changes(lib, aes_sig):
        out.append(f"  [{name}]")
        out.append(f"    IN     {' '.join(sig[0])}")
        out.append(f"    AES50A {' '.join(sig[1])}")
        out.append(f"    AES50B {' '.join(sig[2])}")

    out.append("\n## Recording patch /config/userrout/out (chronological)")
    def rec_sig(sc):
        ln = sc.get("/config/userrout/out")
        return tuple(ln.args) if ln else ()
    for name, sig in _sig_changes(lib, rec_sig):
        nz = [x for x in sig if x != "0"]
        out.append(f"  [{name}] {' '.join(nz)}")

    return "\n".join(out)
