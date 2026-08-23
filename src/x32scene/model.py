"""Faithful X32 / M32 scene (.scn) and channel-preset (.chn) model.

One OSC-style parameter per line, ``/path tok tok ...``, after a padded header line.

``Scene.parse(text).dump() == text`` for every real file: lines are stored verbatim and
rebuilt only when a transform changes one, so the token view is never the source of
truth for an untouched line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pf_core.utils.io import atomic_write_bytes

HEADER_WIDTH = 127
HEADER_RE = re.compile(r"^#\d+\.\d+#$")  # older firmware writes #2.7#, #3.1#


def tokenize(s: str) -> list[str]:
    """Split an X32 line into tokens, treating a double-quoted run as one token.

    Quotes are kept in the returned tokens so a value round-trips exactly.
    """
    tokens: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == " ":
            i += 1
            continue
        if s[i] == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 1
            tokens.append(s[i : j + 1])
            i = j + 1
        else:
            j = i
            while j < n and s[j] != " ":
                j += 1
            tokens.append(s[i:j])
            i = j
    return tokens


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

    def set_arg(self, idx: int, value: str) -> None:
        check_token(value)
        if self.args[idx] != value:
            self.args[idx] = value
            self.rebuild()


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
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return cls.parse(fh.read())

    def dump(self) -> str:
        text = "\n".join(ln.raw for ln in self.lines)
        if self.trailing_newline:
            text += "\n"
        return text

    def save(self, path: str) -> None:
        # bytes, not text: a text-mode write translates "\n" to the platform newline, and
        # an X32 file is LF-only on every platform (parse() rejects CR).
        atomic_write_bytes(path, self.dump().encode("utf-8"))

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
