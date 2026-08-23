"""preflight `outputs`: the five /outputs banks — line shape (always on) and per-output
src / pos / invert pins. One test per failure mode, each mutating one line."""

import unittest

from x32scene.services.preflight import preflight

from tests.preflight_scene import fails, line, mini_scene


def one_fail(findings, *needles):
    fs = fails(findings)
    assert len(fs) == 1, fs
    for n in needles:
        assert n in fs[0].message or n in fs[0].area, (n, fs[0])
    return fs[0]


class OutputShapeTest(unittest.TestCase):
    """Always on: no config needed, because a wrong field count round-trips clean."""

    def test_fixture_lines_pass_with_no_config(self):
        self.assertEqual(fails(preflight(mini_scene(), {})), [])

    def test_rec_line_with_three_fields_fails(self):
        sc = mini_scene({"/outputs/rec/01": "/outputs/rec/01 1 <-EQ OFF"})
        f = one_fail(preflight(sc, {}), "3 field(s), not 2")
        self.assertEqual(f.path, "/outputs/rec/01")

    def test_main_line_with_two_fields_fails(self):
        sc = mini_scene({"/outputs/main/01": "/outputs/main/01 4 POST"})
        one_fail(preflight(sc, {}), "out main 01", "2 field(s), not 3")

    def test_missing_output_line_fails_once_per_bank(self):
        sc = mini_scene({"/outputs/aux/03": None, "/outputs/aux/04": None})
        f = one_fail(preflight(sc, {}), "out aux", "2 line(s) missing")
        self.assertIn("/outputs/aux/03", f.message)


class OutputPinTest(unittest.TestCase):
    def test_bus_and_src_forms_pass_on_the_fixture(self):
        exp = {"outputs": {"main": {"1": {"bus": 1, "pos": "POST", "invert": False},
                                    "7": {"src": 1, "pos": "POST"}},
                           "aux": {"5": {"bus": 9}},
                           "p16": {"1": {"src": 26, "pos": "PRE"}},
                           "aes": {"2": {"src": 2}},
                           "rec": {"1": {"src": 1, "pos": "<-EQ"}}}}
        self.assertEqual(preflight(mini_scene(), exp), [])

    def test_repointed_output_fails_naming_both(self):
        exp = {"outputs": {"main": {"9": {"bus": 3}}}}
        sc = mini_scene({"/outputs/main/09": "/outputs/main/09 4 POST OFF"})
        f = one_fail(preflight(sc, exp), "out main 09", "src 4 (Bus 1)", "expected 6 (bus 3)")
        self.assertEqual(f.path, "/outputs/main/09")

    def test_raw_src_mismatch_fails(self):
        exp = {"outputs": {"p16": {"1": {"src": 28}}}}
        one_fail(preflight(mini_scene(), exp), "out p16 01", "src 26", "expected 28")

    def test_src_and_bus_together_is_a_config_fail(self):
        exp = {"outputs": {"main": {"1": {"src": 4, "bus": 1}}}}
        one_fail(preflight(mini_scene(), exp), "src or bus, not both")

    def test_pos_mismatch_fails(self):
        exp = {"outputs": {"main": {"1": {"pos": "PRE"}}}}
        one_fail(preflight(mini_scene(), exp), "pos POST", "expected PRE")

    def test_invert_mismatch_fails(self):
        exp = {"outputs": {"main": {"1": {"invert": True}}}}
        one_fail(preflight(mini_scene(), exp), "invert OFF", "expected ON")

    def test_invert_on_rec_is_an_unknown_key(self):
        # /outputs/rec lines carry two fields: there is no invert to compare
        exp = {"outputs": {"rec": {"1": {"invert": False}}}}
        one_fail(preflight(mini_scene(), exp), "out rec 01", "unknown config key 'invert'")

    def test_bus_out_of_range_is_a_finding_not_an_exception(self):
        exp = {"outputs": {"main": {"1": {"bus": 17}}}}
        one_fail(preflight(mini_scene(), exp), "bus must be a whole number 1-16")

    def test_unknown_bank_fails(self):
        one_fail(preflight(mini_scene(), {"outputs": {"p17": {}}}), "unknown config key 'p17'")

    def test_output_number_out_of_range_fails(self):
        one_fail(preflight(mini_scene(), {"outputs": {"aux": {"7": {}}}}), "out of range 1-6")

    def test_missing_pinned_line_fails_cannot_verify(self):
        exp = {"outputs": {"aes": {"1": {"src": 1}}}}
        sc = mini_scene({"/outputs/aes/01": None})
        fs = fails(preflight(sc, exp))
        self.assertTrue(any("cannot verify" in f.message and f.area == "out aes 01" for f in fs), fs)

    def test_string_bus_is_a_type_fail(self):
        exp = {"outputs": {"main": {"1": {"bus": "1"}}}}
        one_fail(preflight(mini_scene(), exp), "bus must be a whole number")

    def test_base_line_helper_returns_verbatim_fixture_line(self):
        self.assertEqual(line("/outputs/rec/01"), "/outputs/rec/01 1 <-EQ")


if __name__ == "__main__":
    unittest.main()
