"""Live X32 state over OSC/UDP — ``/node`` queries against the running desk.

A ``/node`` reply carries one line in exactly the scene-file format, so a live pull
assembles ``.scn`` text and the whole toolkit (Scene, diff, preflight, audit) applies
unchanged. The desk answers on UDP 10023; unanswered paths are reported, not raised —
consoles skip /node paths their firmware lacks, so absence is normal, not an error.
"""

from __future__ import annotations

import socket
import struct
import time
from collections.abc import Sequence

from ..model import HEADER_RE, Scene

X32_PORT = 10023
_RECV_BUF = 65536


class OscError(RuntimeError):
    """Malformed OSC datagram."""


def _pad(b: bytes) -> bytes:
    return b + b"\x00" * (4 - len(b) % 4)


def encode_message(addr: str, args: Sequence[str | int | float] = ()) -> bytes:
    tags = ","
    payload = b""
    for a in args:
        if isinstance(a, bool):
            raise OscError("bool args are not part of the X32 dialect")
        if isinstance(a, int):
            tags += "i"
            payload += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"
            payload += struct.pack(">f", a)
        else:
            tags += "s"
            payload += _pad(str(a).encode("utf-8"))
    return _pad(addr.encode("ascii")) + _pad(tags.encode("ascii")) + payload


def _read_padded_string(data: bytes, pos: int) -> tuple[str, int]:
    end = data.index(b"\x00", pos)
    s = data[pos:end].decode("utf-8", "replace")
    return s, pos + ((end - pos) // 4 + 1) * 4


def decode_message(data: bytes) -> tuple[str, list]:
    try:
        addr, pos = _read_padded_string(data, 0)
        tags, pos = _read_padded_string(data, pos)
    except ValueError as e:
        raise OscError(f"truncated OSC datagram: {data[:32]!r}") from e
    args: list = []
    try:
        for t in tags.lstrip(","):
            if t == "s":
                s, pos = _read_padded_string(data, pos)
                args.append(s)
            elif t == "i":
                args.append(struct.unpack_from(">i", data, pos)[0])
                pos += 4
            elif t == "f":
                args.append(struct.unpack_from(">f", data, pos)[0])
                pos += 4
            elif t == "b":   # blob: big-endian length, then the bytes, padded to 4
                n = struct.unpack_from(">i", data, pos)[0]
                args.append(bytes(data[pos + 4:pos + 4 + n]))
                pos += 4 + ((n + 3) // 4) * 4
            else:
                raise OscError(f"unsupported OSC type tag {t!r}")
    except (ValueError, struct.error) as e:
        raise OscError(f"truncated OSC datagram: {data[:32]!r}") from e
    return addr, args


def pull_lines(ip: str, paths: Sequence[str], *, port: int = X32_PORT,
               timeout: float = 0.5, retries: int = 1,
               fail_fast: int | None = None) -> tuple[list[str], list[str]]:
    """Query each path via /node. Returns (scene-format lines, unanswered paths).

    A reply line starts with its own path, so late replies land in the right slot rather
    than desynchronizing the capture. ``fail_fast=N`` raises once N paths have gone
    unanswered with nothing received, instead of timing out over every remaining path.
    """
    got: dict[str, str] = {}  # "/path" -> scene-format line
    wanted = ["/" + p for p in paths]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for n_tried, (path, want) in enumerate(zip(paths, wanted, strict=True), start=1):
            for _ in range(retries + 1):
                if want in got:
                    break
                sock.sendto(encode_message("/node", [path]), (ip, port))
                deadline = time.monotonic() + timeout
                while want not in got:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    sock.settimeout(remaining)
                    try:
                        data, _addr = sock.recvfrom(_RECV_BUF)
                    except socket.timeout:
                        break
                    try:
                        addr, args = decode_message(data)
                    except OscError:
                        continue  # one malformed datagram must not abort the pull
                    if addr != "node" or not args:
                        continue
                    line = str(args[0]).rstrip("\n")
                    got[line.split(" ", 1)[0]] = line
            if want not in got:
                if fail_fast is not None and not got and n_tried >= fail_fast:
                    raise OscError(f"no reply from {ip}:{port} after {n_tried} queries "
                                   "— desk off or unreachable?")
    lines = [got[w] for w in wanted if w in got]
    missing = [p for p, w in zip(paths, wanted, strict=True) if w not in got]
    return lines, missing


def pull_scene_like(reference: Scene, ip: str, *, port: int = X32_PORT,
                    timeout: float = 0.5, retries: int = 1,
                    fail_fast: int | None = 3) -> tuple[Scene, list[str]]:
    """Pull the running desk's state for every path the reference scene has.

    The reference's header line is carried over verbatim (the desk has no
    header node), so the pulled Scene diffs cleanly against saved scenes.
    """
    paths = [ln.path.lstrip("/") for ln in reference.lines if ln.path.startswith("/")]
    lines, missing = pull_lines(ip, paths, port=port, timeout=timeout,
                                retries=retries, fail_fast=fail_fast)
    header = [reference.lines[0].raw] if (
        reference.lines and HEADER_RE.match(reference.lines[0].path)) else []
    return Scene.parse("\n".join(header + lines) + "\n"), missing
