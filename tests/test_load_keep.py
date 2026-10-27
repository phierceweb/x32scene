"""`load --keep-bus` and `--keep`: the lines left as the desk holds them, the link changes
refused around them, and a kept line the desk moves anyway."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.load_desk import Desk, edited
from x32scene.services import load as L
from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.load import load_scene
from x32scene.services.load_keep import Keep

BASE = """\
#4.0# "KEEPTEST" "" %000000000 1
/config/chlink OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF
/config/auxlink OFF OFF OFF OFF
/config/fxlink OFF OFF OFF OFF
/config/buslink OFF OFF OFF OFF OFF OFF ON OFF
/config/mtxlink OFF OFF OFF
/config/linkcfg ON ON ON ON
/ch/01/config "Kick" 1 YE 1
/ch/01/mix/13 ON  -3.0 +0 PRE 0
/ch/01/mix/14 ON  -3.0
/ch/01/mix/15 ON  -9.0 +0 PRE 0
/ch/01/eq/1 PEQ 100.0 +0.00 2.0
/bus/13/config "Plate" 71 RD
/bus/13/mix ON   0.0 OFF +0 OFF   -oo
/bus/14/config "Room" 71 GN
/bus/14/mix ON   0.0 OFF +0 OFF   -oo
/bus/15/config "Slap" 71 YE
/bus/15/mix ON   0.0 OFF +0 OFF   -oo
"""
MIX13 = "/ch/01/mix/13 ON -20.0 +0 PRE 0"
MIX14 = "/ch/01/mix/14 ON -20.0"
EQ = "/ch/01/eq/1 PEQ 200.0 +3.00 2.0"
BUS13 = '/bus/13/config "Verb" 71 RD'
PAIR_13_14 = ["/ch/01/mix/13", "/ch/01/mix/14", "/bus/13/config", "/bus/13/mix",
              "/bus/14/config", "/bus/14/mix"]


def changed(**lines):
    return edited(BASE, **lines)


def without(text: str, path: str) -> str:
    return "".join(ln for ln in text.splitlines(True) if not ln.startswith(path + " "))


class KeepServiceTest(unittest.TestCase):
    def load(self, desk: Desk, text: str, **kw):
        kw.setdefault("sleep", lambda s: None)
        return load_scene(Scene.parse(text), "127.0.0.1", port=desk.port, timeout=0.2, **kw)

    def test_keep_bus_leaves_the_mix_both_sides_and_names_it(self):
        with Desk(BASE) as desk:
            r = self.load(desk, changed(ch_01_mix_13=MIX13, ch_01_mix_14=MIX14, ch_01_eq_1=EQ,
                                        bus_13_config=BUS13), keep=Keep(buses=[13]))
        self.assertEqual(r.passes, [["/ch/01/eq/1"]])
        self.assertEqual([(w, sorted(ps)) for w, ps in r.kept], [("bus 13/14", sorted(PAIR_13_14))])
        self.assertEqual((r.ok, r.moved), (True, []))
        self.assertEqual(desk.lines["/ch/01/mix/13"], "/ch/01/mix/13 ON  -3.0 +0 PRE 0")
        self.assertEqual(desk.lines["/bus/13/config"], '/bus/13/config "Plate" 71 RD')

    def test_the_desks_link_decides_the_pair_when_the_file_has_no_link_line(self):
        text = without(changed(bus_14_config='/bus/14/config "Hall" 71 GN'), "/config/buslink")
        with Desk(BASE) as desk:
            r = self.load(desk, text, keep=Keep(buses=[13]))
        self.assertEqual((r.passes, r.ok), ([], True))
        self.assertEqual([w for w, _ in r.kept], ["bus 13/14"])
        with Desk(BASE) as desk:
            r = self.load(desk, changed(bus_15_config='/bus/15/config "Echo" 71 YE'), keep=Keep(buses=[15]))
        self.assertEqual([(w, ps) for w, ps in r.kept],
                         [("bus 15", ["/ch/01/mix/15", "/bus/15/config", "/bus/15/mix"])])

    def test_a_file_relinking_the_kept_pair_is_refused_before_any_write(self):
        text = changed(config_buslink="/config/buslink OFF OFF OFF OFF OFF OFF OFF OFF", ch_01_eq_1=EQ)
        with Desk(BASE) as desk, self.assertRaises(ValueError) as cm:
            self.load(desk, text, keep=Keep(buses=[14]))
        self.assertIn("bus 13/14 link", str(cm.exception))
        self.assertIn("keep /config/buslink too", str(cm.exception))
        self.assertEqual(desk.writes, [])

    def test_a_file_relinking_a_strip_pair_is_refused_when_the_pair_holds_a_kept_line(self):
        text = changed(config_chlink="/config/chlink ON OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF OFF")
        for keep in (Keep(buses=[13]), Keep(globs=["/ch/01/eq/*"])):
            with self.subTest(keep=keep), Desk(BASE) as desk, self.assertRaises(ValueError) as cm:
                self.load(desk, text, keep=keep)
            self.assertIn("ch 1/2 link", str(cm.exception))
            self.assertEqual(desk.writes, [])
        with Desk(BASE) as desk:
            r = self.load(desk, text, keep=Keep(globs=["/bus/13/*"]))
        self.assertEqual(r.passes, [["/config/chlink"]])

    def test_a_file_relinking_a_matrix_pair_a_kept_bus_sends_into_is_refused(self):
        base = changed(bus_13_mix_01="/bus/13/mix/01 ON   -oo -100 POST 0")
        text = edited(base, config_mtxlink="/config/mtxlink ON OFF OFF")
        with Desk(base) as desk, self.assertRaises(ValueError) as cm:
            self.load(desk, text, keep=Keep(buses=[13]))
        self.assertIn("matrix 1/2 link", str(cm.exception))
        self.assertIn("/bus/13/mix/01", str(cm.exception))
        self.assertEqual(desk.writes, [])

    def test_a_link_line_kept_itself_is_not_refused(self):
        text = changed(config_buslink="/config/buslink OFF OFF OFF OFF OFF OFF OFF OFF")
        with Desk(BASE) as desk:
            r = self.load(desk, text, keep=Keep(buses=[14], globs=["/config/buslink"]))
        self.assertEqual((r.passes, r.ok, desk.writes), ([], True, []))
        self.assertEqual([w for w, _ in r.kept], ["bus 13/14", "/config/buslink"])

    def test_a_pattern_takes_in_the_other_side_of_a_pair_the_desk_links(self):
        base = edited(BASE, config_chlink="/config/chlink ON" + " OFF" * 15,
                      ch_02_eq_1="/ch/02/eq/1 PEQ 100.0 +0.00 2.0")
        text = edited(base, ch_02_eq_1="/ch/02/eq/1 PEQ 300.0 +6.00 2.0",
                      ch_01_mix_15="/ch/01/mix/15 ON -1.0 +0 PRE 0")
        with Desk(base) as desk:
            r = self.load(desk, text, keep=Keep(globs=["/ch/01/eq/*"]))
        self.assertEqual(r.passes, [["/ch/01/mix/15"]])
        self.assertEqual(r.kept, [("/ch/01/eq/* and its linked sides", ["/ch/01/eq/1", "/ch/02/eq/1"])])

    def test_both_sides_of_a_kept_pair_name_one_mix(self):
        with Desk(BASE) as desk:
            r = self.load(desk, BASE, keep=Keep(buses=[13, 14]))
        self.assertEqual([w for w, _ in r.kept], ["bus 13/14"])

    def test_a_link_line_the_desk_does_not_answer_writes_nothing(self):
        for missing in ("/config/mtxlink", "/config/buslink", "/config/linkcfg"):
            with self.subTest(missing=missing), Desk(without(BASE, missing)) as desk:
                with self.assertRaises(O.OscError) as cm:
                    self.load(desk, changed(ch_01_eq_1=EQ), keep=Keep(buses=[15]))
                self.assertIn(f"did not answer {missing}", str(cm.exception))
                self.assertEqual(desk.writes, [])

    def test_an_unmatched_pattern_or_a_bus_past_16_is_refused_before_the_desk_is_asked(self):
        for keep, said in ((Keep(globs=["/nope/*"]), "'/nope/*' matches no line"),
                           (Keep(buses=[17]), "--keep-bus wants a bus 1-16, got 17")):
            with self.subTest(said):
                with mock.patch.object(L.osc_pull, "pull_scene_like", side_effect=AssertionError("asked")), \
                     self.assertRaises(L.Unloadable) as cm:
                    load_scene(Scene.parse(BASE), "127.0.0.1", keep=keep)
                self.assertIn(said, str(cm.exception))

    def test_a_kept_line_the_first_or_the_last_read_misses_is_unanswered(self):
        with Desk(BASE, mute_first_read=("/bus/15/config",)) as desk:
            r = self.load(desk, BASE, keep=Keep(globs=["/bus/15/*"]))
        self.assertEqual((r.passes, r.unanswered, r.ok), ([], ["/bus/15/config"], False))
        with Desk(BASE, mute_first_read=("/bus/15/config",)) as desk:
            r = self.load(desk, changed(ch_01_eq_1=EQ), keep=Keep(globs=["/bus/15/*"]))
        self.assertEqual((r.passes, r.moved), ([["/ch/01/eq/1"]], []))
        self.assertEqual((r.unanswered, r.ok), (["/bus/15/config"], False))
        desk = Desk(BASE)
        desk.muted["/bus/15/config"] = 4     # the first read and the read-back after pass 1
        with desk:
            r = self.load(desk, changed(ch_01_eq_1=EQ), keep=Keep(globs=["/bus/15/*"]))
        self.assertEqual((r.passes, r.unanswered, r.ok), ([["/ch/01/eq/1"]], ["/bus/15/config"], False))

    def test_relinking_another_pair_is_written_with_the_kept_pairs_token_unchanged(self):
        text = changed(config_buslink="/config/buslink OFF OFF OFF OFF OFF OFF ON ON")
        with Desk(BASE) as desk:
            r = self.load(desk, text, keep=Keep(buses=[13]))
        self.assertEqual((r.passes, r.ok), ([["/config/buslink"]], True))
        self.assertEqual([w for w, _ in r.kept], ["bus 13/14"])
        with Desk(BASE) as desk:
            r = self.load(desk, text, keep=Keep(buses=[13], globs=["/config/buslink"]))
        self.assertEqual((r.passes, r.ok, desk.writes), ([], True, []))

    def test_a_kept_mix_the_file_has_no_line_of_is_refused_before_any_write(self):
        with Desk(BASE) as desk, self.assertRaises(L.Unloadable) as cm:
            self.load(desk, changed(ch_01_eq_1=EQ), keep=Keep(buses=[3]))
        self.assertIn("--keep-bus 3: the file has no line of that mix", str(cm.exception))
        self.assertEqual(desk.writes, [])

    def test_keep_glob_leaves_matching_lines_and_an_unmatched_pattern_is_refused(self):
        with Desk(BASE) as desk:
            r = self.load(desk, changed(ch_01_eq_1=EQ, ch_01_mix_15="/ch/01/mix/15 ON -1.0 +0 PRE 0"),
                          keep=Keep(globs=["/ch/01/eq/*"]))
        self.assertEqual(r.passes, [["/ch/01/mix/15"]])
        self.assertEqual(r.kept, [("/ch/01/eq/*", ["/ch/01/eq/1"])])
        with Desk(BASE) as desk, self.assertRaises(ValueError) as cm:
            self.load(desk, changed(ch_01_eq_1=EQ), keep=Keep(globs=["/ch/01/eq/*", "/nope/*"]))
        self.assertIn("'/nope/*' matches no line", str(cm.exception))
        self.assertEqual(desk.writes, [])

    def test_a_kept_path_the_desk_moves_anyway_is_reported(self):
        nudged = "/ch/01/mix/13 ON -40.0 +0 PRE 0"
        with Desk(BASE, effects={"/ch/01/eq/1": {"/ch/01/mix/13": nudged}}) as desk:
            r = self.load(desk, changed(ch_01_eq_1=EQ, ch_01_mix_13=MIX13), keep=Keep(buses=[13]))
        self.assertEqual(r.passes, [["/ch/01/eq/1"]])
        self.assertEqual([(c.path, c.before, c.after) for c in r.moved],
                         [("/ch/01/mix/13", "/ch/01/mix/13 ON  -3.0 +0 PRE 0", nudged)])
        self.assertEqual((r.ok, r.stuck), (False, []))


class KeepCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_load(self, desk: Desk, text: str, *argv):
        path = os.path.join(self.tmp, "a.scn")
        with open(path, "w") as fh:
            fh.write(text)
        out, err = io.StringIO(), io.StringIO()
        with desk, mock.patch.object(O, "X32_PORT", desk.port), \
             mock.patch("x32scene.services.load.time.sleep", lambda s: None), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["load", path, "--ip", "127.0.0.1", "--timeout", "0.2", *argv])
        return rc, out.getvalue(), err.getvalue()

    def test_prints_what_it_kept_and_json_carries_it(self):
        text = changed(ch_01_mix_13=MIX13, ch_01_mix_14=MIX14, ch_01_eq_1=EQ)
        rc, out, err = self.run_load(Desk(BASE), text, "--keep-bus", "13")
        self.assertEqual(rc, 0, err)
        self.assertIn("pass 1: 1 line(s) written", out)
        self.assertIn("kept as the desk holds them: bus 13/14 (6 line(s))", out)
        self.assertIn("the desk holds a.scn outside the kept lines: 1 line(s) written in 1 pass(es)", out)
        rc, out, _ = self.run_load(Desk(BASE), text, "--keep-bus", "13", "--keep", "/bus/15/*", "--json")
        self.assertEqual(rc, 0)
        doc = json.loads(out)
        self.assertEqual([k["what"] for k in doc["kept"]], ["bus 13/14", "/bus/15/*"])
        self.assertEqual(sorted(doc["kept"][0]["paths"]), sorted(PAIR_13_14))
        self.assertEqual((doc["ok"], doc["moved"]), (True, []))

    def test_a_kept_line_the_desk_moved_exits_1_and_shows_both(self):
        nudged = "/ch/01/mix/13 ON -40.0 +0 PRE 0"
        desk = Desk(BASE, effects={"/ch/01/eq/1": {"/ch/01/mix/13": nudged}})
        rc, out, _ = self.run_load(desk, changed(ch_01_eq_1=EQ), "--keep-bus", "13")
        self.assertEqual(rc, 1)
        self.assertIn("1 kept path(s) changed during the load, by a copy of a write or by "
                      "hand:", out)
        self.assertIn("    - /ch/01/mix/13 ON  -3.0 +0 PRE 0", out)
        self.assertIn(f"    + {nudged}", out)
        self.assertNotIn("the desk holds a.scn", out)

    def test_a_desk_silent_on_a_link_line_exits_2_with_nothing_written(self):
        desk = Desk(without(BASE, "/config/mtxlink"))
        rc, _, err = self.run_load(desk, changed(ch_01_eq_1=EQ), "--keep-bus", "13")
        self.assertEqual(rc, 2)
        self.assertIn("did not answer /config/mtxlink", err)
        self.assertIn("nothing was written", err)
        self.assertEqual(desk.writes, [])

    def test_a_refused_file_exits_1_with_nothing_written(self):
        desk = Desk(BASE)
        text = changed(config_buslink="/config/buslink OFF OFF OFF OFF OFF OFF OFF OFF")
        rc, out, err = self.run_load(desk, text, "--keep-bus", "13")
        self.assertEqual(rc, 1)
        self.assertIn("bus 13/14 link", err)
        self.assertIn("nothing written", err)
        self.assertEqual(desk.writes, [])

    def test_a_value_error_once_writes_went_out_is_not_called_nothing_written(self):
        with mock.patch.object(L, "load_scene", side_effect=ValueError("boom")):
            rc, _, err = self.run_load(Desk(BASE), BASE, "--keep-bus", "13")
        self.assertEqual(rc, 1)
        self.assertIn("boom", err)
        self.assertNotIn("nothing written", err)

    def test_keep_bus_must_be_1_to_16(self):
        from x32scene._parsers import _build_parser
        for bad in ("0", "17", "x"):
            with self.subTest(bus=bad), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _build_parser(None).parse_args(["load", "a.scn", "--keep-bus", bad])
        args = _build_parser(None).parse_args(["load", "a.scn", "--keep-bus", "1", "--keep-bus", "16"])
        self.assertEqual(args.keep_bus, [1, 16])


if __name__ == "__main__":
    unittest.main()
