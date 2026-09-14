"""Guards on what the live link believes: a reply slower than one socket wait, an empty
reply, and a datagram from an address that is not the desk."""

import select
import socket
import unittest
from unittest import mock

from tests.test_osc import CANNED, FakeConsole
from x32scene.services import osc as O
from x32scene.services.osc import encode_message, node_line, pull_lines


class SlowReplyTest(unittest.TestCase):
    def test_a_reply_later_than_one_socket_wait_but_within_the_timeout_is_captured(self):
        console = FakeConsole(delay=0.7)
        console.start()
        try:
            lines, missing = pull_lines("127.0.0.1", ["ch/01/config"], port=console.port,
                                        timeout=1.5, retries=0)
        finally:
            console.stop()
        self.assertEqual((lines, missing), ([CANNED["ch/01/config"]], []))


class EmptyReplyTest(unittest.TestCase):
    def test_a_reply_with_no_arguments_is_not_a_line(self):
        self.assertIsNone(node_line([]))


class DrainSenderTest(unittest.TestCase):
    def drained(self, peer: str) -> list:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
            other.bind(("127.0.0.1", 0))
            other.settimeout(2.0)
            with mock.patch.object(O, "desk_address", return_value=peer), \
                 O.UdpTransport("127.0.0.1", other.getsockname()[1]) as link:
                link.send("/xremote")
                _, client = other.recvfrom(64)
                other.sendto(encode_message("/ch/01/mix/fader", [0.5]), client)
                select.select([link._sock], [], [], 1.0)
                return link.drain()

    def test_a_push_from_another_address_is_dropped(self):
        self.assertEqual(self.drained("10.0.0.99"), [])
        self.assertEqual(len(self.drained("127.0.0.1")), 1)


if __name__ == "__main__":
    unittest.main()
