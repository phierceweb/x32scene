"""Tests for FX param read/edit, DCA/mute groups, and the stage-box transform."""

import os
import unittest

from x32scene import Scene
from x32scene import fx as FX
from x32scene import groups as G
from x32scene import transforms as T
from x32scene.services.diff import diff
from x32scene.services.routing import channel_headamp_index

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


class FxTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_read_fx_decodes_plate(self):
        slots = {f.slot: f for f in FX.read_fx(self.sc)}
        self.assertEqual(slots[1].name, "Plate Reverb")
        self.assertEqual(slots[1].source, "MIX13")
        self.assertEqual(slots[1].params["PreDelay"], "32")
        self.assertEqual(slots[1].params["Decay"], "2.11")

    def test_set_fx_param(self):
        FX.set_fx_param(self.sc, 1, "Decay", "3.50")
        self.assertEqual(self.sc.get("/fx/1/par").args[1], "3.50")

    def test_set_fx_param_bad_name(self):
        with self.assertRaises(ValueError):
            FX.set_fx_param(self.sc, 1, "Wobble", "1")

    def test_set_fx_param_on_a_short_par_line_raises_a_domain_error(self):
        par = self.sc.get("/fx/1/par")
        par.args = par.args[:3]
        par.rebuild()
        with self.assertRaises(ValueError) as ctx:
            FX.set_fx_param(self.sc, 1, "Level", "50")
        self.assertIn("Level", str(ctx.exception))
        self.assertIn("/fx/1/par", str(ctx.exception))

    def test_read_fx_decodes_exciter(self):
        slots = {f.slot: f for f in FX.read_fx(self.sc)}
        self.assertEqual(slots[5].code, "EXC")
        self.assertEqual(slots[5].params["Tune"], "3k31")
        self.assertEqual(slots[5].params["Peak"], "28")
        self.assertEqual(slots[5].params["Solo"], "OFF")

    def test_set_fx_param_exciter(self):
        FX.set_fx_param(self.sc, 5, "Mix", "45")
        self.assertEqual(self.sc.get("/fx/5/par").args[5], "45")

    def test_read_fx_decodes_limiter(self):
        slots = {f.slot: f for f in FX.read_fx(self.sc)}
        self.assertEqual(slots[6].code, "LIM")
        self.assertEqual(slots[6].params["Input Gain"], "0.0")
        self.assertEqual(slots[6].params["Attack"], "0.05")
        self.assertEqual(slots[6].params["Stereo Link"], "ON")
        self.assertEqual(slots[6].params["Auto Gain"], "OFF")

    def test_set_fx_param_limiter(self):
        FX.set_fx_param(self.sc, 6, "Release", "800")
        self.assertEqual(self.sc.get("/fx/6/par").args[5], "800")

    def test_read_fx_decodes_geq2_dual_bands(self):
        slots = {f.slot: f for f in FX.read_fx(self.sc)}
        self.assertEqual(slots[7].code, "GEQ2")
        self.assertEqual(len(slots[7].params), 64)
        self.assertEqual(slots[7].params["20 A"], "0.0")
        self.assertEqual(slots[7].params["20000 A"], "0.0")
        self.assertEqual(slots[7].params["Master A"], "0.0")
        self.assertEqual(slots[7].params["20 B"], "0.0")
        self.assertEqual(slots[7].params["20000 B"], "0.0")
        self.assertEqual(slots[7].params["Master B"], "0.0")

    def test_read_fx_decodes_geq_shared_bands(self):
        slots = {f.slot: f for f in FX.read_fx(self.sc)}
        self.assertEqual(slots[8].code, "GEQ")
        self.assertEqual(len(slots[8].params), 32)
        self.assertEqual(slots[8].params["20"], "0.0")
        self.assertEqual(slots[8].params["20000"], "0.0")
        self.assertEqual(slots[8].params["Master"], "0.0")

    def _mini(self, code, par):
        # factory-default parameter values as the console writes them, padded to 64
        vals = par.split()
        vals += ["0"] * (64 - len(vals))
        return Scene.parse(f"/fx/1 {code}\n/fx/1/source MIX13 MIX13\n/fx/1/par {' '.join(vals)}\n")

    def test_read_fx_decodes_hall_delay_chorus_suboctaver(self):
        cases = {
            "HALL": ("20 1.57 60 5k74 25 0.0 83 7k2 0.95 25 50 30",
                     {"Pre Delay": "20", "Bass Multi": "0.95", "Mod Speed": "30"}),
            "DLY": ("100 223 ST 1 1 13 10 20k0 97 30 30 20k0",
                    {"Mode": "ST", "Offset L/R": "13", "Feed Hi Cut": "20k0"}),
            "CRS": ("0.50 15 15 19.9 19.9 100 97 15k1 120 100 85",
                    {"Speed": "0.50", "Phase": "120", "Spread": "85"}),
            "SUB": ("ON LO 100 30 50 ON HI 100 30 0",
                    {"Range A": "LO", "Octave -2 A": "50", "Range B": "HI", "Octave -2 B": "0"}),
        }
        for code, (par, expect) in cases.items():
            with self.subTest(code=code):
                slot = FX.read_fx(self._mini(code, par))[0]
                self.assertTrue(slot.verified)
                for k, v in expect.items():
                    self.assertEqual(slot.params[k], v)

    def test_vintage_room_decodes_its_thirteenth_parameter(self):
        slots = {f.slot: f for f in FX.read_fx(self.sc)}
        self.assertEqual(slots[2].params["Freeze"], "OFF")   # the fixture's VRM in slot 2

    def test_set_fx_param_on_a_corroborated_type(self):
        sc = self._mini("DLY", "100 223 ST 1 1 13 10 20k0 97 30 30 20k0")
        FX.set_fx_param(sc, 1, "Mode", "X")
        self.assertEqual(sc.get("/fx/1/par").args[2], "X")

    def test_console_default_lines_match_the_maps(self):
        # the desk's own default parameter line per type, read back over OSC
        cases = {
            "4TAP": ("200 100 30.0 10 20k0 5 4/3 50 1 50 3/2 50 OFF OFF OFF", {"Dry": "OFF"}),
            "DIMC": ("ON ST OFF ON OFF ON OFF", {"Mode": "ST", "Mode 4": "OFF"}),
            "MODD": ("300 1 30.0 97 9k5 20 1.08 SER CLUB 5.0 5k6 +0 100",
                     {"Setup": "SER", "Type": "CLUB", "Mix": "100"}),
            "CMB": ("ON OFF 100 5 494 ON 5 ON 0 48 3 0.0 0.0 0.0 0.0 0 0.0 0.0 0 0.0 0.0 0 "
                    "0.0 0.0 0 0.0 0.0 0 GR", {"Band Solo": "OFF", "Meter Mode": "GR"}),
            "P1A": ("ON 0.0 0.0 20 0.0 0.6 0.0 12k 0.0 20k ON", {"Lo Freq": "20", "Transformer": "ON"}),
            "PIT": ("0 0 5.0 52 15k8 100", {"Hi Cut": "15k8", "Mix": "100"}),
        }
        for code, (par, expect) in cases.items():
            with self.subTest(code=code):
                slot = FX.read_fx(self._mini(code, par))[0]
                self.assertTrue(slot.verified)
                for k, v in expect.items():
                    self.assertEqual(slot.params[k], v)

    def test_unknown_type_has_no_params(self):
        slot = FX.read_fx(self._mini("NOPE", "1 2 3"))[0]
        self.assertEqual(slot.params, {})
        self.assertFalse(slot.verified)

    def test_fx_codes_cover_the_published_list(self):
        from x32scene.tables_fx import FX_CODES
        self.assertEqual(len(FX_CODES), 61)
        self.assertEqual(FX_CODES["TEQ"], "Stereo TrueEQ")
        self.assertEqual(FX_CODES["PLAT"], "Plate Reverb")   # the existing names stay

    def test_every_published_type_is_mapped_with_unique_names(self):
        from x32scene.tables_fx import FX_CODES
        from x32scene.services.fx import FX_PARAMS
        geq = {"GEQ", "GEQ2", "TEQ", "TEQ2"}
        self.assertEqual(set(FX_CODES) - geq, set(FX_PARAMS))
        for code, names in FX_PARAMS.items():
            with self.subTest(code=code):
                self.assertEqual(len(names), len(set(names)))

    def test_set_fx_param_geq_still_refused(self):
        with self.assertRaises(ValueError):
            FX.set_fx_param(self.sc, 8, "20", "3.0")
        with self.assertRaises(ValueError):
            FX.set_fx_param(self.sc, 7, "20 A", "3.0")


class GroupsTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_dca_members(self):
        m = G.dca_members(self.sc)
        self.assertIn("/ch/01", m[1])    # Kick in DCA1 (Drums)
        self.assertIn("/ch/17", m[2])    # Bass DI in DCA2
        self.assertIn("/ch/23", m[4])    # Vox 1 in DCA4

    def test_set_dca_toggles_one_channel(self):
        base = Scene.load(EXAMPLE)
        G.set_dca(self.sc, 1, 5, on=True)
        changed = {c.path for c in diff(base, self.sc)}
        self.assertEqual(changed, {"/ch/01/grp"})
        self.assertIn("/ch/01", G.dca_members(self.sc)[5])

    def test_mute_members_includes_non_channel_strips(self):
        # the fixture puts /auxin/05-06 in mute group 5 and /fxrtn/01-02 in group 6:
        # a channels-only scan reports group 6 as unused, which is factually wrong
        m = G.mute_members(self.sc)
        self.assertEqual(m[5], ["/ch/31", "/ch/32", "/auxin/05", "/auxin/06"])
        self.assertEqual(m[6], [f"/fxrtn/{n:02d}" for n in range(1, 9)])

    def test_dca_members_returns_strip_paths(self):
        d = G.dca_members(self.sc)
        self.assertIn("/ch/01", d[1])
        self.assertIn("/ch/17", d[2])

    def test_set_mute_group_toggles_one_strip(self):
        base = Scene.load(EXAMPLE)
        G.set_mute_group(self.sc, 1, 2, on=True)
        changed = {c.path for c in diff(base, self.sc)}
        self.assertEqual(changed, {"/ch/01/grp"})
        self.assertIn("/ch/01", G.mute_members(self.sc)[2])
        G.set_mute_group(self.sc, 1, 2, on=False)
        self.assertNotIn("/ch/01", G.mute_members(self.sc)[2])

    def test_set_dca_accepts_non_channel_strip(self):
        base = Scene.load(EXAMPLE)
        G.set_dca(self.sc, "/fxrtn/01", 5, on=True)
        changed = {c.path for c in diff(base, self.sc)}
        self.assertEqual(changed, {"/fxrtn/01/grp"})
        self.assertIn("/fxrtn/01", G.dca_members(self.sc)[5])


class StageboxTest(unittest.TestCase):
    def setUp(self):
        self.base = Scene.load(EXAMPLE)
        self.sc = Scene.load(EXAMPLE)

    def test_move_local_input_to_stagebox(self):
        # ch1 Kick is on Local 1 (headamp 0). Move to AES50-A input 20 (headamp 51).
        old_ha = self.sc.get("/headamp/000").args[:]
        T.move_input_to_stagebox(self.sc, 1, 20, port="A")
        # userrout/in slot 1 now points at AES50-A 20 = source 52
        self.assertEqual(self.sc.get("/config/userrout/in").args[0], "52")
        self.assertEqual(channel_headamp_index(self.sc, 1), 51)
        # gain/phantom carried to the new head-amp index
        self.assertEqual(self.sc.get("/headamp/051").args, old_ha)

    def test_batch_move_and_roundtrip(self):
        n = T.move_inputs_to_stagebox(self.sc, {1: 1, 2: 2, 3: 3}, port="A")
        self.assertEqual(n, 3)
        self.assertEqual(Scene.parse(self.sc.dump()).dump(), self.sc.dump())


if __name__ == "__main__":
    unittest.main(verbosity=2)
