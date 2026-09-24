"""watch's end read-back when the desk changes during it: the change's push is past the end
and dropped, so both read-backs out carry one leaf count, yet their replies differ. The log
must still follow the order the desk took its values in, whichever reply comes back first."""

import itertools
import unittest

from tests.test_watch import REF_TEXT
from tests.test_watch_roundtrip import Planned
from x32scene.model import Scene
from x32scene.services import watch as W

V = [f"/ch/01/mix ON {v} ON +0 OFF   -oo" for v in ("-30.0", "-20.0", "-10.0")]
DELAYS = (0.002, 0.3, 0.6, 0.9, 1.4, None)


class FlushChangeTest(unittest.TestCase):
    def check(self, plan, *leaves):
        """/ch/02/mix never answers, so the end read-back runs to its bound and hears every
        late reply."""
        desk = Planned({"ch/01/mix": plan, "ch/02/mix": [None] * 2})
        desk.push(1.95, "/ch/02/mix/fader", [0.1], "/ch/02/mix ON -3.0 ON +0 OFF   -oo")
        for t, value in leaves:
            desk.push(t, "/ch/01/mix/fader", [0.2], V[value])
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        events = [e for e in w.run(desk, seconds=2.0, clock=desk.clock, wall=desk.wall)
                  if e.path == "/ch/01/mix"]
        self.assertGreaterEqual(desk.now, 2.0 + 2 * 0.5)
        order = [V.index(e.after) for e in events]
        self.assertEqual(order, sorted(set(order)))
        self.assertEqual([e.before for e in events[1:]], [e.after for e in events[:-1]])

    def test_a_change_during_the_end_read_back_never_logs_an_older_value(self):
        # V[1] at 1.9 is read back at the end (2.0) and again at 2.5; V[2] lands between
        for d_end, d_retry in itertools.product(DELAYS, repeat=2):
            with self.subTest(end=d_end, retry=d_retry):
                self.check([0.002, d_end, d_retry], (1.0, 0), (1.9, 1), (2.2, 2))

    def test_a_slow_read_back_out_at_the_end_never_logs_an_older_value(self):
        # V[1] at 1.6 is read back at 1.75 and still out at the end; V[2] lands at 2.1, and
        # the retry at 2.25 reads it
        for d_out, d_retry in itertools.product(DELAYS, repeat=2):
            with self.subTest(out=d_out, retry=d_retry):
                self.check([0.002, d_out, d_retry], (1.0, 0), (1.6, 1), (2.1, 2))


if __name__ == "__main__":
    unittest.main()
