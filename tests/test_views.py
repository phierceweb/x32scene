"""View rendering: the read-only commands are the tool's answer surface, so assert what
they print, not just that they exit 0."""

import contextlib
import io
import os
import unittest

from x32scene import Scene
from x32scene import _views
from x32scene.services.diff import Change, diff

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")


def render(fn, *args) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


class ViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = Scene.load(EXAMPLE)

    def test_info_reports_title_and_channel_names(self):
        out = render(_views.cmd_info, self.sc)
        self.assertIn("Example Rig", out)
        self.assertIn("ch01  Kick", out)
        self.assertIn("bus01", out)

    def test_inputs_resolves_physical_sources(self):
        out = render(_views.cmd_inputs, self.sc)
        self.assertIn("ch01 Kick", out)
        self.assertIn("Local input 1", out)
        self.assertIn("AES50-A input 1", out)   # ch17 via the stage box
        self.assertIn("<- USB/DAW", out)        # card-sourced channels flagged

    def test_ports_labels_taps_and_mirrors(self):
        out = render(_views.cmd_ports, self.sc, 8)
        self.assertIn("main 01", out)
        self.assertIn("[XLR ]", out)
        self.assertIn("[virt]", out)            # outs above the declared jack count
        self.assertIn("-> stagebox", out)

    def test_ports_p16_bank_names_the_direct_outs(self):
        from x32scene._views_ports import cmd_ports
        out = render(lambda: cmd_ports(self.sc, bank="p16"))
        self.assertIn("p16 01 -> Direct Out Ch 1", out)
        self.assertIn("p16 16 -> Direct Out Ch 26", out)

    def test_ports_without_a_jack_count_labels_nothing_physical(self):
        # the console model is not in the file: no count declared, no physical/virtual claim
        out = render(_views.cmd_ports, self.sc)
        self.assertNotIn("[XLR ]", out)
        self.assertNotIn("[virt]", out)
        self.assertIn("main 09", out)

    def test_buses_shows_pairs_fx_and_tap_tally(self):
        out = render(_views.cmd_buses, self.sc)
        self.assertIn("stereo-pair", out)
        self.assertIn("Plate Reverb", out)
        self.assertIn("sends[PRE:", out)

    def test_record_map_lists_tracks_and_loopback(self):
        out = render(_views.cmd_record_map, self.sc)
        self.assertIn("track  1 <- Local input 1", out)
        self.assertIn("DAW return", out)

    def test_fx_decodes_slot_type_and_params(self):
        out = render(_views.cmd_fx, self.sc)
        self.assertIn("FX1 Plate Reverb (PLAT)", out)
        self.assertIn("<- MIX13", out)
        self.assertIn("Decay=", out)

    def test_fx_wraps_geq_band_rows_instead_of_one_long_line(self):
        out = render(_views.cmd_fx, self.sc)
        self.assertLess(max(len(ln) for ln in out.splitlines()), 200)
        self.assertIn("Master A=0.0", out)   # GEQ2's last A-side band, still present
        self.assertIn("Master=0.0", out)     # GEQ's last band

    def test_dca_lists_named_groups_with_members(self):
        out = render(_views.cmd_dca, self.sc)
        self.assertIn("DCA 1 Drums", out)
        self.assertIn("Kick", out)
        self.assertIn("MG 6", out)

    def test_explain_renders_every_output_bank(self):
        out = render(_views.cmd_explain, self.sc)
        for needle in ("aux 01", "p16 01", "aes 01", "rec 01"):
            self.assertIn(needle, out)

    def test_explain_covers_every_section(self):
        out = render(_views.cmd_explain, self.sc)
        for header in ("# INPUTS", "# BUSES", "# OUTPUTS", "# RECORD MAP", "# FX",
                       "# GROUPS"):
            self.assertIn(header, out)

    def test_iem_sorts_loud_to_quiet(self):
        out = render(_views.cmd_iem, self.sc, 1)
        levels = [float(ln.split("dB")[0]) for ln in out.splitlines()
                  if "dB" in ln]
        self.assertTrue(levels)
        self.assertEqual(levels, sorted(levels, reverse=True))


class DiffViewTest(unittest.TestCase):
    def test_diff_reports_changed_paths_with_both_sides(self):
        a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE_ALT)
        out = render(_views.cmd_diff, a, b)
        self.assertIn("changed path(s):", out)
        self.assertIn("    - ", out)
        self.assertIn("    + ", out)

    def test_diff_marks_added_and_removed_semantics(self):
        a = Scene.load(EXAMPLE)
        b = Scene.load(EXAMPLE)
        b.lines = [ln for ln in b.lines if ln.path != "/fx/1"]
        b._reindex()
        changes = {c.path: c for c in diff(a, b)}
        removed = changes["/fx/1"]
        self.assertIsNotNone(removed.before)
        self.assertIsNone(removed.after)
        added = {c.path: c for c in diff(b, a)}["/fx/1"]
        self.assertIsNone(added.before)
        self.assertIsNotNone(added.after)

    def test_diff_renders_one_sided_changes_without_none(self):
        a = Scene.load(EXAMPLE)
        b = Scene.load(EXAMPLE)
        b.lines = [ln for ln in b.lines if ln.path != "/fx/1"]
        b._reindex()
        out = render(_views.cmd_diff, a, b)
        self.assertIn("(removed)", out)
        self.assertNotIn("None", out)

    def test_identical_scenes_diff_empty(self):
        a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        self.assertEqual(diff(a, b), [])
        self.assertIn("0 changed path(s)", render(_views.cmd_diff, a, b))

    def test_change_is_a_plain_record(self):
        c = Change("/ch/01/config", "before", "after")
        self.assertEqual((c.path, c.before, c.after),
                         ("/ch/01/config", "before", "after"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
