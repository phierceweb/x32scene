"""The set-record command, and the snippet --edit that carries it.

Fixture facts the cases lean on: example.scn records user-out slots 1-32 on tracks 1-32,
slot 5 holds Local input 5, and AES50-A/B 1-8 also read slots 1-8; example-alt.scn's
first CARD block is AN1-8.
"""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.snippets import read_header

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EXAMPLE_ALT = os.path.join(FIX, "example-alt.scn")
LOAD_TEST = "LOAD-TEST on the console before a gig."


def _run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


class SetRecordCliTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        self.out = os.path.join(d.name, "out.scn")

    def _changed(self, src: str = EXAMPLE) -> list[str]:
        before, after = Scene.load(src), Scene.load(self.out)
        return [ln.path for ln in after.lines if ln.path and before.get(ln.path).raw != ln.raw]

    def test_prints_old_new_slot_and_the_other_readers(self):
        code, text, err = _run("set-record", EXAMPLE, "5", "Output 9", "-o", self.out)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(text.splitlines(), [
            "track 5: Local input 5 -> Output 9 (user-out slot 5)",
            "  user-out slot 5 also feeds AES50-A 5, AES50-B 5",
            f"wrote {self.out}",
            LOAD_TEST])
        self.assertEqual(self._changed(), ["/config/userrout/out"])
        written = Scene.load(self.out)
        self.assertEqual(written.get("/config/userrout/out").args[4], "177")
        self.assertEqual(Scene.parse(written.dump()).dump(), written.dump())

    def test_record_map_prints_what_was_set(self):
        code, _, _ = _run("set-record", EXAMPLE_ALT, "12", "p16 3", "-o", self.out)
        self.assertEqual(code, 0)
        code, text, _ = _run("record-map", self.out)
        self.assertIn("track 12 <- P16 3", text)
        self.assertEqual(self._changed(EXAMPLE_ALT), ["/config/userrout/out"])

    def test_refusals_write_nothing(self):
        cases = (([EXAMPLE_ALT, "3", "Output 1"], "CARD block 1-8 is AN1-8, not a UOUT block"),
                 ([EXAMPLE, "33", "Output 1"], "record track must be 1-32"),
                 ([EXAMPLE, "1", "bus 9"], "unknown user-out source"),
                 ([EXAMPLE, "1", "output 17"], "output sources run 1-16"))
        for argv, why in cases:
            with self.subTest(argv=argv[1:]):
                code, text, err = _run("set-record", *argv, "-o", self.out)
                self.assertEqual((code, text), (1, ""))
                self.assertIn(why, err)
                self.assertFalse(os.path.exists(self.out))

    def test_a_track_that_is_not_a_number_is_a_usage_error(self):
        code, _, _ = _run("set-record", EXAMPLE, "five", "Output 1", "-o", self.out)
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.out))

    def test_snippet_edit_carries_exactly_the_user_out_line(self):
        snp = os.path.join(self.dir, "rec.snp")
        code, text, err = _run("snippet", EXAMPLE, "-o", snp,
                               "--edit", "set-record 17 'aux out 2'")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("track 17: AES50-A input 1 -> Aux Out 2 (user-out slot 17)", text)
        with open(snp, encoding="utf-8") as fh:
            snip = fh.read()
        self.assertEqual(Scene.parse(snip).dump(), snip)
        self.assertEqual(read_header(snip).describe()["filters"], ["User Out"])
        body = [ln for ln in snip.split("\n")[1:] if ln]
        want = Scene.load(EXAMPLE).get("/config/userrout/out").args
        want[16] = "202"
        self.assertEqual(body, ["/config/userrout/out " + " ".join(want)])

    def test_snippet_edit_refusal_is_exit_1(self):
        snp = os.path.join(self.dir, "rec.snp")
        code, _, _ = _run("snippet", EXAMPLE_ALT, "-o", snp, "--edit", "set-record 1 off")
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(snp))


if __name__ == "__main__":
    unittest.main()
