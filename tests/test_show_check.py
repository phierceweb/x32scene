"""show --check: every cue's slots are in the index, and every slot's companion file is next
to the .shw, reads as its kind and, for a snippet, carries the header its index line copies."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.services.show import read_show
from x32scene.services.show_check import check_cues, check_show, companion

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCN = os.path.join(FIX, "example.scn")
SNP = os.path.join(FIX, "example.snp")
SHW = os.path.join(FIX, "example.shw")


def _read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(p, text):
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class ServiceTest(unittest.TestCase):
    def test_cue_slots_resolve_against_the_index(self):
        show = read_show('#4.0#\nshow "s" 0 "w"\n'
                         'cue/000 100 "Opener" 0 0 -1 0 1 0 0\n'
                         'cue/001 200 "Encore" 0 3 1 0 1 0 0\n'
                         'cue/002 300\n'
                         'scene/000 "A" "" %000000000 1\n')
        found = check_cues(show)
        self.assertEqual([(f.severity, f.path) for f in found],
                         [("FAIL", "cue/001"), ("FAIL", "cue/001"), ("FAIL", "cue/002")])
        self.assertIn("scene 3", found[0].message)
        self.assertIn("snippet 1", found[1].message)

    def test_companion_names_follow_the_show_file(self):
        show = read_show(_read(SHW))
        self.assertEqual(companion("Night", show.of("scene")[0]), "Night.000.scn")
        self.assertEqual(companion("Night", show.of("snippet")[0]), "Night.000.snp")

    def test_reader_errors_become_findings(self):
        show = read_show(_read(SHW))

        def read(name):
            if name.endswith(".scn"):
                raise FileNotFoundError(name)
            raise ValueError(f"{name}: not a console text file")

        found = check_show(show, "example", read)
        self.assertEqual([f.path for f in found], ["scene/000", "snippet/000"])
        self.assertIn("missing", found[0].message)
        self.assertIn("not a console text file", found[1].message)


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _build(self):
        rc, _, err = _run("show-build", "-o", self.tmp, "--name", "Night", "--scene", SCN,
                          "--snippet", SNP, "--cue", "1 Opener scene=0",
                          "--cue", "2 Encore scene=0 snippet=0")
        self.assertEqual(rc, 0, err)
        return os.path.join(self.tmp, "Night.shw")

    def test_fixture_with_companions_passes(self):
        shutil.copy(SHW, os.path.join(self.tmp, "example.shw"))
        shutil.copy(SCN, os.path.join(self.tmp, "example.000.scn"))
        shutil.copy(SNP, os.path.join(self.tmp, "example.000.snp"))
        rc, out, _ = _run("show", os.path.join(self.tmp, "example.shw"), "--check")
        self.assertEqual(rc, 0, out)
        self.assertIn("SHOW OK", out)

    def test_a_file_with_no_show_line_fails(self):
        empty, header_only = os.path.join(self.tmp, "a.shw"), os.path.join(self.tmp, "b.shw")
        _write(empty, "")
        _write(header_only, "#4.0#\n")
        for path in (empty, header_only, SCN):
            with self.subTest(path=os.path.basename(path)):
                rc, out, _ = _run("show", path, "--check")
                self.assertEqual(rc, 1, out)
                self.assertNotIn("SHOW OK", out)
                self.assertRegex(out, r"FAIL\s+show\s+no show line")

    def test_a_cue_with_a_non_numeric_slot_is_a_fail_not_a_crash(self):
        shw = os.path.join(self.tmp, "s.shw")
        _write(shw, _read(SHW).replace('cue/000 100 "Opener" 0 0 0', 'cue/000 100 "Opener" 0 x 0', 1))
        rc, out, err = _run("show", shw, "--check")
        self.assertEqual(rc, 1, err)
        self.assertRegex(out, r"FAIL\s+cue/000\s+not a cue line")
        self.assertNotIn("invalid literal", err)
        rc, out, err = _run("show", shw)
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("cue/000", out)

    def test_fixture_alone_has_no_companions(self):
        rc, out, _ = _run("show", SHW, "--check")
        self.assertEqual(rc, 1)
        fails = [ln for ln in out.splitlines() if ln.strip().startswith("FAIL")]
        self.assertEqual(len(fails), 2)
        self.assertIn("example.000.scn", fails[0])
        self.assertIn("example.000.snp", fails[1])

    def test_built_show_passes(self):
        rc, out, _ = _run("show", self._build(), "--check")
        self.assertEqual((rc, out.strip()),
                         (0, "SHOW OK — 2 cue(s), 1 scene(s), 1 snippet(s)"))

    def test_missing_companion(self):
        shw = self._build()
        os.remove(os.path.join(self.tmp, "Night.000.snp"))
        rc, out, _ = _run("show", shw, "--check")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"FAIL\s+snippet/000\s+Night\.000\.snp is missing")

    def test_mismatched_snippet_header(self):
        shw = self._build()
        snp = os.path.join(self.tmp, "Night.000.snp")
        _write(snp, _read(snp).replace('"Example EQ" 4 1', '"Example EQ" 4 3', 1))
        rc, out, _ = _run("show", shw, "--check")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"FAIL\s+snippet/000\s+Night\.000\.snp: header")

    def test_cue_pointing_at_an_absent_scene(self):
        shw = self._build()
        _write(shw, _read(shw).replace('"Encore" 0 0 0', '"Encore" 0 4 0', 1))
        rc, out, _ = _run("show", shw, "--check")
        self.assertEqual(rc, 1)
        lines = [ln for ln in out.splitlines() if ln.strip().startswith("FAIL")]
        self.assertEqual(len(lines), 1, out)
        self.assertRegex(lines[0], r"FAIL\s+cue/001\s+.*scene 4 .*scene/004")

    def test_truncated_scene_companion_is_a_shape_failure(self):
        shw = self._build()
        scn = os.path.join(self.tmp, "Night.000.scn")
        _write(scn, "\n".join(_read(scn).split("\n")[:50]) + "\n")
        rc, out, _ = _run("show", shw, "--check")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"FAIL\s+scene/000\s+Night\.000\.scn: strips")

    def test_companion_of_the_wrong_kind(self):
        shw = self._build()
        shutil.copy(SNP, os.path.join(self.tmp, "Night.000.scn"))
        rc, out, _ = _run("show", shw, "--check")
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"FAIL\s+scene/000\s+Night\.000\.scn: .*snippet, not a scene")

    def test_json(self):
        shw = self._build()
        os.remove(os.path.join(self.tmp, "Night.000.scn"))
        rc, out, _ = _run("show", shw, "--check", "--json")
        self.assertEqual(rc, 1)
        doc = json.loads(out)
        self.assertFalse(doc["ok"])
        self.assertEqual([(f["severity"], f["path"]) for f in doc["findings"]],
                         [("FAIL", "scene/000")])
        self.assertEqual(doc["checked"], {"cues": 2, "scenes": 1, "snippets": 1})

    def test_listing_is_unchanged_without_check(self):
        rc, out, _ = _run("show", SHW)
        self.assertEqual(rc, 0)
        self.assertIn("cue/000", out)


if __name__ == "__main__":
    unittest.main()
