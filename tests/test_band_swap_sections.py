"""band-setup's processing, FX, routing and output-patch sections: applied in order,
whitelisted exactly, validated whole, and written as a snippet on request."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene
from x32scene.orchestrators.band_swap import apply_plan, run, verify
from x32scene.services.snippets import read_header

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIX, "example.scn")
EFX = os.path.join(FIX, "example.efx")
ROU = os.path.join(FIX, "example.rou")
PLAN_EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "example-plan.json")

PLAN = {
    "channels": {
        "1": {"lowcut": {"on": True, "freq": 40},
              "eq": {"2": {"type": "PEQ", "freq": 100, "gain": 3.0, "q": 1.5}},
              "comp": {"thr": -18, "ratio": "3"}, "gate": {"thr": -45, "range": 40}},
        "5": {"source": "aes50-a 3", "pan": -25},
    },
    "fx": {"4": {"type": "HALL", "source": "MIX15,MIX16", "params": {"Decay": 2.1}},
           "2": {"preset": EFX}},
    "routing": {"switch": "PLAY", "IN": {"1-8": "A1-8"}, "preset": ROU, "banks": ["CARD"]},
    "output_patch": {"main": {"11": {"src": "bus 12", "pos": "PRE+M"}},
                     "p16": {"1": {"src": "direct out ch 5"}},
                     "rec": {"1": {"src": "main r"}}},
}


class SectionsApplyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpl = Scene.load(EXAMPLE)
        cls.sc = Scene.load(EXAMPLE)
        apply_plan(cls.sc, PLAN)
        cls.report = verify(cls.tmpl, cls.sc, PLAN)

    def test_nothing_outside_the_plan_moved(self):
        self.assertEqual(self.report["unexpected"], [])
        self.assertEqual(self.report["malformed"], [])
        self.assertEqual(set(self.report["changed"]), {
            "/ch/01/preamp", "/ch/01/eq/2", "/ch/01/dyn", "/ch/01/gate", "/ch/05/config",
            "/ch/05/mix", "/fx/4", "/fx/4/source", "/fx/4/par", "/fx/2", "/fx/2/par",
            "/config/routing", "/config/routing/IN", "/outputs/main/11", "/outputs/p16/01",
            "/outputs/rec/01"})   # CARD from the preset equals the fixture, so it is unchanged

    def test_channel_values(self):
        self.assertEqual(self.sc.get("/ch/01/eq/2").args, ["PEQ", "100.0", "+3.00", "1.5"])
        self.assertEqual(self.sc.get("/ch/01/dyn").args[4:6], ["-18.0", "3.0"])
        self.assertEqual(self.sc.get("/ch/01/gate").args[2:4], ["-45.0", "40.0"])
        self.assertEqual(self.sc.get("/ch/01/preamp").args[2:5], ["ON", "24", "40"])
        self.assertEqual(self.sc.get("/ch/05/config").args[-1], "35")
        self.assertEqual(self.sc.get("/ch/05/mix").args[3], "-25")

    def test_fx_routing_and_outputs(self):
        self.assertEqual(self.sc.get("/fx/4").args, ["HALL"])
        self.assertEqual(self.sc.get("/fx/4/source").args, ["MIX15", "MIX16"])
        self.assertEqual(self.sc.get("/fx/4/par").args[1], "2.10")
        self.assertEqual(self.sc.get("/fx/2").args, ["PLAT"])
        self.assertEqual(self.sc.get("/config/routing").args, ["PLAY"])
        self.assertEqual(self.sc.get("/config/routing/IN").args[0], "A1-8")
        self.assertEqual(self.sc.get("/outputs/main/11").args[:2], ["15", "PRE+M"])
        self.assertEqual(self.sc.get("/outputs/p16/01").args[0], "30")
        self.assertEqual(self.sc.get("/outputs/rec/01").args[0], "2")

    def test_round_trip(self):
        text = self.sc.dump()
        self.assertEqual(Scene.parse(text).dump(), text)


class SectionsValidationTest(unittest.TestCase):
    def _bad(self, plan: dict, fragment: str):
        with self.assertRaises(ValueError) as cm:
            apply_plan(Scene.load(EXAMPLE), plan)
        self.assertIn(fragment, str(cm.exception))

    def test_typos_and_bad_values_raise_before_any_write(self):
        self._bad({"channels": {"1": {"eq": {"7": {"gain": 1}}}}}, "band must be 1-6")
        self._bad({"channels": {"1": {"eq": {"2": {"gian": 1}}}}}, "unknown key")
        self._bad({"channels": {"1": {"comp": {"thr": "loud"}}}}, "must be a number")
        self._bad({"channels": {"1": {"pan": 150}}}, "pan must be")
        self._bad({"channels": {"1": {"source": "moon 3"}}}, "source")
        self._bad({"fx": {"9": {"type": "HALL"}}}, "out of range 1-8")
        self._bad({"fx": {"5": {"type": "HALL"}}}, "cannot go in FX5")
        self._bad({"fx": {"1": {"type": "PLAT", "params": {"Nope": 1}}}}, "not a PLAT parameter")
        self._bad({"fx": {"1": {"source": "BUS9"}}}, "must be INS")
        self._bad({"fx": {"1": {}}}, "does nothing")
        self._bad({"routing": {"IN": {"1-8": "OUT1-8"}}}, "not a console token")
        self._bad({"routing": {"OUT": {"1-8": "AN1-4"}}}, "blocks are")
        self._bad({"routing": {"switch": "ON"}}, "REC or PLAY")
        self._bad({"output_patch": {"xlr": {"1": {"src": "off"}}}}, "bank must be")
        self._bad({"output_patch": {"main": {"17": {"src": "off"}}}}, "out of range 1-16")
        self._bad({"output_patch": {"main": {"1": {"pos": "LATE"}}}}, "pos must be")
        self._bad({"output_patch": {"rec": {"1": {"invert": True}}}}, "invert")
        self._bad({"output_patch": {"main": {"1": {"src": "kitchen"}}}}, "unknown output source")

    def test_example_plan_validates_and_runs(self):
        with open(PLAN_EXAMPLE, encoding="utf-8") as fh:
            plan = json.load(fh)
        plan["_dir"] = os.path.dirname(PLAN_EXAMPLE)
        with tempfile.TemporaryDirectory() as d:
            rep = run(EXAMPLE, plan, os.path.join(d, "out.scn"))
        self.assertEqual(rep["unexpected"], [])
        self.assertIn("/fx/4/par", rep["changed"])


class SnippetFlagTest(unittest.TestCase):
    def test_band_setup_writes_the_delta_as_a_snippet(self):
        with tempfile.TemporaryDirectory() as d:
            plan_path = os.path.join(d, "plan.json")
            with open(plan_path, "w", encoding="utf-8") as fh:
                json.dump({"channels": {"1": {"eq": {"2": {"gain": 3.0}}}},
                           "output_patch": {"main": {"11": {"pos": "PRE"}}}}, fh)
            out, snp = os.path.join(d, "o.scn"), os.path.join(d, "o.snp")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["band-setup", EXAMPLE, plan_path, "-o", out,
                                       "--snippet", snp]), 0)
            self.assertIn(f"wrote {snp}: 2 lines", buf.getvalue())
            with open(snp, encoding="utf-8") as fh:
                text = fh.read()
            h = read_header(text)
            self.assertEqual(h.describe()["filters"], ["EQ", "Out Patch"])
            self.assertEqual(h.describe()["channels"], ["ch01"])
            self.assertEqual([ln.split(" ")[0] for ln in text.split("\n")[1:] if ln],
                             ["/ch/01/eq/2", "/outputs/main/11"])


if __name__ == "__main__":
    unittest.main()
