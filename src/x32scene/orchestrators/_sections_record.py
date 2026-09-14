"""The record section of a band-setup plan: USB card record tracks by source words. It is
applied after ``routing``, so a track resolves through the plan's own CARD blocks."""

from __future__ import annotations

from ..model import Scene
from ..services import routing_edit as _rt
from ..services.routing import record_map
from ._sections import _numbered_key

RECORD_PATH = "/config/userrout/out"


def validate_record(plan: dict) -> None:
    spec = plan.get("record", {})
    if not isinstance(spec, dict):
        raise ValueError("record must be an object mapping track numbers to sources, "
                         f"got {type(spec).__name__}")
    seen: dict = {}
    for track_s, source in spec.items():
        track = _numbered_key("record", track_s, 1, 32, seen)
        where = f"record track {track}"
        if isinstance(source, bool) or not isinstance(source, (str, int)):
            raise ValueError(f'{where}: source must be words like "Output 9" or a number '
                             f"0-208, got {source!r}")
        try:
            _rt.encode_out_source(source)
        except ValueError as e:
            raise ValueError(f"{where}: {e}") from None


def apply_record(scene: Scene, plan: dict, recorded: dict[int, str] | None = None) -> list[dict]:
    """Resolve every track before writing any, so a refused track leaves the line as it was.
    Returns a ``routing_edit.record_row`` per track, in track order; ``recorded`` is each
    track's source before the plan (``record_map`` of the template), else the scene's now."""
    by_slot: dict[int, tuple[int, int]] = {}
    tracks = sorted((int(t), s) for t, s in plan.get("record", {}).items())
    for track, source in tracks:
        slot, num = _rt.record_slot(scene, track), _rt.encode_out_source(source)
        other, other_num = by_slot.setdefault(slot, (track, num))
        if other_num != num:
            raise ValueError(f"record: tracks {other} and {track} both read user-out slot "
                             f"{slot} and name different sources")
    before = dict(record_map(scene)) if recorded is None else recorded
    for track, source in tracks:
        _rt.set_record(scene, track, source)
    return [_rt.record_row(scene, track, before[track]) for track, _ in tracks]


def allowed_record(plan: dict) -> set[str]:
    return {RECORD_PATH} if plan.get("record") else set()
