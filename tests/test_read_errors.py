"""A file that is not UTF-8 is refused in one line that names it, on every reader path."""

import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class NotUtf8Test(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.bad = self._bytes("bad.scn", b'#2.7#\n/ch/01/config "\xff" 1 RD 1\n')

    def _bytes(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def _assert_named(self, argv, path, rc=1, what="not a console text file"):
        got, _, err = _run(argv)
        self.assertEqual(got, rc, err)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn(path, err)
        self.assertIn(what, err)
        self.assertNotIn("codec", err)

    def test_scene_load_names_the_file(self):
        with self.assertRaisesRegex(ValueError, f"^{re.escape(self.bad)}: not a console text file"):
            Scene.load(self.bad)

    def test_every_scene_reader_names_the_file(self):
        out = os.path.join(self.dir, "out.scn")
        for argv in (["info", self.bad], ["diff", SCENE, self.bad],
                     ["set-fader", self.bad, "/ch/01", "-3", "-o", out]):
            with self.subTest(cmd=argv[0]):
                self._assert_named(argv, self.bad)
        rc, report, _ = _run(["audit", self.dir])
        self.assertEqual(rc, 1)
        self.assertIn("bad.scn: not a console text file", report)
        self.assertNotIn(self.bad, report)

    def test_a_preset_names_the_file(self):
        chn = self._bytes("bad.chn", b'/config "\xfe" 1 RD 1\n')
        out = os.path.join(self.dir, "out.scn")
        self._assert_named(["apply-preset", SCENE, "1", chn, "-o", out], chn)

    def test_a_plan_preset_names_the_file_and_exits_2(self):
        chn = self._bytes("bad.chn", b'/config "\xfe" 1 RD 1\n')
        plan = os.path.join(self.dir, "plan.json")
        with open(plan, "w", encoding="utf-8") as fh:
            json.dump({"channels": {"1": {"preset": chn}}}, fh)
        out = os.path.join(self.dir, "out.scn")
        self._assert_named(["band-setup", SCENE, plan, "-o", out], chn, rc=2)
        self.assertFalse(os.path.exists(out))

    def test_a_json_document_names_the_file(self):
        cfg = self._bytes("cfg.json", b'{"title": "\xff"}')
        self._assert_named(["preflight", SCENE, "--config", cfg], cfg, what="not UTF-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
