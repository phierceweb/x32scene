"""CLI smoke tests: read-only subcommands run without error on the example scene."""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.model import Scene

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


class CliTest(unittest.TestCase):
    def test_readonly_commands_exit_zero(self):
        # ports reads X32SCENE_CONFIG / X32SCENE_STAGE by default: keep it hermetic
        with mock.patch.dict(os.environ):
            os.environ.pop("X32SCENE_CONFIG", None)
            os.environ.pop("X32SCENE_STAGE", None)
            for argv in (["info", SCENE], ["ports", SCENE], ["buses", SCENE],
                         ["inputs", SCENE], ["record-map", SCENE], ["fx", SCENE],
                         ["dca", SCENE], ["explain", SCENE], ["iem", SCENE, "1"]):
                with self.subTest(cmd=argv[0]):
                    self.assertEqual(main(argv), 0)

    def test_live_command_without_ip_fails_cleanly(self):
        # the parser reads X32SCENE_IP: a developer's shell must not turn this into
        # a real network pull
        with mock.patch.dict(os.environ):
            os.environ.pop("X32SCENE_IP", None)
            self.assertEqual(main(["live-diff", SCENE]), 1)

    def test_timeout_resolves_from_env_and_yields_to_the_flag(self):
        from x32scene._parsers import _build_parser

        def timeout(*extra):
            argv = ["live-diff", SCENE, "--ip", "10.0.0.1", *extra]
            return _build_parser(None).parse_args(argv).timeout

        with mock.patch.dict(os.environ):
            os.environ.pop("X32SCENE_TIMEOUT", None)
            self.assertEqual(timeout(), 0.5)
        with mock.patch.dict(os.environ, {"X32SCENE_TIMEOUT": "1.25"}):
            self.assertEqual(timeout(), 1.25)
            self.assertEqual(timeout("--timeout", "2"), 2.0)
        # malformed env falls back rather than raising (pf-core resolve_float)
        with mock.patch.dict(os.environ, {"X32SCENE_TIMEOUT": "soon"}):
            self.assertEqual(timeout(), 0.5)

    def test_iem_view_includes_auxin_and_fxrtn_sends(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(main(["iem", SCENE, "3"]), 0)
        out = buf.getvalue()
        self.assertIn("/fxrtn/01", out)
        self.assertIn("Bluetooth L", out)   # /auxin/05's scribble name

    def test_version_flag_reports_the_installed_version(self):
        import x32scene
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(buf):
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(x32scene.__version__, buf.getvalue())

    def test_piping_into_a_closed_reader_is_silent(self):
        # `x32scene diff a b | head -2` must not tail a BrokenPipeError; diff's output
        # is long enough that the flush lands after the reader is gone
        import subprocess
        alt = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")
        head = subprocess.run(
            f"{sys.executable} -m x32scene.cli diff {SCENE} {alt} | head -2",
            shell=True, capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."))
        self.assertNotIn("Exception ignored", head.stderr)
        self.assertNotIn("BrokenPipeError", head.stderr)

    def test_edit_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "work.scn")
            shutil.copy(SCENE, work)
            with open(work, encoding="utf-8", newline="") as fh:
                before = fh.read()
            rc = main(["set-eq", work, "1", "1", "--gain", "3", "-o", work])
            self.assertEqual(rc, 1)
            with open(work, encoding="utf-8", newline="") as fh:
                self.assertEqual(fh.read(), before)

    def test_edit_commands_write_exactly_intended_paths(self):
        from x32scene.services.diff import diff
        alt = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")
        base = Scene.load(SCENE)
        cases = [
            (["set-comp", SCENE, "9", "--thr", "-20"], {"/ch/09/dyn"}),
            (["set-gate", SCENE, "1", "--thr", "-50"], {"/ch/01/gate"}),
            (["set-lowcut", SCENE, "9", "--on", "--freq", "80"], {"/ch/09/preamp"}),
            # bus 13/14 are unlinked in the fixture; 1/2 are, and would mirror
            (["set-eq", SCENE, "/bus/13", "6", "--gain", "-3"], {"/bus/13/eq/6"}),
            # ch 11/12 are a linked pair in the fixture: exercises CLI-path mirroring
            (["set-eq", SCENE, "11", "1", "--gain", "3"], {"/ch/11/eq/1", "/ch/12/eq/1"}),
            (["set-comp", SCENE, "11", "--thr", "-20"], {"/ch/11/dyn", "/ch/12/dyn"}),
            (["set-gate", SCENE, "11", "--thr", "-50"], {"/ch/11/gate", "/ch/12/gate"}),
            (["set-lowcut", SCENE, "11", "--freq", "80"],
             {"/ch/11/preamp", "/ch/12/preamp"}),
            (["set-fader", SCENE, "1", "-6.5"], {"/ch/01/mix"}),
            (["set-fader", SCENE, "1", "oo"], {"/ch/01/mix"}),
            # ch 11/12 are linked with fdrmute link on: fader/mute mirror, pan doesn't
            (["set-fader", SCENE, "11", "-6.0"], {"/ch/11/mix", "/ch/12/mix"}),
            (["set-fader", SCENE, "11", "-6.0", "--no-link"], {"/ch/11/mix"}),
            (["set-mute", SCENE, "11", "on"], {"/ch/11/mix", "/ch/12/mix"}),
            (["set-eq", SCENE, "11", "1", "--gain", "3", "--no-link"], {"/ch/11/eq/1"}),
            (["set-pan", SCENE, "11", "-50"], {"/ch/11/mix"}),
            (["set-mute", SCENE, "1", "on"], {"/ch/01/mix"}),
            (["set-pan", SCENE, "1", "-50"], {"/ch/01/mix"}),
            (["rename", SCENE, "/bus/01", "Wedge L"], {"/bus/01/config"}),
            # number width is canonicalized per family: /bus/1 and /dca/03 both resolve
            (["rename", SCENE, "/bus/1", "Wedge L"], {"/bus/01/config"}),
            (["set-fader", SCENE, "/dca/03", "-3.0"], {"/dca/3"}),
        ]
        with tempfile.TemporaryDirectory() as d:
            for i, (argv, want) in enumerate(cases):
                with self.subTest(cmd=argv[0]):
                    out = os.path.join(d, f"o{i}.scn")
                    self.assertEqual(main(argv + ["-o", out]), 0)
                    changed = {c.path for c in diff(base, Scene.load(out))}
                    self.assertEqual(changed, want)
            chn = os.path.join(d, "p.chn")
            self.assertEqual(main(["extract-preset", SCENE, "1", "-o", chn,
                                   "--scope", "eq"]), 0)
            with open(chn, "rb") as fh:   # a .chn is LF-only too, on every platform
                self.assertNotIn(b"\r", fh.read())
            out = os.path.join(d, "applied.scn")
            self.assertEqual(main(["apply-preset", SCENE, "20", chn, "-o", out]), 0)
            changed = {c.path for c in diff(base, Scene.load(out))}
            self.assertTrue(changed and all(p.startswith("/ch/20/eq") for p in changed),
                            changed)
            out = os.path.join(d, "ported.scn")
            self.assertEqual(main(["port-iem", SCENE, alt, "-o", out]), 0)
            changed = {c.path for c in diff(Scene.load(alt), Scene.load(out))}
            self.assertTrue(changed and all(p.startswith("/outputs/") for p in changed),
                            changed)

    def test_edit_output_names_the_mirrored_partner(self):
        with tempfile.TemporaryDirectory() as d:
            for i, (argv, want) in enumerate((
                    (["set-comp", SCENE, "11", "--thr", "-20"], "mirrored to /ch/12"),
                    (["set-eq", SCENE, "11", "1", "--gain", "3"], "mirrored to /ch/12"),
                    (["set-comp", SCENE, "9", "--thr", "-20"], None))):
                with self.subTest(cmd=argv[0], strip=argv[2]):
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        self.assertEqual(main(argv + ["-o", os.path.join(d, f"m{i}.scn")]), 0)
                    if want is None:
                        self.assertNotIn("mirrored", buf.getvalue())
                    else:
                        self.assertIn(want, buf.getvalue())

    def test_set_fader_oo_alias_writes_negative_infinity(self):
        # both spellings work, dash included — a bare "-oo" would otherwise parse as -o o
        with tempfile.TemporaryDirectory() as d:
            for i, argv in enumerate((["set-fader", SCENE, "1", "oo"],
                                      ["set-fader", SCENE, "1", "-oo"],
                                      ["set-fader", SCENE, "1", "--", "-oo"])):
                with self.subTest(level=argv[-1], dashed="--" in argv):
                    out = os.path.join(d, f"o{i}.scn")
                    self.assertEqual(main(argv[:3] + ["-o", out] + argv[3:]), 0)
                    self.assertEqual(Scene.load(out).get("/ch/01/mix").args[1], "-oo")

    def test_set_fader_help_documents_both_oo_spellings(self):
        buf = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(buf):
            main(["set-fader", "--help"])
        self.assertIn("oo (also -oo) for -infinity", buf.getvalue())

    def test_edit_refuses_case_variant_overwrite(self):
        # on case-insensitive filesystems (macOS/Windows) -o WORK.SCN is the input file
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "probe"), "w").close()
            if not os.path.exists(os.path.join(d, "PROBE")):
                self.skipTest("case-sensitive filesystem")
            work = os.path.join(d, "work.scn")
            shutil.copy(SCENE, work)
            with open(work, encoding="utf-8", newline="") as fh:
                before = fh.read()
            rc = main(["set-eq", work, "1", "1", "--gain", "3",
                       "-o", os.path.join(d, "WORK.SCN")])
            self.assertEqual(rc, 1)
            with open(work, encoding="utf-8", newline="") as fh:
                self.assertEqual(fh.read(), before)

    def test_lowcut_on_and_off_together_is_an_argparse_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as ctx, \
                    contextlib.redirect_stderr(io.StringIO()):
                main(["set-lowcut", SCENE, "1", "--on", "--off",
                      "-o", os.path.join(d, "o.scn")])
            self.assertEqual(ctx.exception.code, 2)

    def test_flagless_channelfx_edit_is_refused(self):
        # zero knob flags would sell a byte-identical copy as an edit
        with tempfile.TemporaryDirectory() as d:
            for argv in (["set-eq", SCENE, "1", "2"], ["set-comp", SCENE, "1"],
                         ["set-gate", SCENE, "1"], ["set-lowcut", SCENE, "1"]):
                with self.subTest(cmd=argv[0]):
                    out = os.path.join(d, "o.scn")
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        rc = main(argv + ["-o", out])
                    self.assertEqual(rc, 1)
                    self.assertIn("nothing to set", err.getvalue())
                    self.assertFalse(os.path.exists(out))

    def test_iem_rejects_a_bus_the_console_does_not_have(self):
        for bus in ("0", "99"):
            with self.subTest(bus=bus):
                err = io.StringIO()
                with self.assertRaises(SystemExit) as ctx, \
                        contextlib.redirect_stderr(err):
                    main(["iem", SCENE, bus])
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("invalid choice", err.getvalue())

    def test_zero_valued_knob_is_a_real_edit(self):
        # 0.0 == False in Python; a lone zero-valued knob must not read as "nothing to set"
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.scn")
            self.assertEqual(main(["set-eq", SCENE, "1", "2", "--gain", "0",
                                   "-o", out]), 0)
            self.assertEqual(Scene.load(out).get("/ch/01/eq/2").args[2], "+0.00")
            out2 = os.path.join(d, "o2.scn")
            self.assertEqual(main(["set-comp", SCENE, "9", "--thr", "0",
                                   "-o", out2]), 0)
            self.assertEqual(Scene.load(out2).get("/ch/09/dyn").args[4], "0.0")

    def test_diff_renders_added_and_removed_without_none(self):
        with tempfile.TemporaryDirectory() as d:
            b_path = os.path.join(d, "b.scn")
            sc = Scene.load(SCENE)
            sc.lines = [ln for ln in sc.lines if ln.path != "/fx/1"]
            with open(b_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(sc.dump())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["diff", SCENE, b_path]), 0)
            out = buf.getvalue()
            self.assertIn("(removed)", out)
            self.assertNotIn("None", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
