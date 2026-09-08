"""Plan-schema constants and validation for the band-swap orchestrator.

Every guard here exists to make a typo'd plan raise rather than silently do nothing, or
the opposite of what it says. A plan is validated whole, before any line is written.
"""

from __future__ import annotations

from ..services import transforms as T
from ..services.scopes import SCOPES
from ..tables import SEND_STRIPS, strip_path
from . import _sections
from ._sections import _numbered_key


PLAN_KEYS = {"title", "channels", "dca", "iem_copy", "iem_sends", "outputs", "fx", "routing",
             "output_patch"}
IEM_SEND_KEYS = {"strip", "bus", "level", "on"}
IEM_COPY_KEYS = {"src", "dst"}
CHANNEL_KEYS = {"name", "preset", "scopes", "gain_db", "phantom", "fader", "mute",
                *_sections.CHANNEL_PROC_KEYS}
_SEND_STRIP_SET = frozenset(SEND_STRIPS)


def _is_number(v: object) -> bool:
    # bool passes isinstance(int), so True would otherwise read as the level 1.0
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_index(v: object, lo: int, hi: int) -> bool:
    """A whole number naming a bus, channel or output — not a bool, not 3.0."""
    return _is_number(v) and not isinstance(v, float) and lo <= v <= hi


def _mapping(plan: dict, key: str) -> dict:
    """A plan section that must be a JSON object. Unguarded, a list or string reaches
    ``.items()`` and raises AttributeError, which escapes the CLI's boundary as a
    traceback instead of "plan failed, nothing written"."""
    section = plan.get(key, {})
    if not isinstance(section, dict):
        raise ValueError(f"{key} must be an object, got {type(section).__name__}")
    return section


def _records(plan: dict, key: str) -> list:
    section = plan.get(key, [])
    if not isinstance(section, list):
        raise ValueError(f"{key} must be a list of records, got {type(section).__name__}")
    return section


def _valid_fader(v: object) -> bool:
    return v in ("-oo", "oo") or (_is_number(v) and T.LEVEL_MIN_DB <= v <= T.LEVEL_MAX_DB)


def _valid_send_level(v: object) -> bool:
    """A send level. Unlike a fader this refuses "oo": someone typing the unsigned
    spelling into a monitor mix means "open", and it would silently kill the send."""
    return v == "-oo" or (_is_number(v) and T.LEVEL_MIN_DB <= v <= T.LEVEL_MAX_DB)


def _send_strip(v: object) -> str | None:
    """The strip path an iem_sends record names, or None if it names no send strip."""
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        return None
    path = strip_path(v)
    return path if path in _SEND_STRIP_SET else None


def validate_plan(plan: dict) -> None:
    """Reject a plan that would silently do nothing — or the opposite of what it says. A
    typo'd key, scope, bus or channel, a mistyped fader/mute value, and a DCA member list
    that is not a list of channel numbers, all raise here."""
    if not isinstance(plan, dict):
        raise ValueError(f"plan must be an object, got {type(plan).__name__}")
    unknown = [k for k in plan if k not in PLAN_KEYS and not k.startswith("_")]
    if unknown:
        raise ValueError(f"unknown plan key(s): {', '.join(sorted(unknown))}")
    if "title" in plan and not isinstance(plan["title"], str):
        # unchecked, a list reaches the scene header through repr()
        raise ValueError(f"title must be a string, got {plan['title']!r}")
    _validate_channels(plan)
    _validate_dca(plan)
    _validate_copies(plan)
    _validate_outputs(plan)
    _validate_sends(plan)
    _sections.validate_fx(plan)
    _sections.validate_routing(plan)
    _sections.validate_output_patch(plan)


def _validate_channels(plan: dict) -> None:
    seen: dict[int, object] = {}
    for ch_s, spec in _mapping(plan, "channels").items():
        ch = _numbered_key("channels", ch_s, 1, 32, seen)
        if not isinstance(spec, dict):
            raise ValueError(f"channel {ch}: must be an object, got {type(spec).__name__}")
        bad = [k for k in spec if k not in CHANNEL_KEYS]
        if bad:
            raise ValueError(f"channel {ch}: unknown key(s): {', '.join(sorted(bad))}")
        for key in ("name", "preset"):
            if key in spec and not isinstance(spec[key], str):
                raise ValueError(f"channel {ch}: {key} must be a string, got {spec[key]!r}")
        if "scopes" in spec and not isinstance(spec["scopes"], list):
            raise ValueError(f"channel {ch}: scopes must be a list, "
                             f"got {type(spec['scopes']).__name__}")
        for sc in spec.get("scopes") or []:
            if sc not in SCOPES:
                raise ValueError(f"channel {ch}: unknown scope {sc!r} "
                                 f"(valid: {', '.join(SCOPES)})")
        # "false" is truthy, so an unchecked mute value would mute the channel it names
        for key in ("mute", "phantom"):
            if key in spec and not isinstance(spec[key], bool):
                raise ValueError(f"channel {ch}: {key} must be true or false, "
                                 f"got {spec[key]!r}")
        if "fader" in spec and not _valid_fader(spec["fader"]):
            raise ValueError(f"channel {ch}: fader must be {T.LEVEL_MIN_DB:g}.."
                             f'{T.LEVEL_MAX_DB:+g} dB or "-oo"/"oo" (synonyms here), '
                             f"got {spec['fader']!r}")
        if "gain_db" in spec and not (_is_number(spec["gain_db"])
                                      and T.HEADAMP_MIN_DB <= spec["gain_db"] <= T.HEADAMP_MAX_DB):
            raise ValueError(f"channel {ch}: gain_db must be {T.HEADAMP_MIN_DB:g}.."
                             f"{T.HEADAMP_MAX_DB:+g} dB, got {spec['gain_db']!r}")
        _sections.validate_channel_proc(ch, spec)


def _validate_dca(plan: dict) -> None:
    seen: dict[int, object] = {}
    for dca_s, members in _mapping(plan, "dca").items():
        d = _numbered_key("dca", dca_s, 1, 8, seen)
        # a plan names a DCA's WHOLE membership: an unreadable list empties the group
        if not isinstance(members, list):
            raise ValueError(f"dca {d}: members must be a list of channel numbers 1-32, "
                             f"got {type(members).__name__}")
        for m in members:
            if not _is_index(m, 1, 32):
                raise ValueError(f"dca {d}: {m!r} is not a channel number 1-32")


def _validate_copies(plan: dict) -> None:
    for cp in _records(plan, "iem_copy"):
        if not isinstance(cp, dict):
            raise ValueError(f"iem_copy: each record must be an object, got {cp!r}")
        bad = [k for k in cp if k not in IEM_COPY_KEYS]
        if bad:
            raise ValueError(f"iem_copy: unknown key(s): {', '.join(sorted(bad))}")
        for side in ("src", "dst"):
            if side not in cp:
                raise ValueError(f"iem_copy: a record needs both src and dst, missing {side}")
            if not _is_index(cp[side], 1, 16):
                raise ValueError(f"iem_copy: {side} must be a bus 1-16, got {cp[side]!r}")
        if cp["src"] == cp["dst"]:
            raise ValueError(f"iem_copy: src and dst are both bus {cp['src']}")


def _validate_outputs(plan: dict) -> None:
    seen: dict[int, object] = {}
    for out_s, bus in _mapping(plan, "outputs").items():
        out = _numbered_key("outputs", out_s, 1, 16, seen)
        if not _is_index(bus, 1, 16):
            raise ValueError(f"outputs: output {out} must name a bus 1-16, got {bus!r}")


def _validate_sends(plan: dict) -> None:
    seen: set[tuple[str, int]] = set()
    for rec in _records(plan, "iem_sends"):
        if not isinstance(rec, dict):
            raise ValueError(f"iem_sends: each record must be an object, got {rec!r}")
        bad = [k for k in rec if k not in IEM_SEND_KEYS]
        if bad:
            raise ValueError(f"iem_sends: unknown key(s): {', '.join(sorted(bad))}")
        path = _send_strip(rec.get("strip"))
        if path is None:
            raise ValueError('iem_sends: strip must be a channel 1-32 or a send strip path '
                             f'like "/auxin/05", got {rec.get("strip")!r}')
        bus = rec.get("bus")
        if not _is_index(bus, 1, 16):
            raise ValueError(f"iem_sends: {path}: bus must be 1-16, got {bus!r}")
        where = f"iem_sends: {path} -> bus {bus}"
        if "level" not in rec and "on" not in rec:
            raise ValueError(f"{where}: needs a level and/or on, or it does nothing")
        if "on" in rec and not isinstance(rec["on"], bool):
            raise ValueError(f"{where}: on must be true or false, got {rec['on']!r}")
        if "level" in rec and not _valid_send_level(rec["level"]):
            raise ValueError(f"{where}: level must be {T.LEVEL_MIN_DB:g}.."
                             f'{T.LEVEL_MAX_DB:+g} dB or "-oo", got {rec["level"]!r}')
        # an OFF send keeps a stored level that `x32scene iem` does not show, so turning one
        # on blind can drop a strip into someone's ears at an unknown level
        if rec.get("on") is True and "level" not in rec:
            raise ValueError(f"{where}: on:true needs a level too")
        if (path, bus) in seen:
            raise ValueError(f"{where}: set twice")
        seen.add((path, bus))

