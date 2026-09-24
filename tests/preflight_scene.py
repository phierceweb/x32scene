"""Shared mini-scene for the preflight test modules. Not collected by pytest.

Every routing, output, link and mute line is read from tests/fixtures/example.scn, never
hand-typed: a hand-typed line can encode a shape no console ever wrote and hide the
corruption a check exists to catch. The channel, head-amp and FX lines are the hand-built
minimum the channel checks need.
"""

import os
import re

from x32scene.model import Scene

HEADER = '#4.0# "Test Scene" "" %000000000 1'.ljust(127)
_COPIED = re.compile(r"^/(config/(chlink|auxlink|fxlink|buslink|mtxlink|mute|linkcfg|userrout/"
                     r"|routing)|outputs/)")
FIXTURE_LINES = [ln.raw for ln in Scene.load(os.path.join(
    os.path.dirname(__file__), "fixtures", "example.scn")).lines if _COPIED.match(ln.path)]

BASE_LINES = [
    HEADER,
    *FIXTURE_LINES,
    '/ch/01/config "Kick" 1 67 1',
    "/ch/01/mix ON   0.0 ON +0 OFF   -oo",
    '/ch/05/config "Rack 1" 1 67 5',
    "/ch/05/mix OFF -2.0 ON +0 OFF   -oo",
    '/ch/20/config "Gtr 1" 1 67 20',
    "/ch/20/mix ON   0.0 ON -94 OFF   -oo",
    "/headamp/000 +27.0 OFF",
    "/headamp/004 +13.0 OFF",
    "/headamp/035 +0.5 OFF",
    "/fx/1 PLAT",
]


def line(path: str) -> str:
    """The base line at an exact path."""
    for raw in BASE_LINES:
        if raw.split(" ", 1)[0] == path:
            return raw
    raise KeyError(path)


def mini_scene(replace: dict[str, str | None] | None = None,
               extra: list[str] | None = None) -> Scene:
    """BASE_LINES with lines swapped by EXACT path (a None value drops the line), plus
    any ``extra`` lines appended."""
    lines = []
    for raw in BASE_LINES:
        path = raw.split(" ", 1)[0]
        if replace and path in replace:
            if replace[path] is not None:
                lines.append(replace[path])
            continue
        lines.append(raw)
    lines.extend(extra or [])
    return Scene.parse("\n".join(lines) + "\n")


def fails(findings):
    return [f for f in findings if f.severity == "FAIL"]


def warns(findings):
    return [f for f in findings if f.severity == "WARN"]
