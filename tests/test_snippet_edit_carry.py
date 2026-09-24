"""`snippet --edit` refuses an edit whose lines a snippet cannot carry, and prints nothing
until every edit has applied."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")
PRESET = os.path.join(FIXTURES, "example.chn")


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class UncarriedEditTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = os.path.join(self.dir, "edit.snp")

    def _refused(self, *edits):
        argv = ["snippet", EXAMPLE, "-o", self.out]
        for edit in edits:
            argv += ["--edit", edit]
        rc, out, err = _run(*argv)
        self.assertEqual(rc, 1, err)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertEqual(os.listdir(self.dir), [])
        return err

    def test_the_routing_switch_is_refused_naming_the_edit_and_the_scene_route(self):
        err = self._refused("set-routing switch PLAY")
        self.assertIn("'set-routing switch PLAY'", err)
        self.assertIn("/config/routing/routswitch", err)
        self.assertIn("cannot carry", err)
        self.assertIn("run set-routing on the scene with -o OUT.scn", err)

    def test_a_record_output_is_refused(self):
        err = self._refused("set-output rec 1 --src 'bus 3'")
        self.assertIn("/outputs/rec/01", err)
        self.assertIn("run set-output on the scene", err)

    def test_a_preset_whose_automix_moves_is_refused_with_the_scope_route(self):
        err = self._refused(f"apply-preset 15 {PRESET}")
        self.assertIn("/ch/15/automix", err)
        self.assertIn("--scope", err)

    def test_a_carried_edit_beside_it_does_not_let_it_through(self):
        err = self._refused("set-fader 1 -3", "set-routing switch PLAY")
        self.assertIn("set-routing switch PLAY", err)

    def test_a_preset_whose_every_line_is_carried_still_loads(self):
        rc, out, err = _run("snippet", EXAMPLE, "-o", self.out,
                            "--edit", f"apply-preset 15 {PRESET} --scope eq")
        self.assertEqual(rc, 0, err)
        self.assertIn("filters: EQ", out)


class NothingPrintedBeforeEveryEditAppliesTest(unittest.TestCase):
    def test_a_later_failing_edit_leaves_stdout_empty(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "two.snp")
            rc, text, err = _run("snippet", EXAMPLE, "-o", out,
                                 "--edit", "set-fader 1 -3", "--edit", "set-eq 1 9 --gain 3")
            self.assertEqual(rc, 1)
            self.assertEqual(text, "")
            self.assertIn("/ch/01/eq/9", err)
            self.assertFalse(os.path.exists(out))

    def test_an_edit_that_moves_nothing_prints_no_row(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "same.snp")
            rc, text, err = _run("snippet", EXAMPLE, "-o", out,
                                 "--edit", "set-routing switch REC")
            self.assertEqual((rc, text), (1, ""))
            self.assertIn("no changes to write", err)

    def test_rows_come_before_the_summary_when_written(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "ok.snp")
            rc, text, err = _run("snippet", EXAMPLE, "-o", out,
                                 "--edit", "set-fader 1 -3", "--edit", "set-mute 2 on")
            self.assertEqual(rc, 0, err)
            lines = text.splitlines()
            self.assertEqual(lines[:2], ["edited 1", "edited 2"])
            self.assertTrue(lines[2].startswith(f"wrote {out}: 2 lines"), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
