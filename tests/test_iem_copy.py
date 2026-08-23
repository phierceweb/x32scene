"""The monitor-send service itself: stereo-link grouping, and the line-shape rule a copy
must respect. A send line's field count is set by its bus's parity, so a copy that moves
fields across that boundary writes a line the console never wrote — which round-trip and a
path-level diff both certify as fine.
"""

import os
import unittest

from x32scene.model import Scene
from x32scene.services import iem as I
from x32scene.services.diff import diff
from x32scene.tables import SEND_STRIPS, send_line_fields

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")

# buses 5/6 linked, channels 11/12 linked, everything else on its own
TEMPLATE_LINES = [
    '#4.0# "Link Template" "" %000000000 1'.ljust(127),
    "/config/buslink OFF OFF ON OFF OFF OFF OFF OFF",
    "/config/chlink OFF OFF OFF OFF OFF ON OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF",
    "/config/auxlink OFF OFF OFF OFF",
    "/config/fxlink OFF OFF OFF OFF",
]
for _ch in (1, 11, 12, 20):
    for _bus in range(1, 7):
        _tail = "+0 PRE   0" if _bus % 2 else ""
        TEMPLATE_LINES.append(f"/ch/{_ch:02d}/mix/{_bus:02d} ON   -{_ch}.0 {_tail}".rstrip())


def template() -> Scene:
    return Scene.parse("\n".join(TEMPLATE_LINES) + "\n")


class SendLinkGroupTest(unittest.TestCase):
    def test_unlinked_bus_is_its_own_group(self):
        self.assertEqual(I.bus_link_group(template(), 1), (1,))

    def test_linked_pair_is_anchored_on_the_odd_bus_from_either_side(self):
        sc = template()
        self.assertEqual(I.bus_link_group(sc, 5), (5, 6))
        self.assertEqual(I.bus_link_group(sc, 6), (5, 6))

    def test_targets_cross_both_link_axes(self):
        sc = template()
        self.assertEqual(sorted(I.iem_send_targets(sc, 11, 5)),
                         [("/ch/11", 5), ("/ch/11", 6), ("/ch/12", 5), ("/ch/12", 6)])
        # naming the even side of either axis is the same set of lines
        self.assertEqual(sorted(I.iem_send_targets(sc, 12, 6)),
                         sorted(I.iem_send_targets(sc, 11, 5)))

    def test_linked_false_confines_the_edit_to_the_named_strip(self):
        sc = template()
        self.assertEqual(sorted(I.iem_send_targets(sc, 11, 5, linked=False)),
                         [("/ch/11", 5), ("/ch/11", 6)])   # the bus axis still mirrors

    def test_copy_destination_buses_match_what_the_copy_writes(self):
        # the whitelist and the write set have to agree for every pairing, not one case
        for src in range(1, 7):
            for dst in range(1, 7):
                if src == dst:
                    continue
                with self.subTest(src=src, dst=dst):
                    sc, base = template(), template()
                    I.copy_iem_mix(sc, src, dst)
                    written = {int(c.path[-2:]) for c in diff(base, sc)}
                    self.assertLessEqual(written, set(I.copy_iem_dst_buses(base, src, dst)))


class CopyShapeTest(unittest.TestCase):
    def shape_errors(self, sc: Scene) -> list[str]:
        return I.send_shape_errors(
            sc, [f"{s}/mix/{b:02d}" for s in SEND_STRIPS for b in range(1, 17)])

    def test_no_copy_on_a_real_scene_changes_any_line_shape(self):
        for src in range(1, 17):
            for dst in range(1, 17):
                if src == dst:
                    continue
                with self.subTest(src=src, dst=dst):
                    sc = Scene.load(EXAMPLE)
                    I.copy_iem_mix(sc, src, dst)
                    self.assertEqual(self.shape_errors(sc), [])

    def test_cross_parity_copy_moves_level_and_leaves_pan_and_tap(self):
        sc, base = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        I.copy_iem_mix(sc, 13, 14)                       # odd -> even, both unlinked
        self.assertEqual(sc.get("/ch/01/mix/14").args[:2],
                         base.get("/ch/01/mix/13").args[:2])
        self.assertEqual(len(sc.get("/ch/01/mix/14").args), send_line_fields(14))
        sc = Scene.load(EXAMPLE)
        I.copy_iem_mix(sc, 14, 13)                       # even -> odd keeps pan and tap
        self.assertEqual(sc.get("/ch/01/mix/13").args[2:],
                         base.get("/ch/01/mix/13").args[2:])

    def test_same_parity_copy_still_moves_every_field(self):
        sc, base = Scene.load(EXAMPLE), Scene.load(EXAMPLE)
        I.copy_iem_mix(sc, 3, 11)
        for ch in range(1, 33):
            self.assertEqual(sc.get(f"/ch/{ch:02d}/mix/11").args,
                             base.get(f"/ch/{ch:02d}/mix/03").args)

    def test_a_linked_destination_pair_is_never_left_half_written(self):
        # what the console reverts on recall is the DESTINATION pair, so its two sides
        # must agree on (on, level) however the source is configured
        for src in (5, 13, 14):
            with self.subTest(src=src):
                sc = Scene.load(EXAMPLE)
                I.copy_iem_mix(sc, src, 11)              # buses 11/12 are linked
                for strip in SEND_STRIPS:
                    a, b = sc.get(f"{strip}/mix/11"), sc.get(f"{strip}/mix/12")
                    if a and b:
                        self.assertEqual(a.args[:2], b.args[:2], strip)

    def test_copying_a_bus_onto_itself_raises(self):
        with self.assertRaises(ValueError):
            I.copy_iem_mix(Scene.load(EXAMPLE), 5, 5)



if __name__ == "__main__":
    unittest.main(verbosity=2)
