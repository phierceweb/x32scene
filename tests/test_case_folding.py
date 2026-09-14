"""Every word-choice argument accepts either case, lists its canonical spellings in --help and
refuses quoting what was typed."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene._parsers import _build_parser
from x32scene.cli import main

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(argv)
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def _word_choices():
    sub = next(a for a in _build_parser(None)._actions if hasattr(a, "_name_parser_map"))
    for name, parser in sub._name_parser_map.items():
        for action in parser._actions:
            if action.choices and all(isinstance(c, str) for c in action.choices):
                yield name, action


class CaseFoldingTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def _same_file(self, canonical, typed):
        outs = []
        for i, argv in enumerate((canonical, typed)):
            out = os.path.join(self.dir, f"{i}.out")
            rc, _, err = _run([*argv, "-o", out, "--force"])
            self.assertEqual(rc, 0, f"{argv}: {err}")
            with open(out, "rb") as fh:
                outs.append(fh.read())
        self.assertEqual(outs[0], outs[1])

    def test_every_word_choice_takes_either_case_and_gives_the_canonical_spelling(self):
        seen = set()
        for name, action in _word_choices():
            for choice in action.choices:
                with self.subTest(cmd=name, arg=action.dest, choice=choice):
                    self.assertIsNotNone(action.type, "no case-folding type")
                    for typed in (choice.swapcase(), choice.upper(), choice.lower()):
                        self.assertEqual(action.type(typed), choice)
            seen.add((name, action.dest))
        for expected in (("set-mute", "state"), ("set-output", "invert"), ("set-output", "bank"),
                         ("set-routing", "key"), ("apply-routing", "bank"), ("ports", "bank"),
                         ("vocab", "what"), ("meters", "what"), ("extract-preset", "scope")):
            self.assertIn(expected, seen)

    def test_edits_written_from_either_case_are_identical(self):
        rou = os.path.join(self.dir, "r.rou")
        self.assertEqual(_run(["extract-routing", SCENE, "-o", rou])[0], 0)
        for canonical, typed in (
                (["set-mute", SCENE, "/ch/01", "on"], ["set-mute", SCENE, "/ch/01", "ON"]),
                (["set-output", SCENE, "aux", "1", "--invert", "on", "--pos", "PRE"],
                 ["set-output", SCENE, "AUX", "1", "--invert", "On", "--pos", "pre"]),
                (["set-routing", SCENE, "IN", "1-8=A1-8"], ["set-routing", SCENE, "in", "1-8=A1-8"]),
                (["set-routing", SCENE, "switch", "PLAY"], ["set-routing", SCENE, "SWITCH", "play"]),
                (["apply-routing", SCENE, rou, "--bank", "CARD"],
                 ["apply-routing", SCENE, rou, "--bank", "card"])):
            with self.subTest(cmd=typed):
                self._same_file(canonical, typed)

    def test_the_summary_names_the_spelling_written(self):
        rc, out, err = _run(["set-routing", SCENE, "switch", "play", "-o",
                             os.path.join(self.dir, "s.scn")])
        self.assertEqual(rc, 0, err)
        self.assertIn("routing switch PLAY;", out)

    def test_views_read_either_case(self):
        for canonical, typed in ((["vocab", "routing", "IN"], ["vocab", "Routing", "in"]),
                                 (["ports", SCENE, "--bank", "aux"], ["ports", SCENE, "--bank", "AUX"])):
            with self.subTest(cmd=typed):
                self.assertEqual(_run(canonical)[:2], _run(typed)[:2])

    def test_help_lists_canonical_spellings_and_a_refusal_quotes_what_was_typed(self):
        rc, out, _ = _run(["set-mute", "--help"])
        self.assertIn("{on,off}", out)
        rc, _, err = _run(["set-mute", SCENE, "/ch/01", "Onn", "-o", os.path.join(self.dir, "x")])
        self.assertEqual(rc, 2)
        self.assertIn("invalid choice: 'Onn' (choose from on, off)", err)
        rc, _, err = _run(["set-routing", SCENE, "switch", "Rex", "-o", os.path.join(self.dir, "x")])
        self.assertEqual(rc, 1)
        self.assertIn("'Rex'", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
