"""The regex tokenizer against the character-by-character rule it replaced."""

import glob
import os
import random
import unittest

from x32scene import tokenize
from x32scene.model import _spans

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def reference_spans(s):
    spans, i, n = [], 0, len(s)
    while i < n:
        if s[i] == " ":
            i += 1
            continue
        j = i + 1
        if s[i] == '"':
            while j < n and s[j] != '"':
                j += 1
            j = min(j + 1, n)
        else:
            while j < n and s[j] != " ":
                j += 1
        spans.append((i, j))
        i = j
    return spans


def fuzz(count, seed=7):
    rnd = random.Random(seed)
    alphabet = ' "ab\t/1.-#\\'
    return ["".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 24)))
            for _ in range(count)]


EDGES = ["", " ", "   ", '"', '""', '" "', '"a"b', 'a"b', 'a "b c', '"a b" c', "a  b ",
         "\ta b", '/ch/01/config "Lead Vox" 1 1 1', '#4.0# "x" %000 1   ']


class TokenizerEquivalenceTest(unittest.TestCase):
    def check(self, lines):
        for s in lines:
            ref = reference_spans(s)
            self.assertEqual(_spans(s), ref, s)
            self.assertEqual(tokenize(s), [s[a:b] for a, b in ref], s)

    def test_edges(self):
        self.check(EDGES)

    def test_every_fixture_line(self):
        for path in glob.glob(os.path.join(FIXTURES, "**", "*.*"), recursive=True):
            with open(path, encoding="utf-8", errors="replace", newline="") as fh:
                self.check(fh.read().split("\n"))

    def test_fuzzed_lines(self):
        self.check(fuzz(20_000))


if __name__ == "__main__":
    unittest.main()
