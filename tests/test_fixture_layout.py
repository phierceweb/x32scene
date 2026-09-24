"""The example scenes hold no dynamics value whose padding no desk-written file shows: a
release of 1000 or more, or a compressor mix below 100."""

import os
import re
import unittest

from x32scene.model import Scene

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
DYN = re.compile(r"^/(ch|bus|mtx|main)/\w+/dyn$")
GATE = re.compile(r"^/ch/\d\d/gate$")


class DynamicsLayoutTest(unittest.TestCase):
    def test_release_and_mix_stay_where_a_desk_file_shows_the_padding(self):
        for name in ("example.scn", "example-alt.scn"):
            for ln in Scene.load(os.path.join(FIX, name)).lines:
                if DYN.match(ln.path):
                    mix = ln.args[13 if ln.path.startswith(("/ch/", "/bus/")) else 12]
                    with self.subTest(fixture=name, path=ln.path):
                        self.assertLess(int(ln.args[10]), 1000)
                        self.assertEqual(mix, "100")
                elif GATE.match(ln.path):
                    with self.subTest(fixture=name, path=ln.path):
                        self.assertLess(int(ln.args[6]), 1000)


if __name__ == "__main__":
    unittest.main()
