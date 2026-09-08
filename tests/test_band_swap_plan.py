"""Plan validation and whitelist exactness for band-setup.

Every case here is a plan that once did the opposite of what it said, or refused a scene it
should have written. A plan is validated whole before any line is written, so a bad plan
must raise ValueError — never AttributeError, which escapes the CLI's error boundary as a
traceback and loses "nothing written".
"""

import os
import tempfile
import unittest

from x32scene.model import Scene
from x32scene.orchestrators.band_swap import apply_plan, run, verify
from x32scene.services.groups import dca_members

HEADER = '#4.0# "Plan Template" "" %000000000 1'.ljust(127)
TEMPLATE_LINES = [
    HEADER,
    "/config/buslink OFF OFF ON OFF OFF OFF OFF OFF",
    "/config/chlink OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF",
    "/config/auxlink OFF OFF OFF OFF",
    "/config/fxlink OFF OFF OFF OFF",
    '/ch/19/config "Gtr 1 DI" 1 67 19',
    "/ch/19/grp %00000100 %000000",
    "/ch/19/mix/05 ON   -4.0 +0 PRE   0",
    "/ch/19/mix/06 OFF   -4.0",
    '/ch/20/config "Gtr 1" 1 67 20',
    "/ch/20/grp %00000100 %000000",
    "/ch/20/eq/1 PEQ 124.7 -2.00 2.0",
    "/outputs/main/09 6 POST OFF",
]


def template() -> Scene:
    return Scene.parse("\n".join(TEMPLATE_LINES) + "\n")


def scene_file(d: str, lines=None) -> str:
    path = os.path.join(d, "t.scn")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lines or TEMPLATE_LINES) + "\n")
    return path


class DcaValidationTest(unittest.TestCase):
    """An unreadable member list empties the group rather than skipping the step, and the
    all-channel /grp whitelist blesses the damage, so verify cannot catch it."""

    def test_members_must_be_a_list_of_channel_numbers(self):
        for members in ("nope", 19, {"1": 19}, [19, "20"], [19, 99], [19, 0], [19, 2.0],
                        [19, True], [19, None]):
            with self.subTest(members=members):
                sc = template()
                with self.assertRaises(ValueError):
                    apply_plan(sc, {"dca": {"3": members}})
                self.assertEqual(dca_members(sc)[3], ["/ch/19", "/ch/20"])

    def test_dca_number_is_range_checked(self):
        for group in ("9", "0", "abc"):
            with self.subTest(group=group):
                with self.assertRaises(ValueError):
                    apply_plan(template(), {"dca": {group: [19]}})

    def test_two_keys_naming_one_dca_raise(self):
        with self.assertRaises(ValueError):
            apply_plan(template(), {"dca": {"3": [19], "03": [20]}})

    def test_a_valid_membership_still_applies(self):
        sc = template()
        apply_plan(sc, {"dca": {"3": [19]}})
        self.assertEqual(dca_members(sc)[3], ["/ch/19"])


class PlanShapeTest(unittest.TestCase):
    def test_wrong_container_types_raise_value_error(self):
        for plan in ({"channels": []}, {"channels": "x"}, {"dca": []}, {"outputs": []},
                     {"iem_copy": {"src": 1}}, {"iem_sends": {"5": {}}},
                     {"channels": {"20": "x"}}, {"channels": {"20": {"scopes": "eq"}}}):
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    apply_plan(template(), plan)

    def test_numbered_keys_are_validated_and_canonical(self):
        for plan in ({"channels": {"abc": {"name": "X"}}}, {"channels": {"99": {"name": "X"}}},
                     {"channels": {"0": {"name": "X"}}}, {"outputs": {"17": 1}},
                     {"outputs": {"abc": 1}},
                     {"outputs": {"9": 1, "009": 2}},      # both name output 9
                     {"channels": {"20": {"name": "A"}, "020": {"name": "B"}}}):
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    apply_plan(template(), plan)

    def test_iem_copy_buses_are_int_strict(self):
        for cp in ({"src": True, "dst": 5}, {"src": 1.9, "dst": 5}, {"src": "1", "dst": 5},
                   {"src": 0, "dst": 5}, {"src": 17, "dst": 5}, {"src": 1},
                   {"src": 5, "dst": 5}, {"src": 1, "dst": 5, "extra": 1}):
            with self.subTest(cp=cp):
                with self.assertRaises(ValueError):
                    apply_plan(template(), {"iem_copy": [cp]})


class VerifyExactnessTest(unittest.TestCase):
    def test_a_title_applies_to_any_firmware_header(self):
        for rev in ("#2.7#", "#3.1#", "#4.0#"):
            with self.subTest(rev=rev):
                lines = [TEMPLATE_LINES[0].replace("#4.0#", rev, 1), *TEMPLATE_LINES[1:]]
                with tempfile.TemporaryDirectory() as d:
                    out = os.path.join(d, "out.scn")
                    report = run(scene_file(d, lines), {"title": "Retitled"}, out)
                    self.assertEqual(report["unexpected"], [])
                    self.assertEqual(Scene.load(out).name, "Retitled")

    def test_off_refusal_names_the_send_the_plan_named(self):
        # /ch/19/mix/06 is OFF, but bus 5 — the one the plan names — is ON. Judging the
        # mirror would reject a correct trim, after already writing the named send.
        sc = template()
        apply_plan(sc, {"iem_sends": [{"strip": 19, "bus": 5, "level": -14.0}]})
        self.assertEqual(sc.get("/ch/19/mix/05").args[1], "-14.0")

    def test_an_indented_preset_line_is_whitelisted_by_the_parser_that_writes_it(self):
        with tempfile.TemporaryDirectory() as d:
            chn = os.path.join(d, "p.chn")
            with open(chn, "w", encoding="utf-8", newline="") as fh:
                fh.write("  /eq/1 PEQ 100.0 +3.00 2.0\n")
            plan = {"channels": {"20": {"preset": chn, "scopes": ["eq"]}}}
            tmpl, sc = template(), template()
            apply_plan(sc, plan)
            self.assertEqual(verify(tmpl, sc, plan)["unexpected"], [])
            self.assertEqual(sc.get("/ch/20/eq/1").args[1], "100.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class PlanTopLevelShapeTest(unittest.TestCase):
    """A plan file that parses as JSON but is not an object. load_plan assigns into it,
    so without a shape check these raise TypeError rather than a named plan error."""

    def _load(self, text):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plan.json")
            with open(path, "w") as fh:
                fh.write(text)
            from x32scene.orchestrators.band_swap import load_plan
            return load_plan(path)

    def test_non_object_plans_raise_value_error(self):
        for text in ("[1,2,3]", '"a string"', "42", "null", "true"):
            with self.subTest(plan=text):
                with self.assertRaises(ValueError) as cm:
                    self._load(text)
                self.assertIn("must be a JSON object", str(cm.exception))

    def test_the_cli_reports_a_plan_error_and_writes_nothing(self):
        import contextlib
        import io

        from x32scene.cli import main
        with tempfile.TemporaryDirectory() as d:
            plan, out = os.path.join(d, "p.json"), os.path.join(d, "o.scn")
            with open(plan, "w") as fh:
                fh.write("[1,2,3]")
            scene = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = main(["band-setup", scene, plan, "-o", out])
            self.assertEqual(rc, 2)                      # the documented plan-error code
            self.assertIn("nothing written", err.getvalue())
            self.assertFalse(os.path.exists(out))


class SilentNoOpTest(unittest.TestCase):
    """A plan that names something the console does not have must say so, not validate
    clean and then apply nothing at exit 0."""

    def _bad(self, plan, fragment):
        from x32scene.orchestrators._schema import validate_plan
        with self.assertRaises(ValueError) as cm:
            validate_plan(plan)
        self.assertIn(fragment, str(cm.exception))

    def test_a_routing_bank_must_be_one_the_console_has(self):
        for bank in ("Card", "CARDD", "card"):
            with self.subTest(bank=bank):
                self._bad({"routing": {"preset": "x.rou", "banks": [bank]}},
                          "banks must be from")

    def test_two_keys_naming_one_fx_slot_collide(self):
        self._bad({"fx": {"1": {"type": "HALL"}, "01": {"type": "PLAT"}}}, "both name 1")

    def test_two_keys_naming_one_output_collide(self):
        self._bad({"output_patch": {"main": {"9": {"pos": "PRE"}, "09": {"pos": "POST"}}}},
                  "both name 9")

    def test_a_zero_padded_slot_names_the_same_path_apply_writes(self):
        """The whitelist has to name the path apply writes, or a zero-padded key reads
        as an out-of-plan change."""
        from x32scene.orchestrators._sections import allowed_sections
        self.assertIn("/fx/8", allowed_sections({"fx": {"08": {"type": "GEQ2"}}}))
