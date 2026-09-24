"""watch on a slow link when one read-back's reply comes back after it was taken as lost:
every later reply is credited one read-back late, so the last one answers nothing asked for.
The watch still ends on the desk's line."""

import unittest

from tests.test_watch import REF_TEXT
from tests.test_watch_slow_link import RIDE_END, RIDE_START, STEP, SlowDesk, fader
from x32scene.model import Scene
from x32scene.services import watch as W


def ride(delay, seconds: float):
    desk = SlowDesk(delay)
    steps = round((RIDE_END - RIDE_START) / STEP)
    for i in range(steps + 1):
        desk.push(RIDE_START + i * STEP, "/ch/01/mix/fader", [i / steps], fader(i))
    ref = Scene.parse(REF_TEXT)
    w = W.Watch(ref, ref)
    list(w.run(desk, seconds=seconds, clock=desk.clock, wall=desk.wall))
    return desk, w


class LateReplyTest(unittest.TestCase):
    def test_a_reply_nothing_asked_for_that_differs_is_read_again(self):
        # 0.55 s replies hold the lapse near 4 s; the k-th reply comes later than that
        for late, k in ((5.0, 12), (6.0, 20), (9.0, 14)):
            with self.subTest(late=late, query=k):
                desk, w = ride(lambda n, k=k, late=late: late if n == k else 0.55,
                               seconds=RIDE_END + 8.0)
                self.assertEqual(w.summary().unanswered, [])
                self.assertEqual(w.end_scene().get("/ch/01/mix").raw, desk.state["/ch/01/mix"])


if __name__ == "__main__":
    unittest.main()
