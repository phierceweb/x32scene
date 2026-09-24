"""Programmatic "Save as preset" / "Load preset" — extract and apply `.chn` channel strips.

Mirrors the X32 dialog's scope checkboxes. A `.chn` uses bare paths (``/eq/1``); a scene
uses ``/ch/NN/eq/1``. The head-amp is the cross-cutting piece: it lives outside the
channel block at ``/headamp/<source-index>``, so applying remaps it onto the target's.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ..model import HEADER_RE, HEADER_WIDTH, Line, Scene, check_token, put_field, put_level
from ..tables import send_line_fields
from .channelfx import pair_linked
from .iem import bus_link_group
from .routing import channel_headamp_index
from .scopes import SCOPES, scope_of
from .snippets import MIX_FIELD


_STRIP_EQ_BANDS = re.compile(r"^/eq/[56](?: |$)", re.MULTILINE)


def _checked(args: list[str], path: str) -> list[str]:
    """apply_preset assigns args directly rather than through set_arg, so preset tokens
    are validated here instead."""
    try:
        for tok in args:
            check_token(tok)
    except ValueError as e:
        raise ValueError(f"preset line {path!r}: {e}") from e
    return args


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


def _sections_of(lines: list[Line]) -> tuple[set[str], set[str]]:
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


def extract_preset(scene: Scene, ch: int, scopes: list[str] | None = None, *,
                   header: bool | str = False) -> str:
    """Build `.chn` text for one channel, in the selected scopes only — headerless unless
    ``header`` is True (named from the channel's scribble) or a preset name.

    The head-amp line keeps the channel's real source index, as the console writes it.
    """
    sel = _selected(scopes)
    prefix = f"/ch/{ch:02d}"
    out: list[Line] = []
    for ln in scene.lines:
        if not ln.path.startswith(prefix + "/"):
            continue
        bare = ln.path[len(prefix):]
        if scope_of(bare) in sel:
            out.append(Line.parse(bare + (" " + " ".join(ln.args) if ln.args else "")))
    # head amp (HA Config) lives outside /ch/NN — pull it in at the source's real index
    if "ha" in sel:
        idx = channel_headamp_index(scene, ch)
        if idx is not None:
            ha = scene.get(f"/headamp/{idx:03d}")
            if ha:
                out.append(Line.parse(ha.raw))
    text = [ln.raw for ln in out]
    if header:
        cfg = scene.get(f"{prefix}/config")
        name = header if isinstance(header, str) else (
            cfg.args[0].strip('"') if cfg and cfg.args else f"ch {ch:02d}")
        text.insert(0, preset_header(name, *_sections_of(out)))
    return "\n".join(text) + "\n"


def _send_bus(bare: str) -> int | None:
    tail = bare[len("/mix/"):] if bare.startswith("/mix/") else ""
    return int(tail) if tail.isdigit() else None


def mirrored_sends(scene: Scene, ch: int, chn_text: str,
                   scopes: list[str] | None = None) -> list[tuple[str, str]]:
    """``(scene path, preset path)`` for each send whose on and level an apply takes from a
    preset line other than its own: channel ``ch``'s send to a stereo-linked bus partner the
    preset has no line for, or whose line comes first with another on or level (a
    line-by-line load leaves a linked pair at the later line); and, on a stereo-linked
    channel, the partner channel's send to each bus the apply writes, which takes the tap
    too. Raises KeyError when a send is selected and the scene has no ``/config/buslink``."""
    selects = preset_selects(chn_text, scopes)
    source: dict[int, tuple[int, list[str]]] = {}
    own: dict[int, list[str]] = {}
    for ln in body_lines(chn_text):
        bus = _send_bus(ln.path)
        if bus is not None and selects(ln.path):
            own[bus] = ln.args[:2]
            for b in bus_link_group(scene, bus):
                source[b] = (bus, ln.args[:2])
    prefix = f"/ch/{ch:02d}/mix"
    out = [(f"{prefix}/{b:02d}", f"/mix/{src:02d}") for b, (src, took) in sorted(source.items())
           if b != src and own.get(b) != took and scene.get(f"{prefix}/{b:02d}") is not None]
    partner = pair_linked(scene, f"/ch/{ch:02d}") if source else None
    return out + [(f"{partner}/mix/{b:02d}", f"/mix/{src:02d}")
                  for b, (src, _) in sorted(source.items())
                  if partner and scene.get(f"{partner}/mix/{b:02d}") is not None]


def writes_beyond_sends(chn_text: str, scopes: list[str] | None = None) -> bool:
    """Does an apply of this preset write a line other than a send?"""
    selects = preset_selects(chn_text, scopes)
    return any(selects(ln.path) and _send_bus(ln.path) is None for ln in body_lines(chn_text))


def partner_only_sends(scene: Scene, ch: int, chn_text: str,
                       scopes: list[str] | None = None) -> list[str]:
    """The :func:`mirrored_sends` scene paths the preset has no line of its own for."""
    carried = {f"/ch/{ch:02d}{ln.path}" for ln in body_lines(chn_text)}
    return [p for p, _ in mirrored_sends(scene, ch, chn_text, scopes) if p not in carried]


def apply_preset(scene: Scene, ch: int, chn_text: str,
                 scopes: list[str] | None = None) -> int:
    """Apply a `.chn` onto channel ``ch`` in ``scene``. Returns the number of lines changed.

    Only paths whose scope is selected AND present in the preset are written; with no
    ``scopes`` a header's section flags select them (:func:`preset_selects`). The preset's
    head-amp is remapped from its stored index onto the target channel's head-amp index.
    A send on a stereo-linked bus pair is written to both buses (:func:`mirrored_sends`); a
    send line short of its bus's fields (a ``#2.1#`` desk preset's) keeps the target's rest.
    CR line endings, EQ bands 5-6 (a bus, matrix or main strip), or a selected send line
    without on and level or longer than its bus's raise ValueError.
    """
    lines = body_lines(chn_text)
    if _STRIP_EQ_BANDS.search(chn_text):
        raise ValueError("preset has EQ bands 5-6, so it is a bus, matrix or main preset: "
                         "applying it to a channel would put its matrix sends on the "
                         "channel's bus sends")
    selects = preset_selects(chn_text, scopes)
    for ln in lines:
        bus = _send_bus(ln.path)
        if bus is not None and selects(ln.path) and not 2 <= len(ln.args) <= send_line_fields(bus):
            raise ValueError(f"preset {ln.path} carries {len(ln.args)} field(s): a send to bus "
                             f"{bus} carries on and level, and at most {send_line_fields(bus)}")
    mirrors = mirrored_sends(scene, ch, chn_text, scopes)
    by_path = {ln.path: ln for ln in lines}
    for path, src in mirrors:
        scene.get(path).require(len(by_path[src].args[:2]))
    prefix = f"/ch/{ch:02d}"
    before: dict[int, tuple[Line, list[str]]] = {}

    def touch(line: Line) -> None:
        before.setdefault(id(line), (line, list(line.args)))

    for src in lines:
        if src.path.startswith("/headamp"):
            if not selects(src.path):
                continue
            idx = channel_headamp_index(scene, ch)
            if idx is None:
                continue
            target = scene.get(f"/headamp/{idx:03d}")
            if target and target.args != src.args:
                touch(target)
                target.args = _checked(list(src.args), src.path)
                target.rebuild()
            continue
        bare = src.path
        if not selects(bare):
            continue
        field = MIX_FIELD.get(bare[len("/mix/"):]) if bare.startswith("/mix/") else None
        target = scene.get(prefix + ("/mix" if field is not None else bare))
        if target is None:
            continue
        new_args = _checked(list(src.args), src.path)
        if _send_bus(bare) is not None:   # the desk leaves a field the line does not carry
            new_args += target.args[len(new_args):]
        if field is not None:   # the desk saves the main mix one field per line
            if len(new_args) != 1 or field >= len(target.args):
                raise ValueError(f"preset {bare} does not fit {prefix}/mix")
            new_args = [*target.args[:field], new_args[0], *target.args[field + 1:]]
        if bare == "/config" and new_args and target.args:
            # the desk saves name/icon/colour only; a scene line adds the source slot
            if len(new_args) == len(target.args) - 1:
                new_args.append(target.args[-1])
            if len(new_args) != len(target.args):
                raise ValueError(
                    f"preset /config has {len(new_args)} fields, target has "
                    f"{len(target.args)} — refusing to apply a malformed line")
            # /config's last arg is the input source slot — a preset must never
            # repatch the target channel
            new_args[-1] = target.args[-1]
        if target.args != new_args:
            touch(target)
            target.args = new_args
            target.rebuild()
    for path, src in mirrors:
        target = scene.get(path)
        touch(target)
        fields = target.padded_fields()
        put_field(fields, 0, by_path[src].args[0])
        put_level(fields, 1, by_path[src].args[1])
        own = by_path.get(path[len(path) - len("/mix/NN"):])
        if not path.startswith(prefix) and own and len(own.args) > 3 and len(fields) > 3:
            put_field(fields, 3, own.args[3])   # the tap mirrors across a channel pair; pan does not
        target.set_fields(fields)
    return sum(line.args != args for line, args in before.values())
