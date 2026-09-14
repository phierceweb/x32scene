"""The swap-strips, move-strip and reorder-strips commands, and the snippet --edit that
refuses them.

Fixture facts the cases lean on: ch05 "Rack 1" and ch07 "Rack 3" are unlinked and p16 03
taps channel 5; channel pairs 11/12 and 15/16 are linked.
"""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
LOAD_TEST = "LOAD-TEST on the console before a gig."


def _run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


class StripCommandTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name

    def _out(self, name: str = "out.scn") -> str:
        return os.path.join(self.dir, name)

    def test_swap_writes_and_reports_moves_and_references(self):
        out = self._out()
        code, text, err = _run("swap-strips", EXAMPLE, "5", "7", "-o", out)
        self.assertEqual((code, err), (0, ""))
        self.assertIn('ch05 "Rack 1" -> ch07', text)
        self.assertIn('ch07 "Rack 3" -> ch05', text)
        self.assertIn("/outputs/p16/03 field 1 (src): 30 -> 32", text)
        lines = text.rstrip().splitlines()
        self.assertEqual(lines[-2:], [f"wrote {out}", LOAD_TEST])
        written = Scene.load(out)
        self.assertEqual(written.get("/ch/07/config").args[0], '"Rack 1"')
        self.assertEqual(Scene.parse(written.dump()).dump(), written.dump())

    def test_swapping_back_returns_the_original_bytes(self):
        once, twice = self._out("once.scn"), self._out("twice.scn")
        self.assertEqual(_run("swap-strips", EXAMPLE, "5", "7", "-o", once)[0], 0)
        self.assertEqual(_run("swap-strips", once, "7", "5", "-o", twice)[0], 0)
        self.assertEqual(_bytes(twice), _bytes(EXAMPLE))

    def test_move_shifts_the_strips_between(self):
        out = self._out()
        code, text, _ = _run("move-strip", EXAMPLE, "5", "--to", "8", "-o", out)
        self.assertEqual(code, 0)
        names = [Scene.load(out).get(f"/ch/{c:02d}/config").args[0] for c in (5, 6, 7, 8)]
        base = Scene.load(EXAMPLE)
        self.assertEqual(names, [base.get(f"/ch/{c:02d}/config").args[0] for c in (6, 7, 8, 5)])
        self.assertIn('ch05 "Rack 1" -> ch08', text)

    def test_move_then_the_inverse_move_returns_the_original_bytes(self):
        there, back = self._out("there.scn"), self._out("back.scn")
        self.assertEqual(_run("move-strip", EXAMPLE, "3", "--to", "9", "-o", there)[0], 0)
        self.assertEqual(_run("move-strip", there, "9", "--to", "3", "-o", back)[0], 0)
        self.assertEqual(_bytes(back), _bytes(EXAMPLE))

    def test_reorder_matches_the_same_swap(self):
        swapped, reordered = self._out("s.scn"), self._out("r.scn")
        _run("swap-strips", EXAMPLE, "5", "7", "-o", swapped)
        code, _, _ = _run("reorder-strips", EXAMPLE, "5:7", "7:5", "-o", reordered)
        self.assertEqual(code, 0)
        self.assertEqual(_bytes(reordered), _bytes(swapped))

    def test_diff_by_strip_names_both_swapped_strips(self):
        out = self._out()
        _run("swap-strips", EXAMPLE, "5", "7", "-o", out)
        code, text, _ = _run("diff", "--by-strip", EXAMPLE, out)
        self.assertEqual(code, 0)
        self.assertIn('ch 05 "Rack 3"', text)
        self.assertIn('ch 07 "Rack 1"', text)

    def test_refusals_exit_1_and_write_nothing(self):
        out = self._out()
        for argv in (["swap-strips", EXAMPLE, "11", "13"],       # splits linked 11/12
                     ["move-strip", EXAMPLE, "10", "--to", "14"],  # linked pair in the way
                     ["reorder-strips", EXAMPLE, "5:7"],           # not a permutation
                     ["reorder-strips", EXAMPLE, "5:7", "7:5", "5:6"],   # FROM twice
                     ["swap-strips", EXAMPLE, "5", "33"],
                     ["swap-strips", EXAMPLE, "5", "5"],           # nothing moves
                     ["move-strip", EXAMPLE, "4", "--to", "4"]):
            with self.subTest(argv=argv):
                code, text, err = _run(*argv, "-o", out)
                self.assertEqual(code, 1)
                self.assertEqual(text, "")
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                self.assertFalse(os.path.exists(out))

    def test_a_linked_pair_refusal_names_the_pair(self):
        err = _run("move-strip", EXAMPLE, "10", "--to", "14", "-o", self._out())[2]
        self.assertIn("11/12", err)

    def test_a_move_given_twice_is_named(self):
        err = _run("reorder-strips", EXAMPLE, "5:7", "7:5", "5:6", "-o", self._out())[2]
        self.assertIn("ch05", err)

    def test_a_malformed_move_is_an_argument_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            main(["reorder-strips", EXAMPLE, "5-7", "-o", self._out()])
        self.assertIn("FROM:TO", err.getvalue())

    def test_the_input_is_never_overwritten_and_out_needs_force(self):
        code, _, err = _run("swap-strips", EXAMPLE, "5", "7", "-o", EXAMPLE)
        self.assertEqual(code, 1)
        self.assertIn("would overwrite the input", err)
        out = self._out()
        with open(out, "w") as fh:
            fh.write("keep")
        self.assertEqual(_run("swap-strips", EXAMPLE, "5", "7", "-o", out)[0], 1)
        self.assertEqual(_bytes(out), b"keep")
        self.assertEqual(_run("swap-strips", EXAMPLE, "5", "7", "-o", out, "--force")[0], 0)

    def test_a_file_that_is_not_a_scene_is_refused(self):
        snp = self._out("example.snp")
        shutil.copy(EXAMPLE, snp)
        out = self._out()
        for argv in (["swap-strips", snp, "5", "7"], ["move-strip", snp, "5", "--to", "7"],
                     ["reorder-strips", snp, "5:7", "7:5"]):
            with self.subTest(argv=argv):
                code, _, err = _run(*argv, "-o", out)
                self.assertEqual(code, 1)
                self.assertIn(".scn", err)
                self.assertFalse(os.path.exists(out))

    def test_snippet_edit_refuses_them_and_writes_nothing(self):
        out = self._out("moved.snp")
        for edit in ("swap-strips 5 7", "move-strip 5 --to 8", "reorder-strips 5:7 7:5"):
            with self.subTest(edit=edit):
                code, text, err = _run("snippet", EXAMPLE, "-o", out, "--edit", edit)
                self.assertEqual((code, text), (1, ""))
                self.assertIn("/config/chlink", err)
                self.assertIn(edit.split()[0], err)
                self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
