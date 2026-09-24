"""A `monitor` section that is not an object is the same error for `ports` and `report` as
the FAIL `preflight` reports, rather than a silent "no count declared"."""

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


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class MonitorObjectTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in ("X32SCENE_CONFIG", "X32SCENE_STAGE", "X32SCENE_CONSOLE"):
            os.environ.pop(var, None)
        self.cfg = os.path.join(self.dir, "rig.json")
        with open(self.cfg, "w", encoding="utf-8") as fh:
            json.dump({"monitor": 8}, fh)

    def test_the_library_raises_the_check_message(self):
        with self.assertRaises(ValueError) as cm:
            physical_outputs({"monitor": 8})
        self.assertIn("monitor must be an object, got int", str(cm.exception))
        self.assertIsNone(physical_outputs({}))

    def test_ports_and_report_refuse_it_and_preflight_fails_it(self):
        for cmd in ("ports", "report"):
            for console in ((), ("--console", "X32RACK")):
                with self.subTest(cmd=cmd, console=console):
                    rc, text, err = run(cmd, SCENE, "--config", self.cfg, *console)
                    self.assertEqual((rc, text), (1, ""))
                    self.assertIn("monitor must be an object, got int", err)
        rc, text, _ = run("preflight", SCENE, "--config", self.cfg, "--console", "X32RACK")
        self.assertEqual(rc, 1)
        self.assertIn("monitor must be an object, got int", text)


if __name__ == "__main__":
    unittest.main()
