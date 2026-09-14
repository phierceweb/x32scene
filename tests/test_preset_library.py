"""A folder of channel presets against a scene: matching, drift, and regenerating it."""

import os
import shutil
import tempfile
import unittest

from x32scene import Scene
from x32scene.services import preset_library as lib
from x32scene.services.presets import extract_preset

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "example.scn")


def _rename(sc: Scene, ch: int, name: str) -> None:
    sc.get(f"/ch/{ch:02d}/config").set_arg(0, f'"{name}"')


class MatchTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_name_match_ignores_case_quotes_and_surrounding_space(self):
        self.assertEqual(lib.match_channels(self.sc, "snare top"), [3])
        self.assertEqual(lib.match_channels(self.sc, '" SNARE TOP "'), [3])

    def test_name_match_is_exact_otherwise(self):
        self.assertEqual(lib.match_channels(self.sc, "Snare"), [])

    def test_every_channel_sharing_a_name_is_returned(self):
        _rename(self.sc, 5, "kick")
        self.assertEqual(lib.match_channels(self.sc, "Kick"), [1, 5])

    def test_an_empty_name_matches_nothing(self):
        self.assertEqual(lib.match_channels(self.sc, ""), [])


class CheckPresetTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def check(self, text, file="Kick.chn", scopes=None, scene=None):
        return lib.check_preset(scene or self.sc, file, text, scopes)

    def test_a_fresh_extract_matches_its_channel(self):
        r = self.check(extract_preset(self.sc, 1), file="whatever.chn")
        self.assertEqual((r.status, r.channels, r.drift), (lib.MATCH, [1], []))
        self.assertGreater(r.compared, 0)

    def test_a_changed_value_is_drift_naming_both_sides(self):
        chn = extract_preset(self.sc, 1)
        edited = Scene.load(EXAMPLE)
        edited.get("/ch/01/eq/1").set_arg(2, "+3.00")
        r = self.check(chn, scene=edited)
        self.assertEqual(r.status, lib.DRIFT)
        self.assertEqual([(d.path, d.preset, d.scene) for d in r.drift],
                         [("/eq/1", ["PEQ", "36.0", "+0.00", "1.0"],
                           ["PEQ", "36.0", "+3.00", "1.0"])])

    def test_column_padding_is_not_drift(self):
        chn = extract_preset(self.sc, 1).replace("/eq/1 PEQ 36.0", "/eq/1  PEQ   36.0")
        self.assertEqual(self.check(chn).status, lib.MATCH)

    def test_without_a_config_line_the_filename_stem_names_the_channel(self):
        chn = extract_preset(self.sc, 3, scopes=["eq"])
        r = self.check(chn, file="snare top.chn")
        self.assertEqual((r.status, r.channels, r.name), (lib.MATCH, [3], "snare top"))

    def test_the_config_name_wins_over_the_filename(self):
        r = self.check(extract_preset(self.sc, 3), file="Kick.chn")
        self.assertEqual(r.channels, [3])

    def test_an_empty_config_name_falls_back_to_the_filename(self):
        chn = extract_preset(self.sc, 3).replace('"Snare Top"', '""')
        r = self.check(chn, file="Snare Top.chn")
        self.assertEqual(r.channels, [3])
        self.assertEqual([d.path for d in r.drift], ["/config"])

    def test_no_channel_of_that_name(self):
        r = self.check(extract_preset(self.sc, 1, scopes=["eq"]), file="Theremin.chn")
        self.assertEqual((r.status, r.channels), (lib.NO_CHANNEL, []))

    def test_two_channels_of_that_name_is_ambiguous_never_a_guess(self):
        _rename(self.sc, 5, "KICK")
        r = self.check(extract_preset(self.sc, 1))
        self.assertEqual((r.status, r.channels, r.drift), (lib.AMBIGUOUS, [1, 5], []))

    def test_only_selected_scopes_are_compared(self):
        chn = extract_preset(self.sc, 1)
        edited = Scene.load(EXAMPLE)
        edited.get("/ch/01/eq/1").set_arg(2, "+3.00")
        self.assertEqual(self.check(chn, scopes=["gate", "comp"], scene=edited).status,
                         lib.MATCH)
        self.assertEqual(self.check(chn, scopes=["eq"], scene=edited).status, lib.DRIFT)

    def test_the_source_slot_in_config_is_not_drift(self):
        # apply-preset never repatches a channel, so a preset saved on another input matches
        chn = extract_preset(self.sc, 1).replace('/config "Kick" 2 YEi 1', '/config "Kick" 2 YEi 9')
        self.assertEqual(self.check(chn).status, lib.MATCH)

    def test_a_desk_written_config_without_the_source_slot_compares_the_rest(self):
        chn = extract_preset(self.sc, 1).replace('/config "Kick" 2 YEi 1', '/config "Kick" 2 YEi')
        self.assertEqual(self.check(chn).status, lib.MATCH)
        r = self.check(chn.replace('"Kick" 2 YEi', '"Kick" 2 RDi'))
        self.assertEqual([(d.path, d.preset, d.scene) for d in r.drift],
                         [("/config", ['"Kick"', "2", "RDi"], ['"Kick"', "2", "YEi"])])

    def test_split_main_fader_lines_compare_against_the_combined_mix_line(self):
        # a desk-written preset stores the main mix one sub-path per field
        split = "/mix/fader  +6.5\n/mix/st ON\n/mix/pan +0\n/mix/mono OFF\n/mix/mlevel   -oo\n"
        chn = extract_preset(self.sc, 1).replace("/mix ON +6.5 ON +0 OFF -oo\n", split)
        self.assertIn("/mix/fader", chn)
        self.assertEqual(self.check(chn).status, lib.MATCH)
        r = self.check(chn.replace("/mix/fader  +6.5", "/mix/fader -3.0"))
        self.assertEqual([(d.path, d.preset, d.scene) for d in r.drift],
                         [("/mix/fader", ["-3.0"], ["+6.5"])])

    def test_a_path_the_scene_lacks_is_drift(self):
        chn = extract_preset(self.sc, 1)
        edited = Scene([ln for ln in Scene.load(EXAMPLE).lines if ln.path != "/ch/01/automix"])
        r = self.check(chn, scene=edited)
        self.assertEqual([(d.path, d.scene) for d in r.drift], [("/automix", None)])

    def test_head_amp_compares_values_at_the_channels_current_index(self):
        chn = extract_preset(self.sc, 1).replace("/headamp/000", "/headamp/099")
        self.assertEqual(self.check(chn).status, lib.MATCH)
        edited = Scene.load(EXAMPLE)
        edited.get("/headamp/000").set_arg(0, "+40.0")
        r = self.check(chn, scene=edited)
        self.assertEqual([(d.path, d.preset, d.scene) for d in r.drift],
                         [("/headamp/000", ["+27.5", "OFF"], ["+40.0", "OFF"])])

    def test_head_amp_on_a_source_without_one_is_not_comparable(self):
        chn = extract_preset(self.sc, 31) + "/headamp/000 +27.0 OFF\n"   # DAW L <- card
        r = self.check(chn, file="DAW L.chn")
        self.assertEqual((r.status, r.uncompared), (lib.MATCH, ["/headamp/000"]))

    def test_a_filename_stem_matches_a_name_whose_characters_were_replaced(self):
        for ch, name in ((5, "Tom 1/2"), (6, ".38")):
            _rename(self.sc, ch, name)
            chn = extract_preset(self.sc, ch, scopes=["eq"])
            with self.subTest(name=name):
                r = self.check(chn, file=lib.preset_filename(name))
                self.assertEqual((r.status, r.channels), (lib.MATCH, [ch]))

    def test_a_file_that_is_not_a_channel_preset_is_unreadable(self):
        snp = os.path.join(os.path.dirname(EXAMPLE), "example.snp")
        for label, path in (("snippet", snp), ("whole scene", EXAMPLE)):
            with open(path, encoding="utf-8", newline="") as fh, self.subTest(label):
                self.assertEqual(self.check(fh.read()).status, lib.UNREADABLE)
        self.assertEqual(self.check("hello world\n").status, lib.UNREADABLE)

    def test_a_header_line_is_not_compared(self):
        chn = extract_preset(self.sc, 1, header="Something Else")
        self.assertEqual(self.check(chn).status, lib.MATCH)

    def test_unreadable_presets_are_listed_not_raised(self):
        for label, text in (("CR endings", "/eq ON\r\n"), ("empty", ""),
                            ("header only", extract_preset(self.sc, 1, header=True)
                             .splitlines()[0] + "\n")):
            with self.subTest(label):
                r = self.check(text)
                self.assertEqual(r.status, lib.UNREADABLE)
                self.assertTrue(r.reason)


class HeaderScopeTest(unittest.TestCase):
    """A header that leaves a section unflagged: apply skips it, so the compare does too."""

    def test_the_compare_covers_what_an_apply_of_the_preset_touches(self):
        sc = Scene.load(EXAMPLE)
        header = extract_preset(sc, 1, ["eq"], header=True).splitlines()[0]
        body = extract_preset(sc, 1)
        drifted = Scene.load(EXAMPLE)
        drifted.get("/ch/01/gate").set_arg(2, "-10.0")
        self.assertEqual(lib.check_preset(drifted, "Kick.chn", body).status, lib.DRIFT)
        self.assertEqual(lib.check_preset(drifted, "Kick.chn", header + "\n" + body).status,
                         lib.MATCH)
        self.assertEqual(lib.check_preset(drifted, "Kick.chn", header + "\n" + body,
                                          ["gate"]).status, lib.DRIFT)


class CheckLibraryTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def _write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def test_reads_only_chn_files_directly_in_the_directory(self):
        self._write("Kick.chn", extract_preset(self.sc, 1))
        self._write("Hat.CHN", extract_preset(self.sc, 13))
        self._write("notes.txt", "hello\n")
        self._write("sub/Ride.chn", extract_preset(self.sc, 14))
        self.assertEqual([r.file for r in lib.check_library(self.sc, self.dir)],
                         ["Hat.CHN", "Kick.chn"])

    def test_a_file_that_cannot_be_read_is_unreadable(self):
        with open(os.path.join(self.dir, "Kick.chn"), "wb") as fh:
            fh.write(b"/config \xff\n")
        [r] = lib.check_library(self.sc, self.dir)
        self.assertEqual(r.status, lib.UNREADABLE)

    def test_the_reader_is_the_callers(self):
        self._write("Kick.chn", "ignored\n")
        seen = []

        def read(path):
            seen.append(os.path.basename(path))
            return extract_preset(self.sc, 1)

        [r] = lib.check_library(self.sc, self.dir, read=read)
        self.assertEqual((seen, r.status), (["Kick.chn"], lib.MATCH))

    def test_appledouble_sidecars_and_anything_not_a_regular_file_are_never_read(self):
        self._write("Kick.chn", extract_preset(self.sc, 1))
        self._write("._Kick.chn", "\x00\x05\x16\x07")
        os.mkfifo(os.path.join(self.dir, "Pipe.chn"))
        os.symlink(os.path.join(self.dir, "gone"), os.path.join(self.dir, "Dangling.chn"))
        seen = []

        def read(path):
            seen.append(os.path.basename(path))
            return extract_preset(self.sc, 1)

        self.assertEqual([r.file for r in lib.check_library(self.sc, self.dir, read=read)],
                         ["Kick.chn"])
        self.assertEqual(seen, ["Kick.chn"])


class ExtractLibraryTest(unittest.TestCase):
    def setUp(self):
        self.sc = Scene.load(EXAMPLE)

    def test_one_preset_per_named_channel_and_the_unnamed_skipped(self):
        presets, skipped, shared = lib.extract_library(self.sc)
        self.assertEqual((skipped, shared), ([29], []))
        self.assertEqual(len(presets), 31)
        first = presets[0]
        self.assertEqual((first.ch, first.name, first.file), (1, "Kick", "Kick.chn"))
        self.assertEqual(first.text, extract_preset(self.sc, 1))

    def test_scopes_and_header_reach_every_preset(self):
        presets, _, _ = lib.extract_library(self.sc, ["eq"], header=True)
        self.assertEqual(presets[0].text, extract_preset(self.sc, 1, ["eq"], header=True))

    def test_filenames_replace_characters_a_filesystem_refuses(self):
        self.assertEqual(lib.preset_filename(r'a/b\c:d*e?f"g<h>i|j'), "a_b_c_d_e_f_g_h_i_j.chn")
        self.assertEqual(lib.preset_filename("  Vox 1 "), "Vox 1.chn")

    def test_a_leading_dot_neither_hides_the_file_nor_loses_its_extension(self):
        from x32scene.services.validate import kind_of
        for name, want in ((".", "_.chn"), ("...", "_...chn"), (".38 Special", "_38 Special.chn")):
            with self.subTest(name=name):
                self.assertEqual(lib.preset_filename(name), want)
                self.assertEqual(kind_of(want), "chn")

    def test_names_differing_only_in_unicode_normalization_share_a_filename(self):
        import unicodedata
        _rename(self.sc, 5, unicodedata.normalize("NFC", "Café"))
        _rename(self.sc, 6, unicodedata.normalize("NFD", "CAFÉ"))
        presets, _, shared = lib.extract_library(self.sc)
        want = unicodedata.normalize("NFC", "Café.chn")
        self.assertEqual([(s.file, s.channels) for s in shared], [(want, [5, 6])])
        self.assertFalse({5, 6} & {p.ch for p in presets})

    def test_a_whitespace_only_name_is_unnamed(self):
        _rename(self.sc, 4, "   ")
        self.assertIn(4, lib.extract_library(self.sc)[1])

    def test_every_channel_on_a_shared_filename_is_skipped_and_the_rest_extracted(self):
        _rename(self.sc, 5, "KICK")
        _rename(self.sc, 6, "Gtr/1")
        _rename(self.sc, 7, "Gtr:1")
        presets, skipped, shared = lib.extract_library(self.sc)
        self.assertEqual([(s.file, s.channels) for s in shared],
                         [("Kick.chn", [1, 5]), ("Gtr_1.chn", [6, 7])])
        self.assertEqual(skipped, [29])
        self.assertEqual([p.ch for p in presets],
                         [c for c in range(2, 33) if c not in (5, 6, 7, 29)])

    def test_a_name_shared_three_ways_skips_all_three(self):
        for ch in (8, 3, 20):
            _rename(self.sc, ch, "Snare 2")
        _, _, shared = lib.extract_library(self.sc)
        self.assertEqual([(s.file, s.channels) for s in shared], [("Snare 2.chn", [3, 8, 20])])


if __name__ == "__main__":
    unittest.main(verbosity=2)
