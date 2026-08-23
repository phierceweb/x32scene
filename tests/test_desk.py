"""desk: the read-only view of a running console, exercised against canned replies."""

import contextlib
import io
import json
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.services import desk as D
from x32scene.services.osc import encode_message

STAT = {"-stat/selidx": "3", "-stat/solo": "OFF", "-stat/usbmounted": "ON",
        "-stat/xcardtype": "10", "-stat/tape/state": "4", "-stat/tape/file": '"/R_1.wav"'}
LINES = ['/-show/showfile/scene/000 "Opener" "" %000000110 1',
         '/-show/showfile/scene/001 "" "" %000000000 0',
         '/-show/showfile/snippet/003 "Encore" 64 -1 0 0 1',
         '/-show/showfile/cue/000 100 "Cue one" 0 0 3 0 0 0 1',
         '/-libs/ch/001 1 "Kick" 0 %0011111100111000 1',
         '/-libs/fx/002 2 "Vocal Plate" 1 %0000000000000100 1',
         '/-libs/r/001 1 "Local IO" 2 %0000000000000000 1',
         '/-libs/mon/001 1 "Empty" 3 %0000000000000000 1']


def fake_pull(ip, paths, **kw):
    out = []
    for p in paths:
        if p in STAT:
            out.append(f"/{p} {STAT[p]}")
        elif p.startswith("-prefs/"):
            out.append(f"/{p} " + {"-prefs/name": '"X32-TEST"', "-prefs/clockrate": "48K"}.get(p, "OFF"))
        elif p == "-show/showfile/show":
            out.append('/-show/showfile/show "Tour" 0 0 0 0 0 0 0 0 0 0 "4.06"')
        else:
            out.extend(ln for ln in LINES if ln.split(" ")[0] == "/" + p)
    return out, []


class WordsTest(unittest.TestCase):
    def test_selected_strip_and_state(self):
        self.assertEqual(D.selected_strip(3), "Ch 4")
        self.assertEqual(D.selected_strip(41), "FX rtn 1R")
        self.assertEqual(D.selected_strip(71), "Main M/C")
        words = D.state_words(STAT)
        self.assertEqual(words["selected"], "Ch 4")
        self.assertEqual(words["expansion card"], "X-Live")
        self.assertEqual(words["USB recorder"], "record")
        self.assertEqual(words["USB file"], "/R_1.wav")


class ReadDeskTest(unittest.TestCase):
    def test_reads_identity_state_and_occupied_slots(self):
        with mock.patch.object(D, "xinfo", return_value=("10.0.0.2", "X32-TEST", "X32RACK", "4.06")), \
             mock.patch.object(D, "pull_lines", side_effect=fake_pull):
            info = D.read_desk("10.0.0.2")
        self.assertEqual((info.name, info.model, info.firmware), ("X32-TEST", "X32RACK", "4.06"))
        self.assertEqual(info.prefs["-prefs/name"], '"X32-TEST"')
        self.assertTrue(info.show.startswith('"Tour"'))
        self.assertEqual(info.slots["scene"], [(0, "Opener", "safes: Talkback, Effects")])
        self.assertEqual(info.slots["snippet"][0][:2], (3, "Encore"))
        self.assertEqual(info.slots["cue"][0][:2], (0, "Cue one"))
        self.assertEqual([n for _, n, _ in info.slots["ch"]], ["Kick"])
        self.assertEqual(info.slots["fx"][0][2], "Plate Reverb (PLAT)")
        self.assertEqual(info.slots["snippet"][0][2], "Fader, Pan; 32 strip(s)")
        self.assertEqual(info.slots["cue"][0][2], "cue 1.0.0, scene 0, snippet 3")
        self.assertIn("on: gate, eq, dyn", info.slots["ch"][0][2])
        self.assertNotIn(1, [i for i, _, _ in info.slots["scene"]])   # hasdata 0 is skipped

    def test_no_library(self):
        with mock.patch.object(D, "xinfo", return_value=("", "N", "M", "F")), \
             mock.patch.object(D, "pull_lines", side_effect=fake_pull):
            info = D.read_desk("10.0.0.2", library=False)
        self.assertEqual(info.slots, {})


class XinfoTest(unittest.TestCase):
    def test_decodes_the_four_strings(self):
        reply = encode_message("/xinfo", ["10.0.0.2", "X32-TEST", "X32RACK", "4.06"])
        fake = mock.MagicMock()
        fake.__enter__.return_value = fake
        fake.recvfrom.return_value = (reply, ("10.0.0.2", 10023))
        with mock.patch.object(D.socket, "socket", return_value=fake):
            self.assertEqual(D.xinfo("10.0.0.2"), ("10.0.0.2", "X32-TEST", "X32RACK", "4.06"))


class DeskCliTest(unittest.TestCase):
    def test_desk_command_text_and_json(self):
        with mock.patch.object(D, "xinfo", return_value=("10.0.0.2", "X32-TEST", "X32RACK", "4.06")), \
             mock.patch.object(D, "pull_lines", side_effect=fake_pull):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["desk", "--ip", "10.0.0.2"]), 0)
            out = buf.getvalue()
            self.assertIn("X32-TEST  X32RACK  firmware 4.06", out)
            self.assertIn("selected         Ch 4", out)
            self.assertIn("scenes: 1", out)
            self.assertIn("effect presets: 1", out)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["desk", "--ip", "10.0.0.2", "--json", "--no-library"]), 0)
            doc = json.loads(buf.getvalue())
            self.assertEqual(doc["state"]["expansion card"], "X-Live")
            self.assertEqual(doc["slots"], {})

    def test_needs_an_ip(self):
        with mock.patch.dict("os.environ", {"X32SCENE_IP": ""}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(main(["desk"]), 0)


if __name__ == "__main__":
    unittest.main()
