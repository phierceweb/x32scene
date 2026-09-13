"""The CLI's file boundary: which files an edit may land on, and reading one with a word
about its shape. Presentation — the only place outside cli.py that writes to stderr."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

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


def refuse_overwrite(out: str, *inputs: str, force: bool = False, flag: str = "-o") -> None:
    """Edit commands never destroy a file that is already there.

    An input is refused outright and ``--force`` does not unlock it; any other existing
    OUT needs ``--force``. samefile catches aliases realpath misses (case variants on
    macOS/Windows, hardlinks); the realpath comparison covers an OUT not yet created.
    realpath, not Path.resolve(): that raises RuntimeError on a symlink loop.
    """
    for p in inputs:
        try:
            same = os.path.exists(out) and os.path.samefile(out, p)
        except OSError:
            same = False
        if same or os.path.realpath(out) == os.path.realpath(p):
            raise InvalidInputError(
                f"{flag} {out} would overwrite the input {p}; write a new file instead")
    if not force and _taken(out):
        raise InvalidInputError(f"{out} already exists; pass --force to overwrite it")


def refuse_unwritable(out: str, flag: str) -> None:
    """For a file written only after a long run: refuse up front a name that cannot be
    written, so the run is not lost to it at the end."""
    parent = os.path.dirname(out) or "."
    if not out:
        raise InvalidInputError(f"{flag} needs a file name")
    if os.path.isdir(out):
        raise InvalidInputError(f"{flag} {out} is a directory")
    if not os.path.isdir(parent):
        raise InvalidInputError(f"{flag} {out}: no directory {parent}")
    if not os.access(parent, os.W_OK | os.X_OK):
        raise InvalidInputError(f"{flag} {out}: {parent} is not writable")


def refuse_not_directory(out: str, flag: str) -> None:
    """For a directory created if missing: refuse a name taken by something else, or whose
    nearest existing ancestor on the resolved path (a `..` read as the kernel reads it) is
    not a writable directory."""
    if not out:
        raise InvalidInputError(f"{flag} needs a directory name")
    real = os.path.realpath(out)
    if any(os.path.lexists(p) and not os.path.isdir(p) for p in (out, real)):
        raise InvalidInputError(f"{flag} {out} is not a directory")
    parent = real
    while not os.path.lexists(parent):
        parent = os.path.dirname(parent)
    shown = parent if os.path.isabs(out) else os.path.relpath(parent)
    where = f"{flag} {out}" if parent == real else f"{flag} {out}: {shown}"
    if not os.path.isdir(parent):
        raise InvalidInputError(f"{where} is not a directory")
    if not os.access(parent, os.W_OK | os.X_OK):
        raise InvalidInputError(f"{where} is not writable")


def refuse_overwrite_all(outs: list[str], *inputs: str, force: bool = False) -> None:
    """``refuse_overwrite`` for a batch that writes all or nothing: every existing OUT is
    named at once, before any file is written. A directory is never replaced."""
    for out in outs:
        refuse_overwrite(out, *inputs, force=True)
    dirs = [out for out in outs if os.path.isdir(out) and not os.path.islink(out)]
    if dirs:
        raise InvalidInputError(f"{len(dirs)} target(s) are directories, nothing written: "
                                + ", ".join(dirs))
    taken = [out for out in outs if _taken(out)]
    if taken and not force:
        parents = {os.path.dirname(out) for out in taken}
        where = f" in {parents.pop()}" if len(parents) == 1 else ""
        names = [os.path.basename(out) for out in taken] if where else taken
        raise InvalidInputError(f"{len(taken)} file(s) already exist{where}, nothing written; "
                                f"pass --force to overwrite: {', '.join(names)}")


def write_all(files: list[tuple[str, bytes]], directory: str) -> None:
    """Every file or none: each is written in full to a staging folder inside ``directory``
    before any target is replaced; every name the filesystem refuses is named at once."""
    try:
        stage = tempfile.mkdtemp(prefix=".x32scene-", dir=directory)
    except OSError as e:
        raise InvalidInputError(f"{directory}: {e.strerror or e}; nothing written") from None
    try:
        refused = []
        for path, data in files:
            try:
                atomic_write_bytes(os.path.join(stage, os.path.basename(path)), data)
            except OSError as e:
                refused.append(f"{os.path.basename(path)} ({e.strerror or e})")
        if refused:
            raise InvalidInputError(f"{len(refused)} file(s) could not be written in "
                                    f"{directory}, nothing written: {', '.join(refused)}")
        for path, _ in files:
            os.replace(os.path.join(stage, os.path.basename(path)), path)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


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


def read_listed(path: str) -> str:
    """read_checked for a file a command lists rather than stops on: a read or parse failure
    is warned on stderr, then raised for the caller to list."""
    try:
        text = read_checked(path)
        Scene.parse(text)
    except (OSError, ValueError) as e:
        print(f"x32scene: warning: {path}: {clean(e)}", file=sys.stderr)
        raise
    return text


def load_checked(path: str) -> Scene:
    """read_checked, parsed. Raises on CR, as every scene reader does."""
    return Scene.parse(read_checked(path))
