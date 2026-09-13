"""A line the edit writes or reads that carries only its path — no values — is an error
naming that line: exit 2 with nothing written for band-setup, exit 1 for a single edit.
Never a bare 'list index out of range', and never a silent exit 0."""

import contextlib
import io
import os
import re
import tempfile
import unittest

from x32scene.cli import main

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
COPY = '{"iem_copy": [{"src": 1, "dst": 5}]}'


def _stripped(d: str, path: str) -> str:
    with open(EXAMPLE, encoding="utf-8", newline="") as fh:
        text, n = re.subn(rf"^{re.escape(path)}( .*)?$", path, fh.read(), flags=re.M)
    assert n == 1, path
    scene = os.path.join(d, "t.scn")
    with open(scene, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return scene


def _run(argv: list[str]) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        rc = main(argv)
    return rc, err.getvalue()


class BandSetupTest(unittest.TestCase):
    CASES = (
        ("/ch/01/config", '{"channels": {"1": {"name": "Kick 2"}}}'),
        ("/headamp/000", '{"channels": {"1": {"gain_db": 20.0}}}'),
        ("/ch/19/grp", '{"dca": {"3": [19]}}'),
        ("/ch/23/mix/05", '{"iem_sends": [{"strip": 23, "bus": 5, "level": -14.0}]}'),
        ("/config/routing/IN", '{"routing": {"IN": {"1-8": "A1-8"}}}'),
        ("/outputs/main/11", '{"output_patch": {"main": {"11": {"src": "bus 12"}}}}'),
        ("/outputs/p16/01", '{"output_patch": {"p16": {"1": {"src": "direct out ch 5"}}}}'),
        ("/ch/15/mix/05", COPY),
        ("/ch/15/mix/06", COPY),
        ("/ch/01/mix/01", COPY),
    )

    def test_exits_2_naming_the_line(self):
        for path, plan_json in self.CASES:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as d:
                plan, out = os.path.join(d, "p.json"), os.path.join(d, "o.scn")
                with open(plan, "w", encoding="utf-8") as fh:
                    fh.write(plan_json)
                rc, err = _run(["band-setup", _stripped(d, path), plan, "-o", out])
                self.assertEqual(rc, 2, err)
                self.assertIn("nothing written", err)
                self.assertIn(f"{path} has 0 value(s)", err)
                self.assertFalse(os.path.exists(out))


class SingleEditTest(unittest.TestCase):
    CASES = (
        ("/config/routing/IN", ["set-routing", "{scene}", "IN", "1-8=A1-8", "-o", "{out}"]),
        ("/config/routing/IN", ["snippet", "{scene}", "--edit", "set-routing IN 1-8=A1-8",
                                "-o", "{out}"]),
        ("/outputs/main/11", ["set-output", "{scene}", "main", "11", "--src", "bus 12",
                              "-o", "{out}"]),
        ("/ch/01/config", ["set-input", "{scene}", "1", "aes50-a 3", "-o", "{out}"]),
    )

    def test_exits_1_naming_the_line(self):
        for path, argv in self.CASES:
            with self.subTest(cmd=argv[0], path=path), tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "o.snp" if argv[0] == "snippet" else "o.scn")
                subs = {"{scene}": _stripped(d, path), "{out}": out}
                rc, err = _run([subs.get(a, a) for a in argv])
                self.assertEqual(rc, 1, err)
                self.assertEqual(err.strip(), f"x32scene: {path} has 0 value(s), too few "
                                              "for this edit")
                self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
