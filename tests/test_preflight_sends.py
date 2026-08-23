"""preflight `sends`: send-line parity (always on), the tap point per bus with family and
strip exceptions, and which strips must be audible or silent in a bus."""

import os
import unittest

from x32scene import Scene
from x32scene.services.preflight import preflight

from tests.preflight_scene import fails, mini_scene

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def one_fail(findings, *needles):
    fs = fails(findings)
    assert len(fs) == 1, fs
    for n in needles:
        assert n in fs[0].message or n in fs[0].area, (n, fs[0])
    return fs[0]


class SendShapeTest(unittest.TestCase):
    def test_five_field_even_line_fails(self):
        sc = mini_scene(extra=["/ch/01/mix/02 ON  +2.8 +0 PRE 0"])
        f = one_fail(preflight(sc, {}), "send bus 02", "5 field(s), not 2")
        self.assertEqual(f.path, "/ch/01/mix/02")

    def test_no_send_lines_is_not_a_shape_error(self):
        self.assertEqual(fails(preflight(mini_scene(), {})), [])


class TapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = Scene.load(EXAMPLE)

    def test_bus_default_passes_on_an_all_pre_bus(self):
        self.assertEqual(fails(preflight(self.sc, {"sends": {"1": {"tap": "PRE"}}})), [])

    def test_family_and_strip_exceptions_pass(self):
        exp = {"sends": {"9": {"tap": "PRE", "except": {"/fxrtn": "POST", "/ch/11": "POST",
                                                        "/ch/12": "POST"}}}}
        self.assertEqual(fails(preflight(self.sc, exp)), [])

    def test_strip_exception_beats_family_exception(self):
        # bus 9: everything POST, except channels are PRE, except ch 11/12 are POST again
        exp = {"sends": {"9": {"tap": "POST", "except": {"/ch": "PRE", "/ch/11": "POST",
                                                         "/ch/12": "POST", "/auxin": "PRE"}}}}
        self.assertEqual(fails(preflight(self.sc, exp)), [])

    def test_flipped_taps_fail_per_strip(self):
        fs = fails(preflight(self.sc, {"sends": {"9": {"tap": "PRE"}}}))
        self.assertEqual(len(fs), 10, fs)   # ch 11/12 and the eight FX returns are POST
        self.assertTrue(all(f.area == "send bus 09" for f in fs))
        self.assertIn("/ch/11 tap POST != expected PRE", [f.message for f in fs])
        self.assertEqual(fs[0].path, "/ch/11/mix/09")

    def test_tap_on_an_even_bus_is_refused(self):
        one_fail(preflight(self.sc, {"sends": {"10": {"tap": "PRE"}}}), "stored on bus 9")

    def test_unknown_except_key_fails(self):
        exp = {"sends": {"1": {"tap": "PRE", "except": {"/fxrtns": "POST"}}}}
        one_fail(preflight(self.sc, exp), "except key '/fxrtns'")

    def test_except_value_must_be_a_string(self):
        exp = {"sends": {"1": {"tap": "PRE", "except": {"/ch/01": 1}}}}
        one_fail(preflight(self.sc, exp), "must be a string")

    def test_tap_must_be_a_string(self):
        one_fail(preflight(self.sc, {"sends": {"1": {"tap": 1}}}), "tap must be a string")

    def test_missing_send_lines_collapse_to_one_finding(self):
        one_fail(preflight(mini_scene(), {"sends": {"1": {"tap": "PRE"}}}),
                 "48 send line(s) missing", "cannot verify")


class PresentAbsentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = Scene.load(EXAMPLE)

    def test_present_and_absent_pass(self):
        exp = {"sends": {"1": {"present": ["/auxin/05"], "absent": [5]}}}
        self.assertEqual(fails(preflight(self.sc, exp)), [])

    def test_present_strip_that_is_off_fails(self):
        f = one_fail(preflight(self.sc, {"sends": {"1": {"present": [5]}}}),
                     "send bus 01", "/ch/05", "not audible")
        self.assertEqual(f.path, "/ch/05/mix/01")

    def test_absent_strip_that_is_on_fails(self):
        one_fail(preflight(self.sc, {"sends": {"1": {"absent": ["/auxin/05"]}}}),
                 "/auxin/05 is audible")

    def test_even_bus_present_and_absent_are_legal(self):
        exp = {"sends": {"10": {"present": [23]}, "2": {"absent": [5]}}}
        self.assertEqual(fails(preflight(self.sc, exp)), [])

    def test_non_send_strip_fails(self):
        one_fail(preflight(self.sc, {"sends": {"1": {"present": ["/bus/01"]}}}),
                 "not a send strip")

    def test_present_must_be_a_list(self):
        one_fail(preflight(self.sc, {"sends": {"1": {"present": "/ch/05"}}}), "must be a list")

    def test_bus_out_of_range_fails(self):
        one_fail(preflight(self.sc, {"sends": {"17": {}}}), "out of range 1-16")

    def test_unknown_key_fails(self):
        one_fail(preflight(self.sc, {"sends": {"1": {"taps": "PRE"}}}), "unknown config key 'taps'")

    def test_missing_line_cannot_verify(self):
        sc = Scene.load(EXAMPLE)
        sc.lines = [ln for ln in sc.lines if ln.path != "/auxin/05/mix/01"]
        sc._reindex()
        one_fail(preflight(sc, {"sends": {"1": {"present": ["/auxin/05"]}}}), "cannot verify")


if __name__ == "__main__":
    unittest.main()
