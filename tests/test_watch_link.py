"""watch's UDP link against a loopback console: whose datagrams it believes, what it sends,
and draining what is waiting."""

import socket
import threading
import time
import unittest
from unittest import mock

from x32scene.services import watch as W
from x32scene.services.osc import decode_message, encode_message


class LinkTest(unittest.TestCase):
    """The UDP link believes only the desk's own address, as every live read does."""

    def setUp(self):
        self.console = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.console.bind(("127.0.0.1", 0))
        self.console.settimeout(2.0)
        self.port = self.console.getsockname()[1]

    def tearDown(self):
        self.console.close()

    def _push_after_subscribe(self):
        _, client = self.console.recvfrom(1024)
        self.console.sendto(encode_message("/ch/01/mix/on", [0]), client)

    def test_a_push_from_another_address_is_ignored(self):
        with mock.patch.object(W, "desk_address", return_value="10.0.0.99"):
            with W.UdpTransport("127.0.0.1", self.port) as link:
                t = threading.Thread(target=self._push_after_subscribe)
                t.start()
                link.send("/xremote")
                t.join()
                self.assertIsNone(link.recv(0.3))
        # positive control: the same push, from the address believed, is read
        with W.UdpTransport("127.0.0.1", self.port) as link:
            t = threading.Thread(target=self._push_after_subscribe)
            t.start()
            link.send("/xremote")
            t.join()
            self.assertEqual(link.recv(1.0), ("/ch/01/mix/on", [0]))

    def test_drain_returns_what_is_waiting_without_blocking(self):
        with W.UdpTransport("127.0.0.1", self.port) as link:
            started = time.monotonic()
            self.assertEqual(link.drain(), [])
            self.assertLess(time.monotonic() - started, 0.05)
            link.send("/xremote")
            _, client = self.console.recvfrom(1024)
            for n in (0, 1):
                self.console.sendto(encode_message("/ch/01/mix/on", [n]), client)
            self.console.sendto(b"not osc", client)
            time.sleep(0.1)
            self.assertEqual(link.drain(), [("/ch/01/mix/on", [0]), ("/ch/01/mix/on", [1])])
            self.console.sendto(encode_message("/ch/01/mix/on", [1]), client)
            self.assertEqual(link.recv(1.0), ("/ch/01/mix/on", [1]))   # recv still blocks

    def test_the_link_sends_what_it_is_given(self):
        with W.UdpTransport("127.0.0.1", self.port) as link:
            link.send("/node", ["ch/01/mix"])
            data, _ = self.console.recvfrom(1024)
        self.assertEqual(decode_message(data), ("/node", ["ch/01/mix"]))


if __name__ == "__main__":
    unittest.main()
