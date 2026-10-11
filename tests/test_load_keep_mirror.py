"""`load --keep`: the lines taken in with a kept one because the desk copies a write onto
them, as `/config/linkcfg` gates it, and a linked channel's head amp; a preference change
refused around them."""
import unittest

from tests.load_desk import Desk, edited
from tests.test_load_keep import BASE, without
from x32scene.services import load as L
from x32scene.model import Scene
from x32scene.services.load import load_scene
from x32scene.services.load_keep import Keep

CH_1_2 = "/config/chlink ON" + " OFF" * 15
HEADS = edited(BASE, config_chlink=CH_1_2, ch_02_config='/ch/02/config "Snare" 1 YE 2',
               config_routing_IN="/config/routing/IN AN1-8 AN9-16 AN17-24 AN25-32 AUX1-4",
               headamp_000="/headamp/000 +20.0 OFF", headamp_001="/headamp/001 +20.0 OFF",
               headamp_002="/headamp/002 +20.0 OFF",
               config_userrout_in="/config/userrout/in" + " 0" * 32,
               **{f"ch_{c:02d}_config": f'/ch/{c:02d}/config "" 1 OFF {c}' for c in range(3, 33)})


class KeepMirrorTest(unittest.TestCase):
    def load(self, desk: Desk, text: str, **kw):
        return load_scene(Scene.parse(text), "127.0.0.1", port=desk.port, timeout=0.2,
                          sleep=lambda s: None, **kw)

    def test_a_kept_head_amp_takes_in_the_one_its_linked_partner_reads(self):
        text = edited(HEADS, headamp_000="/headamp/000 +30.0 OFF",
                      headamp_001="/headamp/001 +30.0 OFF")
        for name, file in (("scene", text), ("no routing", without(text, "/config/routing/IN"))):
            with self.subTest(name), Desk(HEADS) as desk:
                r = self.load(desk, file, keep=Keep(globs=["/headamp/000"]))
            self.assertEqual(r.kept, [("/headamp/000 and its linked sides",
                                       ["/headamp/000", "/headamp/001"])])
            self.assertEqual((r.passes, desk.writes, r.ok), ([], [], True))

    def test_a_kept_head_amp_takes_in_its_partner_under_the_desks_routing_and_the_files(self):
        text = edited(HEADS, ch_02_config='/ch/02/config "Snare" 1 YE 3',
                      headamp_001="/headamp/001 +30.0 OFF", headamp_002="/headamp/002 +30.0 OFF")
        with Desk(HEADS) as desk:
            r = self.load(desk, text, keep=Keep(globs=["/headamp/000"]))
        self.assertEqual(r.kept, [("/headamp/000 and its linked sides",
                                   ["/headamp/000", "/headamp/001", "/headamp/002"])])
        self.assertEqual(r.passes, [["/ch/02/config"]])

    def test_a_head_amp_the_link_preferences_leave_unshared_is_kept_alone(self):
        base = edited(HEADS, config_linkcfg="/config/linkcfg OFF ON ON ON")
        with Desk(base) as desk:
            r = self.load(desk, edited(base, headamp_001="/headamp/001 +30.0 OFF"),
                          keep=Keep(globs=["/headamp/000"]))
        self.assertEqual(r.kept, [("/headamp/000", ["/headamp/000"])])
        self.assertEqual(r.passes, [["/headamp/001"]])

    def test_a_file_unlinking_the_channels_a_kept_head_amp_feeds_is_refused(self):
        text = edited(HEADS, config_chlink="/config/chlink" + " OFF" * 16)
        with Desk(HEADS) as desk, self.assertRaises(L.Unloadable) as cm:
            self.load(desk, text, keep=Keep(globs=["/headamp/000"]))
        self.assertIn("changes the ch 1/2 link", str(cm.exception))
        self.assertEqual(desk.writes, [])

    def test_a_strip_line_the_link_preferences_leave_unshared_is_not_taken_in(self):
        base = edited(BASE, config_chlink=CH_1_2, config_linkcfg="/config/linkcfg ON OFF ON ON",
                      ch_02_eq_1="/ch/02/eq/1 PEQ 100.0 +0.00 2.0",
                      ch_02_config='/ch/02/config "Snare" 1 YE 2')
        text = edited(base, ch_02_eq_1="/ch/02/eq/1 PEQ 300.0 +6.00 2.0")
        with Desk(base) as desk:
            r = self.load(desk, text, keep=Keep(globs=["/ch/01/eq/*", "/ch/01/config"]))
        self.assertEqual(r.kept, [("/ch/01/eq/*", ["/ch/01/eq/1"]),
                                  ("/ch/01/config and its linked sides",
                                   ["/ch/01/config", "/ch/02/config"])])
        self.assertEqual(r.passes, [["/ch/02/eq/1"]])

    def test_a_preference_change_that_gates_a_kept_linked_line_is_refused_unless_kept(self):
        text = edited(BASE, config_linkcfg="/config/linkcfg ON ON ON OFF")
        with Desk(BASE) as desk, self.assertRaises(L.Unloadable) as cm:
            self.load(desk, text, keep=Keep(buses=[13]))
        self.assertIn("the file changes the fdrmute preference in /config/linkcfg, which decides "
                      "what the desk copies across linked bus 13/14, the pair kept /bus/13/mix "
                      "belongs to; keep /config/linkcfg too", str(cm.exception))
        self.assertEqual(desk.writes, [])
        with Desk(BASE) as desk:
            r = self.load(desk, text, keep=Keep(buses=[13], globs=["/config/linkcfg"]))
        self.assertEqual((r.passes, r.ok, desk.writes), ([], True, []))

    def test_a_preference_change_that_gates_no_kept_linked_line_is_written(self):
        text = edited(BASE, config_linkcfg="/config/linkcfg ON OFF ON ON")
        for keep in (Keep(buses=[13]), Keep(globs=["/ch/01/eq/*"])):
            with self.subTest(keep=keep), Desk(BASE) as desk:
                r = self.load(desk, text, keep=keep)
            self.assertEqual((r.passes, r.ok), ([["/config/linkcfg"]], True))


if __name__ == "__main__":
    unittest.main()
