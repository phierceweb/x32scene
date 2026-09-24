"""Which main outputs reach a rear XLR jack follows /config/routing/OUT, not the output's
number: jacks 1-4 can carry main 9-12, a jack can carry a user-out slot naming an output,
and a jack patched to an input bank carries no main output. ports, report and preflight's
reachability check read it."""

import contextlib
import io
import json
import os
import tempfile
import unittest

from x32scene import Scene
from x32scene.cli import main
from x32scene.services.preflight import preflight
from x32scene.services.routing import jack_outputs

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def patched(out_line: str | None, **slots: int) -> Scene:
    """example.scn with /config/routing/OUT set (None drops it) and user-out slots set."""
    sc = Scene.load(EXAMPLE)
    if out_line is None:
        sc.lines = [ln for ln in sc.lines if ln.path != "/config/routing/OUT"]
        sc._reindex()
    else:
        ln = sc.get("/config/routing/OUT")
        for i, tok in enumerate(out_line.split()):
            ln.set_arg(i, tok)
    uout = sc.get("/config/userrout/out")
    for slot, value in slots.items():
        uout.set_arg(int(slot[1:]) - 1, str(value))
    return sc


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = main(list(argv))
    return rc, out.getvalue()


class JackOutputsTest(unittest.TestCase):
    def test_the_in_order_patch_is_the_output_number(self):
        self.assertEqual(jack_outputs(Scene.load(EXAMPLE), 8), {n: n for n in range(1, 9)})
        self.assertEqual(jack_outputs(patched(None), 16), {n: n for n in range(1, 17)})

    def test_jacks_1_to_4_can_carry_main_9_to_12(self):
        sc = patched("OUT9-12 OUT5-8 OUT1-4 OUT13-16")
        self.assertEqual(jack_outputs(sc, 8), {9: 1, 10: 2, 11: 3, 12: 4, 5: 5, 6: 6, 7: 7, 8: 8})

    def test_a_user_out_slot_naming_an_output_carries_it(self):
        sc = patched("UOUT1-4 OUT5-8 OUT9-12 OUT13-16", s1=168 + 13, s2=168 + 14, s3=0, s4=5)
        self.assertEqual(jack_outputs(sc, 8), {13: 1, 14: 2, 5: 5, 6: 6, 7: 7, 8: 8})

    def test_an_input_bank_carries_no_main_output(self):
        sc = patched("AN1-4 OUT5-8 OUT9-12 OUT13-16")
        self.assertEqual(sorted(jack_outputs(sc, 8)), [5, 6, 7, 8])


class RearJackViewsTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: [os.remove(os.path.join(d, f)) for f in os.listdir(d)]
                       or os.rmdir(d))
        self.scene = os.path.join(d, "patched.scn")
        patched("OUT9-12 OUT5-8 OUT1-4 OUT13-16").save(self.scene)

    def test_ports_json_follows_the_patch(self):
        rc, out = run("ports", self.scene, "--console", "X32RACK", "--json")
        self.assertEqual(rc, 0)
        rows = {r["n"]: r for r in json.loads(out)["outputs"]}
        self.assertEqual((rows[9]["physical"], rows[9]["jack"]), (True, 1))
        self.assertEqual((rows[1]["physical"], rows[1]["jack"]), (False, None))
        self.assertEqual((rows[5]["physical"], rows[5]["jack"]), (True, 5))

    def test_ports_text_names_a_moved_jack(self):
        rc, out = run("ports", self.scene, "--console", "X32RACK")
        self.assertEqual(rc, 0)
        line9 = next(ln for ln in out.splitlines() if "main 09" in ln)
        line1 = next(ln for ln in out.splitlines() if "main 01" in ln)
        self.assertIn("[XLR ]", line9)
        self.assertIn("rear jack 1", line9)
        self.assertIn("[virt]", line1)

    def test_reachability_asks_of_every_output_no_jack_carries(self):
        sc = Scene.load(self.scene)
        for n in (1, 2, 3, 4):   # leave main 1-4 on no AES50, card or user-out path
            sc.get(f"/outputs/main/{n:02d}").set_arg(0, "4")
        for key in ("AES50A", "AES50B", "CARD"):
            ln = sc.get(f"/config/routing/{key}")
            for i, tok in enumerate(ln.args):
                if tok.startswith("OUT1-8") or tok.startswith("OUT1-4"):
                    ln.set_arg(i, "AN1-8")
        uout = sc.get("/config/userrout/out")
        for i, v in enumerate(uout.args):
            if v in {str(168 + n) for n in (1, 2, 3, 4)} or v in {"1", "2", "3", "4"}:
                uout.set_arg(i, "0")
        fails = {f.area for f in preflight(sc, {"monitor": {"physical_outputs": 8,
                                                            "require_reachable": True}})
                 if f.severity == "FAIL"}
        self.assertTrue({f"out main {n:02d}" for n in (1, 2, 3, 4)} <= fails, fails)
        self.assertFalse({f"out main {n:02d}" for n in (9, 10, 11, 12)} & fails, fails)


if __name__ == "__main__":
    unittest.main()
