"""band-setup names every path it changed, and marks the sends a stereo link wrote without
the plan naming them."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from tests.test_band_swap_sends import template
from x32scene.cli import main
from x32scene.orchestrators.band_swap import apply_plan, mirrored_paths, verify

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _mirrored(plan: dict) -> list[str]:
    tmpl, sc = template(), template()
    apply_plan(sc, plan)
    return verify(tmpl, sc, plan)["mirrored"]


class MirroredReportTest(unittest.TestCase):
    def test_a_send_record_marks_every_side_but_the_one_it_named(self):
        self.assertEqual(_mirrored({"iem_sends": [{"strip": 11, "bus": 5, "level": -16.0}]}),
                         ["/ch/11/mix/06", "/ch/12/mix/05", "/ch/12/mix/06"])

    def test_an_unlinked_send_mirrors_nothing(self):
        self.assertEqual(_mirrored({"iem_sends": [{"strip": 20, "bus": 1, "level": -14.0}]}),
                         [])

    def test_a_copy_onto_a_linked_pair_marks_the_bus_it_did_not_name(self):
        got = _mirrored({"iem_copy": [{"src": 3, "dst": 5}]})
        self.assertTrue(got)
        self.assertTrue(all(p.endswith("/mix/06") for p in got), got)

    def test_a_path_another_record_names_is_not_mirrored(self):
        plan = {"iem_copy": [{"src": 3, "dst": 5}],
                "iem_sends": [{"strip": 20, "bus": 6, "level": -9.5, "on": True}]}
        got = _mirrored(plan)
        self.assertNotIn("/ch/20/mix/05", got)
        self.assertNotIn("/ch/20/mix/06", got)
        self.assertIn("/ch/01/mix/06", got)

    def test_a_send_a_channel_preset_writes_is_not_mirrored(self):
        plan = {"_dir": os.path.dirname(EXAMPLE),
                "channels": {"11": {"preset": "example.chn", "scopes": ["sends"]}},
                "iem_sends": [{"strip": 12, "bus": 5, "level": -6.0}]}
        self.assertEqual(mirrored_paths(template(), plan), {"/ch/12/mix/06"})


class BandSetupOutputTest(unittest.TestCase):
    def _run(self, plan: dict, *extra: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            plan_path, out = os.path.join(d, "plan.json"), os.path.join(d, "o.scn")
            with open(plan_path, "w", encoding="utf-8") as fh:
                json.dump(plan, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["band-setup", EXAMPLE, plan_path, "-o", out,
                                       *[a.replace("DIR", d) for a in extra]]), 0)
        return [ln.replace(d, "DIR") for ln in buf.getvalue().splitlines()]

    def test_lists_each_changed_send_by_strip_marking_the_mirrors(self):
        lines = self._run({"iem_sends": [{"strip": 11, "bus": 5, "level": -16.0}]})
        self.assertEqual(lines[0], "applied plan: 4 line(s) over 4 path(s); wrote DIR/o.scn")
        self.assertEqual([ln.split('"')[0] for ln in lines[1:-1:3]], ["ch 11 ", "ch 12 "])
        body = [ln for i, ln in enumerate(lines[1:-1]) if i % 3]
        self.assertEqual([ln.split()[3] for ln in body], ["05", "06", "05", "06"])
        self.assertEqual([ln.endswith("  (mirrored)") for ln in body],
                         [False, True, True, True])
        self.assertIn("level +0.8 -> -16.0", body[0])
        self.assertEqual(lines[-1], "LOAD-TEST on the console before a gig.")

    def test_a_plan_without_mirrors_marks_nothing(self):
        lines = self._run({"channels": {"1": {"name": "Kick 2"}}})
        self.assertEqual(lines[1:3], ['ch 01 "Kick 2"',
                                      '  config             name "Kick" -> "Kick 2"'])

    def test_the_snippet_report_follows_the_list_unchanged(self):
        lines = self._run({"channels": {"1": {"eq": {"2": {"gain": 3.0}}}}},
                          "--snippet", "DIR/o.snp")
        at = lines.index("wrote DIR/o.snp: 1 lines")
        self.assertEqual(lines[at + 1:], ["  filters: EQ", "  channels: ch01",
                                          "LOAD-TEST on the console before a gig."])
        self.assertTrue(lines[at - 1].startswith("  eq 2 "))


if __name__ == "__main__":
    unittest.main()
