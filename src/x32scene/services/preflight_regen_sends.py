"""The ``sends`` section of a regenerated config: per odd bus the tap with the fewest
``except`` rules, and per bus who sends live and who does not."""

from __future__ import annotations

from collections import Counter

from ..model import Scene
from ..tables import SEND_STRIPS, send_is_live
from . import preflight_sends

__all__ = ["sends"]


def _majority(taps: list[str]) -> str:
    counts = Counter(taps)
    return min(counts, key=lambda t: (-counts[t], t))


def _rules_under(tap: str, taps: dict[str, str]) -> dict[str, str]:
    """A family rule only where it saves rules, then each strip that still disagrees."""
    rules: dict[str, str] = {}
    for fam in preflight_sends._FAMILIES:
        own = [t for s, t in taps.items() if s.rpartition("/")[0] == fam]
        others = [t for t in own if t != tap]
        if others:
            alt = _majority(others)
            if 1 + sum(t != alt for t in own) < len(others):
                rules[fam] = alt
    for strip, t in taps.items():
        if t != rules.get(strip.rpartition("/")[0], tap):
            rules[strip] = t
    return rules


def _tap_rules(taps: dict[str, str]) -> dict:
    """The bus tap with the fewest except rules; a tie goes to the commoner tap."""
    counts = Counter(taps.values())
    tap = min(counts, key=lambda t: (len(_rules_under(t, taps)), -counts[t], t))
    rules = _rules_under(tap, taps)
    return {"tap": tap, "except": rules} if rules else {"tap": tap}


def sends(scene: Scene) -> dict:
    out = {}
    for bus in range(1, 17):
        lines = {s: scene.get(f"{s}/mix/{bus:02d}") for s in SEND_STRIPS}
        entry: dict = {}
        if bus % 2 and all(lines.values()):
            taps = {s: ln.args[3] for s, ln in lines.items() if len(ln.args) >= 4}
            if taps:
                entry.update(_tap_rules(taps))
        if any(lines.values()):
            entry["present"] = [s for s, ln in lines.items() if ln and send_is_live(ln.args)]
            entry["absent"] = [s for s, ln in lines.items() if ln and not send_is_live(ln.args)]
        out[str(bus)] = entry
    return out
