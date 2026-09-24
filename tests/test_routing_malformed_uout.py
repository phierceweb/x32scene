"""The routing readers resolve only UOUT tokens the console writes. A hand-edited one
(`UOUT`, `UOUT0-7`) names no user-out slot, so record-map shows its tracks unknown, it
carries no output off the console and reads no slot, never slot 48 through a negative
index or slots 1-8 by guess."""

import os
import unittest

from x32scene import Scene
from x32scene.services.preflight import preflight
from x32scene.services.routing import output_reach, record_map, user_out_readers

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def hand_edited(key: str, first_block: str, *, slot48: str | None = None) -> Scene:
    with open(EXAMPLE, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    i = next(i for i, ln in enumerate(lines) if ln.startswith(f"/config/routing/{key} "))
    toks = lines[i].split(" ")
    lines[i] = " ".join([toks[0], first_block, *toks[2:]])
    if slot48 is not None:
        j = next(j for j, ln in enumerate(lines) if ln.startswith("/config/userrout/out "))
        toks = lines[j].split(" ")
        lines[j] = " ".join([*toks[:-1], slot48])
    return Scene.parse("\n".join(lines))


class MalformedUoutReadTest(unittest.TestCase):
    def test_record_map_shows_the_blocks_tracks_unknown(self):
        for tok in ("UOUT", "UOUT-8", "UOUT0-7", "UOUT3-10"):
            with self.subTest(token=tok):
                tracks = dict(record_map(hand_edited("CARD", tok)))
                self.assertEqual({tracks[t] for t in range(1, 9)}, {"?"})
                self.assertNotEqual(tracks[9], "?")

    def test_preflight_record_pins_fail_rather_than_match_a_guess(self):
        sc = hand_edited("CARD", "UOUT")
        want = dict(record_map(Scene.load(EXAMPLE)))[1]
        fs = preflight(sc, {"record": {"1": want}})
        self.assertEqual([f.area for f in fs if f.severity == "FAIL"], ["record 01"])

    def test_no_output_leaves_through_it(self):
        sc = hand_edited("AES50A", "UOUT0-7", slot48="177")   # slot 48 = Output 9
        self.assertFalse(any(r.startswith("AES50-A 1 ") for rs in output_reach(sc).values()
                             for r in rs))

    def test_no_slot_is_read_by_it(self):
        sc = hand_edited("AES50A", "UOUT0-7")
        for slot in (1, 7, 48):
            with self.subTest(slot=slot):
                self.assertFalse(any(r.startswith("AES50-A") and int(r.split()[1]) <= 8
                                     for r in user_out_readers(sc, slot)))


if __name__ == "__main__":
    unittest.main()
