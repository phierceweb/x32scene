"""preflight family ``groups``: DCA and mute-group membership as set comparisons in both
directions over every strip that carries a /grp line, DCA scribble names, and the saved
master mute state (always on; a deliberately engaged group is declared).

Two opposite conventions meet here: /config/mute is a positional list (field 1 = group 1,
left to right) while a strip's /grp masks are read right to left. ``groups.py`` owns the
masks; this module owns the positional line.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import MUTE_GROUPS, strip_path
from .groups import GROUP_STRIPS, dca_members, dca_names, mute_members
from .preflight_config import (Finding, fail_unknown, mapping, numbered_items, spec,
                               want_str)

SECTIONS = frozenset({"groups"})
_KEYS = frozenset({"dca", "mute", "mute_engaged"})
_DCA_KEYS = frozenset({"name", "members"})
_MUTE_KEYS = frozenset({"members"})
_GROUP_SET = frozenset(GROUP_STRIPS)


def _master_mute(scene: Scene, groups: dict, out: list[Finding]) -> None:
    area, path = "mute master", "/config/mute"
    declared = groups.get("mute_engaged", [])
    if not isinstance(declared, list):
        out.append(Finding("FAIL", area, f"mute_engaged must be a list of group numbers "
                           f"1-{MUTE_GROUPS}, got {declared!r}"))
        declared = []
    engaged: set[int] = set()
    for g in declared:
        if isinstance(g, bool) or not isinstance(g, int) or not 1 <= g <= MUTE_GROUPS:
            out.append(Finding("FAIL", area, f"mute_engaged: {g!r} is not a group number "
                               f"1-{MUTE_GROUPS}"))
        else:
            engaged.add(g)
    ln = scene.get(path)
    if ln is None:
        out.append(Finding("FAIL", area, f"{path} missing — cannot verify the master mute "
                           "state", path))
        return
    if len(ln.args) != MUTE_GROUPS:
        out.append(Finding("FAIL", area, f"carries {len(ln.args)} token(s), not {MUTE_GROUPS}",
                           path))
        return
    for g, tok in enumerate(ln.args, start=1):
        if tok == "ON" and g not in engaged:
            out.append(Finding("FAIL", area, f"mute group {g} is engaged in the saved scene — "
                               "its members are silenced on recall (declare mute_engaged "
                               "to allow it)", path))
        elif g in engaged and tok != "ON":
            out.append(Finding("FAIL", area, f"mute group {g} is {tok}, expected engaged", path))


def _members(v: object, area: str, out: list[Finding]) -> tuple[set[str], bool]:
    """(canonical member paths, whether the list was usable)."""
    if not isinstance(v, list):
        out.append(Finding("FAIL", area, f"members must be a list of strips, got {v!r}"))
        return set(), False
    paths: set[str] = set()
    for m in v:
        if isinstance(m, bool) or not isinstance(m, (int, str)):
            out.append(Finding("FAIL", area, f"{m!r} is not a strip"))
            continue
        p = strip_path(m)
        if p not in _GROUP_SET:
            out.append(Finding("FAIL", area, f"{p} is not a strip that carries a /grp line"))
            continue
        paths.add(p)
    return paths, True


def _membership(scene: Scene, kind: str, groups: dict, out: list[Finding]) -> None:
    hi, keys = (8, _DCA_KEYS) if kind == "dca" else (MUTE_GROUPS, _MUTE_KEYS)
    actual = dca_members(scene) if kind == "dca" else mute_members(scene)
    names = dca_names(scene) if kind == "dca" else {}
    for n, exp in numbered_items(mapping(groups, kind, "groups", out), kind, out, lo=1, hi=hi):
        area = f"{kind} {n}"
        entry = spec(exp, area, out)
        if entry is None:
            continue
        fail_unknown(entry, keys, area, out)
        if kind == "dca":
            want = want_str(entry, "name", area, out)
            cfg = f"/dca/{n}/config"
            if want is not None and n not in names:
                out.append(Finding("FAIL", area, f"{cfg} missing — cannot verify the name", cfg))
            elif want is not None and names[n] != want:
                out.append(Finding("FAIL", area, f'name "{names[n]}" != expected "{want}"', cfg))
        if "members" not in entry:
            continue
        want_set, ok = _members(entry["members"], area, out)
        if not ok:
            continue
        unknown = [p for p in sorted(want_set) if scene.get(f"{p}/grp") is None]
        for p in unknown:
            out.append(Finding("FAIL", area, f"no {p}/grp — membership unknown", f"{p}/grp"))
        got = set(actual.get(n, []))
        missing = sorted(want_set - got - set(unknown))
        extra = sorted(got - want_set)
        if missing:
            out.append(Finding("FAIL", area, f"missing: {', '.join(missing)}", f"{missing[0]}/grp"))
        if extra:
            out.append(Finding("FAIL", area, f"extra: {', '.join(extra)}", f"{extra[0]}/grp"))


def check(scene: Scene, expected: dict, out: list[Finding]) -> None:
    groups = mapping(expected, "groups", "config", out)
    fail_unknown(groups, _KEYS, "groups", out)
    _master_mute(scene, groups, out)
    _membership(scene, "dca", groups, out)
    _membership(scene, "mute", groups, out)
