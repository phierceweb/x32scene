"""ports names every AES50 channel a main output leaves on: an OUT block on the port, and a
UOUT block whose user-out slot carries the output, as preflight's reachability counts it.
The card is not a stage box, so it is not among them."""

import contextlib
import io
import os
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.routing import output_aes_mirrors, output_reach

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ALT = os.path.join(FIXTURES, "example-alt.scn")


class UserOutMirrorsTest(unittest.TestCase):
    def test_mirrors_are_the_aes50_paths_reachability_counts(self):
        for name in ("example.scn", "example-alt.scn"):
            sc = Scene.load(os.path.join(FIXTURES, name))
            mirrors, reach = output_aes_mirrors(sc), output_reach(sc)
            for out in range(1, 17):
                with self.subTest(fixture=name, out=out):
                    want = [p for p in reach.get(out, []) if p.startswith("AES50")]
                    self.assertEqual(mirrors.get(out, []), want)
                    self.assertFalse(any(p.startswith("CARD") for p in mirrors.get(out, [])))

    def test_the_text_view_shows_a_user_out_path(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["ports", ALT]), 0)
        row = next(ln for ln in out.getvalue().splitlines() if " 09 " in ln or "main 09" in ln
                   or ln.lstrip().startswith("09"))
        self.assertIn("AES50-A 9 via user-out 9", row)


if __name__ == "__main__":
    unittest.main()
