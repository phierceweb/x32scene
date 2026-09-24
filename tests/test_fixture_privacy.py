"""Opt-in: no committed fixture carries a real scene's mix or wiring.

Point ``X32SCENE_CORPUS`` at a directory of real console exports. Each fixture is compared
line by line with every ``.scn`` under it, and the closest corpus scene decides:

- **mix**: of the fixture's processing lines (EQ, dynamics, gate, preamp, head amp, insert,
  delay, main mix and sends) whose value differs from the corpus's most common value at
  that path, the share equal to one corpus scene that carries a mix (a send ON above -oo).
  A scene with no live send is an initialized desk, with no mix to leak.
- **wiring**: of the fixture's ``/config/routing/*``, ``/config/userrout/*`` and
  ``/outputs/*`` lines, less those holding the value the console ships with, the share
  equal to one corpus scene.

A fixture fails when a share exceeds its limit on at least ``MIN_HITS`` lines. The limit
sits well above what two unrelated scenes share and well below what a scene shares with
one saved from it. A preset is compared on every channel it could have come from.
Messages carry counts and file paths, never a value.
"""

import glob
import os
import re
import unittest
from collections import Counter

from x32scene.model import Scene

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
CORPUS = os.environ.get("X32SCENE_CORPUS")
MIX_MAX = WIRING_MAX = 0.2
MIN_HITS = 2
PROC = re.compile(r"^/((ch|bus|auxin|fxrtn|mtx|main)/[^/]+/(eq|dyn|gate|preamp|mix|insert|delay)"
                  r"(/|$)|headamp/)")
WIRING = re.compile(r"^/(config/routing|config/userrout|outputs)/")
SEND = re.compile(r"^/(ch|auxin|fxrtn)/\d\d/mix/\d\d$")
SHIPS_WITH = [(re.compile(r"^/outputs/\w+/\d\d/delay$"), ("OFF", "0.3")),
              (re.compile(r"^/outputs/p16/\d\d/iQ$"), ("OFF", "none", "Linear", "0")),
              (re.compile(r"^/config/routing/OUT$"), ("OUT1-4", "OUT5-8", "OUT9-12", "OUT13-16"))]


def _lines(scene: Scene) -> dict[str, tuple[str, ...]]:
    return {ln.path: tuple(ln.args) for ln in scene.lines if ln.path.startswith("/")}


def _ships_with(path: str, args: tuple[str, ...]) -> bool:
    return any(rx.match(path) and args == value for rx, value in SHIPS_WITH)


@unittest.skipUnless(CORPUS, "set X32SCENE_CORPUS to a scene directory to run")
class FixturePrivacyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        files = sorted(glob.glob(os.path.join(CORPUS, "**", "*.scn"), recursive=True))
        cls.corpus = [(p, _lines(Scene.load(p))) for p in files]
        counts: dict[str, Counter] = {}
        for _, lines in cls.corpus:
            for path, args in lines.items():
                counts.setdefault(path, Counter())[args] += 1
        cls.modal = {path: c.most_common(1)[0][0] for path, c in counts.items()}
        cls.mixes = [(p, d) for p, d in cls.corpus
                     if any(SEND.match(k) and v[:1] == ("ON",) and v[1:2] != ("-oo",)
                            for k, v in d.items())]

    def setUp(self):
        self.assertTrue(self.corpus, f"no .scn file under {CORPUS}")

    def _assert_unlike(self, name: str, lines: dict, kind: str) -> None:
        if kind == "mix":
            keys = [k for k in lines if PROC.match(k) and k in self.modal
                    and lines[k] != self.modal[k]]
            scenes, limit = self.mixes, MIX_MAX
        else:
            keys = [k for k in lines if WIRING.match(k) and not _ships_with(k, lines[k])]
            scenes, limit = self.corpus, WIRING_MAX
        if not keys or not scenes:
            return
        hits, path = max((sum(1 for k in keys if d.get(k) == lines[k]), p) for p, d in scenes)
        self.assertFalse(
            hits >= MIN_HITS and hits / len(keys) > limit,
            f"{name}: {hits} of {len(keys)} {kind} lines equal {path}")

    def test_scenes_carry_no_real_mix_or_wiring(self):
        for name in ("example.scn", "example-alt.scn"):
            lines = _lines(Scene.load(os.path.join(FIX, name)))
            for kind in ("mix", "wiring"):
                with self.subTest(fixture=name, kind=kind):
                    self._assert_unlike(name, lines, kind)

    def test_snippet_and_routing_preset_carry_none_either(self):
        for name, kind in (("example.snp", "mix"), ("example.rou", "wiring")):
            with self.subTest(fixture=name):
                self._assert_unlike(name, _lines(Scene.load(os.path.join(FIX, name))), kind)

    def test_channel_preset_matches_no_channel_of_a_real_scene(self):
        bare = _lines(Scene.load(os.path.join(FIX, "example.chn")))
        for ch in range(1, 33):
            with self.subTest(channel=ch):
                self._assert_unlike(
                    f"example.chn on /ch/{ch:02d}",
                    {k if k.startswith("/headamp/") else f"/ch/{ch:02d}{k}": v
                     for k, v in bare.items()}, "mix")


if __name__ == "__main__":
    unittest.main(verbosity=2)
