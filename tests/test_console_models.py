"""Console models: the /xinfo spellings and product names resolve, a count is recorded only
where a manual states it, and a regenerated config carries it when a model is named."""

import json
import os
import re
import unittest
from datetime import date

from x32scene.model import Scene
from x32scene.services import preflight_monitor
from x32scene.services.console_models import MAIN_JACKS, MODELS, console_model, main_jacks
from x32scene.services.preflight import preflight
from x32scene.services.preflight_regen import dumps, regenerate

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")
EXAMPLE_ALT = os.path.join(FIXTURES, "example-alt.scn")
DAY = date(2026, 9, 12)


class ConsoleModelTest(unittest.TestCase):
    def test_xinfo_spellings_and_product_names_resolve_in_any_case(self):
        for name in ("X32RACK", "x32rack", "X32 Rack", "x32-rack", " X32 RACK "):
            with self.subTest(name=name):
                self.assertEqual(console_model(name), "X32RACK")
        self.assertEqual(main_jacks("X32 Rack"), 8)

    def test_each_count_is_the_one_its_manual_states(self):
        self.assertEqual(MAIN_JACKS, {"X32": 16, "X32P": 8, "X32C": 8, "X32RACK": 8,
                                      "X32CORE": 0, "M32": 16, "M32C": 0, "M32R": 8})
        for name, model, n in (("X32", "X32", 16), ("x32 producer", "X32P", 8),
                               ("X32 Compact", "X32C", 8), ("m32", "M32", 16),
                               ("M32R", "M32R", 8)):
            with self.subTest(name=name):
                self.assertEqual(console_model(name), model)
                self.assertEqual(main_jacks(name), n)

    def test_the_models_with_no_rear_xlr_output_have_none(self):
        for name, model in (("X32CORE", "X32CORE"), ("X32 Core", "X32CORE"), ("m32c", "M32C")):
            with self.subTest(name=name):
                self.assertEqual(console_model(name), model)
                self.assertEqual(main_jacks(name), 0)

    def test_every_xinfo_model_string_is_named(self):
        self.assertEqual(set(MODELS), {"X32", "X32P", "X32C", "X32RACK", "X32CORE", "M32",
                                       "M32C", "M32R"})
        self.assertEqual(set(MAIN_JACKS), set(MODELS))

    def test_names_and_counts_are_the_published_table(self):
        doc = os.path.join(os.path.dirname(__file__), "..", "docs", "preflight-config.md")
        with open(doc, encoding="utf-8") as fh:
            rows = re.findall(r"^\| `(\w+)` \| ([^|]+?) \| (\d+) \|", fh.read(), re.M)
        self.assertEqual({m: (p, int(n)) for m, p, n in rows},
                         {m: (MODELS[m], MAIN_JACKS[m]) for m in MODELS})

    def test_counts_fit_the_main_output_bank(self):
        for model, n in MAIN_JACKS.items():
            with self.subTest(model=model):
                self.assertTrue(0 <= n <= 16)

    def test_an_unknown_name_is_refused_listing_the_known_ones(self):
        with self.assertRaises(ValueError) as cm:
            console_model("X99")
        msg = str(cm.exception)
        self.assertIn("'X99'", msg)
        for model in MAIN_JACKS:
            self.assertIn(model, msg)



def _generated(path: str, console: str | None) -> dict:
    return json.loads(dumps(regenerate(Scene.load(path), path, DAY, console=console)))


class RegenerateWithConsoleTest(unittest.TestCase):
    def test_a_console_with_no_jacks_writes_zero_and_still_checks_clean(self):
        for path in (EXAMPLE, EXAMPLE_ALT):
            with self.subTest(scene=os.path.basename(path)):
                doc = _generated(path, "X32 Core")
                self.assertEqual(doc["monitor"]["physical_outputs"], 0)
                self.assertIn("require_reachable", doc["monitor"])
                sc = Scene.load(path)
                self.assertEqual(preflight(sc, doc), preflight(sc, {}))

    def test_writes_the_jack_count_and_reachability_and_still_checks_clean(self):
        for path in (EXAMPLE, EXAMPLE_ALT):
            with self.subTest(scene=os.path.basename(path)):
                doc = _generated(path, "x32 rack")
                self.assertEqual(set(doc["monitor"]), preflight_monitor._KEYS)
                self.assertEqual(doc["monitor"]["physical_outputs"], 8)
                self.assertIs(doc["monitor"]["require_reachable"], True)
                self.assertIn("X32 Rack", doc["_comment"])
                self.assertEqual(preflight(Scene.load(path), doc), [])

    def test_reachability_it_cannot_verify_is_written_false(self):
        with open(EXAMPLE, encoding="utf-8", newline="") as fh:
            text = fh.read()
        sc = Scene.parse("\n".join(ln for ln in text.split("\n") if not ln.startswith(
            ("/config/routing/AES50", "/config/userrout/out"))))
        doc = json.loads(dumps(regenerate(sc, EXAMPLE, DAY, console="X32RACK")))
        self.assertEqual(doc["monitor"]["physical_outputs"], 8)
        self.assertIs(doc["monitor"]["require_reachable"], False)
        self.assertEqual(preflight(sc, doc), preflight(sc, {}))

    def test_without_a_model_the_comment_says_how_to_get_the_count(self):
        doc = _generated(EXAMPLE, None)
        self.assertNotIn("physical_outputs", doc["monitor"])
        self.assertIn("--console", doc["_comment"])

    def test_an_unknown_model_is_a_value_error(self):
        with self.assertRaises(ValueError):
            regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY, console="X99")


if __name__ == "__main__":
    unittest.main()
