"""EQ/dyn/gate editor tests, anchored to GUI-validated values (Floor 1 = ch09)."""

import os
import unittest

from x32scene import Scene
from x32scene import channelfx as F
from x32scene.services.diff import diff

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")


class FmtTest(unittest.TestCase):
    def test_freq_k_notation(self):
        self.assertEqual(F.fmt_freq(85.3), "85.3")
        self.assertEqual(F.fmt_freq(4370), "4k37")
        self.assertEqual(F.fmt_freq(10020), "10k02")
        self.assertEqual(F.fmt_freq(611.0), "611.0")

    def test_freq_just_below_1k_uses_k_notation_when_it_rounds_up(self):
        # rounding to one decimal would emit the non-canonical '1000.0'
        self.assertEqual(F.fmt_freq(999.99), "1k00")

    def test_gain_keeps_quarter_db_steps(self):
        # the console stores EQ gain in 0.25 dB steps and writes two decimals below
        # 10 dB — '+4.75' appears verbatim in the fixture
        self.assertEqual(F.fmt_gain(4.75), "+4.75")
        self.assertEqual(F.fmt_gain(-7.25), "-7.25")
        self.assertEqual(F.fmt_gain(6.0), "+6.00")
        self.assertEqual(F.fmt_gain(0.0), "+0.00")
        self.assertEqual(F.fmt_gain(10.2), "+10.2")   # 5-char field: 1 decimal at >=10
        self.assertEqual(F.fmt_gain(-14.0), "-14.0")

    def test_q_ten_is_bare(self):
        # the Q column is 3 chars: every fixture Q carries one decimal except the top of
        # the range, written '10' (see /ch/02/eq/2 in both fixtures)
        self.assertEqual(F._fmt_q(10), "10")
        self.assertEqual(F._fmt_q(0.3), "0.3")
        self.assertEqual(F._fmt_q(2.0), "2.0")
        self.assertEqual(F._fmt_q(9.9), "9.9")

    def test_three_sig_fig_token_holds_four_chars(self):
        # hold/makeup share a 4-char, 3-significant-digit field: '7.96', '31.7', '126'
        for v, want in ((0.02, "0.02"), (1, "1.00"), (7.96, "7.96"), (9.99, "9.99"),
                        (10, "10.0"), (31.7, "31.7"), (99.9, "99.9"), (100, "100"),
                        (126, "126"),
                        # just under a boundary must round INTO it, not print 5 chars
                        (9.996, "10.0"), (99.99, "100")):
            with self.subTest(v=v):
                self.assertEqual(F._fmt_3sig(v), want)


class ChannelFxTest(unittest.TestCase):
    def setUp(self):
        self.base = Scene.load(EXAMPLE)
        self.sc = Scene.load(EXAMPLE)

    def _changed(self):
        return {c.path for c in diff(self.base, self.sc)}

    def test_set_eq_band_only_touches_that_band(self):
        F.set_eq_band(self.sc, 9, 1, gain=6.0, freq=100)
        self.assertEqual(self._changed(), {"/ch/09/eq/1"})
        self.assertEqual(self.sc.get("/ch/09/eq/1").args, ["PEQ", "100.0", "+6.00", "0.5"])

    def test_eq_k_notation_for_high_freq(self):
        F.set_eq_band(self.sc, 9, 3, freq=5000)
        self.assertEqual(self.sc.get("/ch/09/eq/3").args[1], "5k00")

    def test_eq_validation(self):
        with self.assertRaises(ValueError):
            F.set_eq_band(self.sc, 9, 1, gain=20)      # > +15
        with self.assertRaises(ValueError):
            F.set_eq_band(self.sc, 9, 1, type="BELL")  # bad enum

    def test_set_comp_fields(self):
        F.set_comp(self.sc, 9, thr=-20.0, ratio="3")  # bare "3" normalizes to canonical "3.0"
        self.assertEqual(self._changed(), {"/ch/09/dyn"})
        a = self.sc.get("/ch/09/dyn").args
        self.assertEqual(a[4], "-20.0")
        self.assertEqual(a[5], "3.0")

    def test_comp_ratio_canonical_token(self):
        # single-digit ratios MUST be written as "N.0" — the console rejects a bare "4"
        # and abandons the rest of the /dyn line. Both "4" and "4.0" normalize to "4.0".
        for given in ("4", "4.0"):
            F.set_comp(self.sc, 9, ratio=given)
            self.assertEqual(self.sc.get("/ch/09/dyn").args[5], "4.0")
        F.set_comp(self.sc, 9, ratio="10")  # >=10 stays integer
        self.assertEqual(self.sc.get("/ch/09/dyn").args[5], "10")

    def test_comp_ratio_enum_validation(self):
        with self.assertRaises(ValueError):
            F.set_comp(self.sc, 9, ratio="6")  # not an X32 ratio step

    def test_set_gate_fields(self):
        F.set_gate(self.sc, 1, thr=-50.0, mode="GATE")  # Kick has a gate
        self.assertEqual(self._changed(), {"/ch/01/gate"})

    def test_set_lowcut(self):
        F.set_lowcut(self.sc, 9, on=True, freq=80)
        self.assertEqual(self._changed(), {"/ch/09/preamp"})
        a = self.sc.get("/ch/09/preamp").args
        self.assertEqual(a[2], "ON")
        self.assertEqual(a[4], "80")

    def test_writing_back_a_fixture_token_is_a_no_op(self):
        # the console's own value must survive a round trip through each formatter
        F.set_lowcut(self.sc, 11, freq=121)     # /ch/11+12/preamp carry '121'
        F.set_eq_band(self.sc, 2, 2, q=10)      # /ch/02/eq/2 carries '10'
        F.set_gate(self.sc, 11, hold=126)       # /ch/11+12/gate carry '126'
        F.set_comp(self.sc, 9, makeup=0.0, hold=1.59)
        self.assertEqual(self._changed(), set())

    def test_comp_makeup_drops_a_decimal_at_ten(self):
        for v, want in ((9.99, "9.99"), (10.0, "10.0"), (24.0, "24.0")):
            with self.subTest(makeup=v):
                F.set_comp(self.sc, 9, makeup=v)
                self.assertEqual(self.sc.get("/ch/09/dyn").args[7], want)

    def test_set_eq_gain_roundtrips_a_fixture_value(self):
        before = self.sc.get("/ch/09/eq/2").args[2]
        F.set_eq_band(self.sc, 9, 2, gain=float(before))
        self.assertEqual(self._changed(), set())

    def test_set_lowcut_on_strip_without_lowcut_fields_raises_cleanly(self):
        # auxin /preamp is 2 args (trim, invert) — no low-cut on the X32
        with self.assertRaises(ValueError) as ctx:
            F.set_lowcut(self.sc, "/auxin/01", on=True)
        self.assertIn("low cut", str(ctx.exception).lower())
        self.assertEqual(self._changed(), set())

    def test_set_gate_range_enforces_console_minimum(self):
        with self.assertRaises(ValueError):
            F.set_gate(self.sc, 1, rng=2.0)   # console minimum is 3 dB

    def test_set_lowcut_slope(self):
        F.set_lowcut(self.sc, 9, slope=18)
        self.assertEqual(self.sc.get("/ch/09/preamp").args[3], "18")
        with self.assertRaises(ValueError):
            F.set_lowcut(self.sc, 9, slope=15)  # only 12/18/24 exist

    def test_set_comp_on_off(self):
        F.set_comp(self.sc, 9, on=True)
        self.assertEqual(self.sc.get("/ch/09/dyn").args[0], "ON")
        F.set_comp(self.sc, 9, on=False)
        self.assertEqual(self.sc.get("/ch/09/dyn").args[0], "OFF")

    def test_set_comp_detector(self):
        F.set_comp(self.sc, 9, det="RMS")
        self.assertEqual(self.sc.get("/ch/09/dyn").args[2], "RMS")
        with self.assertRaises(ValueError):
            F.set_comp(self.sc, 9, det="AVG")

    def test_set_eq_on_bus_strip(self):
        # Bus 1 (Guitar L) has 6 EQ bands; edit band 6 via a strip path. Bus 1/2 are
        # link-paired in the fixture; linked=False isolates this test to path resolution.
        F.set_eq_band(self.sc, "/bus/01", 6, gain=-3.0, linked=False)
        self.assertEqual(self._changed(), {"/bus/01/eq/6"})
        self.assertEqual(self.sc.get("/bus/01/eq/6").args[2], "-3.00")

    def test_set_comp_on_bus_strip(self):
        F.set_comp(self.sc, "/bus/01", thr=-6.0, ratio="10", linked=False)
        self.assertEqual(self._changed(), {"/bus/01/dyn"})

    def test_set_comp_mix_on_mtx_and_main_strips(self):
        # /mtx and /main dyn lines have no keysrc field (14 args, mix at 12) —
        # the channel/bus index (13) would overwrite the auto field instead.
        for strip in ("/mtx/01", "/main/st"):
            with self.subTest(strip=strip):
                sc = Scene.load(EXAMPLE)
                before = Scene.load(EXAMPLE).get(f"{strip}/dyn").args
                F.set_comp(sc, strip, mix=50)
                a = sc.get(f"{strip}/dyn").args
                self.assertEqual(a[12], "50")
                self.assertEqual(a[13], before[13])

    def test_set_comp_mix_on_channel_strip(self):
        F.set_comp(self.sc, 9, mix=50)
        a = self.sc.get("/ch/09/dyn").args
        self.assertEqual(a[13], "50")
        self.assertEqual(a[12], self.base.get("/ch/09/dyn").args[12])

    def test_all_comp_fields_write_expected_tokens(self):
        F.set_comp(self.sc, 9, on=True, det="PEAK", thr=-20.0, ratio="4", knee=2,
                   makeup=3.5, attack=10, hold=50, release=250, mix=80)
        a = self.sc.get("/ch/09/dyn").args
        # the console writes hold with a decimal and attack/release as bare ints
        self.assertEqual(
            [a[0], a[2], a[4], a[5], a[6], a[7], a[8], a[9], a[10], a[13]],
            ["ON", "PEAK", "-20.0", "4.0", "2", "3.50", "10", "50.0", "250", "80"])

    def test_all_gate_fields_write_expected_tokens(self):
        F.set_gate(self.sc, 1, mode="DUCK", thr=-45.0, rng=40, attack=5, hold=20,
                   release=120)
        self.assertEqual(self.sc.get("/ch/01/gate").args[1:7],
                         ["DUCK", "-45.0", "40.0", "5", "20.0", "120"])

    def test_eq_type_and_q_write_expected_tokens(self):
        F.set_eq_band(self.sc, 9, 2, type="HShv", q=2.5)
        a = self.sc.get("/ch/09/eq/2").args
        self.assertEqual(a[0], "HShv")
        self.assertEqual(a[3], "2.5")

    def test_edits_roundtrip(self):
        F.set_eq_band(self.sc, 9, 1, gain=3.0)
        F.set_comp(self.sc, 9, thr=-18.0)
        self.assertEqual(Scene.parse(self.sc.dump()).dump(), self.sc.dump())

    def test_eq_edit_mirrors_to_linked_partner(self):
        F.set_eq_band(self.sc, 11, 1, gain=3.0)
        self.assertEqual(self._changed(), {"/ch/11/eq/1", "/ch/12/eq/1"})
        self.assertEqual(self.sc.get("/ch/12/eq/1").args[2], "+3.00")

    def test_eq_edit_unlinked_channel_touches_one_line(self):
        F.set_eq_band(self.sc, 9, 1, gain=3.0)
        self.assertEqual(self._changed(), {"/ch/09/eq/1"})

    def test_linked_false_overrides_mirroring(self):
        F.set_eq_band(self.sc, 11, 1, gain=3.0, linked=False)
        self.assertEqual(self._changed(), {"/ch/11/eq/1"})

    def test_mirroring_follows_every_link_family(self):
        # both fixtures: auxlink OFF OFF ON ON, fxlink all ON, mtxlink all OFF
        for strip, want in (("/auxin/05", {"/auxin/05/eq/1", "/auxin/06/eq/1"}),
                            ("/auxin/01", {"/auxin/01/eq/1"}),
                            ("/fxrtn/01", {"/fxrtn/01/eq/1", "/fxrtn/02/eq/1"}),
                            ("/mtx/01", {"/mtx/01/eq/1"})):
            for path in (EXAMPLE, EXAMPLE_ALT):
                with self.subTest(strip=strip, fixture=os.path.basename(path)):
                    base, sc = Scene.load(path), Scene.load(path)
                    F.set_eq_band(sc, strip, 1, gain=3.0)
                    self.assertEqual({c.path for c in diff(base, sc)}, want)

    def test_setters_return_the_strips_they_edited(self):
        self.assertEqual(F.set_eq_band(self.sc, 11, 1, gain=3.0),
                         ["/ch/11", "/ch/12"])
        self.assertEqual(F.set_comp(self.sc, 9, thr=-20.0), ["/ch/09"])
        self.assertEqual(F.set_gate(self.sc, 11, thr=-50.0), ["/ch/11", "/ch/12"])
        self.assertEqual(F.set_lowcut(self.sc, 9, freq=80), ["/ch/09"])

    def test_comp_mirrors_on_linked_bus_pair(self):
        F.set_comp(self.sc, "/bus/03", thr=-12.0)
        self.assertEqual(self._changed(), {"/bus/03/dyn", "/bus/04/dyn"})

    def test_lowcut_and_eq_mirror_under_independent_linkcfg_flags(self):
        # fixture linkcfg is all-ON, which can't discriminate hadly from eq; toggle
        # explicitly. Token order: 0 hadly, 1 eq, 2 dyn, 3 fdrmute. The toggle itself
        # is the intended baseline change, so diff against a toggled-but-unedited copy.
        def _toggled(hadly: str, eq: str) -> Scene:
            sc = Scene.load(EXAMPLE)
            ln = sc.get("/config/linkcfg")
            ln.set_arg(0, hadly)
            ln.set_arg(1, eq)
            return sc

        base = _toggled("OFF", "ON")
        sc = _toggled("OFF", "ON")
        F.set_lowcut(sc, 11, freq=80)
        self.assertEqual({c.path for c in diff(base, sc)}, {"/ch/11/preamp"})
        F.set_eq_band(sc, 11, 1, gain=3.0)
        self.assertEqual({c.path for c in diff(base, sc)},
                         {"/ch/11/preamp", "/ch/11/eq/1", "/ch/12/eq/1"})

        base = _toggled("ON", "OFF")
        sc = _toggled("ON", "OFF")
        F.set_lowcut(sc, 11, freq=80)
        self.assertEqual({c.path for c in diff(base, sc)},
                         {"/ch/11/preamp", "/ch/12/preamp"})
        F.set_eq_band(sc, 11, 1, gain=3.0)
        self.assertEqual({c.path for c in diff(base, sc)},
                         {"/ch/11/preamp", "/ch/12/preamp", "/ch/11/eq/1"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
