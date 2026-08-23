"""snippets: the a->b delta as a .snp with filter masks derived from its body."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.model import HEADER_WIDTH, Line
from x32scene.services.snippets import (
    SnippetHeader, classify, make_snippet, read_header, snippet_lines,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EXAMPLE_ALT = os.path.join(FIX, "example-alt.scn")
SNP = os.path.join(FIX, "example.snp")


class HeaderTest(unittest.TestCase):
    def test_fixture_header_reads_back(self):
        with open(SNP, encoding="utf-8") as fh:
            h = read_header(fh.read())
        self.assertEqual(h, SnippetHeader("Example EQ", 4, 1, 0, 0))
        self.assertEqual(h.describe(), {"name": "Example EQ", "filters": ["EQ"],
                                        "channels": ["ch01"], "auxbuses": [], "maingrps": []})

    def test_line_is_padded_and_signed(self):
        h = SnippetHeader("all", (1 << 27) - 1, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF)
        self.assertEqual(h.line().rstrip(), '#4.0# "all" 134217727 -1 -1 65535 1')
        self.assertEqual(len(h.line()), HEADER_WIDTH)
        self.assertEqual(read_header(h.line()), h)

    def test_mask_names_cover_every_strip_family(self):
        h = SnippetHeader("x", 0, 1 << 31, 1 | 1 << 8 | 1 << 16, 1 | 1 << 6 | 1 << 7 | 1 << 8)
        d = h.describe()
        self.assertEqual(d["channels"], ["ch32"])
        self.assertEqual(d["auxbuses"], ["auxin01", "fxrtn01", "bus01"])
        self.assertEqual(d["maingrps"], ["mtx01", "main/st", "main/m", "dca01"])

    def test_scene_header_is_not_a_snippet(self):
        self.assertIsNone(read_header('#4.0# "Rig" "" %000000000 1'))


class ClassifyTest(unittest.TestCase):
    def test_strip_paths(self):
        self.assertEqual(classify("/ch/03/eq/2"), (2, "channels", 2))
        self.assertEqual(classify("/ch/01/mix/fader"), (6, "channels", 0))
        self.assertEqual(classify("/ch/01/mix/on"), (7, "channels", 0))
        self.assertEqual(classify("/ch/01/mix/09"), (9, "channels", 0))
        self.assertEqual(classify("/ch/01/mix/13"), (10, "channels", 0))
        self.assertEqual(classify("/ch/01/mix/st"), (11, "channels", 0))
        self.assertEqual(classify("/bus/01/mix/03"), (12, "auxbuses", 16))
        self.assertEqual(classify("/auxin/02/preamp"), (0, "auxbuses", 1))
        self.assertEqual(classify("/fxrtn/08/grp"), (5, "auxbuses", 15))
        self.assertEqual(classify("/mtx/06/dyn"), (3, "maingrps", 5))
        self.assertEqual(classify("/main/st/mix/pan"), (6, "maingrps", 6))
        self.assertEqual(classify("/main/m/mix/on"), (7, "maingrps", 7))
        self.assertEqual(classify("/dca/8/fader"), (6, "maingrps", 15))
        self.assertEqual(classify("/dca/1/config"), (1, "maingrps", 8))

    def test_global_paths(self):
        self.assertEqual(classify("/headamp/000"), (0, None, None))
        self.assertEqual(classify("/fx/3/par"), (15, None, None))
        self.assertEqual(classify("/config/solo"), (21, None, None))
        self.assertEqual(classify("/config/talk/A"), (22, None, None))
        self.assertEqual(classify("/config/routing/IN/1-8"), (23, None, None))
        self.assertEqual(classify("/outputs/main/05"), (24, None, None))
        self.assertEqual(classify("/config/userrout/in"), (25, None, None))
        self.assertEqual(classify("/config/userrout/out"), (26, None, None))

    def test_paths_a_snippet_cannot_carry(self):
        for p in ("/ch/01/mix", "/dca/1", "/config/chlink", "/config/mute/1",
                  "/ch/01/automix", "/outputs/rec/01", "/config/routing/IN"):
            with self.subTest(path=p):
                self.assertIsNone(classify(p))


class SplitTest(unittest.TestCase):
    def test_main_mix_line_splits_keeping_padding(self):
        ln = Line.parse("/ch/01/mix ON  +6.5 ON +0 OFF   -oo")
        self.assertEqual(snippet_lines(ln), [
            "/ch/01/mix/fader  +6.5", "/ch/01/mix/pan +0", "/ch/01/mix/on ON",
            "/ch/01/mix/st ON", "/ch/01/mix/mono OFF", "/ch/01/mix/mlevel   -oo"])

    def test_short_families(self):
        self.assertEqual(snippet_lines(Line.parse("/mtx/01/mix ON   -oo")),
                         ["/mtx/01/mix/fader   -oo", "/mtx/01/mix/on ON"])
        self.assertEqual(snippet_lines(Line.parse("/main/st/mix ON   -oo +0")),
                         ["/main/st/mix/fader   -oo", "/main/st/mix/pan +0", "/main/st/mix/on ON"])
        self.assertEqual(snippet_lines(Line.parse("/main/m/mix ON   0.0")),
                         ["/main/m/mix/fader   0.0", "/main/m/mix/on ON"])
        self.assertEqual(snippet_lines(Line.parse("/dca/1 ON   0.0")),
                         ["/dca/1/fader   0.0", "/dca/1/on ON"])

    def test_routing_banks_split_per_slot_range(self):
        ln = Line.parse("/config/routing/IN AN1-8 AN9-16 AN17-24 AN25-32 AUX1-4")
        self.assertEqual(snippet_lines(ln), [
            "/config/routing/IN/1-8 AN1-8", "/config/routing/IN/9-16 AN9-16",
            "/config/routing/IN/17-24 AN17-24", "/config/routing/IN/25-32 AN25-32",
            "/config/routing/IN/AUX AUX1-4"])
        self.assertEqual(snippet_lines(Line.parse("/config/routing/OUT OUT1-4 OUT5-8 OUT9-12 OUT13-16")),
                         ["/config/routing/OUT/1-4 OUT1-4", "/config/routing/OUT/5-8 OUT5-8",
                          "/config/routing/OUT/9-12 OUT9-12", "/config/routing/OUT/13-16 OUT13-16"])
        self.assertEqual(snippet_lines(Line.parse("/config/routing REC")),
                         ["/config/routing/routswitch REC"])

    def test_other_lines_are_verbatim(self):
        raw = "/ch/01/mix/01 ON   -oo +0 POST"
        self.assertEqual(snippet_lines(Line.parse(raw)), [raw])


class MakeSnippetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = Scene.load(EXAMPLE), Scene.load(EXAMPLE_ALT)
        cls.snip = make_snippet(cls.a, cls.b, "delta")

    def test_body_is_the_delta_and_round_trips(self):
        text = self.snip.scene.dump()
        self.assertEqual(Scene.parse(text).dump(), text)
        self.assertTrue(text.startswith('#4.0# "delta" '))
        body = {ln.path for ln in self.snip.scene.lines[1:]}
        self.assertIn("/outputs/main/05", body)
        self.assertNotIn("/ch/01/mix", body)  # combined line never appears as such

    def test_masks_follow_the_body(self):
        h = self.snip.header
        self.assertTrue(h.eventtyp & 1 << 24)  # an output moved
        d = h.describe()
        self.assertIn("Out Patch", d["filters"])
        for mask in ("channels", "auxbuses", "maingrps"):
            for label in d[mask]:
                fam = label.rstrip("0123456789")
                self.assertTrue(any(p.startswith(f"/{fam}/") for p in
                                    (ln.path for ln in self.snip.scene.lines[1:])), label)

    def test_a_retitle_is_neither_written_nor_reported(self):
        c = Scene.load(EXAMPLE)
        c.lines[0].args[0] = '"Other"'
        c.lines[0].rebuild()
        snip = make_snippet(self.a, c, "x")
        self.assertEqual((len(snip.scene.lines), snip.skipped), (1, []))

    def test_removed_lines_are_reported_not_written(self):
        c = Scene.load(EXAMPLE)
        c.lines = [ln for ln in c.lines if ln.path != "/fx/1"]
        c._reindex()
        snip = make_snippet(self.a, c, "x")
        self.assertEqual(snip.skipped, ["/fx/1"])
        self.assertEqual(len(snip.scene.lines), 1)

    def test_a_changed_main_mix_line_becomes_split_lines_with_one_channel_bit(self):
        c = Scene.load(EXAMPLE)
        ln = c.get("/ch/02/mix")
        ln.args[1] = "-3.0"
        ln.rebuild()
        c._reindex()
        snip = make_snippet(self.a, c, "x")
        self.assertEqual([ln.raw for ln in snip.scene.lines[1:]], ["/ch/02/mix/fader -3.0"])
        self.assertEqual(snip.header.channels, 1 << 1)
        self.assertEqual(snip.header.describe()["filters"], ["Fader, Pan"])


class SnippetEditCliTest(unittest.TestCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def test_edits_applied_in_memory_become_a_narrow_snippet(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "night.snp")
            code, text = self._run("snippet", EXAMPLE, "-o", out,
                                   "--edit", "set-eq 5 2 --freq 100 --gain 6",
                                   "--edit", "set-fader 5 -3",
                                   "--edit", "set-comp /bus/01 --thr -18 --ratio 3")
            self.assertEqual(code, 0)
            self.assertIn("set 5 EQ band 2", text)
            self.assertIn("mirrored to /bus/02", text)
            self.assertIn("filters: EQ, Gate & Comp, Fader, Pan", text)
            with open(out, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
            self.assertEqual(sorted(ln.split(" ")[0] for ln in lines[1:] if ln),
                             ["/bus/01/dyn", "/bus/02/dyn", "/ch/05/eq/2", "/ch/05/mix/fader"])
            self.assertEqual(read_header(lines[0]).describe()["auxbuses"], ["bus01", "bus02"])
            self.assertTrue(os.path.exists(EXAMPLE))  # the scene itself is untouched

    def test_edit_errors_are_input_errors(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "x.snp")
            for edit in ("set-eq 5 2 --gain", "extract-preset 5", "set-fader 5 -3 -o y.scn",
                         "frobnicate 5"):
                with self.subTest(edit=edit):
                    code, _ = self._run("snippet", EXAMPLE, "-o", out, "--edit", edit)
                    self.assertNotEqual(code, 0)
                    self.assertFalse(os.path.exists(out))
            code, _ = self._run("snippet", EXAMPLE, EXAMPLE_ALT, "-o", out, "--edit", "set-fader 5 -3")
            self.assertNotEqual(code, 0)   # --edit takes exactly one scene
            code, _ = self._run("snippet", EXAMPLE, "-o", out)
            self.assertNotEqual(code, 0)   # a delta takes two


class SnippetCliTest(unittest.TestCase):
    def test_snippet_command_writes_and_summarizes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "night.snp")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["snippet", EXAMPLE, EXAMPLE_ALT, "-o", out]), 0)
            self.assertIn(f"wrote {out}", buf.getvalue())
            self.assertIn("filters:", buf.getvalue())
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(read_header(fh.read()).name, "night")

    def test_snippet_refuses_overwrite_and_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "x.snp")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(main(["snippet", EXAMPLE, EXAMPLE, "-o", out]), 0)
                self.assertFalse(os.path.exists(out))
                self.assertNotEqual(main(["snippet", EXAMPLE, EXAMPLE_ALT, "-o", EXAMPLE]), 0)


if __name__ == "__main__":
    unittest.main()
