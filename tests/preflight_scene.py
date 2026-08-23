"""Shared mini-scene for the preflight test modules. Not collected by pytest.

Every routing, output, link and mute line below is COPIED from tests/fixtures/example.scn by the
script that generated this file, never hand-typed: a hand-typed line can encode a shape no
console ever wrote and hide the corruption a check exists to catch. The channel, head-amp
and FX lines are the original hand-built minimum the channel checks need.
"""

from x32scene.model import Scene

HEADER = '#4.0# "Test Scene" "" %000000000 1'.ljust(127)

# verbatim from tests/fixtures/example.scn
FIXTURE_LINES = [
    '/config/chlink OFF OFF OFF OFF OFF ON OFF ON OFF OFF OFF OFF OFF ON OFF ON',
    '/config/auxlink OFF OFF ON ON',
    '/config/fxlink ON ON ON ON',
    '/config/buslink ON ON ON ON ON ON OFF OFF',
    '/config/mtxlink OFF OFF OFF',
    '/config/mute OFF OFF OFF OFF OFF OFF',
    '/config/linkcfg ON ON ON ON',
    '/config/userrout/out 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0',
    '/config/userrout/in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 33 34 35 36 37 38 39 40 41 42 43 44 157 158 129 130',
    '/config/routing REC',
    '/config/routing/IN UIN1-8 UIN9-16 UIN17-24 UIN25-32 AUX1-4',
    '/config/routing/AES50A UOUT1-8 OUT9-16 UOUT17-24 UOUT25-32 UOUT33-40 UOUT41-48',
    '/config/routing/AES50B UOUT1-8 UOUT9-16 OUT1-8 UOUT41-48 UOUT41-48 UOUT41-48',
    '/config/routing/CARD UOUT1-8 UOUT9-16 UOUT17-24 UOUT25-32',
    '/config/routing/OUT OUT1-4 OUT5-8 OUT9-12 OUT13-16',
    '/config/routing/PLAY CARD1-8 CARD9-16 CARD17-24 CARD25-32 AUX1-4',
    '/outputs/main/01 4 POST OFF',
    '/outputs/main/01/delay OFF   0.3',
    '/outputs/main/02 5 POST OFF',
    '/outputs/main/02/delay OFF   0.3',
    '/outputs/main/03 6 POST OFF',
    '/outputs/main/03/delay OFF   0.3',
    '/outputs/main/04 7 POST OFF',
    '/outputs/main/04/delay OFF   0.3',
    '/outputs/main/05 14 POST OFF',
    '/outputs/main/05/delay OFF   0.3',
    '/outputs/main/06 15 POST OFF',
    '/outputs/main/06/delay OFF   0.3',
    '/outputs/main/07 1 POST OFF',
    '/outputs/main/07/delay OFF   0.3',
    '/outputs/main/08 2 POST OFF',
    '/outputs/main/08/delay OFF   0.3',
    '/outputs/main/09 6 POST OFF',
    '/outputs/main/09/delay OFF   0.3',
    '/outputs/main/10 7 POST OFF',
    '/outputs/main/10/delay OFF   0.3',
    '/outputs/main/11 10 POST OFF',
    '/outputs/main/11/delay OFF   0.3',
    '/outputs/main/12 11 POST OFF',
    '/outputs/main/12/delay OFF   0.3',
    '/outputs/main/13 8 POST OFF',
    '/outputs/main/13/delay OFF   0.3',
    '/outputs/main/14 9 POST OFF',
    '/outputs/main/14/delay OFF   0.3',
    '/outputs/main/15 4 POST OFF',
    '/outputs/main/15/delay OFF   0.3',
    '/outputs/main/16 5 POST OFF',
    '/outputs/main/16/delay OFF   0.3',
    '/outputs/aux/01 10 POST OFF',
    '/outputs/aux/02 11 POST OFF',
    '/outputs/aux/03 8 POST OFF',
    '/outputs/aux/04 9 POST OFF',
    '/outputs/aux/05 12 POST OFF',
    '/outputs/aux/06 13 POST OFF',
    '/outputs/p16/01 26 PRE OFF',
    '/outputs/p16/01/iQ OFF none Linear 0',
    '/outputs/p16/02 28 PRE OFF',
    '/outputs/p16/02/iQ OFF none Linear 0',
    '/outputs/p16/03 30 PRE OFF',
    '/outputs/p16/03/iQ OFF none Linear 0',
    '/outputs/p16/04 31 PRE OFF',
    '/outputs/p16/04/iQ OFF none Linear 0',
    '/outputs/p16/05 32 PRE OFF',
    '/outputs/p16/05/iQ OFF none Linear 0',
    '/outputs/p16/06 34 PRE OFF',
    '/outputs/p16/06/iQ OFF none Linear 0',
    '/outputs/p16/07 35 PRE OFF',
    '/outputs/p16/07/iQ OFF none Linear 0',
    '/outputs/p16/08 36 PRE OFF',
    '/outputs/p16/08/iQ OFF none Linear 0',
    '/outputs/p16/09 37 PRE OFF',
    '/outputs/p16/09/iQ OFF none Linear 0',
    '/outputs/p16/10 42 PRE OFF',
    '/outputs/p16/10/iQ OFF none Linear 0',
    '/outputs/p16/11 45 PRE OFF',
    '/outputs/p16/11/iQ OFF none Linear 0',
    '/outputs/p16/12 47 PRE OFF',
    '/outputs/p16/12/iQ OFF none Linear 0',
    '/outputs/p16/13 48 PRE OFF',
    '/outputs/p16/13/iQ OFF none Linear 0',
    '/outputs/p16/14 49 PRE OFF',
    '/outputs/p16/14/iQ OFF none Linear 0',
    '/outputs/p16/15 50 PRE OFF',
    '/outputs/p16/15/iQ OFF none Linear 0',
    '/outputs/p16/16 51 PRE OFF',
    '/outputs/p16/16/iQ OFF none Linear 0',
    '/outputs/aes/01 1 POST OFF',
    '/outputs/aes/02 2 POST OFF',
    '/outputs/rec/01 1 <-EQ',
    '/outputs/rec/02 2 <-EQ',
]

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
