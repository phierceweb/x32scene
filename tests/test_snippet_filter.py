"""A filter typed by name, and the slice of a scene a desk snippet slot saved through it
recalls: every line the filter covers and no other, head amps by the channel mask."""

import os
import random
import unittest

from x32scene import Scene
from x32scene.model import Line
from x32scene.services.routing import channel_sources, resolve_in_slot_number
from x32scene.services.snippet_filter import (STRIP_CATEGORIES, filtered_snippet,
                                              header_from_names)
from x32scene.services.snippets import EVENTTYP_BITS, SnippetHeader, read_header, snippet_lines

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")
SOME = "ch1-8,ch11-12,ch20"
# name: (categories, strips, the header they spell, body lines on example.scn)
FILTERS = {
    "keep": (["Send 9-12", "Config"], ["ch", "auxin,fxrtn", "bus9-10"],
             SnippetHeader("keep", 514, 0xFFFFFFFF, 0x0300FFFF, 0), 274),
    "one vocal": (["Send 1-8"], ["ch25"], SnippetHeader("one vocal", 256, 1 << 24, 0, 0), 8),
    "mixes": (["Send 1-8", "Send 9-12", "Send 13-16", "Config"], ["ch,auxin,fxrtn,bus9-10"],
              SnippetHeader("mixes", 1794, 0xFFFFFFFF, 0x0300FFFF, 0), 850),
    "strips": (["strip"], [SOME, "bus5-8"],
               SnippetHeader("strips", 8191, 0x00080CFF, 0x00F00000, 0), 503),
}


def random_header(rng: random.Random) -> SnippetHeader:
    return SnippetHeader("r", rng.getrandbits(27), rng.getrandbits(32), rng.getrandbits(32),
                         rng.getrandbits(16))


def masked_headamps(sc: Scene, header: SnippetHeader) -> set[str]:
    """The head amps of the header's channels, by source number."""
    out = set()
    for cs in channel_sources(sc):
        num = resolve_in_slot_number(sc, cs.slot)
        if header.channels >> (cs.ch - 1) & 1 and 1 <= num <= 128:
            out.add(f"/headamp/{num - 1:03d}")
    return out


class HeaderFromNamesTest(unittest.TestCase):
    def test_names_spell_the_masks(self):
        for name, (cats, strips, header, _) in FILTERS.items():
            with self.subTest(filter=name):
                self.assertEqual(header_from_names(name, cats, strips), header)

    def test_a_decoded_header_types_back(self):
        rng = random.Random(7)
        for _ in range(200):
            d = random_header(rng).describe()
            back = header_from_names("r", d["filters"],
                                     d["channels"] + d["auxbuses"] + d["maingrps"])
            self.assertEqual(back.describe(), d)

    def test_a_category_matches_in_any_case_and_spacing(self):
        want = header_from_names("n", ["Fader, Pan", "Send M/C, LR", "Gate & Comp"], [])
        self.assertEqual(want.eventtyp, 1 << 6 | 1 << 11 | 1 << 3)
        for spelled in (["fader, pan", "SEND M/C, LR", "gate & comp"],
                        ["  Fader,   Pan ", "send  m/c, lr", "Gate  &  Comp", "Fader, Pan"]):
            self.assertEqual(header_from_names("n", spelled, []), want)

    def test_strip_is_the_thirteen_per_strip_categories(self):
        h = header_from_names("n", ["STRIP"], [])
        self.assertEqual(h.eventtyp, STRIP_CATEGORIES)
        self.assertEqual(h.describe()["filters"], list(EVENTTYP_BITS[:13]))

    def test_strip_specs(self):
        cases = {"ch": ("channels", 0xFFFFFFFF), "ch1": ("channels", 1), "CH32": ("channels", 1 << 31),
                 "ch01-02": ("channels", 3), "ch3 , ch5": ("channels", 0b10100),
                 "auxin": ("auxbuses", 0xFF), "fxrtn2": ("auxbuses", 1 << 9),
                 "bus16": ("auxbuses", 1 << 31), "bus1-16": ("auxbuses", 0xFFFF0000),
                 "mtx": ("maingrps", 0x3F), "main/st": ("maingrps", 1 << 6),
                 "main/m": ("maingrps", 1 << 7), "dca": ("maingrps", 0xFF00),
                 "dca8,mtx6": ("maingrps", 1 << 15 | 1 << 5)}
        for spec, (mask, bits) in cases.items():
            with self.subTest(spec=spec):
                h = header_from_names("n", [], [spec])
                self.assertEqual(getattr(h, mask), bits)
                self.assertEqual(h.channels | h.auxbuses | h.maingrps, bits)

    def test_an_unknown_name_is_refused(self):
        for cats, strips, said in (
                (["Sends"], [], r"no snippet category 'Sends': one of Preamp HA, Config, .*User Out, "
                                r"or strip"),
                ([""], [], r"no snippet category ''"),
                ([], ["ch0"], r"ch0: ch runs 1-32"), ([], ["ch33"], r"ch33: ch runs 1-32"),
                ([], ["bus17"], r"bus17: bus runs 1-16"), ([], ["ch5-3"], r"ch5-3: ch runs 1-32"),
                ([], ["main/x"], r"no strip 'main/x'"), ([], ["chan1"], r"no strip 'chan1'"),
                ([], [""], r"no strip ''"), ([], ["ch1,"], r"no strip ''"),
                ([], ["ch1-"], r"no strip 'ch1-'"), ([], ["main/st1"], r"no strip 'main/st1'")):
            with self.subTest(cats=cats, strips=strips), self.assertRaisesRegex(ValueError, said):
                header_from_names("n", cats, strips)


class FilteredSnippetTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)
        self.split = [Line.parse(raw).path for ln in self.sc.lines[1:] if ln.path
                      for raw in snippet_lines(ln)]

    def check(self, header: SnippetHeader) -> list[str]:
        snip = filtered_snippet(self.sc, header)
        text = snip.scene.dump()
        self.assertEqual(Scene.parse(text).dump(), text)
        self.assertEqual(text.split("\n")[0], header.line())
        self.assertEqual(read_header(text), header)
        self.assertEqual((snip.header, snip.skipped), (header, []))
        body = [ln.path for ln in snip.scene.lines[1:]]
        amps = masked_headamps(self.sc, header) if header.eventtyp & 1 else set()
        want = [p for p in self.split
                if (p in amps if p.startswith("/headamp/") else header.covers(p))]
        self.assertEqual(body, want)
        return body

    def amps(self, header: SnippetHeader) -> list[str]:
        return [p for p in self.check(header) if p.startswith("/headamp/")]

    def test_the_slice_is_every_covered_line_in_scene_order(self):
        for name, (_, _, header, lines) in FILTERS.items():
            with self.subTest(filter=name):
                self.assertEqual(len(self.check(header)), lines)

    def test_any_filter_takes_covered_lines_only(self):
        rng = random.Random(11)
        for _ in range(50):
            self.check(random_header(rng))

    def test_head_amps_follow_the_channel_mask(self):
        every = self.amps(SnippetHeader("ha", 1, 0xFFFFFFFF, 0, 0))
        self.assertEqual(set(every), masked_headamps(self.sc, SnippetHeader("", 1, 0xFFFFFFFF)))
        self.assertTrue(0 < len(every) < 128)
        self.assertEqual(self.check(SnippetHeader("ha", 1, 1, 0, 0)),
                         ["/ch/01/preamp", "/headamp/000"])
        self.assertEqual(self.amps(SnippetHeader("ha", 1, 0, 0xFFFFFFFF, 0xFFFF)), [])
        self.assertEqual(self.amps(SnippetHeader("ha", 1, 1 << 29, 0, 0)), [])   # ch 30: no head amp

    def test_a_body_line_is_the_scene_line_as_written(self):
        snip = filtered_snippet(self.sc, FILTERS["one vocal"][2])
        self.assertEqual([ln.raw for ln in snip.scene.lines[1:]],
                         [self.sc.get(f"/ch/25/mix/{n:02d}").raw for n in range(1, 9)])

    def test_under_play_head_amps_follow_the_play_bank(self):
        text = self.sc.dump().replace("/config/routing REC", "/config/routing PLAY")
        self.sc = Scene.parse(text)
        self.split = [Line.parse(raw).path for ln in self.sc.lines[1:] if ln.path
                      for raw in snippet_lines(ln)]
        self.assertEqual(self.amps(SnippetHeader("ha", 1, 0xFFFFFFFF, 0, 0)),
                         [f"/headamp/{n:03d}" for n in range(40, 44)])   # ch 25-28, the user patch

    def test_a_channel_line_with_no_slot_matters_only_to_head_amps(self):
        text = self.sc.dump().replace('/ch/30/config "Click" 1 WHi 30', '/ch/30/config "Click" 1 WHi')
        sc = Scene.parse(text)
        self.assertEqual(len(filtered_snippet(sc, FILTERS["one vocal"][2]).scene.lines), 9)
        with self.assertRaisesRegex(ValueError, r"/ch/30/config ends in 'WHi', not a source slot"):
            filtered_snippet(sc, SnippetHeader("ha", 1, 1 << 29, 0, 0))


if __name__ == "__main__":
    unittest.main()
