"""Record patch by card track: a track resolves through its CARD block to a user-out slot,
and the slot takes a source in the words `record-map` prints.

Fixture facts the cases lean on: example.scn's CARD blocks are UOUT1-8 … UOUT25-32 with
user-out slots 1-16 holding sources 1-16; example-alt.scn's first CARD block is AN1-8.
"""

import os
import unittest

from x32scene import Scene
from x32scene.services import routing_edit as RT
from x32scene.services.routing import record_map, user_out_readers
from x32scene.tables import decode_out_source

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EXAMPLE_ALT = os.path.join(FIX, "example-alt.scn")


def _changed(before: Scene, after: Scene) -> list[str]:
    return [ln.path for ln in after.lines if ln.path and before.get(ln.path).raw != ln.raw]


class EncodeOutSourceTest(unittest.TestCase):
    def test_every_word_record_map_prints_encodes_back(self):
        for n in range(209):
            with self.subTest(n=n):
                self.assertEqual(RT.encode_out_source(decode_out_source(n)), n)

    def test_short_words_and_numbers(self):
        cases = {"off": 0, "local 5": 5, "aes50-a 3": 35, "AES50-B 12": 92, "card 7": 135,
                 "usb 7": 135, "aux 2": 162, "aux in 2": 162, "talkback ext": 168,
                 "output 9": 177, "out 9": 177, "p16 5": 189, "aux out 2": 202,
                 "monitor l": 207, "Monitor  R": 208, 208: 208, "169": 169, 0: 0}
        for word, n in cases.items():
            with self.subTest(word=word):
                self.assertEqual(RT.encode_out_source(word), n)

    def test_refusals(self):
        cases = (("bus 9", "unknown user-out source"), ("output 17", "output sources run 1-16"),
                 ("p16 0", "p16 sources run 1-16"), ("aux out 7", "aux out sources run 1-6"),
                 ("local 33", "local inputs run 1-32"), (209, "0-208"), ("-1", "unknown"),
                 (True, "a name or a number"), ("", "unknown user-out source"))
        for value, why in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as cm:
                    RT.encode_out_source(value)
                self.assertIn(why, str(cm.exception))


class RecordSlotTest(unittest.TestCase):
    def test_uout_blocks_resolve_track_to_slot(self):
        sc = Scene.load(EXAMPLE)
        self.assertEqual([RT.record_slot(sc, t) for t in (1, 5, 8, 9, 32)], [1, 5, 8, 9, 32])

    def test_an_offset_block_names_its_own_first_slot(self):
        sc = Scene.load(EXAMPLE)
        RT.set_routing(sc, "CARD", {"1-8": "UOUT41-48", "25-32": "UOUT9-16"})
        self.assertEqual(RT.record_slot(sc, 2), 42)
        self.assertEqual(RT.record_slot(sc, 32), 16)

    def test_a_non_uout_block_is_refused_naming_its_token(self):
        sc = Scene.load(EXAMPLE_ALT)
        with self.assertRaises(ValueError) as cm:
            RT.record_slot(sc, 3)
        self.assertIn("CARD block 1-8 is AN1-8, not a UOUT block", str(cm.exception))
        self.assertEqual(RT.record_slot(sc, 9), 9)

    def test_track_range_and_missing_lines(self):
        sc = Scene.load(EXAMPLE)
        for bad in (0, 33, True, "5"):
            with self.subTest(track=bad):
                with self.assertRaises(ValueError):
                    RT.record_slot(sc, bad)
        no_card = Scene.parse("\n".join(ln.raw for ln in sc.lines
                                        if ln.path != "/config/routing/CARD") + "\n")
        with self.assertRaises(KeyError):
            RT.record_slot(no_card, 1)


class SetRecordTest(unittest.TestCase):
    def test_every_source_family_reads_back_through_record_map(self):
        cases = {"off": "OFF", "Local input 5": "Local input 5", "aes50-a 3": "AES50-A input 3",
                 "aes50-b 48": "AES50-B input 48", "Card 7": "Card 7", "aux 6": "Aux In 6",
                 "Talkback Int": "Talkback Int", "Output 9": "Output 9", "p16 16": "P16 16",
                 "Aux Out 2": "Aux Out 2", "monitor l": "Monitor L", 208: "Monitor R"}
        for word, words in cases.items():
            with self.subTest(word=word):
                sc = Scene.load(EXAMPLE)
                self.assertEqual(RT.set_record(sc, 5, word), words)
                self.assertEqual(record_map(sc)[4], (5, words))

    def test_writes_one_token_of_one_line_and_round_trips(self):
        before, sc = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        RT.set_routing(before, "CARD", {"9-16": "UOUT41-48"})
        RT.set_routing(sc, "CARD", {"9-16": "UOUT41-48"})
        RT.set_record(sc, 10, "Output 3")
        self.assertEqual(_changed(before, sc), ["/config/userrout/out"])
        old, new = before.get("/config/userrout/out").args, sc.get("/config/userrout/out").args
        self.assertEqual([i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b], [41])
        self.assertEqual(new[41], "171")
        text = sc.dump()
        self.assertEqual(Scene.parse(text).dump(), text)
        self.assertEqual(sc.get("/config/userrout/out").raw,
                         "/config/userrout/out " + " ".join(new))

    def test_a_refusal_writes_nothing(self):
        sc = Scene.load(EXAMPLE_ALT)
        text = sc.dump()
        for track, source in ((1, "Output 1"), (9, "bus 9"), (40, "off")):
            with self.subTest(track=track):
                with self.assertRaises(ValueError):
                    RT.set_record(sc, track, source)
                self.assertEqual(sc.dump(), text)

    def test_readers_name_every_block_that_reads_a_slot(self):
        sc = Scene.load(EXAMPLE)
        RT.set_routing(sc, "AES50A", {"1-8": "UOUT1-8", "9-16": "OUT9-16"})
        RT.set_routing(sc, "AES50B", {"1-8": "AN1-8", "17-24": "UOUT1-8"})
        RT.set_routing(sc, "CARD", {"25-32": "UOUT1-8"})
        RT.set_routing(sc, "OUT", {"5-8": "UOUT5-8"})
        self.assertEqual(user_out_readers(sc, 5), ["AES50-A 5", "AES50-B 21", "CARD track 5",
                                                   "CARD track 29", "XLR out 5"])
        self.assertEqual(user_out_readers(sc, 48),
                         ["AES50-A 48", "AES50-B 32", "AES50-B 40", "AES50-B 48"])


if __name__ == "__main__":
    unittest.main()
