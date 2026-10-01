"""What `load` may write: only the parameters a scene or snippet carries, and none its own
header's recall scope leaves out. A refused file is refused before the desk is contacted,
by the library as well as the CLI."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.test_load import BASE, Desk, edited
from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.load import load_scene

SNIP_HEAD = '#4.0# "S" 64 1 0 0 1'    # fader/pan, channel 1 only


class LoadScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def refused(self, name: str, text: str, why: str) -> None:
        """Refused by the CLI with exit 1 and by load_scene with ValueError, nothing sent."""
        path = os.path.join(self.tmp, name)
        with open(path, "w") as fh:
            fh.write(text)
        err = io.StringIO()
        with Desk() as desk, mock.patch.object(O, "X32_PORT", desk.port), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = main(["load", path, "--ip", "127.0.0.1", "--timeout", "0.2"])
            with self.assertRaisesRegex(ValueError, why):
                load_scene(Scene.parse(text), "127.0.0.1", port=desk.port, timeout=0.2,
                           sleep=lambda s: None)
        self.assertEqual(rc, 1, err.getvalue())
        self.assertRegex(err.getvalue(), why)
        self.assertEqual(desk.writes, [])

    def test_desk_actions_preferences_and_status_are_never_written(self):
        for line in ("/-action/initall 1", "/-action/formatcard 1", "/-prefs/ip/addr 10 0 0 99",
                     "/-stat/lock 1", "/-show/showfile/show/chan32 0 0", "/xremote", "/ 1"):
            with self.subTest(line=line):
                path = line.split(" ", 1)[0]
                self.refused("a.scn", BASE + line + "\n", f"{path} is not a scene or snippet")
                self.refused("a.snp", f"{SNIP_HEAD}\n/ch/01/mix/fader -20.0\n{line}\n",
                             f"{path} is not a scene or snippet")

    def test_a_scene_whose_header_marks_a_group_safe_is_refused(self):
        text = edited(headamp_000="/headamp/000 +45.0 ON").replace("%000000000", "%001000000")
        self.refused("safed.scn", text, r"marks Preamp \(HA\) safe")

    def test_a_snippet_line_outside_its_own_masks_is_refused(self):
        for line in ("/ch/02/mix/fader -20.0",    # channel 2: not in the channels mask
                     "/ch/01/mix/on OFF"):        # mute: not in the filters
            with self.subTest(line=line):
                self.refused("a.snp", f"{SNIP_HEAD}\n/ch/01/mix/fader -20.0\n{line}\n",
                             f"{line.split()[0]} is outside the snippet's own masks")

    def test_a_snippet_inside_its_own_masks_still_loads(self):
        with Desk(edited(extra="/ch/01/mix/fader   -6.0")) as desk:
            r = load_scene(Scene.parse(f"{SNIP_HEAD}\n/ch/01/mix/fader -20.0\n"), "127.0.0.1",
                           port=desk.port, timeout=0.2, sleep=lambda s: None)
        self.assertTrue(r.ok)
        self.assertEqual(desk.writes, ["/ch/01/mix/fader -20.0"])


class UnansweredPathsTest(unittest.TestCase):
    def test_a_path_named_unanswered_is_not_asked_again(self):
        real, asked = O.pull_lines, []

        def recording(ip, paths, **kw):
            asked.append(list(paths))
            return real(ip, paths, **kw)
        text = edited(ch_01_mix_01="/ch/01/mix/01 ON  -9.0 +0 PRE 0",
                      extra='/ch/33/config "Ghost" 1 YE 33')
        with Desk(drop_writes=["/ch/01/mix/01"], lacks=["/ch/33/config"]) as desk, \
             mock.patch.object(O, "pull_lines", recording):
            r = load_scene(Scene.parse(text), "127.0.0.1", port=desk.port, timeout=0.2,
                           sleep=lambda s: None)
        self.assertEqual(r.unanswered, ["/ch/33/config"])
        self.assertEqual(len(r.passes), 2)
        self.assertEqual(["ch/33/config" in a for a in asked], [True, True, False])


if __name__ == "__main__":
    unittest.main()
