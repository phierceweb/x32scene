"""`extract-preset --all` and `presets-diff`: a preset folder regenerated from a scene is
one that scene matches exactly, and an apply of any of its presets changes nothing."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.presets import apply_preset

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
ALT = os.path.join(os.path.dirname(__file__), "fixtures", "example-alt.scn")


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class ExtractAllTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.lib = os.path.join(self.dir, "presets")

    def test_every_written_preset_applies_as_a_no_op_and_the_folder_matches(self):
        rc, out, _ = _run(["extract-preset", SCENE, "--all", "-o", self.lib])
        self.assertEqual(rc, 0)
        files = sorted(os.listdir(self.lib))
        self.assertEqual(len(files), 31)
        self.assertIn("ch29", out)                   # the unnamed channel, listed as skipped
        self.assertIn("LOAD-TEST", out)
        scene = Scene.load(SCENE)
        for ch in [c for c in range(1, 33) if c != 29]:
            name = scene.get(f"/ch/{ch:02d}/config").args[0].strip('"')
            with self.subTest(ch=ch):
                with open(os.path.join(self.lib, f"{name}.chn"), encoding="utf-8") as fh:
                    self.assertEqual(apply_preset(Scene.load(SCENE), ch, fh.read()), 0)
        rc, out, err = _run(["presets-diff", self.lib, SCENE])
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(out.count("MATCH"), 32)     # 31 rows + the count line
        self.assertNotIn("DRIFT ", out)

    def test_a_scoped_headered_library_still_matches(self):
        _run(["extract-preset", SCENE, "--all", "-o", self.lib, "--scope", "eq", "--header"])
        rc, out, _ = _run(["presets-diff", self.lib, SCENE, "--scope", "eq"])
        self.assertEqual(rc, 0)
        self.assertNotIn("NO CHANNEL ", out)

    def test_one_existing_target_writes_nothing_and_names_it(self):
        os.makedirs(self.lib)
        with open(os.path.join(self.lib, "Hat.chn"), "w") as fh:
            fh.write("keep me\n")
        rc, _, err = _run(["extract-preset", SCENE, "--all", "-o", self.lib])
        self.assertEqual(rc, 1)
        self.assertIn("Hat.chn", err)
        self.assertEqual(os.listdir(self.lib), ["Hat.chn"])
        rc, _, _ = _run(["extract-preset", SCENE, "--all", "-o", self.lib, "--force"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(os.listdir(self.lib)), 31)
        with open(os.path.join(self.lib, "Hat.chn")) as fh:
            self.assertTrue(fh.read().startswith("/config"))

    def test_a_directory_in_a_targets_place_writes_nothing_even_with_force(self):
        os.makedirs(os.path.join(self.lib, "Snare Top.chn"))
        rc, _, err = _run(["extract-preset", SCENE, "--all", "-o", self.lib, "--force"])
        self.assertEqual(rc, 1)
        self.assertIn("Snare Top.chn", err)
        self.assertEqual(os.listdir(self.lib), ["Snare Top.chn"])

    def test_a_file_name_the_filesystem_refuses_writes_nothing(self):
        long = os.path.join(self.dir, "long.scn")
        sc = Scene.load(SCENE)
        sc.get("/ch/05/config").set_arg(0, '"' + "L" * 300 + '"')
        sc.save(long)
        rc, _, err = _run(["extract-preset", long, "--all", "-o", self.lib])
        self.assertEqual(rc, 1)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn("L" * 300 + ".chn", err)
        self.assertNotIn(".x32scene-", err)
        self.assertNotIn(".tmp", err)
        self.assertEqual(os.listdir(self.lib) if os.path.isdir(self.lib) else [], [])

    def test_a_scoped_library_matches_names_whose_characters_were_replaced(self):
        renamed = os.path.join(self.dir, "renamed.scn")
        sc = Scene.load(SCENE)
        sc.get("/ch/05/config").set_arg(0, '"Tom 1/2"')
        sc.get("/ch/06/config").set_arg(0, '"."')
        sc.save(renamed)
        _run(["extract-preset", renamed, "--all", "-o", self.lib, "--scope", "eq"])
        self.assertEqual(len(os.listdir(self.lib)), 31)
        rc, out, _ = _run(["presets-diff", self.lib, renamed, "--scope", "eq"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[-1].split(",")[0], "31 MATCH")

    def _renamed(self, names: dict[int, str]) -> str:
        path = os.path.join(self.dir, "renamed.scn")
        sc = Scene.load(SCENE)
        for ch, name in names.items():
            sc.get(f"/ch/{ch:02d}/config").set_arg(0, f'"{name}"')
        sc.save(path)
        return path

    def test_channels_sharing_a_name_are_skipped_and_the_rest_written(self):
        scene = self._renamed({7: "Snare 2", 8: "Snare 2"})
        rc, out, err = _run(["extract-preset", scene, "--all", "-o", self.lib])
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("skipped, share Snare 2.chn: ch07, ch08", out)
        self.assertIn("skipped, no scribble name: ch29", out)
        self.assertIn("wrote 29 preset(s)", out)
        files = os.listdir(self.lib)
        self.assertEqual(len(files), 29)
        self.assertNotIn("Snare 2.chn", files)

    def test_names_colliding_only_by_case_skip_both(self):
        scene = self._renamed({5: "KICK"})
        os.makedirs(self.lib)
        with open(os.path.join(self.lib, "Kick.chn"), "w") as fh:
            fh.write("keep me\n")
        rc, out, err = _run(["extract-preset", scene, "--all", "-o", self.lib])
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("skipped, share Kick.chn: ch01, ch05", out)
        self.assertEqual(len(os.listdir(self.lib)), 30)
        with open(os.path.join(self.lib, "Kick.chn")) as fh:
            self.assertEqual(fh.read(), "keep me\n")

    def test_a_shared_name_does_not_unlock_an_existing_target(self):
        scene = self._renamed({7: "Snare 2", 8: "Snare 2"})
        os.makedirs(self.lib)
        with open(os.path.join(self.lib, "Hat.chn"), "w") as fh:
            fh.write("keep me\n")
        rc, out, err = _run(["extract-preset", scene, "--all", "-o", self.lib])
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("Hat.chn", err)
        self.assertEqual(os.listdir(self.lib), ["Hat.chn"])

    def test_every_named_channel_sharing_a_name_writes_nothing(self):
        scene = self._renamed({ch: "Same" for ch in range(1, 33) if ch != 29})
        rc, _, err = _run(["extract-preset", scene, "--all", "-o", self.lib])
        self.assertEqual(rc, 1)
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("Same.chn", err)
        self.assertFalse(os.path.exists(self.lib))

    def test_an_out_that_is_not_a_directory_is_one_line_and_writes_nothing(self):
        file = os.path.join(self.dir, "file")
        with open(file, "w") as fh:
            fh.write("keep me\n")
        for out in (file, os.path.join(file, "presets"), ""):
            with self.subTest(out=out):
                rc, text, err = _run(["extract-preset", SCENE, "--all", "-o", out])
                self.assertEqual((rc, text), (1, ""))
                self.assertEqual(len(err.strip().splitlines()), 1)
                self.assertIn("-o", err)
                self.assertNotIn("Errno", err)
        self.assertIn("not a directory", _run(["extract-preset", SCENE, "--all", "-o", file])[2])
        self.assertEqual(os.listdir(self.dir), ["file"])
        with open(file) as fh:
            self.assertEqual(fh.read(), "keep me\n")

    def test_an_out_that_cannot_be_made_a_directory_is_one_line_and_creates_nothing(self):
        file = os.path.join(self.dir, "file")
        with open(file, "w") as fh:
            fh.write("keep me\n")
        os.symlink(os.path.join(self.dir, "gone"), os.path.join(self.dir, "dangling"))
        for out, message in ((os.path.join(self.dir, "nodir", "..", "file"), "not a directory"),
                             (os.path.join(self.dir, "dangling"), "not a directory"),
                             (os.path.join(self.dir, "L" * 300), "-o")):
            with self.subTest(out=os.path.basename(out)[:12]):
                rc, text, err = _run(["extract-preset", SCENE, "--all", "-o", out])
                self.assertEqual((rc, text), (1, ""))
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                self.assertIn(message, err)
                self.assertNotIn("Errno", err)
        self.assertEqual(sorted(os.listdir(self.dir)), ["dangling", "file"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root writes anywhere")
    def test_an_out_that_cannot_be_written_is_one_line_and_writes_nothing(self):
        locked = os.path.join(self.dir, "locked")
        os.mkdir(locked)
        os.chmod(locked, 0o555)
        self.addCleanup(os.chmod, locked, 0o700)
        for out in (locked, os.path.join(locked, "sub")):
            with self.subTest(out=out):
                rc, text, err = _run(["extract-preset", SCENE, "--all", "-o", out])
                self.assertEqual((rc, text), (1, ""))
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                self.assertIn("not writable", err)
                self.assertNotIn(".x32scene-", err)
        self.assertEqual(os.listdir(locked), [])

    def test_an_out_under_parents_that_do_not_exist_is_created(self):
        out = os.path.join(self.dir, "a", "b", "presets")
        rc, _, _ = _run(["extract-preset", SCENE, "--all", "-o", out])
        self.assertEqual(rc, 0)
        self.assertEqual(len(os.listdir(out)), 31)

    def test_ch_and_all_are_exclusive_and_one_is_required(self):
        for argv, want in ((["extract-preset", SCENE, "1", "--all", "-o", self.lib], "not both"),
                           (["extract-preset", SCENE, "-o", self.lib], "needs a channel")):
            with self.subTest(argv=argv):
                rc, _, err = _run(argv)
                self.assertEqual(rc, 1)
                self.assertIn(want, err)
        self.assertFalse(os.path.exists(self.lib))

    def test_a_target_that_is_the_input_scene_is_refused_even_with_force(self):
        os.makedirs(self.lib)
        scene = os.path.join(self.lib, "Kick.chn")
        shutil.copy(SCENE, scene)
        rc, _, err = _run(["extract-preset", scene, "--all", "-o", self.lib, "--force"])
        self.assertEqual(rc, 1)
        self.assertIn("would overwrite the input", err)
        self.assertEqual(os.listdir(self.lib), ["Kick.chn"])

    def test_the_single_channel_form_is_unchanged(self):
        out = os.path.join(self.dir, "kick.chn")
        rc, text, _ = _run(["extract-preset", SCENE, "1", "-o", out])
        self.assertEqual(rc, 0)
        self.assertIn("wrote preset for ch01", text)


class PresetsDiffTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.dir = os.path.join(self.root, "presets")
        _run(["extract-preset", SCENE, "--all", "-o", self.dir])

    def test_drift_exits_one_and_shows_both_values(self):
        drifted = os.path.join(self.root, "edited.scn")
        _run(["set-eq", SCENE, "1", "1", "--gain", "3", "-o", drifted])
        rc, out, _ = _run(["presets-diff", self.dir, drifted])
        self.assertEqual(rc, 1)
        self.assertIn("DRIFT (1 path)", out)
        self.assertIn("/eq/1  PEQ 36.0 +0.00 1.0 -> PEQ 36.0 +3.00 1.0", out)
        self.assertIn("1 DRIFT", out.splitlines()[-1])

    def test_json_mirrors_the_report(self):
        rc, out, _ = _run(["presets-diff", self.dir, ALT, "--json"])
        doc = json.loads(out)
        self.assertEqual(rc, 0 if doc["ok"] else 1)
        self.assertEqual(sum(doc["counts"].values()), 31)
        row = next(p for p in doc["presets"] if p["file"] == "Kick.chn")
        self.assertEqual(set(row), {"file", "status", "name", "channels", "compared",
                                    "drift", "uncompared", "reason"})

    def test_an_unreadable_preset_warns_and_exits_one(self):
        with open(os.path.join(self.dir, "Broken.chn"), "w") as fh:
            fh.write("")
        rc, out, err = _run(["presets-diff", self.dir, SCENE])
        self.assertEqual(rc, 1)
        self.assertIn("warning", err)
        self.assertIn("UNREADABLE", out)
        rc, out, _ = _run(["presets-diff", self.dir, SCENE, "--json"])
        self.assertEqual((rc, json.loads(out)["ok"]), (1, False))

    def test_no_channel_and_ambiguous_do_not_change_the_exit(self):
        with open(os.path.join(self.dir, "Theremin.chn"), "w") as fh:
            fh.write("/eq ON\n")
        doubled = os.path.join(self.root, "doubled.scn")
        _run(["rename", SCENE, "5", "Kick", "-o", doubled])
        rc, out, _ = _run(["presets-diff", self.dir, doubled])
        self.assertEqual(rc, 0)
        self.assertIn("NO CHANNEL ", out)
        self.assertIn("AMBIGUOUS ", out)
        rc, out, _ = _run(["presets-diff", self.dir, doubled, "--json"])
        self.assertEqual((rc, json.loads(out)["ok"]), (0, True))

    def test_a_preset_that_fails_to_parse_warns(self):
        with open(os.path.join(self.dir, "Crlf.chn"), "wb") as fh:
            fh.write(b'/config "Kick" 1 RD 1\r\n')
        with open(os.path.join(self.dir, "Binary.chn"), "wb") as fh:
            fh.write(b"\xff\xfe/config\n")
        rc, out, err = _run(["presets-diff", self.dir, SCENE])
        self.assertEqual(rc, 1)
        self.assertEqual(out.count("UNREADABLE "), 2)
        for name in ("Crlf.chn", "Binary.chn"):
            self.assertIn(f"{name}: ", err)

    def test_a_directory_without_presets_is_an_error(self):
        empty = os.path.join(self.dir, "empty")
        os.makedirs(empty)
        rc, _, err = _run(["presets-diff", empty, SCENE])
        self.assertEqual(rc, 1)
        self.assertIn("no .chn files", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
