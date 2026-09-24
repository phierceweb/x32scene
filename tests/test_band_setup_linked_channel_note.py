"""band-setup says when a channel preset leaves a stereo-linked pair's processing unequal: its
partner gets no preset or another one, as apply-preset says for a single channel."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.orchestrators.band_swap import build

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIX, "example.scn")
CHN = os.path.join(FIX, "example.chn")   # processing and sends


class LinkedChannelNoteTest(unittest.TestCase):
    def _partners(self, channels: dict) -> dict:
        return build(SCENE, {"channels": channels})[1]["preset_partners"]

    def test_a_preset_on_one_side_names_the_partner(self):
        self.assertEqual(self._partners({"11": {"preset": CHN}}), {11: 12})

    def test_the_even_side_names_the_odd_one(self):
        self.assertEqual(self._partners({"12": {"preset": CHN}}), {12: 11})

    def test_the_same_preset_on_both_sides_is_no_note(self):
        self.assertEqual(self._partners({"11": {"preset": CHN}, "12": {"preset": CHN}}), {})

    def test_other_scopes_on_the_partner_are_one_note_per_pair(self):
        self.assertEqual(self._partners({"11": {"preset": CHN},
                                         "12": {"preset": CHN, "scopes": ["eq"]}}), {11: 12})

    def test_a_sends_only_preset_is_no_note(self):
        self.assertEqual(self._partners({"11": {"preset": CHN, "scopes": ["sends"]}}), {})

    def test_an_unlinked_channel_is_no_note(self):
        self.assertEqual(self._partners({"3": {"preset": CHN}}), {})

    def test_the_cli_prints_the_note(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        plan = os.path.join(d, "plan.json")
        with open(plan, "w", encoding="utf-8") as fh:
            fh.write('{"channels": {"11": {"preset": "%s"}}}' % CHN)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = main(["band-setup", SCENE, plan, "-o", os.path.join(d, "o.scn")])
        self.assertEqual(rc, 0)
        self.assertIn("ch11 preset: the stereo-linked ch12 is not given the same preset, so "
                      "it keeps its own processing: a load that reconciles the pair can end at "
                      "ch12's", out.getvalue())


if __name__ == "__main__":
    unittest.main()
