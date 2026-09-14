"""pull when the desk stops answering part-way: it gives up after a run of unanswered paths
instead of timing out over every remaining one, but not while the desk still answers."""

import socket
import threading
import time
import unittest

from x32scene.model import Scene
from x32scene.services.osc import OscError, decode_message, encode_message, pull_lines, pull_scene_like

PATHS = [f"ch/{n:02d}/mix" for n in range(1, 33)]


class DroppingConsole(threading.Thread):
    """Answers ``/node`` for any path not in ``absent`` until it has answered ``answers``
    queries, then goes silent."""

    def __init__(self, answers: int = 10_000, absent=(), delay: float = 0.0):
        super().__init__(daemon=True)
        self.answers, self.absent, self.delay = answers, set(absent), delay
        self.queries = 0
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
            self.queries += 1
            if addr == "/node" and args[0] not in self.absent and self.answers > 0:
                self.answers -= 1
                reply = encode_message("node", [f"/{args[0]} ON\n"])
                if self.delay:
                    threading.Timer(self.delay, self._send, (reply, client)).start()
                else:
                    self.sock.sendto(reply, client)

    def _send(self, reply, client):
        if not self._halt.is_set():
            self.sock.sendto(reply, client)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self._halt.set()
        self.join()
        self.sock.close()


class GiveUpTest(unittest.TestCase):
    def test_a_desk_that_stops_answering_is_given_up_on(self):
        with DroppingConsole(answers=3) as desk:
            with self.assertRaises(OscError) as cm:
                pull_lines("127.0.0.1", PATHS, port=desk.port, timeout=0.05, retries=0,
                           give_up=4)
            self.assertLessEqual(desk.queries, 3 + 4 + 1)
        self.assertIn("4 queries in a row", str(cm.exception))
        self.assertIn("desk off or unreachable", str(cm.exception))

    def test_a_run_of_paths_the_desk_lacks_is_not_given_up_on(self):
        absent = PATHS[1:12]
        with DroppingConsole(absent=absent) as desk:
            lines, missing = pull_lines("127.0.0.1", PATHS, port=desk.port, timeout=0.05,
                                        retries=0, give_up=4)
        self.assertEqual(missing, absent)
        self.assertEqual(len(lines), len(PATHS) - len(absent))

    def test_a_desk_whose_every_reply_is_late_is_not_given_up_on(self):
        with DroppingConsole(delay=0.08) as desk:
            lines, missing = pull_lines("127.0.0.1", PATHS, port=desk.port, timeout=0.05,
                                        retries=0, give_up=4)
        self.assertLessEqual(len(missing), 1)
        self.assertEqual(len(lines) + len(missing), len(PATHS))

    def test_a_scene_pull_gives_up_by_default(self):
        ref = Scene.parse("".join(f"/{p} ON\n" for p in PATHS))
        started = time.monotonic()
        with DroppingConsole(answers=2) as desk, self.assertRaises(OscError):
            pull_scene_like(ref, "127.0.0.1", port=desk.port, timeout=0.05)
        self.assertLess(time.monotonic() - started, 0.1 * 16)


if __name__ == "__main__":
    unittest.main()
