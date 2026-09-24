"""A band-setup plan's graphic-EQ gain outside -15..15 dB is a plan error, as set-fx refuses it."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")   # FX8 is GEQ


class PlanGeqRangeTest(unittest.TestCase):
    def test_an_out_of_range_band_exits_2_with_nothing_written(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        plan, out = os.path.join(d, "plan.json"), os.path.join(d, "out.scn")
        with open(plan, "w", encoding="utf-8") as fh:
            json.dump({"fx": {"8": {"params": {"1000": 20}}}}, fh)
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = main(["band-setup", SCENE, plan, "-o", out])
        self.assertEqual(rc, 2)
        self.assertIn("'1000'", err.getvalue())
        self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
