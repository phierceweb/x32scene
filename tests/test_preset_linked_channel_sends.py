"""A preset applied to one channel of a stereo-linked pair writes its sends to the partner
too, as the desk mirrors a send write across a linked channel pair: on, level and tap, the
pan staying per side. Processing is written to the named channel only."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.presets import apply_preset, mirrored_sends

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
SEND_AND_EQ = "/mix/01 ON -12.0 +0 POST 0\n/eq/1 PEQ 200.0 +3.00 2.0\n"   # ch11/12, buses 1/2 linked
SEND_ONLY = "/mix/01 ON -12.0 +0 POST 0\n"


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class ApplyToLinkedChannelTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(SCENE)
        self.partner_eq = self.sc.get("/ch/12/eq/1").args[:]
        self.partner_pan = self.sc.get("/ch/12/mix/01").args[2]

    def test_the_partner_takes_on_level_and_tap_and_keeps_its_pan(self):
        apply_preset(self.sc, 11, SEND_AND_EQ)
        self.assertEqual(self.sc.get("/ch/11/mix/01").args, ["ON", "-12.0", "+0", "POST", "0"])
        self.assertEqual(self.sc.get("/ch/12/mix/01").args,
                         ["ON", "-12.0", self.partner_pan, "POST", "0"])
        self.assertEqual(self.sc.get("/ch/11/mix/02").args, ["ON", "-12.0"])
        self.assertEqual(self.sc.get("/ch/12/mix/02").args, ["ON", "-12.0"])
        self.assertEqual(Scene.parse(self.sc.dump()).dump(), self.sc.dump())

    def test_processing_stays_on_the_named_channel(self):
        apply_preset(self.sc, 11, SEND_AND_EQ)
        self.assertEqual(self.sc.get("/ch/11/eq/1").args, ["PEQ", "200.0", "+3.00", "2.0"])
        self.assertEqual(self.sc.get("/ch/12/eq/1").args, self.partner_eq)

    def test_mirrored_sends_names_both_axes(self):
        got = set(mirrored_sends(self.sc, 11, SEND_ONLY))
        self.assertEqual(got, {("/ch/11/mix/02", "/mix/01"), ("/ch/12/mix/01", "/mix/01"),
                               ("/ch/12/mix/02", "/mix/01")})

    def test_an_unlinked_channel_mirrors_across_buses_only(self):
        self.assertEqual(mirrored_sends(self.sc, 1, SEND_ONLY), [("/ch/01/mix/02", "/mix/01")])


class LinkedChannelCliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def preset(self, text):
        path = os.path.join(self.dir, "p.chn")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_apply_preset_names_the_partner_sends_and_the_processing_left_one_sided(self):
        rc, out, err = _run(["apply-preset", SCENE, "11", self.preset(SEND_AND_EQ),
                             "-o", os.path.join(self.dir, "out.scn")])
        self.assertEqual(rc, 0, err)
        self.assertIn("mirrored /ch/12/mix/01 from /mix/01, /ch/12/mix/02 from /mix/01 onto "
                      "the stereo-linked ch12", out)
        self.assertIn("ch12 keeps its own processing", out)

    def test_a_send_only_preset_says_nothing_of_processing(self):
        rc, out, _ = _run(["apply-preset", SCENE, "11", self.preset(SEND_ONLY),
                           "-o", os.path.join(self.dir, "out.scn")])
        self.assertEqual(rc, 0)
        self.assertNotIn("keeps its own processing", out)

    def test_band_setup_verifies_and_marks_the_partner_sends(self):
        plan = os.path.join(self.dir, "plan.json")
        with open(plan, "w", encoding="utf-8") as fh:
            json.dump({"channels": {"11": {"preset": self.preset(SEND_ONLY)}}}, fh)
        rc, out, err = _run(["band-setup", SCENE, plan, "-o", os.path.join(self.dir, "o.scn")])
        self.assertEqual(rc, 0, err)
        row = next(ln for ln in out.splitlines() if "/ch/12/mix/01" in ln or "ch 12" in ln)
        self.assertIn("mirrored", out[out.index(row):])


if __name__ == "__main__":
    unittest.main()
