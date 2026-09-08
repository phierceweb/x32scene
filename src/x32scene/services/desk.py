"""Read-only view of the running desk: identity, state, preferences, and what its own
memory holds (scenes, snippets, cues, presets). Every query is a read; nothing here sets."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field

from ..model import Line
from ..tables_fx import FX_DISPLAY_TYPE, decode_fx
from .osc import (X32_PORT, OscError, decode_message, desk_address, encode_message,
                  pull_lines)

_STAT = ["selidx", "chfaderbank", "grpfaderbank", "sendsonfader", "solo", "usbmounted",
         "remote", "xcardtype", "xcardsync", "screen/screen", "tape/state", "tape/file",
         "urec/state", "lock", "autosave"]
_PREFS = ["name", "clockrate", "clocksource", "show_control", "hardmute", "dcamute",
          "safe_masterlevels", "scene_advance", "confirm_sceneload", "rec_control", "remote/enable",
          "remote/protocol", "ip/dhcp", "ip/addr"]
_XCARD = {0: "none", 1: "X-UF", 2: "X-USB", 3: "X-DANTE", 4: "X-ADAT", 5: "X-MADI",
          6: "DN32-USB", 7: "DN32-DANTE", 8: "DN32-ADAT", 9: "DN32-MADI", 10: "X-Live", 11: "X-WSG"}
_TAPE = {0: "stop", 1: "pause", 2: "play", 3: "pause record", 4: "record", 5: "fast forward",
         6: "rewind"}
LIB_KINDS = {"ch": "channel presets", "fx": "effect presets", "r": "routing presets",
             "mon": "DP48 presets"}


@dataclass
class DeskInfo:
    ip: str
    name: str = ""
    model: str = ""
    firmware: str = ""
    stat: dict[str, str] = field(default_factory=dict)
    prefs: dict[str, str] = field(default_factory=dict)
    show: str = ""
    slots: dict[str, list[tuple[int, str, str]]] = field(default_factory=dict)  # kind -> (idx, name, extra)


def xinfo(ip: str, *, port: int = X32_PORT, timeout: float = 1.0) -> tuple[str, str, str, str]:
    """``/xinfo`` -> (address, name, model, firmware)."""
    peer = desk_address(ip)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(encode_message("/xinfo"), (ip, port))
        # Wait out anyone else on the network, but only to the deadline: steady foreign
        # traffic keeps recvfrom succeeding, so the socket timeout alone never fires.
        deadline = time.monotonic() + timeout
        data = None
        while data is None and time.monotonic() < deadline:
            try:
                sock.settimeout(max(deadline - time.monotonic(), 0.001))
                packet, sender = sock.recvfrom(4096)
            except socket.timeout:
                break
            if sender[0] == peer:
                data = packet
        if data is None:
            raise OscError(f"no /xinfo reply from {ip}:{port}")
    addr, args = decode_message(data)
    if addr != "/xinfo" and addr != "xinfo" or len(args) < 4:
        raise OscError(f"unexpected /xinfo reply {addr!r} {args!r}")
    return tuple(str(a) for a in args[:4])   # type: ignore[return-value]


def _node_values(ip: str, paths: list[str], **kw) -> dict[str, str]:
    kw.setdefault("fail_fast", 3)
    lines, _ = pull_lines(ip, paths, **kw)
    out = {}
    for ln in lines:
        path, _, rest = ln.partition(" ")
        out[path.lstrip("/")] = rest.strip()
    return out


def selected_strip(idx: int) -> str:
    for lo, hi, label in ((0, 31, "Ch"), (32, 39, "Aux"), (48, 63, "Bus"), (64, 69, "Matrix")):
        if lo <= idx <= hi:
            return f"{label} {idx - lo + 1}"
    if 40 <= idx <= 47:
        return f"FX rtn {1 + (idx - 40) // 2}{'LR'[(idx - 40) % 2]}"
    return {70: "Main LR", 71: "Main M/C"}.get(idx, str(idx))


def state_words(stat: dict[str, str]) -> dict[str, str]:
    """The raw -stat values a person reads at a glance."""
    out = {}
    if "-stat/selidx" in stat and stat["-stat/selidx"].isdigit():
        out["selected"] = selected_strip(int(stat["-stat/selidx"]))
    for key, label in (("solo", "solo active"), ("sendsonfader", "sends on faders"),
                       ("usbmounted", "USB drive"), ("remote", "DAW remote"), ("lock", "lock"),
                       ("xcardsync", "card sync"), ("autosave", "autosave")):
        if f"-stat/{key}" in stat:
            out[label] = stat[f"-stat/{key}"]
    if "-stat/xcardtype" in stat and stat["-stat/xcardtype"].isdigit():
        out["expansion card"] = _XCARD.get(int(stat["-stat/xcardtype"]), stat["-stat/xcardtype"])
    if "-stat/tape/state" in stat and stat["-stat/tape/state"].isdigit():
        out["USB recorder"] = _TAPE.get(int(stat["-stat/tape/state"]), stat["-stat/tape/state"])
    if "-stat/tape/file" in stat:
        out["USB file"] = stat["-stat/tape/file"].strip('"')
    return out


def read_desk(ip: str, *, port: int = X32_PORT, timeout: float = 0.6,
              library: bool = True) -> DeskInfo:
    info = DeskInfo(ip)
    _, info.name, info.model, info.firmware = xinfo(ip, port=port, timeout=max(timeout, 1.0))
    info.stat = _node_values(ip, [f"-stat/{p}" for p in _STAT], port=port, timeout=timeout)
    info.prefs = _node_values(ip, [f"-prefs/{p}" for p in _PREFS], port=port, timeout=timeout)
    show = _node_values(ip, ["-show/showfile/show"], port=port, timeout=timeout)
    info.show = show.get("-show/showfile/show", "")
    if not library:
        return info
    paths = ([f"-show/showfile/scene/{n:03d}" for n in range(100)]
             + [f"-show/showfile/snippet/{n:03d}" for n in range(100)]
             + [f"-show/showfile/cue/{n:03d}" for n in range(100)]
             + [f"-libs/{k}/{n:03d}" for k in LIB_KINDS for n in range(1, 101)])
    # without this a desk that answers /xinfo but no /node is queried for every slot
    lines, _ = pull_lines(ip, paths, port=port, timeout=timeout, fail_fast=3)
    for ln in lines:
        parsed = Line.parse(ln)
        path, args = parsed.path, parsed.args
        if not args or args[-1] != "1":
            continue   # hasdata 0
        parts = path.strip("/").split("/")
        kind = parts[-2] if parts[0] == "-libs" else parts[2]
        idx = int(parts[-1])
        name = next((a.strip('"') for a in args if a.startswith('"')), "")
        info.slots.setdefault(kind, []).append((idx, name, slot_words(kind, args)))
    return info


def slot_words(kind: str, args: list[str]) -> str:
    """A slot's header fields in words: a scene's safes, a snippet's filters, a preset's
    sections or effect type; a cue's number and what it recalls."""
    from .headers import decode_header   # local: headers imports nothing from here
    if kind == "cue":
        # numb "name" skip scene snippet miditype midichan midipara1 midipara2 hasdata
        numb = args[0] if args else "?"
        num = f"{int(numb) // 100}.{int(numb) // 10 % 10}.{int(numb) % 10}" if numb.isdigit() else numb
        scene = args[3] if len(args) > 3 else "-1"
        snip = args[4] if len(args) > 4 else "-1"
        parts = [f"cue {num}"]
        if scene != "-1":
            parts.append(f"scene {scene}")
        if snip != "-1":
            parts.append(f"snippet {snip}")
        if len(args) > 2 and args[2] == "1":
            parts.append("skip")
        return ", ".join(parts)
    head = "#4.0# " + " ".join(args if kind in ("scene", "snippet") else args)
    d = decode_header(head) or {}
    if kind == "scene":
        return "safes: " + (", ".join(d.get("safes", [])) or "none")
    if kind == "snippet":
        strips = d.get("channels", []) + d.get("auxbuses", []) + d.get("maingrps", [])
        return f"{', '.join(d.get('filters', [])) or 'no filters'}; {len(strips)} strip(s)"
    if kind == "ch":
        sec = d.get("sections") or {}
        return f"has {', '.join(sec.get('present', [])) or '-'}; on: {', '.join(sec.get('active', [])) or '-'}"
    if kind == "fx":
        # the desk's index carries the display type as a %-mask; a .efx header as an int
        raw = d.get("display_type", "")
        num = str(int(raw[1:], 2)) if raw.startswith("%") else raw
        code = FX_DISPLAY_NAMES.get(num)
        return f"{decode_fx(code)} ({code})" if code else raw
    return ""


FX_DISPLAY_NAMES = {str(v): k for k, v in FX_DISPLAY_TYPE.items()}
