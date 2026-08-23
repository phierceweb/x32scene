"""FX writing: values by name formatted like the desk, type changes that reset to the
desk's defaults, and effect presets (.efx) out and in."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import fx as FX
from x32scene.services.headers import decode_header
from x32scene.tables_fx import FX_DEFAULTS, FX_DISPLAY_TYPE, FX_SIDE_RACK_TYPES, FX_TYPES

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EFX = os.path.join(FIX, "example.efx")


class FormatLikeTest(unittest.TestCase):
    def test_numbers_follow_the_default_token(self):
        cases = [("2.11", 3, "3.00"), ("60", 45.6, "46"), ("0.0", -6.5, "-6.5"),
                 ("+10", 5, "+5"), ("+0", -20, "-20"), ("+0", 0, "+0"),
                 ("6k50", 8000, "8k00"), ("6k50", 850, "850.0"), ("7k2", 12000, "12k0"),
                 ("7k2", 800, "800"), ("20k0", 20000, "20k0"), ("0.95", "1.2", "1.20")]
        for default, value, want in cases:
            with self.subTest(default=default, value=value):
                self.assertEqual(FX.format_like(default, value), want)

    def test_enum_tokens_pass_through(self):
        self.assertEqual(FX.format_like("SER", "PAR"), "PAR")
        self.assertEqual(FX.format_like("3/8", "1/2"), "1/2")
        self.assertEqual(FX.format_like("ON", "OFF"), "OFF")


class DefaultsTest(unittest.TestCase):
    def test_every_type_has_defaults_in_its_own_length(self):
        for code in FX_TYPES:
            with self.subTest(code=code):
                self.assertEqual(len(FX.fx_defaults(code)), 64)
                self.assertEqual(len(FX_DEFAULTS[code].split(" ")), len(FX.param_names(code)))
                self.assertIn(code, FX_DISPLAY_TYPE)

    def test_side_rack_types_are_a_subset(self):
        self.assertTrue(FX_SIDE_RACK_TYPES < set(FX_TYPES))
        self.assertIn("GEQ", FX_SIDE_RACK_TYPES)
        self.assertNotIn("PLAT", FX_SIDE_RACK_TYPES)


class SetFxTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_set_params_by_name(self):
        FX.set_fx_params(self.sc, 1, {"Decay": 2.1, "Damp": 8000, "PreDelay": "40"})
        p = self.sc.get("/fx/1/par").args
        self.assertEqual((p[0], p[1], p[3]), ("40", "2.10", "8k00"))
        self.assertEqual(len(p), 64)
        with self.assertRaises(ValueError):
            FX.set_fx_params(self.sc, 1, {"Nope": 1})

    def test_type_change_resets_to_the_desk_defaults(self):
        FX.set_fx_type(self.sc, 4, "HALL")
        self.assertEqual(self.sc.get("/fx/4").args, ["HALL"])
        self.assertEqual(self.sc.get("/fx/4/par").args, FX.fx_defaults("HALL"))
        self.assertEqual(self.sc.get("/fx/4/par").args[:3], ["20", "1.57", "60"])
        with self.assertRaises(ValueError):
            FX.set_fx_type(self.sc, 5, "HALL")     # reverbs cannot live in the side rack
        with self.assertRaises(ValueError):
            FX.set_fx_type(self.sc, 1, "NOPE")
        FX.set_fx_type(self.sc, 5, "LIM")
        self.assertEqual(self.sc.get("/fx/5/par").args[:8], FX.fx_defaults("LIM")[:8])

    def test_source(self):
        FX.set_fx_source(self.sc, 1, "MIX15", "MIX16")
        self.assertEqual(self.sc.get("/fx/1/source").args, ["MIX15", "MIX16"])
        FX.set_fx_source(self.sc, 1, "INS")
        self.assertEqual(self.sc.get("/fx/1/source").args, ["INS", "INS"])
        with self.assertRaises(ValueError):
            FX.set_fx_source(self.sc, 1, "BUS9")
        with self.assertRaises(KeyError):
            FX.set_fx_source(self.sc, 5, "MIX1")

    def test_round_trip_survives_edits(self):
        FX.set_fx_params(self.sc, 1, {"Decay": 2.1})
        text = self.sc.dump()
        self.assertEqual(Scene.parse(text).dump(), text)


class EffectPresetTest(unittest.TestCase):
    def test_extract_matches_the_console_shape(self):
        sc = Scene.load(EXAMPLE)
        text = FX.extract_fx(sc, 1, "Example Plate")
        with open(EFX, encoding="utf-8", newline="") as fh:
            self.assertEqual(text, fh.read())
        self.assertEqual(decode_header(text)["display_type"], str(FX_DISPLAY_TYPE["PLAT"]))
        self.assertEqual(Scene.parse(text).dump(), text)

    def test_apply_sets_type_and_params_but_not_source(self):
        sc = Scene.load(EXAMPLE)
        with open(EFX, encoding="utf-8", newline="") as fh:
            text = fh.read()
        before_src = sc.get("/fx/2/source").args[:]
        self.assertEqual(FX.apply_fx(sc, 2, text), "PLAT")
        self.assertEqual(sc.get("/fx/2").args, ["PLAT"])
        self.assertEqual(sc.get("/fx/2/par").args, sc.get("/fx/1/par").args)
        self.assertEqual(sc.get("/fx/2/source").args, before_src)
        FX.apply_fx(sc, 2, text, source=True)
        self.assertEqual(sc.get("/fx/2/source").args, sc.get("/fx/1/source").args)
        with self.assertRaises(ValueError):
            FX.apply_fx(sc, 5, text)   # a plate cannot load into the side rack
        with self.assertRaises(ValueError):
            FX.apply_fx(sc, 1, "/eq ON\n")


class FxCliTest(unittest.TestCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def test_set_fx_extract_apply_and_snippet(self):
        with tempfile.TemporaryDirectory() as d:
            a, efx, b, snp = (os.path.join(d, n) for n in ("a.scn", "p.efx", "b.scn", "s.snp"))
            code, out = self._run("set-fx", EXAMPLE, "1", "-o", a, "--set", "Decay=2.1",
                                  "--set", "Damp=8000")
            self.assertEqual(code, 0)
            self.assertIn("FX1: Decay=2.1, Damp=8000", out)
            code, out = self._run("extract-fx", a, "1", "-o", efx, "--name", "Long Plate")
            self.assertEqual(code, 0)
            self.assertEqual(decode_header(open(efx, encoding="utf-8").read())["name"], "Long Plate")
            code, out = self._run("apply-fx", EXAMPLE, "2", efx, "-o", b)
            self.assertEqual(code, 0)
            self.assertEqual(Scene.load(b).get("/fx/2/par").args[1], "2.10")
            code, out = self._run("snippet", EXAMPLE, "-o", snp, "--edit", "set-fx 4 --type HALL",
                                  "--edit", f"apply-fx 2 {efx}")
            self.assertEqual(code, 0)
            self.assertIn("filters: FX 2, FX 4", out)
            body = [ln.split(" ")[0] for ln in open(snp, encoding="utf-8").read().split("\n")[1:] if ln]
            self.assertEqual(body, ["/fx/2", "/fx/2/par", "/fx/4", "/fx/4/par"])

    def test_set_fx_needs_a_knob_and_refuses_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "a.scn")
            for argv in (["set-fx", EXAMPLE, "1", "-o", out],
                         ["set-fx", EXAMPLE, "1", "-o", out, "--set", "Decay"],
                         ["set-fx", EXAMPLE, "5", "-o", out, "--type", "PLAT"],
                         ["set-fx", EXAMPLE, "1", "-o", out, "--source", "BUS1"]):
                with self.subTest(argv=argv[3:]):
                    code, _ = self._run(*argv)
                    self.assertNotEqual(code, 0)
                    self.assertFalse(os.path.exists(out))

    def test_fx_types(self):
        code, out = self._run("fx-types")
        self.assertEqual(code, 0)
        self.assertIn("PLAT   Plate Reverb", out)
        self.assertIn("slots 1-8", out)
        code, out = self._run("fx-types", "PLAT")
        self.assertIn("Decay                  default 2.11", out)
        code, _ = self._run("fx-types", "NOPE")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
