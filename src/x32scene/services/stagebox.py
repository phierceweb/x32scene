"""Re-source channels from AES50 stage-box inputs through their user-in slots.

The console keeps head-amp gain and phantom per physical input, not per channel, so a move
carries the old input's ``/headamp`` line onto the new input unless told not to.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ..model import Line, Scene
from ..tables import decode_source
from .routing import resolve_in_slot_number, uin_in_index

_PORT_BASE = {"A": 32, "B": 80}


@dataclass(frozen=True)
class InputMove:
    """One channel re-sourced, by input source number. ``headamp`` is the new input's head
    amp (gain, phantom) once the move is applied — None when the scene has no such line —
    and ``carried`` says whether it came from the old input."""

    ch: int
    old_source: int
    new_source: int
    headamp: tuple[str, ...] | None
    carried: bool


def _headamp(scene: Scene, source: int) -> Line | None:
    return scene.get(f"/headamp/{source - 1:03d}") if 1 <= source <= 128 else None


def _plan_move(scene: Scene, ch: int, aes_input: int, port: str) -> tuple[int, int, int]:
    """Validate one stage-box move; returns (userrout index, new source, old source)."""
    if port not in _PORT_BASE:
        raise ValueError("port must be 'A' or 'B'")
    if not 1 <= aes_input <= 48:
        raise ValueError(f"ch{ch:02d}: AES50-{port} input {aes_input} is out of range 1-48")
    cfg = scene.get(f"/ch/{ch:02d}/config")
    if not cfg or not cfg.args:
        raise KeyError(f"no channel {ch}")
    slot = int(cfg.args[-1])
    if slot == 0:
        raise ValueError(f"ch{ch:02d} has no input source (OFF) — nothing to move")
    if 33 <= slot <= 40:
        raise ValueError(f"ch{ch:02d} reads aux-bank slot {slot}, not a user-in slot — "
                         "only a channel on slots 1-32 can move")
    if not 1 <= slot <= 32:
        raise ValueError(f"ch{ch:02d} source slot {slot} is out of range — nothing to move")
    idx = uin_in_index(scene, slot)
    if idx is None:
        raise ValueError(f"ch{ch:02d} slot {slot} is direct-routed (non-UIN routing block) — "
                         "not supported by this transform")
    uin = scene.get("/config/userrout/in")
    if uin is None or not 0 <= idx < len(uin.args):
        raise ValueError(f"userrout/in index {idx} out of range — "
                         "malformed /config/routing/IN block?")
    return idx, _PORT_BASE[port] + aes_input, resolve_in_slot_number(scene, slot)


def _readers(scene: Scene) -> Iterator[tuple[str, int, int | None, int]]:
    """Every channel and aux-in: (family, number, user-in index or None, source number)."""
    for fam, count in (("ch", 32), ("auxin", 8)):
        for n in range(1, count + 1):
            cfg = scene.get(f"/{fam}/{n:02d}/config")
            if cfg and cfg.args and cfg.args[-1].isdigit():
                slot = int(cfg.args[-1])
                yield fam, n, uin_in_index(scene, slot), resolve_in_slot_number(scene, slot)


def _check_batch(scene: Scene, plans: dict[int, tuple[int, int, int]], move_gain: bool) -> None:
    readers = list(_readers(scene))
    onto: dict[int, int] = {}
    for ch, (idx, new, old) in plans.items():
        if new in onto:
            raise ValueError(f"ch{onto[new]:02d} and ch{ch:02d} both move to "
                             f"{decode_source(new)}")
        onto[new] = ch
        shared = [f"{fam}{n:02d}" for fam, n, i, _ in readers
                  if i == idx and (fam, n) != ("ch", ch)]
        if shared:
            raise ValueError(f"ch{ch:02d} shares user-in slot {idx + 1} with "
                             f"{', '.join(shared)}: moving one would re-source them all")
        if move_gain and _headamp(scene, old) is not None:
            staying = [(fam, n, i) for fam, n, i, src in readers
                       if src == new and not (fam == "ch" and n in plans)]
            if staying:
                names = ", ".join(f"{fam}{n:02d}" for fam, n, _ in staying)
                # only a channel on a user-in slot is something this batch could also move
                also = (f"move {names} too, or " if all(fam == "ch" and i is not None
                                                        for fam, _, i in staying) else "")
                raise ValueError(
                    f"{decode_source(new)} still feeds {names}: carrying ch{ch:02d}'s head "
                    f"amp there would change {names}'s gain and phantom — {also}move "
                    f"ch{ch:02d} without carrying the gain")


def move_to_stagebox(scene: Scene, moves: Iterable[tuple[int, int]], *, port: str,
                     move_gain: bool = True) -> list[InputMove]:
    """Re-source each (channel, stage-box input 1-48) on ``port`` 'A' or 'B'.

    All-or-nothing: every move is checked before a line changes. Refused besides a bad
    channel or input: a channel listed twice, two channels onto one input, a user-in slot
    another channel or aux-in also reads, and — when gain travels — an input a channel or
    aux-in outside the batch still reads. An absent channel line is a KeyError. Head amps
    are read before any is written, so chained and swapped moves each carry their own.
    """
    plans: dict[int, tuple[int, int, int]] = {}
    for ch, aes_input in moves:
        if ch in plans:
            raise ValueError(f"ch{ch:02d} is listed twice")
        plans[ch] = _plan_move(scene, ch, aes_input, port)
    _check_batch(scene, plans, move_gain)
    carry = {old: list(ln.args) for _, _, old in plans.values()
             if move_gain and (ln := _headamp(scene, old)) is not None}
    uin = scene.get("/config/userrout/in")
    done = []
    for ch, (idx, new, old) in plans.items():
        uin.set_arg(idx, str(new))
        dest = _headamp(scene, new)
        carried = dest is not None and old in carry
        if carried and dest.args != carry[old]:
            dest.args = list(carry[old])
            dest.rebuild()
        done.append(InputMove(ch, old, new, tuple(dest.args) if dest else None, carried))
    return done


def move_input_to_stagebox(scene: Scene, ch: int, aes_input: int, *, port: str = "A",
                           move_gain: bool = True) -> None:
    """Re-source one channel from an AES50 stage-box input (1-48); see move_to_stagebox."""
    move_to_stagebox(scene, [(ch, aes_input)], port=port, move_gain=move_gain)


def move_inputs_to_stagebox(scene: Scene, mapping: dict[int, int], *, port: str = "A",
                            move_gain: bool = True) -> int:
    """Batch move: mapping = {channel: aes_input_number}. Returns channels moved."""
    return len(move_to_stagebox(scene, mapping.items(), port=port, move_gain=move_gain))
