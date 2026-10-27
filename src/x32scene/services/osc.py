"""The OSC/UDP wire to an X32: message encoding and decoding, the desk's address, and the
socket a ``watch`` session holds. The desk answers on UDP 10023. The ``/node`` pull that
assembles ``.scn`` text from it is ``osc_pull``.
"""

from __future__ import annotations

import socket
import struct
import time
from collections.abc import Sequence

X32_PORT = 10023
RECV_BUF = 65536


class OscError(RuntimeError):
    """Malformed OSC datagram."""


def desk_address(ip: str) -> str:
    """The numeric address a reply has to come from. Accepts a hostname.

    An unconnected UDP socket hears whatever the network hands it, and a reply here
    becomes console state. Address only, not port: the reply port is a firmware detail
    not pinned down across models, and rejecting a real desk would be worse.
    """
    return socket.gethostbyname(ip)


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


def node_line(args: list) -> str | None:
    """The scene-format line a ``/node`` reply carries, or None when it is not one line."""
    if not args:
        return None
    line = str(args[0]).removesuffix("\n")
    return None if "\n" in line or "\r" in line else line


class UdpTransport:
    """The socket of a ``watch`` session. ``/xremote`` pushes and ``/node`` replies both come
    back to the port that asked, so one socket carries the whole session."""

    def __init__(self, ip: str, port: int = X32_PORT):
        self._to = (ip, port)
        self._peer = desk_address(ip)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def __enter__(self) -> UdpTransport:
        return self

    def __exit__(self, *exc) -> None:
        self._sock.close()

    def send(self, addr: str, args: Sequence[str | int | float] = ()) -> None:
        self._sock.sendto(encode_message(addr, args), self._to)

    def recv(self, timeout: float) -> tuple[str, list] | None:
        """The next message from the desk within ``timeout``; anyone else's is dropped."""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            self._sock.settimeout(remaining)
            try:
                data, sender = self._sock.recvfrom(RECV_BUF)
            except socket.timeout:
                return None
            if sender[0] != self._peer:
                continue
            try:
                return decode_message(data)
            except OscError:
                continue
        return None

    def drain(self) -> list[tuple[str, list]]:
        """Every message from the desk already waiting, without blocking."""
        waiting = []
        self._sock.setblocking(False)
        try:
            while True:
                try:
                    data, sender = self._sock.recvfrom(RECV_BUF)
                except (BlockingIOError, InterruptedError):
                    return waiting
                if sender[0] != self._peer:
                    continue
                try:
                    waiting.append(decode_message(data))
                except OscError:
                    continue
        finally:
            self._sock.setblocking(True)
