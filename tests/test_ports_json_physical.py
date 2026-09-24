"""`ports --json` carries the physical/virtual label the text view prints: the count it
came from, and per output true (a rear jack), false (virtual) or null (not a main output,
or no count given)."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from x32scene.cli import main

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def labels(doc: dict) -> dict[tuple[str, int], object]:
    return {(r["bank"], r["n"]): r["physical"] for r in doc["outputs"]}


class PortsJsonPhysicalTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for var in ("X32SCENE_CONFIG", "X32SCENE_STAGE", "X32SCENE_CONSOLE"):
            os.environ.pop(var, None)
        self.cfg = os.path.join(self.dir, "rig.json")
        with open(self.cfg, "w", encoding="utf-8") as fh:
            json.dump({"monitor": {"physical_outputs": 8}}, fh)

    def _doc(self, *extra: str) -> dict:
        rc, text, err = run("ports", SCENE, "--bank", "all", "--json", *extra)
        self.assertEqual((rc, err), (0, ""))
        return json.loads(text)

    def test_a_count_from_the_model_or_the_config_labels_the_main_outputs(self):
        for extra in (("--console", "X32RACK"), ("--config", self.cfg)):
            with self.subTest(extra=extra):
                doc = self._doc(*extra)
                self.assertEqual(doc["physical_outputs"], 8)
                got = labels(doc)
                self.assertEqual([got[("main", n)] for n in (1, 8, 9, 16)],
                                 [True, True, False, False])
                self.assertIsNone(got[("aux", 1)])
                self.assertIsNone(got[("p16", 1)])

    def test_the_label_agrees_with_the_text_view(self):
        rc, text, _ = run("ports", SCENE, "--console", "X32RACK")
        self.assertEqual(rc, 0)
        got = labels(self._doc("--console", "X32RACK"))
        for n in range(1, 17):
            with self.subTest(n=n):
                tag = "[XLR ]" if got[("main", n)] else "[virt]"
                self.assertIn(f"main {n:02d} {tag}", text)

    def test_a_console_with_no_jacks_labels_every_main_output_virtual(self):
        doc = self._doc("--console", "X32 Core")
        self.assertEqual(doc["physical_outputs"], 0)
        self.assertFalse(any(v for (bank, _), v in labels(doc).items() if bank == "main"))

    def test_without_a_count_nothing_is_labelled(self):
        doc = self._doc()
        self.assertIsNone(doc["physical_outputs"])
        self.assertEqual(set(labels(doc).values()), {None})

    def test_explain_carries_the_same_outputs_document(self):
        rc, text, _ = run("explain", SCENE, "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(text)["outputs"], self._doc())


if __name__ == "__main__":
    unittest.main()
