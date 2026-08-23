"""Preset extract/apply tests: scope filtering, head-amp remap, round-trip safety."""

import os
import unittest

from x32scene import Scene
from x32scene.services.diff import diff
from x32scene.services.presets import apply_preset, extract_preset, header_sections
from x32scene.services.routing import channel_headamp_index
from x32scene.services.scopes import scope_of

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


class ScopeTest(unittest.TestCase):
    def test_scope_classification(self):
        self.assertEqual(scope_of("/config"), "scribble")
        self.assertEqual(scope_of("/eq/1"), "eq")
        self.assertEqual(scope_of("/mix/03"), "sends")
        self.assertEqual(scope_of("/mix/fader"), "mainfader")
        self.assertEqual(scope_of("/headamp/000"), "ha")
        self.assertEqual(scope_of("/dyn"), "comp")
        self.assertIsNone(scope_of("/grp"))

    def test_insert_and_automix_are_classified(self):
        # both are real channel-block lines; unclassified means silently dropped
        self.assertEqual(scope_of("/insert"), "insert")
        self.assertEqual(scope_of("/automix"), "automix")

    def test_full_extract_covers_every_channel_line_except_grp(self):
        sc = Scene.load(EXAMPLE)
        chn = extract_preset(sc, 1)
        emitted = {ln.split(" ", 1)[0] for ln in chn.splitlines() if ln}
        present = {ln.path[len("/ch/01"):] for ln in sc.lines
                   if ln.path.startswith("/ch/01/")}
        missing = present - emitted - {"/grp"}
        self.assertEqual(missing, set(), f"scopes drop channel lines: {missing}")


class PresetTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_headamp_index_resolution(self):
        self.assertEqual(channel_headamp_index(self.sc, 1), 0)    # Kick -> local 1
        self.assertEqual(channel_headamp_index(self.sc, 17), 32)  # Bass DI -> AES50-A 1
        self.assertIsNone(channel_headamp_index(self.sc, 31))     # DAW L <- card: no HA

    def test_extract_includes_only_selected_scopes(self):
        chn = extract_preset(self.sc, 1, scopes=["eq"])
        lines = [ln for ln in chn.splitlines() if ln]
        self.assertTrue(all(ln.startswith("/eq") for ln in lines), lines)

    def test_extract_ha_uses_real_source_index(self):
        chn = extract_preset(self.sc, 17, scopes=["ha"])  # Bass DI -> headamp 032
        self.assertIn("/headamp/032", chn)

    def test_roundtrip_extract_then_apply_is_identity(self):
        # extract everything from ch20, apply onto a fresh copy's ch20 -> no change
        chn = extract_preset(self.sc, 20)
        dst = Scene.load(EXAMPLE)
        n = apply_preset(dst, 20, chn)
        self.assertEqual(n, 0)
        self.assertEqual(diff(self.sc, dst), [])

    def test_apply_eq_only_touches_eq_lines(self):
        chn = extract_preset(self.sc, 1)            # full Kick preset
        dst = Scene.load(EXAMPLE)
        apply_preset(dst, 20, chn, scopes=["eq"])   # onto Gtr 1, EQ only
        changed = {c.path for c in diff(self.sc, dst)}
        self.assertTrue(changed, "expected EQ changes")
        self.assertTrue(all(p.startswith("/ch/20/eq") for p in changed), changed)

    def test_apply_remaps_headamp_to_target(self):
        # Kick preset (HA at idx 000) applied to ch20 (AES50-A 4 -> idx 35) hits /headamp/035
        chn = extract_preset(self.sc, 1, scopes=["ha"])
        dst = Scene.load(EXAMPLE)
        apply_preset(dst, 20, chn, scopes=["ha"])
        changed = {c.path for c in diff(self.sc, dst)}
        self.assertIn("/headamp/035", changed)
        self.assertNotIn("/headamp/000", changed)

    def test_apply_scribble_preserves_target_source_slot(self):
        # /config's last arg is the input source slot — a name/color preset must not
        # repatch the target channel to the source channel's mic line
        chn = extract_preset(self.sc, 1, scopes=["scribble"])
        dst = Scene.load(EXAMPLE)
        slot_before = dst.get("/ch/20/config").args[-1]
        apply_preset(dst, 20, chn, scopes=["scribble"])
        cfg = dst.get("/ch/20/config").args
        self.assertEqual(cfg[0], '"Kick"')
        self.assertEqual(cfg[-1], slot_before)

    def test_apply_rejects_malformed_preset_line(self):
        # apply_preset assigns args directly, bypassing set_arg — it must validate
        # tokens itself or a hand-edited .chn corrupts the line structure
        dst = Scene.load(EXAMPLE)
        with self.assertRaises(ValueError):
            apply_preset(dst, 20, '/config "Vox 1 1 5\n', ["scribble"])
        self.assertEqual(diff(self.sc, dst), [])

    def test_apply_rejects_config_field_count_mismatch(self):
        dst = Scene.load(EXAMPLE)
        with self.assertRaises(ValueError):
            apply_preset(dst, 20, '/config "Vox" 7\n', ["scribble"])
        self.assertEqual(diff(self.sc, dst), [])

    def test_applied_scene_still_roundtrips(self):
        chn = extract_preset(self.sc, 1)
        dst = Scene.load(EXAMPLE)
        apply_preset(dst, 20, chn)
        self.assertEqual(Scene.parse(dst.dump()).dump(), dst.dump())


if __name__ == "__main__":
    unittest.main(verbosity=2)


class HeaderTest(unittest.TestCase):
    """The optional .chn header: `#4.0# <pos> "<name>" <type> %<16 flags> 1`. Bits 8-13
    (right to left) say which sections are present, bits 0-5 which are ON — inferred from
    a zeroed reset preset and the protocol document, so writing one is opt-in."""

    ALL = ["preamp", "config", "locut", "gate", "eq", "dyn"]

    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_extract_with_header_writes_the_published_shape(self):
        first = extract_preset(self.sc, 1, header=True).splitlines()[0]
        self.assertRegex(first, r'^#4\.0# 1 "Kick" 0 %[01]{16} 1 *$')
        first = extract_preset(self.sc, 1, header="My Kick").splitlines()[0]
        self.assertIn('"My Kick"', first)

    def test_header_flags_name_the_sections_present(self):
        chn = extract_preset(self.sc, 1, scopes=["eq", "gate"], header=True)
        self.assertEqual(header_sections(chn)["present"], ["gate", "eq"])
        self.assertEqual(header_sections(extract_preset(self.sc, 1, header=True))["present"],
                         self.ALL)

    def test_header_active_bits_follow_the_lines(self):
        info = header_sections(extract_preset(self.sc, 1, header=True))
        for section, path, idx in (("gate", "/ch/01/gate", 0), ("eq", "/ch/01/eq", 0),
                                   ("dyn", "/ch/01/dyn", 0), ("locut", "/ch/01/preamp", 2)):
            with self.subTest(section=section):
                self.assertEqual(section in info["active"],
                                 self.sc.get(path).args[idx] == "ON")
        self.assertEqual("preamp" in info["active"],
                         self.sc.get("/headamp/000").args[1] == "ON")

    def test_header_reader_returns_none_for_a_headerless_preset(self):
        self.assertIsNone(header_sections(extract_preset(self.sc, 1)))

    def test_zeroed_reset_header_reads_all_present_none_active(self):
        info = header_sections('#2.1# 71 "Zeroed" 0 %0011111100000000 1\n/preamp +0.0 OFF OFF 24 20\n')
        self.assertEqual((info["present"], info["active"]), (self.ALL, []))

    def test_apply_ignores_the_header(self):
        chn = extract_preset(self.sc, 20, header=True)
        dst = Scene.load(EXAMPLE)
        self.assertEqual(apply_preset(dst, 20, chn), 0)

    def test_header_roundtrips_through_the_parser(self):
        chn = extract_preset(self.sc, 1, header=True)
        self.assertEqual(Scene.parse(chn).dump(), chn)

    def test_cli_header_flag(self):
        import tempfile
        from x32scene.cli import main
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "kick.chn")
            self.assertEqual(main(["extract-preset", EXAMPLE, "1", "-o", out, "--header"]), 0)
            with open(out, encoding="utf-8") as fh:
                self.assertTrue(fh.readline().startswith('#4.0# 1 "Kick" 0 %'))


if __name__ == "__main__":
    unittest.main()
