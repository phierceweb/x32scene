"""watch starts its read-back timer from what the start pull measured."""

import unittest
from unittest import mock

from tests.test_watch_cli import WatchCliBase, WatchConsole
from x32scene.services import watch as W


class SeedTest(WatchCliBase):
    def test_the_start_pull_seeds_the_read_back_timer(self):
        seen = []
        real = W.Watch

        def spy(*args, **kw):
            seen.append(kw.get("round_trips"))
            return real(*args, **kw)

        with mock.patch.object(W, "Watch", side_effect=spy):
            rc, _, _ = self.watch(WatchConsole(), "--seconds", "0.3")
        self.assertEqual(rc, 0)
        (trips,) = seen
        self.assertEqual(len(trips), 5)
        self.assertTrue(all(t is not None and 0 <= t < 0.2 for t in trips), trips)


if __name__ == "__main__":
    unittest.main()
