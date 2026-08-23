"""Audit smoke test: structural assumptions hold across a scene library.

Runs against the checked-in fixtures. Point ``X32SCENE_CORPUS`` at your own directory
of ``.scn`` files to audit a real library instead.
"""

import os
import shutil
import tempfile
import unittest

from x32scene import audit
from x32scene.cli import main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")


class AuditTest(unittest.TestCase):
    def test_invariants_hold_for_whole_library(self):
        lib, errors = audit.load_library(os.environ.get("X32SCENE_CORPUS", FIXTURES))
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(lib), 2)
        viol = audit.check_invariants(lib)
        self.assertEqual(viol, [], f"assumption violations: {viol}")


class AuditRobustnessTest(unittest.TestCase):
    def _dir_with_truncated(self, d):
        shutil.copy(EXAMPLE, d)
        open(os.path.join(d, "truncated.scn"), "w").close()

    def test_empty_scene_is_a_violation_not_a_crash(self):
        # an aborted USB copy is exactly the drift audit exists to flag
        with tempfile.TemporaryDirectory() as d:
            self._dir_with_truncated(d)
            lib, _ = audit.load_library(d)
            viol = audit.check_invariants(lib)
            self.assertTrue(any("truncated.scn" in v for v in viol), viol)

    def test_unparseable_scene_is_reported_not_fatal(self):
        # a CRLF-damaged file is reported, not fatal to the rest of the run
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(EXAMPLE, d)
            with open(os.path.join(d, "crlf.scn"), "w", newline="") as fh:
                fh.write('#4.0# "X" "" %000000000 1\r\n')
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["audit", d]), 1)
            out = buf.getvalue()
            self.assertIn("crlf.scn", out)
            self.assertIn("Structural invariants", out)
            self.assertNotIn("ALL OK", out)

    def test_cli_exits_1_on_violations(self):
        with tempfile.TemporaryDirectory() as d:
            self._dir_with_truncated(d)
            self.assertEqual(main(["audit", d]), 1)
        self.assertEqual(main(["audit", FIXTURES]), 0)

    def test_cli_errors_on_missing_or_empty_dir(self):
        # a typo'd path must not report ALL OK
        self.assertEqual(main(["audit", os.path.join(FIXTURES, "no-such-dir")]), 1)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["audit", d]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
