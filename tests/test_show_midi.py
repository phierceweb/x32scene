"""A cue line's last four integers are the MIDI command sent on recall: type, channel and
two parameters. `show` decodes them, and lists a cue's command when one is set."""

import contextlib
import io
import os
import tempfile
import unittest

from x32scene.cli import main
from x32scene.services.show import read_show

SHOW = '''#4.0#
show "midiprobe" 0 0 0 0 0 0 0 0 0 0 "x32scene"
cue/000 100 "PC" 0 -1 -1 1 5 42 0
cue/001 200 "CC" 0 -1 -1 2 6 43 44
cue/002 300 "Note" 0 -1 -1 3 7 45 46
cue/003 400 "Off" 0 -1 -1 0 1 0 0
'''


class ShowMidiTest(unittest.TestCase):
    def test_each_cue_decodes_its_midi_command(self):
        cues = {e.index: e.decoded["midi"] for e in read_show(SHOW).entries}
        self.assertEqual(cues[0], {"type": "program change", "channel": 5, "params": [42, 0]})
        self.assertEqual(cues[1], {"type": "control change", "channel": 6, "params": [43, 44]})
        self.assertEqual(cues[2], {"type": "note", "channel": 7, "params": [45, 46]})
        self.assertEqual(cues[3], {"type": "none", "channel": 1, "params": [0, 0]})

    def test_a_short_cue_line_decodes_without_midi(self):
        entry = read_show('cue/000 100 "Old" 0 -1 -1\n').entries[0]
        self.assertNotIn("midi", entry.decoded)

    def test_the_listing_names_a_set_command_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "midiprobe.shw")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SHOW)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = main(["show", path])
        self.assertEqual(rc, 0)
        lines = out.getvalue().splitlines()
        self.assertIn("midi program change ch 5 42", next(ln for ln in lines if "cue/000" in ln))
        self.assertIn("midi control change ch 6 43 44", next(ln for ln in lines if "cue/001" in ln))
        self.assertIn("midi note ch 7 45 46", next(ln for ln in lines if "cue/002" in ln))
        self.assertNotIn("midi", next(ln for ln in lines if "cue/003" in ln))


if __name__ == "__main__":
    unittest.main()
