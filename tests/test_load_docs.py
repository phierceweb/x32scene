"""The public files that describe the live layer name `load`, none calls it read-only, and
`docs/cli.md` names every key of `load --json`."""

import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


class LoadDocsTest(unittest.TestCase):
    def test_no_public_file_calls_the_live_layer_read_only(self):
        stale = ("only reads the desk", "live layer is read-only", "never sets a parameter",
                 "and read the live desk over OSC")
        for name in ("SECURITY.md", "README.md", "pyproject.toml"):
            with self.subTest(file=name):
                text = _read(name)
                for phrase in stale:
                    self.assertNotIn(phrase, text)
                self.assertIn("load", text)

    def test_env_example_scopes_the_live_variables_to_load_too(self):
        lines = [ln for ln in _read(".env.example").splitlines() if ln.startswith("#") and "`pull`" in ln]
        self.assertTrue(lines)
        for ln in lines:
            with self.subTest(line=ln):
                self.assertIn("`load`", ln)

    def test_cli_md_names_every_json_key(self):
        from tests.test_docs import _rows
        from x32scene._json import load_doc
        from x32scene.services.load import LoadResult
        row = _rows()["load"][0]
        for key in load_doc("a.scn", LoadResult()):
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", row)

    def test_the_top_level_help_names_loading(self):
        from x32scene._parsers import DESCRIPTION
        self.assertIn("load", DESCRIPTION)


if __name__ == "__main__":
    unittest.main()
