"""preflight `monitor`: derived checks with no per-value declaration — physical/virtual
boundary, stereo output pairing, reachability off the console, live senders."""

import os
import unittest

from x32scene import Scene
from x32scene.services.preflight import preflight

from tests.preflight_scene import fails, mini_scene

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")

REACH = {"monitor": {"physical_outputs": 8, "require_reachable": True}}
ALL_UOUT = "/config/routing/AES50A UOUT1-8 UOUT9-16 UOUT17-24 UOUT25-32 UOUT33-40 UOUT41-48"


class ReachabilityTest(unittest.TestCase):
    def test_fixture_virtual_outs_reach_the_stagebox(self):
        self.assertEqual(preflight(mini_scene(), REACH), [])

    def test_repointed_load_bearing_block_strands_every_virtual_out(self):
        # AES50-A block 2 = OUT9-16 is the only path outs 9-16 have off the desk
        sc = mini_scene({"/config/routing/AES50A": ALL_UOUT})
        fs = fails(preflight(sc, REACH))
        self.assertEqual([f.area for f in fs], [f"out main {n:02d}" for n in range(9, 17)])
        self.assertIn("no AES50", fs[0].message)
        self.assertEqual(fs[0].path, "/outputs/main/09")

    def test_alt_fixture_reaches_through_user_out_slots(self):
        # example-alt has no OUT block on either AES50 port; its outs 9-16 leave through
        # /config/userrout/out 177-184 under a UOUT block — the other branch of the resolver
        self.assertEqual(fails(preflight(Scene.load(EXAMPLE_ALT), REACH)), [])

    def test_rear_xlr_bank_does_not_count_as_a_path_off_the_console(self):
        # /config/routing/OUT carries OUT9-12 OUT13-16 on every console; if the resolver
        # counted it, the stranded-outputs case above would print green
        sc = mini_scene({"/config/routing/AES50A": ALL_UOUT})
        self.assertEqual(sc.get("/config/routing/OUT").args[2:], ["OUT9-12", "OUT13-16"])
        self.assertTrue(fails(preflight(sc, REACH)))

    def test_off_virtual_out_is_not_a_dead_ear(self):
        sc = mini_scene({"/outputs/main/09": "/outputs/main/09 0 POST OFF",
                         "/config/routing/AES50A": ALL_UOUT})
        areas = [f.area for f in fails(preflight(sc, REACH))]
        self.assertNotIn("out main 09", areas)
        self.assertIn("out main 10", areas)

    def test_reachable_without_physical_outputs_cannot_verify(self):
        fs = fails(preflight(mini_scene(), {"monitor": {"require_reachable": True}}))
        self.assertEqual(len(fs), 1, fs)
        self.assertIn("physical_outputs", fs[0].message)

    def test_physical_outputs_16_means_nothing_is_virtual(self):
        exp = {"monitor": {"physical_outputs": 16, "require_reachable": True}}
        sc = mini_scene({"/config/routing/AES50A": ALL_UOUT})
        self.assertEqual(fails(preflight(sc, exp)), [])


class StereoPairTest(unittest.TestCase):
    PAIRS = {"monitor": {"stereo_pairs": ["main", "aux"]}}

    def test_fixture_pairs_conform(self):
        self.assertEqual(preflight(mini_scene(), self.PAIRS), [])

    def test_even_output_carrying_the_wrong_bus_fails(self):
        sc = mini_scene({"/outputs/main/10": "/outputs/main/10 6 POST OFF"})   # bus 3 twice
        fs = fails(preflight(sc, self.PAIRS))
        self.assertEqual(len(fs), 1, fs)
        self.assertEqual(fs[0].area, "out main 09")
        self.assertIn("Bus 3 / Bus 3", fs[0].message)

    def test_odd_output_carrying_an_even_bus_fails(self):
        sc = mini_scene({"/outputs/aux/01": "/outputs/aux/01 11 POST OFF",
                         "/outputs/aux/02": "/outputs/aux/02 12 POST OFF"})
        fs = fails(preflight(sc, self.PAIRS))
        self.assertEqual([f.area for f in fs], ["out aux 01"])

    def test_non_bus_pairs_have_no_rule(self):
        # main 07/08 carry Main L/R: nothing to pair-check
        sc = mini_scene({"/outputs/main/08": "/outputs/main/08 0 POST OFF"})
        self.assertEqual(preflight(sc, self.PAIRS), [])

    def test_p16_is_refused_as_a_pair_bank(self):
        fs = fails(preflight(mini_scene(), {"monitor": {"stereo_pairs": ["p16"]}}))
        self.assertEqual(len(fs), 1, fs)
        self.assertIn("p16", fs[0].message)

    def test_stereo_pairs_must_be_a_list(self):
        fs = fails(preflight(mini_scene(), {"monitor": {"stereo_pairs": "main"}}))
        self.assertEqual(len(fs), 1, fs)


class LiveSenderTest(unittest.TestCase):
    LIVE = {"monitor": {"require_live_senders": True}}

    def test_example_scene_has_a_live_sender_in_every_routed_bus(self):
        self.assertEqual(fails(preflight(Scene.load(EXAMPLE), self.LIVE)), [])

    def test_routed_bus_with_every_sender_off_is_a_dead_ear(self):
        sc = Scene.load(EXAMPLE)
        for ln in sc.find("/"):
            if ln.path.endswith("/mix/11") and ln.args:
                ln.set_arg(0, "OFF")
        fs = fails(preflight(sc, self.LIVE))
        self.assertEqual(len(fs), 1, fs)
        self.assertEqual(fs[0].area, "bus 11")
        self.assertIn("/outputs/main/05", fs[0].message)
        self.assertIn("no sender", fs[0].message)

    def test_no_send_lines_at_all_cannot_verify(self):
        fs = fails(preflight(mini_scene(), self.LIVE))
        self.assertTrue(fs)
        self.assertTrue(all("cannot verify" in f.message for f in fs), fs)

    def test_unknown_monitor_key_fails(self):
        fs = fails(preflight(mini_scene(), {"monitor": {"require_reachable_": True}}))
        self.assertEqual(len(fs), 1, fs)


if __name__ == "__main__":
    unittest.main()
