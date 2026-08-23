"""Per-channel EQ / dynamics / gate / low-cut editors.

Each setter edits only the fields you pass and range-checks them; unspecified fields are
preserved. Values are written in the console's own token conventions, per field.

``linked=False`` suppresses stereo-link mirroring; ``linked=True`` forces it past a link
preference that is off, but never onto a pair the console has not linked — an unlinked
strip is always edited alone. Each setter returns the strip paths it edited.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import LINKCFG, LINK_LINES, strip_path as _strip

# ---- X32 numeric formatting -------------------------------------------------
def fmt_freq(hz: float) -> str:
    """X32 frequency token: <1000 -> '85.3'; >=1000 -> '4k37' (k replaces the decimal)."""
    if round(hz, 1) >= 1000:
        return f"{hz / 1000:.2f}".replace(".", "k")
    return f"{hz:.1f}"


def fmt_gain(db: float) -> str:
    """X32 EQ-gain token: a 5-char signed field, so '+4.75' below 10 dB, '+10.2' above."""
    return f"{db:+.2f}" if abs(db) < 10 else f"{db:+.1f}"


def _fmt_q(q: float) -> str:
    """X32 EQ-Q token: a 3-char field, so '2.0' below 10 and a bare '10' at the top."""
    return "10" if round(q, 1) >= 10 else f"{q:.1f}"


def _fmt_3sig(v: float) -> str:
    """Dynamics hold / comp makeup: a 4-char, 3-significant-digit token ('7.96', '31.7',
    '126'). Boundaries compare the rounded value so 9.996 -> '10.0', not '10.00'."""
    if round(v, 2) < 10:
        return f"{v:.2f}"
    return f"{v:.1f}" if round(v, 1) < 100 else f"{v:.0f}"


# ---- enums / ranges (validated) ---------------------------------------------
EQ_TYPES = ["LCut", "LShv", "PEQ", "VEQ", "HShv", "HCut"]
# The console rejects a bare "4" and abandons the rest of the /dyn line, so single-digit
# ratios must carry the decimal; the aliases below normalize to these canonical tokens.
COMP_RATIOS = ["1.1", "1.3", "1.5", "2.0", "2.5", "3.0", "4.0", "5.0", "7.0", "10", "20", "100"]
COMP_RATIO_ALIASES = {"2": "2.0", "3": "3.0", "4": "4.0", "5": "5.0", "7": "7.0"}
GATE_MODES = ["EXP2", "EXP3", "EXP4", "GATE", "DUCK"]


def _rng(name: str, v: float, lo: float, hi: float) -> None:
    if not lo <= v <= hi:
        raise ValueError(f"{name} {v} out of range [{lo}, {hi}]")


def _line(scene: Scene, path: str):
    ln = scene.get(path)
    if ln is None:
        raise KeyError(f"no {path}")
    return ln


# ---- Stereo-link mirroring ----------------------------------------------------
def link_line(path: str) -> str | None:
    """The ``/config`` line governing a strip family's stereo pairing, or None for a
    family the console does not pair."""
    return LINK_LINES.get(path.rpartition("/")[0])


def pair_linked(scene: Scene, path: str) -> str | None:
    """The linked partner's strip path, or None."""
    fam, _, num = path.rpartition("/")
    line = LINK_LINES.get(fam)
    if line is None or not num.isdigit():
        return None
    n = int(num)
    ln = scene.get(line)
    idx = (n - 1) // 2
    if not ln or idx >= len(ln.args) or ln.args[idx] != "ON":
        return None
    return f"{fam}/{(n + 1 if n % 2 else n - 1):02d}"


def _link_pref_on(scene: Scene, pref: str) -> bool:
    ln = scene.get("/config/linkcfg")
    i = LINKCFG[pref]
    return bool(ln) and i < len(ln.args) and ln.args[i] == "ON"


def link_targets(scene: Scene, strip: int | str, pref: str,
                 linked: bool | None) -> list[str]:
    path = _strip(strip)
    partner = pair_linked(scene, path)
    if partner is None or linked is False:
        return [path]
    if linked or _link_pref_on(scene, pref):
        return [path, partner]
    return [path]


# ---- EQ ---------------------------------------------------------------------
def set_eq_band(scene: Scene, strip: int | str, band: int, *, type: str | None = None,
                freq: float | None = None, gain: float | None = None,
                q: float | None = None, linked: bool | None = None) -> list[str]:
    """Edit one EQ band. strip = channel int or path ('/bus/01'). Bands: 1-4 channel, 1-6
    bus/main. On a stereo-linked pair with EQ link on, mirrors to the partner strip unless
    linked=False."""
    paths = link_targets(scene, strip, "eq", linked)
    for path in paths:
        _set_eq_band_one(scene, path, band, type=type, freq=freq, gain=gain, q=q)
    return paths


def _set_eq_band_one(scene: Scene, path: str, band: int, *, type: str | None,
                     freq: float | None, gain: float | None, q: float | None) -> None:
    ln = _line(scene, f"{path}/eq/{band}")
    if type is not None:
        if type not in EQ_TYPES:
            raise ValueError(f"eq type {type!r} not in {EQ_TYPES}")
        ln.set_arg(0, type)
    if freq is not None:
        _rng("freq", freq, 20, 20000)
        ln.set_arg(1, fmt_freq(freq))
    if gain is not None:
        _rng("gain", gain, -15, 15)
        ln.set_arg(2, fmt_gain(gain))
    if q is not None:
        _rng("q", q, 0.3, 10)
        ln.set_arg(3, _fmt_q(q))


LOWCUT_SLOPES = (12, 18, 24)


def set_lowcut(scene: Scene, strip: int | str, *, on: bool | None = None,
               freq: float | None = None, slope: int | None = None,
               linked: bool | None = None) -> list[str]:
    """Low-cut, stored in /preamp. Channel strips only — aux-in and FX-return preamps
    carry just trim + invert. On a stereo-linked pair with head-amp link on, mirrors to
    the partner strip unless linked=False."""
    paths = link_targets(scene, strip, "hadly", linked)
    for path in paths:
        _set_lowcut_one(scene, path, on=on, freq=freq, slope=slope)
    return paths


def _set_lowcut_one(scene: Scene, path: str, *, on: bool | None, freq: float | None,
                    slope: int | None) -> None:
    ln = _line(scene, f"{path}/preamp")
    if len(ln.args) < 5:
        raise ValueError(f"{path} has no low cut "
                         f"(/preamp carries {len(ln.args)} fields)")
    if on is not None:
        ln.set_arg(2, "ON" if on else "OFF")
    if slope is not None:
        if slope not in LOWCUT_SLOPES:
            raise ValueError(f"lowcut slope {slope} not in {LOWCUT_SLOPES}")
        ln.set_arg(3, str(slope))
    if freq is not None:
        _rng("lowcut freq", freq, 20, 400)
        # bare-integer HPF field; round half-up — banker's would send 100.5 down, 101.5 up
        ln.set_arg(4, f"{int(freq + 0.5)}")


# ---- Compressor / dynamics --------------------------------------------------
COMP_DETECTORS = ("PEAK", "RMS")


def set_comp(scene: Scene, strip: int | str, *, thr: float | None = None, ratio: str | None = None,
             knee: int | None = None, makeup: float | None = None, attack: float | None = None,
             hold: float | None = None, release: float | None = None,
             mix: int | None = None, on: bool | None = None, det: str | None = None,
             linked: bool | None = None) -> list[str]:
    """Edit a compressor (/dyn) on any strip that has one. ratio is an enum string. On a
    stereo-linked pair with dynamics link on, mirrors to the partner strip unless
    linked=False."""
    paths = link_targets(scene, strip, "dyn", linked)
    for path in paths:
        _set_comp_one(scene, path, thr=thr, ratio=ratio, knee=knee, makeup=makeup,
                      attack=attack, hold=hold, release=release, mix=mix, on=on, det=det)
    return paths


def _set_comp_one(scene: Scene, path: str, *, thr: float | None, ratio: str | None,
                  knee: int | None, makeup: float | None, attack: float | None,
                  hold: float | None, release: float | None, mix: int | None,
                  on: bool | None, det: str | None) -> None:
    ln = _line(scene, f"{path}/dyn")
    if on is not None:
        ln.set_arg(0, "ON" if on else "OFF")
    if det is not None:
        if det not in COMP_DETECTORS:
            raise ValueError(f"detector {det!r} not in {COMP_DETECTORS}")
        ln.set_arg(2, det)
    if thr is not None:
        _rng("thr", thr, -60, 0)
        ln.set_arg(4, f"{thr:.1f}")
    if ratio is not None:
        ratio = COMP_RATIO_ALIASES.get(ratio, ratio)
        if ratio not in COMP_RATIOS:
            raise ValueError(f"ratio {ratio!r} not in {COMP_RATIOS}")
        ln.set_arg(5, ratio)
    if knee is not None:
        _rng("knee", knee, 0, 5)
        ln.set_arg(6, str(knee))
    if makeup is not None:
        _rng("makeup", makeup, 0, 24)
        ln.set_arg(7, _fmt_3sig(makeup))
    if attack is not None:
        _rng("attack", attack, 0, 120)
        ln.set_arg(8, f"{attack:g}")
    if hold is not None:
        _rng("hold", hold, 0.02, 2000)
        ln.set_arg(9, _fmt_3sig(hold))
    if release is not None:
        _rng("release", release, 5, 4000)
        ln.set_arg(10, f"{release:g}")
    if mix is not None:
        _rng("mix", mix, 0, 100)
        # /mtx and /main dyn lines omit keysrc, putting mix one index earlier
        ln.set_arg(13 if len(ln.args) >= 15 else 12, str(mix))


# ---- Gate -------------------------------------------------------------------
def set_gate(scene: Scene, strip: int | str, *, mode: str | None = None, thr: float | None = None,
             rng: float | None = None, attack: float | None = None, hold: float | None = None,
             release: float | None = None, linked: bool | None = None) -> list[str]:
    """Edit a gate (/gate). rng = gate depth in dB. Channels/auxin only (buses have no
    gate). On a stereo-linked pair with dynamics link on, mirrors to the partner strip
    unless linked=False."""
    paths = link_targets(scene, strip, "dyn", linked)
    for path in paths:
        _set_gate_one(scene, path, mode=mode, thr=thr, rng=rng, attack=attack, hold=hold,
                      release=release)
    return paths


def _set_gate_one(scene: Scene, path: str, *, mode: str | None, thr: float | None,
                  rng: float | None, attack: float | None, hold: float | None,
                  release: float | None) -> None:
    ln = _line(scene, f"{path}/gate")
    if mode is not None:
        if mode not in GATE_MODES:
            raise ValueError(f"gate mode {mode!r} not in {GATE_MODES}")
        ln.set_arg(1, mode)
    if thr is not None:
        _rng("thr", thr, -80, 0)
        ln.set_arg(2, f"{thr:.1f}")
    if rng is not None:
        _rng("range", rng, 3, 60)  # console minimum is 3 dB
        ln.set_arg(3, f"{rng:.1f}")
    if attack is not None:
        _rng("attack", attack, 0, 120)
        ln.set_arg(4, f"{attack:g}")
    if hold is not None:
        _rng("hold", hold, 0.02, 2000)
        ln.set_arg(5, _fmt_3sig(hold))
    if release is not None:
        _rng("release", release, 5, 4000)
        ln.set_arg(6, f"{release:g}")
