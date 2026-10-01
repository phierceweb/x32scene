"""`load` against a desk that mirrors, resets or goes silent: every path is read back after
each pass, a silent desk is probed before any write however few lines there are, a desk that
stops answering or a failed send keeps the passes written, and the files it must not put on a
desk are refused."""

import contextlib
import errno
import io
import json
import os
import shutil
import socket
import tempfile
import unittest
from unittest import mock

from tests.test_load import BASE, Desk, edited
from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.load import load_scene

MIRROR = {"/ch/01/mix/01": "/ch/01/mix/02", "/ch/01/mix/02": "/ch/01/mix/01"}


class FaultyDesk(Desk):
    """``mirror``: a root write to one path copies its on and level to its partner (the desk
    on a linked bus pair). ``fx_reset``: a write to /fx/1 puts /fx/1/par back to ``reset``.
    ``dead_after_start``: answer the first ``answers`` /node replies, then nothing.
    ``silent_after_write``: answer no /node once a root write has arrived."""

    def __init__(self, text=BASE, *, mirror=None, fx_reset=None, dead_after_start=None,
                 silent_after_write=False, **kw):
        super().__init__(text, **kw)
        self.mirror, self.fx_reset = mirror or {}, fx_reset
        self.answers_left, self.silent_after_write = dead_after_start, silent_after_write
        self.silenced = False

    def run(self):
        while not self._halt.is_set():
            try:
                data, client = self.sock.recvfrom(65536)
            except (TimeoutError, OSError):
                continue
            addr, args = O.decode_message(data)
            if addr == "/node":
                path = "/" + args[0]
                if self.silenced or self.answers_left == 0:
                    continue
                if self.answers_left is not None:
                    self.answers_left -= 1
                if path in self.lines:
                    self.sock.sendto(O.encode_message("node", [self.lines[path] + "\n"]), client)
            elif addr == "/":
                raw = str(args[0])
                path = raw.split(" ", 1)[0]
                self.writes.append(raw)
                if self.silent_after_write:
                    self.silenced = True
                if path in self.lacks:
                    continue
                if self.drop.get(path):
                    self.drop[path] -= 1
                    continue
                self.lines[path] = raw
                if path in self.mirror:
                    partner = self.mirror[path]
                    on, level = raw.split()[1:3]
                    rest = self.lines[partner].split()[3:]
                    self.lines[partner] = " ".join([partner, on, level, *rest])
                if path == "/fx/1" and self.fx_reset:
                    self.lines["/fx/1/par"] = self.fx_reset


def load(desk, text, **kw):
    kw.setdefault("sleep", lambda s: None)
    return load_scene(Scene.parse(text), "127.0.0.1", port=desk.port, timeout=0.2, **kw)


class ReadBackEveryPathTest(unittest.TestCase):
    def test_a_linked_pair_whose_sides_differ_is_reported_stuck_not_held(self):
        text = edited(ch_01_mix_01="/ch/01/mix/01 ON -10.0 +0 PRE 0",
                      ch_01_mix_02="/ch/01/mix/02 ON -20.0")
        with FaultyDesk(mirror=MIRROR) as desk:
            r = load(desk, text, passes=3)
        self.assertFalse(r.ok)   # the pair chases itself; one side is left stuck and named
        self.assertTrue({c.path for c in r.stuck} <= {"/ch/01/mix/01", "/ch/01/mix/02"})
        self.assertTrue(r.stuck)

    def test_a_one_sided_edit_the_desk_mirrors_onto_its_partner_is_reported(self):
        text = edited(ch_01_mix_01="/ch/01/mix/01 ON -10.0 +0 PRE 0")   # /mix/02 stays -3.0
        with FaultyDesk(mirror=MIRROR) as desk:
            r = load(desk, text)
        self.assertFalse(r.ok)
        self.assertEqual([c.path for c in r.stuck], ["/ch/01/mix/02"])

    def test_a_lost_fx_type_write_resent_later_does_not_leave_its_parameters_reset(self):
        text = edited(fx_1="/fx/1 PLAT MIX13 MIX13", fx_1_par="/fx/1/par 0.1 0.2 0.3 0.4")
        with FaultyDesk(drop_writes=["/fx/1"], fx_reset="/fx/1/par 0 0 0 0") as desk:
            r = load(desk, text, passes=3)
            self.assertTrue(r.ok, (r.stuck, r.unanswered))
            self.assertEqual(desk.lines["/fx/1/par"], "/fx/1/par 0.1 0.2 0.3 0.4")
        self.assertEqual(r.passes[1], ["/fx/1"])
        self.assertEqual(r.passes[2], ["/fx/1/par"])


class SilentDeskTest(unittest.TestCase):
    def test_a_two_line_file_never_writes_to_a_silent_address(self):
        text = '#4.0# "S" 6910 -1 50397183 0 1\n/ch/01/mix/fader -20.0\n/ch/01/mix/on OFF\n'
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
            silent.bind(("127.0.0.1", 0))
            silent.settimeout(0.3)
            with self.assertRaises(O.OscError):
                load_scene(Scene.parse(text), "127.0.0.1", port=silent.getsockname()[1],
                           timeout=0.1, sleep=lambda s: None)
            writes = []
            with contextlib.suppress(TimeoutError, OSError):
                while True:
                    data, _ = silent.recvfrom(65536)
                    addr, _ = O.decode_message(data)
                    writes.append(addr)
        self.assertNotIn("/", writes)

    def test_a_desk_that_stops_answering_after_the_writes_keeps_them_in_the_result(self):
        text = edited(ch_01_mix_01="/ch/01/mix/01 ON -9.0 +0 PRE 0", headamp_000="/headamp/000 +25.0 OFF")
        with FaultyDesk(silent_after_write=True) as desk:
            r = load(desk, text)
        self.assertEqual(r.passes, [["/ch/01/mix/01", "/headamp/000"]])
        self.assertIn("desk off or unreachable", r.error)
        self.assertFalse(r.ok)

    def test_a_failed_send_keeps_the_lines_already_written(self):
        text = edited(ch_01_mix_01="/ch/01/mix/01 ON -9.0 +0 PRE 0", headamp_000="/headamp/000 +25.0 OFF")
        real = socket.socket.sendto
        sent = {"n": 0}

        def failing(self, data, addr):
            if O.decode_message(data)[0] == "/":
                sent["n"] += 1
                if sent["n"] == 2:
                    raise OSError(errno.EHOSTUNREACH, "No route to host")
            return real(self, data, addr)
        with FaultyDesk() as desk, mock.patch.object(socket.socket, "sendto", failing):
            r = load(desk, text)
        self.assertIn("No route to host", r.error)
        self.assertEqual(r.passes, [["/ch/01/mix/01"]])


class LoadCliReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def file(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", newline="") as fh:
            fh.write(text)
        return path

    def run_load(self, desk, path, *argv):
        out, err = io.StringIO(), io.StringIO()
        with desk, mock.patch.object(O, "X32_PORT", desk.port), \
             mock.patch("x32scene.services.load.time.sleep", lambda s: None), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["load", path, "--ip", "127.0.0.1", "--timeout", "0.2", *argv])
        return rc, out.getvalue(), err.getvalue(), desk.writes

    def test_a_desk_gone_after_the_writes_exits_2_naming_what_went_out(self):
        path = self.file("a.scn", edited(ch_01_mix_01="/ch/01/mix/01 ON -9.0 +0 PRE 0",
                                         headamp_000="/headamp/000 +25.0 OFF"))
        rc, out, err, _ = self.run_load(FaultyDesk(silent_after_write=True), path)
        self.assertEqual(rc, 2)
        self.assertIn("pass 1: 2 line(s) written", out)
        self.assertIn("head amps written: /headamp/000 +25.0 OFF", out)
        self.assertIn("the desk may hold part of a.scn", err)
        rc, out, _, _ = self.run_load(FaultyDesk(silent_after_write=True), path, "--json")
        self.assertEqual(rc, 2)
        self.assertIn('"error":', out)

    def test_ctrl_c_during_the_start_pull_says_nothing_was_written(self):
        path = self.file("a.scn", edited(ch_01_mix_01="/ch/01/mix/01 ON -9.0 +0 PRE 0"))
        with mock.patch("x32scene.services.load.osc.pull_scene_like", side_effect=KeyboardInterrupt):
            rc, out, err, writes = self.run_load(FaultyDesk(), path)
        self.assertEqual(rc, 130)
        self.assertIn("stopped before anything was written", err)
        self.assertNotIn("may hold part", err)
        self.assertEqual(writes, [])

    def test_files_load_must_not_send_are_refused_before_the_desk_is_touched(self):
        cases = {"header-only.snp": '#4.0# "S" 6910 -1 50397183 0 1\n',
                 "slashless.scn": BASE.replace("/ch/01/eq/1 ", "ch/01/eq/1 "),
                 "cut.scn": BASE[:-1] + "/headamp/001 +2"}
        for name, text in cases.items():
            with self.subTest(file=name):
                rc, out, err, writes = self.run_load(FaultyDesk(), self.file(name, text))
                self.assertEqual(rc, 1, err)
                self.assertEqual(writes, [])
                self.assertNotIn("holds", out)

    def test_unanswered_paths_keep_their_leading_slash_in_json_and_text(self):
        path = self.file("a.scn", edited(ch_33_config='/ch/33/config "x" 1 YE 33'))
        rc, out, _, _ = self.run_load(FaultyDesk(lacks=["/ch/33/config"]), path, "--json")
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)["unanswered"], ["/ch/33/config"])
        rc, out, _, _ = self.run_load(FaultyDesk(lacks=["/ch/33/config"]), path)
        self.assertIn("not verified: /ch/33/config", out)


if __name__ == "__main__":
    unittest.main()
