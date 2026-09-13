"""watch: leaf-to-node ownership, debounce, net vs transient, /xremote renewal and the
start-pull backlog — the service over a scripted desk and an injected clock."""

import unittest
from itertools import pairwise

from x32scene.model import Scene
from x32scene.services import watch as W
from x32scene.services.diff import diff

REF_TEXT = ('#4.0# "REF" "" %000000000 1\n'
            "/config/buslink ON ON ON ON ON ON OFF OFF\n"
            '/ch/01/config "Kick" 2 YEi 1\n'
            "/ch/01/eq/1 PEQ 36.0 +0.00 1.0\n"
            "/ch/01/mix ON  +6.5 ON +0 OFF   -oo\n"
            "/ch/01/mix/01 ON  +2.8 +0 PRE 0\n"
            "/ch/02/mix ON  -oo ON +0 OFF   -oo\n")
MIX_OFF = "/ch/01/mix OFF  +6.5 ON +0 OFF   -oo"
MIX_DOWN = "/ch/01/mix ON -10.0 ON +0 OFF   -oo"


class ScriptedDesk:
    """A transport on its own clock: answers /node from in-memory lines and delivers the
    pushes a test schedules. ``drop`` swallows that many /node replies."""

    def __init__(self, text: str = REF_TEXT, drop: int = 0):
        self.now = 0.0
        self.state = {ln.path: ln.raw for ln in Scene.parse(text).lines if ln.path.startswith("/")}
        self.sent: list[tuple[float, str, list]] = []
        self.inbox: list[tuple[float, str, list, str | None]] = []
        self.drop = drop

    def clock(self) -> float:
        return self.now

    def wall(self) -> float:
        return 1_700_000_000.0 + self.now

    def push(self, t: float, addr: str, args: list, new_line: str | None = None) -> None:
        """At ``t`` the desk takes ``new_line`` and reports ``addr``."""
        self.inbox.append((t, addr, args, new_line))
        self.inbox.sort(key=lambda m: m[0])

    def send(self, addr: str, args=()) -> None:
        self.sent.append((self.now, addr, list(args)))
        if addr == "/node":
            if self.drop:
                self.drop -= 1
                return
            line = self.state.get("/" + args[0])
            if line is not None:
                self.push(self.now + 0.002, "node", [line + "\n"])

    def drain(self) -> list:
        waiting = []
        while self.inbox and self.inbox[0][0] <= self.now:
            _, addr, args, new_line = self.inbox.pop(0)
            if new_line is not None:
                self.state[new_line.split(" ", 1)[0]] = new_line
            waiting.append((addr, args))
        return waiting

    def recv(self, timeout: float):
        if self.inbox and self.inbox[0][0] <= self.now + timeout:
            t, addr, args, new_line = self.inbox.pop(0)
            self.now = max(self.now, t)
            if new_line is not None:
                self.state[new_line.split(" ", 1)[0]] = new_line
            return addr, args
        self.now += timeout
        return None

    def queries(self, path: str) -> list[float]:
        return [t for t, addr, args in self.sent if addr == "/node" and args == [path]]


def run(desk: ScriptedDesk, seconds: float = 10.0, **kw):
    ref = Scene.parse(REF_TEXT)
    w = W.Watch(ref, ref, **kw)
    events = list(w.run(desk, seconds=seconds, clock=desk.clock, wall=desk.wall))
    return w, events


class OwnerTest(unittest.TestCase):
    NODES = {ln.path for ln in Scene.parse(REF_TEXT).lines}

    def test_a_leaf_belongs_to_the_longest_reference_path_above_it(self):
        for leaf, node in (("/ch/01/mix/fader", "/ch/01/mix"),
                           ("/ch/01/mix/on", "/ch/01/mix"),
                           ("/ch/01/mix/01/level", "/ch/01/mix/01"),
                           ("/ch/01/eq/1/f", "/ch/01/eq/1"),
                           ("/config/buslink/13-14", "/config/buslink"),
                           ("/ch/01/mix", "/ch/01/mix")):
            with self.subTest(leaf=leaf):
                self.assertEqual(W.owner(leaf, self.NODES), node)

    def test_an_address_outside_the_reference_has_no_owner(self):
        for leaf in ("/-stat/selidx", "/meters/0", "/ch/03/mix/fader", "/ch", "node", ""):
            with self.subTest(leaf=leaf):
                self.assertIsNone(W.owner(leaf, self.NODES))


class DebounceTest(unittest.TestCase):
    def test_a_burst_is_one_query_and_one_change(self):
        desk = ScriptedDesk()
        for i in range(50):
            desk.push(1.0 + i * 0.002, "/ch/01/mix/fader", [0.4 + i * 0.001],
                      MIX_DOWN if i == 0 else None)
        w, events = run(desk)
        self.assertEqual(len(desk.queries("ch/01/mix")), 1)
        self.assertEqual([(e.path, e.before, e.after) for e in events],
                         [("/ch/01/mix", "/ch/01/mix ON  +6.5 ON +0 OFF   -oo", MIX_DOWN)])
        self.assertEqual(w.summary().logged, 1)

    def test_a_long_sweep_is_queried_at_most_once_per_window(self):
        desk = ScriptedDesk()
        for i in range(200):   # two seconds of fader moves, 10 ms apart
            desk.push(1.0 + i * 0.01, "/ch/01/mix/fader", [i / 200],
                      f"/ch/01/mix ON {-60 + i * 0.3:+.1f} ON +0 OFF   -oo")
        _, events = run(desk)
        sent = desk.queries("ch/01/mix")
        self.assertGreater(len(sent), 5)
        self.assertLess(len(sent), 20)
        self.assertTrue(all(b - a >= 0.15 - 1e-9 for a, b in pairwise(sent)))
        self.assertEqual(events[-1].after, desk.state["/ch/01/mix"])   # the final value lands

    def test_a_change_with_no_new_value_logs_nothing(self):
        desk = ScriptedDesk()
        desk.push(1.0, "/ch/01/mix/fader", [0.75])   # reported, but the line reads the same
        w, events = run(desk)
        self.assertEqual(events, [])
        self.assertEqual(len(desk.queries("ch/01/mix")), 1)
        self.assertEqual(w.summary().logged, 0)

    def test_a_lost_reply_is_asked_again(self):
        desk = ScriptedDesk(drop=1)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        _, events = run(desk)
        self.assertEqual(len(desk.queries("ch/01/mix")), 2)
        self.assertEqual([e.after for e in events], [MIX_OFF])


class NetTest(unittest.TestCase):
    def test_a_change_and_back_is_transient_not_net(self):
        desk = ScriptedDesk()
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        desk.push(3.0, "/ch/01/mix/on", [1], "/ch/01/mix ON  +6.5 ON +0 OFF   -oo")
        desk.push(5.0, "/ch/01/eq/1/g", [0.6], "/ch/01/eq/1 PEQ 36.0 +3.00 1.0")
        w, events = run(desk)
        self.assertEqual([e.path for e in events], ["/ch/01/mix", "/ch/01/mix", "/ch/01/eq/1"])
        s = w.summary()
        self.assertEqual([c.path for c in s.net], ["/ch/01/eq/1"])
        self.assertEqual((s.logged, s.transient), (3, 1))

    def test_the_end_scene_differs_from_the_start_by_the_net_changes_only(self):
        desk = ScriptedDesk()
        desk.push(1.0, "/ch/01/eq/1/g", [0.6], "/ch/01/eq/1 PEQ 36.0 +3.00 1.0")
        w, _ = run(desk)
        start = Scene.parse(REF_TEXT)
        end = w.end_scene()
        self.assertEqual(Scene.parse(end.dump()).dump(), end.dump())
        self.assertEqual([(c.path, c.after) for c in diff(start, end)],
                         [("/ch/01/eq/1", "/ch/01/eq/1 PEQ 36.0 +3.00 1.0")])
        self.assertEqual(end.lines[0].raw, start.lines[0].raw)

    def test_an_event_carries_the_wall_time_of_the_push_that_reported_it(self):
        desk = ScriptedDesk()
        desk.push(2.0, "/ch/01/mix/on", [0], MIX_OFF)
        desk.push(2.1, "/ch/01/mix/fader", [0.3], MIX_OFF.replace("+6.5", "-3.0"))
        _, events = run(desk)
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0].at, 1_700_000_000.0 + 2.0, places=3)

    def test_a_change_read_back_twice_takes_each_push_time(self):
        desk = ScriptedDesk()
        desk.push(2.0, "/ch/01/mix/on", [0], MIX_OFF)
        desk.push(5.0, "/ch/01/mix/fader", [0.3], MIX_OFF.replace("+6.5", "-3.0"))
        _, events = run(desk)
        self.assertEqual([round(e.at - 1_700_000_000.0, 3) for e in events], [2.0, 5.0])


class BacklogTest(unittest.TestCase):
    """Pushes that arrive while the start pull runs, kept by the subscription."""

    def test_the_subscription_keeps_pushes_waiting_when_it_is_called(self):
        desk = ScriptedDesk()
        sub = W.subscribe(desk, clock=desk.clock, wall=desk.wall)
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        desk.push(1.1, "/-stat/selidx", [4])
        desk.now = 1.2
        sub()
        self.assertEqual(sub.backlog, [("/ch/01/mix/on", [0], 1.2, 1_700_000_001.2),
                                       ("/-stat/selidx", [4], 1.2, 1_700_000_001.2)])
        desk.now = 1.5
        sub()
        self.assertEqual(len(sub.backlog), 2)

    def test_run_reads_back_the_backlog_and_dates_it_from_when_it_was_kept(self):
        desk = ScriptedDesk()
        sub = W.subscribe(desk, clock=desk.clock, wall=desk.wall)
        desk.push(3.0, "/ch/01/mix/on", [0], MIX_OFF)
        desk.now = 3.2
        sub()
        desk.now = 10.0                      # the pull ends here
        ref = Scene.parse(REF_TEXT)
        w = W.Watch(ref, ref)
        events = list(w.run(desk, seconds=2, clock=desk.clock, wall=desk.wall,
                            backlog=sub.backlog))
        self.assertEqual([(e.path, e.after) for e in events], [("/ch/01/mix", MIX_OFF)])
        self.assertAlmostEqual(events[0].at, 1_700_000_003.2, places=3)
        self.assertEqual(w.summary().ignored, 0)


class UnownedTest(unittest.TestCase):
    def test_addresses_with_no_node_are_counted_and_never_queried(self):
        desk = ScriptedDesk()
        desk.push(1.0, "/-stat/selidx", [4])
        desk.push(1.1, "/meters/0", [b"\x00\x00\x00\x00"])
        desk.push(1.2, "/ch/09/mix/fader", [0.5])
        w, events = run(desk)
        self.assertEqual(events, [])
        self.assertEqual(w.summary().ignored, 3)
        self.assertFalse([a for _, a, _ in desk.sent if a == "/node"])

    def test_a_node_the_snapshot_did_not_answer_is_not_watched(self):
        ref = Scene.parse(REF_TEXT)
        start = Scene.parse("\n".join(ln.raw for ln in ref.lines if ln.path != "/ch/02/mix") + "\n")
        desk = ScriptedDesk()
        desk.push(1.0, "/ch/02/mix/fader", [0.5], "/ch/02/mix ON -3.0 ON +0 OFF   -oo")
        w = W.Watch(ref, start)
        events = list(w.run(desk, seconds=5, clock=desk.clock, wall=desk.wall))
        self.assertEqual(events, [])
        self.assertEqual(w.summary().ignored, 1)
        self.assertEqual(desk.queries("ch/02/mix"), [])


class RenewalTest(unittest.TestCase):
    def test_xremote_is_renewed_inside_ten_seconds(self):
        desk = ScriptedDesk()
        run(desk, seconds=30.0)
        self.assertEqual([t for t, a, _ in desk.sent if a == "/xremote"], [0.0, 8.0, 16.0, 24.0])

    def test_subscribe_sends_xremote_now_and_renews_only_when_due(self):
        desk = ScriptedDesk()
        renew = W.subscribe(desk, clock=desk.clock)
        for t in (3.0, 7.9, 8.0, 12.0, 16.1):
            desk.now = t
            renew()
        self.assertEqual([t for t, a, _ in desk.sent if a == "/xremote"], [0.0, 8.0, 16.1])

    def test_renewal_keeps_its_cadence_through_traffic(self):
        desk = ScriptedDesk()
        for i in range(300):
            desk.push(0.5 + i * 0.1, "/ch/01/mix/fader", [i / 300],
                      f"/ch/01/mix ON {-60 + i * 0.2:+.1f} ON +0 OFF   -oo")
        run(desk, seconds=40.0)
        renewals = [t for t, a, _ in desk.sent if a == "/xremote"]
        self.assertEqual(renewals[0], 0.0)
        self.assertTrue(all(b - a <= 8.0 + 0.01 for a, b in pairwise(renewals)))
        self.assertGreaterEqual(len(renewals), 5)

    def test_it_sends_only_xremote_and_node(self):
        desk = ScriptedDesk()
        desk.push(1.0, "/ch/01/mix/on", [0], MIX_OFF)
        desk.push(2.0, "/-stat/selidx", [4])
        run(desk, seconds=20.0)
        self.assertEqual({a for _, a, _ in desk.sent}, {"/xremote", "/node"})
        self.assertTrue(all(args == [] for _, a, args in desk.sent if a == "/xremote"))

    def test_seconds_ends_the_watch(self):
        desk = ScriptedDesk()
        run(desk, seconds=2.5)
        self.assertGreaterEqual(desk.now, 2.5)
        self.assertLess(desk.now, 2.6)


if __name__ == "__main__":
    unittest.main()
