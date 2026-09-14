"""watch, end to end: the command against a console on loopback that answers /node from
in-memory lines and pushes leaves when the test's script says so."""

import _thread
import contextlib
import io
import json
import os
import re
import shutil
import signal
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock

from x32scene._parsers import _build_parser
from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.osc import decode_message, encode_message
from x32scene.services.snippets import make_snippet

REF_TEXT = ('#4.0# "REF" "" %000000000 1\n'
            '/ch/01/config "Kick" 2 YEi 1\n'
            "/ch/01/eq/1 PEQ 36.0 +0.00 1.0\n"
            "/ch/01/mix ON  +6.5 ON +0 OFF   -oo\n"
            "/ch/01/mix/01 ON  +2.8 +0 PRE 0\n"
            "/ch/02/mix ON  -oo ON +0 OFF   -oo\n")
MIX_START = "/ch/01/mix ON  +6.5 ON +0 OFF   -oo"
MIX_DOWN = "/ch/01/mix ON -10.0 ON +0 OFF   -oo"
EQ_UP = "/ch/01/eq/1 PEQ 36.0 +3.00 1.0"


class WatchConsole(threading.Thread):
    """Answers /node from ``text``; after the first /xremote plays ``script``: (delay, new
    line or None, leaf addresses), or (delay, "INTERRUPT") to press Ctrl-C on the watcher.
    Pushes go only to a subscriber. A path in ``lose`` answers its first /node only, or as
    many as a mapping gives it; ``on_query`` is (path, new line, leaves), played when that
    path is first queried."""

    def __init__(self, text: str = REF_TEXT, script=(), answer: bool = True, lose=(),
                 on_query=None, reply_delay: float = 0.0):
        super().__init__(daemon=True)
        self.state = {ln.path: ln.raw for ln in Scene.parse(text).lines if ln.path.startswith("/")}
        self.lose = dict(lose) if isinstance(lose, dict) else dict.fromkeys(lose, 1)
        self.script, self.answer, self.on_query = list(script), answer, on_query
        self.answers: dict[str, int] = {}
        self.reply_delay = reply_delay
        self.received: list[str] = []
        self.asked: set[str] = set()
        self.subscriber = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                data, client = self.sock.recvfrom(65536)
            except (TimeoutError, OSError):
                continue
            addr, args = decode_message(data)
            self.received.append(addr)
            if addr == "/node":
                self._answer("/" + args[0], client)
            elif addr == "/xremote" and self.subscriber is None:
                self.subscriber = client
                threading.Thread(target=self._play, daemon=True).start()

    def _answer(self, path: str, client) -> None:
        first = path not in self.asked
        self.asked.add(path)
        if first and self.on_query and self.on_query[0] == path:
            self._change(*self.on_query[1:])
        n = self.answers.get(path, 0)
        if self.answer and path in self.state and n < self.lose.get(path, n + 1):
            self.answers[path] = n + 1
            self._halt.wait(self.reply_delay)
            self.sock.sendto(encode_message("node", [self.state[path] + "\n"]), client)

    def _change(self, new_line, leaves) -> None:
        if new_line:
            self.state[new_line.split(" ", 1)[0]] = new_line
        for leaf in leaves if self.subscriber else ():
            self.sock.sendto(encode_message(leaf, [0.5]), self.subscriber)

    def _play(self):
        for delay, *step in self.script:
            self._halt.wait(delay)
            if step[0] == "INTERRUPT":
                _thread.interrupt_main()
                continue
            self._change(*step)

    def stop(self):
        self._halt.set()
        self.join()
        self.sock.close()


class WatchCliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ref = os.path.join(self.tmp, "ref.scn")
        with open(self.ref, "w") as fh:
            fh.write(REF_TEXT)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # interrupt_main does nothing while SIGINT is ignored, as in a backgrounded shell
        self.addCleanup(signal.signal, signal.SIGINT,
                        signal.signal(signal.SIGINT, signal.default_int_handler))

    def watch(self, console, *argv):
        out, err = io.StringIO(), io.StringIO()
        console.start()
        try:
            with mock.patch.object(O, "X32_PORT", console.port), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(["watch", self.ref, "--ip", "127.0.0.1", "--timeout", "0.2", *argv])
        finally:
            console.stop()
        return rc, out.getvalue(), err.getvalue()


class WatchTextTest(WatchCliBase):
    def test_a_change_is_logged_with_its_time_and_fields_then_summarized(self):
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"] * 20),
                                       (0.3, None, ["/-stat/selidx", "/meters/0"])])
        rc, out, _ = self.watch(console, "--seconds", "1")
        self.assertEqual(rc, 0)
        logged = [ln for ln in out.splitlines() if re.match(r"^\d\d:\d\d:\d\d\.\d{3}  ", ln)]
        self.assertEqual(len(logged), 1, out)
        self.assertRegex(logged[0], r'^\d\d:\d\d:\d\d\.\d{3}  /ch/01/mix  ch 01 "Kick"  '
                                    r"fader \+6\.5 -> -10\.0$")
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
        self.assertIn("gain +0.00 -> +3.00", out.split("summary")[1])

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
                                       (0.3, MIX_START, ["/ch/01/mix/fader"]),
                                       (0.3, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, out, _ = self.watch(console, "--seconds", "1.5", "--json")
        self.assertEqual(rc, 0)
        docs = [json.loads(ln) for ln in out.splitlines()]
        self.assertEqual([d["event"] for d in docs], ["change", "change", "change", "summary"])
        first = docs[0]
        self.assertRegex(first["time"], r"^\d\d:\d\d:\d\d\.\d{3}$")
        self.assertEqual((first["path"], first["before"], first["after"]),
                         ("/ch/01/mix", MIX_START, MIX_DOWN))
        self.assertEqual(first["fields"], [{"name": "fader", "before": "+6.5", "after": "-10.0"}])
        summary = docs[-1]
        self.assertEqual((summary["logged"], summary["transient"], summary["ignored"]), (3, 1, 0))
        self.assertEqual(summary["unanswered"], [])
        self.assertEqual([c["path"] for c in summary["net"]], ["/ch/01/eq/1"])
        self.assertIsNone(summary["snippet"])


class WatchSnippetTest(WatchCliBase):
    def test_the_snippet_is_make_snippet_of_start_and_end(self):
        out_snp = os.path.join(self.tmp, "rehearsal.snp")
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (0.2, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--snippet", out_snp)
        self.assertEqual(rc, 0)
        start = Scene.parse(REF_TEXT)
        end = Scene.parse(REF_TEXT.replace(MIX_START, MIX_DOWN).replace(
            "/ch/01/eq/1 PEQ 36.0 +0.00 1.0", EQ_UP))
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
            self.assertIn("/ch/01/eq/1 PEQ 36.0 +3.00 1.0", fh.read())

    def test_no_net_change_writes_nothing_and_says_so(self):
        out_snp = os.path.join(self.tmp, "none.snp")
        console = WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (0.3, MIX_START, ["/ch/01/mix/fader"])])
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
