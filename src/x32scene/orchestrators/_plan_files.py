"""The files a band-swap plan reads: the plan itself, and each preset it names."""

from __future__ import annotations

from pathlib import Path

from ..model import Scene, read_file
from ..services.jsonfile import read_json


def load_plan(path: str | Path) -> dict:
    p = Path(path)
    plan = read_json(p)
    if not isinstance(plan, dict):
        raise ValueError(f"{p}: plan must be a JSON object, got {type(plan).__name__}")
    plan["_dir"] = p.parent
    return plan


def plan_inputs(plan: dict) -> list[str]:
    """Every file the plan reads besides itself: presets named by a channel, an FX slot
    or the routing section."""
    base = Path(plan.get("_dir", "."))
    specs = [s for key in ("channels", "fx") if isinstance(plan.get(key), dict)
             for s in plan[key].values() if isinstance(s, dict)]
    if isinstance(plan.get("routing"), dict):
        specs.append(plan["routing"])
    out = []
    for spec in specs:
        name = spec.get("preset")
        if isinstance(name, str):
            q = Path(name)
            out.append(str(q if q.is_absolute() else base / q))
    return out


def preset_text(plan: dict, spec: dict) -> str:
    """The text of the preset ``spec`` names, resolved against the plan's directory;
    ValueError names the file when it cannot be read or parsed."""
    p = Path(spec["preset"])
    if not p.is_absolute():
        p = Path(plan.get("_dir", ".")) / p
    try:
        text = read_file(str(p))
    except OSError as e:
        raise ValueError(f"preset {p}: {e.strerror}") from e
    except ValueError as e:
        raise ValueError(f"preset {e}") from None   # read_file's message opens with the path
    try:
        Scene.parse(text)
    except ValueError as e:
        raise ValueError(f"preset {p}: {e}") from None
    return text
