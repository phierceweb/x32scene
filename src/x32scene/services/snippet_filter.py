"""A snippet filter typed by name, and the slice of a scene a desk slot saved through it
recalls: parameter categories x strips, head amps by the channel mask."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..model import HEADER_RE, Line, Scene
from .routing import channel_headamp_index
from .snippets import (_MAIN_MASK, _MASK_LABELS, _STRIP_MASK, EVENTTYP_BITS, Snippet,
                       SnippetHeader, snippet_lines)

__all__ = ["STRIP_CATEGORIES", "filtered_snippet", "header_from_names"]

STRIP_CATEGORIES = 0x1FFF   # Preamp HA through Send Matrix: the categories a strip mask gates
_GROUP = "strip"
_SIZE = {fam: hi - lo + 1 for ranges in _MASK_LABELS.values() for fam, lo, hi in ranges
         if fam in _STRIP_MASK}
_STRIP = re.compile(rf"({'|'.join(_SIZE)})(?:(\d+)(?:-(\d+))?)?")


def _fold(name: str) -> str:
    return " ".join(name.split()).casefold()


_CATEGORY = {_fold(n): 1 << i for i, n in enumerate(EVENTTYP_BITS)} | {_GROUP: STRIP_CATEGORIES}


def _strip_bits(spec: str) -> tuple[str, int]:
    """(mask name, bits) for one strip spec: ``main/st``, ``main/m``, or a family with an
    optional number or range."""
    spec = spec.strip().casefold()
    if spec.startswith("main/") and spec[5:] in _MAIN_MASK:
        return "maingrps", 1 << _MAIN_MASK[spec[5:]]
    m = _STRIP.fullmatch(spec)
    if m is None:
        raise ValueError(f"no strip {spec!r}: a family ({', '.join(_SIZE)}) with an optional "
                         "number or range, main/st or main/m")
    fam, size = m.group(1), _SIZE[m.group(1)]
    lo = int(m.group(2) or 1)
    hi = int(m.group(3) or m.group(2) or size)
    if not 1 <= lo <= hi <= size:
        raise ValueError(f"{spec}: {fam} runs 1-{size}")
    mask, base = _STRIP_MASK[fam]
    return mask, sum(1 << base + n - 1 for n in range(lo, hi + 1))


def header_from_names(name: str, filters: Iterable[str],
                      strips: Iterable[str]) -> SnippetHeader:
    """The header a filter spells, the inverse of :meth:`SnippetHeader.describe`.

    Args:
        name: the snippet's name.
        filters: category names as ``describe`` gives them, in any case; ``strip`` is the
            thirteen per-strip categories.
        strips: strip specs, each one or more of ``ch1-14``, ``bus9``, ``auxin``,
            ``main/st``, comma-separated; a bare family is all of it.

    Raises:
        ValueError: an unknown category or strip, or a number outside its family.
    """
    header = SnippetHeader(name)
    for cat in filters:
        if _fold(cat) not in _CATEGORY:
            raise ValueError(f"no snippet category {cat!r}: one of {', '.join(EVENTTYP_BITS)}, "
                             f"or {_GROUP}")
        header.eventtyp |= _CATEGORY[_fold(cat)]
    for spec in strips:
        for part in spec.split(","):
            mask, bits = _strip_bits(part)
            setattr(header, mask, getattr(header, mask) | bits)
    return header


def _masked_headamps(scene: Scene, header: SnippetHeader) -> set[str]:
    """The head amps the header's channels read: Preamp HA follows the channel mask."""
    amps = (channel_headamp_index(scene, ch) for ch in range(1, 33)
            if header.channels >> (ch - 1) & 1)
    return {f"/headamp/{idx:03d}" for idx in amps if idx is not None}


def filtered_snippet(scene: Scene, header: SnippetHeader) -> Snippet:
    """Every line of ``scene`` the header's filter covers, as it is and in scene order,
    under that header: what a desk slot saved through the filter recalls."""
    amps = _masked_headamps(scene, header) if header.eventtyp & 1 else set()
    body: list[Line] = []
    for ln in scene.lines:
        if not ln.path or HEADER_RE.match(ln.path):
            continue
        for raw in snippet_lines(ln):
            sub = Line.parse(raw)
            if sub.path in amps if sub.path.startswith("/headamp/") else header.covers(sub.path):
                body.append(sub)
    return Snippet(Scene([Line.parse(header.line()), *body], True), header)
