"""band-setup's record section: card record tracks patched by source words, resolved after
the routing section, validated whole, and whitelisted to the one user-out line."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene
from x32scene.orchestrators.band_swap import allowed_paths, apply_plan, verify
from x32scene.services.routing import record_map

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EXAMPLE_ALT = os.path.join(FIX, "example-alt.scn")


class RecordApplyTest(unittest.TestCase):
    def test_tracks_are_set_and_only_the_user_out_line_moves(self):
        plan = {"record": {"5": "Output 9", "17": "aux out 2", "32": 208}}
        tmpl, sc = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        apply_plan(sc, plan)
        tracks = dict(record_map(sc))
        self.assertEqual((tracks[5], tracks[17], tracks[32]), ("Output 9", "Aux Out 2", "Monitor R"))
        rep = verify(tmpl, sc, plan)
        self.assertEqual((rep["changed"], rep["unexpected"]), (["/config/userrout/out"], []))
        text = sc.dump()
        self.assertEqual(Scene.parse(text).dump(), text)

    def test_a_track_resolves_through_the_plans_own_card_routing(self):
        plan = {"routing": {"CARD": {"9-16": "UOUT41-48"}}, "record": {"10": "P16 1"}}
        tmpl, sc = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        apply_plan(sc, plan)
        self.assertEqual(sc.get("/config/userrout/out").args[41], "185")
        self.assertEqual(dict(record_map(sc))[10], "P16 1")
        self.assertEqual(verify(tmpl, sc, plan)["unexpected"], [])

    def test_the_user_out_line_is_granted_only_by_a_record_section(self):
        tmpl = Scene.load(EXAMPLE)
        with_record = allowed_paths(tmpl, {"record": {"5": "off"}})
        self.assertEqual(with_record - allowed_paths(tmpl, {}), {"/config/userrout/out"})
        sc = Scene.load(EXAMPLE)
        apply_plan(sc, {"record": {"5": "off"}})
        self.assertEqual(verify(tmpl, sc, {})["unexpected"], ["/config/userrout/out"])
        self.assertEqual(allowed_paths(tmpl, {"record": {}}), allowed_paths(tmpl, {}))

    def test_the_report_names_each_track_and_every_other_reader_of_its_slot(self):
        rep = apply_plan(Scene.load(EXAMPLE), {"record": {"20": "Output 9", "03": "Output 9"}})
        self.assertEqual(rep["record"], [
            {"track": 3, "before": "Local input 3", "after": "Output 9", "slot": 3,
             "also_feeds": ["AES50-A 3", "AES50-B 3"]},
            {"track": 20, "before": "AES50-A input 4", "after": "Output 9", "slot": 20,
             "also_feeds": ["AES50-A 20"]}])
        self.assertEqual(apply_plan(Scene.load(EXAMPLE), {})["record"], [])

    def test_before_is_what_the_template_recorded_when_routing_re_points_the_track(self):
        plan = {"record": {"17": "Output 9"}, "routing": {"CARD": {"17-24": "UOUT1-8"}}}
        rep = apply_plan(Scene.load(EXAMPLE), plan)
        self.assertEqual(dict(record_map(Scene.load(EXAMPLE)))[17], "AES50-A input 1")
        self.assertEqual((rep["record"][0]["before"], rep["record"][0]["after"]),
                         ("AES50-A input 1", "Output 9"))

    def test_two_tracks_on_one_slot_agree_or_are_refused(self):
        routing = {"CARD": {"25-32": "UOUT1-8"}}
        sc = Scene.load(EXAMPLE)
        apply_plan(sc, {"routing": routing, "record": {"1": "Output 1", "25": "output 1"}})
        self.assertEqual(sc.get("/config/userrout/out").args[0], "169")
        with self.assertRaises(ValueError) as cm:
            apply_plan(Scene.load(EXAMPLE),
                       {"routing": routing, "record": {"1": "Output 1", "25": "Output 2"}})
        self.assertIn("tracks 1 and 25 both read user-out slot 1", str(cm.exception))


class RecordValidationTest(unittest.TestCase):
    def _bad(self, plan: dict, fragment: str, scene: str = EXAMPLE):
        sc = Scene.load(scene)
        before = sc.dump()
        with self.assertRaises(ValueError) as cm:
            apply_plan(sc, plan)
        self.assertIn(fragment, str(cm.exception))
        self.assertEqual(sc.get("/config/userrout/out").raw,
                         Scene.parse(before).get("/config/userrout/out").raw)

    def test_each_plan_error(self):
        self._bad({"record": ["5", "Output 9"]}, "record must be an object")
        self._bad({"record": {"33": "off"}}, "record: 33 out of range 1-32")
        self._bad({"record": {"five": "off"}}, "is not a number 1-32")
        self._bad({"record": {"5": "off", "05": "off"}}, "both name 5")
        self._bad({"record": {"5": None}}, "record track 5: source must be")
        self._bad({"record": {"5": ["Output", 9]}}, "record track 5: source must be")
        self._bad({"record": {"5": "bus 9"}}, "record track 5: unknown user-out source")
        self._bad({"record": {"5": "output 17"}}, "output sources run 1-16")
        self._bad({"record": {"5": 209}}, "0-208")

    def test_the_whole_plan_is_checked_before_the_title_is_written(self):
        sc = Scene.load(EXAMPLE)
        header = sc.lines[0].raw
        with self.assertRaises(ValueError):
            apply_plan(sc, {"title": "Renamed", "record": {"5": "bus 9"}})
        self.assertEqual(sc.lines[0].raw, header)

    def test_a_non_uout_block_refuses_the_section_before_any_track_is_written(self):
        self._bad({"record": {"9": "Output 1", "1": "Output 2"}},
                  "CARD block 1-8 is AN1-8, not a UOUT block", EXAMPLE_ALT)


class RecordCliTest(unittest.TestCase):
    def test_band_setup_plan_errors_exit_2_with_nothing_written(self):
        cases = (({"record": {"5": "bus 9"}}, EXAMPLE, "unknown user-out source"),
                 ({"record": {"2": "Output 1"}}, EXAMPLE_ALT, "AN1-8"))
        for plan, template, why in cases:
            with self.subTest(plan=plan), tempfile.TemporaryDirectory() as d:
                path, out = os.path.join(d, "plan.json"), os.path.join(d, "out.scn")
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(plan, fh)
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    code = main(["band-setup", template, path, "-o", out])
                self.assertEqual(code, 2)
                self.assertIn("plan failed, nothing written", err.getvalue())
                self.assertIn(why, err.getvalue())
                self.assertFalse(os.path.exists(out))

    def test_band_setup_writes_the_record_patch(self):
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "plan.json"), os.path.join(d, "out.scn")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"record": {"12": "Output 3"}}, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["band-setup", EXAMPLE_ALT, path, "-o", out]), 0)
            self.assertIn("1 line(s) over 1 path(s)", buf.getvalue())
            self.assertEqual(dict(record_map(Scene.load(out)))[12], "Output 3")

    def test_band_setup_prints_what_set_record_prints_for_a_shared_slot(self):
        with tempfile.TemporaryDirectory() as d:
            path, out = os.path.join(d, "plan.json"), os.path.join(d, "out.scn")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"record": {"3": "Output 9"}}, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["band-setup", EXAMPLE, path, "-o", out]), 0)
            lines = buf.getvalue().splitlines()
            self.assertEqual(lines[1:3], [
                "record track 3: Local input 3 -> Output 9 (user-out slot 3)",
                "  user-out slot 3 also feeds AES50-A 3, AES50-B 3"])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["set-record", EXAMPLE, "3", "Output 9", "-o", os.path.join(d, "s.scn")])
            self.assertEqual(["record " + ln if ln.startswith("track") else ln
                              for ln in buf.getvalue().splitlines()[:2]], lines[1:3])


if __name__ == "__main__":
    unittest.main()
