"""A JSON boolean must never be read as a number anywhere in a plan.

`isinstance(True, int)` is true in Python, so an unguarded numeric check reads `false` as
0 — in a plan, silent damage at exit 0 rather than a refusal.

Top-level keys come from the schema's own key sets, so a new one is covered as soon as it
is added; nested values are listed in NESTED and have to be added by hand.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from x32scene.cli import main
from x32scene.model import Scene
from x32scene.orchestrators import _sections
from x32scene.orchestrators._schema import CHANNEL_KEYS, IEM_SEND_KEYS, PLAN_KEYS

SCENE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")

# The only plan values a boolean legitimately names.
BOOL_KEYS = frozenset({"phantom", "mute", "invert", "on"})


NESTED = [
    ("channels.1.eq.1.{k}", ("type", "freq", "gain", "q"),
     lambda k, v: {"channels": {"1": {"eq": {"1": {k: v}}}}}),
    ("channels.1.comp.{k}", ("thr", "ratio", "makeup", "attack", "release"),
     lambda k, v: {"channels": {"1": {"comp": {k: v}}}}),
    ("channels.1.gate.{k}", ("thr", "range", "attack", "release"),
     lambda k, v: {"channels": {"1": {"gate": {k: v}}}}),
    ("channels.1.lowcut.freq", ("freq",),
     lambda k, v: {"channels": {"1": {"lowcut": {k: v}}}}),
    ("fx.1.params.{k}", ("Decay",),
     lambda k, v: {"fx": {"1": {"type": "PLAT", "params": {k: v}}}}),
    ("routing.IN.{k}", ("1-8",),
     lambda k, v: {"routing": {"IN": {k: v}}}),
    ("dca.1[]", ("",), lambda k, v: {"dca": {"1": [v]}}),
    ("outputs.1", ("",), lambda k, v: {"outputs": {"1": v}}),
    ("iem_copy[].src", ("src",), lambda k, v: {"iem_copy": [{k: v, "dst": 2}]}),
    ("iem_copy[].dst", ("dst",), lambda k, v: {"iem_copy": [{"src": 1, k: v}]}),
    ("channels.1.scopes[]", ("",), lambda k, v: {"channels": {"1": {"scopes": [v]}}}),
]

# iem_sends is validated field by field, so a probe needs a valid base record or it is
# rejected for a missing field and never reaches the value under test
IEM_BASE = {"strip": 23, "bus": 5, "level": -14.0, "on": True}


def plans_with_a_bool(value):
    """(where, plan) for every scalar plan value, nested ones included."""
    for key in sorted(PLAN_KEYS - {"channels", "dca", "iem_copy", "iem_sends", "outputs",
                                   "fx", "routing", "output_patch"}):
        yield key, {key: value}
    for key in sorted(CHANNEL_KEYS - BOOL_KEYS):
        yield f"channels.1.{key}", {"channels": {"1": {key: value}}}
    for key in sorted(_sections.OUTPUT_KEYS - BOOL_KEYS):
        yield f"output_patch.main.9.{key}", {"output_patch": {"main": {"9": {key: value}}}}
    for key in sorted(_sections.FX_KEYS - BOOL_KEYS):
        yield f"fx.1.{key}", {"fx": {"1": {key: value}}}
    for key in sorted(_sections.ROUTING_KEYS - BOOL_KEYS):
        yield f"routing.{key}", {"routing": {key: value}}
    for key in sorted(IEM_SEND_KEYS - BOOL_KEYS):
        yield f"iem_sends.{key}", {"iem_sends": [{**IEM_BASE, key: value}]}
    for label, keys, build in NESTED:
        for k in keys:
            yield label.replace("{k}", k), build(k, value)


class BooleanIsNeverANumberTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.scene = os.path.join(self.dir, "t.scn")
        shutil.copy(SCENE, self.scene)
        self.before = open(self.scene, "rb").read()

    def _run_plan(self, plan):
        path = os.path.join(self.dir, "p.json")
        out = os.path.join(self.dir, "out.scn")
        with open(path, "w") as fh:
            json.dump(plan, fh)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = main(["band-setup", self.scene, path, "-o", out])
        wrote = os.path.exists(out)
        if wrote:
            os.remove(out)
        return rc, err.getvalue(), wrote

    def test_no_plan_key_accepts_a_boolean_as_a_value(self):
        for value in (True, False):
            for where, plan in plans_with_a_bool(value):
                plan.setdefault("title", "Bool Probe")
                with self.subTest(key=where, value=value):
                    rc, err, wrote = self._run_plan(plan)
                    self.assertEqual(rc, 2, f"{where}={value!r} was accepted: {err}")
                    self.assertIn("nothing written", err)
                    self.assertFalse(wrote)

    def test_the_two_encoders_refuse_one_directly(self):
        from x32scene.services import routing_edit as rt
        for value in (True, False):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    rt.encode_input_source(value)
                with self.assertRaises(ValueError):
                    rt.encode_tap(value)

    def test_the_scene_is_untouched_by_every_rejected_plan(self):
        for _where, plan in plans_with_a_bool(False):
            plan.setdefault("title", "Bool Probe")
            self._run_plan(plan)
        self.assertEqual(open(self.scene, "rb").read(), self.before)

    def test_the_keys_that_do_take_a_boolean_still_work(self):
        """The gate must not have been passed by refusing booleans everywhere."""
        out = os.path.join(self.dir, "ok.scn")
        plan = {"title": "Bool Probe",
                "channels": {"1": {"phantom": True, "mute": False}},
                "output_patch": {"main": {"9": {"invert": True}}}}
        path = os.path.join(self.dir, "ok.json")
        with open(path, "w") as fh:
            json.dump(plan, fh)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = main(["band-setup", self.scene, path, "-o", out])
        self.assertEqual(rc, 0)
        sc = Scene.load(out)
        self.assertEqual(sc.get("/headamp/000").args[1], "ON")        # phantom: true
        self.assertEqual(sc.get("/ch/01/mix").args[0], "ON")          # mute: false
        self.assertEqual(sc.get("/outputs/main/09").args[2], "ON")    # invert: true


if __name__ == "__main__":
    unittest.main()


class PlanErrorsNameTheFieldTest(unittest.TestCase):
    """A rejection must say which plan value was wrong. Without a type check the value
    still reaches Python and raises — caught, but reported as `__fspath__` or "argument
    of type 'bool' is not iterable", which tells the user nothing."""

    RAW_PYTHON = ("__fspath__", "not iterable", "unsupported operand", "object is not",
                  "must be str, not")

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.scene = os.path.join(self.dir, "t.scn")
        shutil.copy(SCENE, self.scene)

    def _message(self, plan):
        path = os.path.join(self.dir, "p.json")
        with open(path, "w") as fh:
            json.dump(plan, fh)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            main(["band-setup", self.scene, path, "-o", os.path.join(self.dir, "o.scn")])
        return err.getvalue()

    def test_untyped_values_are_named_not_raised_through(self):
        cases = [
            ("title", {"title": False}, "title"),
            ("title as a list", {"title": ["a"]}, "title"),
            ("channels.name", {"title": "P", "channels": {"1": {"name": False}}}, "name"),
            ("channels.preset", {"title": "P", "channels": {"1": {"preset": False}}}, "preset"),
            ("fx.preset", {"title": "P", "fx": {"1": {"preset": False}}}, "preset"),
            ("routing.preset", {"title": "P", "routing": {"preset": False}}, "preset"),
        ]
        for label, plan, field in cases:
            with self.subTest(case=label):
                msg = self._message(plan)
                self.assertIn(field, msg)
                for fragment in self.RAW_PYTHON:
                    self.assertNotIn(fragment, msg, f"{label} leaked a raw Python error")
