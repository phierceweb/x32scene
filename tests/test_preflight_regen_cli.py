"""`preflight SCENE --regenerate OUT.json`: writes the config, never over a file without
--force, never over the scene, and reads no config even when X32SCENE_CONFIG is set."""

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
CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "example-preflight.json")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class RegenerateCliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = os.path.join(self.dir, "rig.json")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("X32SCENE_CONFIG", None)
        os.environ.pop("X32SCENE_STAGE", None)

    def _read(self) -> str:
        with open(self.out, encoding="utf-8") as fh:
            return fh.read()

    def test_writes_a_config_the_scene_then_passes(self):
        rc, out, _ = run("preflight", SCENE, "--regenerate", self.out)
        self.assertEqual(rc, 0)
        self.assertIn(self.out, out)
        self.assertIn("channels(32)", out)
        doc = json.loads(self._read())
        self.assertIn("example.scn", doc["_comment"])
        self.assertNotIn(self.dir, doc["_comment"])
        rc, out, _ = run("preflight", SCENE, "--config", self.out)
        self.assertEqual(rc, 0, out)
        self.assertIn("PREFLIGHT OK", out)

    def test_a_check_with_no_config_says_how_to_write_one(self):
        rc, _, err = run("preflight", SCENE)
        self.assertEqual(rc, 1)
        self.assertIn("--regenerate", err)

    def test_refuses_an_existing_file_without_force(self):
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("keep me\n")
        rc, _, err = run("preflight", SCENE, "--regenerate", self.out)
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err)
        self.assertEqual(self._read(), "keep me\n")
        self.assertEqual(run("preflight", SCENE, "--regenerate", self.out, "--force")[0], 0)
        self.assertIn("channels", json.loads(self._read()))

    def test_never_writes_over_the_scene(self):
        scene = os.path.join(self.dir, "gig.scn")
        shutil.copy(SCENE, scene)
        rc, _, err = run("preflight", scene, "--regenerate", scene, "--force")
        self.assertEqual(rc, 1)
        self.assertIn("would overwrite the input", err)
        with open(scene, encoding="utf-8") as a, open(SCENE, encoding="utf-8") as b:
            self.assertEqual(a.read(), b.read())

    def test_refuses_an_unwritable_name_in_one_line_before_reading_the_scene(self):
        missing_scene = os.path.join(self.dir, "not-there.scn")
        nodir = os.path.join(self.dir, "nodir", "rig.json")
        cases = (
            ([nodir], "no directory"),
            ([self.dir], "is a directory"),
            ([self.dir, "--force"], "is a directory"),
            ([self.dir + os.sep, "--force"], "is a directory"),
            (["", "--force"], "needs a file name"),
        )
        for scene in (SCENE, missing_scene):
            for extra, message in cases:
                with self.subTest(scene=os.path.basename(scene), argv=extra):
                    rc, out, err = run("preflight", scene, "--regenerate", *extra)
                    self.assertEqual(rc, 1)
                    self.assertEqual(out, "")
                    self.assertIn("--regenerate", err)
                    self.assertIn(message, err)
                    self.assertNotIn("Errno", err)
                    self.assertNotIn(".tmp", err)
                    self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertEqual(os.listdir(self.dir), [])

    def test_a_name_the_filesystem_refuses_is_one_line_without_a_temp_name(self):
        rc, out, err = run("preflight", SCENE, "--regenerate",
                           os.path.join(self.dir, "x" * 300 + ".json"))
        self.assertEqual((rc, out), (1, ""))
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn("--regenerate", err)
        self.assertNotIn(".tmp", err)
        self.assertNotIn("Errno", err)
        self.assertEqual(os.listdir(self.dir), [])

    def test_refuses_the_flags_that_only_mean_something_to_a_check(self):
        for extra in (["--config", CONFIG], ["--stage", CONFIG], ["--json"]):
            with self.subTest(flag=extra[0]):
                rc, _, err = run("preflight", SCENE, "--regenerate", self.out, *extra)
                self.assertEqual(rc, 1)
                self.assertIn(extra[0], err)
                self.assertFalse(os.path.exists(self.out))

    def test_the_environment_defaults_neither_refuse_nor_get_read(self):
        missing = os.path.join(self.dir, "no-such.json")
        with mock.patch.dict(os.environ, {"X32SCENE_CONFIG": missing,
                                          "X32SCENE_STAGE": missing}):
            rc, _, err = run("preflight", SCENE, "--regenerate", self.out)
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.exists(self.out))

    def test_the_config_env_can_name_the_file_being_regenerated(self):
        shutil.copy(CONFIG, self.out)
        with mock.patch.dict(os.environ, {"X32SCENE_CONFIG": self.out}):
            rc, _, err = run("preflight", SCENE, "--regenerate", self.out, "--force")
        self.assertEqual(rc, 0, err)
        self.assertIn("Written by", json.loads(self._read())["_comment"])

    def test_refuses_a_file_that_is_not_a_scene(self):
        for kind in ("snp", "chn", "efx", "rou", "shw"):
            with self.subTest(kind=kind):
                src = os.path.join(os.path.dirname(SCENE), f"example.{kind}")
                rc, _, err = run("preflight", src, "--regenerate", self.out)
                self.assertEqual(rc, 1)
                self.assertIn(f".{kind}", err)
                self.assertFalse(os.path.exists(self.out))

    def test_a_scene_without_the_scn_extension_is_still_read(self):
        scene = os.path.join(self.dir, "pulled.txt")
        shutil.copy(SCENE, scene)
        self.assertEqual(run("preflight", scene, "--regenerate", self.out)[0], 0)

    def test_an_out_named_as_a_console_file_is_refused_even_with_force(self):
        for kind in ("scn", "snp", "chn", "efx", "rou", "shw"):
            with self.subTest(kind=kind):
                target = os.path.join(self.dir, f"GOOD.{kind}")
                shutil.copy(SCENE, target)
                with open(target, "rb") as fh:
                    before = fh.read()
                rc, _, err = run("preflight", SCENE, "--regenerate", target, "--force")
                self.assertEqual(rc, 1)
                self.assertIn(f".{kind}", err)
                with open(target, "rb") as fh:
                    self.assertEqual(fh.read(), before)

    def test_swapped_arguments_never_overwrite_the_scene(self):
        good = os.path.join(self.dir, "GOOD.scn")
        shutil.copy(SCENE, good)
        self.assertEqual(run("preflight", good, "--regenerate", self.out)[0], 0)
        rc, _, _ = run("preflight", self.out, "--regenerate", good, "--force")
        self.assertEqual(rc, 1)
        with open(good, "rb") as a, open(SCENE, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_force_without_regenerate_is_refused(self):
        rc, _, err = run("preflight", SCENE, "--config", CONFIG, "--force")
        self.assertEqual(rc, 1)
        self.assertIn("--regenerate", err)

    def test_a_check_still_reads_the_config_env(self):
        with mock.patch.dict(os.environ, {"X32SCENE_CONFIG": CONFIG}):
            rc, out, _ = run("preflight", SCENE)
        self.assertEqual(rc, 0)
        self.assertIn("PREFLIGHT OK", out)


if __name__ == "__main__":
    unittest.main()
