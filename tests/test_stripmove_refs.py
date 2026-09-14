"""Strip reorder: the references outside /ch that are remapped, and those that refuse a move.

Fixture facts the cases lean on: ch05 and ch07 are unlinked; p16 03 taps channel 5 (30) and
p16 05 channel 7 (32); layer B buttons 11-12 hold the factory "P0000"; every key source is 0
and every automix group OFF.
"""

import os
import unittest

from x32scene import Scene
from x32scene.services import stripmove as SM
from x32scene.services.userctrl import strip_index

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
SWAP = {5: 7, 7: 5}


def _load(*raws: str) -> Scene:
    """The fixture with each named line replaced whole."""
    sc = Scene.load(EXAMPLE)
    for raw in raws:
        path = raw.split(" ", 1)[0]
        sc.lines[sc.lines.index(sc.get(path))] = Scene.parse(raw + "\n").lines[0]
    return Scene.parse(sc.dump())


def _refs(move) -> dict:
    return {(r.path, r.field): (r.before, r.after) for r in move.remapped}


class DirectOutTest(unittest.TestCase):
    def test_p16_taps_follow_their_channels(self):
        sc = _load()
        refs = _refs(SM.permute_channels(sc, SWAP))
        self.assertEqual(refs[("/outputs/p16/03", 1)], ("30", "32"))
        self.assertEqual(refs[("/outputs/p16/05", 1)], ("32", "30"))
        self.assertEqual(sc.get("/outputs/p16/03").raw, "/outputs/p16/03 32 PRE OFF")
        self.assertNotIn(("/outputs/p16/04", 1), refs)   # ch06 stays

    def test_other_banks_follow_and_keep_padding_and_every_other_field(self):
        sc = _load("/outputs/main/01  30 <-EQ ON", "/outputs/rec/02 32 PRE",
                   "/outputs/aes/01 58 POST OFF")
        out = sc.dump()
        refs = _refs(SM.permute_channels(sc, SWAP))
        self.assertEqual(sc.get("/outputs/main/01").raw, "/outputs/main/01  32 <-EQ ON")
        self.assertEqual(sc.get("/outputs/rec/02").raw, "/outputs/rec/02 30 PRE")
        self.assertNotIn(("/outputs/aes/01", 1), refs)   # aux-in direct out, not a channel
        self.assertEqual(Scene.parse(out).dump(), out)

    def test_a_move_and_its_inverse_give_back_a_line_with_trailing_padding(self):
        sc = _load("/outputs/main/02 30 POST OFF  ")
        before = sc.dump()
        SM.permute_channels(sc, SWAP)
        self.assertEqual(sc.get("/outputs/main/02").raw, "/outputs/main/02 32 POST OFF  ")
        SM.permute_channels(sc, SWAP)
        self.assertEqual(sc.dump(), before)


class UserControlTest(unittest.TestCase):
    def test_strip_index_decodes_only_codes_that_name_a_strip(self):
        for code, button, want in (('"F04"', False, 4), ("P31", False, 31),
                                   ("S0402", False, 4), ("O04", True, 4), ("I06", True, 6),
                                   ("P0401", True, 4), ("P0451", True, None),
                                   ("F04", True, None), ("O04", False, None),
                                   ("X300", False, None), ("-", False, None),
                                   ("Mn01064", True, None), ("S012", True, None)):
            with self.subTest(code=code, button=button):
                self.assertEqual(strip_index(code, button=button), want)

    def test_encoder_fader_pan_and_send_codes_follow_their_channels(self):
        sc = _load('/config/userctrl/A/enc "F04" "P06" "S0409" "F40"')
        refs = _refs(SM.permute_channels(sc, SWAP))
        self.assertEqual(sc.get("/config/userctrl/A/enc").raw,
                         '/config/userctrl/A/enc "F06" "P04" "S0609" "F40"')
        self.assertEqual(refs[("/config/userctrl/A/enc", 3)], ('"S0409"', '"S0609"'))
        self.assertNotIn(("/config/userctrl/A/enc", 4), refs)

    def test_button_mute_insert_and_channel_page_codes_follow_their_channels(self):
        sc = _load('/config/userctrl/C/btn "O04" "I06" "P0402" "P0451" "O40" "U06" "U02" "U05"')
        SM.permute_channels(sc, SWAP)
        self.assertEqual(sc.get("/config/userctrl/C/btn").args,
                         ['"O06"', '"I04"', '"P0602"', '"P0451"', '"O40"', '"U06"', '"U02"', '"U05"'])

    def test_the_factory_channel_1_page_jump_is_remapped_when_channel_1_moves(self):
        sc = _load()
        refs = _refs(SM.permute_channels(sc, {1: 3, 3: 1}))
        self.assertEqual(refs[("/config/userctrl/B/btn", 7)], ('"P0000"', '"P0200"'))
        self.assertEqual(refs[("/config/userctrl/B/btn", 8)], ('"P0000"', '"P0200"'))
        self.assertEqual(sc.get("/config/userctrl/A/btn").raw,
                         _load().get("/config/userctrl/A/btn").raw)   # FX pages stay


class KeySourceTest(unittest.TestCase):
    def _refused(self, sc: Scene) -> str:
        before = sc.dump()
        with self.assertRaises(ValueError) as cm:
            SM.permute_channels(sc, SWAP)
        self.assertEqual(sc.dump(), before)
        return str(cm.exception)

    def test_a_key_source_naming_a_moving_channel_is_refused(self):
        for raw in ("/ch/09/gate ON GATE -40.0 60.0 0 35.5  860 5",
                    "/ch/05/gate ON GATE -40.5 60.0 0 35.5  752 7",
                    "/ch/09/dyn ON COMP PEAK LOG -15.0 4.0 2 0.00 100 1.59  11 POST 7 100 OFF",
                    "/bus/01/dyn ON COMP RMS LOG 0.0 100 5 0.00 0 7.96  83 POST 5 100 OFF"):
            with self.subTest(line=raw):
                msg = self._refused(_load(raw))
                self.assertIn(raw.split(" ", 1)[0], msg)
                self.assertIn("not desk-verified", msg)

    def test_a_key_source_naming_a_channel_that_stays_is_fine(self):
        sc = _load("/ch/05/gate ON GATE -40.5 60.0 0 35.5  752 6",
                   "/bus/01/dyn ON COMP RMS LOG 0.0 100 5 0.00 0 7.96  83 POST 40 100 OFF")
        SM.permute_channels(sc, SWAP)
        self.assertEqual(sc.get("/ch/07/gate").args[7], "6")
        self.assertEqual(sc.get("/bus/01/dyn").args[12], "40")

    def test_a_matrix_dyn_line_has_no_key_source(self):
        sc = _load("/mtx/01/dyn OFF COMP RMS LOG 0.0 3.0 1 0.00 10 10.0  151 POST 5 OFF")
        SM.permute_channels(sc, SWAP)


class AutomixTest(unittest.TestCase):
    def test_a_group_crossing_the_channel_8_boundary_is_refused(self):
        for raw, mapping in (("/ch/05/automix X  +0.0", {5: 9, 9: 5}),
                             ("/ch/09/automix Y  +0.0", {9: 3, 3: 9})):
            with self.subTest(raw=raw):
                sc = _load(raw)
                with self.assertRaises(ValueError) as cm:
                    SM.permute_channels(sc, mapping)
                self.assertIn("automix", str(cm.exception))
                self.assertIn("1-8", str(cm.exception))

    def test_a_group_moving_inside_one_side_of_the_boundary_is_fine(self):
        sc = _load("/ch/05/automix X  +0.0")
        SM.permute_channels(sc, SWAP)
        self.assertEqual(sc.get("/ch/07/automix").args[0], "X")
        SM.permute_channels(_load("/ch/05/automix OFF  +0.0"), {5: 9, 9: 5})


if __name__ == "__main__":
    unittest.main()
