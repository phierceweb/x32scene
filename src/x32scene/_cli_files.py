"""The CLI's file boundary: which files an edit may land on, and reading one with a word
about its shape. Presentation — the only place outside cli.py that writes to stderr."""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import sys
import tempfile
from collections.abc import Collection

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

from .model import Scene, read_file
from .services import validate as _validate

_warned: set[str] = set()   # one shape warning per file per run, however often it loads
_this_run: dict[str, str | None] = {"kind": None}


def start_run(kind: str | None = None) -> None:
    """Start a run with its ``--kind``: without it the dedup outlives one invocation and a
    long-lived process falls silent after a file's first read."""
    _warned.clear()
    _this_run["kind"] = kind


def file_kind(path: str) -> str | None:
    """A named file's kind: its extension's, else the run's ``--kind`` for a name that has none."""
    return _validate.kind_of(path) or _this_run["kind"]


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


def write_all(files: list[tuple[str, bytes]], directory: str,
              replaceable: Collection[str] = ()) -> None:
    """Every file or none: each is written in full to a staging folder inside ``directory``
    before any target is replaced; every name the filesystem refuses is named at once. Only a
    file in ``replaceable`` is replaced: anything else found at a target refuses the batch."""
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
        _replace_all([path for path, _ in files], stage, set(replaceable))
    except BaseException:
        aside = os.path.join(stage, _ASIDE)
        if not (os.path.isdir(aside) and os.listdir(aside)):   # an original not put back
            shutil.rmtree(stage, ignore_errors=True)
        raise
    shutil.rmtree(stage, ignore_errors=True)


def write_into(directory: str, files: list[tuple[str, bytes]], *inputs: str,
               force: bool = False) -> None:
    """``refuse_overwrite_all`` then ``write_all`` into ``directory``, created if missing and
    removed again when nothing is written."""
    refuse_overwrite_all([path for path, _ in files], *inputs, force=force)
    checked = {path for path, _ in files if os.path.lexists(path)}
    made = _missing(directory)
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as e:
        raise InvalidInputError(f"-o {directory}: {e.strerror or e}") from None
    try:
        write_all(files, directory, checked)
    except InvalidInputError:
        for d in made:
            with contextlib.suppress(OSError):
                os.rmdir(d)
        raise


def _missing(directory: str) -> list[str]:
    """The folders ``makedirs(directory)`` would create, deepest first."""
    made, d = [], os.path.abspath(directory)
    while not os.path.lexists(d):
        made.append(d)
        d = os.path.dirname(d)
    return made


_ASIDE = "replaced"


def _replace_all(paths: list[str], stage: str, replaceable: set[str]) -> None:
    """Move each existing target aside into ``stage`` before its new file lands, so a
    refused rename puts every original back and removes every new file."""
    aside = os.path.join(stage, _ASIDE)
    os.mkdir(aside)
    moved: list[tuple[str, str]] = []
    placed: list[str] = []
    for path in paths:
        name = os.path.basename(path)
        try:
            if os.path.lexists(path):
                if path not in replaceable or (os.path.isdir(path) and not os.path.islink(path)):
                    raise OSError(errno.EEXIST, "appeared after the overwrite check")
                os.replace(path, os.path.join(aside, name))
                moved.append((path, os.path.join(aside, name)))
            os.replace(os.path.join(stage, name), path)
            placed.append(path)
        except OSError as e:
            lost = _roll_back(placed, moved)
            what = f"{path}: {e.strerror or e}"
            if lost:
                raise InvalidInputError(f"{what}; could not restore {', '.join(lost)}, "
                                        f"originals kept in {aside}") from None
            raise InvalidInputError(f"{what}; nothing written") from None


def _roll_back(placed: list[str], moved: list[tuple[str, str]]) -> list[str]:
    for path in placed:
        with contextlib.suppress(OSError):
            os.remove(path)
    lost = []
    for path, kept in reversed(moved):
        try:
            os.replace(kept, path)
        except OSError:
            lost.append(path)
    return lost


def read_checked(path: str) -> str:
    """A user-named file's text, warning on stderr when it lacks the shape of its kind.

    A warning, never a refusal: reading a truncated scene to see what survived is a real
    job. stderr, so ``--json`` stays a clean pipe. CR is normalized for the check alone —
    Scene.parse refuses it, but `header` and `show` are diagnostics that still read one.
    """
    text = read_file(path)
    if path not in _warned:
        _warned.add(path)
        lf = text.replace("\r\n", "\n").replace("\r", "\n")
        for f in _validate.findings(Scene.parse(lf), file_kind(path)):
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
