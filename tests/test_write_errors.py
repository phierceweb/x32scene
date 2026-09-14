"""A write that fails names the file the user asked for, never the temporary file behind it."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class WriteErrorTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def _assert_names(self, argv, typed):
        rc, _, err = _run(argv)
        self.assertEqual(rc, 1)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn(f"'{typed}'", err)
        self.assertNotIn(".tmp", err)

    def test_every_writer_names_a_missing_directory_as_typed(self):
        missing = os.path.join(self.dir, "nodir")
        for argv, typed in (
                (["set-fader", SCENE, "/ch/01", "-3", "-o"], "x.scn"),
                (["extract-preset", SCENE, "1", "-o"], "x.chn"),
                (["extract-routing", SCENE, "-o"], "x.rou"),
                (["extract-fx", SCENE, "1", "-o"], "x.efx")):
            out = os.path.join(missing, typed)
            with self.subTest(cmd=argv[0]):
                self._assert_names([*argv, out], out)

    def test_a_directory_in_the_outs_place_is_named(self):
        out = os.path.join(self.dir, "d.scn")
        os.makedirs(out)
        self._assert_names(["set-fader", SCENE, "/ch/01", "-3", "-o", out, "--force"], out)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes anywhere")
    def test_a_folder_that_cannot_be_written_is_named(self):
        ro = os.path.join(self.dir, "ro")
        os.makedirs(ro)
        os.chmod(ro, 0o555)
        self.addCleanup(os.chmod, ro, 0o755)
        out = os.path.join(ro, "x.scn")
        self._assert_names(["set-fader", SCENE, "/ch/01", "-3", "-o", out], out)

    def test_scene_save_raises_the_oserror_with_the_callers_path(self):
        out = os.path.join(self.dir, "nodir", "x.scn")
        with self.assertRaises(FileNotFoundError) as cm:
            Scene.load(SCENE).save(out)
        self.assertEqual(cm.exception.filename, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
