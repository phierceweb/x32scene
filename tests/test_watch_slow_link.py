"""watch on a link slower than --timeout: the read-back timer follows the measured round
trip, so a fader ride is logged while it happens and never logged backwards."""

import random
import unittest

from tests.test_watch import REF_TEXT, ScriptedDesk
from x32scene.model import Scene
from x32scene.services import watch as W

RIDE_START, RIDE_END, STEP = 1.0, 21.0, 0.05


def fader(i: int) -> str:
    return f"/ch/01/mix ON {-80 + i * 0.01:+.2f} ON +0 OFF   -oo"


class SlowDesk(ScriptedDesk):
    """Answers the n-th /node query ``delay(n)`` seconds later with the line the desk held
    when it was asked."""

    def __init__(self, delay):
        super().__init__()
        self.delay = delay

    def send(self, addr: str, args=()) -> None:
        self.sent.append((self.now, addr, list(args)))
        if addr == "/node":
            n = len(self.queries(args[0])) - 1
            self.push(self.now + self.delay(n), "node", [self.state["/" + args[0]] + "\n"])


def ride(delay, seconds: float = 25.0, **kw):
    """A fader ride pushing a new value every 50 ms; returns (desk, [(logged at, event)])."""
    desk = SlowDesk(delay)
    steps = round((RIDE_END - RIDE_START) / STEP)
    for i in range(steps + 1):
        desk.push(RIDE_START + i * STEP, "/ch/01/mix/fader", [i / steps], fader(i))
    ref = Scene.parse(REF_TEXT)
    w = W.Watch(ref, ref, **kw)
    return desk, [(desk.now, e) for e in w.run(desk, seconds=seconds, clock=desk.clock,
                                                 wall=desk.wall)]


def value(line: str) -> float:
    return float(line.split()[2])


class SlowLinkTest(unittest.TestCase):
    """--timeout 0.5, every reply 0.55 s after its query, steady or within 10 ms: a retry at
    --timeout always goes out before the first reply lands."""

    LINKS = {"steady": lambda n: 0.55, "jittered": lambda n: 0.55 + ((n * 37) % 21 - 10) / 1000}

    def rides(self, **kw):
        for name, delay in self.LINKS.items():
            with self.subTest(link=name):
                yield ride(delay, **kw)

    def test_a_ride_is_logged_while_it_happens(self):
        for _, logged in self.rides():
            during = [t for t, _ in logged if t <= RIDE_END]
            self.assertGreater(len(during), 25)
            self.assertLess(during[0] - RIDE_START, 2.5)
            gaps = [b - a for a, b in zip(during, [*during[1:], RIDE_END], strict=True)]
            self.assertLess(max(gaps), 2 * 0.56 + 0.1)

    def test_no_logged_value_goes_back(self):
        for _, logged in self.rides():
            values = [value(e.after) for _, e in logged]
            self.assertEqual(values, sorted(set(values)))
            self.assertEqual([e.before for _, e in logged[1:]], [e.after for _, e in logged[:-1]])

    def test_the_final_value_lands_within_two_round_trips_of_the_end(self):
        for desk, logged in self.rides():
            t, last = logged[-1]
            self.assertEqual(last.after, desk.state["/ch/01/mix"])
            self.assertLessEqual(t - RIDE_END, 2 * 0.56 + 0.01)

    def test_a_start_pull_that_timed_out_starts_the_timer_backed_off(self):
        _, logged = ride(lambda n: 0.55, round_trips=[None] * 5)
        self.assertAlmostEqual(logged[0][0], RIDE_START + 0.15 + 0.55, delta=0.01)

    def test_the_end_read_back_waits_out_the_measured_round_trip(self):
        # 0.8 s replies: a read-back out at the end, then one more, takes past two --timeouts
        desk, logged = ride(lambda n: 0.8, seconds=10.0)
        self.assertGreaterEqual(value(logged[-1][1].after), value(fader(round(9.0 / STEP))))
        self.assertLessEqual(desk.now, 10.0 + 2 * (0.8 + 0.125) + 0.01)


class MixedLinkTest(unittest.TestCase):
    """About one reply in five 0.55 s late, the rest at once."""

    def test_no_logged_value_goes_back(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                rnd = random.Random(seed)
                slow = [rnd.random() < 0.2 for _ in range(2000)]
                desk, logged = ride(lambda n, slow=slow: 0.55 if slow[n] else 0.002)
                values = [value(e.after) for _, e in logged]
                self.assertEqual(values, sorted(set(values)))
                self.assertEqual(logged[-1][1].after, desk.state["/ch/01/mix"])
                self.assertGreater(sum(t <= RIDE_END for t, _ in logged), 25)


class VerySlowLinkTest(unittest.TestCase):
    """Round trips near the timer's cap, one reply in four later than six --timeouts."""

    def test_a_measured_slow_round_trip_keeps_very_late_replies_in_order(self):
        desk, logged = ride(lambda n: 3.4 if n % 4 == 3 else 1.8, seconds=30.0,
                            round_trips=[1.8] * 5)
        values = [value(e.after) for _, e in logged]
        self.assertEqual(values, sorted(set(values)))
        self.assertEqual(logged[-1][1].after, desk.state["/ch/01/mix"])


if __name__ == "__main__":
    unittest.main()
