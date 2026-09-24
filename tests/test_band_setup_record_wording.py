"""A band-setup `record` track whose CARD block has no user-out slot is refused in the plan's
own terms: the fix is the plan's `routing` key, not the set-routing command, which stays the
advice `set-record` gives."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.orchestrators.band_swap import apply_plan

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")
EXAMPLE_ALT = os.path.join(FIXTURES, "example-alt.scn")   # CARD block 1-8 is AN1-8
PLAN_FIX = '"routing": {"CARD": {"1-8": "UOUT…"}}'


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class PlanRecordWordingTest(unittest.TestCase):
    def test_the_plan_error_points_at_the_plans_routing_key(self):
        plans = ({"record": {"3": "Output 1"}},
                 {"routing": {"CARD": {"1-8": "AN1-8"}}, "record": {"3": "Output 1"}})
        for template, plan in ((EXAMPLE_ALT, plans[0]), (EXAMPLE, plans[1])):
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError) as cm:
                    apply_plan(Scene.load(template), plan)
                msg = str(cm.exception)
                self.assertIn("CARD block 1-8 is AN1-8, not a UOUT block", msg)
                self.assertIn(PLAN_FIX, msg)
                self.assertNotIn("set-routing", msg)

    def test_band_setup_prints_it_and_set_record_keeps_the_command(self):
        with tempfile.TemporaryDirectory() as d:
            plan, out = os.path.join(d, "plan.json"), os.path.join(d, "out.scn")
            with open(plan, "w", encoding="utf-8") as fh:
                json.dump({"record": {"3": "Output 1"}}, fh)
            rc, _, err = run("band-setup", EXAMPLE_ALT, plan, "-o", out)
            self.assertEqual(rc, 2)
            self.assertIn(PLAN_FIX, err)
            self.assertNotIn("set-routing", err)
            self.assertFalse(os.path.exists(out))
            rc, _, err = run("set-record", EXAMPLE_ALT, "3", "Output 1", "-o", out)
            self.assertEqual(rc, 1)
            self.assertIn("set-routing CARD 1-8=UOUT…", err)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
