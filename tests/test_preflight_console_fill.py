"""`preflight --console`: the "checked:" line and --json `checked` describe the config as
checked, with the model's count filled in, and the FAIL for a missing count names both ways
to give one."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene.cli import main

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
REACH = {"monitor": {"require_reachable": True}}


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class ConsoleFillTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in ("X32SCENE_CONFIG", "X32SCENE_STAGE", "X32SCENE_CONSOLE"):
            os.environ.pop(var, None)

    def _config(self, doc: dict) -> str:
        path = os.path.join(self.dir, "rig.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return path

    def test_checked_counts_the_filled_count(self):
        cfg = self._config(REACH)
        rc, text, err = run("preflight", SCENE, "--config", cfg, "--console", "X32RACK")
        self.assertEqual((rc, err), (0, ""), text)
        self.assertIn("checked: monitor(2)", text)
        rc, text, _ = run("preflight", SCENE, "--config", cfg, "--console", "X32RACK", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(text)["checked"], {"monitor": 2})

    def test_the_environment_model_is_counted_the_same_way(self):
        cfg = self._config(REACH)
        with mock.patch.dict(os.environ, {"X32SCENE_CONSOLE": "X32RACK"}):
            rc, text, _ = run("preflight", SCENE, "--config", cfg, "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(text)["checked"], {"monitor": 2})

    def test_a_config_with_no_monitor_section_is_not_said_to_check_one(self):
        cfg = self._config({"channels": {"1": {"name": "Kick"}}})
        rc, text, _ = run("preflight", SCENE, "--config", cfg, "--console", "X32RACK", "--json")
        self.assertEqual(rc, 0, text)
        self.assertEqual(json.loads(text)["checked"], {"channels": 1})

    def test_the_missing_count_fail_names_the_console_flag_and_variable(self):
        rc, text, _ = run("preflight", SCENE, "--config", self._config(REACH))
        self.assertEqual(rc, 1)
        line = next(ln for ln in text.splitlines() if "require_reachable needs" in ln)
        self.assertIn("physical_outputs", line)
        self.assertIn("--console", line)
        self.assertIn("X32SCENE_CONSOLE", line)

    def test_a_malformed_count_is_one_fail_not_a_missing_count_too(self):
        cfg = self._config({"monitor": {"physical_outputs": 16.0, "require_reachable": True}})
        for console in ((), ("--console", "X32")):
            with self.subTest(console=console):
                rc, text, _ = run("preflight", SCENE, "--config", cfg, *console, "--json")
                self.assertEqual(rc, 1)
                fails = [f["message"] for f in json.loads(text)["findings"]]
                self.assertEqual(fails, ["physical_outputs must be a whole number 0-16, "
                                         "got 16.0"])


if __name__ == "__main__":
    unittest.main()
