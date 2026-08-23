"""Band-swap orchestrator — re-skin a template scene for a different band/lineup.

One JSON plan drives retitle → channel presets → renames → head-amps → DCA reassignment
→ IEM-mix copies → per-send trims → output routing via the single-concern transforms.
``verify`` then proves the result differs from the template only in plan-intended paths
before ``run`` saves anything. That stage order is fixed and load-bearing: a copy replaces
the destination send wholesale, so a trim only survives by running after it.

Plan format::

    {
      "title": "Example Rig - 2026-07-04",
      "channels": {
        "1":  {"name": "Kick", "gain_db": 20.0, "phantom": false},
        "20": {"name": "Gtr 2", "preset": "Channel/Guitar.chn", "scopes": ["eq", "comp"],
               "fader": "-oo", "mute": true}
      },
      "dca":       {"3": [19, 20, 21, 22]},    // full member list per listed DCA
      "iem_copy":  [{"src": 1, "dst": 5}],     // duplicate a player's monitor mix
      "iem_sends": [{"strip": 23, "bus": 5, "level": -14.0}],   // trim one send in one mix
      "outputs":   {"9": 1, "10": 2},          // route physical output <- mix bus
      // processing per channel (inside "channels"): "eq": {"2": {"freq": 100, "gain": 6}},
      // "comp": {"thr": -18, "ratio": "3"}, "gate": {...}, "lowcut": {"on": true, "freq": 80},
      // "pan": -30, "source": "aes50-a 3"
      "fx":       {"4": {"type": "HALL", "source": "MIX15,MIX16", "params": {"Decay": 2.1}},
                   "2": {"preset": "FX/Plate.efx"}},
      "routing":  {"switch": "REC", "IN": {"1-8": "A1-8"}, "preset": "Routing/Local.rou",
                   "banks": ["CARD"]},
      "output_patch": {"main": {"9": {"src": "bus 12", "pos": "PRE+M"}},
                       "p16":  {"1": {"src": "direct out ch 5"}}}
    }

Within a channel a preset applies first, then the plan's own values, so a named EQ band
wins over the preset's. ``fx``: a ``preset`` or ``type`` resets the slot's parameters to
the console's defaults before ``params``. ``routing``: the ``preset`` banks land first,
then named blocks. Every value is checked against the console's own vocabulary before a
line is written.

An ``iem_sends`` record names a channel number or any send strip ("/auxin/05",
"/fxrtn/03"), a level in dB (or ``"-oo"``; a quoted number like "-6.0" is not a level) and
/or ``on``. Both value fields are independent, so a level alone trims a send where it sits
and ``on`` alone cannot be used to add a channel blind — putting a strip into a mix takes
both. A level alone on a send that is currently OFF raises: it would change nothing
audible. Each record writes every send the console mirrors it to — both sides of a stereo
bus pair and of a stereo strip pair — so name only one side of a pair, or the two records
collide.

``outputs`` reaches ``/outputs/main/1-16`` only; the ``/outputs/aux`` bank is not routable
from a plan.

Preset paths are resolved relative to the plan file's directory (absolute paths win).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..model import Line, Scene
from ..services import iem as I
from ..services import transforms as T
from ..services.diff import diff
from ..services.groups import set_dca
from ..services.presets import apply_preset
from . import _sections
from ._schema import _send_strip, validate_plan
from ..services.routing import channel_headamp_index
from ..services.scopes import SCOPES, scope_of
from ..tables import SEND_STRIPS




def load_plan(path: str | Path) -> dict:
    p = Path(path)
    plan = json.loads(p.read_text(encoding="utf-8"))
    plan["_dir"] = p.parent
    return plan


def _send_targets(scene: Scene, plan: dict) -> dict[tuple[str, int], tuple[dict, tuple]]:
    """Every send line the plan's ``iem_sends`` write, mapped to ``(set_iem_send kwargs,
    the target the record itself named)``.

    apply_plan and allowed_paths both expand through this, so the write set and the
    whitelist cannot drift. They agree on link state because no plan key writes
    /config/chlink or /config/buslink.
    """
    targets: dict[tuple[str, int], tuple[dict, tuple]] = {}
    for rec in plan.get("iem_sends", []):
        named = (_send_strip(rec["strip"]), int(rec["bus"]))
        kwargs = {"on": rec.get("on"),
                  "level_db": T.parse_level(rec["level"]) if "level" in rec else None}
        for tgt in I.iem_send_targets(scene, named[0], named[1]):
            if tgt != named and scene.get(f"{tgt[0]}/mix/{tgt[1]:02d}") is None:
                continue   # a mirror the scene lacks is not the plan's problem
            if tgt in targets:
                other = targets[tgt][1]
                raise ValueError(
                    f"iem_sends: {named[0]} -> bus {named[1]} and {other[0]} -> bus "
                    f"{other[1]} both write {tgt[0]} bus {tgt[1]} — a stereo-linked pair "
                    "shares one send, so name only one side of it")
            targets[tgt] = (kwargs, named)
    return targets


def _preset_text(plan: dict, spec: dict) -> str:
    p = Path(spec["preset"])
    if not p.is_absolute():
        p = Path(plan.get("_dir", ".")) / p
    try:
        return p.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"preset {p}: {e.strerror}") from e


def apply_plan(scene: Scene, plan: dict) -> dict:
    """Apply a band-swap plan in place. Raises KeyError on channels the scene lacks."""
    validate_plan(plan)
    if "title" in plan:
        T.retitle_scene(scene, plan["title"])
    for ch_s, spec in sorted(plan.get("channels", {}).items(), key=lambda kv: int(kv[0])):
        ch = int(ch_s)
        if scene.get(f"/ch/{ch:02d}/config") is None:
            raise KeyError(f"channel {ch} not in scene")
        # preset first: a full-scope preset carries /config, and the plan's name must win
        if "preset" in spec:
            apply_preset(scene, ch, _preset_text(plan, spec), spec.get("scopes"))
        if "name" in spec:
            T.rename_channel(scene, ch, spec["name"])
        if "gain_db" in spec or "phantom" in spec:
            idx = channel_headamp_index(scene, ch)
            if idx is None:
                raise KeyError(f"channel {ch} has no head amp (card/aux source?)")
            T.set_headamp_index(scene, idx, spec.get("gain_db"), spec.get("phantom"))
        # linked=False: a plan names its channels explicitly, so a mirror would be a path
        # the plan never asked for
        if "fader" in spec:
            T.set_fader(scene, ch, T.parse_level(spec["fader"]), linked=False)
        if "mute" in spec:
            T.set_mute(scene, ch, bool(spec["mute"]), linked=False)
        _sections.apply_channel_proc(scene, ch, spec)
    for dca_s, members in sorted(plan.get("dca", {}).items(), key=lambda kv: int(kv[0])):
        d, want = int(dca_s), set(members)
        for ch in range(1, 33):
            if scene.get(f"/ch/{ch:02d}/grp") is None:
                if ch in want:
                    raise KeyError(f"channel {ch} has no /grp line for DCA {d}")
                continue
            set_dca(scene, ch, d, ch in want)
    for cp in plan.get("iem_copy", []):
        I.copy_iem_mix(scene, int(cp["src"]), int(cp["dst"]))
    # after iem_copy: a copy replaces the destination send wholesale, erasing a trim
    for (path, bus), (kw, named) in _send_targets(scene, plan).items():
        line = scene.get(f"{path}/mix/{bus:02d}")
        if line is None:
            raise KeyError(f"no send {path}->bus{bus}")
        # only the send the plan NAMED has to be on: a mirror may sit OFF on its own
        if (path, bus) == named and kw["on"] is None and line.args[0] == "OFF":
            raise ValueError(f"iem_sends: {path} -> bus {bus}: send is OFF, so a level "
                             'alone changes nothing — add "on": true')
        I.set_iem_send(scene, path, bus, **kw)
    for out_s, bus in sorted(plan.get("outputs", {}).items(), key=lambda kv: int(kv[0])):
        T.route_output_from_bus(scene, int(out_s), int(bus))
    _sections.apply_fx(scene, plan)
    _sections.apply_routing(scene, plan)
    _sections.apply_output_patch(scene, plan)
    return {"lines_changed": sum(1 for ln in scene.lines if ln.dirty)}


def allowed_paths(template: Scene, plan: dict) -> set[str]:
    """Every scene path the plan is ALLOWED to change (computed from the template)."""
    allowed: set[str] = set()
    if "title" in plan and template.lines:
        allowed.add(template.lines[0].path)   # the header token is its own path: #2.7#..#4.0#
    for ch_s, spec in plan.get("channels", {}).items():
        ch = int(ch_s)
        if "name" in spec:
            allowed.add(f"/ch/{ch:02d}/config")
        if "gain_db" in spec or "phantom" in spec:
            idx = channel_headamp_index(template, ch)
            if idx is not None:
                allowed.add(f"/headamp/{idx:03d}")
        if "fader" in spec or "mute" in spec:
            allowed.add(f"/ch/{ch:02d}/mix")
        allowed.update(_sections.allowed_channel_proc(ch, spec))
        if "preset" in spec:
            sel = set(spec.get("scopes") or SCOPES)
            for raw in _preset_text(plan, spec).splitlines():
                if not raw or raw.startswith("#"):
                    continue
                bare = Line.parse(raw).path   # the parser apply_preset uses, so both agree
                if bare.startswith("/headamp"):
                    if "ha" in sel:
                        idx = channel_headamp_index(template, ch)
                        if idx is not None:
                            allowed.add(f"/headamp/{idx:03d}")
                elif scope_of(bare) in sel:
                    allowed.add(f"/ch/{ch:02d}{bare}")
    if plan.get("dca"):
        allowed.update(f"/ch/{ch:02d}/grp" for ch in range(1, 33))
    for cp in plan.get("iem_copy", []):
        # exactly the buses the copy writes: a wider grant lets a stray send pass unflagged
        for bus in I.copy_iem_dst_buses(template, int(cp["src"]), int(cp["dst"])):
            allowed.update(f"{strip}/mix/{bus:02d}" for strip in SEND_STRIPS)
    allowed.update(f"{path}/mix/{bus:02d}" for path, bus in _send_targets(template, plan))
    allowed.update(f"/outputs/main/{int(out_s):02d}" for out_s in plan.get("outputs", {}))
    allowed.update(_sections.allowed_sections(plan))
    return allowed


def verify(template: Scene, edited: Scene, plan: dict) -> dict:
    """Diff the edited scene against the template, flagging out-of-plan changes and any
    send line whose field count no longer matches its bus."""
    changes = [c.path for c in diff(template, edited)]
    allowed = allowed_paths(template, plan)
    return {"changed": changes,
            "unexpected": [p for p in changes if p not in allowed],
            "malformed": I.send_shape_errors(edited, changes)}


def run(template_path: str | Path, plan: dict, out_path: str | Path) -> dict:
    """plan -> apply -> verify -> save. Returns the verify report; raises ValueError on
    out-of-plan or malformed changes, having written nothing."""
    template, edited = Scene.load(str(template_path)), Scene.load(str(template_path))
    summary = apply_plan(edited, plan)
    report = verify(template, edited, plan)
    if report["unexpected"]:
        raise ValueError("out-of-plan changes, nothing written: "
                         + ", ".join(report["unexpected"]))
    if report["malformed"]:
        raise ValueError("malformed send line(s), nothing written: "
                         + ", ".join(report["malformed"]))
    edited.save(str(out_path))
    return {**report, **summary}
