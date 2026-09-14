"""`extract-preset --all --force` replaces every target or none, and leaves no folder it made."""

import contextlib
import errno
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.model import Scene

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
_real_replace = os.replace


def _staged(src):
    return os.path.basename(os.path.dirname(src)).startswith(".x32scene-")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class ReplaceRollbackTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.lib = os.path.join(self.dir, "presets")
        os.makedirs(self.lib)
        self.kept = {"Hat.chn": "old hat\n", "Kick.chn": "old kick\n", "Bass DI.chn": "old bass\n"}
        for name, text in self.kept.items():
            with open(os.path.join(self.lib, name), "w") as fh:
                fh.write(text)

    def _failing(self, nth, when):
        calls = []

        def replace(src, dst):
            if when(os.fspath(src), os.fspath(dst)):
                calls.append(dst)
                if len(calls) == nth:
                    raise PermissionError(errno.EPERM, "Operation not permitted", src, None, dst)
            return _real_replace(src, dst)
        return replace

    def _assert_untouched(self, rc, err):
        self.assertEqual(rc, 1)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertNotIn(".x32scene-", err)
        self.assertEqual(sorted(os.listdir(self.lib)), sorted(self.kept))
        for name, text in self.kept.items():
            with open(os.path.join(self.lib, name)) as fh:
                self.assertEqual(fh.read(), text)

    def test_a_target_that_cannot_be_placed_mid_batch_restores_every_original(self):
        for nth in (1, 2, 20):
            with self.subTest(nth=nth):
                placing = self._failing(nth, lambda s, d: os.path.dirname(d) == self.lib
                                        and _staged(s))
                with mock.patch("os.replace", placing):
                    rc, _, err = _run(["extract-preset", SCENE, "--all", "-o", self.lib, "--force"])
                self._assert_untouched(rc, err)
                self.assertIn("Operation not permitted", err)
                self.assertRegex(err, r"\.chn")

    def test_a_target_that_cannot_be_moved_aside_restores_the_ones_before_it(self):
        aside = self._failing(2, lambda s, d: os.path.dirname(s) == self.lib)
        with mock.patch("os.replace", aside):
            rc, _, err = _run(["extract-preset", SCENE, "--all", "-o", self.lib, "--force"])
        self._assert_untouched(rc, err)
        self.assertTrue(any(name in err for name in self.kept), err)

    def test_an_original_that_cannot_be_put_back_is_kept_and_named(self):
        calls = []

        def replace(src, dst):
            if os.path.dirname(dst) == self.lib:
                calls.append(dst)
                if len(calls) >= 20:     # every later placement, and every restore
                    raise PermissionError(errno.EPERM, "Operation not permitted", dst)
            return _real_replace(src, dst)
        with mock.patch("os.replace", replace):
            rc, _, err = _run(["extract-preset", SCENE, "--all", "-o", self.lib, "--force"])
        self.assertEqual(rc, 1)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn("could not restore", err)
        [stage] = [n for n in os.listdir(self.lib) if n.startswith(".x32scene-")]
        kept = os.path.join(self.lib, stage, "replaced")
        restored = set(os.listdir(self.lib)) & set(self.kept)
        self.assertEqual(restored | set(os.listdir(kept)), set(self.kept))
        self.assertIn(kept, err)

    def test_a_failed_batch_removes_the_folders_it_created(self):
        lib = os.path.join(self.dir, "new", "deeper", "presets")
        placing = self._failing(3, lambda s, d: os.path.dirname(d) == lib and _staged(s))
        with mock.patch("os.replace", placing):
            rc, _, err = _run(["extract-preset", SCENE, "--all", "-o", lib])
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.lexists(os.path.join(self.dir, "new")), err)

    def test_a_failed_batch_keeps_a_folder_that_was_already_there(self):
        empty = os.path.join(self.dir, "empty")
        os.makedirs(empty)
        placing = self._failing(1, lambda s, d: os.path.dirname(d) == empty)
        with mock.patch("os.replace", placing):
            rc, _, _ = _run(["extract-preset", SCENE, "--all", "-o", empty])
        self.assertEqual((rc, os.listdir(empty)), (1, []))



class RefusedNamesTest(unittest.TestCase):
    def test_every_name_the_filesystem_refuses_is_named_at_once(self):
        with tempfile.TemporaryDirectory() as d:
            scene = os.path.join(d, "long.scn")
            sc = Scene.load(SCENE)
            for ch, letter in ((5, "L"), (9, "M")):
                sc.get(f"/ch/{ch:02d}/config").set_arg(0, '"' + letter * 300 + '"')
            sc.save(scene)
            lib = os.path.join(d, "presets")
            rc, _, err = _run(["extract-preset", scene, "--all", "-o", lib])
        self.assertEqual(rc, 1)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn("2 file(s) could not be written", err)
        for letter in "LM":
            self.assertIn(letter * 300 + ".chn", err)

if __name__ == "__main__":
    unittest.main(verbosity=2)


class WriteRaceTest(unittest.TestCase):
    """What appears at a target after the overwrite check is not replaced."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.a, self.b = os.path.join(self.dir, "A.chn"), os.path.join(self.dir, "B.chn")

    def _write(self, replaceable=()):
        from x32scene._cli_files import write_all
        write_all([(self.a, b"new-A"), (self.b, b"new-B")], self.dir, replaceable)

    def _left(self):
        return sorted(n for n in os.listdir(self.dir) if n.startswith(".x32scene-"))

    def test_a_file_that_appeared_is_kept_and_nothing_is_written(self):
        from pf_core.exceptions import InvalidInputError
        with open(self.b, "wb") as fh:
            fh.write(b"USER-B")
        with self.assertRaises(InvalidInputError) as cm:
            self._write()
        self.assertIn("B.chn", str(cm.exception))
        with open(self.b, "rb") as fh:
            self.assertEqual(fh.read(), b"USER-B")
        self.assertFalse(os.path.exists(self.a))
        self.assertEqual(self._left(), [])

    def test_a_directory_that_appeared_is_kept(self):
        from pf_core.exceptions import InvalidInputError
        os.makedirs(os.path.join(self.a, "keep"))
        with self.assertRaises(InvalidInputError):
            self._write(replaceable={self.a})
        self.assertTrue(os.path.isdir(os.path.join(self.a, "keep")))
        self.assertFalse(os.path.exists(self.b))

    def test_a_target_the_check_saw_is_replaced(self):
        with open(self.a, "wb") as fh:
            fh.write(b"old")
        self._write(replaceable={self.a})
        with open(self.a, "rb") as fh:
            self.assertEqual(fh.read(), b"new-A")
        self.assertEqual(self._left(), [])
