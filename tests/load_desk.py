"""The fake desk the `load` tests write to: it holds scene lines, answers ``/node`` from
them and stores ``/`` root writes. ``BASE`` and ``edited`` build the files loaded onto it."""
import socket
import threading

from x32scene.model import Scene
from x32scene.services import osc as O

BASE = """\
#4.0# "LOADTEST" "" %000000000 1
/ch/01/config "Kick" 1 YE 1
/ch/01/mix ON   -6.0 ON +0 OFF   -oo
/ch/01/mix/01 ON  -3.0 +0 PRE 0
/ch/01/mix/02 ON  -3.0
/ch/01/eq/1 PEQ 100.0 +0.00 2.0
/headamp/000 +20.0 OFF
/fx/1 HALL MIX13 MIX13
/fx/1/par 0.5 0.5 0.5 0.5
"""


def edited(base: str = BASE, /, **lines: str) -> str:
    """``base`` with each given path's line replaced (``ch_01_mix_01`` names ``/ch/01/mix/01``);
    a key naming no line is appended."""
    out = []
    for raw in base.splitlines():
        path = raw.split(" ", 1)[0]
        key = path.strip("/").replace("/", "_")
        out.append(lines.pop(key, raw))
    return "\n".join(out + list(lines.values())) + "\n"


class Desk(threading.Thread):
    """Holds scene lines, answers ``/node`` from them and stores a ``/`` root write.

    ``drop_writes``: paths whose first root write is ignored. ``snap``: path -> the line the
    desk stores instead (its grid). ``mute_after_write``: how many ``/node`` replies to lose
    for a path once it has been written. ``mute_first_read``: paths whose first read (two
    asks) gets no reply. ``lacks``: paths the desk has no node for. ``effects``: path
    written -> {other path: the line the desk then holds}, a write that changes another.
    """

    def __init__(self, text: str = BASE, *, drop_writes=(), snap=None, mute_after_write=0,
                 mute_first_read=(), lacks=(), effects=None):
        super().__init__(daemon=True)
        self.lines = {ln.path: ln.raw for ln in Scene.parse(text).lines if ln.path.startswith("/")}
        self.lacks = set(lacks)      # nodes this firmware has not: never answered, never stored
        self.effects = effects or {}
        self.writes: list[str] = []
        self.drop = dict.fromkeys(drop_writes, 1)
        self.snap = snap or {}
        self.mute_after_write = mute_after_write
        self.muted: dict[str, int] = dict.fromkeys(mute_first_read, 2)   # both asks of a read
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.05)
        self.port = self.sock.getsockname()[1]
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                data, client = self.sock.recvfrom(65536)
            except (TimeoutError, OSError):
                continue
            addr, args = O.decode_message(data)
            if addr == "/node":
                path = "/" + args[0]
                if self.muted.get(path):
                    self.muted[path] -= 1
                elif path in self.lines:
                    self.sock.sendto(O.encode_message("node", [self.lines[path] + "\n"]), client)
            elif addr == "/":
                raw = str(args[0])
                path = raw.split(" ", 1)[0]
                self.writes.append(raw)
                if path in self.lacks:
                    continue
                if self.drop.get(path):
                    self.drop[path] -= 1
                    continue
                self.lines[path] = self.snap.get(path, raw)
                self.lines.update(self.effects.get(path, {}))
                self.muted.setdefault(path, self.mute_after_write)   # the first write arms it

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self._halt.set()
        self.join()
        self.sock.close()


MIX_DOWN = "/ch/01/mix/01 ON  -9.0 +0 PRE 0"
GAIN_UP = "/headamp/000 +25.0 OFF"
