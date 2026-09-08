"""Meters: a read-only window on what the desk is hearing. One ``/meters`` request makes
the console stream a blob every ~50 ms for ten seconds; this collects a short window
and keeps each slot's peak. Values are linear 0-1 as the desk sends them; ``to_db``
turns one into dBFS. A gain-reduction slot (``… GR``) reads 1.0 when the dynamics are
doing nothing and falls as they clamp."""

from __future__ import annotations

import math
import socket
import struct
import time
from dataclasses import dataclass

from ..model import Scene
from .osc import X32_PORT, OscError, decode_message, desk_address, encode_message

# meter id -> the slots its blob carries, in order (protocol document, Meter requests)
METER_SLOTS: dict[int, list[str]] = {
    0: ([f"ch {n}" for n in range(1, 33)] + [f"aux {n}" for n in range(1, 9)]
        + [f"fx rtn {1 + i // 2}{'LR'[i % 2]}" for i in range(8)]
        + [f"bus {n}" for n in range(1, 17)] + [f"matrix {n}" for n in range(1, 7)]),
    2: ([f"bus {n}" for n in range(1, 17)] + [f"matrix {n}" for n in range(1, 7)]
        + ["main L", "main R", "main M/C"]
        + [f"bus {n} GR" for n in range(1, 17)] + [f"matrix {n} GR" for n in range(1, 7)]
        + ["main LR GR", "main M/C GR"]),
    4: ([f"in {n}" for n in range(1, 33)] + [f"aux in {n}" for n in range(1, 9)]
        + [f"out {n}" for n in range(1, 17)] + [f"p16 {n}" for n in range(1, 17)]
        + [f"aux out {n}" for n in range(1, 7)] + ["aes L", "aes R", "monitor L", "monitor R"]),
    7: [f"bus send {n}" for n in range(1, 17)],
    9: [f"fx{s} {k}" for s in range(1, 9) for k in ("send L", "send R", "return L", "return R")],
    11: ["monitor L", "monitor R", "talk level", "talk GR", "oscillator"],
    12: ["rec in L", "rec in R", "playback L", "playback R"],
}
WHAT = {"inputs": 0, "buses": 2, "outputs": 4, "sends": 7, "fx": 9, "monitor": 11, "recorder": 12}


@dataclass
class Peaks:
    meter: int
    frames: int
    peak: dict[str, float]   # slot -> highest linear value seen


def to_db(v: float) -> float:
    return 20 * math.log10(v) if v > 0 else -math.inf


def fmt_db(v: float) -> str:
    db = to_db(v)
    return "-oo" if db == -math.inf else f"{db:+.1f}"


def parse_blob(blob: bytes) -> list[float]:
    """The floats in a meter blob: a little-endian count, then little-endian floats."""
    if len(blob) < 4:
        raise OscError("meter blob too short")
    n = struct.unpack_from("<i", blob, 0)[0]
    if n < 0:   # signed on the wire: a negative count makes the length check below vacuous
        raise OscError(f"meter blob claims {n} floats")
    if len(blob) < 4 + 4 * n:
        raise OscError(f"meter blob claims {n} floats in {len(blob)} bytes")
    values = list(struct.unpack_from(f"<{n}f", blob, 4))
    if not all(math.isfinite(v) for v in values):
        # inf/nan reach int() through to_db and raise OverflowError, which is an
        # ArithmeticError and so escapes the CLI boundary; --json would emit bare Infinity.
        raise OscError("meter blob carries a non-finite level")
    return values


def read_meters(ip: str, meter: int, *, seconds: float = 1.0, port: int = X32_PORT,
                timeout: float = 1.0) -> Peaks:
    """Stream ``/meters/<meter>`` for ``seconds`` and keep each slot's peak."""
    slots = METER_SLOTS.get(meter)
    if slots is None:
        raise ValueError(f"meter id must be one of {sorted(METER_SLOTS)}, got {meter}")
    peak = dict.fromkeys(slots, 0.0)
    frames = 0
    peer = desk_address(ip)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(encode_message("/meters", [f"/meters/{meter}", 0]), (ip, port))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(4096)
            except socket.timeout:
                break
            if sender[0] != peer:
                continue      # someone else on the network, not the desk
            try:
                addr, args = decode_message(data)
            except OscError:
                continue
            if not addr.endswith(f"/meters/{meter}") or not args or not isinstance(args[0], bytes):
                continue
            try:
                values = parse_blob(args[0])
            except OscError:
                continue   # one bad frame, not the end of the window
            frames += 1
            for slot, v in zip(slots, values, strict=False):
                if v > peak[slot]:
                    peak[slot] = v
    if frames == 0:
        raise OscError(f"no meter frames from {ip}:{port} in {timeout:g}s — desk off or unreachable?")
    return Peaks(meter, frames, peak)


def slot_names(scene: Scene | None, slot: str) -> str:
    """A scene's scribble name for a metered slot, when the slot is a named strip."""
    if scene is None:
        return ""
    fam, _, num = slot.partition(" ")
    path = {"ch": "/ch", "in": "/ch", "bus": "/bus", "matrix": "/mtx", "aux": "/auxin"}.get(fam)
    if path is None or not num.isdigit():
        return ""
    cfg = scene.get(f"{path}/{int(num):02d}/config")
    return cfg.args[0].strip('"') if cfg and cfg.args else ""
