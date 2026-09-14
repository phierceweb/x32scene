"""apply-preset takes its default scope from a preset header's section flags."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.orchestrators.band_swap import allowed_paths, run
from x32scene.services.preset_library import DRIFT, check_preset
from x32scene.services.presets import (apply_preset, extract_preset, header_scopes,
                                       preset_header, unflagged_scopes)

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def gate_only_header_over_gate_and_eq() -> str:
    body = extract_preset(Scene.load(EXAMPLE), 1, ["gate", "eq"])
    return preset_header("Kick", {"gate"}, set()) + "\n" + body


class HeaderScopeTest(unittest.TestCase):
    def test_headerless_preset_has_no_header_scopes(self):
        self.assertIsNone(header_scopes(extract_preset(Scene.load(EXAMPLE), 1)))
        self.assertEqual(unflagged_scopes(extract_preset(Scene.load(EXAMPLE), 1)), [])

    def test_flags_select_their_scopes_and_scopes_without_a_flag(self):
        self.assertEqual(header_scopes(gate_only_header_over_gate_and_eq()),
                         ["gate", "sends", "mainfader", "insert", "automix"])

    def test_every_section_flag_maps_to_a_scope(self):
        chn = '#2.1# 71 "Zeroed" 0 %0011111100000000 1\n/preamp +0.0 OFF OFF 24 20\n'
        self.assertEqual(header_scopes(chn), ["ha", "scribble", "gate", "comp", "eq", "sends",
                                              "mainfader", "insert", "automix"])

    def test_unflagged_scopes_name_body_sections_the_header_leaves_out(self):
        self.assertEqual(unflagged_scopes(gate_only_header_over_gate_and_eq()), ["eq"])
        self.assertEqual(unflagged_scopes(gate_only_header_over_gate_and_eq(), ["eq"]), [])


class ApplyFromHeaderTest(unittest.TestCase):
    def setUp(self):
        self.dst = Scene.load(EXAMPLE)
        self.eq_before = self.dst.get("/ch/20/eq/2").args

    def test_header_flags_limit_the_default_scope(self):
        self.assertGreater(apply_preset(self.dst, 20, gate_only_header_over_gate_and_eq()), 0)
        kick = Scene.load(EXAMPLE)
        self.assertEqual(self.dst.get("/ch/20/gate").args, kick.get("/ch/01/gate").args)
        self.assertEqual(self.dst.get("/ch/20/eq/2").args, self.eq_before)

    def test_explicit_scope_wins_over_the_header(self):
        apply_preset(self.dst, 20, gate_only_header_over_gate_and_eq(), ["eq"])
        kick = Scene.load(EXAMPLE)
        self.assertEqual(self.dst.get("/ch/20/eq/2").args, kick.get("/ch/01/eq/2").args)
        self.assertEqual(self.dst.get("/ch/20/gate").args[0], "ON")

    def test_headerless_preset_applies_every_scope_it_carries(self):
        body = extract_preset(Scene.load(EXAMPLE), 1, ["gate", "eq"])
        apply_preset(self.dst, 20, body)
        kick = Scene.load(EXAMPLE)
        self.assertEqual(self.dst.get("/ch/20/eq/2").args, kick.get("/ch/01/eq/2").args)

    def test_extracted_header_round_trips_every_scope(self):
        src = Scene.load(EXAMPLE)
        for scope in ("ha", "scribble", "gate", "comp", "eq", "sends", "mainfader"):
            with self.subTest(scope=scope):
                chn = extract_preset(src, 1, [scope], header=True)
                self.assertEqual(unflagged_scopes(chn), [])
                a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
                self.assertEqual(apply_preset(a, 20, chn), apply_preset(b, 20, chn, [scope]))
                self.assertEqual(a.dump(), b.dump())

    def test_cli_reports_the_skipped_scopes(self):
        with tempfile.TemporaryDirectory() as d:
            chn, out = os.path.join(d, "kick.chn"), os.path.join(d, "out.scn")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write(gate_only_header_over_gate_and_eq())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["apply-preset", EXAMPLE, "20", chn, "-o", out]), 0)
            self.assertIn("skipped eq", buf.getvalue())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["apply-preset", EXAMPLE, "20", chn, "-o", out + "2",
                                       "--scope", "eq"]), 0)
            self.assertNotIn("skipped", buf.getvalue())


def with_header(header: str, body: str) -> str:
    return header + "\n" + body


def _drifted_eq() -> Scene:
    sc = Scene.load(EXAMPLE)
    sc.get("/ch/01/eq/1").set_arg(2, "+15.00")
    return sc


class MasklessHeaderTest(unittest.TestCase):
    """A header whose flags field is not a 16-bit % mask says nothing about sections."""

    HEADERS = ('#4.0# 1 "Kick" 0 1', '#4.0# 1 "Kick" 0 %0011 1', '#4.0# 1 "Kick" 0 %00111111abcdefgh 1')

    def test_it_selects_what_a_headerless_preset_selects(self):
        body = extract_preset(Scene.load(EXAMPLE), 1)
        for head in self.HEADERS:
            with self.subTest(head=head):
                chn = with_header(head, body)
                self.assertIsNone(header_scopes(chn))
                self.assertEqual(unflagged_scopes(chn), [])
                a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
                self.assertEqual(apply_preset(a, 20, chn), apply_preset(b, 20, body))
                self.assertEqual(a.dump(), b.dump())

    def test_presets_diff_still_sees_the_eq_it_carries(self):
        body = extract_preset(Scene.load(EXAMPLE), 1)
        for head in self.HEADERS:
            with self.subTest(head=head):
                res = check_preset(_drifted_eq(), "Kick.chn", with_header(head, body))
                self.assertEqual(res.status, DRIFT)
                self.assertIn("/eq/1", [d.path for d in res.drift])


class DelayFollowsTheConfigFlagTest(unittest.TestCase):
    """`/delay` is the config section in a header's flags, whatever scope it has without one."""

    def setUp(self):
        src = Scene.load(EXAMPLE)
        src.get("/ch/01/delay").args = ["ON", "12.3"]
        src.get("/ch/01/delay").rebuild()
        self.body = extract_preset(src, 1, ["ha", "scribble"])
        self.config_only = [ln for ln in self.body.splitlines()
                            if ln.startswith(("/config", "/delay"))]
        self.ha_only = [ln for ln in self.body.splitlines() if not ln.startswith("/config")]

    def _chn(self, present: set[str], lines: list[str]) -> str:
        return with_header(preset_header("Kick", present, set()), "\n".join(lines) + "\n")

    def test_a_config_flag_writes_the_delay(self):
        chn = self._chn({"config"}, self.config_only)
        dst = Scene.load(EXAMPLE)
        apply_preset(dst, 20, chn)
        self.assertEqual(dst.get("/ch/20/delay").args, ["ON", "12.3"])
        self.assertEqual(unflagged_scopes(chn), [])
        plan = {"channels": {"20": {"preset": "kick.chn"}}}
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "kick.chn"), "w", encoding="utf-8", newline="") as fh:
                fh.write(chn)
            plan["_dir"] = d
            self.assertIn("/ch/20/delay", allowed_paths(Scene.load(EXAMPLE), plan))
        drifted = Scene.load(EXAMPLE)
        self.assertIn("/delay", [x.path for x in check_preset(drifted, "Kick.chn", chn).drift])

    def test_a_preamp_flag_without_config_leaves_the_delay(self):
        chn = self._chn({"preamp", "locut"}, self.ha_only)
        dst = Scene.load(EXAMPLE)
        before = dst.get("/ch/20/delay").args
        apply_preset(dst, 20, chn)
        self.assertEqual(dst.get("/ch/20/delay").args, before)
        self.assertEqual(unflagged_scopes(chn), ["/delay"])
        self.assertNotIn("/delay", [x.path for x in check_preset(Scene.load(EXAMPLE),
                                                                 "Kick.chn", chn).drift])

    def test_the_summary_names_the_delay_not_ha_when_ha_is_flagged_and_written(self):
        chn = self._chn({"preamp", "locut", "gate"}, self.body.splitlines())
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "kick.chn"), os.path.join(d, "out.scn")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(chn)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["apply-preset", EXAMPLE, "20", path, "-o", out]), 0)
        self.assertIn("skipped scribble, /delay: the preset header does not flag them present",
                      buf.getvalue())

    def test_an_explicit_scope_keeps_the_delay_under_ha(self):
        chn = self._chn({"config"}, self.config_only)
        dst = Scene.load(EXAMPLE)
        before = dst.get("/ch/20/delay").args
        apply_preset(dst, 20, chn, ["scribble"])
        self.assertEqual(dst.get("/ch/20/delay").args, before)
        apply_preset(dst, 20, chn, ["ha"])
        self.assertEqual(dst.get("/ch/20/delay").args, ["ON", "12.3"])


class BandSetupHeaderTest(unittest.TestCase):
    def test_a_desk_written_split_main_mix_preset_verifies(self):
        # the desk saves the main mix one field per line; apply folds them into /ch/NN/mix
        with tempfile.TemporaryDirectory() as d:
            chn = os.path.join(d, "kick.chn")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write("/mix/fader -10.0\n/mix/pan +20\n")
            plan = {"channels": {"1": {"preset": chn}}}
            rep = run(EXAMPLE, plan, os.path.join(d, "out.scn"))
            self.assertEqual((rep["changed"], rep["unexpected"]), (["/ch/01/mix"], []))
            self.assertEqual(Scene.load(os.path.join(d, "out.scn")).get("/ch/01/mix").args[1:4],
                             ["-10.0", "ON", "+20"])
            self.assertNotIn("/ch/01/mix/fader", allowed_paths(Scene.load(EXAMPLE), plan))

    def test_plan_preset_without_scopes_follows_the_header(self):
        with tempfile.TemporaryDirectory() as d:
            chn, out = os.path.join(d, "kick.chn"), os.path.join(d, "out.scn")
            plan_path = os.path.join(d, "plan.json")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write(gate_only_header_over_gate_and_eq())
            plan = {"channels": {"20": {"preset": chn}}}
            rep = run(EXAMPLE, plan, out)
            self.assertEqual(rep["unexpected"], [])
            self.assertIn("/ch/20/gate", rep["changed"])
            self.assertNotIn("/ch/20/eq/2", rep["changed"])
            self.assertEqual(rep["preset_skipped"], {20: ["eq"]})
            self.assertNotIn("/ch/20/eq/2", allowed_paths(Scene.load(EXAMPLE), plan))
            with open(plan_path, "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["band-setup", EXAMPLE, plan_path, "-o", out + "2"]), 0)
            self.assertIn("ch20 preset: skipped eq", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
