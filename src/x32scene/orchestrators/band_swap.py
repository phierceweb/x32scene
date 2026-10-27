"""Band-swap orchestrator — re-skin a template scene for a different band/lineup.

One JSON plan drives retitle → routing and sources → presets → renames → head-amps → DCAs
→ IEM-mix copies → per-send trims → output routing via the single-concern transforms.
``verify`` then proves the result differs from the template only in plan-intended paths
before ``run`` saves anything. That stage order is fixed and load-bearing: a copy replaces
the destination send wholesale, so a trim only survives by running after it.

Plan format (every key: ``docs/band-plan.md``)::

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
      "fx":       {"4": {"type": "HALL", "source": "MIX15,MIX16", "params": {"Decay": 2.1}},
                   "2": {"preset": "FX/Plate.efx"}},
      "routing":  {"switch": "REC", "IN": {"1-8": "A1-8"}, "preset": "Routing/Local.rou",
                   "banks": ["CARD"]},
      "output_patch": {"main": {"9": {"src": "bus 12", "pos": "PRE+M"}},
                       "p16":  {"1": {"src": "direct out ch 5"}}},
      "record":   {"5": "Output 9", "17": "local 1"}   // card record track <- source
    }

Within a channel a preset applies first, then the plan's own values, so a named EQ band
wins over the preset's. ``fx``: a ``preset`` or ``type`` resets the slot's parameters to
the console's defaults before ``params``. ``routing``: the ``preset`` banks land first,
then named blocks. ``record`` and a channel ``source`` resolve through the plan's own CARD
and IN blocks, and a head amp lands on the input the channel reads after both. Every value
is checked against the console's own vocabulary before a line is written.

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

from pathlib import Path

from ..model import Scene
from ..services import iem as I
from ..services import transforms as T
from ..services.diff import diff
from ..services.groups import set_dca
from ..services.preset_header import body_lines, preset_selects, unflagged_scopes
from ..services.presets import apply_preset, mirrored_sends, partner_only_sends
from ..services.routing import channel_headamp_index, record_map
from ..services.snippets import MIX_FIELD
from . import (
    _linked_presets, _plan_files, _sections, _sections_record, _sections_routing,
    _sections_sends,
)
from ._plan_files import load_plan as load_plan, plan_inputs as plan_inputs
from ._schema import validate_plan


def apply_plan(scene: Scene, plan: dict) -> dict:
    """Apply a band-swap plan in place. Raises KeyError on channels the scene lacks."""
    validate_plan(plan)
    recorded = dict(record_map(scene)) if plan.get("record") else None
    if "title" in plan:
        T.retitle_scene(scene, plan["title"])
    _sections_routing.apply_routing(scene, plan)
    _sections_routing.apply_sources(scene, plan)
    skipped: dict[int, list[str]] = {}
    for ch_s, spec in sorted(plan.get("channels", {}).items(), key=lambda kv: int(kv[0])):
        ch = int(ch_s)
        if scene.get(f"/ch/{ch:02d}/config") is None:
            raise KeyError(f"channel {ch} not in scene")
        # preset first: a full-scope preset carries /config, and the plan's name must win
        if "preset" in spec:
            text = _plan_files.preset_text(plan, spec)
            apply_preset(scene, ch, text, spec.get("scopes"))
            if unflagged := unflagged_scopes(text, spec.get("scopes")):
                skipped[ch] = unflagged
        if "name" in spec:
            T.rename_channel(scene, ch, spec["name"])
        if "gain_db" in spec or "phantom" in spec:
            idx = channel_headamp_index(scene, ch)
            if idx is None:
                raise KeyError(f"channel {ch} has no head amp (a card, aux, FX, bus or OFF source)")
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
    _sections_sends.apply_sends(scene, plan)
    for out_s, bus in sorted(plan.get("outputs", {}).items(), key=lambda kv: int(kv[0])):
        T.route_output_from_bus(scene, int(out_s), int(bus))
    _sections.apply_fx(scene, plan)
    _sections.apply_output_patch(scene, plan)
    record = _sections_record.apply_record(scene, plan, recorded)
    return {"lines_changed": sum(1 for ln in scene.lines if ln.dirty), "preset_skipped": skipped,
            "record": record,
            "preset_partners": _linked_presets.unmatched_partners(scene, plan, _plan_files.preset_text)}


def allowed_paths(template: Scene, plan: dict) -> set[str]:
    """Every scene path the plan is ALLOWED to change (computed from the template)."""
    allowed: set[str] = set()
    heads = _sections_routing.routed(template, plan)
    if "title" in plan and template.lines:
        allowed.add(template.lines[0].path)   # the header token is its own path: #2.7#..#4.0#
    for ch_s, spec in plan.get("channels", {}).items():
        ch = int(ch_s)
        if "name" in spec:
            allowed.add(f"/ch/{ch:02d}/config")
        if "gain_db" in spec or "phantom" in spec:
            idx = channel_headamp_index(heads, ch)
            if idx is not None:
                allowed.add(f"/headamp/{idx:03d}")
        if "fader" in spec or "mute" in spec:
            allowed.add(f"/ch/{ch:02d}/mix")
        allowed.update(_sections.allowed_channel_proc(ch, spec))
        if "preset" in spec:
            text = _plan_files.preset_text(plan, spec)
            selects = preset_selects(text, spec.get("scopes"))
            allowed.update(p for p, _ in mirrored_sends(template, ch, text, spec.get("scopes")))
            for ln in body_lines(text):   # the parser apply_preset uses, so both agree
                bare = ln.path
                if bare.startswith("/headamp"):
                    if selects(bare):
                        idx = channel_headamp_index(heads, ch)
                        if idx is not None:
                            allowed.add(f"/headamp/{idx:03d}")
                elif selects(bare):
                    split = bare.startswith("/mix/") and bare[len("/mix/"):] in MIX_FIELD
                    allowed.add(f"/ch/{ch:02d}{'/mix' if split else bare}")
    if plan.get("dca"):
        allowed.update(f"/ch/{ch:02d}/grp" for ch in range(1, 33))
    allowed.update(_sections_sends.allowed_sends(template, plan))
    allowed.update(f"/outputs/main/{int(out_s):02d}" for out_s in plan.get("outputs", {}))
    allowed.update(_sections.allowed_sections(plan))
    allowed.update(_sections_routing.allowed_routing(plan))
    allowed.update(_sections_record.allowed_record(plan))
    return allowed


def mirrored_paths(template: Scene, plan: dict) -> set[str]:
    """Send paths the plan writes only because the console mirrors a stereo-linked pair:
    no ``iem_sends`` record, ``iem_copy`` destination or other key names them."""
    mirrors, named = _sections_sends.mirrored_and_named(template, plan)
    presets = {p for ch_s, spec in plan.get("channels", {}).items() if "preset" in spec
               for p in partner_only_sends(template, int(ch_s), _plan_files.preset_text(plan, spec),
                                           spec.get("scopes"))}
    rest = {k: v for k, v in plan.items() if k not in ("iem_sends", "iem_copy")}
    return (mirrors | presets) - named - (allowed_paths(template, rest) - presets)


def verify(template: Scene, edited: Scene, plan: dict) -> dict:
    """Diff the edited scene against the template, flagging out-of-plan changes and any
    send line whose field count no longer matches its bus. ``mirrored`` lists the changed
    paths :func:`mirrored_paths` names."""
    changes = [c.path for c in diff(template, edited)]
    allowed, mirrored = allowed_paths(template, plan), mirrored_paths(template, plan)
    return {"changed": changes,
            "unexpected": [p for p in changes if p not in allowed],
            "mirrored": [p for p in changes if p in mirrored],
            "malformed": I.send_shape_errors(edited, changes)}


def build(template_path: str | Path, plan: dict) -> tuple[Scene, dict]:
    """plan -> apply -> verify. Returns the edited scene and the verify report; raises
    ValueError on out-of-plan or malformed changes."""
    template, edited = Scene.load(str(template_path)), Scene.load(str(template_path))
    summary = apply_plan(edited, plan)
    report = verify(template, edited, plan)
    if report["unexpected"]:
        raise ValueError("out-of-plan changes, nothing written: "
                         + ", ".join(report["unexpected"]))
    if report["malformed"]:
        raise ValueError("malformed send line(s), nothing written: "
                         + ", ".join(report["malformed"]))
    return edited, {**report, **summary}


def run(template_path: str | Path, plan: dict, out_path: str | Path) -> dict:
    """:func:`build`, then save. Returns the verify report; writes nothing on a ValueError."""
    edited, report = build(template_path, plan)
    edited.save(str(out_path))
    return report
