"""watch at its end: a change still inside its debounce window is read back before the
watch returns, whether --seconds ran out or Ctrl-C stopped it, and the read-back is bounded."""

import unittest

from tests.test_watch import MIX_OFF, REF_TEXT, ScriptedDesk, run
from x32scene.model import Scene
from x32scene.services import watch as W


class InterruptedDesk(ScriptedDesk):
    """Presses Ctrl-C once, inside the first recv for which ``when(desk)`` holds."""

    def __init__(self, when, **kw):
        super().__init__(**kw)
        self.when = when

    def recv(self, timeout: float):
        if self.when is not None and self.when(self):
            self.when = None
            raise KeyboardInterrupt
        return super().recv(timeout)


class SecondsEndTest(unittest.TestCase):
    def test_a_change_in_the_last_debounce_window_still_lands(self):
        desk = ScriptedDesk()
        desk.push(9.95, "/ch/01/mix/on", [0], MIX_OFF)
        w, events = run(desk, seconds=10.0)
        self.assertEqual([e.after for e in events], [MIX_OFF])
        self.assertEqual([c.path for c in w.summary().net], ["/ch/01/mix"])

    def test_the_read_back_is_bounded_when_the_desk_does_not_answer(self):
        desk = ScriptedDesk(drop=5)
        desk.push(9.95, "/ch/01/mix/on", [0], MIX_OFF)
        _, events = run(desk, seconds=10.0)
        self.assertEqual(events, [])
        self.assertEqual(len(desk.queries("ch/01/mix")), 2)
        self.assertLessEqual(desk.now, 10.0 + 2 * 0.5 + 0.01)

    def test_nothing_waiting_ends_without_a_query(self):
        desk = ScriptedDesk()
        run(desk, seconds=2.0)
        self.assertEqual({a for _, a, _ in desk.sent}, {"/xremote"})


class EndRetryTest(unittest.TestCase):
    """The end-of-watch retry docs/cli.md states for `watch`."""

    def test_a_path_already_unanswered_is_asked_twice_more(self):
        desk = ScriptedDesk(drop=10)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        w, _ = run(desk, seconds=3.0)
        self.assertEqual([t < 3.0 for t in desk.queries("ch/01/mix")], [True, True, False, False])
        self.assertEqual(w.summary().unanswered, ["/ch/01/mix"])

    def test_a_read_back_out_at_the_end_keeps_its_own_schedule(self):
        desk = ScriptedDesk(drop=10)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        w, _ = run(desk, seconds=1.9)
        self.assertEqual(len(desk.queries("ch/01/mix")), 2)
        self.assertLess(max(desk.queries("ch/01/mix")), 1.9)
        self.assertEqual(w.summary().unanswered, ["/ch/01/mix"])


class InterruptTest(unittest.TestCase):
    def test_flush_reads_back_what_an_interrupted_watch_left_waiting(self):
        desk = InterruptedDesk(lambda d: d.now >= 1.0)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        with self.assertRaises(KeyboardInterrupt):
            list(w.run(desk, clock=desk.clock, wall=desk.wall))
        self.assertEqual(desk.queries("ch/01/mix"), [])
        events = list(w.flush(desk, clock=desk.clock, wall=desk.wall))
        self.assertEqual([e.after for e in events], [MIX_OFF])
        self.assertEqual(len(desk.queries("ch/01/mix")), 1)
        self.assertEqual([c.path for c in w.summary().net], ["/ch/01/mix"])

    def test_a_pending_query_is_asked_again_by_the_flush(self):
        desk = InterruptedDesk(lambda d: d.queries("ch/01/mix"), drop=1)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        with self.assertRaises(KeyboardInterrupt):
            list(w.run(desk, clock=desk.clock, wall=desk.wall))
        self.assertEqual(len(desk.queries("ch/01/mix")), 1)   # sent, reply lost
        events = list(w.flush(desk, clock=desk.clock, wall=desk.wall))
        self.assertEqual([e.after for e in events], [MIX_OFF])


if __name__ == "__main__":
    unittest.main()
