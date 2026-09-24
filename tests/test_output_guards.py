"""Every file a command writes is checked before anything is read or written."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene._parsers import _build_parser
from x32scene.cli import main

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
SECONDARY = {"band-setup": "--snippet", "watch": "--snippet", "preflight": "--regenerate"}


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def _subparsers():
    sub = next(a for a in _build_parser(None)._actions if hasattr(a, "_name_parser_map"))
    return sub.choices


def _filler(action, missing: str) -> str:
    if action.choices:
        return str(next(iter(action.choices)))
    kind = getattr(action.type, "__name__", "")
    if kind in ("_move_arg", "_strip_move_arg"):
        return "1:2"
    if kind in ("int", "float", "_strip_arg"):
        return "1"
    return missing


def _argv(name, sp, missing: str) -> list[str]:
    """The command with every required argument filled, each input naming a missing file."""
    argv = [name]
    for action in sp._actions:
        if not action.option_strings and action.nargs != "?":
            argv.append(_filler(action, missing))
        elif action.required and "--out" not in action.option_strings:
            argv += [action.option_strings[-1], _filler(action, missing)]
    if "--ip" in sp._option_string_actions:
        argv += ["--ip", "127.0.0.1", "--timeout", "0.01"]
    return argv


class EveryOutputIsCheckedFirstTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.missing = os.path.join(self.dir, "not-there.scn")
        self.nodir = os.path.join(self.dir, "nodir")

    def _refused(self, argv, flag):
        rc, out, err = _run(argv)
        self.assertEqual(rc, 1, err)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn(f"{flag} ", err)
        self.assertIn("no directory", err)
        self.assertEqual(os.listdir(self.dir), [])

    def test_every_out_file_before_its_inputs_are_read(self):
        for name, sp in _subparsers().items():
            if "--out" not in sp._option_string_actions:
                continue
            with self.subTest(cmd=name):
                argv = _argv(name, sp, self.missing)
                self._refused([*argv, "-o", os.path.join(self.nodir, "out.x")], "-o")

    def test_every_second_output_file(self):
        subs = _subparsers()
        for name, flag in SECONDARY.items():
            with self.subTest(cmd=name):
                argv = _argv(name, subs[name], self.missing)
                if "--out" in subs[name]._option_string_actions:
                    argv += ["-o", os.path.join(self.dir, "out.scn")]
                self._refused([*argv, flag, os.path.join(self.nodir, "out.x")], flag)


class OutputListTest(unittest.TestCase):
    def test_every_out_flag_beside_o_is_one_the_dispatch_check_knows(self):
        from x32scene._cli_outputs import _SECOND_OUTPUT
        named = {(name, action.dest) for name, sp in _subparsers().items()
                 for action in sp._actions
                 if action.dest != "out" and str(action.metavar or "").startswith("OUT")}
        self.assertEqual(named, set(_SECOND_OUTPUT.items()))


class BandSetupSnippetTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.plan = os.path.join(self.dir, "plan.json")
        with open(self.plan, "w", encoding="utf-8") as fh:
            fh.write('{"title": "New Band"}')
        self.out = os.path.join(self.dir, "out.scn")

    def _band_setup(self, snippet, *extra):
        return _run(["band-setup", SCENE, self.plan, "-o", self.out, "--snippet", snippet,
                     *extra])

    def _refused(self, snippet):
        before = sorted(os.listdir(self.dir))
        rc, out, err = self._band_setup(snippet)
        self.assertEqual(rc, 1, err)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertEqual(sorted(os.listdir(self.dir)), before)
        return err

    def test_a_missing_folder_writes_nothing(self):
        err = self._refused(os.path.join(self.dir, "nope", "out.snp"))
        self.assertIn("--snippet", err)
        self.assertIn("no directory", err)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes anywhere")
    def test_an_unwritable_folder_writes_nothing(self):
        locked = os.path.join(self.dir, "locked")
        os.makedirs(locked)
        os.chmod(locked, 0o555)
        self.addCleanup(os.chmod, locked, 0o700)
        err = self._refused(os.path.join(locked, "out.snp"))
        self.assertIn("--snippet", err)
        self.assertIn("not writable", err)
        self.assertEqual(os.listdir(locked), [])

    def test_an_existing_snippet_without_force_writes_nothing(self):
        snp = os.path.join(self.dir, "old.snp")
        with open(snp, "w", encoding="utf-8") as fh:
            fh.write("keep me\n")
        self.assertIn("already exists", self._refused(snp))
        with open(snp, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep me\n")

    def test_a_snippet_on_the_scene_names_its_own_flag(self):
        rc, _, err = self._band_setup(self.out)
        self.assertEqual(rc, 1)
        self.assertIn(f"--snippet {self.out} would overwrite", err)
        self.assertFalse(os.path.exists(self.out))

    def test_both_files_are_written_into_a_folder_that_is_there(self):
        with open(self.plan, "w", encoding="utf-8") as fh:
            fh.write('{"channels": {"1": {"name": "Floor Tom"}}}')
        snp = os.path.join(self.dir, "out.snp")
        rc, _, err = self._band_setup(snp)
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.isfile(self.out))
        self.assertTrue(os.path.isfile(snp))


class PlaceholderTest(unittest.TestCase):
    def test_snippet_edit_is_not_refused_for_its_internal_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "fader.snp")
            rc, _, err = _run(["snippet", SCENE, "--edit", "set-fader 1 -3", "-o", out])
            self.assertEqual(rc, 0, err)
            self.assertTrue(os.path.isfile(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
