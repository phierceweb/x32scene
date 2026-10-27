"""Re-source channels from AES50 stage-box inputs through their user-in slots.

The console keeps head-amp gain and phantom per physical input, not per channel, so a move
carries the old input's ``/headamp`` line onto the new input unless told not to.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ..model import Line, Scene
from ..tables import ROUTING_BLOCKS, decode_source, routing_block_names
from .routing import input_bank, resolve_in_slot_number, uin_in_index, unwritten_in_block

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
    if (tok := unwritten_in_block(scene, slot)) is not None:
        bank = input_bank(scene)
        raise ValueError(f"ch{ch:02d} slot {slot}: /config/routing/{bank} block "
                         f"{routing_block_names(bank)[(slot - 1) // 8]} is {tok!r}, a token the "
                         "console does not write — nothing to move")
    idx = uin_in_index(scene, slot)
    if idx is None:
        raise ValueError(f"ch{ch:02d} slot {slot} is direct-routed (non-UIN routing block) — "
                         "not supported by this transform")
    uin = scene.get("/config/userrout/in")
    if uin is None or not 0 <= idx < len(uin.args):
        raise ValueError(f"userrout/in index {idx} out of range — "
                         f"malformed /config/routing/{input_bank(scene)} block?")
    return idx, _PORT_BASE[port] + aes_input, resolve_in_slot_number(scene, slot)


def _check_banks(scene: Scene) -> None:
    """A routing line that does not carry its five blocks leaves readers uncounted, so no
    move is reasoned about under one; the live bank's line is required, the other's may be
    absent."""
    for bank in ("IN", "PLAY"):
        line = scene.get(f"/config/routing/{bank}")
        if line is None and bank != input_bank(scene):
            continue
        blocks = list(line.args) if line else []
        if len(blocks) != ROUTING_BLOCKS[bank]:
            what = ("is missing" if line is None
                    else f"carries {len(blocks)} block(s), not {ROUTING_BLOCKS[bank]}")
            raise ValueError(f"/config/routing/{bank} {what} — nothing to move")


def _readers(scene: Scene) -> Iterator[tuple[str, int, str, int | None, int, int]]:
    """Every channel and aux-in under each bank: (family, number, bank, user-in index or
    None, source number, slot). ``/config/userrout/in`` serves IN and PLAY alike, so a slot's
    readers through either bank count; a bank with no routing line names none."""
    for bank in ("IN", "PLAY"):
        if scene.get(f"/config/routing/{bank}") is None:
            continue
        for fam, count in (("ch", 32), ("auxin", 8)):
            for n in range(1, count + 1):
                cfg = scene.get(f"/{fam}/{n:02d}/config")
                if cfg and cfg.args and cfg.args[-1].isdigit():
                    slot = int(cfg.args[-1])
                    yield (fam, n, bank, uin_in_index(scene, slot, bank=bank),
                           resolve_in_slot_number(scene, slot, bank=bank), slot)


def _check_batch(scene: Scene, plans: dict[int, tuple[int, int, int]], move_gain: bool) -> None:
    readers, live = list(_readers(scene)), input_bank(scene)
    rewritten = {idx for idx, new, old in plans.values() if new != old}
    live_idx = {(fam, n): i for fam, n, bank, i, _, _ in readers if bank == live}
    live_slot = {(fam, n): slot for fam, n, bank, _, _, slot in readers if bank == live}
    strips_on: dict[int, set[tuple[str, int]]] = {}
    for fam, n, _, i, _, _ in readers:
        if i is not None:
            strips_on.setdefault(i, set()).add((fam, n))

    def names(hits: list[tuple[str, int, str, int | None]]) -> str:
        """One name per strip; a reading its live slot does not cover is named by its bank."""
        banks: dict[tuple[str, int], set[str]] = {}
        for fam, n, bank, i in hits:
            covered = bank != live and i is not None and i == live_idx.get((fam, n))
            banks.setdefault((fam, n), set()).update(() if covered else (bank,))
        return ", ".join(f"{fam}{n:02d}" + ("" if bs <= {live} else
                                            f" ({'both banks' if len(bs) > 1 else bs.pop() + ' bank'})")
                         for (fam, n), bs in banks.items())

    onto: dict[int, int] = {}
    for ch, (idx, new, old) in plans.items():
        if new in onto:
            raise ValueError(f"ch{onto[new]:02d} and ch{ch:02d} both move to "
                             f"{decode_source(new)}")
        onto[new] = ch
        if new == old:
            continue   # the slot keeps its value and the head amp stays: nothing to check
        shared = [(fam, n, bank, i) for fam, n, bank, i, _, _ in readers
                  if i == idx and (fam, n) != ("ch", ch)]
        if shared:
            raise ValueError(f"ch{ch:02d} shares user-in slot {idx + 1} with "
                             f"{names(shared)}: moving one would re-source them all")
        if move_gain and _headamp(scene, old) is not None:
            # a reading survives the batch unless it goes through a user-in slot the batch
            # rewrites; a direct block, or a slot the batch leaves alone, keeps reading it
            staying = [(fam, n, bank, i) for fam, n, bank, i, src, _ in readers
                       if src == new and i not in rewritten]
            if staying:
                who = names(staying)
                # moving a strip rewrites its live slot, which ends a reading through that
                # index in either bank and no other; it needs a channel slot nobody shares
                movable = all(fam == "ch" and i is not None and i == live_idx.get((fam, n))
                              and 1 <= live_slot.get((fam, n), 0) <= 32
                              and strips_on[i] == {(fam, n)} for fam, n, _, i in staying)
                also = f"move {who} too, or " if movable else ""
                raise ValueError(
                    f"{decode_source(new)} still feeds {who}: carrying ch{ch:02d}'s head amp "
                    f"there would change the gain and phantom of {who} — {also}move "
                    f"ch{ch:02d} without carrying the gain")


def move_to_stagebox(scene: Scene, moves: Iterable[tuple[int, int]], *, port: str,
                     move_gain: bool = True) -> list[InputMove]:
    """Re-source each (channel, stage-box input 1-48) on ``port`` 'A' or 'B'.

    All-or-nothing: every move is checked before a line changes. Refused besides a bad
    channel or input: a routing line short of its blocks or a missing live-bank line, a
    channel listed twice, two channels onto one input, a user-in slot another strip reads
    through either bank, and — when gain travels — an input any strip still reads through
    either bank once the batch is applied, a batch channel included for a reading its move
    does not rewrite. A move onto the input the channel already reads changes nothing. An
    absent channel line is a KeyError. Head amps are read before any is written, so chained
    and swapped moves each carry their own.
    """
    _check_banks(scene)
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
        carried = dest is not None and old in carry and new != old
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
