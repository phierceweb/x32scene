"""Path-level diff between two scenes: which OSC params changed."""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Scene


@dataclass
class Change:
    path: str
    before: str | None  # raw line, or None if added
    after: str | None  # raw line, or None if removed


def diff(a: Scene, b: Scene) -> list[Change]:
    """Changes turning ``a`` into ``b``, keyed by OSC path.

    Path-level, not byte-level: line order and blank lines are not compared, and a path
    occurring twice compares only its last occurrence (the model indexes last-wins, as
    the console does on load).
    """
    a_by = {ln.path: ln.raw for ln in a.lines if ln.path}
    b_by = {ln.path: ln.raw for ln in b.lines if ln.path}
    changes: list[Change] = []
    for path in sorted(set(a_by) | set(b_by)):
        before, after = a_by.get(path), b_by.get(path)
        if before != after:
            changes.append(Change(path, before, after))
    return changes
