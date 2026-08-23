"""High-level, surgical edits on a :class:`~x32scene.model.Scene`.

Every transform touches only the lines it must; everything else stays byte-identical.
Channel/bus indices are 1-based and formatted two digits to match the file (``/ch/05/``).
"""

from __future__ import annotations

from ..model import HEADER_RE, Line, Scene
from .channelfx import link_targets
from .routing import resolve_in_slot_number, uin_in_index
from ..tables import bus_to_tap, headamp_index, strip_path


def _ha(idx: int) -> str:
    return f"/headamp/{idx:03d}"


# ---- naming -----------------------------------------------------------------
def _qname(name: str) -> str:
    if '"' in name or "\n" in name or "\r" in name:
        raise ValueError(f"names must not contain double quotes or line breaks: {name!r}")
    return f'"{name}"'


def retitle_scene(scene: Scene, name: str) -> None:
    """Set the scene title in the ``#4.0#`` header (re-padded to width on rebuild)."""
    if not scene.lines or not HEADER_RE.match(scene.lines[0].path):
        raise ValueError("scene has no header line")
    scene.lines[0].set_arg(0, _qname(name))


def rename_strip(scene: Scene, strip: int | str, name: str) -> list[str]:
    """Rename any strip family (channels, buses, FX returns, DCAs). Never mirrored —
    each side of a linked pair keeps its own name."""
    path = strip_path(strip)
    line = scene.get(f"{path}/config")
    if line is None:
        raise KeyError(f"no {path}/config")
    line.set_arg(0, _qname(name))
    return [path]


def rename_channel(scene: Scene, ch: int, name: str) -> None:
    rename_strip(scene, ch, name)


# ---- preamp (headamp = analog record gain + phantom) ------------------------
# the XLR head amp's 72 dB span; no -oo, unlike a fader
HEADAMP_MIN_DB, HEADAMP_MAX_DB = -12.0, 60.0


def set_headamp_index(scene: Scene, idx: int, gain_db: float | None = None,
                      phantom: bool | None = None) -> None:
    """Set analog gain and/or +48V on a raw ``/headamp/NNN`` index."""
    line = scene.get(_ha(idx))
    if line is None:
        raise KeyError(f"no /headamp/{idx:03d}")
    if gain_db is not None:
        if not HEADAMP_MIN_DB <= gain_db <= HEADAMP_MAX_DB:
            raise ValueError(f"gain must be {HEADAMP_MIN_DB:g}..{HEADAMP_MAX_DB:+g} dB, "
                             f"got {gain_db}")
        line.set_arg(0, f"{gain_db:+.1f}")
    if phantom is not None:
        line.set_arg(1, "ON" if phantom else "OFF")


def set_headamp(scene: Scene, kind: str, n: int, gain_db: float | None = None,
                phantom: bool | None = None) -> None:
    """Set analog gain and/or +48V on a physical input (kind: local / aesa / aesb).

    This is the real preamp (``/headamp/NNN``), not the channel's digital trim.
    """
    set_headamp_index(scene, headamp_index(kind, n), gain_db, phantom)


LEVEL_MIN_DB, LEVEL_MAX_DB = -90.0, 10.0


def fmt_level(level_db: float) -> str:
    # console convention: '-oo', unsigned '0.0' at zero, signed elsewhere
    if level_db == float("-inf"):
        return "-oo"
    # NaN and infinities fail this comparison, so they never reach the file as tokens
    if not LEVEL_MIN_DB <= level_db <= LEVEL_MAX_DB:
        raise ValueError(f"level must be {LEVEL_MIN_DB:g}..{LEVEL_MAX_DB:+g} dB or -oo, "
                         f"got {level_db}")
    tok = f"{level_db:+.1f}"
    return "0.0" if tok in ("+0.0", "-0.0") else tok


def parse_level(v: float | str) -> float:
    """A fader level from user input: a number, or ``-oo`` / ``oo`` for -infinity."""
    if v in ("-oo", "oo"):
        return float("-inf")
    return float(v)


# ---- fader / mute / pan ------------------------------------------------------
_DCA_PATHS = frozenset(f"/dca/{n}" for n in range(1, 9))


def _mix_line(scene: Scene, strip: int | str) -> tuple[str, "Line"]:
    path = strip_path(strip)
    if path.startswith("/dca/"):
        # a DCA's level lives on the strip line itself; without the exact match, deeper
        # paths like /dca/1/config would resolve verbatim and get overwritten
        ln = scene.get(path) if path in _DCA_PATHS else None
    else:
        ln = scene.get(f"{path}/mix")
    if ln is None:
        raise KeyError(f"no mix line for {path}")
    return path, ln


def set_fader(scene: Scene, strip: int | str, level_db: float, *,
              linked: bool | None = None) -> list[str]:
    """Set a strip's fader (works for /dca/N too). On a stereo-linked pair with
    fader/mute link on, mirrors to the partner strip unless linked=False."""
    tok = fmt_level(level_db)
    paths = link_targets(scene, strip, "fdrmute", linked)
    for p in paths:
        _mix_line(scene, p)[1].set_arg(1, tok)
    return paths


def set_mute(scene: Scene, strip: int | str, mute: bool = True, *,
             linked: bool | None = None) -> list[str]:
    """Mute/unmute a strip — the /mix ON flag is the mute state (OFF = muted). On a
    stereo-linked pair with fader/mute link on, mirrors to the partner strip unless
    linked=False."""
    paths = link_targets(scene, strip, "fdrmute", linked)
    for p in paths:
        _mix_line(scene, p)[1].set_arg(0, "OFF" if mute else "ON")
    return paths


def set_pan(scene: Scene, strip: int | str, pan: int) -> list[str]:
    """Set pan/balance, -100..+100 (main/st keeps it one field earlier). Never mirrored —
    a linked pair's pans are individually meaningful."""
    if not -100 <= pan <= 100:
        raise ValueError(f"pan must be -100..100, got {pan}")
    path, ln = _mix_line(scene, strip)
    idx = 2 if path == "/main/st" else 3
    if path.startswith("/dca/") or len(ln.args) <= idx:
        raise ValueError(f"{path} has no pan")
    ln.set_arg(idx, f"{pan:+d}")
    return [path]


# ---- output / IEM routing ---------------------------------------------------
def set_output_tap(scene: Scene, out: int, tap: int) -> None:
    """Set the source tap of a main output (``/outputs/main/NN`` field 1). Outputs 9-16 are
    virtual on a Rack — mirrored down AES50 rather than carrying a jack."""
    line = scene.get(f"/outputs/main/{out:02d}")
    if line is None:
        raise KeyError(f"no output {out}")
    line.set_arg(0, str(tap))


def route_output_from_bus(scene: Scene, out: int, bus: int) -> None:
    """Route main output ``out`` (1-16) from monitor ``bus`` (1-16). ``/outputs/aux`` is
    not reachable this way."""
    set_output_tap(scene, out, bus_to_tap(bus))


def move_input_to_stagebox(scene: Scene, ch: int, aes_input: int, *, port: str = "A",
                           move_gain: bool = True) -> None:
    """Re-source a channel from an AES50 stage-box input (1-48) via its UIN slot.

    ``move_gain`` carries analog gain + phantom over so the channel sounds the same.
    Raises on direct-routed (non-UIN) blocks.
    """
    _apply_move(scene, _plan_move(scene, ch, aes_input, port), move_gain)


def _plan_move(scene: Scene, ch: int, aes_input: int, port: str) -> tuple[int, int, int]:
    """Validate one stage-box move; returns (userrout index, new source, old source)."""
    if port not in ("A", "B"):
        raise ValueError("port must be 'A' or 'B'")
    if not 1 <= aes_input <= 48:
        raise ValueError(f"aes_input must be 1-48, got {aes_input}")
    cfg = scene.get(f"/ch/{ch:02d}/config")
    if not cfg or not cfg.args:
        raise KeyError(f"no channel {ch}")
    slot = int(cfg.args[-1])
    if not 1 <= slot <= 32:
        raise ValueError(f"ch{ch} source slot {slot} is OFF/out of range — nothing to move")
    idx = uin_in_index(scene, slot)
    if idx is None:
        raise ValueError(f"ch{ch} slot {slot} is direct-routed (non-UIN routing block) — "
                         "not supported by this transform")
    uin = scene.get("/config/userrout/in")
    if uin is None or not 0 <= idx < len(uin.args):
        raise ValueError(f"userrout/in index {idx} out of range — "
                         "malformed /config/routing/IN block?")
    return idx, {"A": 32, "B": 80}[port] + aes_input, resolve_in_slot_number(scene, slot)


def _apply_move(scene: Scene, plan: tuple[int, int, int], move_gain: bool) -> None:
    idx, new_src, old_src = plan
    scene.get("/config/userrout/in").set_arg(idx, str(new_src))
    if move_gain and 1 <= old_src <= 128:
        old_ha = scene.get(_ha(old_src - 1))
        new_ha = scene.get(_ha(new_src - 1))
        if old_ha and new_ha and new_ha.args != old_ha.args:
            new_ha.args = list(old_ha.args)
            new_ha.rebuild()


def move_inputs_to_stagebox(scene: Scene, mapping: dict[int, int], *, port: str = "A",
                            move_gain: bool = True) -> int:
    """Batch move: mapping = {channel: aes_input_number}. Returns channels moved.

    Every move is validated before any is applied, so a bad entry leaves the scene clean.
    """
    plans = [_plan_move(scene, ch, aes, port) for ch, aes in mapping.items()]
    for plan in plans:
        _apply_move(scene, plan, move_gain)
    return len(mapping)


def port_output_routing(src: Scene, dst: Scene) -> int:
    """Copy the physical-output routing (main/aux: tap, tap point, polarity) from
    ``src`` to ``dst``, leaving /delay lines alone. Returns output lines changed."""
    changed = 0
    for ln in [*src.find("/outputs/main/"), *src.find("/outputs/aux/")]:
        if ln.path.endswith("/delay"):
            continue
        d = dst.get(ln.path)
        if d is not None and d.args != ln.args:
            d.args = list(ln.args)
            d.rebuild()
            changed += 1
    return changed
