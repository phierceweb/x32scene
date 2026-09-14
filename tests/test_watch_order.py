"""watch when /node replies come back out of order: a reply carries no query id, so a late
answer to an older query must never pass for the answer to a newer one."""

import unittest

from tests.test_watch import MIX_DOWN, MIX_OFF, REF_TEXT, ScriptedDesk, run
from x32scene.model import Scene
from x32scene.services import watch as W

MIX_START = "/ch/01/mix ON  +6.5 ON +0 OFF   -oo"
T0 = 1_700_000_000.0


class Delayed(ScriptedDesk):
    """Answers the n-th /node query for /ch/01/mix after ``plan[n]`` seconds, carrying the
    line the desk held when it was asked, or never when that is None."""

    def __init__(self, plan):
        super().__init__()
        self.plan = list(plan)

    def send(self, addr: str, args=()) -> None:
        if addr == "/node" and args == ["ch/01/mix"] and self.plan:
            self.sent.append((self.now, addr, list(args)))
            delay = self.plan.pop(0)
            if delay is not None:
                self.push(self.now + delay, "node", [self.state["/ch/01/mix"] + "\n"])
            return
        super().send(addr, args)


def watched(plan, *script, seconds=6.0):
    desk = Delayed(plan)
    for t, leaf, line in script:
        desk.push(t, leaf, [0], line)
    w, events = run(desk, seconds=seconds)
    s = w.summary()
    return (desk, [(round(e.at - T0, 3), e.before, e.after) for e in events],
            [c.after for c in s.net], s.unanswered)


class StaleReplyTest(unittest.TestCase):
    def test_a_late_answer_to_an_older_query_does_not_settle_a_newer_one(self):
        desk, events, net, unanswered = watched(
            [1.01, 0.002, None], (1.0, "/ch/01/mix/fader", MIX_DOWN), (2.0, "/ch/01/mix/on", MIX_OFF))
        self.assertEqual(desk.state["/ch/01/mix"], MIX_OFF)
        self.assertEqual(events, [(1.0, MIX_START, MIX_DOWN), (2.0, MIX_DOWN, MIX_OFF)])
        self.assertEqual((net, unanswered), ([MIX_OFF], []))

    def test_a_very_late_old_line_is_not_logged_as_a_revert(self):
        desk, events, net, unanswered = watched(
            [2.5, 0.002, 0.002], (1.0, "/ch/01/mix/fader", MIX_DOWN), (2.0, "/ch/01/mix/on", MIX_OFF))
        self.assertEqual(events, [(1.0, MIX_START, MIX_DOWN), (2.0, MIX_DOWN, MIX_OFF)])
        self.assertEqual((net, unanswered), ([MIX_OFF], []))

    def test_a_late_answer_to_a_retried_query_is_waited_out_from_the_retry(self):
        desk, events, net, unanswered = watched(
            [0.6, 2.9, 0.002, 0.002], (1.0, "/ch/01/mix/fader", MIX_DOWN),
            (2.0, "/ch/01/mix/on", MIX_OFF))
        self.assertEqual(events, [(1.0, MIX_START, MIX_DOWN), (2.0, MIX_DOWN, MIX_OFF)])
        self.assertEqual((net, unanswered), ([MIX_OFF], []))

    def test_a_reply_nothing_asked_for_is_not_believed(self):
        desk = Delayed([0.002])
        desk.push(1.0, "/ch/01/mix/fader", [0], MIX_DOWN)
        desk.push(3.0, "node", [MIX_START + "\n"])
        w, events = run(desk, seconds=5.0)
        self.assertEqual([e.after for e in events], [MIX_DOWN])
        self.assertEqual([c.after for c in w.summary().net], [MIX_DOWN])

    def test_an_old_line_still_ambiguous_at_the_end_is_unanswered_not_net(self):
        desk, events, net, unanswered = watched(
            [1.01, 0.002, None], (1.0, "/ch/01/mix/fader", MIX_DOWN), (2.0, "/ch/01/mix/on", MIX_OFF),
            seconds=2.5)
        self.assertEqual(events, [(1.0, MIX_START, MIX_DOWN)])
        self.assertEqual((net, unanswered), ([], ["/ch/01/mix"]))

    def test_a_change_while_a_slow_reply_is_out_is_asked_once_that_reply_is_in(self):
        desk = Delayed([0.3, 0.3])
        waits = []
        recv = desk.recv
        desk.recv = lambda timeout: waits.append(timeout) or recv(timeout)
        desk.push(1.0, "/ch/01/mix/fader", [0], MIX_DOWN)
        desk.push(1.2, "/ch/01/mix/on", [0], MIX_OFF)
        desk.push(1.36, "/-stat/selidx", [4])      # wakes the loop while the reply is out
        w, events = run(desk, seconds=3.0)
        self.assertEqual([(round(e.at - T0, 3), e.after) for e in events],
                         [(1.0, MIX_DOWN), (1.2, MIX_OFF)])
        self.assertEqual([round(t, 2) for t in desk.queries("ch/01/mix")], [1.15, 1.45])
        self.assertLess(len(waits), 40)

    def test_a_slow_reply_after_its_retry_settled_is_not_logged_as_a_revert(self):
        # the retry is sent with the slow query's count: the change it sees pushes a moment later
        desk = Delayed([None, None] + [0.002] * 20)
        for t, addr, line in ((1.0, "/ch/01/mix/fader", MIX_DOWN),
                              (1.651, "/ch/01/mix/on", MIX_OFF)):
            desk.push(t, addr, [0], line)
        desk.push(1.652, "node", [MIX_OFF + "\n"])     # the retry's reply
        desk.push(1.75, "node", [MIX_DOWN + "\n"])     # the first query's, late
        w, events = run(desk, seconds=8.0)
        self.assertEqual([e.after for e in events], [MIX_OFF])
        self.assertEqual([c.after for c in w.summary().net], [MIX_OFF])

    def test_a_late_duplicate_of_a_settled_reply_does_not_become_the_end_state(self):
        desk = Delayed([None] * 3 + [0.002] * 20)
        desk.push(1.0, "/ch/01/mix/fader", [0], MIX_DOWN)
        desk.push(1.5, "/ch/01/mix/on", [0], MIX_OFF)
        for t, line in ((1.152, MIX_DOWN), (2.152, MIX_OFF), (2.162, MIX_DOWN), (2.17, MIX_OFF)):
            desk.push(t, "node", [line + "\n"])
        w, events = run(desk, seconds=8.0)
        self.assertNotIn((MIX_OFF, MIX_DOWN), [(e.before, e.after) for e in events])
        self.assertEqual([c.after for c in w.summary().net], [MIX_OFF])

    def test_one_slow_reply_during_a_fader_ride_holds_the_channel_for_one_window_only(self):
        desk = Delayed([0.6] + [0.002] * 200)
        for i in range(41):      # a push every 0.2 s from 1.0 to 9.0
            desk.push(1.0 + 0.2 * i, "/ch/01/mix/fader", [0],
                      f"/ch/01/mix ON {-10.0 - i * 0.5:.1f} ON +0 OFF   -oo")
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        reported = [desk.now for _ in w.run(desk, seconds=12.0, clock=desk.clock,
                                            wall=desk.wall)]
        self.assertLess(reported[0], 1.65 + W.LATE * 0.5 + 0.1)
        self.assertGreaterEqual(sum(t < 9.0 for t in reported), 10)
        self.assertEqual([c.after for c in w.summary().net], [desk.state["/ch/01/mix"]])

    def test_a_change_is_dated_from_the_first_push_its_read_back_covered(self):
        both = "/ch/01/mix OFF -10.0 ON +0 OFF   -oo"
        for plan, script, dates in (
                ([0.9, 2.8] + [0.002] * 10,        # a retry covers the 1.6 push
                 ((1.0, MIX_DOWN), (1.6, MIX_OFF), (3.0, both)), [1.0, 3.0]),
                ([0.6] + [0.002] * 10,             # an ambiguous reply is held, then re-asked
                 ((1.0, MIX_DOWN), (1.6, MIX_OFF)), [1.0])):
            with self.subTest(plan=plan[:2]):
                desk = Delayed(plan)
                for t, line in script:
                    desk.push(t, "/ch/01/mix/fader", [0], line)
                w, events = run(desk, seconds=8.0)
                self.assertEqual([round(e.at - T0, 3) for e in events], dates)
                self.assertEqual(events[-1].after, script[-1][1])

    def test_replies_in_order_are_read_at_once(self):
        desk, events, _, _ = watched(
            [0.002, 0.002], (1.0, "/ch/01/mix/fader", MIX_DOWN), (2.0, "/ch/01/mix/on", MIX_OFF))
        self.assertEqual([round(t, 2) for t in desk.queries("ch/01/mix")], [1.15, 2.15])
        self.assertEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main()
