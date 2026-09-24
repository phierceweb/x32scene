"""Edges of a preset's linked-bus send mirror: a pair whose lines agree is not reported as
mirrored, presets-diff still compares a scene with no bus links, and a malformed partner
line is refused before anything is written."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import preset_library as lib
from x32scene.services.presets import apply_preset, body_lines, mirrored_sends

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIX, "example.scn")
CHN = os.path.join(FIX, "example.chn")   # a desk-written preset: linked pairs agree
ONE_SIDE = '/config "Kick" 2 YEi 1\n/mix/01 ON -12.0 +0 PRE 0\n'


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def _read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _without_bus_links() -> Scene:
    return Scene.parse("".join(ln + "\n" for ln in _read(SCENE).splitlines()
                               if not ln.startswith("/config/buslink")))


class AgreeingPairTest(unittest.TestCase):
    def test_a_pair_whose_lines_agree_is_not_mirrored(self):
        sc = Scene.load(SCENE)
        self.assertEqual(mirrored_sends(sc, 2, _read(CHN)), [])
        apply_preset(sc, 2, _read(CHN))
        for ln in body_lines(_read(CHN)):
            if ln.path.startswith("/mix/") and ln.path[5:].isdigit():
                self.assertEqual(sc.get(f"/ch/02{ln.path}").args, ln.args, ln.path)

    def test_apply_preset_names_no_mirror_for_it(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        rc, out, err = _run(["apply-preset", SCENE, "2", CHN, "-o", os.path.join(d, "o.scn")])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("mirrored", out)


class NoBusLinkTest(unittest.TestCase):
    def test_presets_diff_compares_each_send_on_its_own_bus(self):
        sc = _without_bus_links()
        r = lib.check_preset(sc, "Kick.chn", ONE_SIDE)
        self.assertEqual(r.status, lib.DRIFT)
        self.assertEqual([d.path for d in r.drift], ["/mix/01"])

    def test_the_command_reports_every_preset(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        scene = os.path.join(d, "s.scn")
        _without_bus_links().save(scene)
        shutil.copy(CHN, os.path.join(d, "Kick.chn"))
        rc, out, err = _run(["presets-diff", d, scene])
        self.assertEqual(rc, 0, err)
        self.assertTrue(out.startswith("MATCH"), out)


class MalformedPartnerTest(unittest.TestCase):
    def test_a_short_partner_line_is_refused_with_nothing_written(self):
        sc = Scene.parse(_read(SCENE).replace("/ch/01/mix/02 ON  -7.9\n", "/ch/01/mix/02\n"))
        before = sc.dump()
        with self.assertRaisesRegex(IndexError, "/ch/01/mix/02"):
            apply_preset(sc, 1, "/eq/1 PEQ 99.0 +3.00 1.0\n" + ONE_SIDE.split("\n", 1)[1])
        self.assertEqual(sc.dump(), before)


if __name__ == "__main__":
    unittest.main()
