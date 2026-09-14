"""`x32scene --help` tells a user what the tool is and where to read on, not how it is built."""

import contextlib
import io
import unittest

from x32scene.cli import main


class TopHelpTest(unittest.TestCase):
    def test_help_describes_the_tool_and_points_at_per_command_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        text = out.getvalue()
        head = " ".join(text.split("positional arguments")[0].split())
        self.assertIn("X32", head)
        self.assertIn("x32scene <command> --help", head)
        self.assertIn("docs/cli.md", head)
        for internal in ("_views", "_cli_edits", "exception boundary", "argparse", "dispatch"):
            self.assertNotIn(internal, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
