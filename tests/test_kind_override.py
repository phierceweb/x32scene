"""`x32scene --kind KIND COMMAND …`: the kind of a file whose extension names none, for its
shape check and for the commands that refuse a file by kind."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIX, "example.scn")
SNIPPET = os.path.join(FIX, "example.snp")
TRUNCATED = os.path.join(FIX, "broken", "truncated.scn")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class KindOverrideTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name

    def _copy(self, src: str, name: str) -> str:
        dst = os.path.join(self.dir, name)
        shutil.copy(src, dst)
        return dst

    def test_an_oddly_named_truncated_scene_gets_its_shape_check(self):
        odd = self._copy(TRUNCATED, "gig.scn.bak")
        self.assertEqual(run("info", odd)[2], "")
        rc, out, err = run("--kind", "scn", "info", odd)
        self.assertEqual(rc, 0)
        self.assertIn("truncated", err)
        self.assertIn("Example Rig", out)

    def test_an_oddly_named_whole_scene_is_silent(self):
        odd = self._copy(SCENE, "gig")
        for kind in ("scn", "SCN"):
            with self.subTest(kind=kind):
                rc, _, err = run("--kind", kind, "info", odd)
                self.assertEqual((rc, err), (0, ""))

    def test_set_fader_still_takes_minus_infinity_after_the_option(self):
        odd = self._copy(SCENE, "gig.bak")
        out = os.path.join(self.dir, "out.scn")
        rc, _, err = run("--kind", "scn", "set-fader", odd, "1", "-oo", "-o", out)
        self.assertEqual((rc, err), (0, ""))

    def test_a_file_named_by_its_kind_keeps_its_own(self):
        odd = self._copy(SCENE, "gig.bak")
        rc, _, err = run("--kind", "scn", "diff", SNIPPET, odd)
        self.assertEqual((rc, err), (0, ""))
        rc, _, err = run("--kind", "snp", "info", TRUNCATED)
        self.assertIn("truncated", err)

    def test_the_kind_does_not_outlive_its_run(self):
        odd = self._copy(TRUNCATED, "gig.bak")
        self.assertIn("warning:", run("--kind", "scn", "info", odd)[2])
        self.assertEqual(run("info", odd)[2], "")

    def test_an_unknown_kind_is_refused(self):
        rc, _, err = run("--kind", "txt", "info", SCENE)
        self.assertEqual(rc, 2)
        self.assertIn("--kind", err)

    def test_strip_commands_take_an_oddly_named_scene_declared_as_one(self):
        odd = self._copy(SCENE, "gig.bak")
        out = os.path.join(self.dir, "out.scn")
        self.assertEqual(run("swap-strips", odd, "5", "7", "-o", out)[0], 1)
        self.assertFalse(os.path.exists(out))
        rc, _, err = run("--kind", "snp", "swap-strips", odd, "5", "7", "-o", out)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(out))
        rc, _, err = run("--kind", "scn", "swap-strips", odd, "5", "7", "-o", out)
        self.assertEqual((rc, err), (0, ""))
        self.assertTrue(os.path.exists(out))

    def test_regenerate_refuses_an_oddly_named_file_declared_as_another_kind(self):
        odd = self._copy(SCENE, "gig.bak")
        out = os.path.join(self.dir, "rig.json")
        rc, _, err = run("--kind", "snp", "preflight", odd, "--regenerate", out)
        self.assertEqual(rc, 1)
        self.assertIn("needs a scene", err)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(run("--kind", "scn", "preflight", odd, "--regenerate", out)[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
