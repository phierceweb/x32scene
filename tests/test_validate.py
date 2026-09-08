"""Structural validation of a single file, and the warning the CLI prints for it.

The false-positive direction comes first: a check that cries wolf on a valid `.snp`,
`.chn`, `.efx`, `.rou` or `.shw` is worse than the gap it closes, because the six kinds
have genuinely different shapes.

Policy under test: warn on stderr, never refuse, exit code unchanged.
"""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services import validate as V

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
# deliberately malformed: kept out of FIX so the audit tests keep seeing a clean library
BROKEN = os.path.join(FIX, "broken")
VALID = ("example.scn", "example-alt.scn", "example.snp", "example.chn",
         "example.efx", "example.rou", "example.shw")


def load(name):
    root = BROKEN if name.startswith("truncated") else FIX
    with open(os.path.join(root, name), encoding="utf-8", newline="") as fh:
        return Scene.parse(fh.read())


class NoFalsePositivesTest(unittest.TestCase):
    def test_every_valid_fixture_is_silent(self):
        for name in VALID:
            with self.subTest(fixture=name):
                self.assertEqual(V.findings(load(name), V.kind_of(name)), [])

    def test_a_headerless_chn_is_fine(self):
        """Console exports carry no header; docs/format.md documents it as optional."""
        chn = load("example.chn")
        self.assertFalse(chn.name)                       # really has no header
        self.assertEqual(V.findings(chn, "chn"), [])

    def test_a_shw_header_is_not_padded_to_127(self):
        shw = load("example.shw")
        self.assertEqual(len(shw.lines[0].raw), 5)       # bare "#4.0#", not padded
        self.assertEqual(V.findings(shw, "shw"), [])

    def test_kinds_whose_body_is_not_osc_paths_are_fine(self):
        """A .efx body is `type`/`source`/`par` and a .shw's is `show`/`cue/000` — no
        leading slash. An 'are these OSC paths?' check would fail both."""
        for name in ("example.efx", "example.shw"):
            with self.subTest(fixture=name):
                body = load(name).lines[1:]
                self.assertTrue(body and not any(ln.path.startswith("/") for ln in body))
                self.assertEqual(V.findings(load(name), V.kind_of(name)), [])

    def test_an_unrecognized_extension_is_not_second_guessed(self):
        self.assertIsNone(V.kind_of("notes.txt"))
        self.assertEqual(V.findings(load("example.snp"), None), [])


class CatchesBrokenFilesTest(unittest.TestCase):
    def test_a_truncated_scene_is_reported(self):
        f = V.findings(load("truncated.scn"), "scn")
        self.assertEqual([x.area for x in f], ["strips"])
        self.assertIn("32/0/0", f[0].message)

    def test_an_empty_file(self):
        f = V.findings(Scene.parse(""), "scn")
        self.assertEqual([x.area for x in f], ["file"])

    def test_text_that_is_not_a_scene(self):
        f = V.findings(Scene.parse("this is not a scene file\njust text\n"), "scn")
        self.assertEqual([x.area for x in f], ["header", "strips"])

    def test_a_header_only_snippet(self):
        f = V.findings(Scene.parse("#4.0# \"Empty\"".ljust(127) + "\n"), "snp")
        self.assertEqual([x.area for x in f], ["body"])

    def test_an_unpadded_header_on_a_kind_that_pads(self):
        f = V.findings(Scene.parse('#4.0# "Short"\n/ch/01/eq ON\n'), "snp")
        self.assertEqual([x.area for x in f], ["header"])


class CliWarningTest(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_a_broken_file_warns_but_still_reads(self):
        rc, out, err = self._run(["info", os.path.join(BROKEN, "truncated.scn")])
        self.assertEqual(rc, 0)                       # warn, never refuse
        self.assertIn("warning:", err)
        self.assertIn("truncated", err)
        self.assertIn("Example Rig", out)             # and the read still happened

    def test_a_good_file_says_nothing(self):
        rc, _out, err = self._run(["info", os.path.join(FIX, "example.scn")])
        self.assertEqual((rc, err), (0, ""))

    def test_the_warning_goes_to_stderr_so_json_stays_a_clean_pipe(self):
        import json
        rc, out, err = self._run(["fx", os.path.join(BROKEN, "truncated.scn"), "--json"])
        self.assertEqual(rc, 0)
        self.assertIn("warning:", err)
        json.loads(out)                               # raises if the banner leaked

    def test_diff_names_only_the_file_that_is_broken(self):
        rc, _out, err = self._run(["diff", os.path.join(FIX, "example.scn"),
                                   os.path.join(BROKEN, "truncated.scn")])
        self.assertEqual(rc, 0)
        self.assertEqual(err.count("warning:"), 1)
        self.assertNotIn("example.scn:", err)

    def test_an_edit_command_warns_before_it_writes(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "out.scn")
            rc, _out, err = self._run(["set-fader", os.path.join(BROKEN, "truncated.scn"),
                                       "/ch/01", "-3.0", "-o", out_path])
            self.assertEqual(rc, 0)
            self.assertIn("warning:", err)
            self.assertTrue(os.path.exists(out_path))

    def test_audit_still_fails_rather_than_warns(self):
        """The same finding is a warning when you read one file and an exit-1 violation
        when a library audit sees it. One check, two policies."""
        import shutil
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(os.path.join(FIX, "example.scn"), d)
            shutil.copy(os.path.join(BROKEN, "truncated.scn"), d)
            rc, out, _err = self._run(["audit", d])
        self.assertEqual(rc, 1)
        self.assertIn("32/0/0", out)


class SharedWithAuditTest(unittest.TestCase):
    def test_audit_reports_through_the_same_check(self):
        """audit.check_invariants must not grow a second copy of these rules."""
        from x32scene.services import audit
        lib = [("truncated.scn", load("truncated.scn"))]
        viol = audit.check_invariants(lib)
        message = V.findings(load("truncated.scn"), "scn")[0].message
        self.assertIn(f"truncated.scn: {message}", viol)


if __name__ == "__main__":
    unittest.main()
