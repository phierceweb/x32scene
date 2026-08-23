"""Transform tests: each edit changes ONLY its intended lines, nothing else."""

import os
import unittest

from x32scene import Scene
from x32scene.services.diff import diff
from x32scene import iem as I
from x32scene import transforms as T

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")


def changed_paths(before: Scene, after: Scene) -> list[str]:
    return [c.path for c in diff(before, after)]


class TransformTest(unittest.TestCase):
    def setUp(self):
        self.base = Scene.load(EXAMPLE)
        self.work = Scene.load(EXAMPLE)

    def test_retitle_only_touches_header(self):
        T.retitle_scene(self.work, "Test Scene")
        self.assertEqual(changed_paths(self.base, self.work), ["#4.0#"])
        self.assertEqual(self.work.name, "Test Scene")
        # header stays padded to fixed width
        self.assertEqual(len(self.work.lines[0].raw), 127)

    def test_rename_channel_only_touches_one_config(self):
        T.rename_channel(self.work, 20, "Gtr 3")
        self.assertEqual(changed_paths(self.base, self.work), ["/ch/20/config"])

    def test_set_headamp_only_touches_one_headamp(self):
        T.set_headamp(self.work, "local", 4, gain_db=22.5, phantom=True)
        self.assertEqual(changed_paths(self.base, self.work), ["/headamp/003"])
        self.assertEqual(self.work.get("/headamp/003").args[:2], ["+22.5", "ON"])

    def test_set_headamp_rejects_non_finite_and_out_of_range(self):
        # a head amp has no -oo: unlike a fader, -inf is out of range here too
        for gain in (float("nan"), float("inf"), float("-inf"), 1e9, -12.1, 60.1):
            with self.subTest(gain=gain), self.assertRaises(ValueError):
                T.set_headamp(self.work, "local", 1, gain_db=gain)
        self.assertEqual(changed_paths(self.base, self.work), [])
        T.set_headamp(self.work, "local", 1, phantom=True)   # gain_db=None is untouched
        for gain in (-12.0, 0.0, 60.0):
            with self.subTest(gain=gain):
                T.set_headamp(self.work, "local", 1, gain_db=gain)
        self.assertEqual(self.work.get("/headamp/000").args, ["+60.0", "ON"])

    def test_set_iem_send_one_line(self):
        I.set_iem_send(self.work, 17, 7, on=True, level_db=-3.0)
        self.assertEqual(changed_paths(self.base, self.work), ["/ch/17/mix/07"])

    def test_route_output_from_bus(self):
        T.route_output_from_bus(self.work, 5, 1)  # out 5 <- bus 1 (tap 4)
        self.assertEqual(changed_paths(self.base, self.work), ["/outputs/main/05"])
        self.assertEqual(self.work.get("/outputs/main/05").args[0], "4")

    def test_copy_iem_mix_linked_pair_copies_both_sides(self):
        # bus 3/4 and 11/12 are stereo-linked; copying 3->11 must ALSO copy 4->12,
        # else the console's stereo link reverts bus 11's level to the untouched even side.
        I.copy_iem_mix(self.work, 3, 11)
        changed = changed_paths(self.base, self.work)
        self.assertTrue(any(p.endswith("/mix/12") for p in changed),
                        "even bus (12) must be copied too on a linked pair")
        for ch in range(1, 33):
            self.assertEqual(self.work.get(f"/ch/{ch:02d}/mix/11").args,
                             self.base.get(f"/ch/{ch:02d}/mix/03").args)
            self.assertEqual(self.work.get(f"/ch/{ch:02d}/mix/12").args,
                             self.base.get(f"/ch/{ch:02d}/mix/04").args)

    def test_copy_iem_mix_stereo_false_copies_only_odd(self):
        I.copy_iem_mix(self.work, 3, 11, stereo=False)
        self.assertTrue(all(not p.endswith("/mix/12")
                            for p in changed_paths(self.base, self.work)))

    def test_no_op_changes_nothing(self):
        # set the same value already present -> zero changed lines
        cur = self.work.get("/outputs/main/01").args[0]
        T.set_output_tap(self.work, 1, int(cur))
        self.assertEqual(changed_paths(self.base, self.work), [])

    def test_port_output_routing_copies_tap_point_fields(self):
        # a PRE/POST or polarity difference must port too, not just the tap number
        src = Scene.load(EXAMPLE)
        dst = Scene.load(EXAMPLE_ALT)
        src.get("/outputs/main/05").set_arg(1, "PRE")
        T.port_output_routing(src, dst)
        self.assertEqual(dst.get("/outputs/main/05").args,
                         src.get("/outputs/main/05").args)

    def test_port_output_routing_across_scenes_changes_only_outputs(self):
        src = Scene.load(EXAMPLE)
        dst = Scene.load(EXAMPLE_ALT)
        dst_before = Scene.load(EXAMPLE_ALT)
        n = T.port_output_routing(src, dst)
        self.assertGreater(n, 0)
        paths = changed_paths(dst_before, dst)
        self.assertTrue(all(p.startswith("/outputs/main/") or p.startswith("/outputs/aux/")
                            for p in paths), paths)
        # and the result still round-trips
        Scene.parse(dst.dump())

    def test_rename_rejects_quote_in_name(self):
        # '24" Kick' would tokenize to 5 args on reparse and shift every field —
        # and the path-level diff would still pass it.
        with self.assertRaises(ValueError):
            T.rename_channel(self.work, 1, '24" Kick')
        self.assertEqual(changed_paths(self.base, self.work), [])

    def test_rename_strip_families(self):
        for strip, path in (("/bus/01", "/bus/01/config"),
                            ("/dca/1", "/dca/1/config"),
                            ("/fxrtn/01", "/fxrtn/01/config"),
                            (7, "/ch/07/config")):
            with self.subTest(strip=strip):
                work = Scene.load(EXAMPLE)
                T.rename_strip(work, strip, "New Name")
                self.assertEqual(changed_paths(self.base, work), [path])
                self.assertEqual(work.get(path).args[0], '"New Name"')

    def test_rename_strip_rejects_quotes(self):
        with self.assertRaises(ValueError):
            T.rename_strip(self.work, "/bus/01", 'a"b')

    def test_retitle_rejects_newline(self):
        with self.assertRaises(ValueError):
            T.retitle_scene(self.work, "a\nb")

    def test_retitle_empty_scene_raises_value_error(self):
        with self.assertRaises(ValueError):
            T.retitle_scene(Scene.parse(""), "X")

    def test_set_iem_send_writes_signed_level(self):
        I.set_iem_send(self.work, 1, 1, level_db=3.5)
        self.assertEqual(self.work.get("/ch/01/mix/01").args[1], "+3.5")

    def test_set_iem_send_same_level_is_noop(self):
        # fixture already holds +2.8; unsigned formatting would rebuild the line
        I.set_iem_send(self.work, 1, 1, level_db=2.8)
        self.assertEqual(changed_paths(self.base, self.work), [])

    def test_set_iem_send_zero_is_unsigned_and_noop(self):
        # send-level zero is written UNSIGNED ('0.0') by the console, unlike headamp
        # gain ('+0.0') — the sign convention is per-field
        I.set_iem_send(self.work, 1, 11, level_db=0.0)  # fixture line already at 0.0
        self.assertEqual(changed_paths(self.base, self.work), [])
        I.set_iem_send(self.work, 1, 1, level_db=0.0)
        self.assertEqual(self.work.get("/ch/01/mix/01").args[1], "0.0")

    def test_move_input_rejects_malformed_uin_block(self):
        inb = self.work.get("/config/routing/IN")
        inb.args[0] = "UIN0-7"  # consoles never write this; index math would go negative
        inb.rebuild()
        with self.assertRaises(ValueError):
            T.move_input_to_stagebox(self.work, 1, 5, port="A")

    def test_move_input_honors_offset_uin_block(self):
        # with banks swapped, ch1's UIN slot lives at userrout/in entry 9 (index 8)
        inb = self.work.get("/config/routing/IN")
        inb.args[0], inb.args[1] = "UIN9-16", "UIN1-8"
        inb.rebuild()
        T.move_input_to_stagebox(self.work, 1, 5, port="A")
        uin = self.work.get("/config/userrout/in")
        self.assertEqual(uin.args[8], "37")                       # 32 + 5
        self.assertEqual(uin.args[0], self.base.get("/config/userrout/in").args[0])

    def test_move_input_rejects_out_of_range_aes_input(self):
        for bad in (0, 49):
            with self.assertRaises(ValueError):
                T.move_input_to_stagebox(self.work, 1, bad, port="A")
        self.assertEqual(changed_paths(self.base, self.work), [])

    def test_set_headamp_rejects_out_of_range_input(self):
        with self.assertRaises(ValueError):
            T.set_headamp(self.work, "local", 33, gain_db=10.0)
        with self.assertRaises(ValueError):
            T.set_headamp(self.work, "aesa", 49, gain_db=10.0)
        self.assertEqual(changed_paths(self.base, self.work), [])

    def test_copy_iem_mix_carries_auxin_and_fxrtn_sends(self):
        # a player's ears include FX returns (reverb) and aux-ins (click/ambience);
        # copying only /ch sends silently drops them
        I.copy_iem_mix(self.work, 3, 11)
        for path in ("/auxin/05", "/fxrtn/01"):
            with self.subTest(strip=path):
                self.assertEqual(self.work.get(f"{path}/mix/11").args,
                                 self.base.get(f"{path}/mix/03").args)

    def test_copy_iem_mix_even_linked_pair_copies_both_sides(self):
        # buses 3/4 and 11/12 are linked; copying between the EVEN members must still
        # carry the odd partner, or the console reconciles the pair on recall
        I.copy_iem_mix(self.work, 4, 12)
        changed = changed_paths(self.base, self.work)
        self.assertTrue(any(p.endswith("/mix/11") for p in changed),
                        "odd partner (11) must be copied too on a linked pair")
        for ch in range(1, 33):
            self.assertEqual(self.work.get(f"/ch/{ch:02d}/mix/11").args,
                             self.base.get(f"/ch/{ch:02d}/mix/03").args)

    def test_batch_stagebox_move_is_atomic(self):
        # a mid-batch failure must not leave earlier moves applied
        with self.assertRaises(ValueError):
            T.move_inputs_to_stagebox(self.work, {1: 1, 2: 99}, port="A")
        self.assertEqual(changed_paths(self.base, self.work), [])

    # fader / mute / pan / level-token tests live in test_transforms_mix.py

    def test_edited_scene_still_roundtrips(self):
        T.rename_channel(self.work, 1, "Kick In")
        T.set_headamp(self.work, "local", 1, gain_db=30.0)
        reparsed = Scene.parse(self.work.dump())
        self.assertEqual(reparsed.dump(), self.work.dump())


if __name__ == "__main__":
    unittest.main(verbosity=2)
