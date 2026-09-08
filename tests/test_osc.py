"""OSC /node live-pull: wire encoding + a fake console on loopback UDP."""
import socket
import threading
import unittest
from unittest import mock

from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.osc import (
    decode_message, encode_message, pull_lines, pull_scene_like,
)

CANNED = {
    "ch/01/config": '/ch/01/config "Kick" 2 YEi 1',
    "ch/01/eq/1": "/ch/01/eq/1 PEQ 36.0 +0.00 1.0",
    "ch/01/dyn": "/ch/01/dyn OFF COMP RMS LOG -21.5 10 3 0.00 84 0.32  10 POST 0 100 OFF",
}


class FakeConsole(threading.Thread):
    """Answers /node queries from CANNED; ignores unknown paths (client times out).

    ``delay`` postpones every reply, as a desk on a congested link would.
    """

    def __init__(self, delay: float = 0.0):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.delay = delay
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                data, addr = self.sock.recvfrom(65536)
            except socket.timeout:
                continue
            osc_addr, args = decode_message(data)
            if osc_addr == "/node" and args and args[0] in CANNED:
                if self.delay:
                    self._halt.wait(self.delay)
                reply = encode_message("node", [CANNED[args[0]] + "\n"])
                self.sock.sendto(reply, addr)

    def stop(self):
        self._halt.set()
        self.join()
        self.sock.close()


class WireFormatTest(unittest.TestCase):
    def test_encode_pads_to_four(self):
        msg = encode_message("/node", ["ch/01/config"])
        self.assertEqual(msg[:8], b"/node\x00\x00\x00")
        self.assertEqual(msg[8:12], b",s\x00\x00")
        self.assertTrue(msg.endswith(b"\x00"))
        self.assertEqual(len(msg) % 4, 0)

    def test_decode_roundtrip(self):
        addr, args = decode_message(encode_message("/node", ["ch/01/config"]))
        self.assertEqual(addr, "/node")
        self.assertEqual(args, ["ch/01/config"])

    def test_decode_int_and_float(self):
        addr, args = decode_message(encode_message("/x", [3, 0.5]))
        self.assertEqual(args[0], 3)
        self.assertAlmostEqual(args[1], 0.5, places=6)

    def test_truncated_int_arg_raises_oscerror(self):
        from x32scene.services.osc import OscError
        bad = encode_message("/x", [3])[:-2]
        with self.assertRaises(OscError):
            decode_message(bad)


class FakeConsoleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.console = FakeConsole()
        cls.console.start()

    @classmethod
    def tearDownClass(cls):
        cls.console.stop()

    def test_pull_lines_returns_scene_format(self):
        lines, missing = pull_lines("127.0.0.1", ["ch/01/config", "ch/01/eq/1"],
                                    port=self.console.port, timeout=0.3)
        self.assertEqual(missing, [])
        self.assertEqual(lines[0], CANNED["ch/01/config"])

    def test_unanswered_path_collected_as_missing(self):
        lines, missing = pull_lines("127.0.0.1", ["ch/01/config", "ch/99/nope"],
                                    port=self.console.port, timeout=0.3, retries=0)
        self.assertEqual(len(lines), 1)
        self.assertEqual(missing, ["ch/99/nope"])

    def test_fail_fast_when_nothing_answers(self):
        from x32scene.services.osc import OscError
        with self.assertRaises(OscError):
            pull_lines("127.0.0.1", ["ch/99/a", "ch/99/b", "ch/99/c", "ch/01/config"],
                       port=self.console.port, timeout=0.2, retries=0, fail_fast=3)

    def test_pull_scene_like_reference(self):
        ref = Scene.parse('#4.0# "REF" "" %000000000 1\n'
                          + "\n".join(CANNED.values()) + "\n")
        scene, missing = pull_scene_like(ref, "127.0.0.1",
                                         port=self.console.port, timeout=0.3)
        self.assertEqual(missing, [])
        self.assertEqual(scene.get("/ch/01/config").args[0], '"Kick"')
        self.assertEqual(scene.lines[0].path, "#4.0#")  # header carried over
        self.assertEqual(scene.get("/ch/01/dyn").args[4], "-21.5")


class DelayedConsoleTest(unittest.TestCase):
    """Replies arriving after the per-path timeout must never desync the capture:
    a captured path may not be reported missing, and no path may appear twice."""

    def test_stale_replies_do_not_desync(self):
        console = FakeConsole(delay=0.6)
        console.start()
        try:
            paths = ["ch/01/config", "ch/01/eq/1"]
            lines, missing = pull_lines("127.0.0.1", paths,
                                        port=console.port, timeout=0.4, retries=0)
            present = {ln.split(" ", 1)[0] for ln in lines}
            self.assertEqual(len(present), len(lines))          # no duplicates
            for p in missing:
                self.assertNotIn("/" + p, present)              # missing means absent
            for p in paths:
                self.assertTrue("/" + p in present or p in missing,
                                f"{p} neither captured nor reported missing")
            # non-vacuity: the first path's late reply lands in the second window
            # and must be credited to it, not dropped
            self.assertIn("/" + paths[0], present)
        finally:
            console.stop()


class SenderTest(unittest.TestCase):
    """A reply becomes scene state, so the desk's address gates what is believed."""

    def test_a_reply_from_another_address_is_not_captured(self):
        console = FakeConsole()
        console.start()
        try:
            # the console really does answer on loopback; claim the desk lives elsewhere
            with mock.patch.object(O, "desk_address", return_value="10.0.0.99"):
                lines, missing = pull_lines("127.0.0.1", ["ch/01/config"],
                                            port=console.port, timeout=0.3, retries=0)
            self.assertEqual(lines, [])
            self.assertEqual(missing, ["ch/01/config"])
            # positive control: the same query, believed, does capture the line
            lines, missing = pull_lines("127.0.0.1", ["ch/01/config"],
                                        port=console.port, timeout=0.3, retries=0)
            self.assertEqual(lines, [CANNED["ch/01/config"]])
            self.assertEqual(missing, [])
        finally:
            console.stop()

    def test_a_hostname_resolves_before_it_is_compared(self):
        self.assertEqual(O.desk_address("localhost"), "127.0.0.1")
        self.assertEqual(O.desk_address("10.0.0.2"), "10.0.0.2")


if __name__ == "__main__":
    unittest.main()
