"""A preset with CR line endings is refused on every path that applies one, as a scene is:
an X32 file is LF-only, and normalizing one silently would hide a file the desk never wrote."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.orchestrators.band_swap import _preset_text
from x32scene.services.presets import apply_preset

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
CHN = os.path.join(os.path.dirname(__file__), "fixtures", "example.chn")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class CrlfPresetTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        with open(CHN, "rb") as fh:
            lf = fh.read().replace(b'"Kick"', b'"Snare"')
        self.crlf = os.path.join(self.dir, "crlf.chn")
        with open(self.crlf, "wb") as fh:
            fh.write(lf.replace(b"\n", b"\r\n"))
        self.out = os.path.join(self.dir, "out.scn")

    def test_apply_preset_refuses_cr_and_leaves_the_scene_alone(self):
        sc = Scene.load(SCENE)
        before = sc.dump()
        with open(self.crlf, encoding="utf-8", newline="") as fh:
            text = fh.read()
        with self.assertRaisesRegex(ValueError, "CR"):
            apply_preset(sc, 2, text)
        self.assertEqual(sc.dump(), before)

    def test_the_cli_writes_nothing(self):
        rc, _, err = _run(["apply-preset", SCENE, "2", self.crlf, "-o", self.out])
        self.assertEqual(rc, 1)
        self.assertIn("CR", err)
        self.assertFalse(os.path.exists(self.out))

    def test_a_plan_preset_is_read_verbatim_and_refused(self):
        with self.assertRaisesRegex(ValueError, "crlf.chn: CR line endings"):
            _preset_text({"_dir": self.dir}, {"preset": "crlf.chn"})

    def test_a_plan_preset_with_cr_is_a_plan_error_naming_it(self):
        plan = os.path.join(self.dir, "plan.json")
        with open(plan, "w", encoding="utf-8") as fh:
            json.dump({"channels": {"2": {"preset": "crlf.chn"}}}, fh)
        rc, _, err = _run(["band-setup", SCENE, plan, "-o", self.out])
        self.assertEqual(rc, 2, err)
        self.assertIn(self.crlf, err)
        self.assertIn("CR", err)
        self.assertFalse(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()
