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

from dataclasses import dataclass

from ..model import Scene
from ..tables import (AUX_BANK_USB, SLOT_RETURNS, decode_out_source,
                      decode_source, routing_block_names, routing_vocab)


def userrout(scene: Scene, which: str) -> list[int]:
    """The /config/userrout/in (32) or /out (48) slot values; [] when the line is absent."""
    ln = scene.get(f"/config/userrout/{which}")
    return [int(x) for x in ln.args] if ln else []


def routing_blocks(scene: Scene, key: str) -> list[str]:
    """The block tokens on /config/routing/<key>; [] when the line is absent."""
    ln = scene.get(f"/config/routing/{key}")
    return list(ln.args) if ln else []


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


def _aux_past_span(scene: Scene, slot: int) -> int | None:
    """The Aux In number an aux slot reads past its ``AUX`` token's span (``AN1-2`` remaps
    33-34, so 35-38 stay Aux In 3-6; ``AUX1-4`` means all six), else None."""
    blocks = _in_blocks(scene)
    if 33 <= slot <= 38 and len(blocks) >= 5 and unwritten_in_block(scene, slot) is None:
        span = 6 if blocks[4].startswith("AUX") else int(blocks[4].rsplit("-", 1)[1])
        return 160 + slot - 32 if slot - 32 > span else None
    return None


def uin_in_index(scene: Scene, slot: int) -> int | None:
    """0-based /config/userrout/in index feeding ``slot``, honoring the UIN block's own range
    (``UIN9-16`` on bank 0 maps slot 1 -> index 8); None for a non-UIN or Aux In slot."""
    if (not 1 <= slot <= 40 or unwritten_in_block(scene, slot) is not None
            or _aux_past_span(scene, slot) is not None):
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
    """Resolve a 1-based input slot to its physical source *number*, 0 = OFF. Slots 1-32 are
    the channel banks, 33-40 the aux/USB bank; offset blocks (``A17-24``, ``UIN9-16``) and a
    partial ``AUX`` token (``AN1-2``) are honored."""
    if not 1 <= slot <= 40 or unwritten_in_block(scene, slot) is not None:
        return 0
    if (aux := _aux_past_span(scene, slot)) is not None:
        return aux
    idx = uin_in_index(scene, slot)
    if idx is not None:
        uin = userrout(scene, "in")
        return uin[idx] if 0 <= idx < len(uin) else 0
    blocks = _in_blocks(scene)
    b = (slot - 1) // 8
    block = blocks[b] if b < len(blocks) else "UIN"
    return decode_direct_block(block, (slot - 1) - 8 * b)


def resolve_in_slot(scene: Scene, slot: int) -> str:
    """Resolve a channel source slot (0-64) to a source label. Slots 39/40 are the aux
    bank's USB player and 41-64 the FX returns and buses, which no routed-input number names."""
    if not 0 <= slot <= 64:
        return "?"
    named = AUX_BANK_USB.get(slot) or SLOT_RETURNS.get(slot)
    if named:
        return named
    if unwritten_in_block(scene, slot) is not None:
        return "?"
    return decode_source(resolve_in_slot_number(scene, slot))


def routing_switch(scene: Scene) -> str | None:
    """``REC`` or ``PLAY``, the input bank set the desk reads; None without the line."""
    ln = scene.get("/config/routing")
    return ln.args[0].upper() if ln and ln.args else None


PLAY_NOTE = ("the routing switch is PLAY: the desk reads the PLAY bank, so this is the REC "
             "patch")


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


def card_sourced_channels(scene: Scene) -> list[ChannelSource]:
    """Channels whose input is a USB card return (DAW playback / loopback / reamp)."""
    return [cs for cs in channel_sources(scene) if "Card" in cs.source]
