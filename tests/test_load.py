"""`load`: a scene or snippet onto the running desk, written and read back until it holds."""
import contextlib
import io
import os
import shutil
import socket
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.load import load_scene

BASE = """\
#4.0# "LOADTEST" "" %000000000 1
/ch/01/config "Kick" 1 YE 1
/ch/01/mix ON   -6.0 ON +0 OFF   -oo
/ch/01/mix/01 ON  -3.0 +0 PRE 0
/ch/01/mix/02 ON  -3.0
/ch/01/eq/1 PEQ 100.0 +0.00 2.0
/headamp/000 +20.0 OFF
/fx/1 HALL MIX13 MIX13
/fx/1/par 0.5 0.5 0.5 0.5
"""


def edited(**lines: str) -> str:
    """BASE with each given path's line replaced (``ch_01_mix_01`` names ``/ch/01/mix/01``)."""
    out = []
    for raw in BASE.splitlines():
        path = raw.split(" ", 1)[0]
        key = path.strip("/").replace("/", "_")
        out.append(lines.pop(key, raw))
    return "\n".join(out + list(lines.values())) + "\n"


class Desk(threading.Thread):
    """Holds scene lines, answers ``/node`` from them and stores a ``/`` root write.

    ``drop_writes``: paths whose first root write is ignored. ``snap``: path -> the line the
    desk stores instead (its grid). ``mute_after_write``: how many ``/node`` replies to lose
    for a path once it has been written. ``mute_first_read``: paths whose first read (two
    asks) gets no reply. ``lacks``: paths the desk has no node for.
    """

    def __init__(self, text: str = BASE, *, drop_writes=(), snap=None, mute_after_write=0,
                 mute_first_read=(), lacks=()):
        super().__init__(daemon=True)
        self.lines = {ln.path: ln.raw for ln in Scene.parse(text).lines if ln.path.startswith("/")}
        self.lacks = set(lacks)      # nodes this firmware has not: never answered, never stored
        self.writes: list[str] = []
        self.drop = dict.fromkeys(drop_writes, 1)
        self.snap = snap or {}
        self.mute_after_write = mute_after_write
        self.muted: dict[str, int] = dict.fromkeys(mute_first_read, 2)   # both asks of a read
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.05)
        self.port = self.sock.getsockname()[1]
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                data, client = self.sock.recvfrom(65536)
            except (TimeoutError, OSError):
                continue
            addr, args = O.decode_message(data)
            if addr == "/node":
                path = "/" + args[0]
                if self.muted.get(path):
                    self.muted[path] -= 1
                elif path in self.lines:
                    self.sock.sendto(O.encode_message("node", [self.lines[path] + "\n"]), client)
            elif addr == "/":
                raw = str(args[0])
                path = raw.split(" ", 1)[0]
                self.writes.append(raw)
                if path in self.lacks:
                    continue
                if self.drop.get(path):
                    self.drop[path] -= 1
                    continue
                self.lines[path] = self.snap.get(path, raw)
                self.muted.setdefault(path, self.mute_after_write)   # the first write arms it

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self._halt.set()
        self.join()
        self.sock.close()


MIX_DOWN = "/ch/01/mix/01 ON  -9.0 +0 PRE 0"
GAIN_UP = "/headamp/000 +25.0 OFF"


class LoadServiceTest(unittest.TestCase):
    def load(self, desk: Desk, text: str, **kw):
        kw.setdefault("sleep", lambda s: None)
        return load_scene(Scene.parse(text), "127.0.0.1", port=desk.port, timeout=0.2, **kw)

    def test_writes_only_the_lines_the_desk_does_not_hold(self):
        with Desk() as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP))
        self.assertEqual(r.passes, [["/ch/01/mix/01", "/headamp/000"]])
        self.assertEqual((r.ok, r.stuck, r.unanswered, r.written), (True, [], [], 2))
        self.assertEqual(desk.writes, [MIX_DOWN, GAIN_UP])   # no header, nothing unchanged
        self.assertEqual(desk.lines["/ch/01/mix/01"], MIX_DOWN)

    def test_a_desk_already_holding_the_file_gets_no_write(self):
        with Desk() as desk:
            r = self.load(desk, BASE)
        self.assertEqual((r.passes, r.ok, desk.writes), ([], True, []))

    def test_padding_is_the_desks_own_and_not_a_difference(self):
        with Desk() as desk:
            r = self.load(desk, edited(ch_01_mix_02="/ch/01/mix/02 ON -3.0"))
        self.assertEqual((r.passes, desk.writes), ([], []))

    def test_a_write_the_desk_drops_is_written_again_next_pass(self):
        with Desk(drop_writes=["/ch/01/mix/01"]) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP))
        self.assertEqual(r.passes, [["/ch/01/mix/01", "/headamp/000"], ["/ch/01/mix/01"]])
        self.assertTrue(r.ok)
        self.assertEqual(desk.lines["/ch/01/mix/01"], MIX_DOWN)

    def test_a_value_the_desk_snaps_is_reported_after_the_last_pass(self):
        want = "/ch/01/eq/1 PEQ 200.0 +0.00 2.0"
        held = "/ch/01/eq/1 PEQ 202.3 +0.00 2.0"
        with Desk(snap={"/ch/01/eq/1": held}) as desk:
            r = self.load(desk, edited(ch_01_eq_1=want, headamp_000=GAIN_UP), passes=2)
        self.assertEqual(r.passes, [["/ch/01/eq/1", "/headamp/000"], ["/ch/01/eq/1"]])
        self.assertFalse(r.ok)
        self.assertEqual([(c.path, c.before, c.after) for c in r.stuck],
                         [("/ch/01/eq/1", want, held)])
        self.assertEqual(r.unanswered, [])

    def test_a_path_the_desk_never_answers_is_written_once_and_named_unverified(self):
        ghost = '/ch/33/config "Ghost" 1 YE 33'
        with Desk(drop_writes=["/ch/01/mix/01"], lacks=["/ch/33/config"]) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, extra=ghost))
        self.assertEqual(r.passes, [["/ch/01/mix/01", "/ch/33/config"], ["/ch/01/mix/01"]])
        self.assertEqual((r.ok, r.stuck, r.unanswered), (False, [], ["/ch/33/config"]))
        self.assertEqual(desk.writes, [MIX_DOWN, ghost, MIX_DOWN])

    def test_a_path_silent_at_the_start_that_answers_once_written_is_verified(self):
        # a lost /node reply on the first read must not leave the line unwritten
        with Desk(edited(extra="/ch/01/mix/fader   -6.0"), mute_first_read=["/ch/01/mix/fader"]) as desk:
            r = self.load(desk, edited(extra="/ch/01/mix/fader -20.0"))
        self.assertEqual(r.passes, [["/ch/01/mix/fader"]])
        self.assertEqual((r.ok, r.unanswered), (True, []))
        self.assertEqual(desk.lines["/ch/01/mix/fader"], "/ch/01/mix/fader -20.0")

    def test_each_pass_writes_slower_than_the_last(self):
        naps = []
        with Desk(drop_writes=["/ch/01/mix/01"]) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP),
                          sleep=naps.append)
        self.assertEqual([len(p) for p in r.passes], [2, 1])
        gap1, _, _, gap2 = naps[:4]      # write, write, read-back settle, write
        self.assertEqual(gap2, 2 * gap1)

    def test_a_reply_lost_on_the_read_back_is_asked_again_next_pass(self):
        # two lost replies: the read-back asks twice per pass, so the path carries over
        with Desk(mute_after_write=2) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN))
        self.assertEqual(r.passes, [["/ch/01/mix/01"], ["/ch/01/mix/01"]])
        self.assertEqual((r.ok, r.unanswered), (True, []))

    def test_a_path_never_read_back_is_unanswered_not_stuck_and_not_ok(self):
        with Desk(mute_after_write=99) as desk:
            r = self.load(desk, edited(ch_01_mix_01=MIX_DOWN), passes=2)
        self.assertEqual(r.passes, [["/ch/01/mix/01"], ["/ch/01/mix/01"]])
        self.assertEqual((r.ok, r.stuck, r.unanswered), (False, [], ["/ch/01/mix/01"]))

    def test_an_fx_type_line_settles_before_its_parameters_follow(self):
        naps = []
        text = edited(fx_1="/fx/1 PLAT MIX13 MIX13", fx_1_par="/fx/1/par 0.1 0.2 0.3 0.4")
        with Desk() as desk:
            r = self.load(desk, text, sleep=naps.append)
        self.assertEqual(r.passes, [["/fx/1", "/fx/1/par"]])
        self.assertEqual(desk.writes[0].split()[0], "/fx/1")
        self.assertGreaterEqual(naps[0], 0.5)       # after the type line
        self.assertLess(naps[1], 0.5)               # after the par line

    def test_a_snippet_loads_its_split_lines(self):
        snip = ('#4.0# "SNIP" 6910 -1 50397183 0 1\n'
                "/ch/01/mix/fader -20.0\n/ch/01/mix/pan +0\n")
        with Desk(edited(extra="/ch/01/mix/fader   -6.0", extra2="/ch/01/mix/pan +0")) as desk:
            r = self.load(desk, snip)
        self.assertEqual(r.passes, [["/ch/01/mix/fader"]])
        self.assertEqual(desk.lines["/ch/01/mix/fader"], "/ch/01/mix/fader -20.0")

    def test_a_desk_that_never_answers_raises(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
            silent.bind(("127.0.0.1", 0))
            with self.assertRaises(O.OscError):
                load_scene(Scene.parse(BASE), "127.0.0.1", port=silent.getsockname()[1],
                           timeout=0.1, sleep=lambda s: None)


class LoadCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def file(self, name: str, text: str) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def run_load(self, desk: Desk, path: str, *argv):
        out, err = io.StringIO(), io.StringIO()
        with desk, mock.patch.object(O, "X32_PORT", desk.port), \
             mock.patch("x32scene.services.load.time.sleep", lambda s: None), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["load", path, "--ip", "127.0.0.1", "--timeout", "0.2", *argv])
        return rc, out.getvalue(), err.getvalue()

    def test_reports_each_pass_the_result_and_the_head_amps_it_wrote(self):
        path = self.file("a.scn", edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP))
        rc, out, err = self.run_load(Desk(drop_writes=["/ch/01/mix/01"]), path)
        self.assertEqual(rc, 0, err)
        self.assertIn("pass 1: 2 line(s) written", out)
        self.assertIn("pass 2: 1 line(s) written", out)
        self.assertIn("the desk holds a.scn: 3 line(s) written in 2 pass(es)", out)
        self.assertIn("head amps written: /headamp/000 +25.0 OFF", out)
        self.assertNotIn("unanswered", err)

    def test_a_desk_already_holding_the_file_says_so(self):
        path = self.file("a.scn", BASE)
        rc, out, _ = self.run_load(Desk(), path)
        self.assertEqual(rc, 0)
        self.assertIn("the desk already holds a.scn: nothing written", out)
        self.assertNotIn("head amps", out)

    def test_a_value_the_desk_will_not_take_exits_1_and_shows_both_lines(self):
        want = "/ch/01/eq/1 PEQ 200.0 +0.00 2.0"
        held = "/ch/01/eq/1 PEQ 202.3 +0.00 2.0"
        path = self.file("a.scn", edited(ch_01_eq_1=want))
        rc, out, _ = self.run_load(Desk(snap={"/ch/01/eq/1": held}), path, "--passes", "2")
        self.assertEqual(rc, 1)
        self.assertIn("1 path(s) the desk answers with another value after 2 pass(es):", out)
        self.assertIn(f"    - {want}", out)
        self.assertIn(f"    + {held}", out)

    def test_a_path_never_read_back_exits_1_and_is_named(self):
        path = self.file("a.scn", edited(extra='/ch/33/config "Ghost" 1 YE 33'))
        rc, out, err = self.run_load(Desk(lacks=["/ch/33/config"]), path)
        self.assertEqual(rc, 1)
        self.assertIn("pass 1: 1 line(s) written", out)
        self.assertIn("1 path(s) not read back, so not verified: /ch/33/config", out)
        self.assertNotIn("the desk holds", out)

    def test_ctrl_c_after_a_write_says_the_desk_may_be_half_written(self):
        path = self.file("a.scn", edited(ch_01_mix_01=MIX_DOWN, headamp_000=GAIN_UP))
        out, err = io.StringIO(), io.StringIO()
        desk = Desk()

        def interrupt_after_first_write(s):   # the first sleep follows the first write
            raise KeyboardInterrupt
        with desk, mock.patch.object(O, "X32_PORT", desk.port), \
             mock.patch("x32scene.services.load.time",
                        types.SimpleNamespace(sleep=interrupt_after_first_write)), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["load", path, "--ip", "127.0.0.1", "--timeout", "0.2"])
            for _ in range(40):   # let the desk thread log the datagram
                if desk.writes:
                    break
                time.sleep(0.05)
        self.assertEqual(rc, 130)
        self.assertIn("the desk may hold part of a.scn; run load again", err.getvalue())
        self.assertIn("pass 1: 1 line(s) written", out.getvalue())
        self.assertEqual(desk.writes, [MIX_DOWN])

    def test_passes_must_be_a_whole_number_from_1_to_10(self):
        from x32scene._parsers import _build_parser
        for bad in ("0", "11", "two", "1.5"):
            with self.subTest(passes=bad), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _build_parser(None).parse_args(["load", "a.scn", "--passes", bad])
        self.assertEqual(_build_parser(None).parse_args(["load", "a.scn", "--passes", "10"]).passes, 10)

    def test_json_carries_the_passes_the_stuck_lines_and_the_unanswered(self):
        import json
        want = "/ch/01/eq/1 PEQ 200.0 +0.00 2.0"
        held = "/ch/01/eq/1 PEQ 202.3 +0.00 2.0"
        path = self.file("a.scn", edited(ch_01_eq_1=want, headamp_000=GAIN_UP,
                                         extra='/ch/33/config "Ghost" 1 YE 33'))
        rc, out, _ = self.run_load(Desk(snap={"/ch/01/eq/1": held}, lacks=["/ch/33/config"]),
                                   path, "--passes", "2", "--json")
        self.assertEqual(rc, 1)
        doc = json.loads(out)
        self.assertEqual(doc["file"], path)
        self.assertEqual(doc["ok"], False)
        self.assertEqual(doc["passes"], [["/ch/01/eq/1", "/headamp/000", "/ch/33/config"],
                                         ["/ch/01/eq/1"]])
        self.assertEqual(doc["written"], 4)
        self.assertEqual(doc["stuck"], [{"path": "/ch/01/eq/1", "before": want, "after": held}])
        self.assertEqual(doc["unanswered"], ["/ch/33/config"])

    def test_a_snippet_is_loaded(self):
        path = self.file("mix.snp", '#4.0# "SNIP" 6910 -1 50397183 0 1\n/ch/01/mix/fader -20.0\n')
        desk = Desk(edited(extra="/ch/01/mix/fader   -6.0"))
        rc, out, err = self.run_load(desk, path)
        self.assertEqual(rc, 0, err)
        self.assertEqual(desk.lines["/ch/01/mix/fader"], "/ch/01/mix/fader -20.0")

    def test_presets_and_shows_are_refused_before_the_desk_is_touched(self):
        files = {"p.chn": '#4.0# 1 "Kick" 0 %0000000000000000 1\n/eq/1 PEQ 100.0 +0.00 2.0\n',
                 "p.efx": '#4.0# 1 "Verb" 1 5 1\ntype HALL\n',
                 "p.rou": '#4.0# 1 "Local" 2 0 1\n/config/routing/IN AN1-8 AN9-16 AN17-24 AN25-32\n',
                 "s.shw": '#4.0#\nshow "S" 0 0 0 0 0 0 0 0 0 0 "x"\n',
                 "preset-in-scn.scn": '#4.0# 1 "Kick" 0 %0000000000000000 1\n/eq/1 PEQ 100.0 +0.00 2.0\n'}
        for name, text in files.items():
            with self.subTest(name=name):
                desk = Desk()
                rc, out, err = self.run_load(desk, self.file(name, text))
                self.assertEqual(rc, 1)
                self.assertEqual(desk.writes, [])
                self.assertIn("load takes a scene or a snippet", err)

    def test_a_desk_that_does_not_answer_exits_2(self):
        path = self.file("a.scn", BASE)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
            silent.bind(("127.0.0.1", 0))
            err = io.StringIO()
            with mock.patch.object(O, "X32_PORT", silent.getsockname()[1]), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc = main(["load", path, "--ip", "127.0.0.1", "--timeout", "0.1"])
        self.assertEqual(rc, 2)
        self.assertIn("load failed:", err.getvalue())

    def test_without_an_ip_it_fails_cleanly(self):
        path = self.file("a.scn", BASE)
        with mock.patch.dict(os.environ):
            os.environ.pop("X32SCENE_IP", None)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["load", path]), 1)


if __name__ == "__main__":
    unittest.main()
