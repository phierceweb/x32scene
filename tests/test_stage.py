"""The stage sidecar: what the .scn cannot hold, validated whole on load, checked against
the scene by preflight, and rendered by ports."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from x32scene import Scene
from x32scene._views_ports import cmd_ports
from x32scene.cli import main
from x32scene.services import stage as S
from x32scene.services.preflight import coverage, preflight

from tests.preflight_scene import fails, mini_scene

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
SCENE = os.path.join(FIX, "example.scn")
CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "example-preflight.json")
STAGE = os.path.join(os.path.dirname(__file__), "..", "config", "example-stage.json")
ENTRY = {"jack": "Box A out 1", "box": "Stagebox A", "device": "IEM TX 1", "wearer": "Drums",
         "bus": 3}
SIDE = {"outputs": {"main": {"9": ENTRY, "10": {**ENTRY, "jack": "Box A out 2", "bus": 4}},
                    "aux": {"1": {"jack": "Aux out 1", "device": "Headphone amp",
                                  "wearer": "Bass", "bus": 7}}}}


def doc(**outputs):
    return {"outputs": outputs}


def one_fail(findings, *needles):
    fs = fails(findings)
    assert len(fs) == 1, fs
    for n in needles:
        assert n in fs[0].message or n in fs[0].area, (n, fs[0])
    return fs[0]


def render(fn, *args, **kw) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kw)
    return buf.getvalue()


class ValidateTest(unittest.TestCase):
    def test_example_sidecar_loads(self):
        d = S.load_stage(STAGE)
        self.assertIn(("main", 9), S.stage_entries(d))
        self.assertEqual(S.stage_entries(d)[("aux", 1)]["wearer"], "Bass")

    def test_rejections_name_the_problem(self):
        cases = [
            ([], "must be an object"),
            ({"output": {}}, "unknown key 'output'"),
            ({"outputs": []}, "outputs must be an object"),
            (doc(p17={}), "unknown bank 'p17'"),
            (doc(main={"17": ENTRY}), "out of range 1-16"),
            (doc(main={"x": ENTRY}), "not a number"),
            (doc(main={"9": ENTRY, "09": ENTRY}), "both name 9"),
            (doc(main={"9": "Box A"}), "must be an object"),
            (doc(main={"9": {**ENTRY, "person": "x"}}), "unknown key 'person'"),
            (doc(main={"9": {**ENTRY, "bus": 17}}), "bus must be a whole number 1-16"),
            (doc(main={"9": {**ENTRY, "jack": 1}}), "jack must be a string"),
            (doc(main={"9": ENTRY, "10": ENTRY}), "claim the same jack"),
        ]
        for bad, needle in cases:
            with self.subTest(needle=needle):
                with self.assertRaises(ValueError) as cm:
                    S.validate_stage(bad)
                self.assertIn(needle, str(cm.exception))

    def test_same_jack_label_on_two_boxes_is_fine(self):
        S.validate_stage(doc(main={"9": {**ENTRY, "box": "A"},
                                   "10": {**ENTRY, "box": "B", "bus": 4}}))

    def test_comment_keys_are_ignored(self):
        S.validate_stage({"_comment": "x", "outputs": {"_c": "y", "main": {"_n": "z", "9": ENTRY}}})


class StageCheckTest(unittest.TestCase):
    def test_fixture_agrees_with_the_sidecar(self):
        self.assertEqual(preflight(mini_scene(), {}, stage=SIDE), [])

    def test_missing_documented_output_fails(self):
        sc = mini_scene({"/outputs/main/09": None})
        fs = [f for f in fails(preflight(sc, {}, stage=SIDE)) if f.area == "stage main 09"]
        self.assertEqual(len(fs), 1, fs)
        self.assertIn("no such line", fs[0].message)

    def test_documented_output_carrying_nothing_fails(self):
        sc = mini_scene({"/outputs/main/09": "/outputs/main/09 0 POST OFF"})
        f = one_fail(preflight(sc, {}, stage=SIDE), "stage main 09", "Drums", "carries nothing")
        self.assertEqual(f.path, "/outputs/main/09")

    def test_repointed_output_fails_against_the_documented_bus(self):
        sc = mini_scene({"/outputs/main/09": "/outputs/main/09 4 POST OFF"})
        one_fail(preflight(sc, {}, stage=SIDE), "stage main 09", "Bus 1", "documented as bus 3",
                 "Drums")

    def test_sidecar_and_config_disagreeing_is_a_finding(self):
        exp = {"outputs": {"main": {"9": {"bus": 4}}}}
        fs = fails(preflight(mini_scene(), exp, stage=SIDE))
        self.assertTrue(any(f.area == "stage main 09" and "disagree" in f.message for f in fs), fs)

    def test_bus_is_optional(self):
        side = doc(main={"7": {"jack": "XLR out 7", "device": "House PA", "wearer": "Room"}})
        self.assertEqual(preflight(mini_scene(), {}, stage=side), [])

    def test_coverage_counts_sidecar_entries(self):
        self.assertEqual(coverage({}, SIDE), {"stage": 3})
        self.assertEqual(coverage({}), {})


class PortsRenderTest(unittest.TestCase):
    def test_ports_with_sidecar_names_jack_and_wearer(self):
        out = render(cmd_ports, Scene.load(SCENE), 8, bank="main", stage=SIDE)
        self.assertIn("Box A out 1", out)
        self.assertIn("Drums", out)
        self.assertIn("unconfirmed", out)

    def test_ports_all_banks(self):
        out = render(cmd_ports, Scene.load(SCENE), bank="all")
        for needle in ("main 01", "aux 01", "p16 01", "aes 01", "rec 01", "<-EQ"):
            self.assertIn(needle, out)


class StageCliTest(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ)
        self._env.start()
        os.environ.pop("X32SCENE_STAGE", None)
        os.environ.pop("X32SCENE_CONFIG", None)

    def tearDown(self):
        self._env.stop()

    def test_preflight_and_ports_take_a_sidecar(self):
        self.assertEqual(main(["preflight", SCENE, "--config", CONFIG, "--stage", STAGE]), 0)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["ports", SCENE, "--bank", "all", "--stage", STAGE,
                                   "--config", CONFIG]), 0)
        out = buf.getvalue()
        self.assertIn("[virt]", out)   # the example config declares physical_outputs
        self.assertIn("IEM TX 1", out)

    def test_ports_json(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["ports", SCENE, "--bank", "rec", "--json", "--stage", STAGE]), 0)
        d = json.loads(buf.getvalue())
        self.assertEqual((d["outputs"][0]["bank"], d["outputs"][0]["pos"]), ("rec", "<-EQ"))
        self.assertIsNone(d["outputs"][0]["stage"])

    def test_malformed_sidecar_is_one_stderr_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.json")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write('{"outputs": {"main": {"9": {"person": "x"}}}}')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main(["preflight", SCENE, "--config", CONFIG, "--stage", p]), 1)
            self.assertIn("unknown key 'person'", err.getvalue())

    def test_stage_env_var_is_the_default(self):
        with mock.patch.dict(os.environ, {"X32SCENE_STAGE": STAGE}):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["ports", SCENE]), 0)
            self.assertIn("IEM TX 1", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
