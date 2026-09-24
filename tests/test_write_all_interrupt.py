"""A batch write interrupted mid-replace (Ctrl-C) puts every original back, removes every
file it placed, and re-raises."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene._cli_files import write_all

_real_replace = os.replace


def _interrupting(nth, directory):
    """os.replace raising KeyboardInterrupt on the nth rename into or out of ``directory``;
    the staging writes inside the batch's own folder are not counted."""
    calls = []

    def replace(src, dst):
        if directory in (os.path.dirname(src), os.path.dirname(dst)):
            calls.append(dst)
            if len(calls) == nth:
                raise KeyboardInterrupt
        return _real_replace(src, dst)
    return replace


class InterruptedBatchTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.names = ["A.chn", "B.chn", "C.chn"]
        self._fresh("first")

    def _fresh(self, name):
        self.dir = os.path.join(self.root, name)
        os.makedirs(self.dir)
        self.paths = [os.path.join(self.dir, n) for n in self.names]

    def _files(self):
        """Every entry left in the folder; a staging folder shows as a directory."""
        out = {}
        for name in sorted(os.listdir(self.dir)):
            path = os.path.join(self.dir, name)
            if os.path.isdir(path):
                out[name] = "directory"
                continue
            with open(path, "rb") as fh:
                out[name] = fh.read()
        return out

    def _write(self, nth, replaceable=()):
        with mock.patch("os.replace", _interrupting(nth, self.dir)), self.assertRaises(KeyboardInterrupt):
            write_all([(p, b"new " + os.path.basename(p).encode()) for p in self.paths],
                      replaceable)

    def test_every_original_is_restored_whichever_rename_is_interrupted(self):
        originals = {n: b"old " + n.encode() for n in self.names}
        for nth in range(1, 7):     # each target: moved aside, then placed
            with self.subTest(nth=nth):
                self._fresh(f"old{nth}")
                for name, data in originals.items():
                    with open(os.path.join(self.dir, name), "wb") as fh:
                        fh.write(data)
                self._write(nth, replaceable=set(self.paths))
                self.assertEqual(self._files(), originals)

    def test_every_new_file_is_removed(self):
        for nth in range(1, 4):
            with self.subTest(nth=nth):
                self._fresh(f"new{nth}")
                self._write(nth)
                self.assertEqual(self._files(), {})

    def test_a_restore_that_fails_keeps_the_original_aside(self):
        with open(self.paths[0], "wb") as fh:
            fh.write(b"old A")
        calls = []

        def replace(src, dst):
            if self.dir in (os.path.dirname(src), os.path.dirname(dst)):
                calls.append(dst)
                if len(calls) == 2:
                    raise KeyboardInterrupt
                if len(calls) > 2:
                    raise PermissionError(1, "Operation not permitted")
            return _real_replace(src, dst)
        err = io.StringIO()
        with mock.patch("os.replace", replace), self.assertRaises(KeyboardInterrupt), \
                contextlib.redirect_stderr(err):
            write_all([(p, b"new") for p in self.paths], {self.paths[0]})
        [stage] = [n for n in os.listdir(self.dir) if n.startswith(".x32scene-")]
        kept = os.path.join(self.dir, stage, "replaced")
        with open(os.path.join(kept, "A.chn"), "rb") as fh:
            self.assertEqual(fh.read(), b"old A")
        self.assertIn(f"could not restore {self.paths[0]}, originals kept in {kept}",
                      err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
