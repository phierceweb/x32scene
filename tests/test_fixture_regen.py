"""The committed fixtures are what ``tests/fixture_regen.py`` writes from them.

After changing the fixture design, or a writer the generator calls:

    bin/run python -m tests.fixture_regen
"""

import unittest

from x32scene.model import Scene

from tests import fixture_regen as R


class RegenerateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = R.build()

    def test_each_fixture_is_the_generators_output(self):
        for rel, text in self.built.items():
            with self.subTest(fixture=rel):
                with open(R.FIX / rel, encoding="utf-8", newline="") as fh:
                    self.assertEqual(fh.read(), text,
                                     f"{rel}: run bin/run python -m tests.fixture_regen")

    def test_each_fixture_round_trips(self):
        for rel, text in self.built.items():
            with self.subTest(fixture=rel):
                self.assertEqual(Scene.parse(text).dump(), text)

    def test_the_channel_preset_is_extract_preset_output(self):
        """example.chn is `extract-preset` output: /config keeps the source slot a desk-saved
        preset drops, and the main mix stays one line. DeskWrittenPresetTest covers the desk's."""
        chn = Scene.load(str(R.FIX / "example.chn"))
        scene = Scene.load(str(R.FIX / "example.scn"))
        self.assertEqual(chn.get("/config").args, scene.get("/ch/01/config").args)
        self.assertEqual(len(chn.get("/config").args), 4)
        self.assertEqual(chn.get("/mix").args, scene.get("/ch/01/mix").args)


if __name__ == "__main__":
    unittest.main()
