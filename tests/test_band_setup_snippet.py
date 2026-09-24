"""`band-setup --snippet` writes no header-only snippet when the plan changes nothing a
snippet can carry."""

import contextlib
import io
import json
import os
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


class EmptySnippetTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = os.path.join(self.dir, "out.scn")
        self.snp = os.path.join(self.dir, "out.snp")

    def _band_setup(self, plan):
        path = os.path.join(self.dir, "plan.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh)
        return _run(["band-setup", SCENE, path, "-o", self.out, "--snippet", self.snp])

    def test_a_title_only_plan_writes_the_scene_and_no_snippet(self):
        rc, out, err = self._band_setup({"title": "New Band"})
        self.assertEqual(rc, 0, err)
        self.assertEqual(Scene.load(self.out).name, "New Band")
        self.assertFalse(os.path.exists(self.snp))
        self.assertIn(f"nothing a snippet can carry; nothing written to {self.snp}", out)

    def test_a_plan_whose_only_change_a_snippet_cannot_carry_names_it(self):
        rc, out, err = self._band_setup({"routing": {"switch": "PLAY"}})
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(self.snp))
        self.assertIn("nothing a snippet can carry (/config/routing/routswitch); nothing "
                      f"written to {self.snp}", out)

    def test_with_force_a_stale_snippet_is_removed(self):
        with open(self.snp, "w", encoding="utf-8") as fh:
            fh.write("stale\n")
        path = os.path.join(self.dir, "plan.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"title": "New Band"}, fh)
        rc, out, err = _run(["band-setup", SCENE, path, "-o", self.out, "--snippet", self.snp,
                             "--force"])
        self.assertEqual(rc, 0, err)
        self.assertFalse(os.path.exists(self.snp))
        self.assertIn(f"nothing a snippet can carry; removed the old {self.snp}", out)

    def test_a_plan_with_a_carried_change_writes_both(self):
        rc, out, err = self._band_setup({"title": "New Band", "channels": {"1": {"name": "Floor Tom"}}})
        self.assertEqual(rc, 0, err)
        self.assertIn(f"wrote {self.snp}: 1 lines", out)
        self.assertIn("/ch/01/config", open(self.snp, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
