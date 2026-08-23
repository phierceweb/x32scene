"""Monitor-mix (IEM) sends: read-modify-write of ``<strip>/mix/<bus>`` lines.

The console mirrors a send across two stereo links — the bus pair and the strip pair — and
reverts a one-sided write on recall, so an edit here is a set of lines, not one line.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..model import Scene
from ..tables import SEND_STRIPS, send_line_fields, strip_path
from .channelfx import link_line, pair_linked
from .transforms import fmt_level

_SEND_STRIP_SET = frozenset(SEND_STRIPS)
_SEND_PATH = re.compile(r"/mix/(\d\d)$")


def _bus_path(n: int) -> str:
    return f"/bus/{n:02d}"


def send_strip_path(strip: int | str) -> str:
    """The path of a strip that can feed a monitor bus, or raise. Buses and matrices carry
    ``/mix/`` lines too, but those are bus->matrix sends, not monitor sends."""
    path = strip_path(strip)
    if path not in _SEND_STRIP_SET:
        raise ValueError(f"{path} is not a send strip (channel, /auxin/NN or /fxrtn/NN)")
    return path


def set_iem_send(scene: Scene, strip: int | str, bus: int, *, on: bool | None = None,
                 level_db: float | None = None) -> None:
    """Set one strip's send to a monitor bus (``/ch/NN/mix/MM``). Aux-ins and FX returns
    feed ears too, so ``strip`` takes any send strip, not only a channel number."""
    path = send_strip_path(strip)
    line = scene.get(f"{path}/mix/{bus:02d}")
    if line is None:
        raise KeyError(f"no send {path}->bus{bus}")
    if on is not None:
        line.set_arg(0, "ON" if on else "OFF")
    if level_db is not None:
        line.set_arg(1, fmt_level(level_db))


def send_shape_errors(scene: Scene, paths: Iterable[str]) -> list[str]:
    """Which of ``paths`` are send lines whose field count contradicts their bus.

    Round-trip and a path-level diff are both blind to this: the bytes still match and the
    path is unchanged, while the token view shifts and the desk reads the wrong field.
    """
    bad = []
    for path in paths:
        m = _SEND_PATH.search(path)
        line = scene.get(path) if m else None
        if line is None:
            continue
        want = send_line_fields(int(m.group(1)))
        if len(line.args) != want:
            bad.append(f"{path} carries {len(line.args)} field(s), not {want}")
    return bad


def _bus_linked(scene: Scene, bus: int) -> bool:
    return pair_linked(scene, _bus_path(bus)) is not None


def bus_link_group(scene: Scene, bus: int) -> tuple[int, ...]:
    """The buses one monitor send must be written to together — both sides of a
    stereo-linked pair, else just ``bus``."""
    if scene.get("/config/buslink") is None:
        # absent, every pair would read as unlinked and every write go out one-sided
        raise KeyError("no /config/buslink: cannot tell stereo bus pairs apart")
    if not _bus_linked(scene, bus):
        return (bus,)
    odd = bus if bus % 2 else bus - 1
    return (odd, odd + 1)


def iem_send_targets(scene: Scene, strip: int | str, bus: int, *,
                     linked: bool | None = None) -> list[tuple[str, int]]:
    """Every send line one monitor-send edit must write together, ``(strip path, bus)``.

    ``linked=False`` confines the edit to the named strip; the bus pair still mirrors,
    since that axis is the send itself.

    The strip axis ignores ``/config/linkcfg``: which preference governs sends is unconfirmed.
    """
    path = send_strip_path(strip)
    partner = None
    if linked is not False:
        cfg = link_line(path)
        if cfg is not None and scene.get(cfg) is None:
            raise KeyError(f"no {cfg}: cannot tell stereo strip pairs apart")
        partner = pair_linked(scene, path)
        if partner is not None and partner not in _SEND_STRIP_SET:
            partner = None
    paths = [path] + ([partner] if partner else [])
    return [(p, b) for p in paths for b in bus_link_group(scene, bus)]


def copy_iem_dst_buses(scene: Scene, src_bus: int, dst_bus: int, *,
                       stereo: bool | None = None) -> tuple[int, ...]:
    """The destination buses :func:`copy_iem_mix` writes, for a caller that has to
    whitelist exactly them."""
    return tuple(db for _, db in _copy_bus_pairs(scene, src_bus, dst_bus, stereo))


def _group(scene: Scene, bus: int, stereo: bool | None) -> tuple[int, ...]:
    if stereo is False:
        return (bus,)
    if stereo is None:
        return bus_link_group(scene, bus)
    odd = bus if bus % 2 else bus - 1
    return (odd, odd + 1)


def _copy_bus_pairs(scene: Scene, src_bus: int, dst_bus: int,
                    stereo: bool | None) -> tuple[tuple[int, int], ...]:
    """``(source bus, destination bus)`` pairs one copy writes.

    What the console reverts is the DESTINATION pair, so a linked destination is always
    written on both sides — from the matching side of a linked source, or twice over from
    a mono one.
    """
    src_g, dst_g = _group(scene, src_bus, stereo), _group(scene, dst_bus, stereo)
    if len(src_g) == len(dst_g):
        return tuple(zip(src_g, dst_g, strict=True))   # L->L, R->R, whichever side was named
    if len(dst_g) == 2:
        return tuple((src_bus, d) for d in dst_g)
    return ((src_bus, dst_bus),)


def copy_iem_mix(scene: Scene, src_bus: int, dst_bus: int, *, stereo: bool | None = None) -> int:
    """Copy every strip's send from one monitor bus to another. Returns lines changed.

    Both sides of a stereo-linked destination are written, else the console's link reverts
    one on recall. ``stereo`` overrides the auto-detection.

    Only the fields both lines carry are copied, so a copy across bus parity moves on/level
    without disturbing the destination's pan and tap point (:func:`send_line_fields`).
    """
    if src_bus == dst_bus:
        raise ValueError(f"copy source and destination are both bus {src_bus}")
    changed = 0
    for sb, db in _copy_bus_pairs(scene, src_bus, dst_bus, stereo):
        if sb == db:
            continue
        for strip in SEND_STRIPS:
            s = scene.get(f"{strip}/mix/{sb:02d}")
            d = scene.get(f"{strip}/mix/{db:02d}")
            if s is None or d is None:
                continue
            before = list(d.args)
            for i in range(min(len(s.args), len(d.args))):
                d.set_arg(i, s.args[i])
            changed += d.args != before
    return changed
