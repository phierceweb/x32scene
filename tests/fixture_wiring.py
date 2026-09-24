"""The synthetic wiring of the example scenes: routing banks, user patch, output patch and
record patch for example.scn, and the part of it example-alt.scn changes, plus the FX rack
and DCA groups. Not collected by pytest.

Channels 1-16 read local inputs 1-16 and channels 17-28 AES50-A inputs 1-12 (17-24 through
a direct block, 25-28 through user-in slots). Every value is invented for the fixture.
"""

from __future__ import annotations

from x32scene.services.routing_edit import encode_input_source, encode_out_source

Edits = dict[tuple[str, int], object]

ROUTING = {
    "IN": ["UIN1-8", "UIN9-16", "A1-8", "UIN25-32", "AUX1-4"],
    "AES50A": ["OUT1-8", "OUT9-16", "P161-8", "P169-16", "AUX/CR", "AUX/TB"],
    "AES50B": ["UOUT1-8", "UOUT9-16", "UOUT17-24", "UOUT33-40", "UOUT41-48", "UOUT41-48"],
    "CARD": ["UOUT1-8", "UOUT9-16", "UOUT17-24", "UOUT33-40"],
    "OUT": ["OUT1-4", "OUT5-8", "OUT9-12", "OUT13-16"],
    "PLAY": ["CARD1-8", "CARD9-16", "CARD17-24", "UIN25-32", "AUX1-4"],
}
USER_IN = [*(f"local {n}" for n in range(1, 17)), *(f"aes50-a {n}" for n in range(1, 13)),
           "off", "card 32", "card 1", "card 2"]
_TRACKS = [*(f"local {n}" for n in range(1, 17)), *(f"aes50-a {n}" for n in range(1, 13)),
           "aux 5", "aux 6", "Output 1", "Output 2"]
USER_OUT = [*_TRACKS[:24], *["off"] * 8, *_TRACKS[24:], *["off"] * 8]

_BUS = 3   # output tap of bus n is n + 3
OUTPUTS = {
    "main": {1: (1, "POST"), 2: (2, "POST"), **{n: (n - 2 + _BUS, "POST") for n in range(3, 15)},
             15: (3, "POST"), 16: (20, "POST")},
    "aux": {1: (11 + _BUS, "POST"), 2: (12 + _BUS, "POST"), 3: (1, "POST"), 4: (2, "POST"),
            5: (20, "POST"), 6: (21, "POST")},
    "p16": {n: (25 + ch, "PRE") for n, ch in enumerate(
        (17, 18, 19, 20, 21, 22, 5, 23, 7, 24, 25, 26, 1, 3, 30, 11), 1)},
    "aes": {1: (1, "<-EQ"), 2: (2, "<-EQ")},
    "rec": {1: (1, "POST"), 2: (2, "POST")},
}

ALT_ROUTING = {"AES50A": {1: "UOUT9-16"}, "AES50B": {2: "OUT1-8", 3: "OUT9-16", 4: "AN1-8"},
               "CARD": {0: "AN1-8"}}
ALT_USER_IN = {29: "aes50-a 13"}
ALT_USER_OUT = {**{n: f"Output {n}" for n in range(1, 17)}, **{n: "off" for n in range(17, 25)},
                **{n: f"P16 {n - 24}" for n in range(25, 33)}}
ALT_MAIN = {5: 1, 6: 2, 9: 11 + _BUS, 10: 12 + _BUS, 11: 1 + _BUS, 12: 2 + _BUS,
            13: 9 + _BUS, 14: 10 + _BUS, 15: 5 + _BUS, 16: 6 + _BUS}


def wiring() -> Edits:
    e: Edits = {}
    for key, blocks in ROUTING.items():
        e.update({(f"/config/routing/{key}", i): tok for i, tok in enumerate(blocks)})
    e.update({("/config/userrout/in", i): encode_input_source(w) for i, w in enumerate(USER_IN)})
    e.update({("/config/userrout/out", i): encode_out_source(w) for i, w in enumerate(USER_OUT)})
    for bank, outs in OUTPUTS.items():
        for n, (src, pos) in outs.items():
            e.update({(f"/outputs/{bank}/{n:02d}", 0): src, (f"/outputs/{bank}/{n:02d}", 1): pos})
            if bank != "rec":
                e[(f"/outputs/{bank}/{n:02d}", 2)] = "OFF"
    return e


def alt_wiring() -> Edits:
    e: Edits = {}
    for key, blocks in ALT_ROUTING.items():
        e.update({(f"/config/routing/{key}", i): tok for i, tok in blocks.items()})
    e.update({("/config/userrout/in", s - 1): encode_input_source(w)
              for s, w in ALT_USER_IN.items()})
    e.update({("/config/userrout/out", s - 1): encode_out_source(w)
              for s, w in ALT_USER_OUT.items()})
    e.update({(f"/outputs/main/{n:02d}", 0): tap for n, tap in ALT_MAIN.items()})
    return e


FX = {"1": {"type": "PLAT", "params": {"Decay": 1.62, "Size": 44, "PreDelay": 18}},
      "2": {"type": "VRM", "params": {"Decay": 1.35, "RoomSize": 30, "LoCut": 120}},
      "3": {"type": "D/CR", "params": {"Time": 330, "Feed": 25, "Mix": 80}},
      "4": {"type": "CR/R", "params": {"Decay": 1.8, "Depth": 30, "Mix": 90}},
      "5": {"type": "EXC", "params": {"Tune": 4500, "Mix": 40}},
      "6": {"type": "LIM", "params": {"Out Gain": -1.0, "Release": 400}},
      "7": {"type": "GEQ2"}, "8": {"type": "GEQ"}}
DCA = {"1": [*range(1, 17), 27, 28], "2": [17, 18], "3": [19, 20, 21, 22],
       "4": [23, 24, 25, 26], "5": [27, 28, 30, 31, 32], "6": [], "7": [], "8": []}
