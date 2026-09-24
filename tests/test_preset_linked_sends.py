"""A preset's send to one bus of a stereo-linked pair is written to both buses, as the desk
mirrors a send write across a linked pair: the pair ends at the later of the preset's two
lines, on and level only (pan and tap live on the odd bus's line)."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import preset_library as lib
from x32scene.services.presets import apply_preset, mirrored_sends

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
ONE_SIDE = "/mix/01 ON -12.0 +0 PRE 0\n"                       # buses 1/2 are linked
DISAGREE = "/mix/05 ON -3.0 -20 POST 0\n/mix/06 OFF -oo\n"      # buses 5/6 are linked


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def _args(sc, path):
    return sc.get(path).args


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(SCENE)

    def test_a_one_sided_send_is_mirrored_onto_its_linked_partner(self):
        self.assertEqual(mirrored_sends(self.sc, 1, ONE_SIDE), [("/ch/01/mix/02", "/mix/01")])
        self.assertEqual(apply_preset(self.sc, 1, ONE_SIDE), 2)
        self.assertEqual(_args(self.sc, "/ch/01/mix/01"), ["ON", "-12.0", "+0", "PRE", "0"])
        self.assertEqual(_args(self.sc, "/ch/01/mix/02"), ["ON", "-12.0"])
        self.assertEqual(self.sc.get("/ch/01/mix/02").raw, "/ch/01/mix/02 ON -12.0")
        self.assertEqual(Scene.parse(self.sc.dump()).dump(), self.sc.dump())

    def test_the_later_line_of_a_disagreeing_pair_wins_on_and_level(self):
        self.assertEqual(mirrored_sends(self.sc, 1, DISAGREE), [("/ch/01/mix/05", "/mix/06")])
        apply_preset(self.sc, 1, DISAGREE)
        self.assertEqual(_args(self.sc, "/ch/01/mix/05"), ["OFF", "-oo", "-20", "POST", "0"])
        self.assertEqual(_args(self.sc, "/ch/01/mix/06"), ["OFF", "-oo"])
        self.assertEqual(apply_preset(self.sc, 1, DISAGREE), 0)

    def test_an_unlinked_pair_and_an_unselected_scope_mirror_nothing(self):
        before = list(_args(self.sc, "/ch/01/mix/14"))
        self.assertEqual(mirrored_sends(self.sc, 1, "/mix/13 ON -1.0 +0 PRE 0\n"), [])
        apply_preset(self.sc, 1, "/mix/13 ON -1.0 +0 PRE 0\n")
        self.assertEqual(_args(self.sc, "/ch/01/mix/14"), before)
        self.assertEqual(mirrored_sends(self.sc, 1, ONE_SIDE, ["eq"]), [])
        self.assertEqual(apply_preset(self.sc, 1, ONE_SIDE, ["eq"]), 0)

    def test_a_line_written_twice_counts_once(self):
        self.assertEqual(apply_preset(self.sc, 20, "/mix/fader -3.0\n/mix/pan +20\n",
                                      ["mainfader"]), 1)
        self.assertEqual(apply_preset(Scene.load(SCENE), 1, DISAGREE), 2)

    def test_a_scene_without_bus_links_refuses_a_send_and_changes_nothing(self):
        sc = Scene.parse("\n".join(ln.raw for ln in self.sc.lines
                                   if ln.path != "/config/buslink") + "\n")
        before = sc.dump()
        with self.assertRaisesRegex(KeyError, "buslink"):
            apply_preset(sc, 1, "/eq/1 PEQ 99.0 +3.00 1.0\n" + ONE_SIDE)
        self.assertEqual(sc.dump(), before)
        self.assertEqual(apply_preset(sc, 1, "/eq/1 PEQ 99.0 +3.00 1.0\n"), 1)


class PresetsDiffTest(unittest.TestCase):
    def test_a_one_sided_scene_drifts_on_the_partner_and_an_apply_matches(self):
        sc = Scene.load(SCENE)
        sc.get("/ch/01/mix/01").args[1] = "-12.0"
        text = '/config "Kick" 2 YEi 1\n' + ONE_SIDE
        r = lib.check_preset(sc, "Kick.chn", text)
        self.assertEqual(r.status, lib.DRIFT)
        self.assertEqual([(d.path, d.preset, d.scene) for d in r.drift],
                         [("/mix/02", ["ON", "-12.0"], ["ON", "-7.9"])])
        apply_preset(sc, 1, text)
        self.assertEqual(lib.check_preset(sc, "Kick.chn", text).status, lib.MATCH)

    def test_a_disagreeing_pair_matches_the_scene_its_apply_wrote(self):
        sc = Scene.load(SCENE)
        text = '/config "Kick" 2 YEi 1\n' + DISAGREE
        apply_preset(sc, 1, text)
        r = lib.check_preset(sc, "Kick.chn", text)
        self.assertEqual((r.status, r.compared), (lib.MATCH, 3))


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.chn = os.path.join(self.dir, "one.chn")
        with open(self.chn, "w", encoding="utf-8") as fh:
            fh.write(ONE_SIDE)
        self.out = os.path.join(self.dir, "out.scn")

    def test_apply_preset_says_what_it_mirrored(self):
        rc, out, err = _run(["apply-preset", SCENE, "1", self.chn, "-o", self.out])
        self.assertEqual(rc, 0, err)
        self.assertIn("applied 2 line(s) to ch01", out)
        self.assertIn("mirrored /ch/01/mix/02 from /mix/01", out)
        self.assertEqual(_args(Scene.load(self.out), "/ch/01/mix/02"), ["ON", "-12.0"])

    def test_band_setup_verifies_the_mirror_and_marks_it(self):
        plan = os.path.join(self.dir, "plan.json")
        with open(plan, "w", encoding="utf-8") as fh:
            json.dump({"channels": {"1": {"preset": "one.chn"}}}, fh)
        rc, out, err = _run(["band-setup", SCENE, plan, "-o", self.out])
        self.assertEqual(rc, 0, err)
        self.assertEqual(_args(Scene.load(self.out), "/ch/01/mix/02"), ["ON", "-12.0"])
        row = next(ln for ln in out.splitlines() if "bus 02" in ln)
        self.assertIn("(mirrored)", row)


if __name__ == "__main__":
    unittest.main()


class DeskLevelPaddingTest(unittest.TestCase):
    """A mirrored level is padded as the desk pads one: five characters after one space,
    whatever width the value it replaces had (the desk read `OFF   -12.0` back as
    `OFF -12.0` on 2026-09-23)."""

    def test_a_mirrored_level_takes_the_desk_padding(self):
        sc = Scene.load(SCENE)
        for level, raw in (("-12.0", "/ch/01/mix/02 ON -12.0"), ("-7.5", "/ch/01/mix/02 ON  -7.5"),
                           ("-oo", "/ch/01/mix/02 ON   -oo")):
            with self.subTest(level=level):
                sc = Scene.load(SCENE)
                apply_preset(sc, 1, f"/mix/01 ON {level} +0 PRE 0\n")
                self.assertEqual(sc.get("/ch/01/mix/02").raw, raw)
