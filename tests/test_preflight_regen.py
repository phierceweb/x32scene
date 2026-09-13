"""preflight --regenerate: the expected-config written from a scene must check that same
scene clean, cover every section it emits, and come out byte-identical run to run."""

import difflib
import json
import os
import unittest
from datetime import date

from x32scene.model import Scene
from x32scene.services import preflight_monitor
from x32scene.services.preflight import (_ALL_SECTIONS, GAIN_TOLERANCE_DB, coverage,
                                         load_expected, preflight)
from x32scene.services.preflight_regen import (_NOT_INVERTED_KEYS, _NOT_INVERTIBLE, dumps,
                                               regenerate)
from x32scene.tables import SEND_STRIPS

from tests.preflight_scene import fails

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")
EXAMPLE_ALT = os.path.join(FIXTURES, "example-alt.scn")
EXAMPLE_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config",
                              "example-preflight.json")
DAY = date(2026, 9, 12)


def _generated(path: str) -> dict:
    """Through the serialized text, as a reader of the written file sees it."""
    return json.loads(dumps(regenerate(Scene.load(path), path, DAY)))


FXRTN_1_4 = {f"/fxrtn/{n:02d}" for n in range(1, 5)}


def _fewest_rules(taps: dict[str, str]) -> int:
    """Brute force: given the bus tap, each family independently takes the cheaper of no
    family rule or a rule for one other tap."""
    values = set(taps.values())
    best = []
    for tap in values:
        total = 0
        for fam in ("/ch", "/auxin", "/fxrtn"):
            own = [t for s, t in taps.items() if s.rpartition("/")[0] == fam]
            total += min([sum(t != tap for t in own)]
                         + [1 + sum(t != r for t in own) for r in values - {tap}])
        best.append(total)
    return min(best)


def _without(text: str, *prefixes: str) -> Scene:
    return Scene.parse("\n".join(ln for ln in text.split("\n")
                                 if not ln.startswith(prefixes)))


def _fixture_text() -> str:
    with open(EXAMPLE, encoding="utf-8", newline="") as fh:
        return fh.read()


class RoundTripTest(unittest.TestCase):
    """The definition of done: a regenerated config checks its own scene with no finding."""

    def test_each_fixture_checks_clean_against_its_own_config(self):
        for path in (EXAMPLE, EXAMPLE_ALT):
            with self.subTest(scene=os.path.basename(path)):
                doc = _generated(path)
                self.assertEqual(preflight(Scene.load(path), doc), [])

    def test_coverage_reports_every_emitted_section(self):
        for path in (EXAMPLE, EXAMPLE_ALT):
            with self.subTest(scene=os.path.basename(path)):
                doc = _generated(path)
                emitted = {k for k in doc if k in _ALL_SECTIONS}
                self.assertEqual(set(coverage(doc)), emitted)

    def test_a_config_from_one_scene_catches_the_other(self):
        doc = _generated(EXAMPLE)
        areas = {f.area for f in fails(preflight(Scene.load(EXAMPLE_ALT), doc))}
        for area in ("out main 05", "routing CARD", "record 09"):
            self.assertIn(area, areas)


class SectionParityTest(unittest.TestCase):
    """A new checker family fails here until it is inverted or named as not invertible."""

    def test_emitted_sections_are_every_checked_section_minus_the_named_exclusions(self):
        doc = regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY)
        sections = set(doc) - {"_comment", "gain_tolerance_db"}
        self.assertEqual(sections, set(_ALL_SECTIONS) - _NOT_INVERTIBLE)

    def test_exclusions_name_real_sections(self):
        self.assertLessEqual(_NOT_INVERTIBLE, set(_ALL_SECTIONS))

    def test_monitor_emits_every_key_but_the_ones_the_file_cannot_hold(self):
        doc = regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY)
        self.assertEqual(set(doc["monitor"]),
                         preflight_monitor._KEYS - _NOT_INVERTED_KEYS["monitor"])

    def test_gain_tolerance_is_the_checker_default(self):
        doc = _generated(EXAMPLE)
        self.assertEqual(doc["gain_tolerance_db"], GAIN_TOLERANCE_DB)
        self.assertIsInstance(doc["gain_tolerance_db"], float)


class CommentTest(unittest.TestCase):
    def test_names_the_scene_file_and_the_date_never_its_directory(self):
        where = os.path.join("some", "private", "dir", "gig.scn")
        comment = regenerate(Scene.load(EXAMPLE), where, date(2026, 1, 2))["_comment"]
        self.assertIn("gig.scn", comment)
        self.assertIn("2026-01-02", comment)
        self.assertNotIn("private", comment)


class StableOutputTest(unittest.TestCase):
    def test_two_runs_are_byte_identical(self):
        a = dumps(regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY))
        b = dumps(regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY))
        self.assertEqual(a, b)

    def test_ends_with_exactly_one_newline(self):
        text = dumps(regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY))
        self.assertTrue(text.endswith("}\n"))

    def test_keys_are_sorted_comment_first_and_numbers_numerically(self):
        doc = _generated(EXAMPLE)
        self.assertEqual(list(doc)[0], "_comment")
        self.assertEqual(list(doc)[1:], sorted(list(doc)[1:]))
        self.assertEqual(list(doc["channels"]), [str(n) for n in range(1, 33)])
        self.assertEqual(list(doc["outputs"]), sorted(doc["outputs"]))

    def test_gain_is_written_as_a_float(self):
        text = dumps(regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY))
        self.assertIn('"gain": 27.0', text)
        self.assertIn('"gain_tolerance_db": 3.0', text)


class InversionTest(unittest.TestCase):
    """What the generator reads matches what a person would have written by hand."""

    def test_send_taps_reduce_to_the_hand_written_tap_and_exceptions(self):
        doc = _generated(EXAMPLE)
        hand = load_expected(EXAMPLE_CONFIG)["sends"]
        self.assertEqual(doc["sends"]["9"]["tap"], hand["9"]["tap"])
        self.assertEqual(doc["sends"]["9"]["except"], hand["9"]["except"])
        self.assertEqual(doc["sends"]["1"]["tap"], "PRE")
        self.assertNotIn("except", doc["sends"]["1"])

    def test_a_tie_inside_a_family_adds_no_needless_rule(self):
        ties = {"ch 16/16 on bus 1": (1, lambda s: "POST" if s < "/ch/17" and s.startswith("/ch/")
                                      else "PRE"),
                "fxrtn 4/4 on bus 9": (9, lambda s: "PRE" if s in FXRTN_1_4 else None)}
        for case, (bus, retap) in ties.items():
            with self.subTest(case=case):
                sc = Scene.load(EXAMPLE)
                for strip in SEND_STRIPS:
                    ln = sc.get(f"{strip}/mix/{bus:02d}")
                    ln.set_arg(3, retap(strip) or ln.args[3])
                doc = json.loads(dumps(regenerate(sc, EXAMPLE, DAY)))
                taps = {s: sc.get(f"{s}/mix/{bus:02d}").args[3] for s in SEND_STRIPS}
                self.assertEqual(len(doc["sends"][str(bus)].get("except", {})),
                                 _fewest_rules(taps))
                self.assertEqual(preflight(sc, doc), [])

    def test_an_even_bus_carries_no_tap(self):
        self.assertNotIn("tap", _generated(EXAMPLE)["sends"]["2"])

    def test_a_non_bus_output_is_written_as_src(self):
        outputs = _generated(EXAMPLE)["outputs"]
        self.assertEqual(outputs["main"]["1"], {"bus": 1, "invert": False, "pos": "POST"})
        self.assertEqual(outputs["main"]["7"], {"invert": False, "pos": "POST", "src": 1})
        self.assertNotIn("invert", outputs["rec"]["1"])

    def test_an_engaged_mute_group_is_declared(self):
        sc = Scene.parse(_fixture_text().replace("/config/mute OFF OFF OFF",
                                                 "/config/mute OFF OFF ON"))
        doc = json.loads(dumps(regenerate(sc, EXAMPLE, DAY)))
        self.assertEqual(doc["groups"]["mute_engaged"], [3])
        self.assertEqual(preflight(sc, doc), [])

    def test_a_missing_line_drops_only_what_it_would_verify(self):
        # one send line gone: bus 9's tap and the linked pair's symmetry cannot be verified
        sc = _without(_fixture_text(), "/ch/03/mix/09 ")
        doc = json.loads(dumps(regenerate(sc, EXAMPLE, DAY)))
        self.assertEqual(preflight(sc, doc), [])
        self.assertNotIn("tap", doc["sends"]["9"])
        self.assertIs(doc["links"]["require_send_symmetry"], False)
        self.assertEqual(doc["sends"]["1"]["tap"], "PRE")

    def test_a_malformed_line_adds_nothing_to_its_shape_finding(self):
        text = _fixture_text()
        cases = {"short output": ("/outputs/main/03 6 POST OFF", "/outputs/main/03 6 POST"),
                 "link token": ("/config/buslink ON ON", "/config/buslink XX ON"),
                 "short send": ("/ch/01/mix/03 ON  +6.8 +0 PRE 0", "/ch/01/mix/03 ON  +6.8"),
                 "mute width": ("/config/mute OFF OFF OFF OFF OFF OFF", "/config/mute ON OFF"),
                 "routing width": ("/config/routing/CARD UOUT1-8 UOUT9-16 UOUT17-24 UOUT25-32",
                                   "/config/routing/CARD UOUT1-8 UOUT9-16")}
        for case, (old, new) in cases.items():
            with self.subTest(case=case):
                self.assertIn(old, text)
                sc = Scene.parse(text.replace(old, new, 1))
                doc = json.loads(dumps(regenerate(sc, EXAMPLE, DAY)))
                self.assertEqual(preflight(sc, doc), preflight(sc, {}))
                self.assertTrue(preflight(sc, {}))

    def test_a_policy_the_scene_breaks_is_written_false(self):
        text = _fixture_text().replace("/outputs/aux/02 11 ", "/outputs/aux/02 12 ")
        sc = Scene.parse(text)
        doc = json.loads(dumps(regenerate(sc, EXAMPLE, DAY)))
        self.assertEqual(doc["monitor"]["stereo_pairs"], ["main"])
        self.assertEqual(preflight(sc, doc), [])


@unittest.skipUnless(os.environ.get("X32SCENE_CONFIG") and os.environ.get("X32SCENE_REGEN_SCENE"),
                     "set X32SCENE_CONFIG and X32SCENE_REGEN_SCENE to check a rig config "
                     "for drift")
class RigConfigDriftTest(unittest.TestCase):
    """Opt-in: the tracked rig config against one regenerated from the named scene. Comments
    are dropped from both and both are written through ``dumps``, so only content differs."""

    def test_tracked_config_matches_a_regenerated_one(self):
        cfg, scene = os.environ["X32SCENE_CONFIG"], os.environ["X32SCENE_REGEN_SCENE"]
        diff = _drift(load_expected(cfg), regenerate(Scene.load(scene), scene, DAY))
        if diff:
            print(diff)
        self.assertEqual(diff, "", "the tracked rig config differs from the scene; the diff "
                                   "is printed above")


class DriftComparisonTest(unittest.TestCase):
    def test_a_number_spelled_differently_is_not_drift(self):
        fresh = regenerate(Scene.load(EXAMPLE), EXAMPLE, DAY)
        tracked = json.loads(dumps(fresh).replace('"gain": 27.0,', '"gain": 27,'))
        self.assertEqual(_drift(tracked, fresh), "")
        tracked["channels"]["1"]["gain"] = 26
        self.assertIn('"gain": 26', _drift(tracked, fresh))


def _strip_comments(v):
    if isinstance(v, dict):
        return {k: _strip_comments(x) for k, x in v.items() if not str(k).startswith("_")}
    if isinstance(v, list):
        return [_strip_comments(x) for x in v]
    return v


def _drift(tracked: dict, fresh: dict) -> str:
    """The diff between two configs, empty when they hold the same values (27 equals 27.0)."""
    a, b = _strip_comments(tracked), _strip_comments(fresh)
    if a == b:
        return ""
    return "".join(difflib.unified_diff(dumps(a).splitlines(True), dumps(b).splitlines(True),
                                        "tracked", "regenerated"))


if __name__ == "__main__":
    unittest.main()
