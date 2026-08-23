"""One path's timeline across a scene library: the line each time it changes."""

from __future__ import annotations

from ..model import Scene


def history(lib: list[tuple[str, Scene]], path: str) -> list[tuple[str, str | None]]:
    """``(scene name, raw line)`` for each scene where ``path`` differs from the one
    before, over ``lib`` in the order given; None when the line is absent. Empty when no
    scene in the library carries the path."""
    out: list[tuple[str, str | None]] = []
    last: object = object()
    for name, scene in lib:
        ln = scene.get(path)
        raw = ln.raw if ln else None
        if raw != last:
            out.append((name, raw))
            last = raw
    return out if any(raw is not None for _, raw in out) else []
