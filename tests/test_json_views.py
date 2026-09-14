"""--json on info, buses, explain, audit and live-diff."""
import contextlib
import functools
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.test_osc import CANNED, FakeConsole
from x32scene.cli import main
from x32scene.services import osc as O

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIX, "example.scn")


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def run_json(argv):
    rc, out, _ = run(argv)
    return rc, json.loads(out)


class SceneViewsJsonTest(unittest.TestCase):
    def test_info_carries_title_line_count_and_names(self):
        rc, doc = run_json(["info", SCENE, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(set(doc), {"title", "lines", "channels", "buses"})
        _, text, _ = run(["info", SCENE])
        self.assertIn(f"title: {doc['title']!r}   lines: {doc['lines']}", text)
        self.assertEqual(len(doc["channels"]), 32)
        for c in doc["channels"]:
            self.assertIn(f"ch{c['ch']:02d}  {c['name']}", text)
        self.assertEqual([b["bus"] for b in doc["buses"]], list(range(1, 17)))
        self.assertIn(f"bus01  {doc['buses'][0]['name']}", text)

    def test_buses_carries_link_fx_and_send_taps(self):
        rc, doc = run_json(["buses", SCENE, "--json"])
        self.assertEqual(rc, 0)
        rows = doc["buses"]
        self.assertEqual([r["bus"] for r in rows], list(range(1, 17)))
        self.assertEqual(set(rows[0]), {"bus", "name", "linked", "fx", "sends"})
        self.assertEqual((rows[0]["name"], rows[0]["linked"]), ("Guitar L", True))
        self.assertEqual(rows[1]["linked"], True)
        self.assertEqual(rows[0]["sends"]["PRE"], 40)
        self.assertEqual(rows[1]["sends"], {"PRE": 0, "POST": 0})
        _, text, _ = run(["buses", SCENE])
        self.assertTrue(any(r["fx"] for r in rows))
        for r in rows:
            fx = r["fx"]
            if fx is not None:
                self.assertEqual(set(fx), {"slot", "type", "name"})
                self.assertIn(f"-> FX{fx['slot']} ({fx['name']})", text)

    def test_explain_nests_each_views_own_document(self):
        from x32scene import _json
        from x32scene.model import Scene
        rc, doc = run_json(["explain", SCENE, "--json"])
        self.assertEqual(rc, 0)
        sc = Scene.load(SCENE)
        self.assertEqual(doc["title"], sc.name)
        self.assertEqual(doc["inputs"], _json.inputs_doc(sc))
        self.assertEqual(doc["outputs"], _json.ports_doc(sc, "all"))
        self.assertEqual(doc["record_map"], _json.record_map_doc(sc))
        self.assertEqual(doc["fx"], _json.fx_doc(sc))
        self.assertEqual(doc["groups"], _json.groups_doc(sc))
        self.assertEqual(doc["buses"], run_json(["buses", SCENE, "--json"])[1])

    def test_text_views_still_print_without_the_flag(self):
        for cmd in ("info", "buses", "explain"):
            with self.subTest(cmd=cmd):
                rc, out, _ = run([cmd, SCENE])
                self.assertEqual(rc, 0)
                self.assertFalse(out.lstrip().startswith("{"))


class AuditJsonTest(unittest.TestCase):
    def test_clean_library_is_ok_with_drift_sections(self):
        rc, doc = run_json(["audit", FIX, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(set(doc), {"ok", "dir", "scenes", "load_errors", "violations",
                                    "routing", "record_patch"})
        self.assertEqual((doc["ok"], doc["scenes"], doc["load_errors"], doc["violations"]),
                         (True, 2, [], []))
        _, text, _ = run(["audit", FIX])
        for entry in doc["routing"]:
            self.assertEqual(set(entry), {"scene", "IN", "AES50A", "AES50B"})
            self.assertIn(f"[{entry['scene']}]", text)
            self.assertIn("AES50B " + " ".join(entry["AES50B"]), text)
        for entry in doc["record_patch"]:
            nonzero = " ".join(x for x in entry["slots"] if x != "0")
            self.assertIn(f"[{entry['scene']}] {nonzero}", text)

    def test_violation_and_load_error_fail_with_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(SCENE, d)
            open(os.path.join(d, "truncated.scn"), "w").close()
            with open(os.path.join(d, "crlf.scn"), "w", newline="") as fh:
                fh.write('#4.0# "X" "" %000000000 1\r\n')
            rc, doc = run_json(["audit", d, "--json"])
        self.assertEqual(rc, 1)
        self.assertFalse(doc["ok"])
        self.assertTrue(any("crlf.scn" in e for e in doc["load_errors"]), doc)
        self.assertTrue(any("truncated.scn" in v for v in doc["violations"]), doc)


class LiveDiffJsonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.console = FakeConsole()
        cls.console.start()

    @classmethod
    def tearDownClass(cls):
        cls.console.stop()

    def _reference(self, d):
        lines = dict(CANNED)
        lines["ch/01/config"] = '/ch/01/config "Snare" 2 YEi 1'
        path = os.path.join(d, "ref.scn")
        with open(path, "w") as fh:
            fh.write('#4.0# "REF" "" %000000000 1\n' + "\n".join(lines.values())
                     + '\n/ch/02/config "Tom" 3 GN 2\n')
        return path

    def _pull(self, argv):
        real = functools.partial(O.pull_scene_like, port=self.console.port)
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(O, "pull_scene_like", real):
            return run(["live-diff", self._reference(d), "--ip", "127.0.0.1",
                        "--timeout", "0.1", *argv])

    def test_json_carries_changes_and_unanswered_with_warnings_on_stderr(self):
        rc, out, err = self._pull(["--json"])
        self.assertEqual(rc, 0)
        doc = json.loads(out)
        self.assertEqual(set(doc), {"changes", "unanswered"})
        self.assertEqual(doc["unanswered"], ["ch/02/config"])
        paths = {c["path"]: c for c in doc["changes"]}
        self.assertIn("/ch/01/config", paths)
        change = paths["/ch/01/config"]
        self.assertEqual((change["before"], change["after"]),
                         ('/ch/01/config "Snare" 2 YEi 1', '/ch/01/config "Kick" 2 YEi 1'))
        self.assertIn("fields", change)
        self.assertIn("unanswered paths (1)", err)

    def test_text_output_unchanged(self):
        rc, out, err = self._pull([])
        self.assertEqual(rc, 0)
        self.assertIn("/ch/01/config", out)
        self.assertIn("unanswered paths (1)", err)

    def test_failed_pull_exits_2_with_nothing_on_stdout(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(O, "pull_scene_like", side_effect=O.OscError("no reply")):
            rc, out, err = run(["live-diff", self._reference(d), "--ip", "127.0.0.1",
                                "--json"])
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("pull failed", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
