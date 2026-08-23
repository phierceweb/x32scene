"""The tap enumerations as a console writes them."""

import unittest

from x32scene.tables import OUTPUT_POS, SEND_TAPS


class TapTablesTest(unittest.TestCase):
    def test_output_pos_order_matches_the_console_enum(self):
        self.assertEqual(OUTPUT_POS[0], "IN/LC")
        self.assertEqual(OUTPUT_POS[1], "IN/LC+M")
        self.assertEqual(OUTPUT_POS[-1], "POST")
        self.assertEqual(len(OUTPUT_POS), 9)
        self.assertEqual(len(set(OUTPUT_POS)), 9)

    def test_send_taps_order_matches_the_console_enum(self):
        self.assertEqual(SEND_TAPS, ("IN/LC", "<-EQ", "EQ->", "PRE", "POST", "GRP"))


if __name__ == "__main__":
    unittest.main()
