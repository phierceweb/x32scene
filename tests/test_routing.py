"""Routing resolver tests against known facts in the example scene."""

import os
import unittest

from x32scene import Scene
from x32scene import routing as R

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")


class RoutingTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)
        self.by_ch = {cs.ch: cs for cs in R.channel_sources(self.sc)}

    def test_local_input_channel(self):
        self.assertEqual(self.by_ch[1].source, "Local input 1")  # Kick

    def test_aes50_stagebox_channel(self):
        self.assertEqual(self.by_ch[17].source, "AES50-A input 1")  # resolves through the AES50-A stage box

    def test_card_return_channel(self):
        self.assertEqual(self.by_ch[31].source, "USB Card (DAW) 1")  # DAW L from the card

    def test_record_map_is_32_tracks_inputs(self):
        tracks = R.record_map(self.sc)
        self.assertEqual(len(tracks), 32)
        self.assertEqual(tracks[0], (1, "Local input 1"))
        self.assertEqual(tracks[16], (17, "AES50-A input 1"))

    def test_loopback_detection_finds_daw_channels(self):
        chs = {cs.ch for cs in R.card_sourced_channels(self.sc)}
        self.assertTrue({29, 30, 31, 32}.issubset(chs))

    def test_routing_blocks_and_userrout_are_public(self):
        self.assertEqual(R.routing_blocks(self.sc, "OUT"), ["OUT1-4", "OUT5-8", "OUT9-12", "OUT13-16"])
        self.assertEqual(R.routing_blocks(self.sc, "NOPE"), [])
        self.assertEqual(len(R.userrout(self.sc, "out")), 48)
        self.assertEqual(R.userrout(self.sc, "in")[28], 157)

    def test_output_sources_per_bank(self):
        self.assertEqual(R.output_sources(self.sc, "rec"), {1: 1, 2: 2})
        self.assertEqual(R.output_sources(self.sc, "main")[9], 6)

    def test_output_reach_follows_both_indirections(self):
        # example.scn reaches virtual outs 9-16 through the AES50-A OUT9-16 block;
        # example-alt.scn through /config/userrout/out 177-184 under a UOUT block —
        # deleting either branch of the resolver reddens exactly one shipped fixture
        reach = R.output_reach(self.sc)
        self.assertEqual(reach[9], ["AES50-A 9"])
        alt = R.output_reach(Scene.load(EXAMPLE_ALT))
        self.assertTrue(all(n in alt for n in range(9, 17)), alt)
        self.assertIn("user-out 9", alt[9][0])

    def test_output_reach_ignores_the_rear_xlr_bank(self):
        # /config/routing/OUT reads OUT1-4 … OUT13-16 on every console; counting it would
        # make every output trivially reachable and the check vacuous
        self.sc.get("/config/routing/AES50A").set_arg(1, "UOUT9-16")
        self.assertNotIn(9, R.output_reach(self.sc))
        self.assertEqual(R.routing_blocks(self.sc, "OUT")[2], "OUT9-12")

    def test_output_aes_mirrors(self):
        m = R.output_aes_mirrors(self.sc)
        self.assertEqual(m[9], ["AES50-A 9"])    # virtual out 9 -> AES50-A 9 (stagebox)
        self.assertEqual(m[1], ["AES50-B 17"])   # physical out 1 also mirrored to AES50-B 17

    def test_resolve_honors_offset_uin_blocks(self):
        # UIN blocks may sit on any bank (e.g. 'UIN9-16 UIN1-8 ...' is a legal console
        # setup): slot 1 must dereference userrout/in entry 9, not entry 1.
        inb = self.sc.get("/config/routing/IN")
        inb.args[0], inb.args[1] = "UIN9-16", "UIN1-8"
        inb.rebuild()
        uin = self.sc.get("/config/userrout/in")
        self.assertEqual(R.resolve_in_slot_number(self.sc, 1), int(uin.args[8]))
        self.assertEqual(R.resolve_in_slot_number(self.sc, 9), int(uin.args[0]))

    def test_resolve_slot_out_of_range_is_off(self):
        # 1-32 are the channel banks, 33-40 the aux/USB bank; nothing beyond
        self.assertEqual(R.resolve_in_slot_number(self.sc, 0), 0)
        self.assertEqual(R.resolve_in_slot_number(self.sc, 41), 0)

    def test_aux_and_usb_player_slots_resolve(self):
        # the aux/USB bank is slots 33-40 (block 5, 'AUX1-4'): the fixture's own
        # /auxin/01-08/config carry exactly those slots, 07/08 being the USB player
        self.assertEqual(R.resolve_in_slot(self.sc, 33), "Aux In 1")
        self.assertEqual(R.resolve_in_slot(self.sc, 38), "Aux In 6")
        self.assertEqual(R.resolve_in_slot(self.sc, 39), "USB player L")
        self.assertEqual(R.resolve_in_slot(self.sc, 40), "USB player R")

    def test_channel_sourced_from_aux_is_not_reported_off(self):
        cfg = self.sc.get("/ch/30/config")
        cfg.set_arg(len(cfg.args) - 1, "33")
        by_ch = {cs.ch: cs for cs in R.channel_sources(self.sc)}
        self.assertEqual(by_ch[30].source, "Aux In 1")
        self.assertIsNone(R.channel_headamp_index(self.sc, 30))  # aux has no head amp

    def test_record_map_decodes_direct_card_block(self):
        # example-alt routes card block 1 directly from AN1-8 (the factory default
        # layout), which must decode to physical inputs, not a raw token
        tracks = dict(R.record_map(Scene.load(EXAMPLE_ALT)))
        self.assertEqual(tracks[1], "Local input 1")
        self.assertEqual(tracks[8], "Local input 8")

    def test_record_map_decodes_output_slot_recording_alt_fixture(self):
        # the alt fixture records the console's own output slots: userrout/out 177-184
        # feed tracks 9-16, and what each carries is whatever /outputs/main/NN assigns
        tracks = dict(R.record_map(Scene.load(EXAMPLE_ALT)))
        self.assertEqual(tracks[9], "Output 9")
        self.assertEqual(tracks[16], "Output 16")
        self.assertEqual(tracks[17], "OFF")

    def test_decode_out_source_ranges(self):
        # the published /config/userrout/out enumeration, 0-208
        from x32scene.tables import decode_out_source
        for num, label in ((0, "OFF"), (1, "Local input 1"), (129, "Card 1"),
                           (161, "Aux In 1"), (167, "Talkback Int"), (168, "Talkback Ext"),
                           (169, "Output 1"), (184, "Output 16"), (185, "P16 1"),
                           (200, "P16 16"), (201, "Aux Out 1"), (206, "Aux Out 6"),
                           (207, "Monitor L"), (208, "Monitor R"), (209, "out-src 209")):
            with self.subTest(num=num):
                self.assertEqual(decode_out_source(num), label)

    def test_decode_tap_is_the_published_output_source_enumeration(self):
        from x32scene.tables import decode_tap
        for tap, label in ((0, "OFF"), (1, "Main L"), (3, "Main M/C"), (4, "Bus 1"),
                           (19, "Bus 16"), (20, "Matrix 1"), (25, "Matrix 6"),
                           (26, "Direct Out Ch 1"), (57, "Direct Out Ch 32"),
                           (58, "Direct Out Aux 1"), (65, "Direct Out Aux 8"),
                           (66, "Direct Out FX 1L"), (67, "Direct Out FX 1R"),
                           (73, "Direct Out FX 4R"), (74, "Monitor L"), (75, "Monitor R"),
                           (76, "Talkback"), (77, "tap 77")):
            with self.subTest(tap=tap):
                self.assertEqual(decode_tap(tap), label)

    def test_decode_source_talkback_not_usb_player(self):
        # /config/userrout/in 167/168 are talkback; the USB player is a channel-source
        # slot (39/40), which resolve_in_slot names without going through this table
        from x32scene.tables import decode_source
        self.assertEqual(decode_source(167), "Talkback Int")
        self.assertEqual(decode_source(168), "Talkback Ext")
        self.assertEqual(decode_source(169), "?169")


class StripPathTest(unittest.TestCase):
    def test_strip_path_forms(self):
        from x32scene.tables import strip_path
        self.assertEqual(strip_path(5), "/ch/05")
        self.assertEqual(strip_path("/bus/01"), "/bus/01")
        self.assertEqual(strip_path("/main/st/"), "/main/st")


if __name__ == "__main__":
    unittest.main(verbosity=2)
