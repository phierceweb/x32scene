"""The set-send-tap command, and the snippet --edit that carries it.

Fixture facts the cases lean on: ch01 and /auxin/01 are unlinked, channels 11/12 and FX
returns 1/2 are linked, and every odd send line taps PRE.
"""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
LOAD_TEST = "LOAD-TEST on the console before a gig."


def _run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class SetSendTapCliTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        self.out = os.path.join(d.name, "out.scn")

    def _changed(self) -> list[str]:
        before, after = Scene.load(EXAMPLE), Scene.load(self.out)
        return [ln.path for ln in after.lines if ln.path and before.get(ln.path).raw != ln.raw]

    def test_odd_bus(self):
        code, text, err = _run("set-send-tap", EXAMPLE, "1", "9", "POST", "-o", self.out)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(text.splitlines(), [
            "bus 9's tap sets buses 9 and 10",
            "  /ch/01/mix/09 tap PRE -> POST",
            f"wrote {self.out}",
            LOAD_TEST])
        self.assertEqual(self._changed(), ["/ch/01/mix/09"])
        written = Scene.load(self.out)
        self.assertEqual(Scene.parse(written.dump()).dump(), written.dump())

    def test_even_bus_names_the_odd_line_it_writes(self):
        code, text, _ = _run("set-send-tap", EXAMPLE, "1", "10", "POST", "-o", self.out)
        self.assertEqual(code, 0)
        self.assertIn("bus 10's tap lives on bus 9's line: sets buses 9 and 10", text)
        self.assertEqual(self._changed(), ["/ch/01/mix/09"])

    def test_tap_in_either_case_is_written_canonically(self):
        code, text, _ = _run("set-send-tap", EXAMPLE, "1", "1", "in/lc", "-o", self.out)
        self.assertEqual(code, 0)
        self.assertIn("/ch/01/mix/01 tap PRE -> IN/LC", text)
        self.assertEqual(Scene.load(self.out).get("/ch/01/mix/01").args[3], "IN/LC")

    def test_linked_strip_mirrors_and_no_link_opts_out(self):
        code, text, _ = _run("set-send-tap", EXAMPLE, "11", "3", "EQ->", "-o", self.out)
        self.assertEqual(code, 0)
        self.assertIn("  /ch/11/mix/03 tap PRE -> EQ->\n"
                      "  /ch/12/mix/03 tap PRE -> EQ-> (stereo-linked partner)\n", text)
        self.assertEqual(self._changed(), ["/ch/11/mix/03", "/ch/12/mix/03"])
        os.remove(self.out)
        code, text, _ = _run("set-send-tap", EXAMPLE, "11", "3", "EQ->", "--no-link",
                             "-o", self.out)
        self.assertEqual(code, 0)
        self.assertNotIn("/ch/12", text)
        self.assertEqual(self._changed(), ["/ch/11/mix/03"])

    def test_aux_in_and_fx_return(self):
        code, _, _ = _run("set-send-tap", EXAMPLE, "/auxin/01", "2", "GRP", "-o", self.out)
        self.assertEqual(code, 0)
        self.assertEqual(self._changed(), ["/auxin/01/mix/01"])
        os.remove(self.out)
        code, text, _ = _run("set-send-tap", EXAMPLE, "/fxrtn/01", "5", "<-EQ", "-o", self.out)
        self.assertEqual(code, 0)
        self.assertEqual(self._changed(), ["/fxrtn/01/mix/05", "/fxrtn/02/mix/05"])

    def test_refusals_write_nothing(self):
        short = os.path.join(self.dir, "short.scn")
        with open(EXAMPLE, encoding="utf-8") as fh:
            text = fh.read()
        with open(short, "w", encoding="utf-8") as fh:
            fh.write(text.replace("/ch/01/mix/03 ON  +6.8 +0 PRE 0", "/ch/01/mix/03 ON  +6.8"))
        cases = (([EXAMPLE, "33", "1", "POST"], "not a send strip"),
                 ([EXAMPLE, "/bus/01", "1", "POST"], "not a send strip"),
                 ([EXAMPLE, "1", "17", "POST"], "out of range 1-16"),
                 ([EXAMPLE, "1", "0", "POST"], "out of range 1-16"),
                 ([short, "1", "4", "POST"], "too few"))
        for argv, why in cases:
            with self.subTest(argv=argv[1:]):
                code, _, err = _run("set-send-tap", *argv, "-o", self.out)
                self.assertEqual(code, 1)
                self.assertIn(why, err)
                self.assertFalse(os.path.exists(self.out))

    def test_unknown_tap_is_a_usage_error(self):
        code, _, err = _run("set-send-tap", EXAMPLE, "1", "1", "LATE", "-o", self.out)
        self.assertEqual(code, 2)
        self.assertIn("invalid choice: 'LATE'", err)
        self.assertFalse(os.path.exists(self.out))

    def test_snippet_edit_carries_exactly_the_send_lines(self):
        snp = os.path.join(self.dir, "tap.snp")
        code, text, err = _run("snippet", EXAMPLE, "-o", snp,
                               "--edit", "set-send-tap 11 4 post")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("bus 4's tap lives on bus 3's line", text)
        with open(snp, encoding="utf-8") as fh:
            body = [ln for ln in fh.read().split("\n")[1:] if ln]
        self.assertEqual(body, ["/ch/11/mix/03 ON  -1.8 -100 POST 0",
                                "/ch/12/mix/03 ON  -1.8 +100 POST 0"])

    def test_snippet_edit_refusal_is_exit_1(self):
        snp = os.path.join(self.dir, "tap.snp")
        for edit in ("set-send-tap 1 1 LATE", "set-send-tap 1 17 POST"):
            with self.subTest(edit=edit):
                code, _, _ = _run("snippet", EXAMPLE, "-o", snp, "--edit", edit)
                self.assertEqual(code, 1)
                self.assertFalse(os.path.exists(snp))


if __name__ == "__main__":
    unittest.main()
