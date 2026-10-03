"""Routing edits: bank blocks, a channel's source, an output's source/tap, routing
presets out and in, and the vocabulary they are checked against."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import routing as R
from x32scene.services import routing_edit as RT
from x32scene.services.headers import decode_header
from x32scene.tables import routing_block_names, routing_vocab

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
ROU = os.path.join(FIX, "example.rou")


class VocabTest(unittest.TestCase):
    def test_sizes_match_the_published_enumerations(self):
        self.assertEqual(len(routing_vocab("IN", "1-8")), 24)
        self.assertEqual(len(routing_vocab("IN", "AUX")), 16)
        self.assertEqual(len(routing_vocab("PLAY", "AUX")), 16)
        for key in ("AES50A", "AES50B", "CARD"):
            self.assertEqual(len(routing_vocab(key, "1-8")), 36)
        self.assertEqual(len(routing_vocab("OUT", "1-4")), 36)

    def test_tokens_are_spelled_as_the_console_writes_them(self):
        self.assertIn("AUX/CR", routing_vocab("CARD", "9-16"))
        self.assertIn("AUX/TB", routing_vocab("OUT", "13-16"))
        self.assertIn("UOUT41-48", routing_vocab("AES50B", "41-48"))
        self.assertIn("P169-16", routing_vocab("AES50A", "1-8"))
        self.assertIn("AN13-16", routing_vocab("OUT", "5-8"))
        self.assertIn("OUT9-12", routing_vocab("OUT", "9-12"))
        self.assertNotIn("OUT9-12", routing_vocab("OUT", "5-8"))
        self.assertEqual(routing_block_names("IN"), ["1-8", "9-16", "17-24", "25-32", "AUX"])
        self.assertEqual(routing_block_names("OUT"), ["1-4", "5-8", "9-12", "13-16"])

    def test_every_fixture_token_is_in_vocabulary(self):
        sc = Scene.load(EXAMPLE)
        for key in ("IN", "AES50A", "AES50B", "CARD", "OUT", "PLAY"):
            for label, tok in RT.routing_line_words(sc, key):
                with self.subTest(key=key, block=label):
                    self.assertIn(tok, routing_vocab(key, label))


class SetRoutingTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_blocks_by_label(self):
        RT.set_routing(self.sc, "IN", {"1-8": "A1-8", "AUX": "CARD1-6"})
        self.assertEqual(self.sc.get("/config/routing/IN").args[0], "A1-8")
        self.assertEqual(self.sc.get("/config/routing/IN").args[4], "CARD1-6")
        with self.assertRaises(ValueError):
            RT.set_routing(self.sc, "IN", {"1-8": "OUT1-8"})     # an output, not an input
        with self.assertRaises(ValueError):
            RT.set_routing(self.sc, "OUT", {"1-8": "AN1-8"})     # OUT blocks are 4 wide
        with self.assertRaises(ValueError):
            RT.set_routing(self.sc, "NOPE", {"1-8": "AN1-8"})

    def test_switch(self):
        RT.set_routswitch(self.sc, "PLAY")
        self.assertEqual(self.sc.get("/config/routing").args, ["PLAY"])
        with self.assertRaises(ValueError):
            RT.set_routswitch(self.sc, "ON")

    def test_round_trip(self):
        RT.set_routing(self.sc, "AES50A", {"41-48": "AUX/TB"})
        text = self.sc.dump()
        self.assertEqual(Scene.parse(text).dump(), text)


class InputSourceTest(unittest.TestCase):
    def test_encode(self):
        cases = {"off": 0, "local 5": 5, "AES50-A 3": 35, "aes50b 48": 128, "card 7": 135,
                 "aux 2": 162, "AN 1": 1, "12": 12}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(RT.encode_input_source(text), want)
        for bad in ("local 33", "card 0", "aux 7", "moon 1", "169", "local"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    RT.encode_input_source(bad)

    def test_set_input_writes_the_slot_that_reads_the_source(self):
        sc = Scene.load(EXAMPLE)   # IN 17-24 is A1-8, so slot 19 reads AES50-A 3
        self.assertEqual(RT.set_input(sc, 5, "aes50-a 3"), "slot 19 (AES50-A input 3)")
        self.assertEqual(sc.get("/ch/05/config").args[-1], "19")
        self.assertEqual(sc.get("/ch/05/config").args[:3],
                         Scene.load(EXAMPLE).get("/ch/05/config").args[:3])   # name, icon, colour kept
        self.assertEqual(RT.set_input(sc, 5, "card 1"), "slot 31 (USB Card (DAW) 1)")   # via UIN
        self.assertEqual(RT.set_input(sc, 5, "off"), "slot 0 (OFF)")

    def test_set_input_takes_a_bare_number_as_the_slot(self):
        sc = Scene.load(EXAMPLE)
        self.assertEqual(RT.set_input(sc, 5, 64), "slot 64 (Bus 16)")
        self.assertEqual(RT.set_input(sc, 5, "3"), "slot 3 (Local input 3)")
        self.assertEqual(sc.get("/ch/05/config").args[-1], "3")
        for bad in (65, "135", True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                RT.set_input(sc, 5, bad)

    def test_every_label_inputs_prints_drops_back_in(self):
        tmpl = Scene.load(EXAMPLE)
        labels = {R.resolve_in_slot(tmpl, s) for s in range(65)} - {"?"}
        self.assertTrue({"AES50-A input 3", "USB Card (DAW) 1", "USB player L", "FX 1L",
                         "Bus 4", "OFF"} <= labels)
        for label in sorted(labels):
            with self.subTest(label=label):
                sc = Scene.load(EXAMPLE)
                RT.set_input(sc, 5, label)
                slot = int(sc.get("/ch/05/config").args[-1])
                self.assertEqual(R.resolve_in_slot(sc, slot), label)
        self.assertEqual(RT.parse_channel_source("  bus   4 "), ("slot", 52))
        self.assertEqual(RT.parse_channel_source("usb player r"), ("slot", 40))
        self.assertEqual(RT.encode_input_source("Talkback Int"), 167)

    def test_set_input_refuses_a_source_no_slot_reads(self):
        sc = Scene.load(EXAMPLE)
        with self.assertRaisesRegex(ValueError, "no input slot reads USB Card \\(DAW\\) 7"):
            RT.set_input(sc, 5, "card 7")
        self.assertEqual(sc.dump(), Scene.load(EXAMPLE).dump())

    def test_set_input_skips_aux_slots_past_a_partial_token(self):
        sc = Scene.load(EXAMPLE)   # no slot 1-32 reads Local 3; AN1-2 remaps aux slots 33-34
        RT.set_routing(sc, "IN", {"1-8": "A1-8", "9-16": "A9-16", "25-32": "A25-32",
                                  "AUX": "AN1-2"})
        with self.assertRaisesRegex(ValueError, "no input slot reads Local input 3"):
            RT.set_input(sc, 5, "local 3")
        self.assertEqual(RT.set_input(sc, 5, "local 2"), "slot 34 (Local input 2)")
        self.assertEqual(RT.set_input(sc, 5, "aux 3"), "slot 35 (Aux In 3)")

    def test_set_input_keeps_the_channels_own_slot_when_it_reads_the_source(self):
        sc = Scene.load(EXAMPLE)   # slot 1 now reads AES50-A 4 too; ch 20 reads it on slot 20
        sc.get("/config/userrout/in").set_arg(0, "36")
        self.assertEqual(RT.set_input(sc, 20, "aes50-a 4"), "slot 20 (AES50-A input 4)")
        self.assertFalse(sc.get("/ch/20/config").dirty)
        self.assertEqual(RT.set_input(sc, 5, "aes50-a 4"), "slot 1 (AES50-A input 4)")
        self.assertEqual(RT.channel_slot(sc, "aes50-a 4", current=39), 1)   # USB player L


class OutputTest(unittest.TestCase):
    def test_encode_tap(self):
        self.assertEqual(RT.encode_tap("off"), 0)
        self.assertEqual(RT.encode_tap("Bus 9"), 12)
        self.assertEqual(RT.encode_tap("main l"), 1)
        self.assertEqual(RT.encode_tap("Matrix 2"), 21)
        self.assertEqual(RT.encode_tap("direct out ch 5"), 30)
        self.assertEqual(RT.encode_tap("talkback"), 76)
        self.assertEqual(RT.encode_tap("40"), 40)
        for bad in ("bus 17", "77", "kitchen"):
            with self.assertRaises(ValueError):
                RT.encode_tap(bad)

    def test_set_output(self):
        sc = Scene.load(EXAMPLE)
        words = RT.set_output(sc, "main", 9, src="bus 12", pos="PRE+M", invert=True)
        self.assertEqual(sc.get("/outputs/main/09").args, ["15", "PRE+M", "ON"])
        self.assertEqual(words, "Bus 12 PRE+M invert on")
        RT.set_output(sc, "rec", 1, src="main r")
        self.assertEqual(sc.get("/outputs/rec/01").args[0], "2")
        with self.assertRaises(ValueError):
            RT.set_output(sc, "rec", 1, invert=True)          # rec lines have no polarity
        with self.assertRaises(ValueError):
            RT.set_output(sc, "main", 9, pos="POST+M")         # not a console token
        with self.assertRaises(ValueError):
            RT.set_output(sc, "aux", 7, src="off")


class RoutingPresetTest(unittest.TestCase):
    def test_extract_matches_the_fixture(self):
        with open(ROU, encoding="utf-8", newline="") as fh:
            want = fh.read()
        text = RT.extract_routing(Scene.load(EXAMPLE), "Example Routing")
        self.assertEqual(text, want)
        self.assertEqual(decode_header(text)["kind"], "routing preset")

    def test_apply_all_or_some_banks(self):
        sc = Scene.load(EXAMPLE)
        RT.set_routing(sc, "IN", {"1-8": "A1-8"})
        RT.set_routing(sc, "CARD", {"1-8": "A1-8"})
        with open(ROU, encoding="utf-8", newline="") as fh:
            text = fh.read()
        self.assertEqual(RT.apply_routing(sc, text, ["IN"]), ["IN"])
        self.assertEqual(sc.get("/config/routing/IN").args[0], "UIN1-8")
        self.assertEqual(sc.get("/config/routing/CARD").args[0], "A1-8")
        self.assertEqual(RT.apply_routing(sc, text), ["IN", "AES50A", "AES50B", "CARD"])
        self.assertEqual(sc.get("/config/routing/CARD").args[0], "UOUT1-8")
        with self.assertRaises(ValueError):
            RT.apply_routing(sc, "/eq ON\n")
        with self.assertRaises(ValueError):
            RT.apply_routing(sc, "/config/routing/IN NOPE AN9-16 AN17-24 AN25-32 AUX1-4\n")


class RoutingCliTest(unittest.TestCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def test_commands_and_snippet_form(self):
        with tempfile.TemporaryDirectory() as d:
            a, rou, snp = (os.path.join(d, n) for n in ("a.scn", "r.rou", "s.snp"))
            code, out = self._run("set-routing", EXAMPLE, "IN", "1-8=A1-8", "AUX=AUX1-4", "-o", a)
            self.assertEqual(code, 0)
            self.assertIn("routing IN: 1-8=A1-8", out)
            code, out = self._run("set-routing", a, "switch", "PLAY", "-o", a + "2")
            self.assertEqual(code, 0)
            code, out = self._run("set-input", EXAMPLE, "5", "card 1", "-o", a + "3")
            self.assertIn("ch05 source -> slot 31 (USB Card (DAW) 1)", out)
            code, out = self._run("set-output", EXAMPLE, "main", "9", "-o", a + "4",
                                  "--src", "bus 12", "--pos", "PRE")
            self.assertIn("main 09: Bus 12 PRE invert off", out)
            code, _ = self._run("extract-routing", a, "-o", rou)
            self.assertEqual(code, 0)
            code, out = self._run("apply-routing", EXAMPLE, rou, "-o", a + "5", "--bank", "IN")
            self.assertIn("applied routing banks IN", out)
            self.assertEqual(Scene.load(a + "5").get("/config/routing/IN").args[0], "A1-8")
            code, out = self._run("snippet", EXAMPLE, "-o", snp, "--edit", "set-routing IN 1-8=A1-8",
                                  "--edit", "set-output main 9 --src 'bus 12'",
                                  "--edit", "set-input 5 'aes50-a 3'")
            self.assertEqual(code, 0)
            self.assertIn("filters: Config, Routing, Out Patch", out)
            body = [ln.split(" ")[0] for ln in open(snp, encoding="utf-8").read().split("\n")[1:] if ln]
            self.assertEqual(body, ["/ch/05/config", "/config/routing/IN/1-8", "/outputs/main/09"])

    def test_bad_input_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "a.scn")
            for argv in (["set-routing", EXAMPLE, "IN", "1-8=OUT1-8", "-o", out],
                         ["set-routing", EXAMPLE, "IN", "AN1-8", "-o", out],
                         ["set-input", EXAMPLE, "5", "moon 3", "-o", out],
                         ["set-input", EXAMPLE, "5", "card 7", "-o", out],
                         ["set-input", EXAMPLE, "5", "135", "-o", out],
                         ["set-output", EXAMPLE, "main", "9", "-o", out],
                         ["set-output", EXAMPLE, "main", "9", "-o", out, "--pos", "LATE"]):
                with self.subTest(argv=argv[2:]):
                    code, _ = self._run(*argv)
                    self.assertNotEqual(code, 0)
                    self.assertFalse(os.path.exists(out))

    def test_vocab(self):
        code, out = self._run("vocab", "routing", "OUT")
        self.assertEqual(code, 0)
        self.assertIn("AUX/TB", out)
        code, out = self._run("vocab", "taps")
        self.assertIn("12  Bus 9", out)
        code, out = self._run("vocab", "sources")
        self.assertIn("AES50-A input", out)


if __name__ == "__main__":
    unittest.main()
