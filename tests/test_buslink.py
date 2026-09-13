"""set-bus-link: toggling a stereo mix-bus pair the way the desk does.

Fixture facts the cases lean on: buses 13/14 are unlinked with centred pans and differing
sends (ch03 -22.5 on 13, -19.5 on 14); buses 1/2 and 9/10 are linked with main and
matrix-send pans at -100/+100; aux outs 5/6 carry buses 9/10.
"""

import os
import unittest

from x32scene import Scene
from x32scene.model import Line
from x32scene.services import buslink as BL
from x32scene.services.diff import diff
from x32scene.services.routing import outputs_from_buses
from x32scene.tables import SEND_STRIPS

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")

# the even side made to differ in every field a link copies
_DIVERGE = [
    "/ch/01/mix/14 OFF   -oo",
    "/auxin/01/mix/14 OFF -40.0",
    "/fxrtn/01/mix/14 ON -35.0",
    "/bus/14/eq ON",
    "/bus/14/eq/1 LShv 79.6 +6.00 2.0",
    "/bus/14/dyn ON COMP RMS LOG -10.0 3.0 1 0.00 10 10.0  151 POST 0 100 OFF",
    "/bus/14/dyn/filter ON 3.0 496.6",
    "/bus/14/insert OFF PRE OFF",
    "/bus/14/grp %00000001 %000000",
    "/bus/14/mix OFF -10.0 ON +0 ON  -5.0",
    "/bus/14/mix/01 ON -20.0 +0 PRE 0",
    "/bus/14/mix/02 OFF -30.0",
]


def _put(sc: Scene, raw: str) -> None:
    new = Line.parse(raw)
    ln = sc.get(new.path)
    ln.raw, ln.args = new.raw, new.args


def _diverged() -> Scene:
    sc = Scene.load(EXAMPLE)
    for raw in _DIVERGE:
        _put(sc, raw)
    cfg = sc.get("/bus/14/config")
    cfg.set_arg(1, "60")
    cfg.set_arg(2, "GNi")
    return sc


def _raw(sc: Scene, path: str) -> str:
    return sc.get(path).raw


def _field_counts(sc: Scene) -> list[tuple[str, int]]:
    return [(ln.path, len(ln.args)) for ln in sc.lines]


class LinkOnTest(unittest.TestCase):
    def setUp(self):
        self.base = _diverged()
        self.sc = _diverged()
        self.edit = BL.set_bus_link(self.sc, 13, True)

    def test_flips_only_the_pairs_token(self):
        self.assertEqual(_raw(self.sc, "/config/buslink"),
                         "/config/buslink ON ON ON ON ON ON ON OFF")
        self.assertEqual((self.edit.odd, self.edit.even, self.edit.on), (13, 14, True))

    def test_even_sends_take_the_odd_sends_on_and_level_verbatim(self):
        self.assertEqual(_raw(self.sc, "/ch/03/mix/14"), "/ch/03/mix/14 ON -22.5")
        self.assertEqual(_raw(self.sc, "/ch/01/mix/14"), "/ch/01/mix/14 ON   -oo")
        self.assertEqual(_raw(self.sc, "/ch/23/mix/14"), "/ch/23/mix/14 ON -72.0")
        self.assertEqual(_raw(self.sc, "/auxin/01/mix/14"), "/auxin/01/mix/14 ON   -oo")
        self.assertEqual(_raw(self.sc, "/fxrtn/01/mix/14"), "/fxrtn/01/mix/14 ON   -oo")
        for s in SEND_STRIPS:
            self.assertEqual(self.sc.get(f"{s}/mix/14").args,
                             self.base.get(f"{s}/mix/13").args[:2], s)

    def test_odd_sends_keep_their_pan_and_tap(self):
        for s in SEND_STRIPS:
            self.assertEqual(_raw(self.sc, f"{s}/mix/13"), _raw(self.base, f"{s}/mix/13"))

    def test_even_strip_takes_the_odd_strip_keeping_name_and_icon(self):
        name = self.base.get("/bus/14/config").args[0]
        self.assertEqual(_raw(self.sc, "/bus/14/config"), f"/bus/14/config {name} 60 RDi")
        for sub in ("eq", "eq/1", "eq/6", "dyn", "dyn/filter", "insert", "grp"):
            self.assertEqual(_raw(self.sc, f"/bus/14/{sub}"),
                             _raw(self.base, f"/bus/13/{sub}").replace("/bus/13/", "/bus/14/"))
        self.assertEqual(_raw(self.sc, "/bus/14/mix"), "/bus/14/mix ON   0.0 OFF +100 OFF   -oo")

    def test_matrix_sends_copy_and_spread(self):
        self.assertEqual(_raw(self.sc, "/bus/13/mix/01"), "/bus/13/mix/01 ON   -oo -100 POST 0")
        self.assertEqual(_raw(self.sc, "/bus/14/mix/01"), "/bus/14/mix/01 ON   -oo +100 POST 0")
        self.assertEqual(_raw(self.sc, "/bus/14/mix/02"), "/bus/14/mix/02 ON   -oo")
        self.assertEqual(_raw(self.sc, "/bus/14/mix/05"), "/bus/14/mix/05 ON   -oo +100 POST 0")

    def test_centred_main_pans_spread(self):
        self.assertEqual(_raw(self.sc, "/bus/13/mix"), "/bus/13/mix ON   0.0 OFF -100 OFF   -oo")

    def test_writes_exactly_the_desks_paths(self):
        want = {"/config/buslink", "/ch/01/mix/14", "/ch/03/mix/14", "/ch/05/mix/14",
                "/ch/06/mix/14", "/ch/07/mix/14", "/ch/09/mix/14", "/ch/10/mix/14",
                "/ch/11/mix/14", "/ch/12/mix/14", "/ch/23/mix/14", "/ch/24/mix/14",
                "/ch/25/mix/14", "/ch/26/mix/14", "/auxin/01/mix/14", "/fxrtn/01/mix/14",
                "/bus/13/mix", "/bus/13/mix/01", "/bus/13/mix/03", "/bus/13/mix/05",
                "/bus/14/config", "/bus/14/eq", "/bus/14/eq/1", "/bus/14/dyn",
                "/bus/14/dyn/filter", "/bus/14/insert", "/bus/14/grp", "/bus/14/mix",
                "/bus/14/mix/01", "/bus/14/mix/02", "/bus/14/mix/03", "/bus/14/mix/05"}
        self.assertEqual({c.path for c in diff(self.base, self.sc)}, want)
        self.assertEqual(set(self.edit.changed), want)

    def test_field_counts_and_round_trip_hold(self):
        self.assertEqual(_field_counts(self.sc), _field_counts(self.base))
        text = self.sc.dump()
        self.assertEqual(Scene.parse(text).dump(), text)

    def test_either_side_names_the_pair(self):
        other = _diverged()
        BL.set_bus_link(other, 14, True)
        self.assertEqual(other.dump(), self.sc.dump())


class LinkOnPanTest(unittest.TestCase):
    def test_an_off_centre_main_pan_is_left_on_both_sides(self):
        sc = _diverged()
        _put(sc, "/bus/13/mix ON   0.0 OFF +30 OFF   -oo")
        BL.set_bus_link(sc, 13, True)
        self.assertEqual(sc.get("/bus/13/mix").args[3], "+30")
        self.assertEqual(sc.get("/bus/14/mix").args[3], "+0")


class LinkPreferenceTest(unittest.TestCase):
    _ALWAYS = {"/bus/14/config", "/bus/14/dyn/filter", "/bus/14/mix/01", "/ch/03/mix/14"}

    def test_each_preference_turned_off_keeps_only_its_own_lines(self):
        for tokens, kept in (("OFF ON ON ON", set()),
                             ("ON OFF ON ON", {"/bus/14/eq", "/bus/14/eq/1"}),
                             ("ON ON OFF ON", {"/bus/14/dyn", "/bus/14/insert"}),
                             ("ON ON ON OFF", {"/bus/14/grp"}),
                             ("ON OFF OFF OFF", {"/bus/14/eq", "/bus/14/eq/1", "/bus/14/dyn",
                                                 "/bus/14/insert", "/bus/14/grp"})):
            with self.subTest(linkcfg=tokens):
                base, sc = _diverged(), _diverged()
                for s in (base, sc):
                    _put(s, f"/config/linkcfg {tokens}")
                BL.set_bus_link(sc, 13, True)
                changed = {c.path for c in diff(base, sc)}
                self.assertFalse(kept & changed)
                self.assertTrue(self._ALWAYS <= changed)
                mix = sc.get("/bus/14/mix").args  # fdrmute gates every field but the pan
                self.assertEqual(mix[:4], ["ON", "0.0", "OFF", "+100"] if tokens.endswith("ON")
                                 else ["OFF", "-10.0", "ON", "+100"])

    def test_unlink_copies_nothing_so_preferences_do_not_gate_it(self):
        sc = Scene.load(EXAMPLE)
        _put(sc, "/config/linkcfg ON OFF OFF OFF")
        self.assertIn("/config/buslink", BL.set_bus_link(sc, 1, False).changed)


class UntouchedBytesTest(unittest.TestCase):
    def test_a_copy_source_with_trailing_space_keeps_its_bytes(self):
        base = Scene.load(EXAMPLE)
        _put(base, "/ch/05/mix/13 ON   -oo +0 PRE 0 ")
        sc = Scene.parse(base.dump())
        edit = BL.set_bus_link(sc, 13, True)
        self.assertEqual(_raw(sc, "/ch/05/mix/13"), "/ch/05/mix/13 ON   -oo +0 PRE 0 ")
        self.assertNotIn("/ch/05/mix/13", {c.path for c in diff(base, sc)})
        self.assertNotIn("/ch/05/mix/13", edit.changed)


class LinkOffTest(unittest.TestCase):
    def setUp(self):
        self.base = Scene.load(EXAMPLE)
        self.sc = Scene.load(EXAMPLE)
        self.edit = BL.set_bus_link(self.sc, 2, False)

    def test_resets_the_pans_and_nothing_else(self):
        want = {"/config/buslink", "/bus/01/mix", "/bus/02/mix", "/bus/01/mix/01",
                "/bus/01/mix/03", "/bus/01/mix/05", "/bus/02/mix/01", "/bus/02/mix/03",
                "/bus/02/mix/05"}
        self.assertEqual({c.path for c in diff(self.base, self.sc)}, want)
        self.assertEqual(set(self.edit.changed), want)
        self.assertEqual(_raw(self.sc, "/config/buslink"),
                         "/config/buslink OFF ON ON ON ON ON OFF OFF")
        self.assertEqual(_raw(self.sc, "/bus/01/mix"), "/bus/01/mix ON -31.5 OFF +0 OFF   -oo")
        self.assertEqual(_raw(self.sc, "/bus/02/mix"), "/bus/02/mix ON -31.5 OFF +0 OFF   -oo")
        self.assertEqual(_raw(self.sc, "/bus/02/mix/03"), "/bus/02/mix/03 ON   -oo +0 POST 0")
        self.assertEqual(_field_counts(self.sc), _field_counts(self.base))

    def test_main_pans_other_than_a_full_spread_are_left(self):
        sc = Scene.load(EXAMPLE)
        _put(sc, "/bus/01/mix ON -31.5 OFF -60 OFF   -oo")
        BL.set_bus_link(sc, 1, False)
        self.assertEqual(sc.get("/bus/01/mix").args[3], "-60")
        self.assertEqual(sc.get("/bus/02/mix").args[3], "+100")


class RefusalTest(unittest.TestCase):
    def _refused(self, sc: Scene, bus: int, on: bool, exc, words: str) -> None:
        before = sc.dump()
        with self.assertRaises(exc) as cm:
            BL.set_bus_link(sc, bus, on)
        self.assertIn(words, str(cm.exception))
        self.assertEqual(sc.dump(), before)

    def test_a_pair_already_in_the_requested_state(self):
        self._refused(Scene.load(EXAMPLE), 1, True, ValueError, "already linked")
        self._refused(Scene.load(EXAMPLE), 14, False, ValueError, "already unlinked")

    def test_a_bus_the_console_does_not_have(self):
        for bus in (0, 17):
            self._refused(Scene.load(EXAMPLE), bus, True, ValueError, "1-16")

    def test_a_scene_without_the_link_line(self):
        sc = Scene.load(EXAMPLE)
        sc.lines = [ln for ln in sc.lines if ln.path != "/config/buslink"]
        sc._reindex()
        self._refused(sc, 13, True, KeyError, "/config/buslink")

    def test_link_without_the_link_preferences_line(self):
        sc = _diverged()
        sc.lines = [ln for ln in sc.lines if ln.path != "/config/linkcfg"]
        sc._reindex()
        self._refused(sc, 13, True, KeyError, "/config/linkcfg")

    def test_a_scene_missing_a_line_the_link_writes(self):
        for path in ("/fxrtn/08/mix/14", "/bus/13/dyn/filter", "/bus/14/mix/06"):
            with self.subTest(path=path):
                sc = _diverged()
                sc.lines = [ln for ln in sc.lines if ln.path != path]
                sc._reindex()
                self._refused(sc, 13, True, KeyError, path)


class OutputsTest(unittest.TestCase):
    def test_outputs_fed_from_a_pair(self):
        sc = Scene.load(EXAMPLE)
        self.assertEqual(outputs_from_buses(sc, (9, 10)), [("aux", 5, 9), ("aux", 6, 10)])
        self.assertEqual(outputs_from_buses(sc, (13, 14)), [])


if __name__ == "__main__":
    unittest.main()
