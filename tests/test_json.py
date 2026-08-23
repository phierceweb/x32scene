"""--json output: machine-readable views with unchanged exit codes."""
import contextlib
import io
import json
import os
import unittest

from x32scene.cli import main

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIX, "example.scn")
ALT = os.path.join(FIX, "example-alt.scn")
CONFIG = os.path.join(os.path.dirname(__file__), "..", "config",
                      "example-preflight.json")


def run_json(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(argv)
    return rc, json.loads(buf.getvalue())


class JsonTest(unittest.TestCase):
    def test_preflight_json_ok(self):
        rc, doc = run_json(["preflight", SCENE, "--config", CONFIG, "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(set(doc), {"ok", "findings", "checked"})
        self.assertEqual((doc["ok"], doc["findings"]), (True, []))
        self.assertEqual(doc["checked"]["fx"], 4)   # the example config pins four FX slots

    def test_preflight_json_finding_carries_path(self):
        from x32scene._json import preflight_doc
        from x32scene.services.preflight import Finding
        doc = preflight_doc([Finding("FAIL", "ch 01", "x", "/ch/01/config")], {"channels": 1})
        self.assertEqual(doc["findings"][0],
                         {"severity": "FAIL", "area": "ch 01", "message": "x",
                          "path": "/ch/01/config"})
        self.assertEqual(doc["checked"], {"channels": 1})

    def test_diff_json_shapes_changes(self):
        rc, doc = run_json(["diff", SCENE, ALT, "--json"])
        self.assertEqual(rc, 0)
        self.assertTrue(doc["changes"])
        c = doc["changes"][0]
        self.assertTrue({"path", "before", "after", "group", "fields"} <= set(c), c)

    def test_inputs_json(self):
        rc, doc = run_json(["inputs", SCENE, "--json"])
        self.assertEqual(doc["channels"][0],
                         {"ch": 1, "name": "Kick", "slot": 1, "source": "Local input 1"})

    def test_record_map_json(self):
        _, doc = run_json(["record-map", SCENE, "--json"])
        self.assertEqual(doc["tracks"][0], {"track": 1, "source": "Local input 1"})

    def test_fx_json(self):
        _, doc = run_json(["fx", SCENE, "--json"])
        slot1 = doc["slots"][0]
        self.assertEqual((slot1["slot"], slot1["code"]), (1, "PLAT"))
        self.assertEqual(slot1["params"]["Decay"], "2.11")

    def test_dca_json(self):
        _, doc = run_json(["dca", SCENE, "--json"])
        self.assertEqual(doc["dca"][0]["name"], "Drums")
        self.assertIn("/fxrtn/01", doc["mute_groups"][5]["members"])

    def test_iem_json_sorted(self):
        _, doc = run_json(["iem", SCENE, "3", "--json"])
        levels = [s["level_db"] for s in doc["sends"]]
        self.assertEqual(levels, sorted(levels, reverse=True))
