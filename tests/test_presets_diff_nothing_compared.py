"""presets-diff: a preset that compares nothing is NOTHING COMPARED, never MATCH, and the scopes
its header leaves out are named as apply-preset names them."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import preset_library as lib

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
NONE_FLAGGED = ('#4.0# 1 "Kick" 0 %0000000000000000 1\n'
                '/config "Kick" 2 YEi 1\n/eq ON\n/eq/1 PEQ 99.0 +3.00 1.0\n')
EQ_FLAGGED = NONE_FLAGGED.replace("%0000000000000000", "%0001000000000000")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(SCENE)

    def test_a_header_excluding_every_body_section_compares_nothing(self):
        r = lib.check_preset(self.sc, "Kick.chn", NONE_FLAGGED)
        self.assertEqual((r.status, r.compared), (lib.NOTHING_COMPARED, 0))
        self.assertEqual(r.skipped, ["scribble", "eq"])

    def test_a_scope_the_preset_does_not_carry_compares_nothing(self):
        r = lib.check_preset(self.sc, "Kick.chn", '/config "Kick" 2 YEi 1\n', ["eq"])
        self.assertEqual(r.status, lib.NOTHING_COMPARED)
        self.assertEqual(r.skipped, [])

    def test_a_header_that_skips_some_scopes_still_names_them(self):
        r = lib.check_preset(self.sc, "Kick.chn", EQ_FLAGGED)
        self.assertEqual((r.status, r.compared), (lib.DRIFT, 2))
        self.assertEqual(r.skipped, ["scribble"])

    def test_nothing_compared_is_counted_and_does_not_fail(self):
        self.assertIn(lib.NOTHING_COMPARED, lib.STATUSES)


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        with open(os.path.join(self.dir, "Kick.chn"), "w", encoding="utf-8") as fh:
            fh.write(NONE_FLAGGED)

    def test_text_names_the_verdict_and_the_skipped_scopes(self):
        rc, out, _ = _run(["presets-diff", self.dir, SCENE])
        self.assertEqual(rc, 0)
        row, note, count = out.splitlines()
        self.assertTrue(row.startswith("NOTHING COMPARED Kick.chn"), row)
        self.assertNotIn("MATCH", row)
        self.assertIn("skipped scribble, eq: the preset header does not flag them present", note)
        self.assertIn("0 MATCH", count)
        self.assertIn("1 NOTHING COMPARED", count)

    def test_json_carries_the_verdict_and_the_skipped_scopes(self):
        rc, out, _ = _run(["presets-diff", self.dir, SCENE, "--json"])
        doc = json.loads(out)
        self.assertEqual((rc, doc["ok"]), (0, True))
        row = doc["presets"][0]
        self.assertEqual((row["status"], row["compared"], row["skipped"]),
                         ("NOTHING COMPARED", 0, ["scribble", "eq"]))
        self.assertEqual((doc["counts"]["MATCH"], doc["counts"]["NOTHING COMPARED"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
