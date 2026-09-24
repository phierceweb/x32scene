"""Resolve X32 routing: channel input sources and the USB-card record map.

Two indirections this module untangles, both keyed by 8-wide blocks:

1. **Channel input.** ``/ch/NN/config`` ends with a source slot. Its block in
   ``/config/routing/IN`` is either ``UINk`` (look the slot up in
   ``/config/userrout/in``) or a direct domain (``ANk``/``Ak``/``Bk``/``CARDk``/``AUXk``).

2. **USB record map.** Each block in ``/config/routing/CARD`` names where 8 card sends
   come from — ``UOUTk`` dereferences ``/config/userrout/out``, decoded with the *output*
   enum. The result is the 32 tracks the DAW receives, in order.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..model import Scene
from ..tables import (AUX_BANK_USB, OUTPUT_BANKS, decode_out_source, decode_source,
                      routing_block_names, routing_vocab, tap_to_bus, userrout_out_to_output)


def userrout(scene: Scene, which: str) -> list[int]:
    """The /config/userrout/in (32) or /out (48) slot values; [] when the line is absent."""
    ln = scene.get(f"/config/userrout/{which}")
    return [int(x) for x in ln.args] if ln else []


def routing_blocks(scene: Scene, key: str) -> list[str]:
    """The block tokens on /config/routing/<key>; [] when the line is absent."""
    ln = scene.get(f"/config/routing/{key}")
    return list(ln.args) if ln else []


def _block(tok: str) -> tuple[str, int]:
    """A routing token's (prefix, first number): 'UOUT9-16' -> ('UOUT', 9)."""
    prefix = tok.rstrip("0123456789-")
    digits = "".join(c for c in tok.split("-")[0] if c.isdigit())
    return prefix, (int(digits) if digits else 1)


def uout_start(key: str, *, block: int, tok: str) -> int | None:
    """The first user-out slot of a UOUT token at 0-based block ``block`` of
    ``/config/routing/<key>``; None for another token, or a UOUT one the console does not
    write there (``UOUT``, ``UOUT0-7``)."""
    names = routing_block_names(key)
    if (not tok.startswith("UOUT") or block >= len(names)
            or tok not in routing_vocab(key, names[block])):
        return None
    return int(tok[4:].split("-")[0])


def _in_blocks(scene: Scene) -> list[str]:
    return routing_blocks(scene, "IN")


def unwritten_in_block(scene: Scene, slot: int) -> str | None:
    """The ``/config/routing/IN`` token input ``slot`` reads through when the console does
    not write it at that block (``UIN``, ``UIN0-7``, ``A0-7``): such a slot has no source.
    None for a written token, or a block the line does not reach."""
    blocks, b = _in_blocks(scene), (slot - 1) // 8
    if not 1 <= slot <= 40 or b >= len(blocks):
        return None
    tok = blocks[b]
    return None if tok in routing_vocab("IN", routing_block_names("IN")[b]) else tok


def uin_in_index(scene: Scene, slot: int) -> int | None:
    """0-based /config/userrout/in index feeding ``slot``, honoring the UIN block's own
    range (``UIN9-16`` on bank 0 maps slot 1 -> index 8). None for a non-UIN block."""
    if not 1 <= slot <= 40 or unwritten_in_block(scene, slot) is not None:
        return None
    blocks = _in_blocks(scene)
    b = (slot - 1) // 8
    block = blocks[b] if b < len(blocks) else "UIN"
    if block.rstrip("0123456789-") != "UIN":
        return None
    digits = "".join(c for c in block.split("-")[0] if c.isdigit())
    start = int(digits) if digits else 8 * b + 1
    return start - 1 + (slot - 1) - 8 * b


_DIRECT_BASES = {"AN": 0, "A": 32, "B": 80, "CARD": 128, "AUX": 160}


def decode_direct_block(block: str, offset: int) -> int:
    """Source number at 0-based ``offset`` in a direct block, or 0 for a non-direct one.

    A block token names its own first input (``A17-24`` starts at AES50-A 17).
    """
    prefix = block.rstrip("0123456789-")
    base = _DIRECT_BASES.get(prefix)
    if base is None:
        return 0
    digits = "".join(c for c in block.split("-")[0] if c.isdigit())
    return base + (int(digits) if digits else 1) + offset


def resolve_in_slot_number(scene: Scene, slot: int) -> int:
    """Resolve a 1-based input slot to its physical source *number*, 0 = OFF.

    Slots 1-32 are the channel banks; 33-40 the aux/USB bank. Offset blocks
    (``A17-24``, ``UIN9-16``) are honored.
    """
    if not 1 <= slot <= 40 or unwritten_in_block(scene, slot) is not None:
        return 0
    idx = uin_in_index(scene, slot)
    if idx is not None:
        uin = userrout(scene, "in")
        return uin[idx] if 0 <= idx < len(uin) else 0
    blocks = _in_blocks(scene)
    b = (slot - 1) // 8
    block = blocks[b] if b < len(blocks) else "UIN"
    return decode_direct_block(block, (slot - 1) - 8 * b)


def resolve_in_slot(scene: Scene, slot: int) -> str:
    """Resolve a 1-based input slot to a physical source label. Slots 39/40 are the aux
    bank's USB player, which no routed-input number names."""
    if slot in AUX_BANK_USB:
        return AUX_BANK_USB[slot]
    if unwritten_in_block(scene, slot) is not None:
        return "?"
    return decode_source(resolve_in_slot_number(scene, slot))


def channel_headamp_index(scene: Scene, ch: int) -> int | None:
    """The /headamp index feeding a channel, or None if its source has no head amp.

    Index is source number - 1 for sources 1-128; Card/Aux/OFF sources have none.
    """
    cfg = scene.get(f"/ch/{ch:02d}/config")
    if not cfg or not cfg.args:
        return None
    slot = int(cfg.args[-1])
    num = resolve_in_slot_number(scene, slot)
    return num - 1 if 1 <= num <= 128 else None


@dataclass
class ChannelSource:
    ch: int
    name: str
    slot: int
    source: str


def channel_sources(scene: Scene) -> list[ChannelSource]:
    out: list[ChannelSource] = []
    for ch in range(1, 33):
        cfg = scene.get(f"/ch/{ch:02d}/config")
        if not cfg or not cfg.args:
            continue
        name = cfg.args[0].strip('"')
        slot = int(cfg.args[-1])
        out.append(ChannelSource(ch, name, slot, resolve_in_slot(scene, slot)))
    return out


def record_map(scene: Scene) -> list[tuple[int, str]]:
    """The USB record tracks the DAW sees: [(track_no, source_label), ...]."""
    card = scene.get("/config/routing/CARD")
    uout = userrout(scene, "out")
    tracks: list[tuple[int, str]] = []
    blocks = list(card.args) if card else ["UOUT1-8", "UOUT9-16", "UOUT17-24", "UOUT25-32"]
    track_no = 1
    for b, block in enumerate(blocks):
        prefix = block.rstrip("0123456789-")
        start = int("".join(c for c in block.split("-")[0] if c.isdigit()) or "1")
        first = uout_start("CARD", block=b, tok=block)
        for off in range(8):
            k = start + off
            if prefix == "UOUT":
                slot = None if first is None else first + off
                src = decode_out_source(uout[slot - 1]) if slot and slot <= len(uout) else "?"
            elif prefix == "CARD":
                src = f"USB Card {k}"
            else:  # direct block: the factory-default card patch
                num = decode_direct_block(block, off)
                src = decode_source(num) if num else f"{block}:{k}"
            tracks.append((track_no, src))
            track_no += 1
    return tracks


def output_sources(scene: Scene, bank: str) -> dict[int, int]:
    """{output number: src} for every well-formed line of an /outputs bank."""
    out: dict[int, int] = {}
    for n in range(1, OUTPUT_BANKS[bank][0] + 1):
        ln = scene.get(f"/outputs/{bank}/{n:02d}")
        if ln and ln.args and ln.args[0].isdigit():
            out[n] = int(ln.args[0])
    return out


def outputs_from_buses(scene: Scene, buses: Iterable[int]) -> list[tuple[str, int, int]]:
    """``(bank, output, bus)`` for every /outputs line, in any bank, sourced from one of
    ``buses``."""
    wanted = set(buses)
    return [(bank, n, tap_to_bus(src)) for bank in OUTPUT_BANKS
            for n, src in output_sources(scene, bank).items() if tap_to_bus(src) in wanted]


def output_aes_mirrors(scene: Scene) -> dict[int, list[str]]:
    """Where each main output leaves on AES50, the stage-box part of :func:`output_reach`:
    ``{output: ['AES50-A 9', 'AES50-B 3 via user-out 3']}``."""
    return {out: aes for out, paths in output_reach(scene).items()
            if (aes := [p for p in paths if p.startswith("AES50")])}


_REACH_DESTS = {"AES50A": "AES50-A", "AES50B": "AES50-B", "CARD": "CARD"}


def output_reach(scene: Scene) -> dict[int, list[str]]:
    """Which main outputs leave the console, and how:
    ``{output: ['AES50-A 9', 'CARD 3 via user-out 3', ...]}``.

    Two paths are followed: an ``OUTk`` block on a destination, and a ``UOUTk`` block
    whose /config/userrout/out slots name the output. /config/routing/OUT is the rear
    XLR bank itself, not a way off the console, and is deliberately not consulted.
    """
    reach: dict[int, list[str]] = {}
    uout = userrout(scene, "out")
    for dest, label in _REACH_DESTS.items():
        for b, tok in enumerate(routing_blocks(scene, dest)):
            prefix, start = _block(tok)
            for off in range(8):
                ch = 8 * b + 1 + off
                if prefix == "OUT":
                    reach.setdefault(start + off, []).append(f"{label} {ch}")
                elif (first := uout_start(dest, block=b, tok=tok)) is not None:
                    k = first - 1 + off
                    o = userrout_out_to_output(uout[k]) if k < len(uout) else None
                    if o:
                        reach.setdefault(o, []).append(f"{label} {ch} via user-out {k + 1}")
    return reach


_OUT_IN_ORDER = ["OUT1-4", "OUT5-8", "OUT9-12", "OUT13-16"]


def jack_outputs(scene: Scene, jacks: int) -> dict[int, int]:
    """``{main output: the first rear XLR jack (1..jacks) carrying it}`` through
    ``/config/routing/OUT``: an ``OUTk`` block directly, a ``UOUTk`` block through the
    user-out slot that names the output. An absent line reads as the in-order patch."""
    blocks, names = routing_blocks(scene, "OUT") or _OUT_IN_ORDER, routing_block_names("OUT")
    uout = userrout(scene, "out")
    carried: dict[int, int] = {}
    for jack in range(1, min(jacks, 4 * len(blocks)) + 1):
        b, off = (jack - 1) // 4, (jack - 1) % 4
        tok = blocks[b]
        if tok not in routing_vocab("OUT", names[b]):
            continue
        if tok.startswith("OUT"):
            out: int | None = _block(tok)[1] + off
        elif (first := uout_start("OUT", block=b, tok=tok)) is not None:
            k = first - 1 + off
            out = userrout_out_to_output(uout[k]) if k < len(uout) else None
        else:
            out = None
        if out:
            carried.setdefault(out, jack)
    return carried


# an OUT position is a rear jack only up to the console's jack count, which no scene records
_READER_LABELS = {"AES50A": "AES50-A", "AES50B": "AES50-B", "CARD": "CARD track",
                  "OUT": "XLR-out routing"}


def user_out_readers(scene: Scene, slot: int) -> list[str]:
    """Every destination channel a UOUT block fills from user-out ``slot`` (1-48):
    ``['AES50-A 5', 'CARD track 5', 'XLR-out routing 5']``."""
    out = []
    for key, label in _READER_LABELS.items():
        width = 4 if key == "OUT" else 8
        for b, tok in enumerate(routing_blocks(scene, key)):
            start = uout_start(key, block=b, tok=tok)
            if start is not None and start <= slot < start + width:
                out.append(f"{label} {width * b + 1 + slot - start}")
    return out


def card_sourced_channels(scene: Scene) -> list[ChannelSource]:
    """Channels whose input is a USB card return (DAW playback / loopback / reamp)."""
    return [cs for cs in channel_sources(scene) if "Card" in cs.source]
