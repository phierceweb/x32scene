"""The console-wide configuration lines in words: monitor/solo, talkback, oscillator,
USB recorder, automix, mono bus, DP48, iQ speakers, output delays and the user-assign
layers. Every token spelling here was read back from a console."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Scene
from ..tables import OUTPUT_BANKS, line_fields
from .userctrl import decode_layer

OSC_DESTS = [f"Mix bus {n}" for n in range(1, 17)] + ["Main L", "Main R", "Main L+R", "Main M/C"] \
    + [f"Matrix {n}" for n in range(1, 7)]
SOLO_SOURCES = ("OFF", "LR", "LR+C", "LRPFL", "LRAFL", "AUX56", "AUX78")
TALK_DESTS = [f"Mix bus {n}" for n in range(1, 17)] + ["Main LR", "Main M/C"]   # destmap bits 0-17
IQ_SPEAKERS = ("none", "iQ8", "iQ10", "iQ12", "iQ15", "iQ15B", "iQ18B")
IQ_EQ = ("Linear", "Live", "Speech", "Playback", "User")


@dataclass
class Section:
    title: str
    rows: list[tuple[str, str]] = field(default_factory=list)


def _fields(scene: Scene, path: str) -> dict[str, str]:
    ln = scene.get(path)
    if ln is None:
        return {}
    names = line_fields(path, len(ln.args)) or []
    return dict(zip(names, ln.args, strict=False))


def _talk_dests(mask: str) -> str:
    bits = mask.lstrip("%")[::-1]
    on = [TALK_DESTS[i] for i, b in enumerate(bits) if b == "1" and i < len(TALK_DESTS)]
    return ", ".join(on) or "none"


def monitor(scene: Scene) -> Section:
    f = _fields(scene, "/config/solo")
    m = _fields(scene, "/config/mono")
    rows = [("source", f.get("source", "?")), ("level", f.get("level", "?")),
            ("source trim", f.get("source trim", "?") + " dB"),
            ("solo modes", f"ch {f.get('ch mode', '?')}, bus {f.get('bus mode', '?')}, "
                           f"dca {f.get('dca mode', '?')}"),
            ("exclusive solo", f.get("exclusive", "?")),
            ("follow select / follow solo", f"{f.get('follow select', '?')} / "
                                            f"{f.get('follow solo', '?')}"),
            ("dim", f"{f.get('dim', '?')} ({f.get('dim att', '?')} dB, PFL dim "
                    f"{f.get('dim pfl', '?')})"),
            ("mono / delay", f"{f.get('mono', '?')} / {f.get('delay', '?')} "
                             f"{f.get('delay time', '?')} ms"),
            ("master control / mute", f"{f.get('master ctrl', '?')} / {f.get('mute', '?')}"),
            ("mono bus", f"{m.get('mode', '?')}, linked to LR {m.get('link', '?')}")]
    return Section("Monitor", rows)


def talkback(scene: Scene) -> Section:
    t = _fields(scene, "/config/talk")
    rows = [("enabled", t.get("enable", "?")), ("source", t.get("source", "?"))]
    for side in "AB":
        s = _fields(scene, f"/config/talk/{side}")
        rows.append((f"talk {side}", f"{s.get('level', '?')} dB, dim {s.get('dim', '?')}, "
                                     f"latch {s.get('latch', '?')}, to "
                                     f"{_talk_dests(s.get('dest', ''))}"))
    return Section("Talkback", rows)


def oscillator(scene: Scene) -> Section:
    o = _fields(scene, "/config/osc")
    dest = o.get("dest", "")
    where = OSC_DESTS[int(dest)] if dest.isdigit() and int(dest) < len(OSC_DESTS) else dest
    return Section("Oscillator", [
        ("type", o.get("type", "?")), ("level", o.get("level", "?")),
        ("frequency", f"F1 {o.get('f1', '?')} / F2 {o.get('f2', '?')} (using "
                      f"{o.get('f sel', '?')})"),
        ("destination", where)])


def recorder_and_automix(scene: Scene) -> Section:
    t = _fields(scene, "/config/tape")
    a = _fields(scene, "/config/amixenable")
    return Section("USB recorder and automix", [
        ("recorder gain", f"L {t.get('gain L', '?')} / R {t.get('gain R', '?')} dB"),
        ("autoplay", t.get("autoplay", "?")),
        ("automix groups", f"X {a.get('X', '?')}, Y {a.get('Y', '?')}")])


def dp48(scene: Scene) -> Section:
    d = _fields(scene, "/config/dp48")
    names = scene.get("/config/dp48/grpname")
    groups = [n.strip('"') for n in (names.args if names else [])]
    named = ", ".join(f"{i}: {g}" for i, g in enumerate(groups, start=1) if g) or "none named"
    return Section("DP48 personal monitoring", [
        ("broadcast port", d.get("aes port", "?")), ("scope", d.get("scope", "?")),
        ("groups", named)])


def output_delays(scene: Scene) -> Section:
    rows = []
    for bank in OUTPUT_BANKS:
        for n in range(1, OUTPUT_BANKS[bank][0] + 1):
            d = _fields(scene, f"/outputs/{bank}/{n:02d}/delay")
            if d.get("on") == "ON":
                rows.append((f"{bank} {n:02d}", f"{d.get('time', '?')} ms"))
    return Section("Output delays", rows or [("(none engaged)", "")])


def iq_speakers(scene: Scene) -> Section:
    rows = []
    for n in range(1, 17):
        q = _fields(scene, f"/outputs/p16/{n:02d}/iQ")
        if q and q.get("speaker", "none") != "none":
            rows.append((f"p16 {n:02d}", f"group {q.get('group')}, {q.get('speaker')}, "
                                        f"EQ {q.get('eq')}, model {q.get('model')}"))
    return Section("iQ speakers on P16", rows or [("(none configured)", "")])


def user_assign(scene: Scene) -> Section:
    rows = []
    for layer in "ABC":
        colour = _fields(scene, f"/config/userctrl/{layer}").get("colour", "?")
        enc = scene.get(f"/config/userctrl/{layer}/enc")
        btn = scene.get(f"/config/userctrl/{layer}/btn")
        rows.append((f"set {layer}", f"colour {colour}"))
        for k, v in decode_layer(enc.args if enc else [], btn.args if btn else []).items():
            rows.append((f"  {layer} {k}", v))
    return Section("User assign", rows)


def console_sections(scene: Scene) -> list[Section]:
    return [monitor(scene), talkback(scene), oscillator(scene), recorder_and_automix(scene),
            dp48(scene), output_delays(scene), iq_speakers(scene), user_assign(scene)]
