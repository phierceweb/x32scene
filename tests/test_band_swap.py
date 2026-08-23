"""Band-swap orchestrator: one JSON plan re-skins a template scene (title, names,
head-amps, presets, DCAs, IEM copies) by composing existing transforms, then verifies
the output differs from the template ONLY in plan-intended paths.
"""

import json
import os
import tempfile
import unittest

from x32scene.model import Scene
from x32scene.orchestrators.band_swap import apply_plan, verify
from x32scene.services.diff import diff
from x32scene.services.groups import dca_members

HEADER = '#4.0# "Example Template" "" %000000000 1'.ljust(127)
TEMPLATE_LINES = [
    HEADER,
    "/config/routing/IN AN1-8 AN9-16 A1-8 A9-16",
    "/config/buslink OFF OFF OFF OFF OFF OFF OFF OFF",
    '/ch/01/config "Kick" 1 67 1',
    "/ch/01/mix ON   0.0 ON +0 OFF   -oo",
    "/ch/01/mix/01 ON   -6.0 +0 POST   0",
    "/ch/01/mix/03 OFF   -oo +0 POST   0",
    "/ch/01/grp %00000000 %000000",
    '/ch/20/config "Gtr 1" 1 67 20',
    "/ch/20/mix ON   0.0 ON -94 OFF   -oo",
    "/ch/20/mix/01 ON   -3.0 +0 PRE   0",
    "/ch/20/mix/03 OFF   -oo +0 POST   0",
    "/ch/20/eq/1 PEQ 124.7 -2.00 2.0",
    "/ch/20/grp %00000100 %000000",
    "/headamp/000 +27.0 OFF",
    "/headamp/035 +0.5 OFF",
    "/fx/1 PLAT",
]


def template() -> Scene:
    return Scene.parse("\n".join(TEMPLATE_LINES) + "\n")


def make_plan(preset_path: str | None = None) -> dict:
    plan = {
        "title": "Alt Rig - Test",
        "channels": {
            "1": {"name": "Kick C", "gain_db": 20.0, "phantom": True},
            "20": {"name": "Gtr Sam"},
        },
        "dca": {"3": [1]},
        "iem_copy": [{"src": 1, "dst": 3}],
    }
    if preset_path:
        plan["channels"]["20"]["preset"] = preset_path
        plan["channels"]["20"]["scopes"] = ["eq"]
    return plan


class ApplyPlanTest(unittest.TestCase):
    def test_applies_title_names_headamp_dca_and_iem_copy(self):
        sc = template()
        summary = apply_plan(sc, make_plan())
        self.assertEqual(sc.name, "Alt Rig - Test")
        self.assertEqual(sc.get("/ch/01/config").args[0], '"Kick C"')
        self.assertEqual(sc.get("/ch/20/config").args[0], '"Gtr Sam"')
        self.assertEqual(sc.get("/headamp/000").args, ["+20.0", "ON"])
        self.assertEqual(dca_members(sc)[3], ["/ch/01"])  # ch20 dropped, ch1 added
        self.assertEqual(sc.get("/ch/01/mix/03").args, sc.get("/ch/01/mix/01").args)
        self.assertGreater(summary["lines_changed"], 0)

    def test_applies_channel_preset_with_scopes(self):
        with tempfile.TemporaryDirectory() as d:
            chn = os.path.join(d, "gtr.chn")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write("/eq/1 LCut 80.0 0.00 2.0\n/config \"NOPE\" 1 1 1\n")
            sc = template()
            apply_plan(sc, make_plan(chn))
            self.assertEqual(sc.get("/ch/20/eq/1").args, ["LCut", "80.0", "0.00", "2.0"])
            # scribble scope not selected: preset /config must NOT override the rename
            self.assertEqual(sc.get("/ch/20/config").args[0], '"Gtr Sam"')

    def test_plan_rename_wins_over_full_scope_preset(self):
        # default (all) scopes include scribble: the preset's /config must not override
        # the plan's explicit rename, and the source slot must stay the template's
        with tempfile.TemporaryDirectory() as d:
            chn = os.path.join(d, "gtr.chn")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write('/config "Vox" 1 1 5\n/eq/1 LCut 80.0 0.00 2.0\n')
            plan = make_plan()
            plan["channels"]["20"]["preset"] = chn
            sc = template()
            apply_plan(sc, plan)
            cfg = sc.get("/ch/20/config").args
            self.assertEqual(cfg[0], '"Gtr Sam"')
            self.assertEqual(cfg[-1], "20")

    def test_unknown_plan_keys_raise(self):
        for bad in ({"chanels": {}}, {"channels": {"1": {"nmae": "X"}}}):
            with self.subTest(plan=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), {**make_plan(), **bad})

    def test_bad_scope_name_raises(self):
        with tempfile.TemporaryDirectory() as d:
            chn = os.path.join(d, "g.chn")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write("/eq/1 LCut 80.0 0.00 2.0\n")
            plan = make_plan(chn)
            plan["channels"]["20"]["scopes"] = ["EQ"]  # valid names are lowercase
            with self.assertRaises(ValueError):
                apply_plan(template(), plan)

    def test_out_of_range_iem_copy_bus_raises(self):
        plan = make_plan()
        plan["iem_copy"] = [{"src": 1, "dst": 17}]
        with self.assertRaises(ValueError):
            apply_plan(template(), plan)

    def test_unknown_channel_raises(self):
        plan = make_plan()
        plan["channels"]["31"] = {"name": "Ghost"}
        with self.assertRaises(KeyError):
            apply_plan(template(), plan)

    def test_plan_mute_and_fader_values_are_type_checked(self):
        # "false" is truthy, so an unchecked bool() would mute the channel it names;
        # a bool passes isinstance(int), so True must not sneak through as a level.
        # Range errors must raise in validate_plan too, naming the channel.
        for spec in ({"mute": "false"}, {"mute": 0}, {"fader": True}, {"fader": -95},
                     {"fader": 11}, {"gain_db": True}, {"gain_db": "20"},
                     {"gain_db": 65}, {"phantom": 1}, {"phantom": "false"}):
            with self.subTest(spec=spec):
                plan = make_plan()
                plan["channels"]["20"].update(spec)
                with self.assertRaises(ValueError) as ctx:
                    apply_plan(template(), plan)
                self.assertIn("20", str(ctx.exception))

    def test_plan_fader_and_mute_neutralize_a_channel(self):
        for spelling in ("-oo", "oo"):
            with self.subTest(fader=spelling):
                plan = make_plan()
                plan["channels"]["20"].update({"fader": spelling, "mute": True})
                tmpl, edited = template(), template()
                apply_plan(edited, plan)
                mix = edited.get("/ch/20/mix").args
                self.assertEqual(mix[0], "OFF")
                self.assertEqual(mix[1], "-oo")
                self.assertEqual(verify(tmpl, edited, plan)["unexpected"], [])


class VerifyTest(unittest.TestCase):
    def test_clean_apply_verifies_with_no_unexpected_paths(self):
        tmpl, edited = template(), template()
        plan = make_plan()
        apply_plan(edited, plan)
        report = verify(tmpl, edited, plan)
        changed = set(report["changed"])
        self.assertIn("/ch/01/config", changed)
        self.assertIn("/headamp/000", changed)
        self.assertEqual(report["unexpected"], [])

    def test_out_of_plan_edit_is_flagged(self):
        tmpl, edited = template(), template()
        plan = make_plan()
        apply_plan(edited, plan)
        edited.get("/fx/1").set_arg(0, "VRM")  # rogue edit outside the plan
        report = verify(tmpl, edited, plan)
        self.assertEqual(report["unexpected"], ["/fx/1"])

    def test_verify_passes_for_preset_plus_gain_plan(self):
        # allowed_paths resolves the headamp from the template and apply from the edited
        # scene; the two must agree even when the preset carries a /config line
        with tempfile.TemporaryDirectory() as d:
            chn = os.path.join(d, "k.chn")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write('/config "Vox" 1 1 5\n/eq/1 LCut 80.0 0.00 2.0\n')
            plan = make_plan()
            plan["channels"]["1"]["preset"] = chn
            tmpl, edited = template(), template()
            apply_plan(edited, plan)
            report = verify(tmpl, edited, plan)
            self.assertEqual(report["unexpected"], [])

    def test_round_trip_preserved(self):
        edited = template()
        apply_plan(edited, make_plan())
        text = edited.dump()
        self.assertEqual(Scene.parse(text).dump(), text)


class RunTest(unittest.TestCase):
    """The verify-before-save guarantee must live in the orchestrator, not only the CLI."""

    def _template_file(self, d):
        p = os.path.join(d, "tmpl.scn")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(template().dump())
        return p

    def test_run_writes_and_reports(self):
        from x32scene.orchestrators.band_swap import run
        with tempfile.TemporaryDirectory() as d:
            tmpl, out = self._template_file(d), os.path.join(d, "out.scn")
            rep = run(tmpl, make_plan(), out)
            self.assertEqual(rep["unexpected"], [])
            self.assertTrue(os.path.exists(out))
            self.assertEqual(Scene.load(out).name, "Alt Rig - Test")

    def test_run_refuses_to_save_on_unexpected_change(self):
        from unittest import mock
        from x32scene.orchestrators import band_swap as bs
        with tempfile.TemporaryDirectory() as d:
            tmpl, out = self._template_file(d), os.path.join(d, "out.scn")
            with mock.patch.object(bs, "allowed_paths", return_value=set()):
                with self.assertRaises(ValueError):
                    bs.run(tmpl, make_plan(), out)
            self.assertFalse(os.path.exists(out))


class BandSetupCliTest(unittest.TestCase):
    def test_cli_writes_output_and_reports(self):
        from x32scene.cli import main
        with tempfile.TemporaryDirectory() as d:
            tmpl = os.path.join(d, "tmpl.scn")
            with open(tmpl, "w", encoding="utf-8", newline="") as fh:
                fh.write(template().dump())
            plan_p = os.path.join(d, "plan.json")
            with open(plan_p, "w", encoding="utf-8") as fh:
                json.dump(make_plan(), fh)
            out = os.path.join(d, "out.scn")
            self.assertEqual(main(["band-setup", tmpl, plan_p, "-o", out]), 0)
            changed = {c.path for c in diff(Scene.load(tmpl), Scene.load(out))}
            self.assertIn("#4.0#", changed)
            self.assertIn("/ch/01/config", changed)

    def test_cli_verify_failed_exits_2_and_writes_nothing(self):
        # pins the save gate itself: when verify reports out-of-plan paths, the CLI
        # must exit 2 without writing, regardless of why verify flagged them
        from unittest import mock
        from x32scene import _cli_edits as edits_mod
        from x32scene import cli as cli_mod
        with tempfile.TemporaryDirectory() as d:
            tmpl = os.path.join(d, "tmpl.scn")
            with open(tmpl, "w", encoding="utf-8", newline="") as fh:
                fh.write(template().dump())
            plan_p = os.path.join(d, "plan.json")
            with open(plan_p, "w", encoding="utf-8") as fh:
                json.dump(make_plan(), fh)
            out = os.path.join(d, "out.scn")
            with mock.patch.object(edits_mod._band_swap, "verify",
                                   return_value={"changed": [], "unexpected": ["/fx/1"]}):
                self.assertEqual(cli_mod.main(["band-setup", tmpl, plan_p, "-o", out]), 2)
            self.assertFalse(os.path.exists(out))

    def test_cli_bad_plan_exits_2_and_writes_nothing(self):
        from x32scene.cli import main
        with tempfile.TemporaryDirectory() as d:
            tmpl = os.path.join(d, "tmpl.scn")
            with open(tmpl, "w", encoding="utf-8", newline="") as fh:
                fh.write(template().dump())
            plan_p = os.path.join(d, "plan.json")
            plan = make_plan()
            plan["channels"]["31"] = {"name": "Ghost"}
            with open(plan_p, "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            out = os.path.join(d, "out.scn")
            self.assertEqual(main(["band-setup", tmpl, plan_p, "-o", out]), 2)
            self.assertFalse(os.path.exists(out))

    def test_cli_plan_problems_all_exit_2(self):
        # same class of user mistake must not return different codes
        from x32scene.cli import main
        with tempfile.TemporaryDirectory() as d:
            tmpl = os.path.join(d, "tmpl.scn")
            with open(tmpl, "w", encoding="utf-8", newline="") as fh:
                fh.write(template().dump())
            out = os.path.join(d, "out.scn")
            bad_json = os.path.join(d, "bad.json")
            with open(bad_json, "w", encoding="utf-8") as fh:
                fh.write("{not valid json")
            missing_preset = os.path.join(d, "mp.json")
            plan = make_plan()
            plan["channels"]["20"]["preset"] = "nope.chn"
            with open(missing_preset, "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            dir_preset = os.path.join(d, "dp.json")
            plan2 = make_plan()
            plan2["channels"]["20"]["preset"] = d  # a directory, not a file
            with open(dir_preset, "w", encoding="utf-8") as fh:
                json.dump(plan2, fh)
            for plan_p in (bad_json, missing_preset, dir_preset):
                with self.subTest(plan=os.path.basename(plan_p)):
                    self.assertEqual(main(["band-setup", tmpl, plan_p, "-o", out]), 2)
                    self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
