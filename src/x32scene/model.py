"""Faithful X32 / M32 scene (.scn) and channel-preset (.chn) model.

One OSC-style parameter per line, ``/path tok tok ...``, after a padded header line.

``Scene.parse(text).dump() == text`` for every real file: lines are stored verbatim and
rebuilt only when a transform changes one, so the token view is never the source of
truth for an untouched line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from pf_core.utils.io import atomic_write_bytes



def write_file(path: str, data: bytes) -> None:
    """``atomic_write_bytes``, raising a failure's OSError against ``path`` rather than
    the temporary file it writes first."""
    try:
        atomic_write_bytes(path, data)
    except OSError as e:
        if e.errno is None:
            raise
        raise OSError(e.errno, e.strerror, path) from None


def read_file(path: str) -> str:
    """A console file's text, verbatim. Raises ValueError naming ``path`` when it is not
    UTF-8, rather than a codec error that names nothing."""
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path}: not a console text file (byte {e.start} is not UTF-8)"
                         ) from None


HEADER_WIDTH = 127
HEADER_RE = re.compile(r"^#\d+\.\d+#$")  # older firmware writes #2.7#, #3.1#


def _spans(s: str) -> list[tuple[int, int]]:
    """(start, end) of each token ``tokenize`` returns."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == " ":
            i += 1
            continue
        j = i + 1
        if s[i] == '"':
            while j < n and s[j] != '"':
                j += 1
            j = min(j + 1, n)
        else:
            while j < n and s[j] != " ":
                j += 1
        spans.append((i, j))
        i = j
    return spans


def tokenize(s: str) -> list[str]:
    """Split an X32 line into tokens, treating a double-quoted run as one token.

    Quotes are kept in the returned tokens so a value round-trips exactly.
    """
    return [s[a:b] for a, b in _spans(s)]


def check_token(tok: str) -> None:
    """Reject a value that would break the line's token structure on reparse.

    Round-trip cannot catch this: verbatim bytes still match while the token view shifts.
    """
    if "\n" in tok or "\r" in tok:
        raise ValueError(f"token contains a line break: {tok!r}")
    if tok.startswith('"'):
        if len(tok) < 2 or not tok.endswith('"') or '"' in tok[1:-1]:
            raise ValueError(f"malformed quoted token: {tok!r}")
    elif '"' in tok or " " in tok or not tok:
        raise ValueError(f"token must be quoted or contain no quotes/spaces: {tok!r}")


@dataclass
class Line:
    """One line: verbatim ``raw`` (no newline), leading ``path``, tokenized ``args``.

    Assigning ``args`` directly requires a ``rebuild()`` to refresh ``raw``; prefer
    ``set_arg``, which validates the token and rebuilds only on a real change.
    """

    raw: str
    path: str
    args: list[str]
    dirty: bool = False

    @classmethod
    def parse(cls, raw: str) -> "Line":
        toks = tokenize(raw)
        if not toks:
            return cls(raw=raw, path="", args=[])
        return cls(raw=raw, path=toks[0], args=toks[1:])

    def rebuild(self) -> None:
        """Regenerate ``raw`` from path + args. Header line is re-padded to width."""
        body = " ".join([self.path, *self.args]) if self.path else ""
        if HEADER_RE.match(self.path):
            body = body.ljust(HEADER_WIDTH)
        self.raw = body
        self.dirty = True

    def require(self, count: int) -> None:
        """Raise IndexError naming the line when it carries fewer than ``count`` values."""
        if len(self.args) < count:
            raise IndexError(f"{self.path} has {len(self.args)} value(s), too few for this edit")

    def set_arg(self, idx: int, value: str) -> None:
        check_token(value)
        self.require(idx + 1 if idx >= 0 else -idx)
        if self.args[idx] != value:
            self.args[idx] = value
            self.rebuild()

    def padded_fields(self) -> list[str]:
        """The values, each with the whitespace the desk wrote in front of it (none for a
        token glued to a quote); ``set_fields`` takes them back."""
        spans = _spans(self.raw)
        return [self.raw[prev:end] for (_, prev), (_, end) in pairwise(spans)]

    def set_fields(self, fields: list[str]) -> bool:
        """Rebuild from ``padded_fields``-shaped values, keeping what precedes the path and
        follows the last value. True when the line changed. Raises ValueError, leaving the
        line as it was, when the values no longer split into the same tokens."""
        spans = _spans(self.raw)
        raw = self.raw[:spans[0][1]] + "".join(fields) + self.raw[spans[-1][1]:]
        if raw == self.raw:
            return False
        args = Line.parse(raw).args
        if args != [f.lstrip(" ") for f in fields]:
            raise ValueError(f"{self.path}: the edited values would split differently: {raw!r}")
        self.raw, self.args, self.dirty = raw, args, True
        return True


def put_field(fields: list[str], i: int, tok: str) -> None:
    """Replace one of ``Line.padded_fields`` with ``tok``, keeping the padding in front."""
    check_token(tok)
    fields[i] = fields[i][:len(fields[i]) - len(fields[i].lstrip(" "))] + tok


class Scene:
    """An ordered list of :class:`Line` with a path index for fast lookup."""

    def __init__(self, lines: list[Line], trailing_newline: bool = True):
        self.lines = lines
        self.trailing_newline = trailing_newline
        self._index: dict[str, int] = {}
        self._reindex()

    def _reindex(self) -> None:
        self._index = {ln.path: i for i, ln in enumerate(self.lines) if ln.path}

    # ---- IO ---------------------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "Scene":
        if "\r" in text:
            raise ValueError("CR line endings found — X32 files are LF-only; "
                             "convert CRLF to LF before editing")
        trailing_newline = text.endswith("\n")
        body = text[:-1] if trailing_newline else text
        # An empty file splits to [''] which we must not treat as a line.
        raws = body.split("\n") if body != "" else []
        return cls([Line.parse(r) for r in raws], trailing_newline)

    @classmethod
    def load(cls, path: str) -> "Scene":
        return cls.parse(read_file(path))

    def dump(self) -> str:
        text = "\n".join(ln.raw for ln in self.lines)
        if self.trailing_newline:
            text += "\n"
        return text

    def save(self, path: str) -> None:
        # bytes, not text: a text-mode write translates "\n" to the platform newline, and
        # an X32 file is LF-only on every platform (parse() rejects CR).
        write_file(path, self.dump().encode("utf-8"))

    # ---- lookup -----------------------------------------------------------
    def get(self, path: str) -> Line | None:
        idx = self._index.get(path)
        return self.lines[idx] if idx is not None else None

    def find(self, prefix: str) -> list[Line]:
        """All lines whose path starts with ``prefix`` (e.g. ``/headamp/``)."""
        return [ln for ln in self.lines if ln.path.startswith(prefix)]

    @property
    def name(self) -> str:
        """Scene title from the header, or "" for a headerless file (a bare .chn)."""
        if not self.lines:
            return ""
        hdr = self.lines[0]
        if not HEADER_RE.match(hdr.path) or not hdr.args:
            return ""
        return hdr.args[0].strip('"')
