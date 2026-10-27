"""Stage-box moves and the two routing banks: `/config/userrout/in` serves IN and PLAY
alike, so readers through either count, and a bank's line decides what can be counted."""

import unittest

from x32scene import Scene
from x32scene.services import routing_edit as RE
from x32scene.services import stagebox as SB

from tests.test_move_inputs import SCENE


def _with_play(line: str | None) -> Scene:
    """The fixture with its PLAY line's blocks replaced, or the line removed when None."""
    out = []
    for ln in Scene.load(SCENE).dump().splitlines(True):
        if ln.startswith("/config/routing/PLAY "):
            if line is not None:
                out.append(f"/config/routing/PLAY {line}\n")
        else:
            out.append(ln)
    return Scene.parse("".join(out))


class TwoBankTest(unittest.TestCase):
    def test_a_user_in_slot_the_other_bank_reads_through_is_refused(self):
        """/config/userrout/in is shared by the IN and PLAY banks, so a move re-sources a
        channel that reads the slot through either; the other bank's reader is named."""
        sc = Scene.load(SCENE)
        RE.set_routing(sc, "IN", {"1-8": "UIN25-32"})   # ch01 reads slot 25 under REC
        with self.assertRaisesRegex(ValueError, "ch25 shares user-in slot 25 with ch01:"):
            SB.move_to_stagebox(sc, [(25, 20)], port="A")
        RE.set_routswitch(sc, "PLAY")                    # ch01 now reads the card, by PLAY
        with self.assertRaisesRegex(ValueError, r"ch25 shares user-in slot 25 with ch01 \(IN bank\):"):
            SB.move_to_stagebox(sc, [(25, 20)], port="A")

    def test_gain_onto_an_input_a_strip_reads_through_the_other_bank_is_refused(self):
        """ch01 reads AES50-A 17 directly through the PLAY bank; carrying ch09's head amp
        there changes what ch01 hears under PLAY, and moving ch01's IN-bank slot away
        changes nothing about that."""
        sc = Scene.load(SCENE)
        RE.set_routing(sc, "PLAY", {"1-8": "A17-24"})
        with self.assertRaisesRegex(ValueError, r"AES50-A input 17 still feeds ch01 \(PLAY bank\)"):
            SB.move_to_stagebox(sc, [(9, 17)], port="A")
        with self.assertRaisesRegex(ValueError, r"AES50-A input 17 still feeds ch01 \(PLAY bank\)"):
            SB.move_to_stagebox(sc, [(9, 17), (1, 30)], port="A")

    def test_a_strip_reading_the_input_through_both_banks_is_not_offered_as_a_move(self):
        """ch21 reads AES50-A 5 through a PLAY user-in slot and directly through IN: moving
        it in this batch would leave the IN reading, so the hint is withheld and the batch
        that follows it is refused."""
        sc = Scene.load(SCENE)
        RE.set_routswitch(sc, "PLAY")
        RE.set_routing(sc, "PLAY", {"1-8": "UIN1-8", "17-24": "UIN17-24"})
        with self.assertRaisesRegex(ValueError, r"still feeds ch21 \(both banks\)") as cm:
            SB.move_to_stagebox(sc, [(1, 5)], port="A")
        self.assertNotIn("move ch21 too", str(cm.exception))
        with self.assertRaisesRegex(ValueError, "still feeds ch21"):
            SB.move_to_stagebox(sc, [(1, 5), (21, 30)], port="A")

    def test_a_bank_with_no_routing_line_has_no_readers(self):
        sc = _with_play(None)
        RE.set_routing(sc, "IN", {"1-8": "UIN9-16", "9-16": "UIN1-8"})   # ch01 on slot 9, ch09 on slot 1
        moved = SB.move_to_stagebox(sc, [(1, 20)], port="A")
        self.assertEqual([(m.ch, m.new_source) for m in moved], [(1, 52)])

    def test_a_missing_live_bank_line_is_refused(self):
        sc = _with_play(None)
        RE.set_routswitch(sc, "PLAY")
        with self.assertRaisesRegex(ValueError, "^/config/routing/PLAY is missing"):
            SB.move_to_stagebox(sc, [(1, 20)], port="A")

    def test_a_short_routing_line_in_either_bank_is_refused(self):
        """A line short of its five blocks leaves readers past its end uncounted, so no move is
        reasoned about under one: the channel's own block in range or not, live bank or not."""
        sc = _with_play("UIN1-8 UIN9-16")
        RE.set_routswitch(sc, "PLAY")
        for ch in (1, 25):
            with self.subTest(ch=ch), self.assertRaisesRegex(
                    ValueError, r"^/config/routing/PLAY carries 2 block\(s\), not 5"):
                SB.move_to_stagebox(sc, [(ch, 20)], port="A")
        sc = _with_play("UIN1-8 UIN9-16")                        # REC: PLAY is the other bank
        with self.assertRaisesRegex(ValueError, r"/config/routing/PLAY carries 2 block\(s\), not 5"):
            SB.move_to_stagebox(sc, [(1, 13)], port="A")

    def test_a_move_onto_the_input_the_channel_already_reads_changes_nothing(self):
        """ch25 already reads AES50-A 9 through user-in slot 25: nothing is re-sourced and no
        head amp moves, whatever else the other bank reads through that slot or input."""
        for play, gain in (("CARD1-8 UIN25-32 CARD17-24 UIN25-32 AUX1-4", False),
                           ("CARD1-8 CARD9-16 CARD17-24 A9-16 AUX1-4", True),
                           ("CARD1-8 A9-16 CARD17-24 UIN25-32 AUX1-4", True)):
            with self.subTest(play=play, gain=gain):
                sc = _with_play(play)
                before = sc.dump()
                moved = SB.move_to_stagebox(sc, [(25, 9)], port="A", move_gain=gain)
                self.assertEqual([(m.ch, m.old_source, m.new_source) for m in moved], [(25, 41, 41)])
                self.assertEqual(sc.dump(), before)

    def test_an_aux_in_on_the_usb_player_slots_is_not_a_user_in_reader(self):
        """Slots 39 and 40 are the USB player, which no UIN aux token reaches: under PLAY ch08
        moves although auxin08 sits on slot 40, under IN ch07 although auxin07 sits on 39."""
        sc = _with_play("CARD1-8 CARD9-16 CARD17-24 UIN25-32 UIN1-2")
        self.assertEqual([m.ch for m in SB.move_to_stagebox(sc, [(8, 13)], port="A")], [8])
        sc = Scene.load(SCENE)
        RE.set_routing(sc, "IN", {"AUX": "UIN1-2"})
        self.assertEqual([m.ch for m in SB.move_to_stagebox(sc, [(7, 13)], port="A")], [7])

    def test_a_usb_player_aux_in_never_reads_a_direct_input(self):
        """Under `B1-6` the aux block feeds slots 33-38 from AES50-B 1-6; slots 39/40 stay the
        USB player, so auxin07 does not read AES50-B 7 and ch02 may take it."""
        sc = Scene.load(SCENE)
        RE.set_routing(sc, "IN", {"AUX": "B1-6"})
        self.assertEqual([m.ch for m in SB.move_to_stagebox(sc, [(2, 7)], port="B")], [2])

    def test_the_hint_never_names_a_channel_on_an_aux_slot(self):
        """ch10 reads AES50-A 13 through the aux block's user-in slot 3: a channel on an aux
        slot cannot move, so it is not offered."""
        sc = Scene.load(SCENE)
        RE.set_routing(sc, "IN", {"AUX": "UIN1-6"})
        sc.get("/ch/10/config").set_arg(3, "35")
        sc.get("/ch/03/config").set_arg(3, "0")
        sc.get("/auxin/03/config").set_arg(3, "0")
        sc.get("/config/userrout/in").set_arg(2, "45")
        with self.assertRaisesRegex(ValueError, "still feeds ch10") as cm:
            SB.move_to_stagebox(sc, [(7, 13)], port="A")
        self.assertNotIn(" too", str(cm.exception))

    def test_a_no_op_move_in_the_same_bank_changes_nothing(self):
        """ch09 shares user-in slot 25 with ch25 through the IN bank; ch25 onto the input it
        already reads is not a move, so the share is no refusal and nothing is carried."""
        sc = Scene.load(SCENE)
        RE.set_routing(sc, "IN", {"9-16": "UIN25-32"})
        before = sc.dump()
        moved = SB.move_to_stagebox(sc, [(25, 9)], port="A")
        self.assertEqual([(m.ch, m.carried) for m in moved], [(25, False)])
        self.assertEqual(sc.dump(), before)

    def test_a_no_op_slot_still_counts_as_a_reader_whatever_the_order(self):
        """ch01 already reads AES50-A 8; moving ch02 there is refused in either order, and
        with ch01's no-op listed first the readers named still include ch01."""
        sc = Scene.load(SCENE)
        sc.get("/config/userrout/in").set_arg(0, "40")
        with self.assertRaisesRegex(ValueError, "still feeds ch01, ch24"):
            SB.move_to_stagebox(sc, [(2, 8), (1, 8)], port="A")
        with self.assertRaisesRegex(ValueError, "ch01 and ch02 both move to AES50-A input 8"):
            SB.move_to_stagebox(sc, [(1, 8), (2, 8)], port="A")

    def test_an_empty_or_overlong_routing_line_is_short_of_its_blocks(self):
        for line, n in (("", 0), ("CARD1-8 CARD9-16 CARD17-24 UIN25-32 AUX1-4 AUX1-4", 6)):
            with self.subTest(blocks=n), self.assertRaisesRegex(
                    ValueError, rf"^/config/routing/PLAY carries {n} block\(s\), not 5"):
                SB.move_to_stagebox(_with_play(line), [(1, 20)], port="A")

    def test_the_hint_is_withheld_when_the_named_move_would_itself_be_refused(self):
        """ch09 and ch25 both read AES50-A 9 through user-in slot 25: moving either alone is
        a shared-slot refusal, so neither is offered."""
        sc = Scene.load(SCENE)
        RE.set_routing(sc, "IN", {"9-16": "UIN25-32"})
        with self.assertRaisesRegex(ValueError, "still feeds ch09, ch25") as cm:
            SB.move_to_stagebox(sc, [(1, 9)], port="A")
        self.assertNotIn(" too", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
