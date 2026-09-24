"""set-fx refuses a type whose parameters it cannot write, and says what to do instead."""

import os
import unittest

from x32scene import Scene
from x32scene.services import fx as FX

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


class RefusalWordingTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_a_true_eq_names_itself_and_the_graphic_eq_to_use_instead(self):
        for code, alt in (("TEQ", "GEQ"), ("TEQ2", "GEQ2")):
            FX.set_fx_type(self.sc, 8, code)
            with self.subTest(code=code), self.assertRaises(ValueError) as cm:
                FX.set_fx_params(self.sc, 8, {"20" if code == "TEQ" else "20 A": 3})
            msg = str(cm.exception)
            self.assertIn(f"{code} (", msg)
            self.assertIn("not desk-verified", msg)
            self.assertIn(f"--type {alt}", msg)

    def test_an_unknown_type_is_named_rather_than_a_bare_key(self):
        self.sc.get("/fx/1").args = ["XYZ"]
        for call in (lambda: FX.set_fx_params(self.sc, 1, {"Decay": 2}),
                     lambda: FX.set_fx_param(self.sc, 1, "Decay", "2.00")):
            with self.subTest(call=call), self.assertRaises(ValueError) as cm:
                call()
            self.assertIn("'XYZ'", str(cm.exception))
            self.assertIn("fx-types", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
