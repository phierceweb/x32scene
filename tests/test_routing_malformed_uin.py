"""The input resolvers read only IN block tokens the console writes. A hand-edited one
(`UIN`, `UIN0-7`, `A0-7`) names no source, so its slots read `?` and move-inputs refuses
them, never a negative user-in index, another domain's input or the first block by guess."""

import os
import unittest

from x32scene import Scene
from x32scene.services.routing import (resolve_in_slot, resolve_in_slot_number,
                                       uin_in_index, unwritten_in_block)
from x32scene.services.stagebox import move_to_stagebox

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
MALFORMED = ("UIN", "UIN0-7", "UIN3-10", "A", "A0-7", "AN33-40", "XYZ")


def with_in_line(first_block: str | None) -> Scene:
    """example.scn with its IN line's first block replaced, or the line dropped (None), and
    ch01 reading slot 1."""
    with open(EXAMPLE, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    i = next(i for i, ln in enumerate(lines) if ln.startswith("/config/routing/IN "))
    if first_block is None:
        del lines[i]
    else:
        toks = lines[i].split(" ")
        lines[i] = " ".join([toks[0], first_block, *toks[2:]])
    sc = Scene.parse("\n".join(lines))
    sc.get("/ch/01/config").set_arg(-1, "1")
    return sc


class MalformedInBlockTest(unittest.TestCase):
    def test_a_token_the_console_does_not_write_resolves_to_nothing(self):
        for tok in MALFORMED:
            with self.subTest(token=tok):
                sc = with_in_line(tok)
                self.assertEqual(unwritten_in_block(sc, 1), tok)
                self.assertIsNone(uin_in_index(sc, 1))
                self.assertEqual(resolve_in_slot_number(sc, 1), 0)
                self.assertEqual(resolve_in_slot(sc, 1), "?")

    def test_the_next_block_still_resolves(self):
        sc, good = with_in_line("A0-7"), with_in_line("UIN1-8")
        self.assertIsNone(unwritten_in_block(sc, 9))
        self.assertEqual(resolve_in_slot(sc, 9), resolve_in_slot(good, 9))

    def test_written_tokens_keep_their_own_offsets(self):
        self.assertEqual(uin_in_index(with_in_line("UIN9-16"), 1), 8)
        self.assertEqual(resolve_in_slot(with_in_line("A17-24"), 1), "AES50-A input 17")
        self.assertIsNone(unwritten_in_block(with_in_line("UIN9-16"), 1))

    def test_an_absent_in_line_keeps_the_user_in_default(self):
        sc = with_in_line(None)
        self.assertIsNone(unwritten_in_block(sc, 1))
        self.assertEqual(uin_in_index(sc, 1), 0)

    def test_move_inputs_names_the_block_and_token(self):
        for tok in ("UIN0-7", "UIN"):
            with self.subTest(token=tok):
                sc = with_in_line(tok)
                before = sc.dump()
                with self.assertRaises(ValueError) as cm:
                    move_to_stagebox(sc, [(1, 5)], port="A")
                self.assertIn(f"'{tok}'", str(cm.exception))
                self.assertIn("1-8", str(cm.exception))
                self.assertEqual(sc.dump(), before)


if __name__ == "__main__":
    unittest.main()
