"""The two guards that keep an edit command from doing damage or going unfindable:
refusing to write over a file that is already there, and every subcommand appearing in
`--help`."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


class OverwriteGuardTest(unittest.TestCase):
    """An edit command may not destroy a file already on disk without --force."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = os.path.join(self.dir, "out.scn")

    def _edit(self, *extra):
        return main(["set-fader", SCENE, "/ch/01", "-3.0", "-o", self.out, *extra])

    def test_writes_when_the_target_is_free(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self._edit(), 0)
        self.assertTrue(os.path.exists(self.out))

    def test_refuses_an_existing_file(self):
        with open(self.out, "w") as fh:
            fh.write("do not destroy me\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self._edit(), 1)
        self.assertIn("already exists", err.getvalue())
        self.assertIn("--force", err.getvalue())
        with open(self.out) as fh:
            self.assertEqual(fh.read(), "do not destroy me\n")   # untouched

    def test_force_overwrites(self):
        with open(self.out, "w") as fh:
            fh.write("replace me\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self._edit("--force"), 0)
        self.assertEqual(Scene.load(self.out).name, "Example Rig")

    def test_a_dangling_symlink_still_counts_as_taken(self):
        os.symlink(os.path.join(self.dir, "gone.scn"), self.out)
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self._edit(), 1)

    def test_force_never_unlocks_an_input(self):
        scene_copy = os.path.join(self.dir, "in.scn")
        shutil.copy(SCENE, scene_copy)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = main(["set-fader", scene_copy, "/ch/01", "-3.0", "-o", scene_copy, "--force"])
        self.assertEqual(rc, 1)
        self.assertIn("would overwrite the input", err.getvalue())

    def test_every_writer_offers_force(self):
        """A new output-writing subcommand must not ship without the guard's flag."""
        from x32scene._parsers import _build_parser
        sub = next(a for a in _build_parser(None)._actions if hasattr(a, "_name_parser_map"))
        for name, sp in sub.choices.items():
            opts = {o for a in sp._actions for o in a.option_strings}
            if "--out" in opts or (name == "show-build" and "--dir" in opts):
                with self.subTest(cmd=name):
                    self.assertIn("--force", opts)


class HelpCoverageTest(unittest.TestCase):
    def test_every_subcommand_is_listed_in_help(self):
        """argparse omits a subparser that carries no help=, leaving the command
        undiscoverable from the CLI while still working."""
        from x32scene._parsers import _build_parser
        sub = next(a for a in _build_parser(None)._actions if hasattr(a, "_name_parser_map"))
        listed = {a.dest for a in sub._choices_actions}
        self.assertEqual(sorted(set(sub.choices) - listed), [])


class InputsTheGuardCannotSeeTest(unittest.TestCase):
    """An input is not always an argument: a band-setup plan names presets it reads, a
    `snippet --edit` names one inside its edit string, and show-build writes into the
    same layout it reads from."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        shutil.copy(SCENE, os.path.join(self.dir, "template.scn"))
        self.template = os.path.join(self.dir, "template.scn")
        self.preset = os.path.join(self.dir, "kick.chn")
        with contextlib.redirect_stdout(io.StringIO()):
            main(["extract-preset", self.template, "1", "-o", self.preset])
        self.before = open(self.preset, "rb").read()

    def _refused(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = main(argv)
        self.assertEqual(rc, 1)
        self.assertIn("would overwrite the input", err.getvalue())
        self.assertEqual(open(self.preset, "rb").read(), self.before)

    def _plan(self):
        path = os.path.join(self.dir, "plan.json")
        with open(path, "w") as fh:
            fh.write('{"title": "New Band", "channels": {"3": {"preset": "kick.chn"}}}')
        return path

    def test_band_setup_force_cannot_land_on_a_preset_the_plan_reads(self):
        self._refused(["band-setup", self.template, self._plan(), "-o", self.preset, "--force"])

    def test_band_setup_snippet_cannot_land_on_it_either(self):
        out = os.path.join(self.dir, "out.scn")
        self._refused(["band-setup", self.template, self._plan(), "-o", out,
                       "--snippet", self.preset, "--force"])

    def test_snippet_edit_force_cannot_land_on_the_preset_it_loads(self):
        self._refused(["snippet", self.template, "--edit", f"apply-preset 3 {self.preset}",
                       "-o", self.preset, "--force"])

    def test_show_build_force_cannot_land_on_one_of_its_own_scenes(self):
        show = os.path.join(self.dir, "show")
        os.makedirs(show)
        slot = os.path.join(show, "Gig.000.scn")
        shutil.copy(SCENE, slot)
        before = open(slot, "rb").read()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = main(["show-build", "-o", show, "--name", "Gig",
                       "--scene", self.template, "--scene", slot, "--force"])
        self.assertEqual(rc, 1)
        self.assertIn("would overwrite the input", err.getvalue())
        self.assertEqual(open(slot, "rb").read(), before)

    def test_band_setup_checks_the_template_shape(self):
        """band-setup writes a gig scene, so its template is checked like any other."""
        broken = os.path.join(self.dir, "broken.scn")
        shutil.copy(os.path.join(os.path.dirname(__file__), "fixtures", "broken",
                                 "truncated.scn"), broken)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            main(["band-setup", broken, self._plan(), "-o", os.path.join(self.dir, "o.scn")])
        self.assertIn("warning:", err.getvalue())
