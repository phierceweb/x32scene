"""preset_filename keeps a channel name off the Windows console and superscript-digit
device names too: CONIN$, CONOUT$, COM¹-³ and LPT¹-³."""

import unittest

from x32scene.services.preset_library import preset_filename


class ConsoleDeviceNameTest(unittest.TestCase):
    def test_each_gains_a_leading_underscore(self):
        for name in ("CONIN$", "conout$", "CONIN$.x", "COM¹", "com²", "LPT³", "lpt¹ ."):
            with self.subTest(name=name):
                self.assertTrue(preset_filename(name).startswith("_"), preset_filename(name))

    def test_near_misses_are_left_alone(self):
        for name in ("CONINX", "COM⁴", "LPT0", "CONSOLE"):
            with self.subTest(name=name):
                self.assertEqual(preset_filename(name), name + ".chn")


if __name__ == "__main__":
    unittest.main()
