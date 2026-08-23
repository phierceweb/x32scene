"""FX rack read/edit.

``FX_PARAMS`` holds the parameter order for every effect type, each corroborated against a
line a console wrote; those read and write. The graphic EQs (GEQ, GEQ2, TEQ, TEQ2) decode for
reading only — the band labels are the standard ISO series, not desk-verified.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import HEADER_WIDTH, Scene, check_token
from ..tables_fx import (
    FX_DEFAULTS, FX_DISPLAY_TYPE, FX_PARAMS, FX_SIDE_RACK_TYPES, FX_TYPES, decode_fx,
    geq_param_names,
)

FX_SOURCES = ("INS", *[f"MIX{n}" for n in range(1, 17)], "M/C")


# read-only: GEQ/GEQ2 band names, computed rather than listed in FX_PARAMS so
# set_fx_param keeps refusing them.
_GEQ_NAMES = {"GEQ": geq_param_names(dual=False), "GEQ2": geq_param_names(dual=True),
              "TEQ": geq_param_names(dual=False), "TEQ2": geq_param_names(dual=True)}


@dataclass
class FxSlot:
    slot: int
    code: str
    name: str
    source: str | None
    params: dict[str, str]  # empty if the type's layout is unknown
    verified: bool = False  # order corroborated against a real file (FX_PARAMS)


def read_fx(scene: Scene) -> list[FxSlot]:
    out: list[FxSlot] = []
    for n in range(1, 9):
        tline = scene.get(f"/fx/{n}")
        if not tline or not tline.args:
            continue
        code = tline.args[0]
        src = scene.get(f"/fx/{n}/source")
        source = src.args[0] if src and src.args else None
        params: dict[str, str] = {}
        names = FX_PARAMS.get(code) or _GEQ_NAMES.get(code)
        par = scene.get(f"/fx/{n}/par")
        if names and par:
            params = {nm: par.args[i] for i, nm in enumerate(names) if i < len(par.args)}
        out.append(FxSlot(n, code, decode_fx(code), source, params, code in FX_PARAMS))
    return out


def set_fx_param(scene: Scene, slot: int, param: str, raw_value: str) -> None:
    """Set one FX parameter by name. raw_value is the exact X32 token (e.g. '5k06', '+10',
    '30') — FX params have type-specific formats, so the caller supplies the literal token.
    """
    tline = scene.get(f"/fx/{slot}")
    if not tline or not tline.args:
        raise KeyError(f"no /fx/{slot}")
    code = tline.args[0]
    names = FX_PARAMS.get(code)
    if not names:
        why = "read-only (band labels not desk-verified)" if code in _GEQ_NAMES else "unknown"
        raise ValueError(f"FX type {code!r} param layout {why} — refusing to write")
    try:
        i = names.index(param)
    except ValueError:
        raise ValueError(f"{param!r} not in {code} params {names}") from None
    par = scene.get(f"/fx/{slot}/par")
    if par is None:
        raise KeyError(f"no /fx/{slot}/par")
    if i >= len(par.args):
        raise ValueError(f"/fx/{slot}/par carries {len(par.args)} value(s) — "
                         f"no slot {i} for {param!r}")
    par.set_arg(i, raw_value)


# ---- writing: values by name, type changes, effect presets -------------------------
def param_names(code: str) -> list[str]:
    return FX_PARAMS.get(code) or _GEQ_NAMES.get(code) or []


def fx_defaults(code: str) -> list[str]:
    """The 64 parameter tokens a console writes when a slot switches to ``code``."""
    toks = FX_DEFAULTS[code].split(" ")
    return toks + ["0"] * (64 - len(toks))


def format_like(default: str, value: float | int | str) -> str:
    """A parameter token in the format of the desk's own default for that slot: same
    decimals, same sign style, the same `k` notation for frequencies. A non-numeric
    value (an enum token like ``SER`` or ``3/8``) passes through as typed."""
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return value
    if "k" in default:
        digits = len(default.split("k")[1])
        if value >= 1000:
            return f"{value / 1000:.{digits}f}".replace(".", "k")
        return f"{value:.0f}" if digits == 1 else f"{value:.1f}"
    sign = "+" if default.startswith("+") or default.startswith("-") and default != "-0" else ""
    if "." in default:
        tok = f"{value:{sign}.{len(default.split('.')[1])}f}"
    else:
        tok = f"{value:{sign}.0f}"
    return tok.replace("+0.", "0.") if sign and tok.startswith("+0.") and float(value) == 0 else tok


def set_fx_type(scene: Scene, slot: int, code: str) -> None:
    """Switch a slot's effect type and reset its parameters to the desk's defaults, as
    the console does; slots 5-8 take only the side-rack types."""
    if code not in FX_TYPES:
        raise ValueError(f"unknown FX type {code!r}; see `x32scene fx-types`")
    if slot >= 5 and code not in FX_SIDE_RACK_TYPES:
        raise ValueError(f"{code} ({decode_fx(code)}) cannot go in FX{slot}: slots 5-8 take "
                         "the insert-style types only (`x32scene fx-types`)")
    tline = scene.get(f"/fx/{slot}")
    par = scene.get(f"/fx/{slot}/par")
    if tline is None or par is None:
        raise KeyError(f"no /fx/{slot}")
    tline.args = [code]
    tline.rebuild()
    par.args = fx_defaults(code)
    par.rebuild()


def set_fx_source(scene: Scene, slot: int, left: str, right: str | None = None) -> None:
    ln = scene.get(f"/fx/{slot}/source")
    if ln is None:
        raise KeyError(f"/fx/{slot} has no source line (slots 5-8 are inserts)")
    for tok in (left, right or left):
        if tok not in FX_SOURCES:
            raise ValueError(f"FX source must be one of {', '.join(FX_SOURCES)}, got {tok!r}")
    ln.args = [left, right or left]
    ln.rebuild()


def set_fx_params(scene: Scene, slot: int, values: dict[str, float | int | str]) -> None:
    """Set parameters by name with values formatted like the desk's defaults."""
    tline = scene.get(f"/fx/{slot}")
    if not tline or not tline.args:
        raise KeyError(f"no /fx/{slot}")
    code = tline.args[0]
    defaults = fx_defaults(code)
    names = param_names(code)
    for name, value in values.items():
        if name not in names:
            raise ValueError(f"{name!r} is not a {code} parameter; "
                             f"see `x32scene fx-types {code}`")
        set_fx_param(scene, slot, name, format_like(defaults[names.index(name)], value))


def extract_fx(scene: Scene, slot: int, name: str) -> str:
    """The slot as an effect preset (`.efx`): header, then the slash-less
    ``type`` / ``source`` / ``par`` lines the console's library writes."""
    tline, par = scene.get(f"/fx/{slot}"), scene.get(f"/fx/{slot}/par")
    if not tline or not tline.args or par is None:
        raise KeyError(f"no /fx/{slot}")
    code = tline.args[0]
    check_token(f'"{name}"')
    head = f'#4.0# 1 "{name}" 1 {FX_DISPLAY_TYPE.get(code, 0)} 1'.ljust(HEADER_WIDTH)
    lines = [head, f"type {code}"]
    src = scene.get(f"/fx/{slot}/source")
    if src is not None:
        lines.append("source " + " ".join(src.args))
    lines.append("par" + par.raw[len(par.path):])
    return "\n".join(lines) + "\n"


def apply_fx(scene: Scene, slot: int, text: str, *, source: bool = False) -> str:
    """Load an effect preset into a slot: type and parameters, and the source only when
    asked (the console's library load leaves the source alone)."""
    body = {ln.path: ln for ln in Scene.parse(text).lines if ln.path in ("type", "source", "par")}
    if "type" not in body or "par" not in body:
        raise ValueError("not an effect preset: needs `type` and `par` lines")
    code = body["type"].args[0]
    set_fx_type(scene, slot, code)
    par = scene.get(f"/fx/{slot}/par")
    par.args = body["par"].args
    par.rebuild()
    if source and "source" in body and scene.get(f"/fx/{slot}/source") is not None:
        set_fx_source(scene, slot, *body["source"].args[:2])
    return code
