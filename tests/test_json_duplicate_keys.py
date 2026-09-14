"""A JSON document that repeats a key at any depth is refused, never read last-wins."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.services.jsonfile import read_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE = os.path.join(ROOT, "tests", "fixtures", "example.scn")
EXAMPLE_CFG = os.path.join(ROOT, "config", "example-preflight.json")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class DuplicateKeyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def _write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def _example_with(self, example, old, new):
        with open(os.path.join(ROOT, "config", example), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(old, text)
        return self._write(example, text.replace(old, new, 1))

    def test_read_json_names_the_key_and_file_at_any_depth(self):
        for doc in ('{"a": 1, "a": 2}', '{"a": [{"b": {"c": 1, "c": 1}}]}'):
            path = self._write("doc.json", doc)
            with self.subTest(doc=doc), self.assertRaises(ValueError) as cm:
                read_json(path)
            self.assertIn(path, str(cm.exception))
            self.assertIn("duplicate key", str(cm.exception))
        self.assertEqual(read_json(self._write("ok.json", '{"a": {"a": 1}}')), {"a": {"a": 1}})

    def test_band_setup_exits_2_and_writes_nothing(self):
        plan = self._write("plan.json", '{"channels": {"1": {"name": "Kick A"}, '
                                        '"1": {"name": "Kick B"}}}')
        out = os.path.join(self.dir, "out.scn")
        rc, _, err = _run(["band-setup", SCENE, plan, "-o", out])
        self.assertEqual(rc, 2, err)
        self.assertIn('duplicate key "1"', err)
        self.assertIn(plan, err)
        self.assertFalse(os.path.exists(out))

    def test_preflight_config_and_stage_sidecar_exit_1(self):
        cfg = self._example_with("example-preflight.json", '"1": {', '"1": {"name": "Dup", ')
        stage = self._example_with("example-stage.json", '"_comment": ',
                                   '"_comment": "a", "_comment": ')
        for argv, path, key in ((["--config", cfg], cfg, "name"),
                                (["--config", EXAMPLE_CFG, "--stage", stage], stage, "_comment")):
            with self.subTest(file=os.path.basename(path)):
                rc, out, err = _run(["preflight", SCENE, *argv])
                self.assertEqual((rc, out), (1, ""), err)
                self.assertIn(f'duplicate key "{key}"', err)
                self.assertIn(path, err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
