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
from ..tables import (AUX_BANK_USB, OUTPUT_BANKS, decode_out_source, decode_source,
                      userrout_out_to_output)


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


def _in_blocks(scene: Scene) -> list[str]:
    return routing_blocks(scene, "IN")


def uin_in_index(scene: Scene, slot: int) -> int | None:
    """0-based /config/userrout/in index feeding ``slot``, honoring the UIN block's own
    range (``UIN9-16`` on bank 0 maps slot 1 -> index 8). None for a non-UIN block."""
    if not 1 <= slot <= 40:
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
    if not 1 <= slot <= 40:
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
    for block in blocks:
        prefix = block.rstrip("0123456789-")
        start = int("".join(c for c in block.split("-")[0] if c.isdigit()) or "1")
        for off in range(8):
            k = start + off
            if prefix == "UOUT":
                src = decode_out_source(uout[k - 1]) if k - 1 < len(uout) else "?"
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


def output_aes_mirrors(scene: Scene) -> dict[int, list[str]]:
    """Where each main output is mirrored on AES50: {output_num: ['AES50-A 9', ...]}.

    A ``/config/routing/AES50A|B`` token 'OUT9-16' means those 8 AES50 channels carry
    output signals 9-16.
    """
    mirrors: dict[int, list[str]] = {}
    for port in ("A", "B"):
        for b, tok in enumerate(routing_blocks(scene, f"AES50{port}")):
            prefix, out_start = _block(tok)
            if prefix != "OUT":
                continue
            for off in range(8):
                mirrors.setdefault(out_start + off, []).append(f"AES50-{port} {8 * b + 1 + off}")
    return mirrors


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
                elif prefix == "UOUT":
                    k = start - 1 + off
                    o = userrout_out_to_output(uout[k]) if k < len(uout) else None
                    if o:
                        reach.setdefault(o, []).append(f"{label} {ch} via user-out {k + 1}")
    return reach


def card_sourced_channels(scene: Scene) -> list[ChannelSource]:
    """Channels whose input is a USB card return (DAW playback / loopback / reamp)."""
    return [cs for cs in channel_sources(scene) if "Card" in cs.source]
