"""pull when the reference opens with paths the desk's firmware lacks: a desk that answers
anything is read on; one that answers nothing still fails fast."""

import socket
import threading
import time
import unittest

from x32scene.model import Scene
from x32scene.services.osc import OscError, decode_message, encode_message, pull_scene_like

PATHS = [f"ch/{n:02d}/mix" for n in range(1, 25)]
REF = Scene.parse("".join(f"/{p} ON\n" for p in PATHS))


class Console(threading.Thread):
    """Answers ``/node`` for every path not in ``absent``, and ``/xinfo`` when ``xinfo``;
    ``node=False`` answers no ``/node`` at all."""

    def __init__(self, absent=(), xinfo: bool = True, node: bool = True):
        super().__init__(daemon=True)
        self.absent, self.xinfo, self.node = set(absent), xinfo, node
        self.received: list[str] = []
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
            addr, args = decode_message(data)
            self.received.append(addr)
            if addr == "/xinfo" and self.xinfo:
                self.sock.sendto(encode_message("/xinfo", ["127.0.0.1", "X32-TEST", "X32", "4.06"]),
                                 client)
            elif addr == "/node" and self.node and args[0] not in self.absent:
                self.sock.sendto(encode_message("node", [f"/{args[0]} ON\n"]), client)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self._halt.set()
        self.join()
        self.sock.close()


class AbsentPathsTest(unittest.TestCase):
    def test_a_reference_whose_first_paths_the_desk_lacks_is_read_on(self):
        # 16 and 20 run past a second give-up check, whose probe must still count
        for absent in (PATHS[:3], PATHS[:12], PATHS[:16], PATHS[:20]):
            with self.subTest(absent=len(absent)), Console(absent=absent) as desk:
                scene, missing = pull_scene_like(REF, "127.0.0.1", port=desk.port, timeout=0.05)
                self.assertEqual(missing, absent)
                self.assertEqual(len(scene.lines), len(PATHS) - len(absent))

    def test_a_silent_desk_still_fails_fast(self):
        with Console(xinfo=False, node=False) as desk:
            started = time.monotonic()
            with self.assertRaises(OscError) as cm:
                pull_scene_like(REF, "127.0.0.1", port=desk.port, timeout=0.05)
            self.assertLess(time.monotonic() - started, 0.05 * (3 * 2 + 2) + 0.3)
            self.assertEqual(desk.received, ["/node"] * 3 * 2 + ["/node", "/xinfo"])
        self.assertIn("desk off or unreachable", str(cm.exception))

    def test_a_device_answering_xinfo_but_no_node_fails_fast(self):
        with Console(xinfo=True, node=False) as desk:
            started = time.monotonic()
            with self.assertRaises(OscError) as cm:
                pull_scene_like(REF, "127.0.0.1", port=desk.port, timeout=0.05)
            self.assertLess(time.monotonic() - started, 0.05 * (3 * 2 + 2) + 0.3)
            self.assertEqual(desk.received, ["/node"] * 3 * 2 + ["/node", "/xinfo"])
        self.assertIn("answers /xinfo but no /node", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
