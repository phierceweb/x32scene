"""CLI glue for `--console MODEL`: the model's main output jack count, reconciled with a
config's ``monitor.physical_outputs``."""

from __future__ import annotations

from pf_core.exceptions import InvalidInputError

from .services import console_models as _models
from .services import preflight as _preflight
from .services import preflight_monitor as _monitor


def _model_count(console: str, declared: int | None) -> int:
    model = _models.console_model(console)
    n = _models.MAIN_JACKS[model]
    if declared is not None and declared != n:
        raise InvalidInputError(
            f"console {_models.MODELS[model]} (--console or X32SCENE_CONSOLE) has {n} main "
            f"output jacks, but the config declares monitor.physical_outputs {declared}")
    return n


def jack_count(console: str | None, expected: dict | None) -> int | None:
    """The model's count when one is named, else the config's. A declared count that is not
    a whole number 0-16 raises ValueError; a whole one other than the model's is refused."""
    declared = None if expected is None else _preflight.physical_outputs(expected)
    return _model_count(console, declared) if console else declared


def config_jacks(args) -> int | None:
    """`ports` and `report`: the count from ``--console``, ``--config`` or both."""
    expected = _preflight.load_expected(args.config) if args.config else None
    return jack_count(args.console, expected)


def with_console(expected: dict, console: str | None) -> dict:
    """``expected`` with the model's count filled into a ``monitor`` section that declares
    none. A declared count that is not a whole number 0-16 is left to the monitor check."""
    if not console:
        return expected
    mon = expected.get("monitor")
    if not isinstance(mon, dict):
        _model_count(console, None)
        return expected
    if "physical_outputs" in mon:
        _model_count(console, _monitor.physical_count(mon, []))
        return expected
    return {**expected, "monitor": {**mon, "physical_outputs": _model_count(console, None)}}
