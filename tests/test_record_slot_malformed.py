"""A hand-edited CARD block that starts UOUT but is no token the console writes (`UOUT`,
`UOUT-8`, `UOUT0-7`) names no user-out slot: `record_slot` refuses it naming the block and
token, and `set-record` / `band-setup` write nothing."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import routing_edit as RT

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
MALFORMED = ("UOUT", "UOUT-8", "UOUT0-7", "UOUT3-10", "UOUT49-56")


def hand_edited(first_block: str) -> str:
    with open(EXAMPLE, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    i = next(i for i, ln in enumerate(lines) if ln.startswith("/config/routing/CARD "))
    toks = lines[i].split(" ")
    lines[i] = " ".join([toks[0], first_block, *toks[2:]])
    return "\n".join(lines)


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class MalformedCardTokenTest(unittest.TestCase):
    def test_record_slot_names_the_block_and_token(self):
        for tok in MALFORMED:
            sc = Scene.parse(hand_edited(tok))
            for track in (1, 3, 8):
                with self.subTest(token=tok, track=track):
                    with self.assertRaises(ValueError) as cm:
                        RT.record_slot(sc, track)
                    msg = str(cm.exception)
                    self.assertIn("CARD block 1-8", msg)
                    self.assertIn(repr(tok), msg)
                    self.assertNotIn("invalid literal", msg)
            self.assertEqual(RT.record_slot(sc, 9), 9)

    def test_set_record_leaves_the_scene_as_it_was(self):
        text = hand_edited("UOUT0-7")
        sc = Scene.parse(text)
        with self.assertRaises(ValueError):
            RT.set_record(sc, 1, "Output 9")
        self.assertEqual(sc.dump(), text)

    def test_set_record_and_band_setup_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            scene, out = os.path.join(d, "hand.scn"), os.path.join(d, "out.scn")
            plan = os.path.join(d, "plan.json")
            with open(scene, "w", encoding="utf-8") as fh:
                fh.write(hand_edited("UOUT-8"))
            with open(plan, "w", encoding="utf-8") as fh:
                json.dump({"record": {"2": "Output 9"}}, fh)
            rc, text, err = run("set-record", scene, "2", "Output 9", "-o", out)
            self.assertEqual((rc, text), (1, ""))
            self.assertEqual(len(err.strip().splitlines()), 1, err)
            self.assertIn("'UOUT-8'", err)
            self.assertFalse(os.path.exists(out))
            rc, _, err = run("band-setup", scene, plan, "-o", out)
            self.assertEqual(rc, 2)
            self.assertIn("plan failed, nothing written", err)
            self.assertIn("'UOUT-8'", err)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
