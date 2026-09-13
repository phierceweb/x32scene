"""Every third-party action in a workflow is pinned to a full commit SHA, its tag in a comment."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
_USES = re.compile(r"^\s*-?\s*uses:\s*(.+?)\s*$")
_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$")


def unpinned(text: str) -> list[str]:
    refs = (m.group(1) for m in map(_USES.match, text.splitlines()) if m)
    return [r for r in refs if not r.startswith("./") and not _PINNED.match(r)]


@unittest.skipUnless(WORKFLOWS.is_dir(), "workflows ship only in the repository")
class WorkflowPinTest(unittest.TestCase):
    def test_every_action_is_pinned_to_a_sha(self):
        files = sorted(WORKFLOWS.glob("*.yml"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(workflow=path.name):
                self.assertEqual(unpinned(path.read_text(encoding="utf-8")), [])

    def test_a_tag_or_branch_ref_is_caught(self):
        for ref in ("actions/checkout@v4", "pypa/gh-action-pypi-publish@release/v1",
                    "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
                    "actions/checkout@11d5960a # v4.4.0"):
            with self.subTest(ref=ref):
                self.assertEqual(unpinned(f"      - uses: {ref}\n"), [ref])


if __name__ == "__main__":
    unittest.main()
