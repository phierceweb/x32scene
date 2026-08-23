"""Byte-faithful round-trip (``Scene.parse(text).dump() == text``) plus the guards
round-trip alone cannot provide: token validation and edit->reparse structure checks
(verbatim storage round-trips ANY input, including ones the token layer misreads).

Coverage: the checked-in example scenes (always run), and optionally your own library —
point ``X32SCENE_CORPUS`` at a directory of real ``.scn``/``.chn`` files.
"""

import glob
import os
import tempfile
import unittest

from x32scene import Scene, tokenize
from x32scene.model import HEADER_WIDTH

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

HEADER = '#4.0# "Example Rig" "" %000000000 1'.ljust(HEADER_WIDTH)

# Exercises the format's awkward corners: padded header, quoted names containing
# spaces, an -oo token, mixed numeric formats, and a line the model has no opinion on.
SCENE = "\n".join([
    HEADER,
    "/config/routing/IN AN1-8 AN9-16 A1-8 A9-16",
    '/ch/01/config "Kick" 1 67 1',
    "/ch/01/mix ON   0.0 ON +0 OFF   -oo",
    '/ch/02/config "Gtr 1 DI" 1 67 2',
    "/ch/02/dyn ON COMP RMS LOG -18.0 4.0 0 2.0 10 80 POST 100 OFF 100",
    "/headamp/000 +27.0 OFF",
    "/fx/1 PLAT",
    "/some/unknown/path with weird tokens 1 2 3",
]) + "\n"


class RoundTripTest(unittest.TestCase):
    def test_byte_faithful_roundtrip(self):
        self.assertEqual(Scene.parse(SCENE).dump(), SCENE)

    def test_header_padding_survives(self):
        emitted = Scene.parse(SCENE).dump()
        self.assertEqual(len(emitted.split("\n")[0]), HEADER_WIDTH)

    def test_unknown_lines_survive_verbatim(self):
        emitted = Scene.parse(SCENE).dump()
        self.assertIn("/some/unknown/path with weird tokens 1 2 3", emitted)

    def test_fixture_scenes_roundtrip(self):
        """The checked-in example scenes — anonymized full-console exports, 2118 lines each."""
        files = sorted(glob.glob(os.path.join(FIXTURES, "*.scn")))
        self.assertTrue(files, "no fixture scenes found")
        for path in files:
            with self.subTest(file=os.path.basename(path)):
                with open(path, encoding="utf-8", newline="") as fh:
                    original = fh.read()
                self.assertEqual(Scene.parse(original).dump(), original)

    @unittest.skipUnless(os.environ.get("X32SCENE_CORPUS"),
                         "set X32SCENE_CORPUS to a scene directory to run")
    def test_user_corpus_roundtrips(self):
        """Opt-in: prove the parser against exports this repo has never seen."""
        root = os.environ["X32SCENE_CORPUS"]
        files = []
        for ext in ("scn", "chn"):
            files.extend(glob.glob(os.path.join(root, "**", f"*.{ext}"), recursive=True))
        self.assertTrue(files, f"no .scn/.chn found under {root}")
        for path in sorted(files):
            with self.subTest(file=os.path.basename(path)):
                with open(path, encoding="utf-8", newline="") as fh:
                    original = fh.read()
                self.assertEqual(Scene.parse(original).dump(), original)

    def test_save_is_byte_identical_to_dump(self):
        """Round-trip through a FILE, not only memory. A text-mode write translates
        newlines per platform (CRLF on Windows), which parse() rejects and the desk
        cannot load — so the saved bytes must equal dump()'s, verbatim."""
        with open(os.path.join(FIXTURES, "example.scn"), encoding="utf-8",
                  newline="") as fh:
            fixture = fh.read()
        for name, text in (("synthetic", SCENE), ("fixture", fixture)):
            with self.subTest(source=name), tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "out.scn")
                Scene.parse(text).save(out)
                with open(out, "rb") as fh:
                    raw = fh.read()
                self.assertNotIn(b"\r", raw)
                self.assertEqual(raw, text.encode("utf-8"))
                self.assertEqual(Scene.load(out).dump(), text)

    def test_tokenize_roundtrips_with_quotes(self):
        line = '/ch/01/config "Lead Vox" 1 1 1'
        self.assertEqual(tokenize(line), ["/ch/01/config", '"Lead Vox"', "1", "1", "1"])


class MutationGuardTest(unittest.TestCase):
    """set_arg is the primitive every transform funnels through, so it is where a value
    that would break the line's token structure has to be refused."""

    def _line(self):
        return Scene.parse(SCENE).get("/ch/01/config")

    def test_rejects_embedded_quote_in_quoted_token(self):
        with self.assertRaises(ValueError):
            self._line().set_arg(0, '"24" Kick"')

    def test_rejects_newline(self):
        with self.assertRaises(ValueError):
            self._line().set_arg(0, '"a\nb"')

    def test_rejects_unquoted_space(self):
        with self.assertRaises(ValueError):
            self._line().set_arg(1, "2 11")

    def test_rejects_empty_token(self):
        with self.assertRaises(ValueError):
            self._line().set_arg(1, "")

    def test_allows_quoted_name_and_plain_tokens(self):
        ln = self._line()
        ln.set_arg(0, '"Lead Vox"')
        ln.set_arg(1, "2")
        self.assertEqual(ln.args[:2], ['"Lead Vox"', "2"])


class EditReparseTest(unittest.TestCase):
    """After an edit, the reparsed token structure must be unchanged except where
    intended — the property the round-trip test cannot supply."""

    def test_edits_preserve_token_structure(self):
        from x32scene import channelfx as F
        from x32scene import transforms as T
        path = os.path.join(FIXTURES, "example.scn")
        base, work = Scene.load(path), Scene.load(path)
        T.rename_channel(work, 1, "Kick In")
        T.retitle_scene(work, "Property Test")
        T.set_headamp(work, "local", 1, gain_db=30.0, phantom=True)
        F.set_eq_band(work, 9, 1, gain=6.0)
        F.set_comp(work, "/mtx/01", mix=50)
        reparsed = Scene.parse(work.dump())
        self.assertEqual([ln.path for ln in reparsed.lines],
                         [ln.path for ln in base.lines])
        for b, r in zip(base.lines, reparsed.lines, strict=True):
            self.assertEqual(len(r.args), len(b.args),
                             f"token count changed on {b.path}: {r.raw!r}")


class ParseGuardTest(unittest.TestCase):
    def test_crlf_rejected(self):
        with self.assertRaises(ValueError):
            Scene.parse(SCENE.replace("\n", "\r\n"))

    def test_empty_scene_name_is_empty(self):
        self.assertEqual(Scene.parse("").name, "")

    def test_headerless_chn_has_no_name(self):
        # a .chn may start straight at /preamp; its first token is not a title
        sc = Scene.parse("/preamp +0.0 OFF ON 24  30\n")
        self.assertEqual(sc.name, "")

    def test_older_firmware_header_keeps_padding_on_edit(self):
        from x32scene import transforms as T
        old = '#2.7# "Old Rig" "" %000000000 1'.ljust(HEADER_WIDTH)
        sc = Scene.parse(old + "\n/ch/01/config \"Kick\" 1 67 1\n")
        T.retitle_scene(sc, "Renamed")
        self.assertEqual(len(sc.lines[0].raw), HEADER_WIDTH)
        self.assertEqual(sc.name, "Renamed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
