"""Strip reorder: the moves themselves, the mapping check, stereo links and the verify gate.

Fixture facts the cases lean on: ch05 "Rack 1" and ch07 "Rack 3" are unlinked; channel pairs
11/12, 15/16, 27/28 and 31/32 are linked; p16 03 and 05 tap channels 5 and 7 (30, 32).
"""

import os
import unittest

from x32scene import Scene
from x32scene.services import stripmove as SM
from x32scene.services.diff import diff

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _load() -> Scene:
    return Scene.load(EXAMPLE)


def _ch_lines(scene: Scene, ch: int) -> list[str]:
    prefix = f"/ch/{ch:02d}/"
    return [ln.raw[len(prefix):] for ln in scene.lines if ln.path.startswith(prefix)]


class MoveTest(unittest.TestCase):
    def test_swap_carries_every_line_verbatim_and_keeps_line_order(self):
        base, sc = _load(), _load()
        move = SM.permute_channels(sc, {5: 7, 7: 5})
        self.assertEqual(move.moves, [(5, 7), (7, 5)])
        self.assertEqual(_ch_lines(sc, 7), _ch_lines(base, 5))
        self.assertEqual(_ch_lines(sc, 5), _ch_lines(base, 7))
        self.assertEqual([ln.path for ln in sc.lines], [ln.path for ln in base.lines])
        out = sc.dump()
        self.assertEqual(Scene.parse(out).dump(), out)

    def test_diff_touches_only_the_moved_strips_and_the_reported_references(self):
        base, sc = _load(), _load()
        move = SM.permute_channels(sc, {5: 7, 7: 5})
        refs = {r.path for r in move.remapped}
        for c in diff(base, sc):
            self.assertTrue(c.path.startswith(("/ch/05/", "/ch/07/")) or c.path in refs, c.path)
        self.assertEqual(sorted(move.changed), sorted(c.path for c in diff(base, sc)))

    def test_swap_twice_returns_the_original_bytes(self):
        sc = _load()
        for _ in range(2):
            SM.permute_channels(sc, {5: 7, 7: 5})
        self.assertEqual(sc.dump(), _load().dump())

    def test_move_then_the_inverse_move_returns_the_original_bytes(self):
        sc = _load()
        SM.permute_channels(sc, SM.move_mapping(3, 9))
        self.assertNotEqual(sc.dump(), _load().dump())
        SM.permute_channels(sc, SM.move_mapping(9, 3))
        self.assertEqual(sc.dump(), _load().dump())

    def test_move_mapping_shifts_the_strips_between(self):
        self.assertEqual(SM.move_mapping(3, 6), {3: 6, 4: 3, 5: 4, 6: 5})
        self.assertEqual(SM.move_mapping(6, 3), {6: 3, 3: 4, 4: 5, 5: 6})
        self.assertEqual(SM.swap_mapping(2, 9), {2: 9, 9: 2})

    def test_identity_mapping_changes_nothing(self):
        sc = _load()
        move = SM.permute_channels(sc, {5: 5, 7: 7})
        self.assertEqual((move.moves, move.remapped, move.changed), ([], [], []))
        self.assertEqual(sc.dump(), _load().dump())

    def test_identity_entries_are_ignored_beside_real_moves(self):
        sc = _load()
        move = SM.permute_channels(sc, {5: 7, 7: 5, 9: 9})
        self.assertEqual(move.moves, [(5, 7), (7, 5)])


class RefusalTest(unittest.TestCase):
    def _refused(self, sc: Scene, mapping: dict) -> str:
        before = sc.dump()
        with self.assertRaises(ValueError) as cm:
            SM.permute_channels(sc, mapping)
        self.assertEqual(sc.dump(), before)
        return str(cm.exception)

    def test_a_mapping_that_is_not_a_permutation_names_every_problem(self):
        msg = self._refused(_load(), {1: 2, 3: 2, 2: 1})
        self.assertIn("ch02", msg)   # two strips onto one
        self.assertIn("ch03", msg)   # left empty
        self.assertIn("not a permutation", self._refused(_load(), {5: 12}))

    def test_an_index_outside_1_to_32_is_refused(self):
        msg = self._refused(_load(), {0: 5, 5: 0, 33: 1, 1: 33})
        self.assertIn("0", msg)
        self.assertIn("33", msg)

    def test_strips_carrying_different_lines_are_refused(self):
        text = _load().dump().replace("/ch/07/automix OFF  +0.0\n", "")
        msg = self._refused(Scene.parse(text), {5: 7, 7: 5})
        self.assertIn("ch05", msg)
        self.assertIn("ch07", msg)

    def test_a_missing_chlink_or_config_line_is_refused(self):
        text = _load().dump()
        self.assertIn("/config/chlink",
                      self._refused(Scene.parse(text.replace("/config/chlink", "/config/xlink")),
                                    {5: 7, 7: 5}))
        gone = text.replace('/ch/07/config "Rack 3" 7 YEi 7\n', "").replace(
            '/ch/05/config "Rack 1" 6 YEi 5\n', "")
        self.assertIn("/ch/05/config", self._refused(Scene.parse(gone), {5: 7, 7: 5}))

    def test_every_problem_is_named_at_once(self):
        sc = _load()
        sc.get("/ch/05/automix").set_arg(0, "X")
        msg = self._refused(sc, {5: 11, 11: 5})
        self.assertIn("automix", msg)
        self.assertIn("11/12", msg)


class ChannelLinkTest(unittest.TestCase):
    def test_a_linked_pair_moved_whole_takes_its_link_along(self):
        sc = _load()
        move = SM.permute_channels(sc, {11: 5, 12: 6, 5: 11, 6: 12})
        links = sc.get("/config/chlink").args
        self.assertEqual((links[2], links[5]), ("ON", "OFF"))
        self.assertIn(SM.RemappedRef("/config/chlink", 3, "OFF", "ON"), move.remapped)
        self.assertIn(SM.RemappedRef("/config/chlink", 6, "ON", "OFF"), move.remapped)

    def test_two_linked_pairs_trading_places_leave_the_tokens_alone(self):
        sc = _load()
        move = SM.permute_channels(sc, {11: 15, 12: 16, 15: 11, 16: 12})
        self.assertEqual([r for r in move.remapped if r.path == "/config/chlink"], [])

    def test_splitting_or_reversing_a_linked_pair_is_refused(self):
        for mapping in ({11: 13, 13: 11}, {11: 12, 12: 11}, SM.move_mapping(10, 14)):
            with self.subTest(mapping=mapping):
                sc = _load()
                with self.assertRaises(ValueError) as cm:
                    SM.permute_channels(sc, mapping)
                self.assertIn("11/12", str(cm.exception))
                self.assertEqual(sc.dump(), _load().dump())

    def test_an_unlinked_pair_splits_freely(self):
        sc = _load()
        SM.permute_channels(sc, {5: 8, 8: 5})
        self.assertEqual(sc.get("/config/chlink").args, _load().get("/config/chlink").args)


class VerifyTest(unittest.TestCase):
    def test_a_change_outside_the_report_is_flagged(self):
        base, sc = _load(), _load()
        move = SM.permute_channels(sc, {5: 7, 7: 5})
        self.assertEqual(SM.unexpected_changes(base, sc, move), [])
        sc.get("/ch/09/mix").set_arg(1, "-3.0")
        self.assertEqual(SM.unexpected_changes(base, sc, move), ["/ch/09/mix"])

    def test_a_moved_line_or_reference_field_beyond_the_report_is_flagged(self):
        base, sc = _load(), _load()
        move = SM.permute_channels(sc, {5: 7, 7: 5})
        sc.get("/outputs/p16/03").set_arg(1, "POST")
        sc.get("/ch/07/mix/01").set_arg(1, "-3.0")
        self.assertEqual(SM.unexpected_changes(base, sc, move),
                         ["/ch/07/mix/01", "/outputs/p16/03"])

    def test_a_reported_reference_that_did_not_change_is_flagged(self):
        base, sc = _load(), _load()
        move = SM.permute_channels(sc, {5: 7, 7: 5})
        move.remapped.append(SM.RemappedRef("/outputs/aux/01", 1, "30", "32"))
        self.assertEqual(SM.unexpected_changes(base, sc, move), ["/outputs/aux/01"])


if __name__ == "__main__":
    unittest.main()
