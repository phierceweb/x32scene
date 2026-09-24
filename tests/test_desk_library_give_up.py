"""desk gives up on a desk that goes away partway through its memory-slot read, instead of
waiting out every remaining slot."""

import time
import unittest

from tests.test_desk_absent_paths import PREFS, Fading
from x32scene.services import desk as D
from x32scene.services.osc import OscError


class LibraryGiveUpTest(unittest.TestCase):
    def test_a_desk_that_goes_away_during_the_library_read_is_given_up_on(self):
        before_library = len(D._STAT) + len(PREFS) + 1
        with Fading(answers=before_library + 50) as desk:
            started = time.monotonic()
            with self.assertRaises(OscError) as cm:
                D.read_desk("127.0.0.1", port=desk.port, timeout=0.05)
            elapsed = time.monotonic() - started
            asked = desk.received.count("/node")
        self.assertLess(asked, before_library + 50 + 40)
        self.assertLess(elapsed, 3.0)
        self.assertIn("in a row", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
