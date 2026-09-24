"""A user-out slot read by `/config/routing/OUT` is named as a position of that routing
bank, never as an XLR jack: positions 9-16 have no jack on an 8-jack console and none do on
a console with no rear outputs, and the scene does not say which console it is."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services import routing_edit as RT
from x32scene.services.routing import user_out_readers

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class OutRoutingWordingTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)
        RT.set_routing(self.sc, "OUT", {"9-12": "UOUT9-12", "13-16": "UOUT13-16"})

    def test_the_out_bank_is_named_by_routing_position(self):
        self.assertIn("XLR-out routing 9", user_out_readers(self.sc, 9))
        self.assertIn("XLR-out routing 16", user_out_readers(self.sc, 16))
        for slot in range(1, 49):
            with self.subTest(slot=slot):
                self.assertFalse(any(r.startswith("XLR out") for r in
                                     user_out_readers(self.sc, slot)))

    def test_set_record_prints_the_same_words(self):
        with tempfile.TemporaryDirectory() as d:
            scene, out = os.path.join(d, "in.scn"), os.path.join(d, "out.scn")
            self.sc.save(scene)
            rc, text, err = run("set-record", scene, "9", "Output 1", "-o", out)
            self.assertEqual(rc, 0, err)
            feeds = next(ln for ln in text.splitlines() if "also feeds" in ln)
            self.assertIn("XLR-out routing 9", feeds)
            self.assertNotIn("XLR out", feeds)


if __name__ == "__main__":
    unittest.main()
