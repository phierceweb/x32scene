"""Preflight: semantic rig invariants (names/sources/phantom/gain/mute/record/FX)
checked against an expected-config. Golden: the checked-in example scene must pass the
checked-in example config cleanly.
"""

import json
import os
import tempfile
import unittest

from x32scene.model import Scene
from x32scene.services.preflight import (
    Finding, coverage, preflight, report)

from tests.preflight_scene import fails, line, mini_scene, warns

EXAMPLE_SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")
EXAMPLE_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "config", "example-preflight.json")

EXPECTED = {
    "gain_tolerance_db": 3.0,
    "channels": {
        "1": {"name": "Kick", "source": "Local input 1", "gain": 27.0,
              "phantom": False, "in_main": True},
        "5": {"name": "Rack 1", "source": "Local input 5", "gain": 13.0,
              "phantom": False, "in_main": False},
        "20": {"name": "Gtr 1", "source": "AES50-A input 4", "gain": 0.5,
               "phantom": False, "in_main": True},
    },
    "record": {"29": "AES50-A input 13", "32": "AES50-A input 16"},
    "fx": {"1": "PLAT"},
}


class PreflightTest(unittest.TestCase):
    def test_clean_scene_passes(self):
        self.assertEqual(preflight(mini_scene(), EXPECTED), [])

    def test_name_mismatch_fails(self):
        sc = mini_scene({"/ch/01/config": '/ch/01/config "Kick Drum" 1 67 1'})
        f = fails(preflight(sc, EXPECTED))
        self.assertEqual(len(f), 1)
        self.assertIn("name", f[0].message)

    def test_source_mismatch_fails(self):
        sc = mini_scene({"/ch/20/config": '/ch/20/config "Gtr 1" 1 67 19'})
        msgs = [f.message for f in fails(preflight(sc, EXPECTED))]
        self.assertTrue(any("source" in m for m in msgs), msgs)

    def test_phantom_mismatch_fails(self):
        sc = mini_scene({"/headamp/000": "/headamp/000 +27.0 ON"})
        f = fails(preflight(sc, EXPECTED))
        self.assertEqual(len(f), 1)
        self.assertIn("phantom", f[0].message)

    def test_gain_drift_warns_not_fails(self):
        sc = mini_scene({"/headamp/000": "/headamp/000 +31.5 OFF"})
        findings = preflight(sc, EXPECTED)
        self.assertEqual(fails(findings), [])
        self.assertEqual(len(warns(findings)), 1)
        self.assertIn("gain", warns(findings)[0].message)

    def test_gain_within_tolerance_is_silent(self):
        sc = mini_scene({"/headamp/000": "/headamp/000 +29.0 OFF"})
        self.assertEqual(preflight(sc, EXPECTED), [])

    def test_out_of_main_channel_fails_when_audible(self):
        sc = mini_scene({"/ch/05/mix": "/ch/05/mix ON -2.0 ON +0 OFF   -oo"})
        f = fails(preflight(sc, EXPECTED))
        self.assertEqual(len(f), 1)
        self.assertIn("main", f[0].message)

    def test_fader_at_minus_inf_counts_as_out_of_main(self):
        # ON + LR assigned + fader at -oo is out of the blend, not in it
        sc = mini_scene({"/ch/05/mix": "/ch/05/mix ON   -oo ON +0 OFF   -oo"})
        self.assertEqual(preflight(sc, EXPECTED), [])

    def test_missing_channel_fails(self):
        exp = {**EXPECTED, "channels": {**EXPECTED["channels"],
                                        "2": {"name": "Kick Sub"}}}
        msgs = [f.message for f in fails(preflight(mini_scene(), exp))]
        self.assertTrue(any("missing" in m for m in msgs), msgs)

    def test_record_map_mismatch_fails(self):
        toks = line("/config/userrout/out").split(" ")
        toks[32] = "1"   # slot 32 (track 32) now sources Local input 1
        sc = mini_scene({"/config/userrout/out": " ".join(toks)})
        f = fails(preflight(sc, EXPECTED))
        self.assertEqual(len(f), 1)
        self.assertIn("record", f[0].message)

    def test_fx_type_mismatch_fails(self):
        sc = mini_scene({"/fx/1": "/fx/1 VRM"})
        f = fails(preflight(sc, EXPECTED))
        self.assertEqual(len(f), 1)
        self.assertIn("fx", f[0].message.lower())

    def test_missing_mix_line_fails_in_main_check(self):
        # absence of the /mix line is not evidence the channel is out of the blend
        sc = mini_scene({"/ch/05/mix": None})
        exp = {"channels": {"5": {"in_main": False}}}
        self.assertTrue(fails(preflight(sc, exp)))

    def test_unknown_channel_key_is_flagged(self):
        # a typo'd key must not silently disable the check it was meant to be
        fs = fails(preflight(mini_scene(), {"channels": {"1": {"phanton": True}}}))
        self.assertTrue(any("phanton" in f.message for f in fs), fs)

    def test_unknown_top_level_key_is_flagged(self):
        fs = fails(preflight(mini_scene(), {"channel": {}}))
        self.assertTrue(any("channel" in f.message for f in fs), fs)

    def test_underscore_keys_are_comments(self):
        exp = {"_comment": "x",
               "channels": {"1": {"name": "Kick", "_note": "y"}}}
        self.assertEqual(preflight(mini_scene(), exp), [])

    def test_underscore_keys_allowed_inside_numbered_dicts(self):
        # users copy the example config's _comment pattern into channels/record/fx
        exp = {"channels": {"_comment": "x", "1": {"name": "Kick"}},
               "record": {"_comment": "y"}, "fx": {"_note": "z"}}
        self.assertEqual(preflight(mini_scene(), exp), [])

    def test_non_numeric_key_fails_cleanly(self):
        fs = fails(preflight(mini_scene(), {"channels": {"one": {"name": "Kick"}}}))
        self.assertTrue(any("one" in f.message for f in fs), fs)


class PreflightCliTest(unittest.TestCase):
    def _write(self, dir_, name, text):
        p = os.path.join(dir_, name)
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return p

    def test_cli_pass_and_fail_exit_codes(self):
        from x32scene.cli import main
        with tempfile.TemporaryDirectory() as d:
            scn = self._write(d, "ok.scn", mini_scene().dump())
            bad = self._write(d, "bad.scn", mini_scene(
                {"/headamp/000": "/headamp/000 +27.0 ON"}).dump())
            cfg = self._write(d, "exp.json", json.dumps(EXPECTED))
            self.assertEqual(main(["preflight", scn, "--config", cfg]), 0)
            self.assertEqual(main(["preflight", bad, "--config", cfg]), 1)


class GoldenPreflightTest(unittest.TestCase):
    """No skip guard: both files ship, so this must always run."""

    def _expected(self):
        with open(EXAMPLE_CONFIG, encoding="utf-8") as fh:
            return json.load(fh)

    def test_example_scene_passes_example_config(self):
        findings = preflight(Scene.load(EXAMPLE_SCENE), self._expected())
        self.assertEqual(findings, [])

    def test_example_scene_passes_example_sidecar(self):
        from x32scene.services.stage import load_stage
        stage = load_stage(os.path.join(os.path.dirname(EXAMPLE_CONFIG), "example-stage.json"))
        self.assertEqual(preflight(Scene.load(EXAMPLE_SCENE), self._expected(), stage=stage), [])

    def test_example_alt_fails_example_config_in_named_areas(self):
        # the negative golden: a console-written scene that differs in exactly the places
        # the monitor-skeleton families check must light up each of them
        findings = preflight(Scene.load(EXAMPLE_ALT), self._expected())
        areas = {f.area for f in findings if f.severity == "FAIL"}
        for area in ("out main 05", "out main 09", "routing AES50A", "routing CARD",
                     "record 09"):
            self.assertIn(area, areas)


class ConfigShapeTest(unittest.TestCase):
    """A malformed config is a named FAIL — never a traceback, never a silent pass."""

    def test_string_boolean_is_a_fail_not_a_pass(self):
        # "false" is truthy: coerced, it agreed with a channel that IS in the blend
        for key in ("in_main", "phantom"):
            with self.subTest(key=key):
                fs = fails(preflight(mini_scene(), {"channels": {"1": {key: "false"}}}))
                self.assertEqual(len(fs), 1, fs)
                self.assertIn(key, fs[0].message)
                self.assertIn("true or false", fs[0].message)

    def test_string_gain_is_a_fail(self):
        fs = fails(preflight(mini_scene(), {"channels": {"1": {"gain": "27"}}}))
        self.assertEqual(len(fs), 1, fs)
        self.assertIn("gain", fs[0].message)

    def test_string_tolerance_is_a_fail(self):
        fs = fails(preflight(mini_scene(), {"gain_tolerance_db": "3"}))
        self.assertEqual(len(fs), 1, fs)
        self.assertIn("gain_tolerance_db", fs[0].message)

    def test_list_valued_section_is_one_finding(self):
        for section in ("channels", "record", "fx"):
            with self.subTest(section=section):
                fs = fails(preflight(mini_scene(), {section: []}))
                self.assertEqual(len(fs), 1, fs)
                self.assertIn(section, fs[0].message)
                self.assertIn("object", fs[0].message)

    def test_string_channel_spec_is_one_finding(self):
        fs = fails(preflight(mini_scene(), {"channels": {"1": "Kick"}}))
        self.assertEqual(len(fs), 1, fs)
        self.assertEqual(fs[0].area, "ch 01")

    def test_colliding_numbered_keys_fail_loudly(self):
        fs = fails(preflight(mini_scene(), {"channels": {"1": {"name": "Kick"},
                                                         "01": {"name": "Kick"}}}))
        self.assertEqual(len(fs), 1, fs)
        self.assertIn("'01'", fs[0].message)

    def test_out_of_range_numbered_key_fails(self):
        cases = {"channels": ("33", {}), "record": ("0", "x"), "fx": ("9", "PLAT")}
        for section, (key, val) in cases.items():
            with self.subTest(section=section):
                fs = fails(preflight(mini_scene(), {section: {key: val}}))
                self.assertEqual(len(fs), 1, fs)
                self.assertIn("out of range", fs[0].message)


class CoverageTest(unittest.TestCase):
    """PREFLIGHT OK must say what ran; a section the config never declared did not."""

    def test_coverage_counts_declared_entries(self):
        self.assertEqual(coverage(EXPECTED), {"channels": 3, "record": 2, "fx": 1})

    def test_coverage_skips_comments_and_absent_sections(self):
        exp = {"_c": "x", "gain_tolerance_db": 2, "fx": {"_n": "y", "1": "PLAT"}}
        self.assertEqual(coverage(exp), {"fx": 1})

    def test_report_names_what_ran(self):
        text = report([], coverage(EXPECTED))
        self.assertIn("PREFLIGHT OK", text)
        self.assertIn("checked: channels(3) record(2) fx(1)", text)
        self.assertNotIn("matches the expected config", text)

    def test_report_with_nothing_declared_says_so(self):
        self.assertIn("no expected-config sections", report([], {}))

    def test_report_with_findings_still_names_what_ran(self):
        f = Finding("FAIL", "ch 01", "x")
        self.assertIn("checked: channels(3)", report([f], coverage(EXPECTED)))

    def test_findings_carry_the_scene_path(self):
        fs = fails(preflight(mini_scene({"/headamp/000": "/headamp/000 +27.0 ON"}), EXPECTED))
        self.assertEqual(fs[0].path, "/headamp/000")
        fs = fails(preflight(mini_scene({"/fx/1": "/fx/1 VRM"}), EXPECTED))
        self.assertEqual(fs[0].path, "/fx/1")


if __name__ == "__main__":
    unittest.main()
