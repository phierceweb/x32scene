"""--console MODEL and X32SCENE_CONSOLE: the model's jack count labels `ports` and `report`,
fills a `preflight` config that declares none, and is written by `--regenerate`; a config
declaring a different count, or an unknown model, is refused in one line."""

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


class ConsoleCliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in ("X32SCENE_CONFIG", "X32SCENE_STAGE", "X32SCENE_CONSOLE"):
            os.environ.pop(var, None)

    def _config(self, doc: dict, name: str = "rig.json") -> str:
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return path

    def _read(self, path: str) -> dict:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_regenerate_writes_the_count_and_the_config_then_checks_clean(self):
        out = os.path.join(self.dir, "rig.json")
        rc, _, err = run("preflight", SCENE, "--regenerate", out, "--console", "X32 Rack")
        self.assertEqual(rc, 0, err)
        mon = self._read(out)["monitor"]
        self.assertEqual((mon["physical_outputs"], mon["require_reachable"]), (8, True))
        for extra in ((), ("--console", "x32rack")):
            with self.subTest(extra=extra):
                rc, text, err = run("preflight", SCENE, "--config", out, *extra)
                self.assertEqual(rc, 0, err)
                self.assertIn("PREFLIGHT OK", text)

    def test_regenerate_reads_the_environment(self):
        out = os.path.join(self.dir, "rig.json")
        with mock.patch.dict(os.environ, {"X32SCENE_CONSOLE": "X32RACK"}):
            self.assertEqual(run("preflight", SCENE, "--regenerate", out)[0], 0)
        self.assertEqual(self._read(out)["monitor"]["physical_outputs"], 8)

    def test_an_unknown_model_is_one_line_listing_the_known_and_writes_nothing(self):
        out = os.path.join(self.dir, "rig.json")
        reach = self._config(REACH, "reach.json")
        cases = (("preflight", SCENE, "--regenerate", out), ("ports", SCENE),
                 ("report", SCENE), ("preflight", SCENE, "--config", reach))
        for argv in cases:
            with self.subTest(cmd=argv[0], regenerate="--regenerate" in argv):
                rc, _, err = run(*argv, "--console", "X99")
                self.assertEqual(rc, 1)
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                self.assertIn("'X99'", err)
                self.assertIn("X32RACK (X32 Rack)", err)
        self.assertFalse(os.path.exists(out))

    def test_a_console_with_no_jacks_labels_every_main_output_virtual(self):
        rc, text, err = run("ports", SCENE, "--console", "X32 Core")
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("Outputs (main 1-16 = virtual: no rear jacks)", text)
        self.assertIn("main 01 [virt]", text)
        self.assertNotIn("[XLR ]", text)
        rc, text, _ = run("report", SCENE, "--console", "M32C")
        self.assertEqual(rc, 0)
        self.assertNotIn("(XLR)", text)
        self.assertIn("(virtual)", text)

    def test_preflight_fills_a_config_that_declares_no_count(self):
        cfg = self._config(REACH)
        rc, text, _ = run("preflight", SCENE, "--config", cfg)
        self.assertEqual(rc, 1)
        self.assertIn("require_reachable needs physical_outputs", text)
        rc, text, err = run("preflight", SCENE, "--config", cfg, "--console", "X32RACK")
        self.assertEqual(rc, 0, text + err)
        self.assertIn("checked: monitor(1)", text)

    def test_preflight_takes_the_model_from_the_environment(self):
        cfg = self._config(REACH)
        with mock.patch.dict(os.environ, {"X32SCENE_CONSOLE": "X32 Rack"}):
            self.assertEqual(run("preflight", SCENE, "--config", cfg)[0], 0)

    def test_a_config_declaring_another_count_is_refused_in_one_line(self):
        cfg = self._config({"monitor": {"physical_outputs": 16, "require_reachable": True}})
        for argv in (("preflight", SCENE, "--config", cfg), ("ports", SCENE, "--config", cfg),
                     ("report", SCENE, "--config", cfg)):
            with self.subTest(cmd=argv[0]):
                rc, text, err = run(*argv, "--console", "X32RACK")
                self.assertEqual((rc, text), (1, ""))
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                self.assertIn("physical_outputs 16", err)
                self.assertIn("8", err)

    def test_ports_and_report_label_from_the_model(self):
        rc, text, _ = run("ports", SCENE, "--console", "X32RACK")
        self.assertEqual(rc, 0)
        self.assertIn("main 08 [XLR ]", text)
        self.assertIn("main 09 [virt]", text)
        rc, text, _ = run("report", SCENE, "--console", "x32 rack")
        self.assertEqual(rc, 0)
        self.assertIn("main 08 (XLR)", text)
        self.assertIn("main 09 (virtual)", text)

    def test_a_model_whose_every_main_output_is_a_jack_claims_no_virtual_range(self):
        rc, text, _ = run("ports", SCENE, "--console", "X32")
        self.assertEqual(rc, 0)
        self.assertIn("main 16 [XLR ]", text)
        self.assertNotIn("virt", text.splitlines()[0])
        self.assertNotIn("17-16", text)

    def test_ports_takes_the_model_from_the_environment_and_agrees_with_a_config(self):
        cfg = self._config({"monitor": {"physical_outputs": 8}})
        with mock.patch.dict(os.environ, {"X32SCENE_CONSOLE": "X32RACK"}):
            for extra in ((), ("--config", cfg)):
                with self.subTest(extra=extra):
                    rc, text, _ = run("ports", SCENE, *extra)
                    self.assertEqual(rc, 0)
                    self.assertIn("main 09 [virt]", text)

    def test_ports_without_a_count_says_how_to_give_one(self):
        rc, text, _ = run("ports", SCENE)
        self.assertEqual(rc, 0)
        self.assertIn("--console", text.splitlines()[0])
        self.assertNotIn("[virt]", text)


if __name__ == "__main__":
    unittest.main()
