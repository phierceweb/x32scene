"""console: the console-wide configuration lines named field by field and read in words,
including the user-assign strings."""

import contextlib
import io
import json
import os
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import console as C
from x32scene.services.userctrl import decode_assignment, strip_name
from x32scene.tables import line_fields

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")


class FieldNamesTest(unittest.TestCase):
    def test_every_console_line_in_the_fixture_is_named_to_its_width(self):
        sc = Scene.load(EXAMPLE)
        for ln in sc.lines[1:]:
            if ln.path.endswith("/par"):
                continue   # FX parameters are named per effect type
            with self.subTest(path=ln.path):
                names = line_fields(ln.path, len(ln.args))
                self.assertIsNotNone(names)
                self.assertEqual(len(names), len(ln.args))

    def test_solo_talk_osc_and_numbered_lines(self):
        self.assertEqual(line_fields("/config/solo", 17)[:3], ["level", "source", "source trim"])
        self.assertEqual(line_fields("/config/talk/A", 4), ["level", "dim", "latch", "dest"])
        self.assertEqual(line_fields("/config/osc", 6)[-2:], ["type", "dest"])
        self.assertEqual(line_fields("/config/userctrl/A/btn", 8)[0], "btn 5")
        self.assertEqual(line_fields("/config/dp48/link", 24)[-1], "pair 24")
        self.assertEqual(line_fields("/outputs/aux/03/delay", 2), ["on", "time"])
        self.assertEqual(line_fields("/outputs/p16/16/iQ", 4), ["group", "speaker", "eq", "model"])


class SectionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = Scene.load(EXAMPLE)
        cls.by = {s.title: dict(s.rows) for s in C.console_sections(cls.sc)}

    def test_monitor(self):
        m = self.by["Monitor"]
        self.assertEqual(m["source"], "LR")
        self.assertEqual(m["solo modes"], "ch PFL, bus PFL, dca PFL")
        self.assertEqual(m["mono bus"], "LR+M, linked to LR OFF")

    def test_talkback_oscillator_recorder(self):
        self.assertEqual(self.by["Talkback"]["enabled"], "ON")
        self.assertIn("Mix bus 1, Mix bus 2", self.by["Talkback"]["talk A"])
        o = self.by["Oscillator"]
        self.assertEqual((o["type"], o["destination"]), ("PINK", "Mix bus 1"))
        self.assertEqual(self.by["USB recorder and automix"]["automix groups"], "X OFF, Y OFF")

    def test_delays_iq_and_user_assign(self):
        self.assertEqual(self.by["Output delays"], {"(none engaged)": ""})
        self.assertEqual(self.by["iQ speakers on P16"], {"(none configured)": ""})
        ua = self.by["User assign"]
        self.assertEqual(ua["set A"], "colour CY")
        self.assertEqual(ua["  A enc 1"], "FX1 param 2")
        self.assertEqual(ua["  A btn 5"], "Mute FX rtn 1L")

    def test_osc_dest_and_talk_dest_tables(self):
        self.assertEqual(len(C.OSC_DESTS), 26)
        self.assertEqual(C.OSC_DESTS[16], "Main L")
        self.assertEqual(C._talk_dests("%000000000000000011"), "Mix bus 1, Mix bus 2")
        self.assertEqual(C._talk_dests("%110000000000000000"), "Main LR, Main M/C")


class UserAssignTest(unittest.TestCase):
    def test_strip_names(self):
        self.assertEqual(strip_name(0), "Ch 1")
        self.assertEqual(strip_name(41), "FX rtn 1R")
        self.assertEqual(strip_name(63), "Bus 16")
        self.assertEqual(strip_name(70), "Main LR")
        self.assertEqual(strip_name(85), "Mute group 6")

    def test_encoders(self):
        cases = {"F00": "Fader Ch 1", "P48": "Pan Bus 1", "S0004": "Send Ch 1 -> bus 5",
                 "X001": "FX1 param 2", "MC05001": "MIDI CC ch 5 value 1", "R008": "Remote Jog",
                 "DG": "Selected channel Dyn ratio", "U2": "X-Live session list", "-": "unassigned"}
        for code, want in cases.items():
            with self.subTest(code=code):
                self.assertEqual(decode_assignment(code, button=False), want)

    def test_buttons(self):
        cases = {"P0001": "Page Channel Ch 1: Config", "P0051": "Page FX: FX1", "P0010": "Page Meter: Channel",
                 "P0036": "Page Setup: Card", "O40": "Mute FX rtn 1L", "O85": "Mute Mute group 6",
                 "I70": "Insert Main LR", "S900": "Show Prev", "S203": "Recall Snippet 3",
                 "S412": "Recall Cue 12", "T4": "USB Play/Stop", "U06": "SD recorder Add marker",
                 "L105": "X-Live marker 5", "A1": "Automix group Y", "R019": "Remote Play",
                 "Mn01064": "MIDI Note toggle ch 1 value 64", '"X201"': "FX3 param 2"}
        for code, want in cases.items():
            with self.subTest(code=code):
                self.assertEqual(decode_assignment(code, button=True), want)

    def test_unknown_shape_is_returned_verbatim(self):
        self.assertEqual(decode_assignment("Z9", button=True), "Z9")
        self.assertEqual(decode_assignment("F", button=False), "F")


class ConsoleCliTest(unittest.TestCase):
    def test_console_and_report(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["console", EXAMPLE]), 0)
        self.assertIn("Monitor\n  source", buf.getvalue())
        self.assertIn("User assign", buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["console", EXAMPLE, "--json"]), 0)
        doc = json.loads(buf.getvalue())
        self.assertEqual(doc["sections"][0]["title"], "Monitor")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["report", EXAMPLE]), 0)
        self.assertIn("## Console", buf.getvalue())
        self.assertIn("### Talkback", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
