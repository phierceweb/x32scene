"""A doc that quotes a fixture ("From [`tests/fixtures/NAME`](...):" then a code block)
quotes lines that fixture still holds."""

import glob
import os
import re
import unittest

from x32scene.model import Line, Scene

ROOT = os.path.join(os.path.dirname(__file__), "..")
QUOTE = re.compile(r"^From \[`tests/fixtures/([^`]+)`\]\([^)]*\):\n\n```\n(.*?)\n```", re.M | re.S)


class FixtureQuoteTest(unittest.TestCase):
    def test_quoted_lines_are_in_the_fixture(self):
        quotes = 0
        for doc in sorted(glob.glob(os.path.join(ROOT, "docs", "*.md"))):
            with open(doc, encoding="utf-8") as fh:
                text = fh.read()
            for name, block in QUOTE.findall(text):
                fixture = Scene.load(os.path.join(ROOT, "tests", "fixtures", name))
                for raw in block.splitlines():
                    quotes += 1
                    ln = Line.parse(raw)
                    held = fixture.get(ln.path)
                    with self.subTest(doc=os.path.basename(doc), path=ln.path):
                        self.assertEqual(held.args if held else None, ln.args)
        self.assertGreater(quotes, 0)


if __name__ == "__main__":
    unittest.main()
