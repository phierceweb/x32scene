"""DCA and mute-group membership. ``<strip>/grp <dca-mask %8> <mute-mask %6>``, LSB = group 1.

Masks are X32 '%' bitstrings (e.g. %00000100 = DCA 3). Bit i (from the right) = group i+1.
Channels are not the only members: aux-ins, FX returns, buses, matrices and the mains all
carry a /grp line, so membership is reported and edited by strip path.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import strip_path as _strip

# Strip families carrying a /grp line, in console order. (/config/dp48/grp is a P16
# config line, not a strip.)
GROUP_STRIPS = (
    [f"/ch/{n:02d}" for n in range(1, 33)]
    + [f"/auxin/{n:02d}" for n in range(1, 9)]
    + [f"/fxrtn/{n:02d}" for n in range(1, 9)]
    + [f"/bus/{n:02d}" for n in range(1, 17)]
    + [f"/mtx/{n:02d}" for n in range(1, 7)]
    + ["/main/st", "/main/m"]
)


def _bit_set(mask: str, group: int) -> bool:
    bits = mask.lstrip("%")
    # rightmost char = group 1
    return len(bits) >= group and bits[-group] == "1"


def _set_bit(mask: str, group: int, on: bool) -> str:
    bits = list(mask.lstrip("%"))
    bits[-group] = "1" if on else "0"
    return "%" + "".join(bits)


def _members(scene: Scene, arg: int, count: int) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {g: [] for g in range(1, count + 1)}
    for path in GROUP_STRIPS:
        ln = scene.get(f"{path}/grp")
        if not ln or len(ln.args) <= arg:
            continue
        for g in range(1, count + 1):
            if _bit_set(ln.args[arg], g):
                out[g].append(path)
    return out


def dca_members(scene: Scene) -> dict[int, list[str]]:
    """{dca_number: [strip path, ...]} for DCAs 1-8."""
    return _members(scene, 0, 8)


def dca_names(scene: Scene) -> dict[int, str]:
    """{dca_number: scribble name} for DCAs 1-8 ('' when unnamed)."""
    names = {}
    for n in range(1, 9):
        ln = scene.get(f"/dca/{n}/config")
        if ln is not None:
            names[n] = ln.args[0].strip('"') if ln.args else ""
    return names


def mute_members(scene: Scene) -> dict[int, list[str]]:
    """{mute_group: [strip path, ...]} for mute groups 1-6."""
    return _members(scene, 1, 6)


def _set_group(scene: Scene, strip: int | str, arg: int, group: int, on: bool) -> None:
    ln = scene.get(f"{_strip(strip)}/grp")
    if not ln:
        raise KeyError(f"no {_strip(strip)}/grp")
    ln.set_arg(arg, _set_bit(ln.args[arg], group, on))


def set_dca(scene: Scene, strip: int | str, dca: int, on: bool = True) -> None:
    """Add/remove a strip to/from a DCA group (1-8)."""
    if not 1 <= dca <= 8:
        raise ValueError("dca must be 1-8")
    _set_group(scene, strip, 0, dca, on)


def set_mute_group(scene: Scene, strip: int | str, group: int, on: bool = True) -> None:
    """Add/remove a strip to/from a mute group (1-6)."""
    if not 1 <= group <= 6:
        raise ValueError("mute group must be 1-6")
    _set_group(scene, strip, 1, group, on)
