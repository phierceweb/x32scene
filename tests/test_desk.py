"""desk: the read-only view of a running console, exercised against canned replies."""

import contextlib
import io
import json
import time
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.services import desk as D
from x32scene.services.osc import decode_message, encode_message

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

    def test_a_reply_from_another_host_is_waited_out(self):
        """An impostor's /xinfo must not become the desk's identity."""
        evil = encode_message("/xinfo", ["10.0.0.99", "IMPOSTOR", "X32", "0.00"])
        good = encode_message("/xinfo", ["10.0.0.2", "X32-TEST", "X32RACK", "4.06"])
        fake = mock.MagicMock()
        fake.__enter__.return_value = fake
        fake.recvfrom.side_effect = [(evil, ("10.0.0.99", 10023)), (good, ("10.0.0.2", 10023))]
        with mock.patch.object(D.socket, "socket", return_value=fake):
            self.assertEqual(D.xinfo("10.0.0.2"), ("10.0.0.2", "X32-TEST", "X32RACK", "4.06"))

    def test_only_an_impostor_answering_times_out(self):
        evil = encode_message("/xinfo", ["10.0.0.99", "IMPOSTOR", "X32", "0.00"])
        fake = mock.MagicMock()
        fake.__enter__.return_value = fake
        fake.recvfrom.side_effect = [(evil, ("10.0.0.99", 10023)), TimeoutError()]
        with mock.patch.object(D.socket, "socket", return_value=fake):
            with self.assertRaises(D.OscError):
                D.xinfo("10.0.0.2", timeout=0.2)


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


class XinfoTimeoutTest(unittest.TestCase):
    def test_the_sender_filter_cannot_outlive_the_timeout(self):
        """Steady traffic from another host keeps recvfrom succeeding, so the loop has
        to consult the deadline rather than rely on the socket timeout."""
        evil = encode_message("/xinfo", ["10.0.0.99", "IMPOSTOR", "X32", "0.00"])
        fake = mock.MagicMock()
        fake.__enter__.return_value = fake
        fake.recvfrom.return_value = (evil, ("10.0.0.99", 10023))   # never stops arriving
        started = time.monotonic()
        with mock.patch.object(D.socket, "socket", return_value=fake):
            with self.assertRaises(D.OscError):
                D.xinfo("10.0.0.2", timeout=0.05)
        # a wall-clock bound, so losing the deadline fails the test instead of wedging it
        self.assertLess(time.monotonic() - started, 5.0)


class HalfResponsiveDeskTest(unittest.TestCase):
    """A console that answers /xinfo but no /node must not cost a full walk of every slot
    query at the timeout before saying anything."""

    def test_read_desk_gives_up_early(self):
        import socket as _socket
        import threading
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        halt = threading.Event()

        def answer_xinfo_only():
            reply = encode_message("/xinfo", ["127.0.0.1", "X32-TEST", "X32RACK", "4.06"])
            sock.settimeout(0.2)
            while not halt.is_set():
                try:
                    data, addr = sock.recvfrom(65536)
                except (_socket.timeout, OSError):
                    continue                     # closed under us at teardown
                if decode_message(data)[0] in ("/xinfo", "xinfo"):
                    sock.sendto(reply, addr)     # every /node goes unanswered

        threading.Thread(target=answer_xinfo_only, daemon=True).start()
        try:
            started = time.monotonic()
            with self.assertRaises(D.OscError):
                D.read_desk("127.0.0.1", port=port, timeout=0.05)
            self.assertLess(time.monotonic() - started, 10.0)
        finally:
            halt.set()
            time.sleep(0.25)     # let the responder leave recvfrom before the close
            sock.close()
