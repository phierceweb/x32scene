"""A channel slot whose block its routing line does not reach, the line missing or short of
its five blocks, names no source: never the user patch read by guess."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.orchestrators.band_swap import apply_plan
from x32scene.services.routing import (channel_headamp_index, channel_sources, resolve_in_slot,
                                       resolve_in_slot_number, uin_in_index, unwritten_in_block)
from x32scene.services.routing_edit import channel_slot, set_routswitch

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def with_blocks(bank: str, keep: int | None) -> Scene:
    """example.scn with ``/config/routing/<bank>`` cut to its first ``keep`` blocks, or
    dropped (None)."""
    out = []
    for raw in Scene.load(EXAMPLE).dump().split("\n"):
        if raw.startswith(f"/config/routing/{bank} "):
            if keep is None:
                continue
            raw = " ".join(raw.split(" ")[:keep + 1])
        out.append(raw)
    return Scene.parse("\n".join(out))


class UnreachedSlotTest(unittest.TestCase):
    def test_a_missing_line_names_no_source_for_any_routed_slot(self):
        sc = with_blocks("IN", None)
        for slot in (1, 17, 32, 33, 38):
            with self.subTest(slot=slot):
                self.assertIsNone(unwritten_in_block(sc, slot))   # there is no token to name
                self.assertIsNone(uin_in_index(sc, slot))
                self.assertEqual(resolve_in_slot_number(sc, slot), 0)
                self.assertEqual(resolve_in_slot(sc, slot), "?")

    def test_a_short_line_names_no_source_past_its_end(self):
        full, sc = Scene.load(EXAMPLE), with_blocks("IN", 2)
        for slot in (1, 16):
            with self.subTest(reached=slot):
                self.assertEqual(resolve_in_slot(sc, slot), resolve_in_slot(full, slot))
                self.assertEqual(uin_in_index(sc, slot), uin_in_index(full, slot))
        for slot in (17, 24, 25, 32, 33, 38):
            with self.subTest(unreached=slot):
                self.assertIsNone(uin_in_index(sc, slot))
                self.assertEqual(resolve_in_slot_number(sc, slot), 0)
                self.assertEqual(resolve_in_slot(sc, slot), "?")

    def test_slots_that_read_no_routed_input_keep_their_names(self):
        full, sc = Scene.load(EXAMPLE), with_blocks("IN", None)
        for slot in (0, 39, 40, 41, 64):
            with self.subTest(slot=slot):
                self.assertEqual(resolve_in_slot(sc, slot), resolve_in_slot(full, slot))
        self.assertEqual(resolve_in_slot(sc, 0), "OFF")

    def test_only_the_bank_the_switch_selects_counts(self):
        full, sc = Scene.load(EXAMPLE), with_blocks("PLAY", 2)
        self.assertEqual(resolve_in_slot(sc, 17), resolve_in_slot(full, 17))   # REC reads IN
        self.assertEqual(resolve_in_slot_number(sc, 17, bank="PLAY"), 0)
        self.assertIsNone(uin_in_index(sc, 17, bank="PLAY"))
        set_routswitch(sc, "PLAY")
        self.assertEqual(resolve_in_slot(sc, 17), "?")

    def test_channel_sources_and_head_amps_follow(self):
        sc = with_blocks("IN", 2)
        by_ch = {c.ch: c.source for c in channel_sources(sc)}
        self.assertEqual((by_ch[1], by_ch[17], by_ch[25]), ("Local input 1", "?", "?"))
        self.assertIsNotNone(channel_headamp_index(sc, 1))
        self.assertIsNone(channel_headamp_index(sc, 17))


class SetInputByNameTest(unittest.TestCase):
    def test_a_name_only_an_unreached_slot_would_read_is_refused_naming_the_fault(self):
        for keep, fault in ((None, "is missing"), (2, r"carries 2 block\(s\), not 5")):
            sc = with_blocks("IN", keep)
            before = sc.dump()
            with self.subTest(keep=keep), self.assertRaisesRegex(
                    ValueError, "^no input slot reads AES50-A input 1 under this scene's "
                                f"/config/routing/IN, which {fault}; give the slot 0-64$"):
                channel_slot(sc, "aes50-a 1")
            self.assertEqual(sc.dump(), before)

    def test_a_line_that_reaches_every_slot_keeps_the_re_patch_hint(self):
        whole = Scene.load(EXAMPLE).dump()
        line = next(ln for ln in whole.split("\n") if ln.startswith("/config/routing/IN "))
        for name, text in (("whole", whole), ("six blocks", whole.replace(line, line + " AUX1-4"))):
            with self.subTest(line=name), self.assertRaisesRegex(
                    ValueError, "/config/routing/IN; re-patch one of its blocks to carry it, or "
                                "give the slot 0-64$"):
                channel_slot(Scene.parse(text), "card 7")

    def test_a_name_a_reached_slot_reads_is_still_found(self):
        self.assertEqual(channel_slot(with_blocks("IN", 2), "local 5"),
                         channel_slot(Scene.load(EXAMPLE), "local 5"))

    def test_a_bare_slot_is_written_as_given(self):
        self.assertEqual(channel_slot(with_blocks("IN", None), 17), 17)


class PlanHeadAmpTest(unittest.TestCase):
    def test_gain_on_a_channel_with_no_known_source_is_refused_saying_so(self):
        sc = with_blocks("IN", 2)
        before = sc.dump()
        with self.assertRaisesRegex(KeyError, r"channel 17 has no head amp: .* or one "
                                              r"`inputs` reads as \?"):
            apply_plan(sc, {"channels": {"17": {"gain_db": 12.5}}})
        self.assertEqual(sc.dump(), before)


class PresetsDiffCliTest(unittest.TestCase):
    def test_a_head_amp_left_uncompared_allows_for_an_unknown_source(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        scene, presets = os.path.join(tmp, "no-in.scn"), os.path.join(tmp, "presets")
        with_blocks("IN", None).save(scene)
        os.mkdir(presets)
        shutil.copy(os.path.join(os.path.dirname(EXAMPLE), "example.chn"),
                    os.path.join(presets, "Kick.chn"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            main(["presets-diff", presets, scene])
        self.assertIn("/headamp/000  not compared: the channel's source has no head amp, or "
                      "`inputs` reads it as ?\n", out.getvalue())


class InputsCliTest(unittest.TestCase):
    def test_inputs_reads_unknown_for_a_channel_past_the_line(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = os.path.join(tmp, "short.scn")
        with_blocks("IN", 2).save(path)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["inputs", path]), 0)
        self.assertRegex(out.getvalue(), r"ch16 .*-> Local input 16\n")
        self.assertRegex(out.getvalue(), r"ch17 .*slot 17 -> \?\n")


if __name__ == "__main__":
    unittest.main()
