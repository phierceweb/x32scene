"""Semantic diff: naming the fields a changed line differs in, grouped by strip."""

import contextlib
import io
import os
import unittest

from x32scene import Scene
from x32scene import _views
from x32scene.services import describe as D
from x32scene.services.diff import Change, diff
from x32scene.tables import line_fields

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EXAMPLE_ALT = os.path.join(FIX, "example-alt.scn")


class LineFieldsTest(unittest.TestCase):
    def test_strip_lines(self):
        self.assertEqual(line_fields("/ch/01/config", 4), ["name", "icon", "colour", "source"])
        self.assertEqual(line_fields("/bus/01/config", 3), ["name", "icon", "colour"])
        self.assertEqual(line_fields("/ch/01/mix", 6),
                         ["on", "fader", "lr", "pan", "mono", "mono level"])
        self.assertEqual(line_fields("/main/st/mix", 3), ["on", "fader", "balance"])
        self.assertEqual(line_fields("/mtx/01/mix", 2), ["on", "fader"])
        self.assertEqual(line_fields("/ch/01/mix/09", 5), ["on", "level", "pan", "tap", "pan follow"])
        self.assertEqual(line_fields("/auxin/05/mix/10", 2), ["on", "level"])
        self.assertEqual(line_fields("/ch/01/eq/2", 4), ["type", "freq", "gain", "q"])
        self.assertEqual(line_fields("/ch/01/dyn", 15)[12], "keysrc")
        self.assertEqual(line_fields("/mtx/01/dyn", 14)[12], "mix")   # no keysrc on a matrix
        self.assertEqual(line_fields("/ch/01/preamp", 5), ["trim", "polarity", "lowcut", "slope", "lowcut freq"])
        self.assertEqual(line_fields("/ch/01/grp", 2), ["dca", "mute"])
        self.assertEqual(line_fields("/dca/1", 2), ["on", "fader"])

    def test_console_lines(self):
        self.assertEqual(line_fields("/headamp/000", 2), ["gain", "phantom"])
        self.assertEqual(line_fields("/outputs/main/09", 3), ["src", "pos", "invert"])
        self.assertEqual(line_fields("/outputs/rec/01", 2), ["src", "pos"])
        self.assertEqual(line_fields("/config/routing/AES50A", 6)[1], "block 2")
        self.assertEqual(line_fields("/config/routing", 1), ["mode"])
        self.assertEqual(line_fields("/config/userrout/in", 32)[28], "slot 29")
        self.assertEqual(line_fields("/config/buslink", 8)[5], "pair 11/12")
        self.assertEqual(line_fields("/config/linkcfg", 4), ["hadly", "eq", "dyn", "fdrmute"])
        self.assertEqual(line_fields("/config/mute", 6)[0], "group 1")
        self.assertEqual(line_fields("/fx/1", 1), ["type"])
        self.assertEqual(line_fields("/fx/1/source", 2), ["left", "right"])

    def test_unknown_line_has_no_layout(self):
        self.assertIsNone(line_fields("/config/nope", 2))
        self.assertIsNone(line_fields("/fx/1/par", 64))   # names depend on the effect type


class DescribeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = Scene.load(EXAMPLE), Scene.load(EXAMPLE_ALT)
        cls.by_path = {c.path: c for c in diff(cls.a, cls.b)}

    def test_output_change_names_the_source_with_its_label(self):
        d = D.describe(self.b, self.by_path["/outputs/main/05"])
        self.assertEqual((d.group, d.what), ("outputs", "main 05"))
        self.assertEqual(d.fields, [("src", "14 (Bus 11)", "8 (Bus 5)")])

    def test_routing_block_change_names_the_block(self):
        d = D.describe(self.b, self.by_path["/config/routing/AES50A"])
        self.assertEqual((d.group, d.what), ("routing", "AES50A"))
        self.assertEqual(d.fields, [("block 2", "OUT9-16", "UOUT9-16")])

    def test_link_change_names_the_pair(self):
        d = D.describe(self.b, self.by_path["/config/chlink"])
        self.assertEqual((d.group, d.what), ("config", "chlink"))
        self.assertEqual(d.fields, [("pair 27/28", "ON", "OFF")])

    def test_headamp_change_groups_under_the_channel_it_feeds(self):
        d = D.describe(self.b, self.by_path["/headamp/001"])   # local input 2 -> ch 02
        self.assertEqual(d.group, "/ch/02")
        self.assertEqual(d.label, 'ch 02 "Kick Sub"')
        self.assertEqual(d.what, "headamp 001")
        self.assertEqual(d.fields, [("gain", "+26.0", "+22.0")])

    def test_strip_line_change_lists_only_the_changed_fields(self):
        d = D.describe(self.b, self.by_path["/ch/07/mix"])
        self.assertEqual((d.group, d.what), ("/ch/07", "mix"))
        names = [f[0] for f in d.fields]
        self.assertTrue(names and set(names) <= {"on", "fader", "lr", "pan", "mono", "mono level"}, names)

    def test_send_change_names_the_bus(self):
        b = Scene.load(EXAMPLE)
        b.get("/ch/23/mix/09").set_arg(1, "-11.0")
        d = D.describe(b, diff(self.a, b)[0])
        self.assertEqual((d.group, d.label, d.what), ("/ch/23", 'ch 23 "Vox 1"', "send -> bus 09"))
        self.assertEqual(d.fields, [("level", "0.0", "-11.0")])

    def test_fx_param_change_uses_the_effect_map(self):
        b = Scene.load(EXAMPLE)
        b.get("/fx/1/par").set_arg(1, "3.50")
        d = D.describe(b, diff(self.a, b)[0])
        self.assertEqual((d.group, d.what), ("fx", "fx 1 params"))
        self.assertEqual(d.fields, [("Decay", "2.11", "3.50")])

    def test_fx_type_change_is_labelled(self):
        b = Scene.load(EXAMPLE)
        b.get("/fx/1").set_arg(0, "HALL")
        d = D.describe(b, {c.path: c for c in diff(self.a, b)}["/fx/1"])
        self.assertEqual(d.fields, [("type", "PLAT (Plate Reverb)", "HALL (Hall Reverb)")])

    def test_removed_and_added_lines_carry_a_note(self):
        d = D.describe(self.b, Change("/fx/1", "/fx/1 PLAT", None))
        self.assertEqual((d.note, d.fields), ("removed", []))
        d = D.describe(self.b, Change("/fx/1", None, "/fx/1 PLAT"))
        self.assertEqual(d.note, "added")

    def test_field_count_change_is_noted(self):
        d = D.describe(self.b, Change("/ch/01/mix/02", "/ch/01/mix/02 ON  +2.8",
                                       "/ch/01/mix/02 ON  +2.8 +0 PRE 0"))
        self.assertIn("2 -> 5 field(s)", d.note)

    def test_unknown_layout_falls_back_to_field_numbers(self):
        d = D.describe(self.b, Change("/config/nope", "/config/nope 0 0", "/config/nope 0 1"))
        self.assertEqual(d.fields, [("field 2", "0", "1")])

    def test_describe_all_orders_strips_before_console_sections(self):
        groups = [d.group for d in D.describe_all(self.b, diff(self.a, self.b))]
        first_console = next(i for i, g in enumerate(groups) if not g.startswith("/"))
        self.assertTrue(all(g.startswith("/") for g in groups[:first_console]))
        self.assertLess(groups.index("/ch/02"), groups.index("outputs"))


class DiffByStripViewTest(unittest.TestCase):
    def test_view_groups_by_strip_and_names_fields(self):
        a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE_ALT)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _views.cmd_diff_by_strip(a, b)
        out = buf.getvalue()
        self.assertIn('ch 02 "Kick Sub"', out)
        self.assertIn("gain +26.0 -> +22.0", out)
        self.assertIn("block 2 OUT9-16 -> UOUT9-16", out)

    def test_cli_flag_and_json_fields(self):
        import json
        from x32scene.cli import main
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["diff", EXAMPLE, EXAMPLE_ALT, "--by-strip"]), 0)
        self.assertIn('ch 02 "Kick Sub"', buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["diff", EXAMPLE, EXAMPLE_ALT, "--json"]), 0)
        doc = json.loads(buf.getvalue())
        c = next(c for c in doc["changes"] if c["path"] == "/outputs/main/05")
        self.assertEqual(c["group"], "outputs")
        self.assertEqual(c["fields"], [{"name": "src", "before": "14 (Bus 11)", "after": "8 (Bus 5)"}])


if __name__ == "__main__":
    unittest.main()
