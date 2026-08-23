"""The band-setup plan's `outputs` key: point a physical output at a mix bus."""

import unittest

from x32scene.model import Scene
from x32scene.orchestrators.band_swap import apply_plan, verify

HEADER = '#4.0# "Out Template" "" %000000000 1'.ljust(127)
TEMPLATE_LINES = [
    HEADER,
    "/config/buslink OFF OFF OFF OFF OFF OFF OFF OFF",
    "/outputs/main/09 6 POST OFF",   # tap 6 = bus 3
    "/outputs/main/10 7 POST OFF",   # tap 7 = bus 4
]


def template() -> Scene:
    return Scene.parse("\n".join(TEMPLATE_LINES) + "\n")


class OutputRoutingPlanTest(unittest.TestCase):
    """`outputs` re-points a physical output at a mix bus (tap = bus + 3)."""

    def test_routes_outputs_from_named_buses(self):
        sc = template()
        apply_plan(sc, {"outputs": {"9": 1, "10": 2}})
        self.assertEqual(sc.get("/outputs/main/09").args[0], "4")
        self.assertEqual(sc.get("/outputs/main/10").args[0], "5")

    def test_tap_point_and_polarity_are_untouched(self):
        sc = template()
        apply_plan(sc, {"outputs": {"9": 1}})
        self.assertEqual(sc.get("/outputs/main/09").args[1:], ["POST", "OFF"])

    def test_only_the_routed_line_is_rebuilt(self):
        sc = template()
        apply_plan(sc, {"outputs": {"9": 1}})
        want = list(TEMPLATE_LINES)
        want[want.index("/outputs/main/09 6 POST OFF")] = "/outputs/main/09 4 POST OFF"
        self.assertEqual(sc.dump().splitlines(), want)

    def test_verify_allows_only_the_named_outputs(self):
        tmpl, sc = template(), template()
        plan = {"outputs": {"9": 1, "10": 2}}
        apply_plan(sc, plan)
        report = verify(tmpl, sc, plan)
        self.assertEqual(report["unexpected"], [])
        self.assertEqual(sorted(report["changed"]),
                         ["/outputs/main/09", "/outputs/main/10"])

    def test_out_of_plan_output_edit_is_flagged(self):
        tmpl, sc = template(), template()
        plan = {"outputs": {"9": 1}}
        apply_plan(sc, plan)
        sc.get("/outputs/main/10").set_arg(0, "9")
        self.assertEqual(verify(tmpl, sc, plan)["unexpected"], ["/outputs/main/10"])

    def test_unknown_output_raises(self):
        with self.assertRaises(KeyError):
            apply_plan(template(), {"outputs": {"3": 1}})

    def test_out_of_range_raises(self):
        for bad in ({"0": 1}, {"17": 1}, {"9": 0}, {"9": 17}):
            with self.subTest(outputs=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), {"outputs": bad})

    def test_non_integer_bus_is_type_checked(self):
        # True would otherwise route from bus 1, and "1" from a stray JSON string
        for bad in ({"9": True}, {"9": "1"}, {"9": 1.5}, {"9": None}):
            with self.subTest(outputs=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), {"outputs": bad})
