"""A checked read parses a file once: the shape check and the caller share the parse."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene import _cli_files as F
from x32scene.model import Scene

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")
TRUNCATED = os.path.join(FIXTURES, "broken", "truncated.scn")
_real_parse = Scene.parse.__func__


class ParseOnceTest(unittest.TestCase):
    def setUp(self):
        F.start_run()
        self.addCleanup(F.start_run)
        self.parses = 0

        def counting(cls, text):
            self.parses += 1
            return _real_parse(cls, text)
        patcher = mock.patch.object(Scene, "parse", classmethod(counting))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _quiet(self, fn, *args):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = fn(*args)
        return result, err.getvalue()

    def test_a_first_load_parses_once(self):
        sc, _ = self._quiet(F.load_checked, EXAMPLE)
        self.assertEqual(self.parses, 1)
        with open(EXAMPLE, encoding="utf-8", newline="") as fh:
            self.assertEqual(sc.dump(), fh.read())

    def test_a_second_load_of_the_same_file_parses_once_more(self):
        self._quiet(F.load_checked, EXAMPLE)
        self._quiet(F.load_checked, EXAMPLE)
        self.assertEqual(self.parses, 2)

    def test_a_listed_read_parses_once(self):
        self._quiet(F.read_listed, EXAMPLE)
        self.assertEqual(self.parses, 1)

    def test_a_damaged_file_still_warns_once_per_run(self):
        _, first = self._quiet(F.load_checked, TRUNCATED)
        _, second = self._quiet(F.load_checked, TRUNCATED)
        self.assertEqual(len(first.strip().splitlines()), 1, first)
        self.assertIn("warning:", first)
        self.assertEqual(second, "")


class CarriageReturnTest(unittest.TestCase):
    def setUp(self):
        F.start_run()
        self.addCleanup(F.start_run)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.crlf = os.path.join(self.dir, "crlf.scn")
        shutil.copy(TRUNCATED, self.crlf)
        with open(self.crlf, "rb") as fh:
            data = fh.read()
        with open(self.crlf, "wb") as fh:
            fh.write(data.replace(b"\n", b"\r\n"))

    def test_the_text_read_still_warns_on_its_shape(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            text = F.read_checked(self.crlf)
        self.assertIn("\r\n", text)
        self.assertIn("warning:", err.getvalue())

    def test_a_load_still_refuses_it(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ValueError) as cm:
            F.load_checked(self.crlf)
        self.assertIn("CR line endings", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
