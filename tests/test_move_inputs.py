"""Stage-box moves: the batch service and the `move-inputs` command over it.

Fixture facts the cases lean on: ch1 is Local 1 (/headamp/000 +27.0 OFF); ch17-28 are
AES50-A 1-12 through user-in slots 17-28; AES50-A 13 and up feed no channel (13 and 14
sit at +21.5 OFF); ch31 is Card 1.
"""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene import transforms as T
from x32scene.cli import main
from x32scene.services import stagebox as SB
from x32scene.services.diff import diff

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _changed(before: Scene, after: Scene) -> set[str]:
    return {c.path for c in diff(before, after)}


def _ha(scene: Scene, idx: int) -> list[str]:
    return list(scene.get(f"/headamp/{idx:03d}").args)


class StageboxBatchTest(unittest.TestCase):
    def setUp(self):
        self.base = Scene.load(SCENE)
        self.sc = Scene.load(SCENE)

    def _set_slot(self, ch: int, slot: int) -> None:
        cfg = self.sc.get(f"/ch/{ch:02d}/config")
        cfg.set_arg(len(cfg.args) - 1, str(slot))

    def test_chained_moves_carry_each_channels_own_head_amp(self):
        # ch1 lands on A1 in the same batch that moves ch17 off A1
        T.move_inputs_to_stagebox(self.sc, {1: 1, 17: 13}, port="A")
        self.assertEqual(_ha(self.sc, 32), _ha(self.base, 0))
        self.assertEqual(_ha(self.sc, 44), _ha(self.base, 32))

    def test_swapped_moves_exchange_head_amps(self):
        T.move_inputs_to_stagebox(self.sc, {17: 2, 18: 1}, port="A")
        self.assertEqual(_ha(self.sc, 33), _ha(self.base, 32))
        self.assertEqual(_ha(self.sc, 32), _ha(self.base, 33))
        uin = self.sc.get("/config/userrout/in").args
        self.assertEqual(uin[16:18], ["34", "33"])

    def test_batch_reports_each_move(self):
        moves = SB.move_to_stagebox(self.sc, [(1, 13), (31, 14)], port="A")
        self.assertEqual([(m.ch, m.old_source, m.new_source) for m in moves],
                         [(1, 1, 45), (31, 129, 46)])
        self.assertEqual((moves[0].headamp, moves[0].carried), (("+27.0", "OFF"), True))
        # a card source has no head amp: the destination keeps its own
        self.assertEqual((moves[1].headamp, moves[1].carried), (("+21.5", "OFF"), False))
        self.assertEqual(_ha(self.sc, 45), _ha(self.base, 45))

    def test_no_gain_reports_the_destination_as_it_stays(self):
        moves = SB.move_to_stagebox(self.sc, [(1, 13)], port="A", move_gain=False)
        self.assertEqual((moves[0].headamp, moves[0].carried), (("+21.5", "OFF"), False))
        self.assertEqual(_changed(self.base, self.sc), {"/config/userrout/in"})

    def test_port_b_numbers_from_81(self):
        moves = SB.move_to_stagebox(self.sc, [(1, 5)], port="B")
        self.assertEqual(moves[0].new_source, 85)
        self.assertEqual(_ha(self.sc, 84), _ha(self.base, 0))

    def _refused(self, moves, fragment, **kw):
        before = self.sc.dump()
        with self.assertRaises(ValueError) as ctx:
            SB.move_to_stagebox(self.sc, moves, port="A", **kw)
        self.assertIn(fragment, str(ctx.exception))
        self.assertEqual(self.sc.dump(), before)

    def test_channel_listed_twice_is_refused(self):
        self._refused([(1, 13), (1, 14)], "ch01 is listed twice")

    def test_two_channels_onto_one_input_are_refused(self):
        self._refused([(1, 13), (2, 13)], "ch01 and ch02 both move to AES50-A input 13")

    def test_channels_sharing_a_user_in_slot_are_refused(self):
        self._set_slot(2, 1)
        self._refused([(1, 13)], "ch01 shares user-in slot 1 with ch02")

    def test_a_user_in_slot_shared_through_a_repeated_uin_block_is_refused(self):
        inb = self.sc.get("/config/routing/IN")
        inb.set_arg(1, "UIN1-8")   # slot 9 now reads user-in slot 1 too
        self._refused([(1, 13)], "ch01 shares user-in slot 1 with ch09")

    def test_moving_both_channels_off_a_shared_slot_is_still_refused(self):
        self._set_slot(2, 1)
        self._refused([(1, 13), (2, 14)], "shares user-in slot 1")

    def test_an_aux_in_on_the_same_slot_counts_as_sharing(self):
        cfg = self.sc.get("/auxin/01/config")
        cfg.set_arg(len(cfg.args) - 1, "1")
        self._refused([(1, 13)], "ch01 shares user-in slot 1 with auxin01")

    def test_gain_onto_an_input_another_channel_reads_is_refused(self):
        # A2 feeds ch18: carrying ch1's head amp there would re-gain ch18
        self._refused([(1, 2)], "AES50-A input 2 still feeds ch18")

    def test_no_gain_may_share_an_input_deliberately(self):
        SB.move_to_stagebox(self.sc, [(1, 2)], port="A", move_gain=False)
        self.assertEqual(_changed(self.base, self.sc), {"/config/userrout/in"})

    def test_an_aux_in_reader_is_not_offered_as_a_move(self):
        self.sc.get("/config/routing/IN").set_arg(4, "A1-4")   # auxin01 reads AES50-A 1
        self.sc.get("/auxin/01/config").set_arg(3, "33")
        with self.assertRaises(ValueError) as ctx:
            SB.move_to_stagebox(self.sc, [(17, 13), (1, 1)], port="A")
        msg = str(ctx.exception)
        self.assertIn("AES50-A input 1 still feeds auxin01", msg)
        self.assertNotIn("move auxin01 too", msg)

    def test_a_direct_routed_reader_is_not_offered_as_a_move(self):
        self.sc.get("/config/routing/IN").set_arg(1, "A9-16")   # ch09 reads AES50-A 9 directly
        with self.assertRaises(ValueError) as ctx:
            SB.move_to_stagebox(self.sc, [(1, 9)], port="A")
        msg = str(ctx.exception)
        self.assertIn("still feeds ch09, ch25", msg)
        self.assertNotIn("too", msg)

    def test_a_movable_reader_is_offered_as_a_move(self):
        self._refused([(1, 2)], "move ch18 too")

    def test_an_unknown_channel_is_a_key_error_leaving_the_scene(self):
        before = self.sc.dump()
        with self.assertRaises(KeyError):
            SB.move_to_stagebox(self.sc, [(1, 13), (33, 14)], port="A")
        self.assertEqual(self.sc.dump(), before)

    def test_an_out_of_range_input_names_the_channel(self):
        self._refused([(1, 13), (2, 49)], "ch02: AES50-A input 49 is out of range 1-48")

    def test_a_channel_on_the_aux_bank_is_not_called_off(self):
        self._set_slot(1, 33)
        with self.assertRaises(ValueError) as ctx:
            SB.move_to_stagebox(self.sc, [(1, 13)], port="A")
        self.assertIn("ch01 reads aux-bank slot 33", str(ctx.exception))
        self.assertNotIn("OFF", str(ctx.exception))

    def test_a_channel_with_no_source_is_called_off(self):
        self._set_slot(1, 0)
        self._refused([(1, 13)], "ch01 has no input source (OFF)")

    def test_direct_routed_channel_keeps_the_existing_reason(self):
        self.sc.get("/config/routing/IN").set_arg(0, "AN1-8")
        self._refused([(1, 13)], "direct-routed")

    def test_the_port_is_required(self):
        with self.assertRaises(TypeError):
            SB.move_to_stagebox(self.sc, [(1, 13)])


class MoveInputsCliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = os.path.join(self.dir, "out.scn")
        self.base = Scene.load(SCENE)

    def _run(self, *argv, scene=SCENE):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["move-inputs", scene, *argv, "-o", self.out])
        return rc, out.getvalue(), err.getvalue()

    def _variant(self, old: str, new: str | None) -> str:
        """The fixture with one line replaced, or dropped when ``new`` is None."""
        sc = Scene.load(SCENE)
        text = sc.dump().replace(old + "\n", "" if new is None else new + "\n")
        path = os.path.join(self.dir, "in.scn")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_a_head_amp_line_short_of_fields_still_reports(self):
        for old, new, flags in (("/headamp/000 +27.0 OFF", "/headamp/000 +27.0", ()),
                                ("/headamp/044 +21.5 OFF", "/headamp/044", ("--no-gain",))):
            with self.subTest(line=new):
                scene = self._variant(old, new)
                rc, out, err = self._run("1:13", "--to", "A", *flags, scene=scene)
                self.assertEqual(rc, 0, err)
                self.assertIn("ch01", out)
                os.remove(self.out)

    def test_a_missing_old_head_amp_line_is_not_reported_as_no_gain(self):
        scene = self._variant("/headamp/000 +27.0 OFF", None)
        rc, out, _ = self._run("1:13", "--to", "A", scene=scene)
        self.assertEqual(rc, 0)
        kick = next(ln for ln in out.splitlines() if "ch01" in ln)
        self.assertIn("Local input 1 has no head-amp line to carry", kick)
        self.assertNotIn("not carried", kick)

    def test_output_differs_only_in_user_in_and_the_affected_head_amps(self):
        rc, _, _ = self._run("1:13", "17:14", "--to", "A")
        self.assertEqual(rc, 0)
        after = Scene.load(self.out)
        self.assertEqual(_changed(self.base, after),
                         {"/config/userrout/in", "/headamp/044", "/headamp/045"})
        self.assertEqual(_ha(after, 44), _ha(self.base, 0))
        self.assertEqual(_ha(after, 45), _ha(self.base, 32))

    def test_no_gain_touches_only_user_in(self):
        rc, _, _ = self._run("1:13", "--to", "B", "--no-gain")
        self.assertEqual(rc, 0)
        after = Scene.load(self.out)
        self.assertEqual(_changed(self.base, after), {"/config/userrout/in"})
        self.assertEqual(after.get("/config/userrout/in").args[0], "93")

    def test_one_line_per_channel_names_where_from_where_to_and_the_gain(self):
        rc, out, _ = self._run("1:13", "31:14", "--to", "A")
        self.assertEqual(rc, 0)
        lines = out.splitlines()
        kick = next(ln for ln in lines if "ch01" in ln)
        self.assertIn("Kick", kick)
        self.assertIn("Local input 1 -> AES50-A input 13", kick)
        self.assertIn("+27.0 dB, phantom OFF", kick)
        daw = next(ln for ln in lines if "ch31" in ln)
        self.assertIn("USB Card (DAW) 1 -> AES50-A input 14", daw)
        self.assertIn("no head amp", daw)
        self.assertIn(f"wrote {self.out}", out)

    def test_an_invalid_move_writes_nothing(self):
        rc, _, err = self._run("1:13", "2:49", "--to", "A")
        self.assertEqual(rc, 1)
        self.assertIn("ch02: AES50-A input 49 is out of range 1-48", err)
        self.assertFalse(os.path.exists(self.out))

    def test_a_duplicate_channel_writes_nothing(self):
        rc, _, err = self._run("1:13", "1:14", "--to", "A")
        self.assertEqual(rc, 1)
        self.assertIn("listed twice", err)
        self.assertFalse(os.path.exists(self.out))

    def test_port_is_accepted_in_either_case(self):
        rc, out, err = self._run("1:13", "--to", "b", "--no-gain")
        self.assertEqual(rc, 0, err)
        self.assertIn("AES50-B input 13", out)
        self.assertEqual(Scene.load(self.out).get("/config/userrout/in").args[0], "93")

    def test_a_refused_port_is_quoted_as_typed(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            main(["move-inputs", SCENE, "1:13", "--to", "c", "-o", self.out])
        self.assertIn("invalid choice: 'c' (choose from A, B)", err.getvalue())

    def test_to_has_no_default(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run("1:13")
        self.assertEqual(ctx.exception.code, 2)

    def test_a_malformed_move_is_a_usage_error(self):
        for bad in ("1-13", "1:", "a:3", "1:2:3"):
            with self.subTest(move=bad), self.assertRaises(SystemExit) as ctx:
                self._run(bad, "--to", "A")
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
