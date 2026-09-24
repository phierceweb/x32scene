"""A plan's channel presets that leave a stereo-linked channel pair's processing unequal: a
load that reconciles the pair can then end at either side's."""

from __future__ import annotations

from collections.abc import Callable

from ..model import Scene
from ..services.channelfx import pair_linked
from ..services.presets import writes_beyond_sends


def unmatched_partners(scene: Scene, plan: dict,
                       read: Callable[[dict, dict], str]) -> dict[int, int]:
    """``{channel: its stereo-linked partner}`` for each plan preset that writes more than
    sends while the partner is not given the same preset and scopes; one entry per pair.
    ``read(plan, spec)`` is a channel spec's preset text."""
    presets = {int(ch): (read(plan, spec), spec.get("scopes"))
               for ch, spec in plan.get("channels", {}).items() if "preset" in spec}
    out: dict[int, int] = {}
    for ch, (text, scopes) in sorted(presets.items()):
        partner = pair_linked(scene, f"/ch/{ch:02d}")
        other = int(partner.rsplit("/", 1)[1]) if partner else None
        if (other is not None and other not in out and presets.get(other) != (text, scopes)
                and writes_beyond_sends(text, scopes)):
            out[ch] = other
    return out
