"""The start pull's reply times, for watch's read-back timer: one entry per path that
answered, in reply order, None when the path had been asked again before its reply came."""

import unittest

from tests.test_osc import CANNED, FakeConsole
from x32scene.model import Scene
from x32scene.services.osc import pull_lines, pull_scene_like

PATHS = list(CANNED)


class RoundTripsTest(unittest.TestCase):
    def pull(self, delay: float, **kw):
        console = FakeConsole(delay=delay)
        console.start()
        try:
            trips: list = []
            lines, missing = pull_lines("127.0.0.1", kw.pop("paths", PATHS), port=console.port,
                                        round_trips=trips, **kw)
        finally:
            console.stop()
        return lines, missing, trips

    def test_a_prompt_reply_is_timed_from_its_query(self):
        lines, missing, trips = self.pull(0.0, timeout=0.5, paths=[*PATHS, "ch/99/nope"],
                                          retries=0)
        self.assertEqual((len(lines), missing), (len(PATHS), ["ch/99/nope"]))
        self.assertEqual(len(trips), len(PATHS))
        self.assertTrue(all(t is not None and 0 <= t < 0.5 for t in trips), trips)

    # the fake console answers one query at a time, so a slow one's last reply can come
    # after the pull ends; what was recorded is one entry per path that answered

    def test_a_reply_after_the_retry_went_out_is_not_timed(self):
        lines, _, trips = self.pull(0.3, timeout=0.2, retries=1)
        self.assertGreaterEqual(len(lines), 1)
        self.assertEqual(trips, [None] * len(lines))

    def test_a_late_reply_to_a_path_asked_once_is_timed(self):
        lines, _, trips = self.pull(0.3, timeout=0.2, retries=0, paths=PATHS[:2])
        self.assertEqual(len(trips), len(lines))
        self.assertGreaterEqual(trips[0], 0.2)

    def test_a_scene_pull_passes_them_on(self):
        console = FakeConsole()
        console.start()
        try:
            trips: list = []
            ref = Scene.parse("".join(line + "\n" for line in CANNED.values()))
            pull_scene_like(ref, "127.0.0.1", port=console.port, timeout=0.5, round_trips=trips)
        finally:
            console.stop()
        self.assertEqual(len(trips), len(CANNED))


if __name__ == "__main__":
    unittest.main()
