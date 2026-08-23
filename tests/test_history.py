"""history: one path's timeline across a date-ordered scene library."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.history import history

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EXAMPLE_ALT = os.path.join(FIX, "example-alt.scn")


class HistoryTest(unittest.TestCase):
    def test_records_a_line_each_time_it_changes(self):
        a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE_ALT)
        lib = [("one", a), ("two", b), ("three", Scene.load(EXAMPLE))]
        h = history(lib, "/outputs/main/05")
        self.assertEqual([n for n, _ in h], ["one", "two", "three"])
        self.assertEqual(h[0][1], "/outputs/main/05 14 POST OFF")
        self.assertEqual(h[1][1], "/outputs/main/05 8 POST OFF")
        self.assertEqual(h[2][1], h[0][1])

    def test_unchanged_line_is_one_entry(self):
        lib = [("one", Scene.load(EXAMPLE)), ("two", Scene.load(EXAMPLE_ALT))]
        self.assertEqual(len(history(lib, "/outputs/main/01")), 1)

    def test_absence_is_an_entry_not_a_gap(self):
        c = Scene.load(EXAMPLE)
        c.lines = [ln for ln in c.lines if ln.path != "/fx/1"]
        c._reindex()
        lib = [("one", Scene.load(EXAMPLE)), ("two", c), ("three", Scene.load(EXAMPLE))]
        h = history(lib, "/fx/1")
        self.assertEqual([raw for _, raw in h], ["/fx/1 PLAT", None, "/fx/1 PLAT"])

    def test_path_never_present_is_empty(self):
        self.assertEqual(history([("one", Scene.load(EXAMPLE))], "/nope"), [])


class HistoryCliTest(unittest.TestCase):
    def test_cli_walks_a_directory_in_date_order_and_names_fields(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(EXAMPLE, os.path.join(d, "Rig - 2025-01-10.scn"))
            shutil.copy(EXAMPLE_ALT, os.path.join(d, "Rig - 2025-03-02.scn"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["history", "--dir", d, "/outputs/main/05", "/config/routing/AES50A"])
            out = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertLess(out.index("2025-01-10"), out.index("2025-03-02"))
            self.assertIn("src 14 (Bus 11) -> 8 (Bus 5)", out)
            self.assertIn("block 2 OUT9-16 -> UOUT9-16", out)

    def test_cli_json(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(EXAMPLE, os.path.join(d, "a-2025-01-10.scn"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["history", "--dir", d, "/fx/1", "--json"]), 0)
            doc = json.loads(buf.getvalue())
            self.assertEqual(doc["paths"]["/fx/1"], [{"scene": "a-2025-01-10.scn", "line": "/fx/1 PLAT"}])

    def test_cli_needs_a_directory(self):
        from unittest import mock
        with mock.patch.dict(os.environ):
            os.environ.pop("X32SCENE_CORPUS", None)
            self.assertEqual(main(["history", "/fx/1"]), 1)


if __name__ == "__main__":
    unittest.main()
