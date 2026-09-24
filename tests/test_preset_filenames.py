"""A preset file name never lands on a Windows device name (`AUX.chn` opens the AUX device
there, not a file), and presets-diff still finds the channel it came from."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.preset_library import match_channels, preset_filename

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class ReservedNameTest(unittest.TestCase):
    def test_a_device_name_in_any_case_is_escaped(self):
        for name in ("AUX", "aux", "Con", "PRN", "nul", "COM1", "com9", "LPT1", "Lpt9"):
            with self.subTest(name=name):
                self.assertEqual(preset_filename(name), f"_{name}.chn")

    def test_trailing_dots_or_spaces_and_an_extension_do_not_hide_one(self):
        for name, want in (("AUX.", "_AUX..chn"), ("AUX ", "_AUX.chn"), ("Nul . ", "_Nul ..chn"),
                           ("CON.Vox", "_CON.Vox.chn"), ("aux .x", "_aux .x.chn")):
            with self.subTest(name=name):
                self.assertEqual(preset_filename(name), want)

    def test_names_that_only_look_like_one_are_kept(self):
        for name in ("AUX 1", "Auxiliary", "Console", "COM", "COM10", "LPT", "NULL", "Aux-L"):
            with self.subTest(name=name):
                self.assertEqual(preset_filename(name), f"{name}.chn")

    def test_the_escaped_stem_still_names_its_channel(self):
        sc = Scene.load(SCENE)
        sc.get("/ch/05/config").set_arg(0, '"Aux"')
        self.assertEqual(match_channels(sc, "_Aux", stem=True), [5])


class ExtractAllTest(unittest.TestCase):
    def test_a_channel_named_aux_round_trips_through_its_folder(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        scene, lib = os.path.join(d, "s.scn"), os.path.join(d, "lib")
        sc = Scene.load(SCENE)
        sc.get("/ch/05/config").set_arg(0, '"AUX"')
        sc.save(scene)
        rc, out, _ = _run(["extract-preset", scene, "--all", "-o", lib])
        self.assertEqual(rc, 0, out)
        self.assertIn("_AUX.chn", os.listdir(lib))
        self.assertNotIn("AUX.chn", os.listdir(lib))
        rc, out, _ = _run(["presets-diff", lib, scene])
        self.assertEqual(rc, 0, out)
        row = next(ln for ln in out.splitlines() if "_AUX.chn" in ln)
        self.assertTrue(row.startswith("MATCH"), row)
        self.assertIn("ch05", row)


if __name__ == "__main__":
    unittest.main()
