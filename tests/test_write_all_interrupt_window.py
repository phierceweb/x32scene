"""A Ctrl-C that lands just before or just after a rename in a batch write puts every
original back, removes every file placed, and claims no original is lost."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene._cli_files import write_all

_real_replace = os.replace


def _interrupting(nth, directory, after):
    """os.replace raising KeyboardInterrupt on the nth rename into or out of ``directory``,
    before it runs or once it has completed, as a signal delivered when the call returns."""
    calls = []

    def replace(src, dst):
        if directory not in (os.path.dirname(src), os.path.dirname(dst)):
            return _real_replace(src, dst)
        calls.append(dst)
        if len(calls) != nth:
            return _real_replace(src, dst)
        if after:
            _real_replace(src, dst)
        raise KeyboardInterrupt
    return replace


class InterruptAroundRenameTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.names = ["A.chn", "B.chn", "C.chn"]

    def _batch(self, name, nth, after, originals):
        folder = os.path.join(self.root, name)
        os.makedirs(folder)
        for n, data in originals.items():
            with open(os.path.join(folder, n), "wb") as fh:
                fh.write(data)
        paths = [os.path.join(folder, n) for n in self.names]
        err = io.StringIO()
        with mock.patch("os.replace", _interrupting(nth, folder, after)), \
                contextlib.redirect_stderr(err), self.assertRaises(KeyboardInterrupt):
            write_all([(p, b"new") for p in paths], {os.path.join(folder, n) for n in originals})
        self.assertEqual(err.getvalue(), "")
        left = {}
        for n in os.listdir(folder):
            path = os.path.join(folder, n)
            if os.path.isdir(path):
                left[n] = "directory"
                continue
            with open(path, "rb") as fh:
                left[n] = fh.read()
        return left

    def _each(self, originals, renames):
        for after in (False, True):
            for nth in range(1, renames + 1):
                with self.subTest(after=after, nth=nth):
                    left = self._batch(f"{len(originals)}-{after}-{nth}", nth, after, originals)
                    self.assertEqual(left, originals)

    def test_every_original_is_restored(self):
        self._each({n: b"old " + n.encode() for n in self.names}, 6)

    def test_every_new_file_is_removed(self):
        self._each({}, 3)

    def test_a_mixed_batch_keeps_only_its_originals(self):
        self._each({"A.chn": b"old A", "C.chn": b"old C"}, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
