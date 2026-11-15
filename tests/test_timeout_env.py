"""An ``X32SCENE_TIMEOUT`` no live command can use: one warning line on stderr, then the
default."""

import contextlib
import io
import os
import unittest
from unittest import mock

from x32scene._parsers import _build_parser


class TimeoutEnvWarningTest(unittest.TestCase):
    def test_a_bad_value_warns_in_one_line_and_falls_back(self):
        for bad, why in (("soon", "must be a number, got 'soon'"),
                         ("   ", "must be a number, got ''"),
                         ("0", "must be greater than 0 and at most 3600 seconds, got 0"),
                         ("\t\n0\r", "must be greater than 0 and at most 3600 seconds, got 0"),
                         ("inf", "must be greater than 0 and at most 3600 seconds, got inf")):
            err = io.StringIO()
            with self.subTest(value=bad), \
                 mock.patch.dict(os.environ, {"X32SCENE_TIMEOUT": bad}), \
                 contextlib.redirect_stderr(err):
                args = _build_parser(None).parse_args(["desk", "--ip", "10.0.0.1"])
                self.assertEqual(args.timeout, 0.5)
                self.assertEqual(err.getvalue(), "x32scene: warning: X32SCENE_TIMEOUT: timeout "
                                                 f"{why}; using 0.5\n")

    def test_a_usable_value_is_silent(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"X32SCENE_TIMEOUT": " 1.25 "}), \
             contextlib.redirect_stderr(err):
            args = _build_parser(None).parse_args(["desk", "--ip", "10.0.0.1"])
        self.assertEqual((args.timeout, err.getvalue()), (1.25, ""))


if __name__ == "__main__":
    unittest.main()
