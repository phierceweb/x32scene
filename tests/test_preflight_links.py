"""preflight `links`: stereo-pair state per family keyed by the odd strip, the four
link preferences, and (opt-in) send symmetry across a linked bus pair."""

import os
import unittest

from x32scene import Scene
from x32scene.services.preflight import preflight

from tests.preflight_scene import fails, mini_scene

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
LINKS_OK = {"links": {"bus": {"1": True, "13": False}, "ch": {"11": True, "1": False},
                      "auxin": {"5": True, "1": False}, "fxrtn": {"1": True},
                      "mtx": {"1": False},
                      "linkcfg": {"hadly": True, "eq": True, "dyn": True, "fdrmute": True}}}


def one_fail(findings, *needles):
    fs = fails(findings)
    assert len(fs) == 1, fs
    for n in needles:
        assert n in fs[0].message or n in fs[0].area, (n, fs[0])
    return fs[0]


def drop(scene, path):
    scene.lines = [ln for ln in scene.lines if ln.path != path]
    scene._reindex()


class LinkShapeTest(unittest.TestCase):
    def test_fixture_lines_pass_with_no_config(self):
        self.assertEqual(fails(preflight(mini_scene(), {})), [])

    def test_short_link_line_fails(self):
        sc = mini_scene({"/config/buslink": "/config/buslink ON ON ON ON ON ON OFF"})
        one_fail(preflight(sc, {}), "link bus", "7 token(s), not 8")

    def test_missing_link_line_fails(self):
        sc = mini_scene({"/config/mtxlink": None})
        one_fail(preflight(sc, {}), "link mtx", "missing")

    def test_non_on_off_token_fails(self):
        sc = mini_scene({"/config/buslink": "/config/buslink on ON ON ON ON ON OFF OFF"})
        one_fail(preflight(sc, {}), "link bus", "'on'")


class LinkPinTest(unittest.TestCase):
    def test_fixture_pins_pass(self):
        self.assertEqual(preflight(mini_scene(), LINKS_OK), [])

    def test_unlinked_pair_fails_naming_the_pair(self):
        sc = mini_scene({"/config/buslink": "/config/buslink ON ON ON ON ON OFF OFF OFF"})
        f = one_fail(preflight(sc, {"links": {"bus": {"11": True}}}),
                     "link bus 11", "pair 11/12 is OFF", "expected ON")
        self.assertEqual(f.path, "/config/buslink")

    def test_even_key_names_the_odd_sibling(self):
        one_fail(preflight(mini_scene(), {"links": {"bus": {"12": True}}}), "odd member", "11")

    def test_pair_out_of_range_fails(self):
        one_fail(preflight(mini_scene(), {"links": {"mtx": {"7": True}}}), "out of range 1-6")

    def test_non_bool_value_fails(self):
        one_fail(preflight(mini_scene(), {"links": {"bus": {"1": "on"}}}), "true or false")

    def test_pinned_pair_on_missing_line_cannot_verify(self):
        sc = mini_scene({"/config/auxlink": None})
        fs = fails(preflight(sc, {"links": {"auxin": {"5": True}}}))
        self.assertTrue(any("cannot verify" in f.message for f in fs), fs)

    def test_linkcfg_mismatch_fails(self):
        sc = mini_scene({"/config/linkcfg": "/config/linkcfg ON ON ON OFF"})
        f = one_fail(preflight(sc, {"links": {"linkcfg": {"fdrmute": True}}}),
                     "linkcfg", "fdrmute is OFF", "expected ON")
        self.assertEqual(f.path, "/config/linkcfg")

    def test_unknown_family_fails(self):
        one_fail(preflight(mini_scene(), {"links": {"dca": {}}}), "unknown config key 'dca'")
        one_fail(preflight(mini_scene(), {"links": {"linkcfg": {"hpf": True}}}),
                 "unknown config key 'hpf'")


class SendSymmetryTest(unittest.TestCase):
    """A one-sided write to a linked bus pair survives round-trip, diff and verify; the
    console reverts one side on recall. Opt-in: the rule is inferred, not desk-proven."""

    SYM = {"links": {"require_send_symmetry": True}}

    def test_example_scene_is_symmetric(self):
        self.assertEqual(fails(preflight(Scene.load(EXAMPLE), self.SYM)), [])

    def test_one_sided_send_fails_once_per_pair(self):
        sc = Scene.load(EXAMPLE)
        sc.get("/ch/30/mix/02").set_arg(1, "-17.0")   # its partner /mix/01 stays -18.0
        f = one_fail(preflight(sc, self.SYM), "link bus 01", "1 send(s)", "/ch/30", "recall")
        self.assertEqual(f.path, "/ch/30/mix/01")

    def test_symmetry_is_opt_in(self):
        sc = Scene.load(EXAMPLE)
        sc.get("/ch/30/mix/02").set_arg(1, "-17.0")
        self.assertEqual(fails(preflight(sc, {})), [])

    def test_unlinked_pair_is_not_compared(self):
        sc = Scene.load(EXAMPLE)   # buses 13/14 are unlinked mono FX sends
        sc.get("/ch/02/mix/14").set_arg(1, "-10.0")
        self.assertEqual(fails(preflight(sc, self.SYM)), [])

    def test_missing_send_line_cannot_verify(self):
        sc = Scene.load(EXAMPLE)
        drop(sc, "/ch/30/mix/02")
        one_fail(preflight(sc, self.SYM), "link bus 01", "cannot verify")


if __name__ == "__main__":
    unittest.main()
