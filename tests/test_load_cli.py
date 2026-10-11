"""The `load` command: what it prints, its exit codes, and what it refuses."""
import contextlib
import io
import os
import shutil
import socket
import tempfile
import time
import types
import unittest
from unittest import mock

from tests.load_desk import BASE, GAIN_UP, MIX_DOWN, Desk, edited
from x32scene.cli import main
from x32scene.services import osc as O


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
