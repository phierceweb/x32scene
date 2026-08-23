"""The user-assign section: the strings on ``/config/userctrl/{A,B,C}/enc`` and ``/btn``,
decoded into words (protocol document, User Definable Controls chapter)."""

from __future__ import annotations

_PAGES = {"0": ("Channel", {"0": "Home", "1": "Config", "2": "Gate", "3": "Dyn", "4": "EQ",
                            "5": "Mix", "6": "Main", "S": "Sends on faders"}),
          "1": ("Meter", {"0": "Channel", "1": "Mix Bus", "2": "Aux/FX", "3": "In/Out", "4": "RTA"}),
          "2": ("Route", {"0": "Home", "1": "Analog out", "2": "Aux out", "3": "P16 out",
                          "4": "Card out", "5": "AES50-A out", "6": "AES50-B out", "7": "XLR out"}),
          "3": ("Setup", {"0": "Global", "1": "Config", "2": "Remote", "3": "Network", "4": "Names",
                          "5": "Preamps", "6": "Card"}),
          "4": ("Library", {"0": "Channel", "1": "Effect", "2": "Route"}),
          "5": ("FX", {"0": "Home", **{str(i): f"FX{i}" for i in range(1, 9)}}),
          "6": ("Monitor", {"0": "Monitor", "1": "Talk A", "2": "Talk B", "3": "Oscillator"}),
          "7": ("USB", {"0": "Home", "1": "Config"}),
          "8": ("Scene", {"0": "Home", "1": "Scenes", "2": "Bit", "3": "Param safe",
                          "4": "Channel safe", "5": "MIDI"}),
          "9": ("Assign", {"0": "Home", "1": "Set A", "2": "Set B", "3": "Set C"})}
_SELECTED = {"@": "Fader", "A": "Gate threshold", "B": "Gate range", "C": "Gate attack",
             "D": "Gate hold", "E": "Gate release", "F": "Dyn threshold", "G": "Dyn ratio",
             "H": "Dyn knee", "I": "Dyn makeup", "J": "Dyn attack", "K": "Dyn hold",
             "L": "Dyn release"}
_REMOTE = {**{i: f"F{i + 1}" for i in range(8)}, 8: "Undo", 9: "Save", 10: "Bank <",
           11: "Bank >", 12: "Channel <", 13: "Channel >", 14: "Up", 15: "Down", 16: "Left",
           17: "Right", 18: "Stop", 19: "Play", 20: "Rec", 21: "FF", 22: "Rew", 23: "Mrk/RTZ",
           24: "Cycle", 25: "Scrub", 26: "Nudge/Shuttle", 27: "Drop/In", 28: "Rep/Out",
           29: "Click/Off", 30: "Read", 31: "Write", 32: "Touch", 33: "Trim", 34: "Latch"}
_ENCODER_REMOTE = {**{i: f"Remote {i + 1}" for i in range(8)}, 8: "Jog"}
_SHOW = {"9": {"00": "Prev", "01": "Next", "02": "Undo", "03": "Go"}}
_S_KIND = {"0": "Scene", "2": "Snippet", "4": "Cue"}
_USB = {"0": "Stop", "1": "Play", "2": "Record", "3": "Pause", "4": "Play/Stop",
        "5": "Play/Pause", "6": "Rec/Stop", "7": "Rec/Pause", "8": "Previous track",
        "9": "Next track"}
_SD = {0: "Stop", 1: "Play", 2: "Record", 3: "Pause", 4: "Play/Stop", 5: "Play/Pause",
       6: "Add marker", 7: "Previous marker", 8: "Next marker", 9: "Play marker",
       10: "Select marker", 11: "Select session", 12: "USB playback", 13: "Channel routing"}
_XLIVE = {"0": "X-Live locator", "1": "X-Live marker list", "2": "X-Live session list"}
_MIDI = {"C": "CC", "N": "Note", "P": "Program", "c": "CC toggle", "n": "Note toggle"}


def strip_name(n: int) -> str:
    """The strip a two-digit user-control index names (00 = channel 1 … 85 = mute group 6)."""
    for lo, hi, label in ((0, 31, "Ch"), (32, 39, "Aux"), (48, 63, "Bus"), (64, 69, "Matrix"),
                          (72, 79, "DCA"), (80, 85, "Mute group")):
        if lo <= n <= hi:
            return f"{label} {n - lo + 1}"
    if 40 <= n <= 47:
        return f"FX rtn {1 + (n - 40) // 2}{'LR'[(n - 40) % 2]}"
    return {70: "Main LR", 71: "Main M/C"}.get(n, f"strip {n}")


def _int(s: str) -> int | None:
    return int(s) if s.isdigit() else None


def decode_assignment(code: str, *, button: bool) -> str:
    """One encoder or button assignment string in words; an unknown shape comes back as
    the code itself, never a guess."""
    code = code.strip('"')
    if code in ("", "-"):
        return "unassigned"
    k, rest = code[0], code[1:]
    n = _int(rest[:2])
    if k in ("F", "P") and not button and n is not None:
        return f"{'Fader' if k == 'F' else 'Pan'} {strip_name(n)}"
    if k == "S" and not button and n is not None and _int(rest[2:4]) is not None:
        return f"Send {strip_name(n)} -> bus {int(rest[2:4]) + 1}"
    if k == "X" and rest[:1].isdigit() and _int(rest[1:3]) is not None:
        return f"FX{int(rest[0]) + 1} param {int(rest[1:3]) + 1}"
    if k == "M" and len(rest) >= 6 and rest[0] in _MIDI:
        return f"MIDI {_MIDI[rest[0]]} ch {int(rest[1:3])} value {int(rest[3:6])}"
    if k == "R" and _int(rest[:3]) is not None:
        table = _REMOTE if button else _ENCODER_REMOTE
        return f"Remote {table.get(int(rest[:3]), rest[:3])}"
    if k == "D" and rest[:1] in _SELECTED:
        return f"Selected channel {_SELECTED[rest[0]]}"
    if k == "U" and not button and rest[:1] in _XLIVE:
        return _XLIVE[rest[0]]
    if button:
        if k == "U" and n is not None and n in _SD:
            return f"SD recorder {_SD[n]}"
        if k == "L" and _int(rest[:3]) is not None:
            v = int(rest[:3])
            return f"X-Live session {v}" if v < 100 else f"X-Live marker {v - 100}"
        if k == "A" and rest[:1] in ("0", "1"):
            return f"Automix group {'XY'[int(rest[0])]}"
        if k == "P" and n is not None and len(rest) >= 4 and rest[2] in _PAGES:
            target, pages = _PAGES[rest[2]]
            page = pages.get(rest[3], rest[3])
            where = f" {strip_name(n)}" if rest[2] == "0" else ""
            return f"Page {target}{where}: {page}"
        if k == "O" and n is not None:
            return f"Mute {strip_name(n)}"
        if k == "I" and n is not None:
            return f"Insert {strip_name(n)}"
        if k == "S" and rest[:1] == "9" and rest[1:3] in _SHOW["9"]:
            return f"Show {_SHOW['9'][rest[1:3]]}"
        if k == "S" and rest[:1] in _S_KIND and _int(rest[1:3]) is not None:
            return f"Recall {_S_KIND[rest[0]]} {int(rest[1:3])}"
        if k == "T" and rest[:1] in _USB:
            return f"USB {_USB[rest[0]]}"
    return code


def decode_layer(enc: list[str], btn: list[str]) -> dict[str, str]:
    """{"enc 1": …, "btn 5": …} for one user-assign layer."""
    out = {f"enc {i}": decode_assignment(c, button=False) for i, c in enumerate(enc, start=1)}
    out.update({f"btn {i}": decode_assignment(c, button=True) for i, c in enumerate(btn, start=5)})
    return out
