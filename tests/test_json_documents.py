"""Every JSON document the CLI reads — a band-setup plan, the preflight config, the stage
sidecar — fails as one named error line with the command's exit code, whatever the text."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from x32scene.cli import main

HERE = os.path.dirname(__file__)
SCENE = os.path.join(HERE, "fixtures", "example.scn")
CONFIG = os.path.join(HERE, "..", "config", "example-preflight.json")
DEPTH = 100_000
DEEP = {
    "array": "[" * DEPTH + "]" * DEPTH,
    "object under a valid key": '{"outputs": ' + '{"a": ' * DEPTH + "1" + "}" * DEPTH + "}",
}


class DeeplyNestedJsonTest(unittest.TestCase):
    """json raises RecursionError past the interpreter's limit, which the CLI boundary
    does not catch: it has to arrive as a named ValueError instead."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def _run(self, argv, env=None):
        err = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            rc = main(argv)
        return rc, err.getvalue()

    def test_every_json_reader_names_the_file(self):
        out = os.path.join(self.dir.name, "o.scn")
        for shape, text in DEEP.items():
            doc = os.path.join(self.dir.name, "deep.json")
            with open(doc, "w") as fh:
                fh.write(text)
            cases = [
                (["band-setup", SCENE, doc, "-o", out], None, 2),
                (["preflight", SCENE, "--config", doc], None, 1),
                (["preflight", SCENE], {"X32SCENE_CONFIG": doc}, 1),
                (["preflight", SCENE, "--config", CONFIG, "--stage", doc], None, 1),
                (["ports", SCENE, "--config", doc], None, 1),
                (["ports", SCENE, "--config", CONFIG, "--stage", doc], None, 1),
                (["report", SCENE, "--config", doc], None, 1),
                (["report", SCENE, "--config", CONFIG, "--stage", doc], None, 1),
            ]
            for argv, env, code in cases:
                with self.subTest(shape=shape, argv=argv[0], env=env, flags=argv[2:]):
                    rc, err = self._run(argv, env)
                    self.assertEqual(rc, code)
                    self.assertIn(doc, err)
                    self.assertIn("nests too deeply", err)
                    self.assertEqual(len(err.strip().splitlines()), 1, err)
                    self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
