"""watch, end to end, against a desk that answers slowly: the fake console's script waits on
the watcher, so a slow start pull or read-back changes how long a test runs, not what it
sees."""

import json
import unittest

from tests.watch_console import MIX_DOWN, MIX_START, READ_BACK, WatchCliBase, WatchConsole


class SlowDeskTest(WatchCliBase):
    def test_a_change_scripted_after_a_slow_start_pull_is_logged(self):
        console = WatchConsole(reply_delay=0.1, script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"])])
        rc, out, _ = self.watch(console, "--seconds", "1")
        self.assertEqual(rc, 0)
        self.assertIn("1 change(s) logged", out)

    def test_a_second_change_waits_for_the_read_back_of_the_first(self):
        console = WatchConsole(reply_delay=0.1,
                               script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (READ_BACK, MIX_START, ["/ch/01/mix/fader"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--json")
        self.assertEqual(rc, 0)
        summary = json.loads(out.splitlines()[-1])
        self.assertEqual((summary["logged"], summary["transient"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
