"""The fake console the `watch` CLI tests run against, on loopback, and the base class that
points the command at it. Not collected by pytest."""

import _thread
import contextlib
import io
import os
import shutil
import signal
import socket
import tempfile
import threading
import unittest
from unittest import mock

from x32scene.cli import main
from x32scene.model import Scene
from x32scene.services import osc as O
from x32scene.services.osc import decode_message, encode_message

REF_TEXT = ('#4.0# "REF" "" %000000000 1\n'
            '/ch/01/config "Kick" 2 YEi 1\n'
            "/ch/01/eq/1 PEQ 52.6 +4.75 1.6\n"
            "/ch/01/mix ON  -4.8 ON +0 OFF   -oo\n"
            "/ch/01/mix/01 ON  -7.9 +0 PRE 0\n"
            "/ch/02/mix ON  -oo ON +0 OFF   -oo\n")
MIX_START = "/ch/01/mix ON  -4.8 ON +0 OFF   -oo"
MIX_DOWN = "/ch/01/mix ON -10.0 ON +0 OFF   -oo"
EQ_UP = "/ch/01/eq/1 PEQ 52.6 +7.75 1.6"
READ_BACK = object()


class WatchConsole(threading.Thread):
    """Answers /node from ``text``. When the watch itself subscribes (the first /xremote
    after the start pull has asked for every path held here) plays ``script``: (delay, new
    line or None, leaf addresses), or (delay, "INTERRUPT") to press Ctrl-C on the watcher. A
    delay is seconds after the step before it, or ``READ_BACK``: once the watcher has been
    answered the line the console last changed. Pushes go only to a subscriber. A path in
    ``lose`` answers its first /node only, or as many as a mapping gives it; ``on_query`` is
    (path, new line, leaves), played when that path is first queried."""

    def __init__(self, text: str = REF_TEXT, script=(), answer: bool = True, lose=(),
                 on_query=None, reply_delay: float = 0.0):
        super().__init__(daemon=True)
        self.state = {ln.path: ln.raw for ln in Scene.parse(text).lines if ln.path.startswith("/")}
        self.lose = dict(lose) if isinstance(lose, dict) else dict.fromkeys(lose, 1)
        self.script, self.answer, self.on_query = list(script), answer, on_query
        self.answers: dict[str, int] = {}
        self.reply_delay = reply_delay
        self.received: list[str] = []
        self.asked: set[str] = set()
        self.subscriber = None
        self._playing, self._changed = False, None
        self._lock, self._read_back = threading.Lock(), threading.Event()
        self._read_back.set()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
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
            if addr == "/node":
                self._answer("/" + args[0], client)
            elif addr == "/xremote" and self.subscriber is None:
                self.subscriber = client
            elif addr == "/xremote" and not self._playing and self.state.keys() <= self.asked:
                self._playing = True
                threading.Thread(target=self._play, daemon=True).start()

    def _answer(self, path: str, client) -> None:
        first = path not in self.asked
        self.asked.add(path)
        if first and self.on_query and self.on_query[0] == path:
            self._change(*self.on_query[1:])
        n = self.answers.get(path, 0)
        if self.answer and path in self.state and n < self.lose.get(path, n + 1):
            self.answers[path] = n + 1
            self._halt.wait(self.reply_delay)
            with self._lock:   # a change lands wholly before this reply or wholly after it
                self.sock.sendto(encode_message("node", [self.state[path] + "\n"]), client)
                if path == self._changed:
                    self._read_back.set()

    def _change(self, new_line, leaves) -> None:
        if new_line:
            with self._lock:
                self._changed = new_line.split(" ", 1)[0]
                self.state[self._changed] = new_line
                self._read_back.clear()
        for leaf in leaves if self.subscriber else ():
            self.sock.sendto(encode_message(leaf, [0.5]), self.subscriber)

    def _play(self):
        for delay, *step in self.script:
            if delay is READ_BACK:
                self._read_back.wait(5)
            else:
                self._halt.wait(delay)
            if self._halt.is_set():
                return
            if step[0] == "INTERRUPT":
                _thread.interrupt_main()
                continue
            self._change(*step)

    def stop(self):
        self._halt.set()
        self.join()
        self.sock.close()


class WatchCliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ref = os.path.join(self.tmp, "ref.scn")
        with open(self.ref, "w") as fh:
            fh.write(REF_TEXT)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # interrupt_main does nothing while SIGINT is ignored, as in a backgrounded shell
        self.addCleanup(signal.signal, signal.SIGINT,
                        signal.signal(signal.SIGINT, signal.default_int_handler))

    def watch(self, console, *argv):
        out, err = io.StringIO(), io.StringIO()
        console.start()
        try:
            with mock.patch.object(O, "X32_PORT", console.port), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(["watch", self.ref, "--ip", "127.0.0.1", "--timeout", "0.2", *argv])
        finally:
            console.stop()
        return rc, out.getvalue(), err.getvalue()
