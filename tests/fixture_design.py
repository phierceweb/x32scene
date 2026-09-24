"""The synthetic mix the example scenes carry. Not collected by pytest.

Every value is drawn from a seeded generator on the console's own control grids, so it
owes nothing to any real scene; only the template's structure (strip names, link lines)
is read. ``fixture_regen`` writes these values through the band-setup plan and the edit
services.
"""

from __future__ import annotations

import random

from x32scene.model import Scene
from x32scene.services.channelfx import COMP_RATIOS, EQ_TYPES, pair_linked
from x32scene.tables import SEND_STRIPS

Edits = dict[tuple[str, int], object]


def rng(*key: object) -> random.Random:
    return random.Random("|".join(map(str, ("x32scene-fixture", *key))))


def _pick(r: random.Random, grid: list[float], lo: float, hi: float) -> float:
    return r.choice([v for v in grid if lo <= v <= hi])


def _fader(i: int) -> float:
    f = i / 1023
    db = 40 * f - 30 if f >= 0.5 else 80 * f - 50 if f >= 0.25 else (
        160 * f - 70 if f >= 0.0625 else 480 * f - 90)
    return round(db, 1)


FREQ = [20 * 1000 ** (i / 200) for i in range(201)]
HPF = [20 * 20 ** (i / 100) for i in range(101)]
Q = [10 * 0.03 ** (i / 71) for i in range(72)]
HOLD = [0.02 * 10 ** (i / 20) for i in range(101)]
RELEASE = [round(5 * 800 ** (i / 100)) for i in range(101)]
LEVEL = sorted({_fader(i) for i in range(1, 1024)})
HALF = [i / 2 for i in range(-180, 121)]
QUARTER = [i / 4 for i in range(-60, 61)]
FILTERS = ("LC6", "LC12", "HC6", "HC12", "1.0", "2.0", "3.0", "5.0", "10.0")
FILTER_REST = ("OFF", "3.0", 990.9)

ROLE = {1: "kick", 2: "kick", 3: "snare", 4: "snare", **dict.fromkeys(range(5, 11), "tom"),
        11: "oh", 12: "oh", 13: "cymbal", 14: "cymbal", 15: "room", 16: "room",
        17: "bass", 18: "bass", 19: "gtr", 20: "gtr", 21: "gtr", 22: "gtr",
        **dict.fromkeys(range(23, 27), "vox"), 27: "trig", 28: "trig", 29: "spare",
        30: "click", 31: "daw", 32: "daw"}
PAN = {5: -40, 6: -20, 7: 10, 8: 30, 9: 50, 10: 60, 11: -70, 12: 70, 13: -30, 14: 40,
       15: -100, 16: 100, 19: -50, 20: -50, 21: 50, 22: 50, 24: -20, 25: 20, 26: -10,
       27: -100, 28: 100, 31: -100, 32: 100}
# role: low cut (on, lo, hi) Hz, gate on, comp on, eq bands (type, lo, hi Hz, dB lo, dB hi)
SPEC = {
    "kick": ((True, 20, 40), True, True, [("PEQ", 45, 80, 2, 6), ("PEQ", 250, 450, -9, -3),
                                          ("PEQ", 2000, 5000, 2, 7), ("HShv", 8000, 12000, -4, 1)]),
    "snare": ((True, 60, 110), True, True, [("PEQ", 150, 260, 1, 4), ("PEQ", 400, 900, -6, -1),
                                            ("PEQ", 3000, 6000, 1, 5), ("HShv", 8000, 12000, 1, 4)]),
    "tom": ((True, 50, 90), True, False, [("PEQ", 80, 150, 2, 5), ("PEQ", 300, 600, -7, -2),
                                          ("PEQ", 2500, 5000, 1, 4), ("HCut", 9000, 14000, 0, 0)]),
    "oh": ((True, 120, 250), False, False, [("LShv", 150, 300, -4, -1), ("PEQ", 400, 900, -3, 0),
                                             ("PEQ", 2500, 5000, -2, 2), ("HShv", 9000, 13000, 1, 3)]),
    "bass": ((True, 20, 35), False, True, [("LShv", 50, 90, 1, 4), ("PEQ", 200, 400, -5, -1),
                                           ("PEQ", 700, 1500, 1, 4), ("HCut", 5000, 9000, 0, 0)]),
    "gtr": ((True, 70, 120), False, True, [("PEQ", 120, 250, -3, 1), ("PEQ", 400, 800, -4, 0),
                                           ("PEQ", 2000, 4500, 1, 4), ("HShv", 6000, 10000, -4, 0)]),
    "vox": ((True, 80, 130), False, True, [("PEQ", 150, 300, -4, -1), ("PEQ", 400, 900, -3, 0),
                                           ("PEQ", 2500, 5000, 1, 4), ("HShv", 9000, 12000, 1, 3)]),
}
for _role in ("cymbal", "room"):
    SPEC[_role] = SPEC["oh"]
for _role in ("trig", "click", "daw"):
    SPEC[_role] = ((False, 20, 30), False, False, SPEC["gtr"][3])
SPEC["spare"] = ((False, 20, 20), False, False, None)
REST_BANDS = [("PEQ", 124.7), ("PEQ", 496.6), ("PEQ", 1970.0), ("HShv", 10020.0)]
BUS_BANDS = [("LShv", 79.6), ("PEQ", 158.9), ("PEQ", 496.6), ("PEQ", 1970.0), ("PEQ", 5020.0),
             ("HShv", 10020.0)]
# monitor bus (odd of its pair) -> which channels it hears, and at what mean level (dB)
OWN = {1: ("/ch/19", "/ch/20"), 5: ("/ch/21", "/ch/22")}   # unity: the player's own instrument
MIXES = {1: {"own": (19, 20), "kick": -6, "snare": -8, "bass": -8, "gtr": -10, "vox": -5,
             "click": -12, "oh": -18},
         3: {"kick": -2, "snare": -3, "tom": -10, "cymbal": -16, "bass": -4, "gtr": -12,
             "vox": -8, "click": -4, "daw": -10, "trig": -6},
         5: {"own": (21, 22), "kick": -6, "snare": -8, "bass": -8, "gtr": -10, "vox": -5,
             "click": -12},
         7: {"kick": -3, "snare": -8, "bass": 0, "gtr": -10, "vox": -8, "click": -8},
         9: {"vox": -2, "kick": -12, "snare": -14, "bass": -10, "gtr": -10, "click": -18,
             "daw": -10},
         11: {"vox": -8, "kick": -10, "bass": -10, "click": -14}}
FX_SENDS = {13: ("vox", "snare"), 14: ("tom", "snare", "gtr"), 15: ("vox",), 16: ("oh",)}
# (strip, odd monitor bus) -> the level an OFF send keeps stored
OFF_SENDS = {("/ch/05", 1): -6, ("/ch/09", 3): -8, ("/ch/24", 7): -5}


def _rep(scene: Scene, path: str) -> str:
    partner = pair_linked(scene, path)
    return min(path, partner) if partner else path


def _level(r: random.Random, mean: float) -> float:
    return _pick(r, LEVEL, max(mean - 3, -40), min(mean + 3, 10))


def channel(scene: Scene, ch: int, e: Edits) -> None:
    p, role = f"/ch/{ch:02d}", ROLE[ch]
    key = _rep(scene, p)
    r = rng(key, "proc")
    (hpf_on, lo, hi), gate_on, comp_on, bands = SPEC[role]
    trim = r.choice([0.0, 0.0, 0.0, _pick(r, HALF, -6, 6)])
    e[(p + "/preamp", 0)] = 0.0 if role == "spare" else trim
    e[(p + "/preamp", 1)] = "ON" if ch == 4 else "OFF"
    e[(p + "/preamp", 2)] = "ON" if hpf_on else "OFF"
    e[(p + "/preamp", 3)] = r.choice([12, 18, 24, 24])
    e[(p + "/preamp", 4)] = round(_pick(r, HPF, lo, hi))
    e[(p + "/gate", 0)] = "ON" if gate_on else "OFF"
    e.update({(p + "/gate", 1): r.choice(["GATE", "GATE", "EXP2", "EXP3"]),
              (p + "/gate", 2): _pick(r, HALF, -60, -25), (p + "/gate", 3): _pick(r, HALF, 12, 60),
              (p + "/gate", 4): r.randint(0, 8), (p + "/gate", 5): _pick(r, HOLD, 5, 200),
              (p + "/gate", 6): _pick(r, RELEASE, 100, 900)})
    e.update({(p + "/dyn", 0): "ON" if comp_on else "OFF", (p + "/dyn", 2): r.choice(["PEAK", "RMS"]),
              (p + "/dyn", 4): _pick(r, HALF, -32, -8),
              (p + "/dyn", 5): r.choice(["2.0", "2.5", "3.0", "4.0", "5.0"]),
              (p + "/dyn", 6): r.randint(0, 4), (p + "/dyn", 7): _pick(r, HALF, 0, 6),
              (p + "/dyn", 8): r.randint(3, 40), (p + "/dyn", 9): _pick(r, HOLD, 0.05, 20),
              (p + "/dyn", 10): _pick(r, RELEASE, 40, 400),
              (p + "/dyn", 13): 100})
    for flt, on in (("/gate/filter", role == "kick"), ("/dyn/filter", role in ("bass", "kick"))):
        e.update({(p + flt, i): v for i, v in enumerate(FILTER_REST)})
        if on:
            e.update({(p + flt, 0): "ON", (p + flt, 1): r.choice(FILTERS[:4]),
                      (p + flt, 2): _pick(r, FREQ, 60, 250)})
    e[(p + "/eq", 0)] = "OFF" if role in ("click", "trig", "spare") else "ON"
    if bands is None:
        for b, (typ, f) in enumerate(REST_BANDS, 1):
            e.update({(f"{p}/eq/{b}", 0): typ, (f"{p}/eq/{b}", 1): f, (f"{p}/eq/{b}", 2): 0.0,
                      (f"{p}/eq/{b}", 3): 2.0})
    for b, (typ, flo, fhi, glo, ghi) in enumerate(bands or [], 1):
        e.update({(f"{p}/eq/{b}", 0): typ, (f"{p}/eq/{b}", 1): _pick(r, FREQ, flo, fhi),
                  (f"{p}/eq/{b}", 2): _pick(r, QUARTER, glo, ghi),
                  (f"{p}/eq/{b}", 3): _pick(r, Q, 0.7, 4) if typ == "PEQ" else Q[33]})
    if ch == 2:
        e[(p + "/eq/2", 3)] = 10.0   # a notch: Q at the top of its range
    e[(p + "/mix", 0)] = "OFF" if ch == 19 or role == "spare" else "ON"
    e[(p + "/mix", 1)] = "-oo" if role == "spare" else _level(r, -12 if role == "click" else -4)
    e[(p + "/mix", 2)] = "OFF" if role in ("click", "trig", "spare") else "ON"
    base = PAN.get(ch, 0)
    jitter = 2 * rng(key, "pan").randint(-4, 4) if 0 < abs(base) < 90 else 0
    e[(p + "/mix", 3)] = base + (jitter if key == p else -jitter)   # a linked pair mirrors


def _hears(bus: int, strip: str) -> float | None:
    """The mean level ``strip`` sends to monitor ``bus``, or None for silent."""
    if not strip.startswith("/ch/"):
        return {"/auxin/05": -14, "/auxin/06": -14}.get(strip) if bus != 11 else None
    ch = int(strip[4:])
    mix = MIXES[bus]
    if ch in mix.get("own", ()):
        return 0
    return mix.get(ROLE[ch])


def sends(scene: Scene, e: Edits) -> None:
    for strip in SEND_STRIPS:
        rep = _rep(scene, strip)
        for bus in range(1, 17):
            p = f"{strip}/mix/{bus:02d}"
            odd = bus if bus % 2 else bus - 1
            brep = _rep(scene, f"/bus/{bus:02d}")
            r = rng(rep, brep, "send")
            if bus <= 12:
                mean = _hears(odd, rep)
                if rep.startswith("/fxrtn/") and odd in (1, 5, 9):
                    mean = -12
            else:
                mean = -10 if rep.startswith("/ch/") and ROLE[int(rep[4:])] in FX_SENDS[bus] \
                    else None
            off = OFF_SENDS.get((rep, odd))
            e[(p, 0)] = "ON" if off is None else "OFF"
            e[(p, 1)] = _level(r, off) if off is not None else "-oo" if mean is None else \
                0.0 if rep in OWN.get(odd, ()) else _level(r, mean)
            if bus % 2:
                partner = pair_linked(scene, strip)
                pan = 0 if bus > 12 else -100 if partner and strip < partner else \
                    100 if partner else PAN.get(int(strip[4:]), 0) if strip.startswith("/ch/") else 0
                e[(p, 2)] = max(-100, min(100, pan))
                post = bus > 12 or bus == 9 and (strip.startswith("/fxrtn/")
                                                  or strip in ("/ch/31", "/ch/32"))
                e[(p, 3)] = "POST" if post else "PRE"


def buses(scene: Scene, e: Edits) -> None:
    for n in range(1, 13):
        p = f"/bus/{n:02d}"
        r = rng(_rep(scene, p), "bus")
        e.update({(p + "/dyn", 0): "ON", (p + "/dyn", 2): r.choice(["PEAK", "RMS"]),
                  (p + "/dyn", 4): _pick(r, HALF, -6, -1), (p + "/dyn", 5): r.choice(COMP_RATIOS[-3:]),
                  (p + "/dyn", 6): r.randint(2, 5), (p + "/dyn", 7): 0.0,
                  (p + "/dyn", 8): r.randint(0, 10), (p + "/dyn", 9): _pick(r, HOLD, 2, 20),
                  (p + "/dyn", 10): _pick(r, RELEASE, 50, 250), (p + "/dyn", 13): 100,
                  (p + "/eq", 0): "ON"})
        e.update({(p + "/dyn/filter", i): v for i, v in enumerate(FILTER_REST)})
        for b, (typ, f) in enumerate(BUS_BANDS, 1):
            gain = _pick(r, QUARTER, -8, -2) if b == 1 else _pick(r, QUARTER, -3, 2) if b == 6 else 0.0
            freq = _pick(r, FREQ, 60, 120) if b == 1 else _pick(r, FREQ, 8000, 12000) if b == 6 else f
            e.update({(f"{p}/eq/{b}", 0): typ, (f"{p}/eq/{b}", 1): freq, (f"{p}/eq/{b}", 2): gain,
                      (f"{p}/eq/{b}", 3): 2.0})
        e[(p + "/mix", 1)] = _level(r, -6)
    for n in range(1, 9):
        e[(f"/fxrtn/{n:02d}/mix", 1)] = 0.0
    for n in (5, 6):
        e[(f"/auxin/{n:02d}/mix", 1)] = _level(rng("/auxin/05", "fader"), -8)
        e[(f"/auxin/{n:02d}/preamp", 0)] = 4.5
    e[("/main/st/mix", 1)] = -2.5


PHANTOM = ("oh", "cymbal", "room")


def head_amps(scene: Scene, e: Edits, readers: dict[int, int]) -> None:
    """Gain and phantom for every input a channel reads, by role; two spare stage-box
    inputs carry a gain of their own so a move onto them has something to keep."""
    ranges = {"kick": (20, 34), "snare": (14, 30), "tom": (14, 30), "oh": (22, 40),
              "cymbal": (22, 38), "room": (28, 46), "bass": (8, 26), "gtr": (6, 34),
              "vox": (30, 50), "trig": (0, 14)}
    for idx in range(128):
        ch = readers.get(idx)
        gain = 0.0
        if ch is not None and ROLE[ch] in ranges:
            gain = _pick(rng(_rep(scene, f"/ch/{ch:02d}"), "gain"), HALF, *ranges[ROLE[ch]])
        elif idx in (44, 45):
            gain = _pick(rng(idx, "gain"), HALF, 18, 36)
        e[(f"/headamp/{idx:03d}", 0)] = gain
        e[(f"/headamp/{idx:03d}", 1)] = "ON" if ch is not None and ROLE[ch] in PHANTOM else "OFF"


# release stays under 1000: no desk-written file shows how a four-digit one is padded
ALT_KINDS = {"freq": FREQ, "gain": QUARTER, "q": Q, "hold": HOLD,
             "release": [v for v in RELEASE if v < 1000],
             "hpf": HPF, "makeup": [i / 2 for i in range(25)]}


def alt_value(kind: str, e_tok: str, fmt, n: int = 0) -> object:
    """A value of ``kind`` whose token differs from ``e_tok``; the same ``e_tok`` always
    maps to the same value, so mirrored pairs stay mirrored."""
    r = rng("alt", kind, e_tok, n)
    enums = {"onoff": ["ON", "OFF"], "type": EQ_TYPES[1:5], "ratio": COMP_RATIOS,
             "filter": list(FILTERS), "tap": ["PRE", "POST"]}
    for _ in range(64):
        if kind in enums:
            v = r.choice(enums[kind])
        elif kind in ("attack", "knee"):
            v = r.randint(0, 5 if kind == "knee" else 60)
        elif kind == "pan":
            v = 2 * r.randint(-50, 50)
        elif kind == "headamp":
            v = _pick(r, HALF, float(e_tok) - 8, float(e_tok) + 8)
        elif kind == "level":
            base = -10.0 if e_tok == "-oo" else float(e_tok)
            v = _pick(r, LEVEL, max(base - 10, -40), min(base + 6, 10))
        elif kind == "half":
            v = _pick(r, HALF, -50, -1)
        else:
            grid = ALT_KINDS[kind]
            v = r.choice(grid[len(grid) // 8: len(grid) - len(grid) // 8])
        if fmt(kind, v) != e_tok:
            return v
    raise ValueError(f"no alternative {kind} for {e_tok!r}")
