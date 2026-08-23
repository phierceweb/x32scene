"""preflight `routing`: REC/PLAY mode, routing block pins by 1-based index with
per-destination widths, and /config/userrout slots. Shape checks are always on."""

import unittest

from x32scene.services.preflight import preflight

from tests.preflight_scene import fails, line, mini_scene


def one_fail(findings, *needles):
    fs = fails(findings)
    assert len(fs) == 1, fs
    for n in needles:
        assert n in fs[0].message or n in fs[0].area, (n, fs[0])
    return fs[0]


class RoutingShapeTest(unittest.TestCase):
    def test_fixture_lines_pass_with_no_config(self):
        self.assertEqual(fails(preflight(mini_scene(), {})), [])

    def test_short_in_line_fails(self):
        sc = mini_scene({"/config/routing/IN": "/config/routing/IN UIN1-8 UIN9-16 UIN17-24 UIN25-32"})
        one_fail(preflight(sc, {}), "routing IN", "4 block(s), not 5")

    def test_missing_routing_line_fails(self):
        sc = mini_scene({"/config/routing/OUT": None})
        one_fail(preflight(sc, {}), "routing OUT", "missing")

    def test_short_userrout_line_fails(self):
        toks = line("/config/userrout/out").split(" ")[:-1]
        sc = mini_scene({"/config/userrout/out": " ".join(toks)})
        one_fail(preflight(sc, {}), "userrout out", "47 slot(s), not 48")

    def test_missing_mode_line_fails(self):
        sc = mini_scene({"/config/routing": None})
        one_fail(preflight(sc, {}), "routing", "/config/routing missing")


class RoutingPinTest(unittest.TestCase):
    def test_fixture_pins_pass(self):
        exp = {"routing": {"mode": "REC",
                           "blocks": {"IN": {"1": "UIN1-8", "5": "AUX1-4"},
                                      "AES50A": {"2": "OUT9-16"}, "AES50B": {"3": "OUT1-8"},
                                      "CARD": {"1": "UOUT1-8"}, "OUT": {"1": "OUT1-4"},
                                      "PLAY": {"1": "CARD1-8"}},
                           "userrout": {"out": {"1": 1, "17": 33}, "in": {"29": 157}}}}
        self.assertEqual(preflight(mini_scene(), exp), [])

    def test_mode_mismatch_fails(self):
        sc = mini_scene({"/config/routing": "/config/routing PLAY"})
        f = one_fail(preflight(sc, {"routing": {"mode": "REC"}}), "mode PLAY", "expected REC")
        self.assertEqual(f.path, "/config/routing")

    def test_repointed_block_fails_naming_both_tokens(self):
        toks = "UOUT1-8 UOUT9-16 UOUT17-24 UOUT25-32 UOUT33-40 UOUT41-48"
        sc = mini_scene({"/config/routing/AES50A": "/config/routing/AES50A " + toks})
        exp = {"routing": {"blocks": {"AES50A": {"2": "OUT9-16"}}}}
        f = one_fail(preflight(sc, exp), "routing AES50A", "block 2 is UOUT9-16", "expected OUT9-16")
        self.assertEqual(f.path, "/config/routing/AES50A")

    def test_block_index_beyond_width_is_a_config_fail(self):
        exp = {"routing": {"blocks": {"AES50A": {"7": "OUT9-16"}}}}
        one_fail(preflight(mini_scene(), exp), "out of range 1-6")
        exp = {"routing": {"blocks": {"OUT": {"5": "OUT1-4"}}}}
        one_fail(preflight(mini_scene(), exp), "out of range 1-4")

    def test_unknown_block_name_fails(self):
        one_fail(preflight(mini_scene(), {"routing": {"blocks": {"AES50C": {}}}}),
                 "unknown config key 'AES50C'")

    def test_pinned_block_on_missing_line_cannot_verify(self):
        sc = mini_scene({"/config/routing/CARD": None})
        exp = {"routing": {"blocks": {"CARD": {"1": "UOUT1-8"}}}}
        fs = fails(preflight(sc, exp))
        self.assertTrue(any("cannot verify" in f.message for f in fs), fs)

    def test_userrout_slot_mismatch_fails(self):
        exp = {"routing": {"userrout": {"out": {"1": 2}}}}
        f = one_fail(preflight(mini_scene(), exp), "userrout out", "slot 1 holds 1", "expected 2")
        self.assertEqual(f.path, "/config/userrout/out")

    def test_userrout_slot_out_of_range_fails(self):
        one_fail(preflight(mini_scene(), {"routing": {"userrout": {"in": {"33": 1}}}}),
                 "out of range 1-32")

    def test_userrout_value_must_be_a_whole_number(self):
        one_fail(preflight(mini_scene(), {"routing": {"userrout": {"out": {"1": "1"}}}}),
                 "whole number")

    def test_unknown_routing_key_fails(self):
        one_fail(preflight(mini_scene(), {"routing": {"block": {}}}), "unknown config key 'block'")


if __name__ == "__main__":
    unittest.main()
