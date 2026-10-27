"""`inputs` and `set-input` resolve through the PLAY bank when the routing switch is PLAY, and
say so; `inputs --json` carries the switch."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services.routing import routing_switch

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
NOTE = "the routing switch is PLAY: sources resolve through the PLAY bank, not the IN bank"


class PlayNoteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.rec = EXAMPLE
        sc = Scene.load(EXAMPLE)
        sc.get("/config/routing").set_arg(0, "PLAY")
        self.play = os.path.join(self.tmp, "play.scn")
        sc.save(self.play)

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = main(list(argv))
        return rc, out.getvalue()

    def test_routing_switch_reads_the_line(self):
        self.assertEqual(routing_switch(Scene.load(self.rec)), "REC")
        self.assertEqual(routing_switch(Scene.load(self.play)), "PLAY")
        self.assertIsNone(routing_switch(Scene.parse('#4.0# "X" "" %000000000 1\n')))

    def test_inputs_notes_play_and_not_rec(self):
        rc, out = self.run_cli("inputs", self.play)
        self.assertEqual(rc, 0)
        self.assertIn(f"note: {NOTE}", out)
        self.assertRegex(out, r"ch01 .*-> USB Card \(DAW\) 1\b")   # the PLAY bank's CARD1-8
        rc, out = self.run_cli("inputs", self.rec)
        self.assertEqual(rc, 0)
        self.assertNotIn("note:", out)
        self.assertRegex(out, r"ch01 .*-> Local input 1\b")

    def test_report_reads_the_play_bank(self):
        rc, out = self.run_cli("report", self.play)
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"\| 0?1 \| Kick \| USB Card \(DAW\) 1")

    def test_a_switch_token_the_desk_does_not_write_is_noted(self):
        sc = Scene.load(EXAMPLE)
        sc.get("/config/routing").set_arg(0, "play")
        odd = os.path.join(self.tmp, "odd.scn")
        sc.save(odd)
        rc, out = self.run_cli("inputs", odd)
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"ch01 .*-> Local input 1\b")
        self.assertIn("note: /config/routing is 'play', not REC or PLAY", out)
        rc, out = self.run_cli("inputs", odd, "--json")
        self.assertEqual(json.loads(out)["switch"], "play")

    def test_inputs_json_carries_the_switch(self):
        for path, want in ((self.play, "PLAY"), (self.rec, "REC")):
            rc, out = self.run_cli("inputs", path, "--json")
            self.assertEqual(rc, 0)
            doc = json.loads(out)
            self.assertEqual(doc["switch"], want)
            self.assertEqual(doc["channels"][0]["ch"], 1)

    def test_set_input_notes_play_and_not_rec(self):
        out_play, out_rec = (os.path.join(self.tmp, n) for n in ("p.scn", "r.scn"))
        rc, out = self.run_cli("set-input", self.play, "1", "card 5", "-o", out_play)
        self.assertEqual(rc, 0, out)
        self.assertIn("ch01 source -> slot 5 (USB Card (DAW) 5); note: " + NOTE, out)
        rc, out = self.run_cli("set-input", self.rec, "1", "local 5", "-o", out_rec)
        self.assertEqual(rc, 0, out)
        self.assertIn("ch01 source -> slot 5 (Local input 5)", out)
        self.assertNotIn("note:", out)

    def test_set_input_refuses_a_source_no_play_block_reads(self):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = main(["set-input", self.play, "1", "local 5", "-o", os.path.join(self.tmp, "x.scn")])
        self.assertEqual(rc, 1)
        self.assertIn("/config/routing/PLAY", err.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x.scn")))


if __name__ == "__main__":
    unittest.main()
