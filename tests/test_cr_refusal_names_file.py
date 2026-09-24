"""A CR line ending is refused by every reader that parses a file, and the refusal names
the file: a scene argument, or the preset apply-preset, apply-fx or apply-routing reads."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene.cli import main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def crlf_copy(d: str, name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8", newline="") as fh:
        text = fh.read()
    path = os.path.join(d, "crlf-" + name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace("\n", "\r\n"))
    return path


class CrRefusalNamesFileTest(unittest.TestCase):
    def test_a_scene_argument(self):
        with tempfile.TemporaryDirectory() as d:
            scn = crlf_copy(d, "example.scn")
            rc, _, err = run("info", scn)
            self.assertEqual(rc, 1)
            last = err.strip().splitlines()[-1]
            self.assertIn(scn, last)
            self.assertIn("CR line endings", last)

    def test_a_preset_read_by_an_apply(self):
        scene = os.path.join(FIXTURES, "example.scn")
        cases = (("apply-preset", "example.chn", ["1"]), ("apply-fx", "example.efx", ["1"]),
                 ("apply-routing", "example.rou", []))
        for cmd, preset, extra in cases:
            with self.subTest(cmd=cmd), tempfile.TemporaryDirectory() as d:
                path = crlf_copy(d, preset)
                out = os.path.join(d, "out.scn")
                rc, _, err = run(cmd, scene, *extra, path, "-o", out)
                self.assertEqual(rc, 1)
                last = err.strip().splitlines()[-1]
                self.assertIn(path, last)
                self.assertIn("CR line endings", last)
                self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
