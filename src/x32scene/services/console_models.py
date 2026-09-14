"""Console models by the name ``/xinfo`` reports, and how many ``/outputs/main`` have a rear
XLR jack on each: outputs 1 to N are the jacks (none on a model with 0), and the rest leave
the console only through an AES50 or card block or a user-out slot. Every count is from the
model's own manual; ``docs/preflight-config.md`` lists the sources.
"""

from __future__ import annotations

__all__ = ["MAIN_JACKS", "MODELS", "console_model", "main_jacks"]

MODELS: dict[str, str] = {
    "X32": "X32", "X32P": "X32 Producer", "X32C": "X32 Compact", "X32RACK": "X32 Rack",
    "X32CORE": "X32 Core", "M32": "M32", "M32C": "M32C", "M32R": "M32R",
}
MAIN_JACKS: dict[str, int] = {
    "X32": 16, "X32P": 8, "X32C": 8, "X32RACK": 8, "X32CORE": 0,
    "M32": 16, "M32R": 8, "M32C": 0,
}


def _key(name: str) -> str:
    return "".join(ch for ch in name.upper() if ch.isalnum())


_BY_KEY = {_key(s): model for model, product in MODELS.items() for s in (model, product)}


def _known() -> str:
    return ", ".join(m if MODELS[m] == m else f"{m} ({MODELS[m]})" for m in sorted(MAIN_JACKS))


def console_model(name: str) -> str:
    """The ``/xinfo`` model string for ``name``, given either that string or the product name,
    in any case (``X32RACK``, ``"x32 rack"``).

    Raises:
        ValueError: the name is not a model.
    """
    model = _BY_KEY.get(_key(name))
    if model is None:
        raise ValueError(f"unknown console model {name!r}; known: {_known()}")
    return model


def main_jacks(name: str) -> int:
    """How many ``/outputs/main`` have a rear XLR jack on the named model."""
    return MAIN_JACKS[console_model(name)]
