"""band-setup writes OUT and its --snippet all or nothing: a snippet the filesystem refuses
at write time (a full disk, a race the up-front check cannot see) leaves no OUT behind."""

import contextlib
import errno
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from pf_core.utils.io import atomic_write_bytes

from x32scene.cli import main
from x32scene.orchestrators import band_swap

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def _full_for_snippets(path, data):
    if str(path).endswith(".snp"):
        raise OSError(errno.ENOSPC, "No space left on device")
    return atomic_write_bytes(path, data)


_real_replace = os.replace


def _volumes(*roots):
    """os.replace refusing a rename between two of ``roots``, as between filesystems."""
    def volume(p):
        p = os.path.abspath(os.fspath(p))
        return next((r for r in roots if p.startswith(r + os.sep)), None)

    def replace(src, dst):
        if volume(src) != volume(dst):
            raise OSError(errno.EXDEV, "Cross-device link")
        return _real_replace(src, dst)
    return replace


class BandSetupAtomicTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = os.path.join(self.dir, "out.scn")
        self.snp = os.path.join(self.dir, "out.snp")
        self.plan = os.path.join(self.dir, "plan.json")
        with open(self.plan, "w", encoding="utf-8") as fh:
            json.dump({"title": "New Band", "channels": {"1": {"name": "Kick In"}}}, fh)

    def band_setup(self, *extra):
        return _run(["band-setup", SCENE, self.plan, "-o", self.out, "--snippet", self.snp,
                     *extra])

    def test_a_snippet_refused_at_write_time_leaves_no_out(self):
        with mock.patch("x32scene._cli_files.atomic_write_bytes", _full_for_snippets):
            rc, out, err = self.band_setup()
        self.assertEqual(rc, 1, out + err)
        self.assertIn("nothing written", err)
        self.assertEqual(sorted(os.listdir(self.dir)), ["plan.json"])

    def test_with_force_the_originals_survive_a_refused_snippet(self):
        for path in (self.out, self.snp):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("original\n")
        with mock.patch("x32scene._cli_files.atomic_write_bytes", _full_for_snippets):
            rc, _, _ = self.band_setup("--force")
        self.assertEqual(rc, 1)
        for path in (self.out, self.snp):
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "original\n")

    def test_the_snippet_may_sit_on_another_volume(self):
        disk, stick = os.path.join(self.dir, "disk"), os.path.join(self.dir, "stick")
        for force in (False, True):
            with self.subTest(force=force):
                for v in (disk, stick):
                    os.makedirs(v, exist_ok=True)
                self.out, self.snp = os.path.join(disk, "out.scn"), os.path.join(stick, "out.snp")
                with mock.patch("os.replace", _volumes(disk, stick)):
                    rc, _, err = self.band_setup(*(["--force"] if force else []))
                self.assertEqual(rc, 0, err)
                self.assertEqual(os.listdir(disk), ["out.scn"])
                self.assertEqual(os.listdir(stick), ["out.snp"])

    def test_both_files_are_written_when_nothing_refuses(self):
        rc, out, err = self.band_setup()
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.isfile(self.out) and os.path.isfile(self.snp))
        self.assertIn(self.snp, out)


class RaceTest(unittest.TestCase):
    """A file another process puts at OUT or --snippet while the plan builds is neither
    replaced nor removed without --force."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = os.path.join(self.dir, "out.scn")
        self.snp = os.path.join(self.dir, "out.snp")

    def band_setup(self, plan, appears):
        path = os.path.join(self.dir, "plan.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        real = band_swap.build

        def racing(*a, **k):
            with open(appears, "w", encoding="utf-8") as fh:
                fh.write("someone else's\n")
            return real(*a, **k)
        with mock.patch("x32scene.orchestrators.band_swap.build", racing):
            return _run(["band-setup", SCENE, path, "-o", self.out, "--snippet", self.snp])

    def _kept(self, path):
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "someone else's\n")

    def test_an_out_that_appears_is_kept_and_nothing_is_written(self):
        rc, out, err = self.band_setup({"channels": {"1": {"name": "Kick In"}}}, self.out)
        self.assertEqual(rc, 1, out + err)
        self.assertIn("appeared after the overwrite check", err)
        self._kept(self.out)
        self.assertFalse(os.path.exists(self.snp))

    def test_a_snippet_that_appears_is_not_removed(self):
        rc, out, err = self.band_setup({"title": "New Band"}, self.snp)
        self.assertEqual(rc, 0, err)
        self._kept(self.snp)
        self.assertIn(f"nothing written to {self.snp}", out)


if __name__ == "__main__":
    unittest.main()
