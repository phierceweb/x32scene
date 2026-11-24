"""apply-preset checks the head-amp line it writes: two fields, a gain in the head amp's
range written with a sign and one decimal, then ON or OFF."""

import os
import unittest

from x32scene import Scene
from x32scene.services.presets import apply_preset

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")
HA = "/headamp/000 +22.5 OFF"


def preset(line: str) -> str:
    with open(os.path.join(FIXTURES, "example.chn"), encoding="utf-8", newline="") as fh:
        text = fh.read()
    assert HA in text
    return text.replace(HA, line)


class HeadAmpLineTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)
        self.before = self.sc.dump()

    def test_a_line_the_desk_would_write_is_applied(self):
        for fields in ("+60.0 ON", "-12.0 OFF", "+0.0 OFF", "+7.5 ON", "+10.0 OFF", "-9.5 ON"):
            with self.subTest(fields=fields):
                sc = Scene.load(EXAMPLE)
                apply_preset(sc, 1, preset(f"/headamp/000 {fields}"), ["ha"])
                self.assertEqual(sc.get("/headamp/000").raw, f"/headamp/000 {fields}")

    def test_a_line_the_desk_would_not_write_is_refused_and_nothing_changes(self):
        for fields in ("+999 FOO", "+60.5 OFF", "-12.5 OFF", "+999.0 OFF", "22 OFF", "22.5 OFF",
                       "+22.50 OFF", "+22 OFF", "loud OFF", "+inf OFF", "nan OFF", "+22.5 on",
                       "+22.5 1", "+22.5", "+22.5 OFF 1", "", "+060.0 ON", "+00.0 OFF",
                       "+05.0 OFF", "-012.0 OFF", "+.5 OFF", "+5. OFF", "+\uff12\uff12.5 ON",
                       "+\u0662\u0662.5 ON", "+22.\u0665 ON"):
            for scopes in (None, ["ha"]):
                with self.subTest(fields=fields, scopes=scopes):
                    line = f"/headamp/000 {fields}".rstrip()
                    with self.assertRaises(ValueError) as cm:
                        apply_preset(self.sc, 1, preset(line), scopes)
                    self.assertEqual(str(cm.exception),
                                     f"preset {line}: a head-amp line carries a gain from -12.0 "
                                     "to +60.0 written like +19.0, then ON or OFF")
                    self.assertEqual(self.sc.dump(), self.before)

    def test_a_line_that_is_not_written_is_not_checked(self):
        bad = preset("/headamp/000 +999 FOO")
        amps = [ln.raw for ln in self.sc.lines if ln.path.startswith("/headamp")]
        apply_preset(self.sc, 1, bad, ["eq"])       # not selected
        apply_preset(self.sc, 30, bad, ["ha"])      # ch 30's source has no head amp
        self.assertEqual([ln.raw for ln in self.sc.lines if ln.path.startswith("/headamp")],
                         amps)
        partial = Scene.parse("\n".join(ln.raw for ln in self.sc.lines
                                        if ln.path != "/headamp/000"))
        apply_preset(partial, 1, bad, ["ha"])       # the scene holds no line to write it to
        self.assertEqual([ln.raw for ln in partial.lines if ln.path.startswith("/headamp")],
                         amps[1:])


if __name__ == "__main__":
    unittest.main()
