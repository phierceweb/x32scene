"""CLI glue for `--console MODEL`: the model's main output jack count, reconciled with a
config's ``monitor.physical_outputs``."""

from __future__ import annotations

from pf_core.exceptions import InvalidInputError

from .services import console_models as _models
from .services import preflight as _preflight

_ABSENT = object()


def _declared(expected: dict | None) -> object:
    mon = expected.get("monitor") if expected is not None else None
    return mon.get("physical_outputs", _ABSENT) if isinstance(mon, dict) else _ABSENT


def jack_count(console: str | None, expected: dict | None) -> int | None:
    """The model's count when one is named, else the config's; a config declaring another
    count is refused."""
    if not console:
        return None if expected is None else _preflight.physical_outputs(expected)
    model = _models.console_model(console)
    n = _models.MAIN_JACKS[model]
    declared = _declared(expected)
    if declared is not _ABSENT and (declared != n or isinstance(declared, bool)):
        raise InvalidInputError(
            f"console {_models.MODELS[model]} (--console or X32SCENE_CONSOLE) has {n} main "
            f"output jacks, but the config declares monitor.physical_outputs {declared!r}")
    return n


def config_jacks(args) -> int | None:
    """`ports` and `report`: the count from ``--console``, ``--config`` or both."""
    expected = _preflight.load_expected(args.config) if args.config else None
    return jack_count(args.console, expected)


def with_console(expected: dict, console: str | None) -> dict:
    """``expected`` with the model's count filled in where the config declares none."""
    n = jack_count(console, expected)
    mon = expected.get("monitor", {})
    if not console or not isinstance(mon, dict) or "physical_outputs" in mon:
        return expected
    return {**expected, "monitor": {**mon, "physical_outputs": n}}
