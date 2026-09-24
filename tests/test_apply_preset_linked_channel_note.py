"""apply-preset writes processing to the channel it names only. When that channel is
stereo-linked, the summary says the partner kept its own processing, since a load that
reconciles the pair can end at the partner's."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.channelfx import pair_linked

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
EXAMPLE = os.path.join(FIXTURES, "example.scn")
PRESET = os.path.join(FIXTURES, "example.chn")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def channels() -> tuple[int, int, int]:
    """A linked channel, its partner, and an unlinked channel of the fixture."""
    sc = Scene.load(EXAMPLE)
    linked = [ch for ch in range(1, 33) if pair_linked(sc, f"/ch/{ch:02d}")]
    unlinked = next(ch for ch in range(1, 33) if ch not in linked)
    partner = int(pair_linked(sc, f"/ch/{linked[0]:02d}").rsplit("/", 1)[1])
    return linked[0], partner, unlinked


class LinkedChannelNoteTest(unittest.TestCase):
    def apply(self, ch: int) -> str:
        with tempfile.TemporaryDirectory() as d:
            rc, out, _ = run("apply-preset", EXAMPLE, str(ch), PRESET, "-o",
                             os.path.join(d, "out.scn"))
        self.assertEqual(rc, 0)
        return out

    def test_a_linked_channel_names_its_partner(self):
        ch, partner, _ = channels()
        out = self.apply(ch)
        self.assertIn(f"ch{partner:02d} keeps its own processing", out)

    def test_an_unlinked_channel_has_no_note(self):
        *_, ch = channels()
        self.assertNotIn("keeps its own processing", self.apply(ch))


if __name__ == "__main__":
    unittest.main()
