"""Mix-line transforms: fader / mute / pan tokens, link mirroring, strip addressing."""

import os
import unittest

from x32scene import Scene
from x32scene.services.diff import diff
from x32scene import transforms as T

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def changed_paths(before: Scene, after: Scene) -> list[str]:
    return [c.path for c in diff(before, after)]


class MixLineTransformTest(unittest.TestCase):
    def setUp(self):
        self.base = Scene.load(EXAMPLE)
        self.work = Scene.load(EXAMPLE)

    def test_set_fader_writes_level_convention(self):
        T.set_fader(self.work, 1, -6.5)
        self.assertEqual(changed_paths(self.base, self.work), ["/ch/01/mix"])
        self.assertEqual(self.work.get("/ch/01/mix").args[1], "-6.5")
        T.set_fader(self.work, 1, float("-inf"))
        self.assertEqual(self.work.get("/ch/01/mix").args[1], "-oo")

    def test_set_fader_zero_is_unsigned(self):
        T.set_fader(self.work, "/fxrtn/01", 0.0)   # fixture already holds 0.0 -> no-op
        self.assertEqual(changed_paths(self.base, self.work), [])

    def test_set_fader_near_zero_is_unsigned(self):
        # a level that only rounds to zero must still write the corpus's bare '0.0'
        for level in (0.03, -0.04):
            with self.subTest(level=level):
                T.set_fader(self.work, 1, level)
                self.assertEqual(self.work.get("/ch/01/mix").args[1], "0.0")

    def test_set_fader_rejects_non_finite_and_out_of_range(self):
        for level in (float("nan"), float("inf"), 1e9, -500.0, 10.1, -90.1):
            with self.subTest(level=level), self.assertRaises(ValueError):
                T.set_fader(self.work, 1, level)
        self.assertEqual(changed_paths(self.base, self.work), [])
        for level in (-90.0, 10.0, float("-inf")):
            with self.subTest(level=level):
                T.set_fader(self.work, 1, level)

    def test_parse_level_spellings(self):
        self.assertEqual(T.parse_level("-oo"), float("-inf"))
        self.assertEqual(T.parse_level("oo"), float("-inf"))
        self.assertEqual(T.parse_level("-6.5"), -6.5)
        self.assertEqual(T.parse_level(0), 0.0)
        with self.assertRaises(ValueError):
            T.parse_level("loud")

    def test_set_fader_and_mute_mirror_a_linked_pair(self):
        # ch 11/12 are chlinked and the fixture's linkcfg fdrmute token is ON
        self.assertEqual(T.set_fader(self.work, 11, -7.5), ["/ch/11", "/ch/12"])
        self.assertEqual(changed_paths(self.base, self.work),
                         ["/ch/11/mix", "/ch/12/mix"])
        self.assertEqual(self.work.get("/ch/12/mix").args[1], "-7.5")
        work2 = Scene.load(EXAMPLE)
        self.assertEqual(T.set_mute(work2, 11), ["/ch/11", "/ch/12"])
        self.assertEqual(work2.get("/ch/12/mix").args[0], "OFF")

    def test_set_fader_linked_false_edits_one_side(self):
        self.assertEqual(T.set_fader(self.work, 11, -7.5, linked=False), ["/ch/11"])
        self.assertEqual(changed_paths(self.base, self.work), ["/ch/11/mix"])

    def test_strip_number_width_is_canonicalized(self):
        T.set_fader(self.work, "/dca/03", -3.0)
        self.assertEqual(self.work.get("/dca/3").args[1], "-3.0")
        T.rename_strip(self.work, "/bus/1", "Wedge L")
        self.assertEqual(self.work.get("/bus/01/config").args[0], '"Wedge L"')

    def test_set_fader_on_dca(self):
        T.set_fader(self.work, "/dca/1", -3.0)
        self.assertEqual(changed_paths(self.base, self.work), ["/dca/1"])
        self.assertEqual(self.work.get("/dca/1").args[1], "-3.0")

    def test_dca_subpath_is_not_a_mix_line(self):
        # /dca/N resolves verbatim; anything deeper must not fall through to it
        for strip in ("/dca/1/config", "/dca/9", "/dca/1/grp"):
            with self.subTest(strip=strip), self.assertRaises(KeyError):
                T.set_mute(self.work, strip)
        self.assertEqual(changed_paths(self.base, self.work), [])

    def test_set_mute_toggles_on_flag(self):
        T.set_mute(self.work, 1)
        self.assertEqual(self.work.get("/ch/01/mix").args[0], "OFF")
        self.assertEqual(changed_paths(self.base, self.work), ["/ch/01/mix"])
        # fixture's /mix line is column-padded; a genuine edit-then-revert normalizes
        # that padding, so compare args (semantic state) rather than raw-diff emptiness
        T.set_mute(self.work, 1, False)
        self.assertEqual(self.work.get("/ch/01/mix").args, self.base.get("/ch/01/mix").args)

    def test_set_pan_tokens_and_guards(self):
        T.set_pan(self.work, 1, 0)
        self.assertEqual(self.work.get("/ch/01/mix").args[3], "+0")
        self.assertNotIn("/ch/01/mix", changed_paths(self.base, self.work))
        T.set_pan(self.work, "/main/st", -100)          # balance lives at arg 2
        self.assertEqual(self.work.get("/main/st/mix").args[2], "-100")
        for strip in ("/mtx/01", "/dca/1"):             # no pan on these
            with self.assertRaises(ValueError):
                T.set_pan(self.work, strip, 0)
        with self.assertRaises(ValueError):
            T.set_pan(self.work, 1, 101)


if __name__ == "__main__":
    unittest.main(verbosity=2)
