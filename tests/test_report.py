"""report: the per-channel snapshot as markdown, generated from the scene instead of
maintained by hand."""

import contextlib
import io
import os
import re
import unittest
from unittest import mock

from x32scene import Scene
from x32scene._views_report import cmd_report
from x32scene.cli import main
from x32scene.services.stage import load_stage

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "example-preflight.json")
STAGE = os.path.join(os.path.dirname(__file__), "..", "config", "example-stage.json")


def render(fn, *args, **kw) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kw)
    return buf.getvalue()


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = Scene.load(EXAMPLE)
        cls.out = render(cmd_report, cls.sc)

    def test_title_and_sections(self):
        self.assertTrue(self.out.startswith("# Example Rig\n"))
        for h in ("## Channels", "## Buses", "## Outputs", "## Monitor mixes", "## FX", "## Groups"):
            self.assertIn(h, self.out)

    def test_channel_row_carries_source_gain_phantom_processing_and_groups(self):
        row = next(ln for ln in self.out.splitlines() if ln.startswith("| 01 |"))
        self.assertIn("| Kick | Local input 1 | +27.0 | off |", row)
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertRegex(cells[5], r"^(off|\d+ Hz)$")     # low cut
        self.assertIn(cells[6], ("on", "off"))            # gate
        self.assertIn(cells[7], ("on", "off"))            # comp
        self.assertEqual(cells[8], "1")                   # DCA 1 Drums
        self.assertEqual(cells[9], "in")                  # in the main blend

    def test_card_sourced_channel_has_no_head_amp(self):
        row = next(ln for ln in self.out.splitlines() if ln.startswith("| 31 |"))
        self.assertIn("| DAW L | USB Card (DAW) 1 | — | — |", row)

    def test_bus_rows_name_pairs_and_fx_roles(self):
        self.assertIn("| 01 | Guitar L | 1/2 | monitor |", self.out)
        self.assertIn("| 13 | Plate | mono | FX 1 send (Plate Reverb) |", self.out)

    def test_outputs_and_matrix_and_fx_and_groups(self):
        self.assertIn("| main 09 | Bus 3 (Drums L) | POST | AES50-A 9 |", self.out)
        self.assertIn("| rec 01 | Main L | <-EQ |", self.out)
        self.assertIn("1/2 Guitar L", self.out)
        self.assertIn("| ch01 Kick |", self.out)
        self.assertIn("| 1 | Plate Reverb (PLAT) | MIX13 |", self.out)
        self.assertIn("| DCA 1 | Drums | ch01, ch02,", self.out)
        self.assertIn("| MG 5 |", self.out)

    def test_jack_count_and_sidecar_enrich_the_outputs(self):
        out = render(cmd_report, self.sc, 8, load_stage(STAGE))
        self.assertIn("| main 09 (virtual) |", out)
        self.assertIn("| main 01 (XLR) |", out)
        self.assertIn("Box A out 1 -> IEM TX 1 / Drums", out)

    def test_markdown_tables_are_well_formed(self):
        for ln in self.out.splitlines():
            if ln.startswith("|"):
                self.assertTrue(ln.endswith("|"), ln)


class ReportCliTest(unittest.TestCase):
    def test_report_command(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("X32SCENE_CONFIG", None)
            os.environ.pop("X32SCENE_STAGE", None)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["report", EXAMPLE]), 0)
            self.assertNotIn("(virtual)", buf.getvalue())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["report", EXAMPLE, "--config", CONFIG, "--stage", STAGE]), 0)
            out = buf.getvalue()
            self.assertIn("(virtual)", out)
            self.assertIn("IEM TX 1", out)
            self.assertTrue(re.search(r"^# Example Rig$", out, re.M))


if __name__ == "__main__":
    unittest.main()
