"""`load`: a scene or snippet onto the running desk, written and read back until it holds."""
import socket
import unittest

from tests.load_desk import BASE, GAIN_UP, MIX_DOWN, Desk, edited
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.load import load_scene


class LoadServiceTest(unittest.TestCase):
    def load(self, desk: Desk, text: str, **kw):
        kw.setdefault("sleep", lambda s: None)
        return load_scene(Scene.parse(text), "127.0.0.1", port=desk.port, timeout=0.2, **kw)

    def test_writes_only_the_lines_the_desk_does_not_hold(self):
        with Desk() as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP))
        self.assertEqual(r.passes, [["/ch/01/mix/01", "/headamp/000"]])
        self.assertEqual((r.ok, r.stuck, r.unanswered, r.written), (True, [], [], 2))
        self.assertEqual(desk.writes, [MIX_DOWN, GAIN_UP])   # no header, nothing unchanged
        self.assertEqual(desk.lines["/ch/01/mix/01"], MIX_DOWN)

    def test_a_desk_already_holding_the_file_gets_no_write(self):
        with Desk() as desk:
            r = self.load(desk, BASE)
        self.assertEqual((r.passes, r.ok, desk.writes), ([], True, []))

    def test_padding_is_the_desks_own_and_not_a_difference(self):
        with Desk() as desk:
            r = self.load(desk, edited(ch_01_mix_02="/ch/01/mix/02 ON -3.0"))
        self.assertEqual((r.passes, desk.writes), ([], []))

    def test_a_write_the_desk_drops_is_written_again_next_pass(self):
        with Desk(drop_writes=["/ch/01/mix/01"]) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP))
        self.assertEqual(r.passes, [["/ch/01/mix/01", "/headamp/000"], ["/ch/01/mix/01"]])
        self.assertTrue(r.ok)
        self.assertEqual(desk.lines["/ch/01/mix/01"], MIX_DOWN)

    def test_a_value_the_desk_snaps_is_reported_after_the_last_pass(self):
        want = "/ch/01/eq/1 PEQ 200.0 +0.00 2.0"
        held = "/ch/01/eq/1 PEQ 202.3 +0.00 2.0"
        with Desk(snap={"/ch/01/eq/1": held}) as desk:
            r = self.load(desk, edited(ch_01_eq_1=want, headamp_000=GAIN_UP), passes=2)
        self.assertEqual(r.passes, [["/ch/01/eq/1", "/headamp/000"], ["/ch/01/eq/1"]])
        self.assertFalse(r.ok)
        self.assertEqual([(c.path, c.before, c.after) for c in r.stuck],
                         [("/ch/01/eq/1", want, held)])
        self.assertEqual(r.unanswered, [])

    def test_a_path_the_desk_never_answers_is_written_once_and_named_unverified(self):
        ghost = '/ch/33/config "Ghost" 1 YE 33'
        with Desk(drop_writes=["/ch/01/mix/01"], lacks=["/ch/33/config"]) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, extra=ghost))
        self.assertEqual(r.passes, [["/ch/01/mix/01", "/ch/33/config"], ["/ch/01/mix/01"]])
        self.assertEqual((r.ok, r.stuck, r.unanswered), (False, [], ["/ch/33/config"]))
        self.assertEqual(desk.writes, [MIX_DOWN, ghost, MIX_DOWN])

    def test_a_path_silent_at_the_start_that_answers_once_written_is_verified(self):
        # a lost /node reply on the first read must not leave the line unwritten
        with Desk(edited(extra="/ch/01/mix/fader   -6.0"), mute_first_read=["/ch/01/mix/fader"]) as desk:
            r = self.load(desk, edited(extra="/ch/01/mix/fader -20.0"))
        self.assertEqual(r.passes, [["/ch/01/mix/fader"]])
        self.assertEqual((r.ok, r.unanswered), (True, []))
        self.assertEqual(desk.lines["/ch/01/mix/fader"], "/ch/01/mix/fader -20.0")

    def test_each_pass_writes_slower_than_the_last(self):
        naps = []
        with Desk(drop_writes=["/ch/01/mix/01"]) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP),
                          sleep=naps.append)
        self.assertEqual([len(p) for p in r.passes], [2, 1])
        gap1, _, _, gap2 = naps[:4]      # write, write, read-back settle, write
        self.assertEqual(gap2, 2 * gap1)

    def test_a_reply_lost_on_the_read_back_is_asked_again_next_pass(self):
        # two lost replies: the read-back asks twice per pass, so the path carries over
        with Desk(mute_after_write=2) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN))
        self.assertEqual(r.passes, [["/ch/01/mix/01"], ["/ch/01/mix/01"]])
        self.assertEqual((r.ok, r.unanswered), (True, []))

    def test_a_path_never_read_back_is_unanswered_not_stuck_and_not_ok(self):
        with Desk(mute_after_write=99) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN), passes=2)
        self.assertEqual(r.passes, [["/ch/01/mix/01"], ["/ch/01/mix/01"]])
        self.assertEqual((r.ok, r.stuck, r.unanswered), (False, [], ["/ch/01/mix/01"]))

    def test_an_fx_type_line_settles_before_its_parameters_follow(self):
        naps = []
        text = edited(fx_1="/fx/1 PLAT MIX13 MIX13", fx_1_par="/fx/1/par 0.1 0.2 0.3 0.4")
        with Desk() as desk:
            r = self.load(desk, text, sleep=naps.append)
        self.assertEqual(r.passes, [["/fx/1", "/fx/1/par"]])
        self.assertEqual(desk.writes[0].split()[0], "/fx/1")
        self.assertGreaterEqual(naps[0], 0.5)       # after the type line
        self.assertLess(naps[1], 0.5)               # after the par line

    def test_a_link_line_settles_before_the_strips_follow(self):
        naps = []
        link = "/config/chlink ON OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF"
        text = BASE.replace("/ch/01/config", link + "\n/ch/01/config", 1)
        with Desk(edited(extra=link.replace("ON", "OFF", 1), ch_01_mix_01=MIX_DOWN)) as desk:
            r = self.load(desk, text, sleep=naps.append)
        self.assertEqual(r.passes, [["/config/chlink", "/ch/01/mix/01"]])
        self.assertGreaterEqual(naps[0], 0.5)       # after the link line
        self.assertLess(naps[1], 0.5)               # after the strip's line

    def test_a_snippet_loads_its_split_lines(self):
        snip = ('#4.0# "SNIP" 6910 -1 50397183 0 1\n'
                "/ch/01/mix/fader -20.0\n/ch/01/mix/pan +0\n")
        with Desk(edited(extra="/ch/01/mix/fader   -6.0", extra2="/ch/01/mix/pan +0")) as desk:
            r = self.load(desk, snip)
        self.assertEqual(r.passes, [["/ch/01/mix/fader"]])
        self.assertEqual(desk.lines["/ch/01/mix/fader"], "/ch/01/mix/fader -20.0")

    def test_a_desk_that_never_answers_raises(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
            silent.bind(("127.0.0.1", 0))
            with self.assertRaises(O.OscError):
                load_scene(Scene.parse(BASE), "127.0.0.1", port=silent.getsockname()[1],
                           timeout=0.1, sleep=lambda s: None)


if __name__ == "__main__":
    unittest.main()
