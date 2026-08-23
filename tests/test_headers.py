"""headers and show: every header kind decoded, and the .shw index."""

import contextlib
import io
import json
import os
import unittest

from x32scene.cli import main
from x32scene.services.headers import decode_header, scene_safes
from x32scene.services.show import read_show

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8", newline="") as fh:
        return fh.read()


class SceneSafesTest(unittest.TestCase):
    def test_bits_read_right_to_left_with_bit_zero_unused(self):
        self.assertEqual(scene_safes("%000000110"), ["Talkback", "Effects"])
        self.assertEqual(scene_safes("%100000000"), ["Routing I/O"])
        self.assertEqual(scene_safes("%000000000"), [])


class DecodeHeaderTest(unittest.TestCase):
    def test_scene(self):
        self.assertEqual(decode_header(_read("example.scn")),
                         {"version": "4.0", "kind": "scene", "name": "Example Rig", "note": "",
                          "safes": []})

    def test_snippet(self):
        d = decode_header(_read("example.snp"))
        self.assertEqual((d["kind"], d["name"], d["filters"], d["channels"]),
                         ("snippet", "Example EQ", ["EQ"], ["ch01"]))

    def test_channel_preset_carries_slot_and_sections(self):
        d = decode_header('#2.0# 20 "Tom" 0 %0011111100111000 1')
        self.assertEqual(d["kind"], "channel preset")
        self.assertEqual(d["slot"], 20)
        self.assertEqual(d["version"], "2.0")
        self.assertEqual(d["sections"]["active"], ["gate", "eq", "dyn"])

    def test_effect_and_routing_presets(self):
        self.assertEqual(decode_header(_read("example.efx")),
                         {"version": "4.0", "kind": "effect preset", "slot": 1,
                          "name": "Example Plate", "display_type": "4"})
        self.assertEqual(decode_header(_read("example.rou"))["kind"], "routing preset")

    def test_headerless_preset_is_none(self):
        self.assertIsNone(decode_header("/eq ON\n/eq/1 PEQ 100 +0.00 2.0\n"))


class ShowTest(unittest.TestCase):
    def test_index_decodes_each_slot_like_its_own_header(self):
        show = read_show(_read("example.shw"))
        self.assertEqual((show.name, show.writer), ("Example Show", "X32-Edit 4.00"))
        self.assertEqual([(e.kind, e.index, e.name) for e in show.entries],
                         [("cue", 0, "Opener"), ("cue", 1, "Encore"),
                          ("scene", 0, "Example Rig"), ("snippet", 0, "Example EQ")])
        self.assertEqual(show.of("scene")[0].decoded["safes"], ["Talkback", "Effects"])
        self.assertEqual(show.of("snippet")[0].decoded["filters"], ["EQ"])

    def test_cue_lines_are_kept_raw(self):
        show = read_show('#4.0#\nshow "s" 0 "w"\ncue/000 100 "Opener" 0 0 -1 0 0 0\n')
        cue = show.of("cue")[0]
        self.assertEqual((cue.index, cue.name, cue.args[0]), (0, "Opener", "100"))


class HeaderCliTest(unittest.TestCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(list(argv)), 0)
        return buf.getvalue()

    def test_header_and_show_commands(self):
        out = self._run("header", os.path.join(FIX, "example.snp"))
        self.assertIn("kind: snippet", out)
        self.assertIn("filters: EQ", out)
        doc = json.loads(self._run("header", os.path.join(FIX, "example.efx"), "--json"))
        self.assertEqual(doc["kind"], "effect preset")
        out = self._run("show", os.path.join(FIX, "example.shw"))
        self.assertIn("scene/000  Example Rig   [Talkback, Effects]", out)
        doc = json.loads(self._run("show", os.path.join(FIX, "example.shw"), "--json"))
        self.assertEqual(doc["entries"][3]["filters"], ["EQ"])
        self.assertEqual(doc["entries"][0]["number"], "1.0.0")

    def test_headerless_file_is_an_error(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(main(["header", os.path.join(FIX, "example-stage.json")]), 0)


if __name__ == "__main__":
    unittest.main()
