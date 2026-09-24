"""desk when the firmware lacks the first paths of a group read after the status paths: a
desk that has answered is read on; one that goes silent still fails fast."""

import time
import unittest

from tests.test_osc_absent_paths import Console
from x32scene.services import desk as D
from x32scene.services.osc import OscError, decode_message, encode_message

PREFS = [f"-prefs/{p}" for p in D._PREFS]
FIRST_SLOTS = [f"-show/showfile/scene/{n:03d}" for n in range(3)]


class Fading(Console):
    """Answers ``/xinfo`` and ``answers`` ``/node`` queries, then nothing at all."""

    def __init__(self, answers: int):
        super().__init__()
        self.answers = answers

    def run(self):
        while not self._halt.is_set():
            try:
                data, client = self.sock.recvfrom(65536)
            except (TimeoutError, OSError):
                continue
            addr, args = decode_message(data)
            self.received.append(addr)
            if self.answers <= 0:
                continue
            if addr == "/xinfo":
                self.sock.sendto(encode_message("/xinfo", ["127.0.0.1", "X32-TEST", "X32", "4.06"]),
                                 client)
            elif addr == "/node":
                self.answers -= 1
                self.sock.sendto(encode_message("node", [f"/{args[0]} ON\n"]), client)


class AbsentPathsTest(unittest.TestCase):
    def test_a_desk_lacking_the_first_preference_paths_is_read_on(self):
        with Console(absent=PREFS[:3]) as desk:
            info = D.read_desk("127.0.0.1", port=desk.port, timeout=0.05, library=False)
        self.assertEqual(list(info.prefs), PREFS[3:])
        self.assertEqual(len(info.stat), len(D._STAT))

    def test_a_desk_lacking_the_first_library_slots_is_read_on(self):
        with Console(absent=FIRST_SLOTS) as desk:
            D.read_desk("127.0.0.1", port=desk.port, timeout=0.05)
            asked = desk.received.count("/node")
        self.assertEqual(asked, len(D._STAT) + len(PREFS) + 1 + 300 + 100 * len(D.LIB_KINDS)
                         + len(FIRST_SLOTS) + 1)   # + the probe that finds the desk there

    def test_a_desk_that_goes_silent_after_its_status_still_fails_fast(self):
        with Fading(answers=len(D._STAT)) as desk:
            started = time.monotonic()
            with self.assertRaises(OscError) as cm:
                D.read_desk("127.0.0.1", port=desk.port, timeout=0.05)
            self.assertLess(time.monotonic() - started, 1.0 + 0.05 * (3 * 2 + 1) + 0.3)
        self.assertIn("desk off or unreachable", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
