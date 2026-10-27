"""Under ``/config/routing PLAY`` every slot resolves through the PLAY bank: sources, head
amps, set-input's search, the regenerated config, and the desk lines a kept head amp needs."""
import os
import unittest
from datetime import date

from x32scene.model import Scene
from x32scene.services.load_keep import Keep
from x32scene.services.preflight_regen import regenerate
from x32scene.services.routing import (channel_headamp_index, channel_sources, resolve_in_slot,
                                       resolve_in_slot_number, routing_switch, unwritten_in_block)
from x32scene.services.routing_edit import channel_slot, set_routing, set_routswitch
from x32scene.tables import routing_vocab

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def play() -> Scene:
    sc = Scene.load(EXAMPLE)
    set_routswitch(sc, "PLAY")
    return sc


class InputBankTest(unittest.TestCase):
    def test_the_switch_names_the_bank(self):
        from x32scene.services.routing import input_bank
        self.assertEqual(input_bank(Scene.load(EXAMPLE)), "IN")
        self.assertEqual(input_bank(play()), "PLAY")
        self.assertEqual(input_bank(Scene.parse('#4.0# "X" "" %000000000 1\n')), "IN")

    def test_sources_follow_the_play_bank(self):
        rec, pl = Scene.load(EXAMPLE), play()
        self.assertEqual(resolve_in_slot(rec, 1), "Local input 1")
        self.assertEqual(resolve_in_slot(pl, 1), "USB Card (DAW) 1")
        self.assertEqual(resolve_in_slot(pl, 25), resolve_in_slot(rec, 25))
        self.assertEqual(channel_sources(pl)[0].source, "USB Card (DAW) 1")

    def test_head_amps_follow_the_play_bank(self):
        rec, pl = Scene.load(EXAMPLE), play()
        self.assertIsNone(channel_headamp_index(pl, 1))   # a card return has no head amp
        self.assertEqual(channel_headamp_index(pl, 25), channel_headamp_index(rec, 25))

    def test_an_unwritten_play_token_has_no_source(self):
        pl = play()
        pl.get("/config/routing/PLAY").set_arg(0, "UIN")
        self.assertEqual(unwritten_in_block(pl, 1), "UIN")
        self.assertEqual(resolve_in_slot(pl, 1), "?")
        self.assertIsNone(unwritten_in_block(Scene.load(EXAMPLE), 1))
        self.assertIsNone(unwritten_in_block(pl, 1, bank="IN"))   # bank= reads the other bank

    def test_the_usb_player_slots_have_no_source_number(self):
        """Slots 39/40 are the USB player under every aux token: no routed input, no head amp."""
        for tok in routing_vocab("IN", "AUX"):
            sc = Scene.load(EXAMPLE)
            set_routing(sc, "IN", {"AUX": tok})
            sc.get("/ch/32/config").set_arg(3, "39")
            with self.subTest(tok=tok):
                self.assertEqual((resolve_in_slot_number(sc, 39), resolve_in_slot_number(sc, 40)),
                                 (0, 0))
                self.assertIsNone(channel_headamp_index(sc, 32))
                self.assertEqual(resolve_in_slot(sc, 39), "USB player L")

    def test_bank_reads_the_other_bank(self):
        pl = play()
        self.assertEqual(resolve_in_slot_number(pl, 1), 129)              # the PLAY bank's card 1
        self.assertEqual(resolve_in_slot_number(pl, 1, bank="IN"), 1)    # the IN bank's local 1

    def test_a_switch_token_the_desk_does_not_write_selects_in(self):
        sc = Scene.load(EXAMPLE)
        sc.get("/config/routing").set_arg(0, "play")
        self.assertEqual(routing_switch(sc), "play")
        from x32scene.services.routing import input_bank
        self.assertEqual(input_bank(sc), "IN")
        self.assertEqual(resolve_in_slot(sc, 1), "Local input 1")


class SetInputTest(unittest.TestCase):
    def test_a_source_name_is_found_through_the_play_bank(self):
        self.assertEqual(channel_slot(play(), "card 3"), 3)
        with self.assertRaises(ValueError):
            channel_slot(Scene.load(EXAMPLE), "card 3")   # no IN block reads it

    def test_a_source_no_play_block_reads_names_the_bank(self):
        with self.assertRaisesRegex(ValueError, r"/config/routing/PLAY; re-patch one of its blocks"):
            channel_slot(play(), "local 5")


class RegenerateTest(unittest.TestCase):
    def test_the_config_reads_the_play_bank(self):
        doc = regenerate(play(), EXAMPLE, date(2026, 1, 1))
        self.assertEqual(doc["channels"]["1"]["source"], "USB Card (DAW) 1")
        self.assertNotIn("gain", doc["channels"]["1"])


class KeepHeadAmpTest(unittest.TestCase):
    def test_a_kept_head_amp_reads_the_switch_and_the_play_bank(self):
        paths = Keep(globs=["/headamp/000"]).desk_paths(Scene.load(EXAMPLE))
        self.assertIn("/config/routing", paths)
        self.assertIn("/config/routing/PLAY", paths)

    def test_the_partner_of_a_kept_head_amp_is_found_through_the_play_bank(self):
        """Under PLAY the desk reads ch 1/2 on AES50-B 1-2, which no IN block reads: a
        write to head amp 80 is copied onto 81 across the linked pair."""
        desk = play()
        desk.get("/config/routing/PLAY").set_arg(0, "B1-8")
        desk.get("/config/chlink").set_arg(0, "ON")
        self.assertEqual(Keep(globs=["/headamp/080"]).resolve(desk, desk),
                         [("/headamp/080 and its linked sides", ["/headamp/080", "/headamp/081"])])
        rec = Scene.load(EXAMPLE)
        rec.get("/config/chlink").set_arg(0, "ON")
        self.assertEqual(Keep(globs=["/headamp/080"]).resolve(rec, rec),
                         [("/headamp/080", ["/headamp/080"])])

    def test_a_kept_routing_line_keeps_the_desks_bank_for_the_widening(self):
        """With /config/routing kept the desk stays on PLAY while the file's PLAY bank is
        written, so ch 11/12 (linked) read AES50-A 3/4 and head amp 34 widens to 35."""
        desk, target = play(), Scene.load(EXAMPLE)
        target.get("/config/routing/PLAY").set_arg(1, "A1-8")
        self.assertEqual(Keep(globs=["/config/routing", "/headamp/034"]).resolve(target, desk),
                         [("/config/routing", ["/config/routing"]),
                          ("/headamp/034 and its linked sides", ["/headamp/034", "/headamp/035"])])

    def test_a_kept_in_line_keeps_the_desks_blocks_for_the_widening(self):
        """The file re-routes 9-16 to AES50-A 1-8 but that line is kept, so ch 11/12 go on
        reading user-in slots 11/12, which the file re-points to AES50-A 8/9."""
        desk, target = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        target.get("/config/routing/IN").set_arg(1, "A1-8")
        target.get("/config/userrout/in").set_arg(10, "40")
        target.get("/config/userrout/in").set_arg(11, "41")
        self.assertEqual(Keep(globs=["/config/routing/IN", "/headamp/039"]).resolve(target, desk),
                         [("/config/routing/IN", ["/config/routing/IN"]),
                          ("/headamp/039 and its linked sides", ["/headamp/039", "/headamp/040"])])

    def test_a_config_line_kept_through_its_pair_is_the_desks_too(self):
        """Keeping ch 1's config keeps ch 2's (linked), so the model reads the desk's ch 2
        slot, 6, through the file's user patch, where slot 6 now feeds AES50-A 8: head amp 39
        belongs to ch 2 and a write to its partner's head amp 0 would move it."""
        desk, target = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        for sc in (desk, target):
            sc.get("/config/chlink").set_arg(0, "ON")
        desk.get("/ch/02/config").set_arg(3, "6")
        target.get("/config/userrout/in").set_arg(5, "40")
        kept = dict(Keep(globs=["/ch/01/config", "/headamp/039"]).resolve(target, desk))
        self.assertEqual(kept["/ch/01/config and its linked sides"], ["/ch/01/config", "/ch/02/config"])
        self.assertIn("/headamp/000", kept["/headamp/039 and its linked sides"])

    def test_a_config_line_kept_through_its_pair_is_not_modelled_as_the_files(self):
        """The file moves ch 2 to slot 6 but that config line is kept: at write time ch 2 still
        reads slot 2 and head amp 1, so head amp 5 has no linked reader and widens to nothing."""
        desk, target = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        for sc in (desk, target):
            sc.get("/config/chlink").set_arg(0, "ON")
        target.get("/ch/02/config").set_arg(3, "6")
        kept = dict(Keep(globs=["/ch/01/config", "/headamp/005"]).resolve(target, desk))
        self.assertEqual(kept["/headamp/005"], ["/headamp/005"])


if __name__ == "__main__":
    unittest.main()
