"""A user-in slot the user patch does not hold, the line missing or short of the slot's
index, names no source; and a channel line that ends in no slot number is named in the
error."""

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
                                       resolve_in_slot_number, uin_in_index)

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "example-preflight.json")


def with_user_patch(keep: int | None) -> Scene:
    """example.scn with ``/config/userrout/in`` cut to its first ``keep`` slots, or dropped
    (None)."""
    out = []
    for raw in Scene.load(EXAMPLE).dump().split("\n"):
        if raw.startswith("/config/userrout/in "):
            if keep is None:
                continue
            raw = " ".join(raw.split(" ")[:keep + 1])
        out.append(raw)
    return Scene.parse("\n".join(out))


def with_config_tail(ch: int, tail: str) -> Scene:
    """example.scn with the slot ending ``/ch/NN/config`` replaced by ``tail``."""
    text = Scene.load(EXAMPLE).dump().split("\n")
    at = next(i for i, raw in enumerate(text) if raw.startswith(f"/ch/{ch:02d}/config "))
    text[at] = text[at].rsplit(" ", 1)[0] + tail
    return Scene.parse("\n".join(text))


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class UserPatchUnreadTest(unittest.TestCase):
    def setUp(self):
        self.full = Scene.load(EXAMPLE)

    def test_a_missing_line_names_no_source_for_a_user_in_slot(self):
        sc = with_user_patch(None)
        for slot in (1, 16, 25, 29, 32):
            with self.subTest(slot=slot):
                self.assertEqual(resolve_in_slot(sc, slot), "?")
                self.assertEqual(resolve_in_slot_number(sc, slot), 0)
                self.assertEqual(uin_in_index(sc, slot), uin_in_index(self.full, slot))

    def test_a_short_line_names_no_source_past_its_end(self):
        sc = with_user_patch(16)
        for slot in (1, 16):
            with self.subTest(held=slot):
                self.assertEqual(resolve_in_slot(sc, slot), resolve_in_slot(self.full, slot))
        for slot in (25, 29, 32):
            with self.subTest(past=slot):
                self.assertEqual(resolve_in_slot(sc, slot), "?")

    def test_a_slot_that_reads_no_user_patch_keeps_its_name(self):
        sc = with_user_patch(None)
        for slot in (0, 17, 24, 33, 38, 39, 40, 41, 64):
            with self.subTest(slot=slot):
                self.assertEqual(resolve_in_slot(sc, slot), resolve_in_slot(self.full, slot))

    def test_a_user_in_slot_patched_to_nothing_still_reads_off(self):
        self.assertEqual(self.full.get("/config/userrout/in").args[28], "0")
        self.assertEqual(resolve_in_slot(self.full, 29), "OFF")
        self.assertEqual(resolve_in_slot(with_user_patch(29), 29), "OFF")
        self.assertEqual(resolve_in_slot(with_user_patch(28), 29), "?")

    def test_channel_sources_and_head_amps_follow(self):
        sc = with_user_patch(None)
        by_ch = {cs.ch: cs.source for cs in channel_sources(sc)}
        self.assertEqual(by_ch[1], "?")
        self.assertEqual(by_ch[17], resolve_in_slot(self.full, 17))
        self.assertIsNone(channel_headamp_index(sc, 1))
        self.assertEqual(channel_headamp_index(sc, 17), channel_headamp_index(self.full, 17))

    def test_inputs_reads_unknown(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = os.path.join(tmp, "no-patch.scn")
        with_user_patch(None).save(path)
        rc, out, _ = run("inputs", path)
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"ch01 .*slot  1 -> \?\n")
        self.assertRegex(out, r"ch17 .*slot 17 -> AES50-A input 1\n")

    def test_a_plan_gain_there_is_refused_naming_which_sources_have_a_head_amp(self):
        sc = with_user_patch(None)
        before = sc.dump()
        with self.assertRaisesRegex(KeyError, r"channel 1 has no head amp: its source is not a "
                                              r"local or AES50 input, or one `inputs` reads "
                                              r"as \?"):
            apply_plan(sc, {"channels": {"1": {"gain_db": 12.5}}})
        self.assertEqual(sc.dump(), before)


class ConfigSlotTest(unittest.TestCase):
    def test_a_line_ending_in_no_slot_number_is_named(self):
        for tail, last in (("", "YEi"), (" x", "x"), (" 1.5", "1.5")):
            with self.subTest(tail=tail):
                sc = with_config_tail(1, tail)
                want = rf"^/ch/01/config ends in '{last}', not a source slot$"
                with self.assertRaisesRegex(ValueError, want):
                    channel_headamp_index(sc, 1)
                with self.assertRaisesRegex(ValueError, want):
                    channel_sources(sc)

    def test_a_slot_number_reads_as_before(self):
        for tail, source in ((" 1", "Local input 1"), (" 0", "OFF"), (" -1", "?"), (" 65", "?")):
            with self.subTest(tail=tail):
                self.assertEqual(channel_sources(with_config_tail(1, tail))[0].source, source)

    def test_the_commands_say_which_line(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = os.path.join(tmp, "no-slot.scn")
        with_config_tail(1, "").save(path)
        for argv in (("inputs", path), ("preflight", path, "--config", EXAMPLE_CONFIG),
                     ("presets-diff", os.path.dirname(EXAMPLE), path),
                     ("move-inputs", path, "1:1", "--to", "A", "-o", os.path.join(tmp, "o.scn"))):
            with self.subTest(cmd=argv[0]):
                rc, _, err = run(*argv)
                self.assertEqual((rc, err), (1, "x32scene: /ch/01/config ends in 'YEi', not a "
                                                "source slot\n"))


if __name__ == "__main__":
    unittest.main()
