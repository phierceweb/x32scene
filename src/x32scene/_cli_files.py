"""The CLI's file boundary: which files an edit may land on, and reading one with a word
about its shape. Presentation — the only place outside cli.py that writes to stderr."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pf_core.exceptions import InvalidInputError

from .model import Scene
from .services import validate as _validate

_warned: set[str] = set()   # one shape warning per file per run, however often it loads


def reset_warnings() -> None:
    """Start a run: without it the dedup outlives one invocation and a long-lived process
    falls silent after a file's first read."""
    _warned.clear()


def clean(e: Exception) -> str:
    """KeyError stringifies to its repr, which shows the message in stray quotes."""
    return e.args[0] if isinstance(e, KeyError) and e.args else str(e)


def _taken(path: str) -> bool:
    """Is a name already in use? lexists, so a dangling symlink counts; and the parent is
    resolved first, so a `..` through a directory that does not exist yet cannot step
    around the check into one that does."""
    if os.path.lexists(path):
        return True
    parent = os.path.realpath(os.path.dirname(path) or ".")
    return os.path.lexists(os.path.join(parent, os.path.basename(path)))


def refuse_overwrite(out: str, *inputs: str, force: bool = False) -> None:
    """Edit commands never destroy a file that is already there.

    An input is refused outright and ``--force`` does not unlock it; any other existing
    OUT needs ``--force``. samefile catches aliases Path.resolve() misses (case variants
    on macOS/Windows, hardlinks); the resolve comparison covers an OUT not yet created.
    """
    for p in inputs:
        try:
            same = os.path.exists(out) and os.path.samefile(out, p)
        except OSError:
            same = False
        if same or Path(out).resolve() == Path(p).resolve():
            raise InvalidInputError(
                f"-o {out} would overwrite the input {p}; write a new file instead")
    if not force and _taken(out):
        raise InvalidInputError(f"{out} already exists; pass --force to overwrite it")


def read_checked(path: str) -> str:
    """A user-named file's text, warning on stderr when it lacks the shape of its kind.

    A warning, never a refusal: reading a truncated scene to see what survived is a real
    job. stderr, so ``--json`` stays a clean pipe. CR is normalized for the check alone —
    Scene.parse refuses it, but `header` and `show` are diagnostics that still read one.
    """
    with open(path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    if path not in _warned:
        _warned.add(path)
        lf = text.replace("\r\n", "\n").replace("\r", "\n")
        for f in _validate.findings(Scene.parse(lf), _validate.kind_of(path)):
            print(f"x32scene: warning: {path}: {f.area} — {f.message}", file=sys.stderr)
    return text


def load_checked(path: str) -> Scene:
    """read_checked, parsed. Raises on CR, as every scene reader does."""
    return Scene.parse(read_checked(path))
