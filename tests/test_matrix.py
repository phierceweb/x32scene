"""IEM matrix: every monitor mix at once — senders down, monitor buses across — and the
same view as a delta between two scenes."""

import contextlib
import io
import json
import os
import unittest

from x32scene import Scene
from x32scene._views_report import cmd_iem_matrix
from x32scene.cli import main
from x32scene.services import matrix as M

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")


def render(fn, *args, **kw) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kw)
    return buf.getvalue()


class ColumnsTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_default_columns_are_the_monitor_pairs_not_the_fx_sends(self):
        cols = M.monitor_buses(self.sc)
        self.assertEqual([c.bus for c in cols], [1, 3, 5, 7, 9, 11])
        self.assertEqual(cols[0].buses, (1, 2))
        self.assertEqual(cols[0].label, "1/2 Guitar L")
        self.assertEqual(M.fx_fed_buses(self.sc), {13, 14, 15, 16})

    def test_requested_buses_normalise_onto_their_pair(self):
        cols = M.monitor_buses(self.sc, [2, 13])
        self.assertEqual([(c.bus, c.buses, c.label) for c in cols],
                         [(1, (1, 2), "1/2 Guitar L"), (13, (13,), "13 Plate")])

    def test_unlinked_pair_is_two_mono_columns(self):
        self.sc.get("/config/buslink").set_arg(0, "OFF")
        cols = M.monitor_buses(self.sc, [1, 2])
        self.assertEqual([c.buses for c in cols], [(1,), (2,)])

    def test_bus_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            M.monitor_buses(self.sc, [17])


class MatrixTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_cells_carry_the_live_level_or_nothing(self):
        m = M.iem_matrix(self.sc)
        rows = {r.strip: r for r in m.rows}
        self.assertEqual(rows["/ch/01"].label, "ch01 Kick")
        self.assertEqual(rows["/ch/01"].cells[1].level, "+2.8")
        self.assertIsNone(rows["/ch/05"].cells[1].level)     # OFF in bus 1
        self.assertFalse(any(c.asym for r in m.rows for c in r.cells.values()))

    def test_rows_are_strips_with_a_live_send_unless_all(self):
        m = M.iem_matrix(self.sc, [13])
        self.assertTrue(all(r.cells[13].level for r in m.rows))
        self.assertLess(len(m.rows), 48)
        self.assertEqual(len(M.iem_matrix(self.sc, [13], all_rows=True).rows), 48)

    def test_one_sided_pair_is_flagged(self):
        self.sc.get("/ch/30/mix/02").set_arg(1, "-17.0")
        m = M.iem_matrix(self.sc, [1])
        cell = {r.strip: r for r in m.rows}["/ch/30"].cells[1]
        self.assertEqual((cell.level, cell.asym), ("-18.0", True))

    def test_compare_marks_the_moved_cells(self):
        b = Scene.load(EXAMPLE)
        b.get("/ch/23/mix/09").set_arg(1, "-11.0")
        m = M.compare(self.sc, b, [9])
        self.assertTrue(m.compare)
        cell = {r.strip: r for r in m.rows}["/ch/23"].cells[9]
        self.assertEqual((cell.before, cell.level, cell.changed), ("0.0", "-11.0", True))
        self.assertEqual(sum(c.changed for r in m.rows for c in r.cells.values()), 1)

    def test_compare_rows_are_the_union_of_live_senders(self):
        b = Scene.load(EXAMPLE)
        b.get("/ch/05/mix/01").set_arg(0, "ON")          # newly live in b
        m = M.compare(self.sc, b, [1])
        cell = {r.strip: r for r in m.rows}["/ch/05"].cells[1]
        self.assertEqual((cell.before, cell.level, cell.changed), (None, "-5.0", True))


class MatrixViewTest(unittest.TestCase):
    def test_renders_labels_levels_and_asymmetry(self):
        sc = Scene.load(EXAMPLE)
        sc.get("/ch/30/mix/02").set_arg(1, "-17.0")
        out = render(cmd_iem_matrix, M.iem_matrix(sc))
        self.assertIn("1/2 Guitar L", out)
        self.assertIn("ch01 Kick", out)
        self.assertIn("+2.8", out)
        self.assertIn("-18.0*", out)

    def test_renders_deltas(self):
        a, b = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        b.get("/ch/23/mix/09").set_arg(1, "-11.0")
        out = render(cmd_iem_matrix, M.compare(a, b, [9]))
        self.assertIn("0.0>-11.0", out)


class MatrixCliTest(unittest.TestCase):
    def test_exit_codes_and_flags(self):
        self.assertEqual(main(["iem-matrix", EXAMPLE]), 0)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["iem-matrix", EXAMPLE, "--buses", "1,3"]), 0)
        self.assertNotIn("9/10", buf.getvalue())
        self.assertEqual(main(["iem-matrix", EXAMPLE, "--compare", EXAMPLE]), 0)
        self.assertEqual(main(["iem-matrix", EXAMPLE, "--buses", "17"]), 1)

    def test_json_shape(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["iem-matrix", EXAMPLE, "--buses", "1", "--json"]), 0)
        doc = json.loads(buf.getvalue())
        self.assertEqual(doc["columns"][0], {"bus": 1, "buses": [1, 2], "label": "1/2 Guitar L"})
        row = next(r for r in doc["rows"] if r["strip"] == "/ch/01")
        self.assertEqual(row["cells"]["1"]["level"], "+2.8")


if __name__ == "__main__":
    unittest.main()
