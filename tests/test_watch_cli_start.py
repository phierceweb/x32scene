"""watch, end to end, at its start: the subscription opens before the start pull and is
kept alive through it, so a change made while the pull runs is not lost."""

import json
import time
import unittest
from unittest import mock

from tests.test_watch_cli import MIX_DOWN, MIX_START, WatchCliBase, WatchConsole
from x32scene.services import watch as W


class StartPullTest(WatchCliBase):
    def changes(self, console):
        rc, out, _ = self.watch(console, "--seconds", "0.8", "--json")
        self.assertEqual(rc, 0)
        docs = [json.loads(ln) for ln in out.splitlines()]
        return ([(d["path"], d["before"], d["after"]) for d in docs if d["event"] == "change"],
                [c["path"] for c in docs[-1]["net"]])

    def test_the_subscription_opens_before_the_first_query(self):
        console = WatchConsole()
        self.watch(console, "--seconds", "0.3")
        self.assertEqual(console.received[0], "/xremote")

    def test_a_change_to_a_pulled_path_while_the_pull_runs_is_logged(self):
        console = WatchConsole(on_query=("/ch/02/mix", MIX_DOWN, ["/ch/01/mix/fader"]))
        logged, net = self.changes(console)
        self.assertEqual(logged, [("/ch/01/mix", MIX_START, MIX_DOWN)])
        self.assertEqual(net, ["/ch/01/mix"])

    def test_a_change_during_the_pull_is_dated_from_the_pull_not_its_end(self):
        console = WatchConsole(on_query=("/ch/01/mix/01", MIX_DOWN, ["/ch/01/mix/fader"]),
                               reply_delay=0.15)
        run_began = []
        real_run = W.Watch.run

        def timed_run(w, *a, **kw):
            run_began.append(time.time())
            return real_run(w, *a, **kw)

        with mock.patch.object(W.Watch, "run", timed_run):
            rc, out, _ = self.watch(console, "--seconds", "0.5", "--json")
        self.assertEqual(rc, 0)
        change = next(json.loads(ln) for ln in out.splitlines() if '"change"' in ln)
        h, m, s = change["time"].split(":")
        began = time.localtime(run_began[0])
        began_s = began.tm_hour * 3600 + began.tm_min * 60 + began.tm_sec + run_began[0] % 1
        self.assertLess(int(h) * 3600 + int(m) * 60 + float(s), began_s - 0.1)

    def test_a_change_before_the_pull_reads_its_path_is_the_start(self):
        console = WatchConsole(on_query=("/ch/01/config", MIX_DOWN, ["/ch/01/mix/fader"]))
        self.assertEqual(self.changes(console), ([], []))

    def test_the_watch_is_told_when_the_start_pull_asked_for_each_path(self):
        seen = []
        real_run = W.Watch.run

        def spy(w, *a, **kw):
            seen.append((dict(kw.get("pulled") or {}), time.monotonic()))
            return real_run(w, *a, **kw)

        started = time.monotonic()
        with mock.patch.object(W.Watch, "run", spy):
            self.watch(WatchConsole(), "--seconds", "0.3")
        pulled, run_began = seen[0]
        self.assertEqual(len(pulled), 5)
        self.assertTrue(all(started < t < run_began for t in pulled.values()), pulled)

    def test_the_subscription_is_renewed_during_a_long_pull(self):
        console = WatchConsole(reply_delay=0.06)
        with mock.patch.object(W, "RENEW", 0.1):
            self.watch(console, "--seconds", "0.3")
        last_query = [i for i, a in enumerate(console.received) if a == "/node"][4]
        self.assertGreaterEqual(console.received[:last_query].count("/xremote"), 2)


if __name__ == "__main__":
    unittest.main()
