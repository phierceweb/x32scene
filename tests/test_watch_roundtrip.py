"""watch's read-back timer: RFC 6298 over /node round trips, between --timeout and CAP
--timeouts, backed off by a timeout and never sampled from a retried read-back."""

import unittest

from tests.test_watch import REF_TEXT, ScriptedDesk
from x32scene.model import Scene
from x32scene.services import watch as W
from x32scene.services.watch_readback import CAP, LATE, MARGIN, RoundTrip


class TimerTest(unittest.TestCase):
    def test_it_starts_at_the_floor_and_a_fast_link_keeps_it_there(self):
        t = RoundTrip(0.5)
        self.assertEqual((t.rto, t.estimate), (0.5, 0.5))
        for _ in range(5):
            t.sample(0.002)
        self.assertEqual((t.rto, t.estimate), (0.5, 0.5))

    def test_the_first_sample_sets_srtt_and_half_of_it_as_rttvar(self):
        t = RoundTrip(0.5)
        t.sample(0.55)
        self.assertAlmostEqual(t.rto, 0.55 + 4 * 0.275)

    def test_a_steady_round_trip_keeps_a_margin_above_it(self):
        t = RoundTrip(0.5)
        for _ in range(200):
            t.sample(0.55)
        self.assertAlmostEqual(t.rto, 0.675, places=6)
        self.assertEqual(MARGIN * 0.5, 0.125)

    def test_a_timeout_doubles_it_once_however_many_queries_it_cost(self):
        t = RoundTrip(0.5)
        for _ in range(3):
            t.timed_out(0.5)
        self.assertEqual(t.rto, 1.0)
        t.timed_out(1.0)
        self.assertEqual(t.rto, 2.0)
        self.assertEqual(t.estimate, 0.5)

    def test_it_never_passes_the_cap(self):
        t = RoundTrip(0.5)
        for rto in (0.5, 1.0, 2.0, 4.0):
            t.timed_out(rto)
        self.assertEqual(t.rto, CAP * 0.5)
        t.sample(30.0)
        self.assertEqual((t.rto, t.estimate), (CAP * 0.5, CAP * 0.5))

    def test_a_clean_sample_ends_the_back_off(self):
        t = RoundTrip(0.5)
        t.timed_out(0.5)
        t.sample(0.002)
        self.assertEqual(t.rto, 0.5)

    def test_a_start_pull_seeds_it_in_reply_order(self):
        for replies, rto in (([None] * 20, 1.0), ([None, 0.002], 0.5), ([0.002, None], 1.0),
                             ([0.55], 0.55 + 4 * 0.275), ([], 0.5)):
            with self.subTest(replies=replies):
                t = RoundTrip(0.5)
                t.seed(replies)
                self.assertAlmostEqual(t.rto, rto)


class Planned(ScriptedDesk):
    """Answers a path's n-th /node query ``plans[path][n]`` seconds later, or never for None;
    at once past the end of its plan."""

    def __init__(self, plans):
        super().__init__()
        self.plans = {p: list(v) for p, v in plans.items()}

    def send(self, addr: str, args=()) -> None:
        self.sent.append((self.now, addr, list(args)))
        if addr == "/node":
            plan = self.plans.get(args[0], [])
            delay = plan.pop(0) if plan else 0.002
            if delay is not None:
                self.push(self.now + delay, "node", [self.state["/" + args[0]] + "\n"])


CH2_DOWN = "/ch/02/mix ON -20.0 ON +0 OFF   -oo"
CH2_UP = "/ch/02/mix ON -10.0 ON +0 OFF   -oo"


class KarnTest(unittest.TestCase):
    def watch(self, desk):
        ref = Scene.parse(REF_TEXT)
        return list(W.Watch(ref, ref).run(desk, seconds=8.0, clock=desk.clock, wall=desk.wall))

    def test_a_reply_to_a_retried_read_back_leaves_the_timer_backed_off(self):
        desk = Planned({"ch/01/mix": [None, 0.002], "ch/02/mix": [None, 0.002]})
        desk.push(1.0, "/ch/01/mix/fader", [0.2], "/ch/01/mix ON -30.0 ON +0 OFF   -oo")
        desk.push(3.0, "/ch/02/mix/fader", [0.2], CH2_DOWN)
        self.assertEqual(len(self.watch(desk)), 2)
        self.assertEqual([round(t, 2) for t in desk.queries("ch/02/mix")], [3.15, 4.15])

    def test_a_clean_read_back_brings_the_timer_back_for_every_path(self):
        desk = Planned({"ch/01/mix": [None, 0.002], "ch/02/mix": [0.002, None, 0.002]})
        desk.push(1.0, "/ch/01/mix/fader", [0.2], "/ch/01/mix ON -30.0 ON +0 OFF   -oo")
        desk.push(3.0, "/ch/02/mix/fader", [0.2], CH2_DOWN)
        desk.push(5.0, "/ch/02/mix/fader", [0.3], CH2_UP)
        self.assertEqual([e.after for e in self.watch(desk)][1:], [CH2_DOWN, CH2_UP])
        self.assertEqual([round(t, 2) for t in desk.queries("ch/02/mix")], [3.15, 5.15, 5.65])


V1, V2, V3 = (f"/ch/01/mix ON {v} ON +0 OFF   -oo" for v in ("-30.0", "-20.0", "-10.0"))


class AllAnsweredTest(unittest.TestCase):
    """Replies held as ambiguous: once each query out has had one, the path is asked again at
    once rather than when the last of them lapses."""

    def watch(self, plan, *leaves, seconds=8.0):
        desk = Planned({"ch/01/mix": plan})
        for t, line in leaves:
            desk.push(t, "/ch/01/mix/fader", [0.2], line)
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        events = list(w.run(desk, seconds=seconds, clock=desk.clock, wall=desk.wall))
        return desk, w, events

    def test_a_pair_whose_replies_are_both_in_is_asked_again_at_once(self):
        desk, _, events = self.watch([0.6, 0.002], (1.0, V1), (1.3, V2))
        self.assertEqual([round(t, 2) for t in desk.queries("ch/01/mix")], [1.15, 1.65, 1.75])
        self.assertEqual([e.after for e in events], [V2])

    def test_a_pair_missing_a_reply_waits_for_the_last_to_lapse(self):
        desk, _, events = self.watch([None, 0.002], (1.0, V1), (1.3, V2))
        self.assertEqual([round(t, 2) for t in desk.queries("ch/01/mix")],
                         [1.15, 1.65, round(1.65 + LATE * 0.5, 2)])
        self.assertEqual([e.after for e in events], [V2])

    def test_a_held_reply_whose_query_lapses_no_longer_counts(self):
        # the reply held at 3.0 answered the query that lapses at 4.15; the retry sent at
        # 2.65 is still out when the change at 4.3 is asked about, so its old line is not taken
        desk, w, events = self.watch([1.85, 2.55, 1.81, 0.02], (1.0, V1), (1.4, V2), (4.3, V3))
        self.assertEqual([e.after for e in events], [V2, V3])
        self.assertEqual(w.end_scene().get("/ch/01/mix").raw, V3)


class LapseTest(unittest.TestCase):
    def test_a_longer_round_trip_learned_since_a_read_back_was_sent_extends_its_lapse(self):
        # /ch/02/mix's 0.45 s reply lifts the estimate after the 3.4 s read-back left at the
        # floor; that reply then arrives past six --timeouts and must not settle the newer one
        desk = Planned({"ch/01/mix": [3.4, 0.002], "ch/02/mix": [0.45]})
        for t, leaf, line in ((0.85, "/ch/01/mix/fader", V1), (0.85, "/ch/02/mix/fader", CH2_DOWN),
                              (1.2, "/ch/01/mix/fader", V2)):
            desk.push(t, leaf, [0.2], line)
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        events = list(w.run(desk, seconds=8.0, clock=desk.clock, wall=desk.wall))
        self.assertEqual([e.after for e in events if e.path == "/ch/01/mix"], [V2])
        self.assertEqual(w.end_scene().get("/ch/01/mix").raw, V2)


class EndPaceTest(unittest.TestCase):
    def test_a_backed_off_read_back_out_at_the_end_is_asked_again_within_one_round_trip(self):
        # two lost replies back the timer off to 2 s; the end does not wait that out
        desk = Planned({"ch/01/mix": [None, None, None]})
        desk.push(1.0, "/ch/01/mix/fader", [0.2], V1)
        desk.push(5.0, "/ch/01/mix/fader", [0.3], V2)
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        events = list(w.run(desk, seconds=5.5, clock=desk.clock, wall=desk.wall))
        self.assertEqual([round(t, 2) for t in desk.queries("ch/01/mix")], [1.15, 1.65, 5.15, 6.0])
        self.assertEqual(([e.after for e in events], w.summary().unanswered), ([V2], []))
        self.assertLessEqual(desk.now, 5.5 + 2 * 0.5 + 0.01)


if __name__ == "__main__":
    unittest.main()
