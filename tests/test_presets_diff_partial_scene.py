"""presets-diff on a scene that lacks the named channel's side of a linked send its partner
channel has: the partner channel's sends are not compared, so nothing is read from the
missing line."""

import os
import unittest

from x32scene import Scene
from x32scene.services import preset_library as lib
from x32scene.services.presets import extract_preset

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _scene_without(path: str) -> Scene:
    with open(SCENE, encoding="utf-8", newline="") as fh:
        return Scene.parse("".join(ln + "\n" for ln in fh.read().splitlines()
                                   if ln.split(" ", 1)[0] != path))


class PartialSceneTest(unittest.TestCase):
    def test_presets_diff_reads_a_scene_missing_one_side_of_a_linked_send(self):
        text = "".join(ln + "\n" for ln in extract_preset(Scene.load(SCENE), 11).splitlines()
                       if not ln.startswith("/mix/04 "))
        r = lib.check_preset(_scene_without("/ch/11/mix/04"), "x.chn", text)
        self.assertEqual((r.status, r.drift), (lib.MATCH, []))


if __name__ == "__main__":
    unittest.main()
