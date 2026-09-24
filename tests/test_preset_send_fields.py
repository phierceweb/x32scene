"""A preset's send line against the scene's: a desk-written line short of the bus's fields
keeps the target's last ones, a line without on and level or longer than its bus is refused
before anything is written, and presets-diff compares the fields a preset carries."""

import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.orchestrators.band_swap import build
from x32scene.services import preset_library as lib
from x32scene.services.presets import apply_preset

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIX, "example.scn")
# the shape a #2.1# desk preset writes: no pan-follow field on the odd bus
FOUR = "/mix/13 ON   -oo +0 EQ->\n/mix/14 ON   -oo\n"


class ShortDeskLineTest(unittest.TestCase):
    def test_a_four_field_odd_send_keeps_the_targets_pan_follow(self):
        sc = Scene.load(SCENE)
        follow = sc.get("/ch/03/mix/13").args[4]
        apply_preset(sc, 3, FOUR)
        self.assertEqual(sc.get("/ch/03/mix/13").args, ["ON", "-oo", "+0", "EQ->", follow])
        self.assertEqual(sc.get("/ch/03/mix/14").args, ["ON", "-oo"])

    def test_band_setup_takes_a_four_field_preset(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        chn = os.path.join(d, "four.chn")
        with open(chn, "w", encoding="utf-8", newline="") as fh:
            fh.write(FOUR)
        edited, rep = build(SCENE, {"channels": {"3": {"preset": chn}}})
        self.assertEqual(rep["malformed"], [])
        self.assertEqual(len(edited.get("/ch/03/mix/13").args), 5)

    def test_presets_diff_matches_after_the_apply(self):
        sc = Scene.load(SCENE)
        apply_preset(sc, 3, FOUR)
        r = lib.check_preset(sc, "Snare Top.chn", FOUR)
        self.assertEqual((r.status, r.compared, r.drift), (lib.MATCH, 2, []))


class MalformedSendTest(unittest.TestCase):
    def _refused(self, text: str, path: str) -> None:
        sc = Scene.load(SCENE)
        before = sc.dump()
        with self.assertRaises(ValueError) as cm:
            apply_preset(sc, 3, text)
        self.assertIn(path, str(cm.exception))
        self.assertEqual(sc.dump(), before)

    def test_a_send_without_its_level_is_refused(self):
        self._refused("/mix/13 ON\n", "/mix/13")

    def test_a_send_without_its_level_on_a_linked_bus_is_refused(self):
        self._refused("/mix/03 ON\n", "/mix/03")

    def test_an_odd_send_longer_than_its_bus_is_refused(self):
        self._refused("/mix/13 ON -oo +0 POST 0 7\n", "/mix/13")

    def test_an_even_send_longer_than_its_bus_is_refused(self):
        self._refused("/mix/14 ON -oo +0\n", "/mix/14")

    def test_a_malformed_send_outside_the_scope_is_not_refused(self):
        sc = Scene.load(SCENE)
        apply_preset(sc, 3, "/mix/13 ON\n", ["eq"])
        self.assertEqual(sc.dump(), Scene.load(SCENE).dump())


if __name__ == "__main__":
    unittest.main()
