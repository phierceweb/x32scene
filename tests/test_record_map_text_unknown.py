"""record-map's text view lists a track whose CARD block the console does not write as
`?`, as --json does, rather than hiding it with the OFF tracks."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene.cli import main

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class RecordMapUnknownTrackTest(unittest.TestCase):
    def test_the_blocks_tracks_show_as_unknown(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        i = next(i for i, ln in enumerate(lines) if ln.startswith("/config/routing/CARD "))
        toks = lines[i].split(" ")
        lines[i] = " ".join([toks[0], "UOUT0-7", *toks[2:]])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "hand.scn")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write("\n".join(lines))
            rc, out, _ = run("record-map", path)
        self.assertEqual(rc, 0)
        for track in range(1, 9):
            self.assertIn(f"track {track:>2} <- ?", out)


if __name__ == "__main__":
    unittest.main()
