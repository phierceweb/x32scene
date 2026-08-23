"""preflight `groups`: DCA and mute-group membership compared as sets in both directions,
DCA names, and the saved master mute state (always on, exceptions declarable)."""

import os
import unittest

from x32scene import Scene
from x32scene.services.preflight import preflight

from tests.preflight_scene import fails, mini_scene

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
GROUPS_OK = {"groups": {
    "dca": {"2": {"name": "Bass", "members": [17, 18]},
            "4": {"members": [8, 23, 24, 25, 26]}},
    "mute": {"5": {"members": ["/ch/31", "/ch/32", "/auxin/05", "/auxin/06"]},
             "6": {"members": [f"/fxrtn/{n:02d}" for n in range(1, 9)]}}}}


def one_fail(findings, *needles):
    fs = fails(findings)
    assert len(fs) == 1, fs
    for n in needles:
        assert n in fs[0].message or n in fs[0].area, (n, fs[0])
    return fs[0]


class MembershipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = Scene.load(EXAMPLE)

    def test_fixture_membership_passes(self):
        self.assertEqual(fails(preflight(self.sc, GROUPS_OK)), [])

    def test_missing_member_fails(self):
        exp = {"groups": {"dca": {"2": {"members": [17, 18, 19]}}}}
        f = one_fail(preflight(self.sc, exp), "dca 2", "missing: /ch/19")
        self.assertEqual(f.path, "/ch/19/grp")

    def test_extra_member_fails(self):
        exp = {"groups": {"dca": {"2": {"members": [17]}}}}
        one_fail(preflight(self.sc, exp), "dca 2", "extra: /ch/18")

    def test_both_directions_reported_separately(self):
        exp = {"groups": {"dca": {"2": {"members": [17, 19]}}}}
        self.assertEqual(len(fails(preflight(self.sc, exp))), 2)

    def test_mute_membership_is_independent_of_dca(self):
        # ch/08 is in DCA 1 and DCA 4 but only mute group 1
        exp = {"groups": {"mute": {"4": {"members": [23, 24, 25, 26]}}}}
        self.assertEqual(fails(preflight(self.sc, exp)), [])

    def test_name_mismatch_fails(self):
        exp = {"groups": {"dca": {"2": {"name": "Bass Guitar"}}}}
        f = one_fail(preflight(self.sc, exp), "dca 2", 'name "Bass"', 'expected "Bass Guitar"')
        self.assertEqual(f.path, "/dca/2/config")

    def test_member_without_grp_line_is_unknown_not_absent(self):
        sc = Scene.load(EXAMPLE)
        sc.lines = [ln for ln in sc.lines if ln.path != "/mtx/01/grp"]
        sc._reindex()
        exp = {"groups": {"dca": {"1": {"members": [*range(1, 17), "/mtx/01"]}}}}
        f = one_fail(preflight(sc, exp), "no /mtx/01/grp", "unknown")
        self.assertNotIn("missing", f.message)

    def test_member_outside_group_strips_fails(self):
        exp = {"groups": {"dca": {"1": {"members": ["/fx/1"]}}}}
        fs = fails(preflight(self.sc, exp))
        self.assertTrue(any("/fx/1" in f.message and "not a strip" in f.message for f in fs), fs)

    def test_members_must_be_a_list(self):
        one_fail(preflight(self.sc, {"groups": {"dca": {"2": {"members": 17}}}}), "must be a list")

    def test_group_number_out_of_range_fails(self):
        one_fail(preflight(self.sc, {"groups": {"dca": {"9": {}}}}), "out of range 1-8")
        one_fail(preflight(self.sc, {"groups": {"mute": {"7": {}}}}), "out of range 1-6")

    def test_unknown_key_fails(self):
        one_fail(preflight(self.sc, {"groups": {"dcas": {}}}), "unknown config key 'dcas'")
        one_fail(preflight(self.sc, {"groups": {"dca": {"2": {"member": []}}}}),
                 "unknown config key 'member'")


class MasterMuteTest(unittest.TestCase):
    """/config/mute is the engaged state of each group, positional, applied on recall."""

    def test_all_off_passes_with_no_config(self):
        self.assertEqual(fails(preflight(mini_scene(), {})), [])

    def test_engaged_group_fails_by_default(self):
        sc = mini_scene({"/config/mute": "/config/mute ON OFF OFF OFF OFF OFF"})
        f = one_fail(preflight(sc, {}), "mute master", "group 1 is engaged")
        self.assertEqual(f.path, "/config/mute")

    def test_positional_not_bitmask(self):
        # field 3 = group 3, left to right — the opposite convention from /grp masks
        sc = mini_scene({"/config/mute": "/config/mute OFF OFF ON OFF OFF OFF"})
        one_fail(preflight(sc, {}), "group 3 is engaged")

    def test_declared_engaged_group_passes(self):
        sc = mini_scene({"/config/mute": "/config/mute ON OFF OFF OFF OFF OFF"})
        self.assertEqual(fails(preflight(sc, {"groups": {"mute_engaged": [1]}})), [])

    def test_declared_engaged_but_off_fails(self):
        one_fail(preflight(mini_scene(), {"groups": {"mute_engaged": [2]}}),
                 "group 2", "expected engaged")

    def test_missing_mute_line_cannot_verify(self):
        one_fail(preflight(mini_scene({"/config/mute": None}), {}), "mute master", "cannot verify")

    def test_wrong_token_count_fails(self):
        sc = mini_scene({"/config/mute": "/config/mute OFF OFF OFF"})
        one_fail(preflight(sc, {}), "3 token(s), not 6")

    def test_mute_engaged_must_be_group_numbers(self):
        one_fail(preflight(mini_scene(), {"groups": {"mute_engaged": [7]}}), "1-6")
        one_fail(preflight(mini_scene(), {"groups": {"mute_engaged": 1}}), "must be a list")


if __name__ == "__main__":
    unittest.main()
