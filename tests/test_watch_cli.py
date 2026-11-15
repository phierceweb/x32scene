"""watch, end to end: the command against a console on loopback that answers /node from
in-memory lines and pushes leaves when the test's script says so."""

import contextlib
import io
import json
import os
import re
import signal
import time
import unittest
from unittest import mock

from tests.watch_console import (EQ_UP, MIX_DOWN, MIX_START, READ_BACK, REF_TEXT, WatchCliBase,
                                 WatchConsole)
from x32scene._parsers import _build_parser
from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services.snippets import make_snippet


class WatchTextTest(WatchCliBase):
    def test_a_change_is_logged_with_its_time_and_fields_then_summarized(self):
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"] * 20),
                                       (0.3, None, ["/-stat/selidx", "/meters/0"])])
        rc, out, _ = self.watch(console, "--seconds", "1")
        self.assertEqual(rc, 0)
        logged = [ln for ln in out.splitlines() if re.match(r"^\d\d:\d\d:\d\d\.\d{3}  ", ln)]
        self.assertEqual(len(logged), 1, out)
        self.assertRegex(logged[0], r'^\d\d:\d\d:\d\d\.\d{3}  /ch/01/mix  ch 01 "Kick"  '
                                    r"fader -4\.8 -> -10\.0$")
        self.assertIn("1 change(s) logged", out)
        self.assertIn("2 message(s) ignored", out)
        self.assertIn("1 changed path(s):", out)
        self.assertEqual(set(console.received), {"/node", "/xremote"})

    def test_ctrl_c_ends_the_watch_with_the_summary(self):
        console = WatchConsole(script=[(0.1, EQ_UP, ["/ch/01/eq/1/g"]), (0.5, "INTERRUPT")])
        started = time.monotonic()
        rc, out, err = self.watch(console, "--seconds", "20")
        self.assertLess(time.monotonic() - started, 3)   # no wait outlives the interrupt
        self.assertEqual(rc, 0)
        self.assertNotIn("Traceback", err)
        self.assertIn("1 change(s) logged", out)
        self.assertIn("gain +4.75 -> +7.75", out.split("summary")[1])

    def test_a_silent_desk_fails_the_start_snapshot(self):
        rc, out, err = self.watch(WatchConsole(answer=False), "--seconds", "1")
        self.assertEqual(rc, 2)
        self.assertIn("watch failed", err)
        self.assertEqual(out, "")

    def test_needs_an_ip(self):
        with mock.patch.dict(os.environ, {"X32SCENE_IP": ""}), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["watch", self.ref]), 1)


class WatchJsonTest(WatchCliBase):
    def test_json_lines_one_per_change_then_the_summary(self):
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (READ_BACK, MIX_START, ["/ch/01/mix/fader"]),
                                       (READ_BACK, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, out, _ = self.watch(console, "--seconds", "1.5", "--json")
        self.assertEqual(rc, 0)
        docs = [json.loads(ln) for ln in out.splitlines()]
        self.assertEqual([d["event"] for d in docs], ["change", "change", "change", "summary"])
        first = docs[0]
        self.assertRegex(first["time"], r"^\d\d:\d\d:\d\d\.\d{3}$")
        self.assertEqual((first["path"], first["before"], first["after"]),
                         ("/ch/01/mix", MIX_START, MIX_DOWN))
        self.assertEqual(first["fields"], [{"name": "fader", "before": "-4.8", "after": "-10.0"}])
        summary = docs[-1]
        self.assertEqual((summary["logged"], summary["transient"], summary["ignored"]), (3, 1, 0))
        self.assertEqual(summary["unanswered"], [])
        self.assertEqual([c["path"] for c in summary["net"]], ["/ch/01/eq/1"])
        self.assertIsNone(summary["snippet"])


class WatchSnippetTest(WatchCliBase):
    def test_the_snippet_is_make_snippet_of_start_and_end(self):
        out_snp = os.path.join(self.tmp, "rehearsal.snp")
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (READ_BACK, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--snippet", out_snp)
        self.assertEqual(rc, 0)
        start = Scene.parse(REF_TEXT)
        end = Scene.parse(REF_TEXT.replace(MIX_START, MIX_DOWN).replace(
            "/ch/01/eq/1 PEQ 52.6 +4.75 1.6", EQ_UP))
        with open(out_snp) as fh:
            self.assertEqual(fh.read(), make_snippet(start, end, "rehearsal").scene.dump())
        self.assertIn(f"wrote {out_snp}", out)

    def test_an_existing_snippet_is_refused_before_the_watch_starts(self):
        out_snp = os.path.join(self.tmp, "taken.snp")
        with open(out_snp, "w") as fh:
            fh.write("keep me\n")
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"])])
        rc, _, err = self.watch(console, "--seconds", "1", "--snippet", out_snp)
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err)
        self.assertEqual(console.received, [])       # not a single query went out
        with open(out_snp) as fh:
            self.assertEqual(fh.read(), "keep me\n")

    def test_force_overwrites_an_existing_snippet(self):
        out_snp = os.path.join(self.tmp, "taken.snp")
        with open(out_snp, "w") as fh:
            fh.write("old\n")
        console = WatchConsole(script=[(0.1, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, _, _ = self.watch(console, "--seconds", "1", "--snippet", out_snp, "--force")
        self.assertEqual(rc, 0)
        with open(out_snp) as fh:
            self.assertIn("/ch/01/eq/1 PEQ 52.6 +7.75 1.6", fh.read())

    def test_no_net_change_writes_nothing_and_says_so(self):
        out_snp = os.path.join(self.tmp, "none.snp")
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (READ_BACK, MIX_START, ["/ch/01/mix/fader"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--snippet", out_snp)
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(out_snp))
        self.assertIn(f"no net change; nothing written to {out_snp}", out)
        self.assertIn("1 path(s) changed and came back", out)


class CtrlCTestHarnessTest(unittest.TestCase):
    def test_the_base_restores_ctrl_c_when_sigint_starts_ignored(self):
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        self.addCleanup(signal.signal, signal.SIGINT, previous)
        base = WatchCliBase()
        base.setUp()
        self.assertIs(signal.getsignal(signal.SIGINT), signal.default_int_handler)
        base.doCleanups()
        self.assertIs(signal.getsignal(signal.SIGINT), signal.SIG_IGN)


class WatchSecondsBoundTest(unittest.TestCase):
    def parse(self, value):
        with contextlib.redirect_stderr(io.StringIO()):
            return _build_parser(None).parse_args(
                ["watch", "ref.scn", "--ip", "10.0.0.1", "--seconds", value]).seconds

    def test_seconds_is_bounded_to_twelve_hours(self):
        for bad in ("0", "-1", "inf", "nan", "43201", "soon"):
            with self.subTest(value=bad):
                with self.assertRaises(SystemExit):
                    self.parse(bad)
        self.assertEqual(self.parse("43200"), 43200.0)
        self.assertEqual(self.parse("0.5"), 0.5)

    def test_zero_is_refused_with_a_message_that_says_so(self):
        for argv, what in ((["watch", "ref.scn", "--seconds", "0"], "seconds"),
                           (["meters", "--seconds", "0"], "seconds"),
                           (["desk", "--timeout", "0"], "timeout")):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                    _build_parser(None).parse_args([*argv, "--ip", "10.0.0.1"])
                self.assertRegex(err.getvalue(), rf": {what} must be greater than 0 and at most "
                                                 r"\d+ seconds, got 0\n")

    def test_no_seconds_watches_until_stopped(self):
        args = _build_parser(None).parse_args(["watch", "ref.scn", "--ip", "10.0.0.1"])
        self.assertIsNone(args.seconds)


if __name__ == "__main__":
    unittest.main()
