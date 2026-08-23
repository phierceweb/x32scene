"""Programmatic "Save as preset" / "Load preset" — extract and apply `.chn` channel strips.

Mirrors the X32 dialog's scope checkboxes. A `.chn` uses bare paths (``/eq/1``); a scene
uses ``/ch/NN/eq/1``. The head-amp is the cross-cutting piece: it lives outside the
channel block at ``/headamp/<source-index>``, so applying remaps it onto the target's.
"""

from __future__ import annotations

from ..model import HEADER_RE, HEADER_WIDTH, Line, Scene, check_token
from .routing import channel_headamp_index
from .scopes import SCOPES, scope_of


def _checked(args: list[str], path: str) -> list[str]:
    """apply_preset assigns args directly rather than through set_arg, so preset tokens
    are validated here instead."""
    try:
        for tok in args:
            check_token(tok)
    except ValueError as e:
        raise ValueError(f"preset line {path!r}: {e}") from e
    return args


def _selected(scopes: list[str] | None) -> set[str]:
    return set(SCOPES if scopes is None else scopes)


# .chn header flag order, bit 8 upward = section present, bit 0 upward = section ON.
# Inferred from the protocol document and a zeroed reset preset, not confirmed on hardware.
_SECTIONS = ("preamp", "config", "locut", "gate", "eq", "dyn")
# (section, bare path that decides "present", arg index whose ON token decides "active")
_SECTION_LINES = {"preamp": ("/headamp", 1), "config": ("/delay", 0), "locut": ("/preamp", 2),
                  "gate": ("/gate", 0), "eq": ("/eq", 0), "dyn": ("/dyn", 0)}


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


def header_sections(chn_text: str) -> dict[str, list[str]] | None:
    """What a `.chn` header declares — ``{"present": [...], "active": [...]}`` in flag
    order — or None for a headerless preset."""
    ln = Line.parse(chn_text.split("\n", 1)[0])
    if not HEADER_RE.match(ln.path):
        return None
    mask = next((a[1:] for a in ln.args if a.startswith("%") and len(a) == 17), None)
    if mask is None:
        return {"present": [], "active": []}
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
    if "/preamp" in {ln.path for ln in lines}:
        present.add("preamp")   # the digital preamp line is the preamp section too
    return present, active


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


def apply_preset(scene: Scene, ch: int, chn_text: str,
                 scopes: list[str] | None = None) -> int:
    """Apply a `.chn` onto channel ``ch`` in ``scene``. Returns the number of lines changed.

    Only paths whose scope is selected AND present in the preset are written. The preset's
    head-amp is remapped from its stored index onto the target channel's head-amp index.
    """
    sel = _selected(scopes)
    prefix = f"/ch/{ch:02d}"
    changed = 0
    for raw in chn_text.splitlines():
        raw = raw.rstrip("\n")
        if not raw or raw.startswith("#"):  # skip blank + optional #2.1# header
            continue
        src = Line.parse(raw)
        if src.path.startswith("/headamp"):
            if "ha" not in sel:
                continue
            idx = channel_headamp_index(scene, ch)
            if idx is None:
                continue
            target = scene.get(f"/headamp/{idx:03d}")
            if target and target.args != src.args:
                target.args = _checked(list(src.args), src.path)
                target.rebuild()
                changed += 1
            continue
        bare = src.path
        if scope_of(bare) not in sel:
            continue
        target = scene.get(prefix + bare)
        if target is None:
            continue
        new_args = _checked(list(src.args), src.path)
        if bare == "/config" and new_args and target.args:
            if len(new_args) != len(target.args):
                raise ValueError(
                    f"preset /config has {len(new_args)} fields, target has "
                    f"{len(target.args)} — refusing to apply a malformed line")
            # /config's last arg is the input source slot — a preset must never
            # repatch the target channel
            new_args[-1] = target.args[-1]
        if target.args != new_args:
            target.args = new_args
            target.rebuild()
            changed += 1
    return changed
