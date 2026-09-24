"""show-build's -o DIR is checked at dispatch, before any input is read."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene.cli import main


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class ShowBuildDirFirstTest(unittest.TestCase):
    def test_a_file_named_as_dir_is_refused_before_a_missing_input(self):
        with tempfile.TemporaryDirectory() as d:
            taken = os.path.join(d, "taken")
            with open(taken, "w", encoding="utf-8") as fh:
                fh.write("x")
            rc, _, err = _run(["show-build", "-o", taken, "--name", "gig",
                               "--scene", os.path.join(d, "missing.scn")])
        self.assertEqual(rc, 1)
        self.assertIn(f"-o {taken} is not a directory", err)
        self.assertNotIn("missing.scn", err)


if __name__ == "__main__":
    unittest.main()
