"""The send tap-point writer: the tap lives on the odd line of a bus pair, and a
stereo-linked strip carries it on both sides.

Fixture facts the cases lean on: ch01 and /auxin/01 are unlinked, channels 11/12 and FX
returns 1/2 are linked, and every odd send line taps PRE.
"""

import os
import unittest

from x32scene.model import Scene
from x32scene.services import iem as I
from x32scene.services.diff import diff
from x32scene.tables import SEND_TAPS

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def example() -> Scene:
    return Scene.load(EXAMPLE)


class SetSendTapTest(unittest.TestCase):
    def test_odd_bus_writes_its_own_line_keeping_the_padding(self):
        sc = example()
        self.assertEqual(I.set_send_tap(sc, 1, 9, "POST"), ["/ch/01/mix/09"])
        self.assertEqual(sc.get("/ch/01/mix/09").raw, "/ch/01/mix/09 ON  -0.3 +0 POST 0")
        self.assertEqual([c.path for c in diff(example(), sc)], ["/ch/01/mix/09"])

    def test_even_bus_writes_the_odd_partners_line(self):
        sc = example()
        self.assertEqual(I.set_send_tap(sc, 1, 10, "POST"), ["/ch/01/mix/09"])
        self.assertEqual(sc.get("/ch/01/mix/10").raw, "/ch/01/mix/10 ON  -0.3")

    def test_every_tap_is_written_verbatim_and_round_trips(self):
        for tap in SEND_TAPS:
            with self.subTest(tap=tap):
                sc = example()
                I.set_send_tap(sc, 1, 1, tap)
                self.assertEqual(sc.get("/ch/01/mix/01").args[3], tap)
                self.assertEqual(Scene.parse(sc.dump()).dump(), sc.dump())

    def test_tap_is_case_folded_to_its_canonical_spelling(self):
        sc = example()
        I.set_send_tap(sc, 1, 1, "in/lc")
        I.set_send_tap(sc, 1, 3, "<-eq")
        self.assertEqual(sc.get("/ch/01/mix/01").args[3], "IN/LC")
        self.assertEqual(sc.get("/ch/01/mix/03").args[3], "<-EQ")

    def test_linked_strip_mirrors_from_either_side(self):
        sc = example()
        self.assertEqual(I.set_send_tap(sc, 11, 3, "EQ->"), ["/ch/11/mix/03", "/ch/12/mix/03"])
        self.assertEqual(I.set_send_tap(example(), "/ch/12", 4, "EQ->"),
                         ["/ch/12/mix/03", "/ch/11/mix/03"])
        self.assertEqual(sc.get("/ch/12/mix/03").raw, "/ch/12/mix/03 ON  -1.8 +100 EQ-> 0")

    def test_linked_false_confines_the_write_to_the_named_strip(self):
        sc = example()
        self.assertEqual(I.set_send_tap(sc, 11, 3, "POST", linked=False), ["/ch/11/mix/03"])
        self.assertEqual(sc.get("/ch/12/mix/03").args[3], "PRE")

    def test_aux_in_and_fx_return_strips(self):
        sc = example()
        self.assertEqual(I.set_send_tap(sc, "/auxin/1", 1, "GRP"), ["/auxin/01/mix/01"])
        self.assertEqual(I.set_send_tap(sc, "/fxrtn/01", 2, "POST"),
                         ["/fxrtn/01/mix/01", "/fxrtn/02/mix/01"])
        self.assertEqual(sc.get("/auxin/01/mix/01").raw, "/auxin/01/mix/01 ON   -oo +0 GRP 0")


class SetSendTapRefusalTest(unittest.TestCase):
    def _refused(self, sc: Scene, exc: type, *args, **kw) -> None:
        before = sc.dump()
        with self.assertRaises(exc):
            I.set_send_tap(sc, *args, **kw)
        self.assertEqual(sc.dump(), before)

    def test_out_of_range_strip_or_bus(self):
        for strip, bus in ((33, 1), (0, 1), ("/bus/01", 1), ("/auxin/09", 1), (1, 0), (1, 17)):
            with self.subTest(strip=strip, bus=bus):
                self._refused(example(), ValueError, strip, bus, "POST")

    def test_unknown_tap(self):
        self._refused(example(), ValueError, 1, 1, "LATE")

    def test_missing_send_line(self):
        text = "\n".join(ln for ln in open(EXAMPLE, encoding="utf-8").read().split("\n")
                         if not ln.startswith("/ch/12/mix/03 "))
        self._refused(Scene.parse(text), KeyError, 11, 3, "POST")

    def test_short_send_line_on_the_partner(self):
        text = open(EXAMPLE, encoding="utf-8").read().replace(
            "/ch/12/mix/03 ON  -1.8 +100 PRE 0", "/ch/12/mix/03 ON  -1.8 +100")
        self._refused(Scene.parse(text), IndexError, 11, 3, "POST")

    def test_missing_link_config_unless_unlinked(self):
        text = "\n".join(ln for ln in open(EXAMPLE, encoding="utf-8").read().split("\n")
                         if not ln.startswith("/config/chlink "))
        self._refused(Scene.parse(text), KeyError, 11, 3, "POST")
        self.assertEqual(I.set_send_tap(Scene.parse(text), 11, 3, "POST", linked=False),
                         ["/ch/11/mix/03"])


if __name__ == "__main__":
    unittest.main()
