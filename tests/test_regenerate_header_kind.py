"""`preflight --regenerate` decides "is this a scene" by the header as well as the name: a
snippet or preset renamed .scn, even one carrying channel strips, is refused with nothing
written."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene.cli import main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIXTURES, "example.scn")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def _first_line(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.readline()


class RegenerateHeaderKindTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in ("X32SCENE_CONFIG", "X32SCENE_STAGE", "X32SCENE_CONSOLE"):
            os.environ.pop(var, None)
        self.out = os.path.join(self.dir, "rig.json")
        with open(SCENE, encoding="utf-8") as fh:
            self.body = fh.read().split("\n", 1)[1]

    def _scene_with_header(self, header: str) -> str:
        path = os.path.join(self.dir, "renamed.scn")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header + self.body)
        return path

    def test_a_snippet_or_preset_header_is_refused_with_nothing_written(self):
        cases = {"snippet": _first_line(os.path.join(FIXTURES, "example.snp")),
                 "routing preset": _first_line(os.path.join(FIXTURES, "example.rou")),
                 "effect preset": _first_line(os.path.join(FIXTURES, "example.efx"))}
        for kind, header in cases.items():
            src = self._scene_with_header(header)
            for extra in ((), ("--kind", "scn")):
                with self.subTest(kind=kind, extra=extra):
                    rc, out, err = run(*extra, "preflight", src, "--regenerate", self.out)
                    self.assertEqual((rc, out), (1, ""))
                    last = err.strip().splitlines()[-1]
                    self.assertIn(f"{src} has a {kind} header", last)
                    self.assertIn("nothing written", last)
                    self.assertFalse(os.path.exists(self.out))

    def test_a_header_of_no_known_shape_is_refused(self):
        src = self._scene_with_header("#4.0# 5".ljust(127) + "\n")
        rc, out, err = run("preflight", src, "--regenerate", self.out)
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("not a scene's", err.strip().splitlines()[-1])
        self.assertFalse(os.path.exists(self.out))

    def test_a_scene_header_is_still_read(self):
        src = self._scene_with_header(_first_line(SCENE))
        rc, _, err = run("preflight", src, "--regenerate", self.out)
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.exists(self.out))


if __name__ == "__main__":
    unittest.main()
