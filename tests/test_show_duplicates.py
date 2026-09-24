"""show --check: a scene, snippet or cue slot listed twice in a .shw is a finding. What
X32-Edit or the desk does with one is unknown, so the check does not pick a line."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.services.show import read_show
from x32scene.services.show_check import check_show

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SHW = os.path.join(FIX, "example.shw")


def _read(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def _companions(name):
    return _read(os.path.join(FIX, "example.scn" if name.endswith(".scn") else "example.snp"))


class ServiceTest(unittest.TestCase):
    def test_the_fixture_has_no_duplicates(self):
        self.assertEqual(check_show(read_show(_read(SHW)), "example", _companions), [])

    def test_each_duplicated_slot_is_one_finding_naming_its_count(self):
        text = _read(SHW)
        text += 'scene/000 "Other" "" %000000000 1\n' * 2
        text += 'cue/001 200 "Again" 0 0 0 0 1 0 0\n'
        text += 'snippet/000 "Example EQ" 4 1 0 0 1\n'
        found = [f for f in check_show(read_show(text), "example", _companions)
                 if f.area == "duplicate"]
        self.assertEqual([(f.severity, f.path) for f in found],
                         [("FAIL", "cue/001"), ("FAIL", "scene/000"), ("FAIL", "snippet/000")])
        self.assertIn("3 times", found[1].message)
        self.assertIn("2 times", found[0].message)

    def test_a_duplicated_slot_reads_its_companion_once(self):
        text = _read(SHW) + 'scene/000 "Other" "" %000000000 1\n'
        reads = []

        def read(name):
            reads.append(name)
            raise FileNotFoundError(name)

        found = check_show(read_show(text), "example", read)
        self.assertEqual(reads.count("example.000.scn"), 1)
        self.assertEqual(sum("missing" in f.message for f in found), 2)   # .scn and .snp


class CommandTest(unittest.TestCase):
    def test_a_duplicate_exits_1_in_text_and_json(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        shw = os.path.join(d, "Night.shw")
        with open(shw, "w", encoding="utf-8") as fh:
            fh.write(_read(SHW) + 'cue/000 300 "Twice" 0 -1 -1 0 1 0 0\n')
        shutil.copy(os.path.join(FIX, "example.scn"), os.path.join(d, "Night.000.scn"))
        shutil.copy(os.path.join(FIX, "example.snp"), os.path.join(d, "Night.000.snp"))
        for extra in ([], ["--json"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = main(["show", shw, "--check", *extra])
            with self.subTest(extra=extra):
                self.assertEqual(rc, 1)
                if extra:
                    doc = json.loads(out.getvalue())
                    self.assertEqual([f["path"] for f in doc["findings"]], ["cue/000"])
                else:
                    self.assertIn("cue/000", out.getvalue())
                    self.assertIn("2 times", out.getvalue())


if __name__ == "__main__":
    unittest.main()
