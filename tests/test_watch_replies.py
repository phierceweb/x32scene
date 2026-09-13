"""watch when a read-back fails: a path whose /node reply never comes is reported as
unanswered rather than dropped, and a reply that is more than one line is never believed."""

import unittest

from tests.test_watch import MIX_DOWN, MIX_OFF, REF_TEXT, ScriptedDesk, run
from tests.test_watch_end import InterruptedDesk
from x32scene.model import Scene
from x32scene.services import watch as W

MIX_START = "/ch/01/mix ON  +6.5 ON +0 OFF   -oo"


class SilentFrom(ScriptedDesk):
    """Loses every /node reply asked for from ``t`` on."""

    def __init__(self, t: float):
        super().__init__()
        self.t = t

    def send(self, addr: str, args=()) -> None:
        if addr == "/node" and self.now >= self.t:
            self.sent.append((self.now, addr, list(args)))
            return
        super().send(addr, args)


class SendFails(ScriptedDesk):
    """The first /node send raises ``error`` after leaving the host, as a Ctrl-C or a
    dropped network can."""

    def __init__(self, error: BaseException):
        super().__init__()
        self.error = error

    def send(self, addr: str, args=()) -> None:
        super().send(addr, args)
        if addr == "/node" and self.error is not None:
            error, self.error = self.error, None
            raise error


class UnansweredTest(unittest.TestCase):
    def test_a_read_back_whose_send_is_interrupted_is_unanswered_not_lost(self):
        for error in (KeyboardInterrupt(), OSError(65, "No route to host")):
            with self.subTest(error=type(error).__name__):
                desk = SendFails(error)
                desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
                ref = Scene.parse(REF_TEXT)
                w = W.Watch(ref, ref)
                with self.assertRaises(type(error)):
                    list(w.run(desk, seconds=5, clock=desk.clock, wall=desk.wall))
                s = w.summary()
                self.assertEqual((s.net, s.unanswered), ([], ["/ch/01/mix"]))

    def test_a_path_that_never_answers_is_reported_not_dropped(self):
        desk = ScriptedDesk(drop=100)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        w, events = run(desk)
        self.assertEqual(events, [])
        s = w.summary()
        self.assertEqual((s.net, s.unanswered), ([], ["/ch/01/mix"]))

    def test_the_end_asks_an_unanswered_path_again_within_its_bound(self):
        desk = ScriptedDesk(drop=100)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        run(desk)
        self.assertEqual([t >= 10.0 for t in desk.queries("ch/01/mix")],
                         [False, False, True, True])
        self.assertLessEqual(desk.now, 10.0 + 2 * 0.5 + 0.01)

    def test_an_answer_at_the_end_logs_the_change_and_clears_it(self):
        desk = ScriptedDesk(drop=2)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        w, events = run(desk)
        self.assertEqual([e.after for e in events], [MIX_OFF])
        s = w.summary()
        self.assertEqual(([c.path for c in s.net], s.unanswered), (["/ch/01/mix"], []))

    def test_a_later_answer_while_watching_clears_it(self):
        desk = ScriptedDesk(drop=2)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        desk.push(5.0, "/ch/01/mix/fader", [0.5], MIX_DOWN)
        w, events = run(desk)
        self.assertEqual([e.after for e in events], [MIX_DOWN])
        self.assertEqual(len(desk.queries("ch/01/mix")), 3)    # nothing left for the end to ask
        self.assertEqual(w.summary().unanswered, [])

    def test_unanswered_paths_are_in_scene_order(self):
        desk = ScriptedDesk(drop=100)
        desk.push(1.0, "/ch/02/mix/fader", [0.5], "/ch/02/mix ON -3.0 ON +0 OFF   -oo")
        desk.push(1.0, "/config/buslink/13-14", [0], "/config/buslink ON ON ON ON ON ON ON OFF")
        w, _ = run(desk)
        self.assertEqual(w.summary().unanswered, ["/config/buslink", "/ch/02/mix"])

    def test_a_path_whose_last_read_back_is_lost_is_not_in_the_net_change(self):
        for script in (((1.0, MIX_DOWN), (5.0, MIX_START)),
                       ((1.0, MIX_DOWN), (2.0, MIX_START), (5.0, MIX_OFF))):
            with self.subTest(script=script):
                desk = SilentFrom(4.0)
                for t, line in script:
                    desk.push(t, "/ch/01/mix/fader", [0.5], line)
                w, events = run(desk)
                self.assertEqual(len(events), len(script) - 1)
                s = w.summary()
                self.assertEqual((s.net, s.transient, s.unanswered), ([], 0, ["/ch/01/mix"]))

    def test_a_flush_cut_short_leaves_its_paths_unanswered(self):
        desk = InterruptedDesk(lambda d: d.now >= 1.0)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        with self.assertRaises(KeyboardInterrupt):
            list(w.run(desk, clock=desk.clock, wall=desk.wall))
        desk.when = lambda d: True
        with self.assertRaises(KeyboardInterrupt):
            list(w.flush(desk, clock=desk.clock, wall=desk.wall))
        self.assertEqual(w.summary().unanswered, ["/ch/01/mix"])


class NotALineTest(unittest.TestCase):
    def test_a_reply_carrying_a_second_line_is_never_believed(self):
        for sep in ("\n", "\r", "\r\n"):
            with self.subTest(sep=sep):
                desk = ScriptedDesk()
                desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF + sep + "/config/routing/IN 1 2 3 4")
                w, events = run(desk)
                self.assertEqual(events, [])
                self.assertEqual(w.end_scene().dump(), REF_TEXT)
                self.assertEqual(len(desk.queries("ch/01/mix")), 4)   # asked again each time
                self.assertEqual(w.summary().unanswered, ["/ch/01/mix"])


if __name__ == "__main__":
    unittest.main()
