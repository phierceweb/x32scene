"""preflight --regenerate on a damaged scene: a value its line cannot support is left out, so
the damaged scene checks as it would with no config, and the intact scene breaks no claim."""

import json
import math
import os
import random
import re
import unittest
from datetime import date

from x32scene.model import Scene
from x32scene.services.preflight import coverage, preflight
from x32scene.services.preflight_regen import dumps, regenerate
from x32scene.tables import bus_to_tap

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")
DAY = date(2026, 9, 12)


def _text() -> str:
    with open(EXAMPLE, encoding="utf-8", newline="") as fh:
        return fh.read()


def _regen(text: str) -> tuple[Scene, dict, str]:
    sc = Scene.parse(text)
    written = dumps(regenerate(sc, EXAMPLE, DAY))
    return sc, json.loads(written), written


def _drop(text: str, pattern: str) -> str:
    kept = [ln for ln in text.split("\n") if not re.match(pattern, ln)]
    assert len(kept) < text.count("\n") + 1, pattern
    return "\n".join(kept)


class DamagedSceneTest(unittest.TestCase):
    def assertHonest(self, damaged: str, doc: dict) -> None:
        sc = Scene.parse(damaged)
        self.assertEqual(preflight(sc, doc), preflight(sc, {}))
        self.assertEqual(preflight(Scene.parse(_text()), doc), [])

    def _replaced(self, old: str, new: str) -> str:
        text = _text()
        self.assertIn(old, text)
        return text.replace(old, new, 1)

    def test_a_bad_token_leaves_its_value_out_instead_of_aborting(self):
        userrout = re.search(r"^/config/userrout/in 1 ", _text(), re.M).group(0)
        cases = {
            "short channel config": ('/ch/01/config "Kick" 2 YEi 1', '/ch/01/config "Kick"',
                                     ("source", "gain", "phantom")),
            "non-numeric slot": ('/ch/01/config "Kick" 2 YEi 1', '/ch/01/config "Kick" 2 YEi X',
                                 ("source", "gain", "phantom")),
            "gain abc": ("/headamp/000 +27.0 OFF", "/headamp/000 abc OFF", ("gain",)),
            "gain -oo": ("/headamp/000 +27.0 OFF", "/headamp/000 -oo OFF", ("gain",)),
            "gain nan": ("/headamp/000 +27.0 OFF", "/headamp/000 nan OFF", ("gain",)),
            "gain inf": ("/headamp/000 +27.0 OFF", "/headamp/000 inf OFF", ("gain",)),
            "user-in slot": (userrout, userrout.replace(" 1 ", " X ", 1),
                             ("source", "gain", "phantom")),
        }
        for case, (old, new, dropped) in cases.items():
            with self.subTest(case=case):
                damaged = self._replaced(old, new)
                _, doc, written = _regen(damaged)
                self.assertNotIn("NaN", written)
                self.assertNotIn("Infinity", written)
                for key in dropped:
                    self.assertNotIn(key, doc["channels"]["1"])
                self.assertEqual(doc["channels"]["1"]["name"], "Kick")
                self.assertHonest(damaged, doc)

    def test_every_written_gain_is_finite(self):
        _, doc, _ = _regen(_text())
        self.assertTrue(all(math.isfinite(c["gain"]) for c in doc["channels"].values()
                            if "gain" in c))

    def test_a_non_numeric_user_out_slot_leaves_the_record_map_out(self):
        line = re.search(r"^/config/userrout/out .*$", _text(), re.M).group(0)
        damaged = self._replaced(line, line.replace(" 1 ", " X ", 1))
        _, doc, _ = _regen(damaged)
        self.assertNotIn("record", doc)
        self.assertHonest(damaged, doc)

    def test_a_short_user_out_line_leaves_out_the_tracks_it_cannot_resolve(self):
        line = re.search(r"^/config/userrout/out .*$", _text(), re.M).group(0)
        damaged = self._replaced(line, "/config/userrout/out 1 2 3")
        _, doc, _ = _regen(damaged)
        self.assertEqual(sorted(doc["record"], key=int), ["1", "2", "3"])
        self.assertNotIn("?", doc["record"].values())
        self.assertHonest(damaged, doc)

    def test_a_strip_without_a_grp_line_leaves_membership_out(self):
        damaged = _drop(_text(), r"/ch/01/grp ")
        _, doc, _ = _regen(damaged)
        self.assertTrue(all("members" not in g for g in doc["groups"]["dca"].values()))
        self.assertNotIn("mute", doc["groups"])
        self.assertEqual(doc["groups"]["dca"]["1"].get("name"), _regen(_text())[1][
            "groups"]["dca"]["1"].get("name"))
        self.assertHonest(damaged, doc)

    def test_send_symmetry_is_not_claimed_without_the_buslink_line(self):
        asym = self._replaced("/ch/01/mix/10 ON ", "/ch/01/mix/10 OFF ")
        _, doc, _ = _regen(_drop(asym, r"/config/buslink "))
        self.assertIs(doc["links"]["require_send_symmetry"], False)
        self.assertEqual(preflight(Scene.parse(asym), doc), [])

    def test_live_senders_are_not_claimed_without_the_output_lines(self):
        dead = re.sub(r"^(/[a-z]+/\d+/mix/16) ON ", r"\1 OFF ", _text(), flags=re.M)
        dead = re.sub(r"^/outputs/main/16 \d+ ", f"/outputs/main/16 {bus_to_tap(16)} ", dead,
                      flags=re.M)
        for gone in (r"/outputs/main/16 ", r"/outputs/"):
            with self.subTest(dropped=gone):
                _, doc, _ = _regen(_drop(dead, gone))
                self.assertIs(doc["monitor"]["require_live_senders"], False)
                self.assertEqual(preflight(Scene.parse(dead), doc), [])

    def test_a_section_with_nothing_to_declare_is_left_out(self):
        damaged = _drop(_drop(_text(), r"/fx/\d "), r"/ch/\d\d/config ")
        _, doc, _ = _regen(damaged)
        self.assertNotIn("fx", doc)
        self.assertNotIn("channels", doc)
        self.assertEqual(set(coverage(doc)), {k for k in doc if not k.startswith("_")}
                         - {"gain_tolerance_db"})
        self.assertHonest(damaged, doc)

    def test_a_routing_line_the_resolver_would_default_leaves_its_values_out(self):
        for gone, section in ((r"/config/userrout/in ", "channels"),
                              (r"/config/routing/IN ", "channels"),
                              (r"/config/routing/CARD ", "record")):
            with self.subTest(dropped=gone):
                damaged = _drop(_text(), gone)
                _, doc, _ = _regen(damaged)
                if section == "channels":
                    self.assertNotIn("source", doc["channels"]["1"])
                else:
                    self.assertNotIn("record", doc)
                self.assertHonest(damaged, doc)


class LineDropSweepTest(unittest.TestCase):
    """Seeded random line drops: a config from any subset of a scene's lines checks that
    subset as no config would, covers what it emits, and holds for the whole scene."""

    def test_no_subset_of_lines_yields_a_claim_the_whole_scene_breaks(self):
        rnd = random.Random(7)
        for path in (EXAMPLE, EXAMPLE_ALT):
            with open(path, encoding="utf-8", newline="") as fh:
                text = fh.read()
            whole, lines = Scene.parse(text), text.split("\n")
            for i in range(30):
                rate = (0.002, 0.01, 0.05, 0.3)[i % 4]
                kept = [ln for j, ln in enumerate(lines) if j == 0 or rnd.random() > rate]
                sc = Scene.parse("\n".join(kept))
                doc = json.loads(dumps(regenerate(sc, path, DAY)))
                with self.subTest(scene=os.path.basename(path), variant=i):
                    self.assertEqual(preflight(sc, doc), preflight(sc, {}))
                    self.assertEqual(set(coverage(doc)),
                                     set(doc) - {"_comment", "gain_tolerance_db"})
                    self.assertEqual(preflight(whole, doc), [])


if __name__ == "__main__":
    unittest.main()
