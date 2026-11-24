"""snippet --filter: the slice a desk snippet slot saved through a filter recalls, written
from one scene; a filter that cannot be read, or selects nothing, writes no file."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.snippet_filter import filtered_snippet, header_from_names

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
EXAMPLE_ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


class SnippetFilterCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, "Guest mix.snp")

    def test_the_file_is_the_slice_under_the_filter_itself(self):
        rc, out, err = run("snippet", EXAMPLE, "-o", self.out, "--filter", "send 9-12",
                           "--filter", "Config", "--strips", "ch,auxin,fxrtn", "--strips", "bus9-10")
        self.assertEqual((rc, err), (0, ""))
        want = filtered_snippet(Scene.load(EXAMPLE), header_from_names(
            "Guest mix", ["Send 9-12", "Config"], ["ch", "auxin", "fxrtn", "bus9-10"]))
        with open(self.out, encoding="utf-8", newline="") as fh:
            self.assertEqual(fh.read(), want.scene.dump())
        self.assertEqual(out.splitlines()[:2], [f"wrote {self.out}: 274 lines",
                                                "  filters: Config, Send 9-12"])
        self.assertIn("  auxbuses: auxin01, ", out)
        self.assertNotIn("skipped", out)

    def test_header_prints_the_filter_typed(self):
        run("snippet", EXAMPLE, "-o", self.out, "--name", "Lead vox", "--filter", "strip",
            "--strips", "ch25,main/st")
        rc, out, _ = run("header", self.out)
        self.assertEqual(rc, 0)
        self.assertIn("name: Lead vox\n", out)
        self.assertIn("filters: Preamp HA, Config, EQ, Gate & Comp, Insert, Groups, Fader, Pan, "
                      "Mute, Send 1-8, Send 9-12, Send 13-16, Send M/C, LR, Send Matrix\n", out)
        self.assertIn("channels: ch25\n", out)
        self.assertIn("maingrps: main/st\n", out)

    def test_a_category_that_no_strip_gates_needs_no_strips(self):
        rc, out, _ = run("snippet", EXAMPLE, "-o", self.out, "--filter", "FX 1", "--filter", "Routing")
        self.assertEqual(rc, 0)
        self.assertIn("  filters: FX 1, Routing\n", out)
        with open(self.out, encoding="utf-8") as fh:
            paths = {ln.split(" ")[0].rsplit("/", 1)[0] for ln in fh.read().splitlines()[1:]}
        self.assertEqual(paths, {"/fx", "/fx/1", "/config/routing/IN", "/config/routing/AES50A",
                                 "/config/routing/AES50B", "/config/routing/CARD",
                                 "/config/routing/OUT", "/config/routing/PLAY"})

    def test_any_strip_family_satisfies_a_per_strip_category(self):
        for strips, lines in (("ch1", 5), ("bus9", 7), ("fxrtn1", 5), ("mtx1", 7),
                              ("main/st", 7), ("main/m", 7)):
            with self.subTest(strips=strips):
                rc, out, err = run("snippet", EXAMPLE, "-o", self.out, "--force",
                                   "--filter", "EQ", "--strips", strips)
                self.assertEqual((rc, err), (0, ""))
                self.assertEqual(out.splitlines()[0], f"wrote {self.out}: {lines} lines")

    def test_refusals_write_nothing(self):
        f, s = ("--filter", "EQ"), ("--strips", "ch1")
        cases = {
            "unknown category": ((EXAMPLE, "--filter", "Sends", *s), "no snippet category 'Sends': one of"),
            "unknown strip": ((EXAMPLE, *f, "--strips", "chan1"), "no strip 'chan1'"),
            "strip out of range": ((EXAMPLE, *f, "--strips", "ch33"), "ch33: ch runs 1-32"),
            "strips alone": ((EXAMPLE, *s), "--strips names the strips of a --filter"),
            "no strips": ((EXAMPLE, *f, "--filter", "FX 1"),
                          "EQ is recalled per strip: name the strips with --strips"),
            "two scenes": ((EXAMPLE, EXAMPLE_ALT, *f, *s), "--filter takes one scene"),
            "with --edit": ((EXAMPLE, *f, *s, "--edit", "set-fader 1 -3"), "--filter takes one scene"),
            "with --bus": ((EXAMPLE, *f, *s, "--bus", "9"), "--filter takes one scene"),
            "with --only": ((EXAMPLE, *f, *s, "--only", "/ch/01/*"), "--filter takes one scene"),
            "nothing selected": ((EXAMPLE, "--filter", "Send Matrix", *s),
                                 "the filter selects no line of"),
        }
        for case, (argv, said) in cases.items():
            with self.subTest(case=case):
                rc, out, err = run("snippet", *argv, "-o", self.out)
                self.assertEqual((rc, out), (1, ""))
                self.assertIn(said, err)
                self.assertEqual(err.count("\n"), 1)
                self.assertFalse(os.path.exists(self.out))

    def test_the_output_guard_holds(self):
        scene = os.path.join(self.tmp, "in.scn")
        shutil.copy(EXAMPLE, scene)
        before = open(scene, encoding="utf-8", newline="").read()
        rc, _, err = run("snippet", scene, "-o", scene, "--force", "--filter", "EQ", "--strips", "ch1")
        self.assertEqual(rc, 1)
        self.assertEqual(open(scene, encoding="utf-8", newline="").read(), before)
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("keep me")
        rc, _, err = run("snippet", scene, "-o", self.out, "--filter", "EQ", "--strips", "ch1")
        self.assertEqual(rc, 1)
        self.assertIn("--force", err)
        self.assertEqual(open(self.out, encoding="utf-8").read(), "keep me")
        self.assertEqual(run("snippet", scene, "-o", self.out, "--force", "--filter", "EQ",
                             "--strips", "ch1")[0], 0)

    def test_the_other_modes_say_how_a_filter_is_taken(self):
        rc, _, err = run("snippet", EXAMPLE, "-o", self.out)
        self.assertEqual(rc, 1)
        self.assertIn("one scene with --bus/--only/--filter (those lines as they are)", err)


if __name__ == "__main__":
    unittest.main()
