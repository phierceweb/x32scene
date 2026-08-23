"""transplant: carry a monitor mix, path patterns or channel sections from one scene into
another and touch nothing else; snippet --bus / --only keep a delta to the same."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.diff import diff
from x32scene.services.snippets import make_snippet, read_header
from x32scene.services.transplant import bus_mix_paths, glob_paths, transplant

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EXAMPLE_ALT = os.path.join(FIX, "example-alt.scn")


class PathsTest(unittest.TestCase):
    def test_bus_mix_paths_cover_both_sides_of_a_pair(self):
        sc = Scene.load(EXAMPLE)
        paths = bus_mix_paths(sc, 1)
        self.assertIn("/bus/01/config", paths)
        self.assertIn("/bus/02/config", paths)          # 1/2 are linked in the fixture
        self.assertIn("/bus/01/mix", paths)
        self.assertIn("/ch/01/mix/01", paths)
        self.assertIn("/ch/32/mix/02", paths)
        self.assertIn("/auxin/01/mix/01", paths)
        self.assertNotIn("/ch/01/mix/03", paths)
        self.assertNotIn("/outputs/main/01", paths)
        self.assertEqual(bus_mix_paths(sc, 13), bus_mix_paths(sc, 13))   # mono: itself only
        self.assertNotIn("/bus/14/config", bus_mix_paths(sc, 13))
        with self.assertRaises(ValueError):
            bus_mix_paths(sc, 17)

    def test_glob_paths(self):
        sc = Scene.load(EXAMPLE)
        self.assertEqual(glob_paths(sc, ["/headamp/00[01]"]), ["/headamp/000", "/headamp/001"])
        self.assertEqual(len(glob_paths(sc, ["/ch/03/eq/*"])), 4)
        self.assertEqual(glob_paths(sc, ["/nope/*"]), [])


class TransplantTest(unittest.TestCase):
    def setUp(self):
        self.src, self.dst = Scene.load(EXAMPLE_ALT), Scene.load(EXAMPLE)

    def test_bus_mix_moves_and_nothing_else(self):
        changed = transplant(self.src, self.dst, buses=[1])
        expected = {c.path for c in diff(Scene.load(EXAMPLE), self.dst)}
        self.assertEqual(set(changed), expected)
        self.assertTrue(changed)
        allowed = set(bus_mix_paths(self.src, 1))
        self.assertTrue(set(changed) <= allowed, set(changed) - allowed)
        for p in changed:
            self.assertEqual(self.dst.get(p).raw, self.src.get(p).raw)
        text = self.dst.dump()
        self.assertEqual(Scene.parse(text).dump(), text)

    def test_paths_and_channel_sections(self):
        self.src.get("/headamp/000").args[0] = "+29.5"
        self.src.get("/headamp/000").rebuild()
        self.src.get("/ch/03/eq/2").args[2] = "+6.00"
        self.src.get("/ch/03/eq/2").rebuild()
        changed = transplant(self.src, self.dst, globs=["/headamp/000"], channels=[3], scopes=["eq"])
        self.assertIn("/headamp/000", changed)
        self.assertIn("/ch/03/eq/2", changed)
        self.assertEqual(self.dst.get("/headamp/000").args[0], "+29.5")
        self.assertEqual(self.dst.get("/ch/03/eq/2").args[2], "+6.00")
        self.assertNotIn("/ch/03/dyn", changed)

    def test_missing_path_is_an_error_and_unchanged_lines_are_not_reported(self):
        same = self.dst.get("/config/chlink")
        self.src.get("/config/chlink").raw = same.raw    # identical line: nothing to report
        self.assertEqual(transplant(self.src, self.dst, globs=["/config/chlink"]), [])
        self.assertEqual(transplant(self.src, self.dst, globs=["/nope"]), [])   # matches nothing
        c = Scene.load(EXAMPLE)
        c.lines = [ln for ln in c.lines if ln.path != "/headamp/000"]
        c._reindex()
        with self.assertRaises(KeyError):
            transplant(self.src, c, globs=["/headamp/000"])


class SnippetFilterTest(unittest.TestCase):
    def test_only_keeps_the_delta_to_a_bus(self):
        a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE_ALT)
        keep = set(bus_mix_paths(b, 1))
        snip = make_snippet(a, b, "vox", keep.__contains__)
        body = {ln.path for ln in snip.scene.lines[1:]}
        self.assertTrue(body)
        for p in body:
            self.assertTrue(p.startswith("/bus/0") or "/mix/0" in p, p)
        for p in body:   # split sub-lines (/bus/01/mix/fader) descend from a kept path
            self.assertTrue(p in keep or p.rsplit("/", 1)[0] in keep, p)
        d = snip.header.describe()
        self.assertTrue(d["channels"])
        self.assertIn("Send 1-8", d["filters"])
        self.assertNotIn("Send 9-12", d["filters"])   # nothing outside bus 1/2's mix


class CliTest(unittest.TestCase):
    def _run(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def test_transplant_and_snippet_bus(self):
        with tempfile.TemporaryDirectory() as d:
            out, snp = os.path.join(d, "o.scn"), os.path.join(d, "o.snp")
            code, text = self._run("transplant", EXAMPLE_ALT, EXAMPLE, "-o", out, "--bus", "1",
                                   "--path", "/headamp/000")
            self.assertEqual(code, 0)
            self.assertIn("carried", text)
            self.assertTrue(os.path.exists(out))
            code, _ = self._run("transplant", EXAMPLE_ALT, EXAMPLE, "-o", out + "2")
            self.assertNotEqual(code, 0)
            code, text = self._run("snippet", EXAMPLE, EXAMPLE_ALT, "-o", snp, "--bus", "1")
            self.assertEqual(code, 0)
            with open(snp, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
            self.assertTrue(all(ln.startswith("/bus/0") or "/mix/0" in ln for ln in lines[1:] if ln))
            self.assertIsNotNone(read_header(lines[0]))
            code, text = self._run("snippet", EXAMPLE, "-o", snp + "3", "--bus", "13")
            self.assertEqual(code, 0)   # one scene + --bus: the whole mix as it is, not a delta
            with open(snp + "3", encoding="utf-8") as fh:
                body = [ln for ln in fh.read().split("\n")[1:] if ln]
            self.assertTrue(any(ln.startswith("/bus/13/config") for ln in body))
            self.assertTrue(any(ln.startswith("/ch/01/mix/13 ") for ln in body))
            code, text = self._run("snippet", EXAMPLE, EXAMPLE_ALT, "-o", snp + "2", "--only", "/outputs/*")
            self.assertEqual(code, 0)
            with open(snp + "2", encoding="utf-8") as fh:
                self.assertTrue(all(ln.startswith("/outputs/") for ln in fh.read().split("\n")[1:] if ln))


if __name__ == "__main__":
    unittest.main()
