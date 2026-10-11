"""Where the console's outputs go: each /outputs bank's sources, the rear jacks and the
AES50 and card destinations that carry a main output, and what a user-out slot feeds.
``routing.py`` is the input side."""

from __future__ import annotations

from collections.abc import Iterable

from ..model import Scene
from ..tables import (OUTPUT_BANKS, routing_block_names, routing_vocab, tap_to_bus,
                      userrout_out_to_output)
from .routing import routing_blocks, uout_start, userrout


def _block(tok: str) -> tuple[str, int]:
    """A routing token's (prefix, first number): 'UOUT9-16' -> ('UOUT', 9)."""
    prefix = tok.rstrip("0123456789-")
    digits = "".join(c for c in tok.split("-")[0] if c.isdigit())
    return prefix, (int(digits) if digits else 1)


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
