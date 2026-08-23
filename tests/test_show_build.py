"""show-build: cues parsed from words, the index written in X32-Edit's shape, companions
copied verbatim, and the reader decoding what the writer wrote."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene.cli import main
from x32scene.services.show import Cue, build_show, parse_cue, read_show

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
SNP = os.path.join(FIX, "example.snp")


def _read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


class CueTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(Cue("1").numb(), 100)
        self.assertEqual(Cue("1.2").numb(), 120)
        self.assertEqual(Cue("12.3.4").numb(), 1234)
        self.assertEqual(Cue("500").numb(), 50000)
        for bad in ("1.10", "501", "a", "1.2.3.4"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    Cue(bad).numb()

    def test_parse_words(self):
        c = parse_cue("1.5 Encore bows scene=2 snippet=0 skip")
        self.assertEqual((c.number, c.name, c.scene, c.snippet, c.skip),
                         ("1.5", "Encore bows", 2, 0, True))
        self.assertEqual(c.line(3), 'cue/003 150 "Encore bows" 1 2 0 0 1 0 0')
        self.assertEqual(parse_cue("2").line(0), 'cue/000 200 "" 0 -1 -1 0 1 0 0')
        with self.assertRaises(ValueError):
            parse_cue("1 x scene=100")
        with self.assertRaises(ValueError):
            parse_cue("")


class BuildTest(unittest.TestCase):
    def test_index_and_companions(self):
        files = build_show("Night", [(EXAMPLE, _read(EXAMPLE))], [(SNP, _read(SNP))],
                           [parse_cue("1 Opener scene=0"), parse_cue("2 Encore snippet=0 skip")])
        self.assertEqual(set(files), {"Night.shw", "Night.000.scn", "Night.000.snp"})
        self.assertEqual(files["Night.000.scn"], _read(EXAMPLE))
        self.assertEqual(files["Night.000.snp"], _read(SNP))
        lines = files["Night.shw"].split("\n")
        self.assertEqual(lines[0], "#4.0#")
        self.assertEqual(lines[1], 'show "Night" 0 0 0 0 0 0 0 0 0 0 "x32scene"')
        self.assertEqual(lines[2], 'cue/000 100 "Opener" 0 0 -1 0 1 0 0')
        self.assertEqual(lines[3], 'cue/001 200 "Encore" 1 -1 0 0 1 0 0')
        self.assertEqual(lines[4], 'scene/000 "Example Rig" "" %000000000 1')
        self.assertEqual(lines[5], 'snippet/000 "Example EQ" 4 1 0 0 1')
        show = read_show(files["Night.shw"])
        self.assertEqual([e.decoded["scene"] for e in show.of("cue")], [0, None])
        self.assertEqual(show.of("cue")[1].decoded, {"name": "Encore", "number": "2.0.0",
                                                     "skip": True, "scene": None, "snippet": 0})

    def test_refuses_dangling_links_and_wrong_files(self):
        with self.assertRaises(ValueError):
            build_show("N", [], [], [parse_cue("1 x scene=0")])
        with self.assertRaises(ValueError):
            build_show("N", [(SNP, _read(SNP))], [], [])    # a snippet is not a scene
        with self.assertRaises(ValueError):
            build_show("N", [], [(EXAMPLE, _read(EXAMPLE))], [])


class ShowBuildCliTest(unittest.TestCase):
    def test_writes_a_directory_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "show")
            argv = ["show-build", "-o", out, "--name", "Night", "--scene", EXAMPLE,
                    "--snippet", SNP, "--cue", "1 Opener scene=0 snippet=0"]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(argv), 0)
            self.assertIn("wrote Night.shw with 1 cue(s)", buf.getvalue())
            self.assertEqual(sorted(os.listdir(out)), ["Night.000.scn", "Night.000.snp", "Night.shw"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(main(argv), 0)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["show", os.path.join(out, "Night.shw")]), 0)
            self.assertIn("cue/000  1.0.0 Opener   [scene 0, snippet 0]", buf.getvalue())

    def test_bad_cue_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "show")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(main(["show-build", "-o", out, "--name", "N",
                                          "--cue", "1 x scene=3"]), 0)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
