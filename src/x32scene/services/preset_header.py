"""The `.chn` header's flag model and the scopes it selects.

A header is ``#4.0# <pos> "<name>" 0 %<16 flags> 1``: bit 8 upward says a section is
present, bit 0 upward that it is ON. ``preset_selects`` turns those flags, or an explicit
scope list, into the predicate an apply writes a bare preset path by.
"""

from __future__ import annotations

from collections.abc import Callable

from ..model import HEADER_RE, HEADER_WIDTH, Line, Scene, check_token
from .scopes import SCOPES, scope_of


def body_lines(chn_text: str) -> list[Line]:
    """Every line of a preset but its header and blank lines. Raises ValueError on CR, as
    ``Scene.parse`` does."""
    return [ln for ln in Scene.parse(chn_text).lines if ln.raw and not ln.raw.startswith("#")]


def _selected(scopes: list[str] | None) -> set[str]:
    return set(SCOPES if scopes is None else scopes)


# .chn header flag order, bit 8 upward = section present, bit 0 upward = section ON.
_SECTIONS = ("preamp", "config", "locut", "gate", "eq", "dyn")
# (section, bare path that decides "present", arg index whose ON token decides "active")
_SECTION_LINES = {"preamp": ("/headamp", 1), "config": ("/delay", 0), "locut": ("/preamp", 2),
                  "gate": ("/gate", 0), "eq": ("/eq", 0), "dyn": ("/dyn", 0)}
_SECTION_SCOPES = {"preamp": "ha", "locut": "ha", "config": "scribble", "gate": "gate",
                   "eq": "eq", "dyn": "comp"}


def preset_header(name: str, present: set[str], active: set[str], pos: int = 1) -> str:
    """A `.chn` header line: ``#4.0# <pos> "<name>" 0 %<16 flags> 1``, padded like the
    console writes it."""
    check_token(f'"{name}"')
    bits = ["0"] * 16
    for i, section in enumerate(_SECTIONS):
        if section in present:
            bits[15 - (8 + i)] = "1"
        if section in active:
            bits[15 - i] = "1"
    return f'#4.0# {pos} "{name}" 0 %{"".join(bits)} 1'.ljust(HEADER_WIDTH)


def _header_mask(chn_text: str) -> str | None:
    """The 16 flag bits of the header the text opens with, or None."""
    ln = Line.parse(chn_text.split("\n", 1)[0])
    if not HEADER_RE.match(ln.path):
        return None
    return next((a[1:] for a in ln.args
                 if a.startswith("%") and len(a) == 17 and set(a[1:]) <= {"0", "1"}), None)


def header_sections(chn_text: str) -> dict[str, list[str]] | None:
    """What a `.chn` header declares — ``{"present": [...], "active": [...]}`` in flag
    order — or None for a preset with no header or whose header carries no 16-bit flag mask."""
    mask = _header_mask(chn_text)
    if mask is None:
        return None
    return {"present": [s for i, s in enumerate(_SECTIONS) if mask[15 - (8 + i)] == "1"],
            "active": [s for i, s in enumerate(_SECTIONS) if mask[15 - i] == "1"]}


def sections_of(lines: list[Line]) -> tuple[set[str], set[str]]:
    """(present, active) sections of extracted preset lines, per the header's flag model."""
    present, active = set(), set()
    for ln in lines:
        for section, (bare, idx) in _SECTION_LINES.items():
            if ln.path == bare or ln.path.startswith(bare + "/"):
                present.add(section)
                if ln.path == bare and len(ln.args) > idx and ln.args[idx] == "ON":
                    active.add(section)
    paths = {ln.path for ln in lines}
    if "/preamp" in paths:
        present.add("preamp")   # the digital preamp line is the preamp section too
    if "/config" in paths:
        present.add("config")
    return present, active


def header_scopes(chn_text: str) -> list[str] | None:
    """The scopes a `.chn` header flags present, plus every scope no flag covers (sends,
    main/fader, insert, automix) — or None for a preset with no header or whose header
    carries no 16-bit flag mask."""
    if _header_mask(chn_text) is None:
        return None
    flagged = {_SECTION_SCOPES[s] for s in header_sections(chn_text)["present"]}
    return [s for s in SCOPES if s in flagged or s not in _SECTION_SCOPES.values()]


def preset_selects(chn_text: str, scopes: list[str] | None) -> Callable[[str], bool]:
    """The predicate for whether an apply writes a bare preset path: by ``scopes`` when given, else by the
    header's flags (:func:`header_scopes`, with ``/delay`` following the config flag), else
    every scope."""
    header = header_scopes(chn_text) if scopes is None else None
    sel = _selected(scopes if header is None else header)
    config = header is not None and "config" in header_sections(chn_text)["present"]

    def selects(bare: str) -> bool:
        return config if header is not None and bare == "/delay" else scope_of(bare) in sel
    return selects


def unflagged_scopes(chn_text: str, scopes: list[str] | None = None) -> list[str]:
    """Scopes of body lines an apply skips because the header does not flag them present, then
    ``/delay`` when the config flag skips it; empty when ``scopes`` is given or the header
    carries no flag mask."""
    if scopes is not None or header_scopes(chn_text) is None:
        return []
    selects = preset_selects(chn_text, None)
    skipped = {ln.path for ln in body_lines(chn_text) if not selects(ln.path)}
    by_scope = {scope_of(p) for p in skipped - {"/delay"}}
    return [s for s in SCOPES if s in by_scope] + (["/delay"] if "/delay" in skipped else [])
