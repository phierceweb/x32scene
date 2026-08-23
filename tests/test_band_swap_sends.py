"""Band-swap plan keys that touch routing and monitor sends: `outputs` and `iem_sends`.

The template here is deliberately richer than test_band_swap.py's: it carries a linked bus
pair, a linked channel pair, an aux-in and an OFF send, because every mirroring and
refusal rule below is invisible on an all-unlinked scene.
"""

import os
import tempfile
import unittest

from x32scene.model import Scene
from x32scene.orchestrators.band_swap import apply_plan, run, verify

HEADER = '#4.0# "Send Template" "" %000000000 1'.ljust(127)
# buslink pair 3 = buses 5/6; chlink pair 6 = channels 11/12. Everything else unlinked.
# Send lines follow the console's shape: odd bus 5 fields, even bus 2 (send_line_fields).
TEMPLATE_LINES = [
    HEADER,
    "/config/buslink OFF OFF ON OFF OFF OFF OFF OFF",
    "/config/chlink OFF OFF OFF OFF OFF ON OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF",
    "/config/auxlink OFF OFF OFF OFF",
    "/config/fxlink OFF OFF OFF OFF",
    '/ch/01/config "Kick" 1 67 1',
    "/ch/01/mix/01 ON   -6.0 +0 PRE   0",
    "/ch/01/mix/03 ON   -2.0 +0 PRE   0",
    "/ch/01/mix/04 ON   -5.0",
    "/ch/01/mix/05 ON   -4.0 +0 PRE   0",
    "/ch/01/mix/06 ON   -4.0",
    '/ch/11/config "OH L" 1 67 11',
    "/ch/11/mix/05 ON   -8.0 -100 PRE   0",
    "/ch/11/mix/06 ON   -8.0",
    '/ch/12/config "OH R" 1 67 12',
    "/ch/12/mix/05 ON   -8.0 +100 PRE   0",
    "/ch/12/mix/06 ON   -8.0",
    '/ch/20/config "Gtr 1" 1 67 20',
    "/ch/20/mix/01 ON   -3.0 +0 PRE   0",
    "/ch/20/mix/03 OFF   -9.0 +0 PRE   0",
    "/ch/20/mix/05 ON   -3.0 +0 PRE   0",
    "/ch/20/mix/06 ON   -3.0",
    "/auxin/05/mix/05 ON   -12.0 -100 PRE   0",
    "/auxin/05/mix/06 ON   -12.0",
    "/fxrtn/03/mix/05 ON   -18.0 +0 PRE   0",
    "/fxrtn/03/mix/06 ON   -18.0",
    "/outputs/main/09 6 POST OFF",   # tap 6 = bus 3
    "/outputs/main/10 7 POST OFF",   # tap 7 = bus 4
]


def template() -> Scene:
    return Scene.parse("\n".join(TEMPLATE_LINES) + "\n")


def level(sc: Scene, path: str, bus: int) -> str:
    return sc.get(f"{path}/mix/{bus:02d}").args[1]


class IemSendsApplyTest(unittest.TestCase):
    def test_trims_an_unmirrored_send(self):
        sc = template()
        apply_plan(sc, {"iem_sends": [{"strip": 20, "bus": 1, "level": -14.0}]})
        self.assertEqual(level(sc, "/ch/20", 1), "-14.0")

    def test_level_alone_leaves_the_on_flag_pan_and_tap_alone(self):
        sc = template()
        apply_plan(sc, {"iem_sends": [{"strip": 20, "bus": 1, "level": -14.0}]})
        self.assertEqual(sc.get("/ch/20/mix/01").args, ["ON", "-14.0", "+0", "PRE", "0"])

    def test_mirrors_across_a_linked_bus_pair(self):
        # buses 5/6 are linked: a one-sided write is reverted by the console on recall
        sc = template()
        apply_plan(sc, {"iem_sends": [{"strip": 20, "bus": 5, "level": -20.0}]})
        self.assertEqual(level(sc, "/ch/20", 5), "-20.0")
        self.assertEqual(level(sc, "/ch/20", 6), "-20.0")

    def test_naming_either_side_of_a_linked_pair_is_the_same_edit(self):
        a, b = template(), template()
        apply_plan(a, {"iem_sends": [{"strip": 20, "bus": 5, "level": -20.0}]})
        apply_plan(b, {"iem_sends": [{"strip": 20, "bus": 6, "level": -20.0}]})
        self.assertEqual(a.dump(), b.dump())

    def test_mirrors_across_both_stereo_axes(self):
        # ch 11/12 linked AND buses 5/6 linked: one record, four send lines
        sc = template()
        apply_plan(sc, {"iem_sends": [{"strip": 11, "bus": 5, "level": -16.0}]})
        for path in ("/ch/11", "/ch/12"):
            for bus in (5, 6):
                self.assertEqual(level(sc, path, bus), "-16.0", f"{path} bus {bus}")

    def test_reaches_aux_ins_and_fx_returns(self):
        for strip in ("/auxin/05", "/fxrtn/03"):
            with self.subTest(strip=strip):
                sc = template()
                apply_plan(sc, {"iem_sends": [{"strip": strip, "bus": 5, "level": -30.0}]})
                self.assertEqual(level(sc, strip, 5), "-30.0")
                self.assertEqual(level(sc, strip, 6), "-30.0")

    def test_on_false_switches_a_send_out_without_a_level(self):
        sc = template()
        apply_plan(sc, {"iem_sends": [{"strip": 20, "bus": 1, "on": False}]})
        self.assertEqual(sc.get("/ch/20/mix/01").args[0], "OFF")

    def test_trim_survives_a_copy_of_the_same_bus(self):
        # copy replaces the destination line wholesale, so ordering is the whole feature:
        # a count or an empty-diff proxy passes either way, only the token catches a swap
        sc = template()
        apply_plan(sc, {"iem_copy": [{"src": 1, "dst": 3}],
                        "iem_sends": [{"strip": 20, "bus": 3, "level": -25.0, "on": True}]})
        self.assertEqual(level(sc, "/ch/01", 3), "-6.0")     # copied from bus 1
        self.assertEqual(level(sc, "/ch/20", 3), "-25.0")    # trimmed on top of the copy

    def test_missing_mirror_partner_is_skipped_not_fatal(self):
        lines = [ln for ln in TEMPLATE_LINES if ln != "/ch/20/mix/06 ON   -3.0"]
        sc = Scene.parse("\n".join(lines) + "\n")
        apply_plan(sc, {"iem_sends": [{"strip": 20, "bus": 5, "level": -20.0}]})
        self.assertEqual(level(sc, "/ch/20", 5), "-20.0")

    def test_missing_named_send_raises(self):
        with self.assertRaises(KeyError):
            apply_plan(template(), {"iem_sends": [{"strip": 32, "bus": 1, "level": -6.0}]})

    def test_level_alone_on_an_off_send_raises(self):
        # /ch/20/mix/03 is OFF: the level would change nothing audible and verify, which
        # only sees the rebuilt line, would still report success
        with self.assertRaises(ValueError) as ctx:
            apply_plan(template(), {"iem_sends": [{"strip": 20, "bus": 3, "level": -6.0}]})
        self.assertIn("OFF", str(ctx.exception))

    def test_buslink_absent_raises_rather_than_guessing(self):
        lines = [ln for ln in TEMPLATE_LINES if not ln.startswith("/config/buslink")]
        sc = Scene.parse("\n".join(lines) + "\n")
        with self.assertRaises(KeyError):
            apply_plan(sc, {"iem_sends": [{"strip": 20, "bus": 5, "level": -20.0}]})


class IemSendsValidationTest(unittest.TestCase):
    def send(self, **rec):
        return {"iem_sends": [rec]}

    def test_unknown_record_key_raises(self):
        for bad in ({"ch": 20}, {"lvl": -6.0}, {"level_db": -6.0}):
            with self.subTest(rec=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), self.send(strip=20, bus=1, **bad))

    def test_strip_must_name_a_send_strip(self):
        for bad in (0, 33, True, "/bus/01", "/main/st", 20.0, None, [20]):
            with self.subTest(strip=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), self.send(strip=bad, bus=1, level=-6.0))

    def test_bus_is_int_strict_and_range_checked(self):
        for bad in (0, 17, True, "1", 1.0, None):
            with self.subTest(bus=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), self.send(strip=20, bus=bad, level=-6.0))

    def test_level_is_range_checked_and_string_forms_restricted(self):
        # "oo" reads as "open" to a plan author but parses as -inf, killing the send;
        # a quoted number is the other likely JSON slip
        for bad in ("oo", "-6.0", True, None, -90.1, 10.1, [-6.0]):
            with self.subTest(level=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), self.send(strip=20, bus=1, level=bad))

    def test_minus_infinity_and_the_range_edges_are_accepted(self):
        for good, want in (("-oo", "-oo"), (-90.0, "-90.0"), (10.0, "+10.0")):
            with self.subTest(level=good):
                sc = template()
                apply_plan(sc, self.send(strip=20, bus=1, level=good))
                self.assertEqual(level(sc, "/ch/20", 1), want)

    def test_on_must_be_a_real_bool(self):
        for bad in (1, 0, "false", "true"):
            with self.subTest(on=bad):
                with self.assertRaises(ValueError):
                    apply_plan(template(), self.send(strip=20, bus=1, on=bad))

    def test_on_true_needs_a_level(self):
        # an OFF send keeps a stored level that `x32scene iem` hides, so unmuting blind can
        # drop a strip into someone's ears at an unknown level
        with self.assertRaises(ValueError):
            apply_plan(template(), self.send(strip=20, bus=3, on=True))

    def test_record_with_neither_level_nor_on_raises(self):
        with self.assertRaises(ValueError):
            apply_plan(template(), self.send(strip=20, bus=1))

    def test_duplicate_strip_and_bus_raises(self):
        plan = {"iem_sends": [{"strip": 20, "bus": 1, "level": -6.0},
                              {"strip": 20, "bus": 1, "level": -9.0}]}
        with self.assertRaises(ValueError):
            apply_plan(template(), plan)

    def test_duplicate_via_a_linked_alias_raises(self):
        # buses 5 and 6 are the same send once the link mirrors it
        plan = {"iem_sends": [{"strip": 20, "bus": 5, "level": -6.0},
                              {"strip": 20, "bus": 6, "level": -9.0}]}
        with self.assertRaises(ValueError):
            apply_plan(template(), plan)

    def test_duplicate_via_a_linked_channel_alias_raises(self):
        plan = {"iem_sends": [{"strip": 11, "bus": 5, "level": -6.0},
                              {"strip": 12, "bus": 5, "level": -9.0}]}
        with self.assertRaises(ValueError):
            apply_plan(template(), plan)

    def test_bus_major_dict_raises_a_plain_value_error(self):
        # the shape a nested-map-minded author writes; an AttributeError here would escape
        # the CLI's (KeyError, ValueError, OSError) boundary and lose "nothing written"
        with self.assertRaises(ValueError):
            apply_plan(template(), {"iem_sends": {"5": {"20": -6.0}}})

    def test_record_must_be_an_object(self):
        with self.assertRaises(ValueError):
            apply_plan(template(), {"iem_sends": [[20, 1, -6.0]]})


class IemSendsVerifyTest(unittest.TestCase):
    def test_whitelist_covers_every_mirrored_path(self):
        tmpl, sc = template(), template()
        plan = {"iem_sends": [{"strip": 11, "bus": 5, "level": -16.0}]}
        apply_plan(sc, plan)
        report = verify(tmpl, sc, plan)
        self.assertEqual(report["unexpected"], [])
        self.assertEqual(sorted(report["changed"]),
                         ["/ch/11/mix/05", "/ch/11/mix/06",
                          "/ch/12/mix/05", "/ch/12/mix/06"])

    def test_whitelist_is_not_wider_than_the_record(self):
        tmpl, sc = template(), template()
        plan = {"iem_sends": [{"strip": 20, "bus": 1, "level": -14.0}]}
        apply_plan(sc, plan)
        sc.get("/ch/01/mix/01").set_arg(1, "-30.0")
        self.assertEqual(verify(tmpl, sc, plan)["unexpected"], ["/ch/01/mix/01"])

    def test_copy_blesses_only_the_buses_it_writes(self):
        # a +/-1 window would whitelist buses 2 and 4 for a copy onto bus 3, letting a
        # stray send in an unrelated mix pass verify unflagged
        tmpl, sc = template(), template()
        plan = {"iem_copy": [{"src": 1, "dst": 3}]}
        apply_plan(sc, plan)
        sc.get("/ch/01/mix/04").set_arg(1, "-30.0")
        self.assertEqual(verify(tmpl, sc, plan)["unexpected"], ["/ch/01/mix/04"])

    def test_a_malformed_send_line_is_reported_even_when_its_path_is_allowed(self):
        # neither round-trip nor the path whitelist can see a field-count change
        tmpl, sc = template(), template()
        plan = {"iem_sends": [{"strip": 20, "bus": 1, "level": -14.0}]}
        apply_plan(sc, plan)
        ln = sc.get("/ch/20/mix/01")
        ln.args = ln.args[:2]           # drop pan/tap from an odd bus
        ln.rebuild()
        report = verify(tmpl, sc, plan)
        self.assertEqual(report["unexpected"], [])
        self.assertEqual(len(report["malformed"]), 1)
        self.assertIn("/ch/20/mix/01", report["malformed"][0])


EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


class NewWritePathRoundTripTest(unittest.TestCase):
    def test_iem_sends_and_outputs_round_trip_on_a_real_scene(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.scn")
            plan = {"iem_copy": [{"src": 13, "dst": 14}],
                    "iem_sends": [{"strip": 23, "bus": 9, "level": -14.0}],
                    "outputs": {"9": 1, "10": 2}}
            report = run(EXAMPLE, plan, out)
            self.assertEqual(report["unexpected"], [])
            self.assertEqual(report["malformed"], [])
            with open(out, encoding="utf-8", newline="") as fh:
                text = fh.read()
            self.assertEqual(Scene.parse(text).dump(), text)
