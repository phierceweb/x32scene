"""Transplant: carry chosen lines from one scene into another and touch nothing else —
a monitor bus with every send that feeds it, any path pattern, or a channel's sections
(head amp re-mapped as a preset load would). The read side of a "one aux from that
night, everything else from this one" scene."""

from __future__ import annotations

import fnmatch

from ..model import Line, Scene
from ..tables import SEND_STRIPS
from .iem import bus_link_group
from .presets import apply_preset, extract_preset


def bus_mix_paths(scene: Scene, bus: int) -> list[str]:
    """Every path that makes up one monitor mix: the bus strip's own lines and each
    sender's send to it, for both sides of a linked pair."""
    if not 1 <= bus <= 16:
        raise ValueError(f"bus must be 1-16, got {bus}")
    paths: list[str] = []
    for b in bus_link_group(scene, bus):
        strip = f"/bus/{b:02d}"
        paths += [ln.path for ln in scene.lines if ln.path == strip or ln.path.startswith(strip + "/")]
        paths += [f"{s}/mix/{b:02d}" for s in SEND_STRIPS if scene.get(f"{s}/mix/{b:02d}") is not None]
    return paths


def glob_paths(scene: Scene, patterns: list[str]) -> list[str]:
    """The scene's paths matching any shell-style pattern (``/ch/0[1-4]/eq/*``)."""
    return [ln.path for ln in scene.lines
            if ln.path and any(fnmatch.fnmatchcase(ln.path, p) for p in patterns)]


def _take(dst: Line, src: Line) -> bool:
    if dst.raw == src.raw:
        return False
    dst.args = list(src.args)
    dst.raw = src.raw
    dst.dirty = True
    return True


def transplant(src: Scene, dst: Scene, *, buses: list[int] = (), globs: list[str] = (),
               channels: list[int] = (), scopes: list[str] | None = None) -> list[str]:
    """Copy lines from ``src`` into ``dst`` in place; returns the paths that changed.
    A path ``src`` has and ``dst`` lacks is an error, not a silent skip."""
    wanted: list[str] = []
    for bus in buses:
        wanted += bus_mix_paths(src, bus)
    wanted += glob_paths(src, list(globs))
    changed: list[str] = []
    seen: set[str] = set()
    for path in wanted:
        if path in seen:
            continue
        seen.add(path)
        s, d = src.get(path), dst.get(path)
        if s is None or d is None:
            raise KeyError(f"{path}: not in {'source' if s is None else 'destination'} scene")
        if _take(d, s):
            changed.append(path)
    for ch in channels:
        before = {ln.path: ln.raw for ln in dst.lines}
        apply_preset(dst, ch, extract_preset(src, ch, scopes), scopes)
        changed += [ln.path for ln in dst.lines if before.get(ln.path) != ln.raw
                    and ln.path not in changed]
    dst._reindex()
    return changed
