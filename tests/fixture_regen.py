"""Regenerate the synthetic example fixtures from the committed ones' structure:

    bin/run python -m tests.fixture_regen

Values come from ``fixture_design`` and ``fixture_wiring`` and reach each scene through the
band-setup plan and the edit services. example-alt.scn is example.scn with a new value at
exactly the fields where the committed pair differs, so the pair's delta keeps its paths.
The preset, snippet, routing and truncated fixtures are cut from the new example.scn.
Run on the committed fixtures it rewrites them byte for byte; ``test_fixture_regen`` holds
it to that.
"""

from __future__ import annotations

import re
from pathlib import Path

from x32scene.model import Line, Scene
from x32scene.orchestrators.band_swap import apply_plan, verify
from x32scene.services import channelfx as F
from x32scene.services import iem as I
from x32scene.services import transforms as T
from x32scene.services.channelfx import _fmt_3sig, _fmt_q, fmt_freq, fmt_gain
from x32scene.services.fx import extract_fx
from x32scene.services.presets import extract_preset
from x32scene.services.routing import channel_headamp_index
from x32scene.services.routing_edit import extract_routing
from x32scene.services.snippets import make_snippet
from x32scene.tables import routing_block_names

from tests import fixture_design as D
from tests import fixture_wiring as W

FIX = Path(__file__).resolve().parent / "fixtures"
SEND = re.compile(r"^(/(?:ch|auxin|fxrtn)/\d\d)/mix/(\d\d)$")
STRUCTURAL = re.compile(r"^(#|/config/(chlink|dp48/link)$|/ch/\d\d/config$)")
WIRING = re.compile(r"^/(config/(routing|userrout)/|outputs/)")
KINDS = [(r"/mix/\d\d$", {0: "onoff", 1: "level", 2: "pan", 3: "tap"}),
         (r"/mix$", {0: "onoff", 1: "level", 3: "pan"}),
         (r"/eq/\d$", {0: "type", 1: "freq", 2: "gain", 3: "q"}),
         (r"/dyn$", {0: "onoff", 4: "half", 5: "ratio", 6: "knee", 7: "makeup", 8: "attack",
                     9: "hold", 10: "release"}),
         (r"/gate$", {0: "onoff", 2: "half", 4: "attack"}),
         (r"/filter$", {0: "onoff", 1: "filter", 2: "freq"}),
         (r"/preamp$", {2: "onoff", 4: "hpf"}),
         (r"^/headamp/", {0: "headamp"})]
CH_PLAN = {("mix", 0): ("mute",), ("mix", 1): ("fader",), ("mix", 3): ("pan",),
           ("preamp", 2): ("lowcut", "on"), ("preamp", 4): ("lowcut", "freq"),
           ("dyn", 4): ("comp", "thr"), ("dyn", 5): ("comp", "ratio"),
           ("dyn", 7): ("comp", "makeup"), ("dyn", 8): ("comp", "attack"),
           ("dyn", 10): ("comp", "release"), ("gate", 2): ("gate", "thr"),
           ("gate", 3): ("gate", "range"), ("gate", 4): ("gate", "attack"),
           ("gate", 6): ("gate", "release")}
EQ_KEYS = ("type", "freq", "gain", "q")
COMP = {0: "on", 2: "det", 4: "thr", 5: "ratio", 6: "knee", 7: "makeup", 8: "attack",
        9: "hold", 10: "release", 13: "mix"}
GATE = {1: "mode", 2: "thr", 3: "rng", 4: "attack", 5: "hold", 6: "release"}
# the desk right-aligns these fields: (path, field) -> width after the separating space
COLUMNS = [(r"^/(ch|auxin|fxrtn|bus|mtx)/\d\d/mix$|^/main/(st|m)/mix$", (1, 5), 5),
           (r"/mix/\d\d$|^/dca/\d$|/delay$|/automix$", (1,), 5), (r"/eq/\d$", (3,), 3),
           (r"^/ch/\d\d/preamp$", (4,), 3), (r"^/ch/\d\d/gate$", (5, 6), 4)]


def fmt(kind: str, v) -> str:
    if kind == "level":
        return T.fmt_level(T.parse_level(v))
    table = {"pan": lambda: f"{v:+d}", "freq": lambda: fmt_freq(v), "gain": lambda: fmt_gain(v),
             "q": lambda: _fmt_q(v), "half": lambda: f"{v:.1f}", "makeup": lambda: _fmt_3sig(v),
             "hold": lambda: _fmt_3sig(v), "hpf": lambda: str(int(v + 0.5)),
             "headamp": lambda: f"{v:+.1f}", "knee": lambda: f"{v:g}",
             "attack": lambda: f"{v:g}", "release": lambda: f"{v:g}"}
    return table[kind]() if kind in table else str(v)


def kind_of(path: str, i: int) -> str:
    return next(k[i] for rx, k in KINDS if re.search(rx, path) and i in k)


def field_delta(a: Scene, b: Scene) -> dict[str, tuple[int, ...]]:
    out = {}
    for la in a.lines:
        lb = b.get(la.path)
        if lb is not None and la.args != lb.args:
            out[la.path] = tuple(i for i, (x, y) in enumerate(zip(la.args, lb.args, strict=True))
                                 if x != y)
    return out


def _card_tracks(scene: Scene, edits: D.Edits) -> dict[int, int]:
    """user-out slot (0-based) -> the record track that reads it once ``edits`` land."""
    card = [edits.get(("/config/routing/CARD", i), t)
            for i, t in enumerate(scene.get("/config/routing/CARD").args)]
    return {int(tok[4:].split("-")[0]) + t % 8 - 1: t + 1 for t in range(32)
            if (tok := card[t // 8]).startswith("UOUT")}


def _num(v):
    return float(v) if isinstance(v, str) and v != "-oo" else v


def _plan(scene: Scene, edits: D.Edits) -> tuple[dict, D.Edits]:
    plan: dict = {}
    rest: D.Edits = {}
    readers = {channel_headamp_index(scene, ch): ch for ch in range(1, 33)}
    tracks, sends = _card_tracks(scene, edits), {}
    for (path, i), v in edits.items():
        m = re.match(r"^/ch/(\d\d)/(eq/\d|mix|preamp|dyn|gate)$", path)
        if m and (m[2], i) in CH_PLAN or m and m[2].startswith("eq/"):
            spec = plan.setdefault("channels", {}).setdefault(str(int(m[1])), {})
            if m[2].startswith("eq/"):
                spec.setdefault("eq", {}).setdefault(m[2][3:], {})[EQ_KEYS[i]] = v
            else:
                *outer, key = CH_PLAN[(m[2], i)]
                for o in outer:
                    spec = spec.setdefault(o, {})
                spec[key] = v == "OFF" if key == "mute" else v == "ON" if key == "on" else v
        elif SEND.match(path) and i < 2:
            sends.setdefault(path, {})[i] = v
        elif path.startswith("/headamp/") and int(path[9:]) in readers:
            plan.setdefault("channels", {}).setdefault(str(readers[int(path[9:])]), {})[
                ("gain_db", "phantom")[i]] = v == "ON" if i == 1 else v
        elif path.startswith("/config/routing/"):
            key = path.rsplit("/", 1)[1]
            plan.setdefault("routing", {}).setdefault(key, {})[routing_block_names(key)[i]] = v
        elif path.startswith("/outputs/"):
            bank, n = path.split("/")[2:4]
            plan.setdefault("output_patch", {}).setdefault(bank, {}).setdefault(str(int(n)), {})[
                ("src", "pos", "invert")[i]] = v == "ON" if i == 2 else v
        elif path == "/config/userrout/out" and i in tracks:
            plan.setdefault("record", {})[str(tracks[i])] = v
        else:
            rest[(path, i)] = v
    groups: dict[frozenset, tuple[str, dict]] = {}
    for path, vals in sorted(sends.items()):
        strip, bus = SEND.match(path).groups()
        line = scene.get(path)
        full = {0: line.args[0], 1: line.args[1], **vals}
        group = frozenset(I.iem_send_targets(scene, strip, int(bus)))
        if group in groups:
            assert groups[group][1] == full, f"{path} breaks its stereo mirror"
            continue
        groups[group] = (path, full)
    plan["iem_sends"] = [{"strip": SEND.match(p)[1], "bus": int(SEND.match(p)[2]),
                          "on": v[0] == "ON", "level": _num(v[1])} for p, v in groups.values()]
    return plan, rest


def _rest(scene: Scene, path: str, i: int, v) -> None:
    strip, _, leaf = path.rpartition("/")
    ln = scene.get(path)
    if (m := SEND.match(path)) and i == 3:
        I.set_send_tap(scene, m[1], int(m[2]), v, linked=False)
    elif path.endswith("/mix") and i < 2:
        (T.set_mute if i == 0 else T.set_fader)(
            scene, strip if leaf == "mix" else path, v == "OFF" if i == 0 else T.parse_level(v),
            linked=False)
    elif path.endswith("/mix") and i == 3:
        T.set_pan(scene, path[:-4], v)
    elif re.search(r"/eq/\d$", path):
        F.set_eq_band(scene, strip[:-3], int(leaf), linked=False, **{EQ_KEYS[i]: v})
    elif leaf == "dyn":
        F.set_comp(scene, strip, linked=False, **{COMP[i]: v == "ON" if i == 0 else v})
    elif leaf == "gate" and i in GATE:
        F.set_gate(scene, strip, linked=False, **{GATE[i]: v})
    elif leaf == "preamp" and i in (2, 3, 4) and strip.startswith("/ch/"):
        key = {2: "on", 3: "slope", 4: "freq"}[i]
        F.set_lowcut(scene, strip, linked=False, **{key: v == "ON" if i == 2 else v})
    elif path.startswith("/headamp/"):
        T.set_headamp_index(scene, int(path[9:]), **({"phantom": v == "ON"} if i == 1
                                                      else {"gain_db": v}))
    else:
        tok = fmt("freq", v) if leaf == "filter" and i == 2 else f"{v:+.1f}" if (
            leaf == "preamp" and i == 0) else fmt("pan", v) if SEND.match(path) else str(v)
        ln.set_arg(i, tok)


def apply(scene: Scene, edits: D.Edits, extra: dict | None = None) -> None:
    plan, rest = _plan(scene, edits)
    plan.update(extra or {})
    before = Scene.parse(scene.dump())
    apply_plan(scene, plan)
    report = verify(before, scene, plan)
    assert not report["unexpected"] and not report["malformed"], report
    for (path, i), v in sorted(rest.items()):
        _rest(scene, path, i, v)


def relayout(scene: Scene, template: Scene) -> None:
    """Restore the template's bytes where tokens came back unchanged; give every other
    line the columns the desk writes."""
    for ln in scene.lines:
        t = template.get(ln.path)
        if t is not None and t.args == ln.args:
            ln.raw, ln.dirty = t.raw, False
            continue
        if not ln.dirty or ln.path.startswith("#"):
            continue
        fields = [" " + f.lstrip(" ") for f in ln.padded_fields()]
        for rx, idx, width in COLUMNS:
            if re.search(rx, ln.path):
                for i in (j for j in idx if j < len(fields)):
                    fields[i] = " " + fields[i][1:].rjust(width)
        if ln.path.endswith("/dyn"):
            fields[10] = " " * (3 if len(fields[10]) == 2 else 2) + fields[10][1:]
        ln.set_fields(fields)


def build_example(tmpl: Scene) -> Scene:
    e = Scene.parse(tmpl.dump())
    apply(e, W.wiring())
    edits: D.Edits = {}
    for ch in range(1, 33):
        D.channel(e, ch, edits)
    D.sends(e, edits)
    D.buses(e, edits)
    D.head_amps(e, edits, {channel_headamp_index(e, ch): ch for ch in range(1, 33)})
    apply(e, edits, {"fx": W.FX, "dca": W.DCA})
    relayout(e, tmpl)
    return e


def build_alt(e: Scene, tmpl_e: Scene, tmpl_a: Scene) -> Scene:
    delta = field_delta(tmpl_e, tmpl_a)
    alt = Scene([Line.parse(tmpl_a.get(ln.path).raw) if ln.path in delta and STRUCTURAL.match(
        ln.path) else ln for ln in Scene.parse(e.dump()).lines])
    edits = W.alt_wiring()
    for path, fields in delta.items():
        if not STRUCTURAL.match(path) and not WIRING.match(path):
            edits.update({(path, i): D.alt_value(kind_of(path, i), alt.get(path).args[i], fmt)
                          for i in fields})
    apply(alt, edits)
    relayout(alt, e)
    assert field_delta(e, alt) == delta, "the alt delta moved"
    return alt


def build() -> dict[str, str]:
    """Every regenerated fixture, by path relative to tests/fixtures."""
    tmpl_e, tmpl_a = (Scene.load(str(FIX / n)) for n in ("example.scn", "example-alt.scn"))
    e = build_example(tmpl_e)
    alt = build_alt(e, tmpl_e, tmpl_a)
    eq = make_snippet(Scene([e.lines[0]]), e, "Example EQ",
                      lambda p: p == "/ch/01/eq" or p.startswith("/ch/01/eq/"))
    out = {"example.scn": e.dump(), "example-alt.scn": alt.dump(),
           "example.chn": extract_preset(e, 1), "example.efx": extract_fx(e, 1, "Example Plate"),
           "example.rou": extract_routing(e, "Example Routing"), "example.snp": eq.scene.dump(),
           "broken/truncated.scn": e.dump()[:40000]}
    for text in out.values():
        assert Scene.parse(text).dump() == text
    assert [ln.path for ln in Scene.parse(out["example.scn"]).lines] == \
        [ln.path for ln in tmpl_e.lines]
    return out


def main() -> None:
    for rel, text in build().items():
        (FIX / rel).write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    main()
