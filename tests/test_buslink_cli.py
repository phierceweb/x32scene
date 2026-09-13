"""The set-bus-link command, the snippet --edit that refuses it, and the warning on a snippet
delta across a link change.

Fixture facts the cases lean on: buses 13/14 are unlinked; buses 9/10 are linked and feed
aux outs 5/6; bus 1 is already linked.
"""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.buslink import set_bus_link

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class SetBusLinkCliTest(unittest.TestCase):
    def test_link_writes_and_reports(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "linked.scn")
            code, text, _ = _run("set-bus-link", EXAMPLE, "14", "on", "-o", out)
            self.assertEqual(code, 0)
            self.assertEqual(Scene.load(out).get("/config/buslink").args[6], "ON")
            self.assertIn("linked bus 13/14", text)
            self.assertIn("sender sends", text)
            self.assertIn("/bus/14/mix", text)
            self.assertIn("no output is fed from bus 13 or 14", text)
            self.assertTrue(text.rstrip().endswith("LOAD-TEST on the console before a gig."))

    def test_unlink_names_the_outputs_the_pair_feeds(self):
        with tempfile.TemporaryDirectory() as d:
            code, text, _ = _run("set-bus-link", EXAMPLE, "9", "off", "-o",
                                 os.path.join(d, "u.scn"))
            self.assertEqual(code, 0)
            self.assertIn("unlinked bus 9/10", text)
            self.assertIn("aux 05 <- bus 9", text)
            self.assertIn("aux 06 <- bus 10", text)

    def test_state_is_accepted_in_either_case(self):
        for state, token in (("ON", "ON"), ("On", "ON"), ("OFF", "OFF")):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "x.scn")
                bus = "13" if token == "ON" else "9"
                self.assertEqual(_run("set-bus-link", EXAMPLE, bus, state, "-o", out)[0], 0)
                links = Scene.load(out).get("/config/buslink").args
                self.assertEqual(links[(int(bus) - 1) // 2], token)

    def test_a_refused_state_is_quoted_as_typed(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            main(["set-bus-link", EXAMPLE, "13", "MAYBE", "-o", "x.scn"])
        self.assertIn("invalid choice: 'MAYBE' (choose from on, off)", err.getvalue())

    def test_refusals_exit_1_and_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "x.scn")
            for argv in (["1", "on"], ["13", "off"], ["17", "on"], ["0", "off"]):
                with self.subTest(argv=argv):
                    self.assertEqual(_run("set-bus-link", EXAMPLE, *argv, "-o", out)[0], 1)
                    self.assertFalse(os.path.exists(out))

    def test_snippet_edit_refuses_it_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "link.snp")
            for edits in (["set-bus-link 13 on"], ["set-fader 5 -3", "set-bus-link 9 OFF"]):
                with self.subTest(edits=edits):
                    argv = [a for e in edits for a in ("--edit", e)]
                    code, text, err = _run("snippet", EXAMPLE, "-o", out, *argv)
                    self.assertEqual(code, 1)
                    self.assertEqual(text, "")
                    msg = err.strip().splitlines()
                    self.assertEqual(len(msg), 1, err)
                    self.assertIn("/config/buslink", msg[0])
                    self.assertIn("set-bus-link", msg[0])
                    self.assertFalse(os.path.exists(out))

    def test_snippet_help_does_not_offer_it_to_edit(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            main(["snippet", "--help"])
        self.assertIn("but set-bus-link", " ".join(out.getvalue().split()))


class HalfLinkSnippetTest(unittest.TestCase):
    """A delta across a link change carries the reshaped lines but never the link."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        self.linked = os.path.join(self.dir, "linked.scn")
        sc = Scene.load(EXAMPLE)
        set_bus_link(sc, 13, True)
        sc.get("/ch/01/mix").set_arg(1, "-10.0")
        sc.save(self.linked)
        self.out = os.path.join(self.dir, "d.snp")

    def test_a_delta_that_changes_a_link_and_carries_the_pair_is_written_with_a_warning(self):
        for argv in ([EXAMPLE, self.linked], [self.linked, EXAMPLE],
                     [EXAMPLE, self.linked, "--bus", "13"],
                     [EXAMPLE, self.linked, "--only", "/ch/03/mix/14"]):
            with self.subTest(argv=argv[2:] or argv):
                code, text, err = _run("snippet", *argv, "-o", self.out, "--force")
                self.assertEqual(code, 0)
                self.assertIn(f"wrote {self.out}", text)
                warning = err.strip().splitlines()
                self.assertEqual(len(warning), 1, err)
                self.assertIn("warning", warning[0])
                self.assertIn("bus 13/14", warning[0])
                self.assertIn("/config/buslink", warning[0])
                self.assertTrue(os.path.exists(self.out))

    def test_a_delta_that_leaves_the_pair_out_is_written_without_a_warning(self):
        code, _, err = _run("snippet", EXAMPLE, self.linked, "-o", self.out,
                            "--only", "/ch/01/mix")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(Scene.load(self.out).lines[1].raw, "/ch/01/mix/fader -10.0")


if __name__ == "__main__":
    unittest.main()
