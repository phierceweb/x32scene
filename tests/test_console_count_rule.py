"""One rule for `monitor.physical_outputs` on every path: a declared count that is not a
whole number 0-16 is the same error for `ports`, `report` and `preflight`, with or without
--console, and never passes the model's mismatch test by comparing equal."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.services.preflight import physical_outputs

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
BAD = (16.0, 8.0, True, "16", "8", 17, -1)
MESSAGE = "physical_outputs must be a whole number 0-16, got {!r}"


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class CountRuleTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in ("X32SCENE_CONFIG", "X32SCENE_STAGE", "X32SCENE_CONSOLE"):
            os.environ.pop(var, None)

    def _config(self, count) -> str:
        path = os.path.join(self.dir, "rig.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"monitor": {"physical_outputs": count}}, fh)
        return path

    def test_the_library_raises_the_check_message_for_a_malformed_count(self):
        for bad in BAD:
            with self.subTest(count=bad), self.assertRaises(ValueError) as cm:
                physical_outputs({"monitor": {"physical_outputs": bad}})
            self.assertIn("monitor." + MESSAGE.format(bad), str(cm.exception))
        self.assertIsNone(physical_outputs({"monitor": {}}))
        self.assertEqual(physical_outputs({"monitor": {"physical_outputs": 8}}), 8)

    def test_ports_and_report_refuse_it_in_one_line_with_or_without_a_model(self):
        for bad in BAD:
            cfg = self._config(bad)
            for cmd in ("ports", "report"):
                for console in ((), ("--console", "X32"), ("--console", "X32RACK")):
                    with self.subTest(count=bad, cmd=cmd, console=console):
                        rc, text, err = run(cmd, SCENE, "--config", cfg, *console)
                        self.assertEqual((rc, text), (1, ""))
                        self.assertEqual(len(err.strip().splitlines()), 1, err)
                        self.assertIn(MESSAGE.format(bad), err)

    def test_preflight_fails_it_as_a_finding_with_or_without_a_model(self):
        for bad in BAD:
            cfg = self._config(bad)
            for console in ((), ("--console", "X32"), ("--console", "X32RACK")):
                with self.subTest(count=bad, console=console):
                    rc, text, err = run("preflight", SCENE, "--config", cfg, *console)
                    self.assertEqual((rc, err), (1, ""))
                    self.assertIn(MESSAGE.format(bad), text)
                    self.assertNotIn("but the config declares", text)

    def test_a_whole_count_that_differs_from_the_model_is_still_the_mismatch(self):
        cfg = self._config(16)
        for cmd in ("ports", "report", "preflight"):
            with self.subTest(cmd=cmd):
                rc, text, err = run(cmd, SCENE, "--config", cfg, "--console", "X32RACK")
                self.assertEqual((rc, text), (1, ""))
                self.assertIn("but the config declares monitor.physical_outputs 16", err)


if __name__ == "__main__":
    unittest.main()
