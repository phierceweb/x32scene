"""watch, end to end, at the edges: Ctrl-C and --seconds with a change still waiting, a path
that stops answering, an --snippet destination that cannot be written, and what the summary
says about the snippet."""

import errno
import json
import os
import stat
import unittest
from unittest import mock

from tests.test_watch_cli import EQ_UP, MIX_DOWN, MIX_START, REF_TEXT, WatchCliBase, WatchConsole
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services import watch as W
from x32scene.services.snippets import make_snippet

BUSLINK_REF = REF_TEXT + "/config/buslink OFF OFF OFF OFF OFF OFF OFF OFF\n"
BUSLINK_ON = "/config/buslink ON OFF OFF OFF OFF OFF OFF OFF"


class WatchEndTest(WatchCliBase):
    def test_ctrl_c_reads_back_a_change_still_in_its_debounce_window(self):
        out_snp = os.path.join(self.tmp, "late.snp")
        console = WatchConsole(script=[(0.2, MIX_DOWN, ["/ch/01/mix/fader"]), (0.02, "INTERRUPT")])
        rc, out, err = self.watch(console, "--snippet", out_snp)
        self.assertEqual(rc, 0)
        self.assertNotIn("Traceback", err)
        self.assertIn("1 change(s) logged", out)
        start = Scene.parse(REF_TEXT)
        with open(out_snp) as fh:
            self.assertEqual(fh.read(), make_snippet(start, Scene.parse(
                REF_TEXT.replace(MIX_START, MIX_DOWN)), "late").scene.dump())

    def test_seconds_end_reads_back_a_change_still_in_its_debounce_window(self):
        console = WatchConsole(script=[(0.9, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--json")
        self.assertEqual(rc, 0)
        summary = json.loads(out.splitlines()[-1])
        self.assertEqual([c["path"] for c in summary["net"]], ["/ch/01/eq/1"])

    def test_ctrl_c_during_the_start_pull_exits_cleanly(self):
        with mock.patch.object(O, "pull_scene_like", side_effect=KeyboardInterrupt):
            rc, out, err = self.watch(WatchConsole(), "--seconds", "5")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertIn("nothing watched", err)

    def test_ignored_addresses_are_worded_as_unwatched(self):
        desk = REF_TEXT.replace("/ch/02/mix ON  -oo ON +0 OFF   -oo\n", "")
        console = WatchConsole(text=desk, script=[(0.2, None, ["/ch/02/mix/fader"])])
        rc, out, _ = self.watch(console, "--seconds", "0.8")
        self.assertEqual(rc, 0)
        self.assertIn("1 message(s) ignored (no watched path)", out)


class UnansweredTest(WatchCliBase):
    """/ch/01/mix answers the start pull, then stops answering."""

    def test_the_summary_says_which_paths_did_not_answer(self):
        out_snp = os.path.join(self.tmp, "none.snp")
        console = WatchConsole(lose={"/ch/01/mix"}, script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--snippet", out_snp)
        self.assertEqual(rc, 0)
        summary = out.split("summary")[1]
        self.assertNotIn("net: nothing differs from the start\n", summary)
        self.assertIn("1 path(s) did not answer; their net change is unknown: /ch/01/mix\n", summary)
        self.assertIn(f"no net change among the paths that answered; nothing written to {out_snp}",
                      summary)
        self.assertFalse(os.path.exists(out_snp))

    def test_json_carries_the_unanswered_paths(self):
        console = WatchConsole(lose={"/ch/01/mix"}, script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--json")
        self.assertEqual(rc, 0)
        summary = json.loads(out.splitlines()[-1])
        self.assertEqual((summary["net"], summary["unanswered"]), ([], ["/ch/01/mix"]))

    def test_the_snippet_holds_what_answered_and_says_it_may_be_incomplete(self):
        out_snp = os.path.join(self.tmp, "part.snp")
        console = WatchConsole(lose={"/ch/01/mix"}, script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                                            (0.1, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, out, _ = self.watch(console, "--seconds", "1", "--snippet", out_snp)
        self.assertEqual(rc, 0)
        with open(out_snp) as fh:
            self.assertEqual(fh.read(), make_snippet(Scene.parse(REF_TEXT), Scene.parse(
                REF_TEXT.replace("/ch/01/eq/1 PEQ 36.0 +0.00 1.0", EQ_UP)), "part").scene.dump())
        self.assertIn("1 changed path(s):", out)
        self.assertIn("the snippet may be incomplete: 1 path(s) did not answer\n", out)

    def test_a_path_that_goes_silent_after_a_change_leaves_its_old_value_out(self):
        out_snp = os.path.join(self.tmp, "stale.snp")
        console = WatchConsole(lose={"/ch/01/mix": 2},
                               script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (0.4, EQ_UP, ["/ch/01/eq/1/g"]),
                                       (0.1, MIX_START, ["/ch/01/mix/fader"])])
        rc, out, _ = self.watch(console, "--seconds", "1.2", "--snippet", out_snp)
        self.assertEqual(rc, 0)
        self.assertIn("2 change(s) logged", out)
        summary = out.split("summary")[1]
        self.assertIn("net: 1 changed path(s):", summary)
        self.assertNotIn("-10.0", summary)
        self.assertIn("1 path(s) did not answer; their net change is unknown: /ch/01/mix\n",
                      summary)
        with open(out_snp) as fh:
            self.assertEqual(fh.read(), make_snippet(Scene.parse(REF_TEXT), Scene.parse(
                REF_TEXT.replace("/ch/01/eq/1 PEQ 36.0 +0.00 1.0", EQ_UP)), "stale").scene.dump())


class LinkFailureTest(WatchCliBase):
    """The network goes away mid-watch: what was already read back still reaches the summary
    and the snippet."""

    def fail_second_read_back(self, *argv):
        real_send = W.UdpTransport.send
        sent = {"node": 0}

        def send(link, addr, args=()):
            if addr == "/node":
                sent["node"] += 1
                if sent["node"] == 2:
                    raise OSError(errno.EHOSTUNREACH, "No route to host")
            return real_send(link, addr, args)

        console = WatchConsole(script=[(0.2, MIX_DOWN, ["/ch/01/mix/fader"]),
                                       (0.6, EQ_UP, ["/ch/01/eq/1/g"])])
        with mock.patch.object(W.UdpTransport, "send", send):
            return self.watch(console, "--seconds", "5", *argv)

    def test_the_summary_and_snippet_survive_and_the_exit_is_1(self):
        out_snp = os.path.join(self.tmp, "partial.snp")
        rc, out, err = self.fail_second_read_back("--snippet", out_snp)
        self.assertEqual(rc, 1)
        self.assertIn("No route to host", err)
        self.assertNotIn("Traceback", err)
        summary = out.split("summary")[1]
        self.assertIn("net: 1 changed path(s):", summary)
        self.assertIn("1 path(s) did not answer; their net change is unknown: /ch/01/eq/1", summary)
        with open(out_snp) as fh:
            self.assertEqual(fh.read(), make_snippet(Scene.parse(REF_TEXT), Scene.parse(
                REF_TEXT.replace(MIX_START, MIX_DOWN)), "partial").scene.dump())

    def test_json_still_ends_on_the_summary(self):
        rc, out, _ = self.fail_second_read_back("--json")
        self.assertEqual(rc, 1)
        summary = json.loads(out.splitlines()[-1])
        self.assertEqual(([c["path"] for c in summary["net"]], summary["unanswered"]),
                         (["/ch/01/mix"], ["/ch/01/eq/1"]))


class SnippetDestinationTest(WatchCliBase):
    def refused(self, *argv):
        console = WatchConsole(script=[(0.1, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, out, err = self.watch(console, "--seconds", "1", *argv)
        self.assertEqual(rc, 1)
        self.assertEqual(console.received, [])       # refused before any OSC went out
        self.assertEqual(out, "")
        return err

    def test_a_missing_directory_is_refused_before_the_watch(self):
        err = self.refused("--snippet", os.path.join(self.tmp, "no", "such", "a.snp"))
        self.assertIn("--snippet", err)
        self.assertIn("no directory", err)

    def test_a_directory_is_refused_before_the_watch_even_with_force(self):
        err = self.refused("--snippet", self.tmp, "--force")
        self.assertIn("is a directory", err)

    def test_an_empty_name_is_refused(self):
        self.assertIn("--snippet", self.refused("--snippet", ""))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes anywhere")
    def test_a_read_only_directory_is_refused_before_the_watch(self):
        locked = os.path.join(self.tmp, "locked")
        os.mkdir(locked)
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, locked, stat.S_IRWXU)
        self.assertIn("not writable", self.refused("--snippet", os.path.join(locked, "a.snp")))

    def test_naming_the_reference_names_the_snippet_flag(self):
        err = self.refused("--snippet", self.ref)
        self.assertIn(f"--snippet {self.ref} would overwrite the input", err)
        self.assertNotIn("-o ", err)

    def test_a_failed_write_still_prints_the_summary(self):
        out_snp = os.path.join(self.tmp, "a.snp")
        for argv in ((), ("--json",)):
            with self.subTest(argv=argv), \
                 mock.patch.object(Scene, "save", side_effect=OSError("disk full")):
                console = WatchConsole(script=[(0.1, EQ_UP, ["/ch/01/eq/1/g"])])
                rc, out, err = self.watch(console, "--seconds", "0.8", "--snippet", out_snp, *argv)
                self.assertEqual(rc, 1)
                self.assertIn("disk full", err)
                if argv:
                    summary = json.loads(out.splitlines()[-1])
                    self.assertEqual(summary["snippet"]["written"], False)
                    self.assertEqual([c["path"] for c in summary["net"]], ["/ch/01/eq/1"])
                else:
                    self.assertIn("net: 1 changed path(s):", out)


class SnippetJsonTest(WatchCliBase):
    def summary(self, console, *argv):
        rc, out, _ = self.watch(console, "--seconds", "0.8", "--json", *argv)
        self.assertEqual(rc, 0)
        return json.loads(out.splitlines()[-1])["snippet"]

    def test_written(self):
        out_snp = os.path.join(self.tmp, "w.snp")
        snip = self.summary(WatchConsole(script=[(0.1, EQ_UP, ["/ch/01/eq/1/g"])]),
                            "--snippet", out_snp)
        self.assertEqual(snip, {"file": out_snp, "written": True, "lines": 1, "skipped": []})

    def test_no_net_change_says_nothing_was_written(self):
        out_snp = os.path.join(self.tmp, "none.snp")
        snip = self.summary(WatchConsole(script=[(0.1, MIX_DOWN, ["/ch/01/mix/fader"]),
                                                 (0.25, MIX_START, ["/ch/01/mix/fader"])]),
                            "--snippet", out_snp)
        self.assertEqual(snip, {"file": out_snp, "written": False, "lines": 0, "skipped": []})
        self.assertFalse(os.path.exists(out_snp))

    def test_a_change_no_snippet_can_carry_names_what_was_skipped(self):
        with open(self.ref, "w") as fh:
            fh.write(BUSLINK_REF)
        out_snp = os.path.join(self.tmp, "bl.snp")
        snip = self.summary(WatchConsole(text=BUSLINK_REF,
                                         script=[(0.1, BUSLINK_ON, ["/config/buslink/1-2"])]),
                            "--snippet", out_snp)
        self.assertEqual(snip, {"file": out_snp, "written": False, "lines": 0,
                                "skipped": ["/config/buslink"]})


class RelinkedSnippetTest(WatchCliBase):
    """A link pressed during the watch reshapes sends the snippet carries, but not the link."""

    SEND_DOWN = "/ch/01/mix/01 ON  -5.0 +0 PRE 0"

    def run_relink(self, *argv):
        with open(self.ref, "w") as fh:
            fh.write(BUSLINK_REF)
        out_snp = os.path.join(self.tmp, "relink.snp")
        console = WatchConsole(text=BUSLINK_REF,
                               script=[(0.1, BUSLINK_ON, ["/config/buslink/1-2"]),
                                       (0.05, self.SEND_DOWN, ["/ch/01/mix/01/level"])])
        rc, out, err = self.watch(console, "--seconds", "1", "--snippet", out_snp, *argv)
        self.assertEqual(rc, 0)
        return out_snp, out, err

    def test_the_snippet_is_written_with_a_warning_naming_the_pair(self):
        for argv in ((), ("--json",)):
            with self.subTest(argv=argv):
                out_snp, out, err = self.run_relink("--force", *argv)
                with open(out_snp) as fh:
                    self.assertIn("/ch/01/mix/01", fh.read())
                warnings = [ln for ln in err.splitlines() if "/config/buslink" in ln]
                self.assertEqual(len(warnings), 1, err)
                self.assertIn("warning", warnings[0])
                self.assertIn("bus 1/2", warnings[0])
                if argv:
                    self.assertTrue(json.loads(out.splitlines()[-1])["snippet"]["written"])

    def test_a_link_change_the_snippet_carries_nothing_of_gives_no_warning(self):
        with open(self.ref, "w") as fh:
            fh.write(BUSLINK_REF)
        out_snp = os.path.join(self.tmp, "only-link.snp")
        console = WatchConsole(text=BUSLINK_REF,
                               script=[(0.1, BUSLINK_ON, ["/config/buslink/1-2"]),
                                       (0.05, EQ_UP, ["/ch/01/eq/1/g"])])
        rc, _, err = self.watch(console, "--seconds", "1", "--snippet", out_snp)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(out_snp))
        self.assertNotIn("/config/buslink", err)


if __name__ == "__main__":
    unittest.main()
