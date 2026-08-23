"""meters: blob decoding, peak collection over a window, and the read-only command."""

import contextlib
import io
import json
import math
import os
import struct
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.services import meters as M
from x32scene.services.osc import decode_message, encode_message

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")


def blob_message(meter: int, values: list[float]) -> bytes:
    payload = struct.pack("<i", len(values)) + struct.pack(f"<{len(values)}f", *values)
    body = struct.pack(">i", len(payload)) + payload
    pad = b"\x00" * ((4 - len(body) % 4) % 4)
    addr = f"/meters/{meter}".encode() + b"\x00"
    addr += b"\x00" * ((4 - len(addr) % 4) % 4)
    return addr + b",b\x00\x00" + body + pad


class BlobTest(unittest.TestCase):
    def test_decoder_reads_a_blob_argument(self):
        addr, args = decode_message(blob_message(6, [0.5, 1.0, 0.0, 0.25]))
        self.assertEqual(addr, "/meters/6")
        self.assertEqual(M.parse_blob(args[0]), [0.5, 1.0, 0.0, 0.25])

    def test_short_blob_is_an_error(self):
        with self.assertRaises(M.OscError):
            M.parse_blob(b"\x05\x00\x00\x00\x00")

    def test_db(self):
        self.assertEqual(M.fmt_db(1.0), "+0.0")
        self.assertEqual(M.fmt_db(0.0), "-oo")
        self.assertAlmostEqual(M.to_db(0.1), -20.0)
        self.assertTrue(math.isinf(M.to_db(0)))

    def test_slot_tables_match_the_published_counts(self):
        self.assertEqual(len(M.METER_SLOTS[0]), 70)
        self.assertEqual(len(M.METER_SLOTS[2]), 49)
        self.assertEqual(len(M.METER_SLOTS[4]), 82)
        self.assertEqual(len(M.METER_SLOTS[9]), 32)
        self.assertEqual(M.METER_SLOTS[4][40], "out 1")
        self.assertEqual(M.METER_SLOTS[2][22], "main L")


def _fake_socket(frames):
    fake = mock.MagicMock()
    fake.__enter__.return_value = fake
    fake.recvfrom.side_effect = [(f, ("10.0.0.2", 10023)) for f in frames] + [TimeoutError()]
    return fake


class ReadMetersTest(unittest.TestCase):
    def test_keeps_each_slots_peak(self):
        frames = [blob_message(0, [0.1] * 70), blob_message(0, [0.5] + [0.0] * 69),
                  blob_message(0, [0.2] * 70)]
        with mock.patch.object(M.socket, "socket", return_value=_fake_socket(frames)):
            peaks = M.read_meters("10.0.0.2", 0, seconds=5)
        self.assertEqual(peaks.frames, 3)
        self.assertEqual(peaks.peak["ch 1"], 0.5)
        self.assertAlmostEqual(peaks.peak["ch 2"], 0.2, places=6)
        self.assertAlmostEqual(peaks.peak["matrix 6"], 0.2, places=6)

    def test_other_meters_and_junk_are_ignored(self):
        frames = [blob_message(4, [1.0] * 82), b"garbage", encode_message("/node", ["x"]),
                  blob_message(0, [0.3] * 70)]
        with mock.patch.object(M.socket, "socket", return_value=_fake_socket(frames)):
            peaks = M.read_meters("10.0.0.2", 0, seconds=5)
        self.assertEqual(peaks.frames, 1)
        self.assertAlmostEqual(peaks.peak["ch 1"], 0.3, places=6)

    def test_no_frames_is_an_error(self):
        with mock.patch.object(M.socket, "socket", return_value=_fake_socket([])):
            with self.assertRaises(M.OscError):
                M.read_meters("10.0.0.2", 0, seconds=5)
        with self.assertRaises(ValueError):
            M.read_meters("10.0.0.2", 99)


class MetersCliTest(unittest.TestCase):
    def test_text_and_json(self):
        frames = [blob_message(0, [0.5] + [0.0] * 69)]
        with mock.patch.object(M.socket, "socket", return_value=_fake_socket(frames)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["meters", "--ip", "10.0.0.2", "--scene", EXAMPLE]), 0)
            out = buf.getvalue()
            self.assertIn("ch 1         Kick           -6.0", out)
            self.assertNotIn("ch 2 ", out)
        with mock.patch.object(M.socket, "socket", return_value=_fake_socket(frames)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["meters", "--ip", "10.0.0.2", "--json"]), 0)
            doc = json.loads(buf.getvalue())
            self.assertEqual(doc["slots"][0], {"slot": "ch 1", "name": "", "peak": 0.5, "db": -6.0})
            self.assertIsNone(doc["slots"][1]["db"])

    def test_needs_an_ip(self):
        with mock.patch.dict("os.environ", {"X32SCENE_IP": ""}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(main(["meters"]), 0)


if __name__ == "__main__":
    unittest.main()
