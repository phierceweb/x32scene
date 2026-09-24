"""The `ports` header states only the jack count: whether a virtual output leaves the console
depends on the scene's routing, which the rows (mirrors) and `preflight` (require_reachable)
report, so the header never claims an AES50 path."""

import contextlib
import io
import os
import unittest

from x32scene._views_ports import cmd_ports
from x32scene.model import Scene

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def header(path: str, physical: int) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cmd_ports(Scene.load(path), physical)
    return out.getvalue().splitlines()[0]


class PortsHeaderTest(unittest.TestCase):
    def test_no_aes50_claim_for_a_scene_with_no_out_block_on_either_port(self):
        line = header(os.path.join(FIXTURES, "example-alt.scn"), 8)
        self.assertEqual(line, "Outputs (main 1-8 = physical jacks; 9-16 = virtual):")

    def test_the_same_header_whatever_the_routing(self):
        self.assertEqual(header(os.path.join(FIXTURES, "example.scn"), 12),
                         "Outputs (main 1-12 = physical jacks; 13-16 = virtual):")


if __name__ == "__main__":
    unittest.main()
