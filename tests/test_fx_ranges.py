"""set-fx refuses a graphic-EQ gain outside the desk's -15..+15 dB, naming the parameter and
the range, and writes nothing."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import fx as FX

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")   # FX7 GEQ2, FX8 GEQ


class GeqRangeTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_the_ends_of_the_range_are_written(self):
        FX.set_fx_params(self.sc, 8, {"20": -15, "20000": 15, "Master": -15.04})
        p = self.sc.get("/fx/8/par").args
        self.assertEqual((p[0], p[30], p[31]), ("-15.0", "15.0", "-15.0"))

    def test_a_gain_past_the_range_is_refused_naming_it(self):
        for slot, values, name in ((8, {"1000": 16}, "1000"), (8, {"Master": -20}, "Master"),
                                   (7, {"20 B": -15.06}, "20 B"), (8, {"20": "loud"}, "20")):
            before = self.sc.dump()
            with self.subTest(values=values), self.assertRaises(ValueError) as cm:
                FX.set_fx_params(self.sc, slot, values)
            self.assertIn(repr(name), str(cm.exception))
            self.assertIn("-15.0 to 15.0", str(cm.exception))
            self.assertEqual(self.sc.dump(), before)

    def test_one_bad_value_writes_none_of_the_others(self):
        before = self.sc.dump()
        with self.assertRaises(ValueError):
            FX.set_fx_params(self.sc, 8, {"20": 3, "25": 99})
        self.assertEqual(self.sc.dump(), before)

    def test_a_true_eq_is_refused_as_read_only_before_its_range(self):
        FX.set_fx_type(self.sc, 8, "TEQ")
        with self.assertRaisesRegex(ValueError, "not desk-verified"):
            FX.set_fx_params(self.sc, 8, {"20": 99})

    def test_the_raw_token_setter_checks_too(self):
        with self.assertRaisesRegex(ValueError, "'20'"):
            FX.set_fx_param(self.sc, 8, "20", "15.5")

    def test_the_cli_exits_1_with_nothing_written(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.scn")
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = main(["set-fx", EXAMPLE, "8", "--set", "1000=+16", "-o", out])
            self.assertEqual(rc, 1)
            self.assertIn("'1000'", err.getvalue())
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
