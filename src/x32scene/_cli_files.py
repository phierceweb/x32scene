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

from .model import CR_ENDINGS, Scene, read_file
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


def write_all(files: list[tuple[str, bytes]], replaceable: Collection[str] = ()) -> None:
    """Every file or none: each is written in full to a staging folder beside its target, so
    no rename crosses a volume, before any target is replaced; every name the filesystem
    refuses is named at once. Only a file in ``replaceable`` is replaced: anything else found
    at a target refuses the batch."""
    stages: dict[str, str] = {}   # target folder -> its staging folder
    try:
        for folder in dict.fromkeys(os.path.dirname(path) or "." for path, _ in files):
            try:
                stages[folder] = tempfile.mkdtemp(prefix=".x32scene-", dir=folder)
            except OSError as e:
                raise InvalidInputError(f"{folder}: {e.strerror or e}; nothing written") from None
        staged = [os.path.join(stages[os.path.dirname(path) or "."], os.path.basename(path))
                  for path, _ in files]
        refused = []
        for (path, data), new in zip(files, staged, strict=True):
            try:
                atomic_write_bytes(new, data)
            except OSError as e:
                shown = os.path.basename(path) if len(stages) == 1 else path
                refused.append(f"{shown} ({e.strerror or e})")
        if refused:
            where = f" in {next(iter(stages))}" if len(stages) == 1 else ""
            raise InvalidInputError(f"{len(refused)} file(s) could not be written{where}, "
                                    f"nothing written: {', '.join(refused)}")
        _replace_all([path for path, _ in files], staged, set(replaceable))
    except BaseException:
        for stage in stages.values():
            aside = os.path.join(stage, _ASIDE)
            if not (os.path.isdir(aside) and os.listdir(aside)):   # an original not put back
                shutil.rmtree(stage, ignore_errors=True)
        raise
    for stage in stages.values():
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
        write_all(files, checked)
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


def _replace_all(paths: list[str], staged: list[str], replaceable: set[str]) -> None:
    """Move each existing target aside, into its staging folder, before its new file lands,
    so a refused rename, or an interrupt, puts every original back and removes every new
    file."""
    for stage in dict.fromkeys(os.path.dirname(new) for new in staged):
        os.mkdir(os.path.join(stage, _ASIDE))
    moved: list[tuple[str, str]] = []
    placed: list[tuple[str, str]] = []
    for path, new in zip(paths, staged, strict=True):
        kept = os.path.join(os.path.dirname(new), _ASIDE, os.path.basename(new))
        try:
            if os.path.lexists(path):
                if path not in replaceable or (os.path.isdir(path) and not os.path.islink(path)):
                    raise OSError(errno.EEXIST, "appeared after the overwrite check")
                moved.append((path, kept))
                os.replace(path, kept)
            placed.append((path, new))
            os.replace(new, path)
        except OSError as e:
            lost = _roll_back(placed, moved)
            what = f"{path}: {e.strerror or e}"
            if lost:
                raise InvalidInputError(f"{what}; could not restore {', '.join(lost)}, "
                                        f"originals kept in {_kept_in(lost, moved)}") from None
            raise InvalidInputError(f"{what}; nothing written") from None
        except BaseException:
            lost = _roll_back(placed, moved)
            if lost:
                print(f"x32scene: could not restore {', '.join(lost)}, originals kept in "
                      f"{_kept_in(lost, moved)}", file=sys.stderr)
            raise


def _kept_in(lost: list[str], moved: list[tuple[str, str]]) -> str:
    return ", ".join(dict.fromkeys(os.path.dirname(kept) for path, kept in moved if path in lost))


def _roll_back(placed: list[tuple[str, str]], moved: list[tuple[str, str]]) -> list[str]:
    """Undo each rename that happened: recorded before it runs, so one interrupted
    part-way is judged by where its file is now."""
    for path, staged in placed:
        if not os.path.lexists(staged):
            with contextlib.suppress(OSError):
                os.remove(path)
    lost = []
    for path, kept in reversed(moved):
        if not os.path.lexists(kept):
            continue
        try:
            os.replace(kept, path)
        except OSError:
            lost.append(path)
    return lost


def _checked(path: str) -> tuple[str, Scene | None]:
    """A user-named file's text, warning on stderr when it lacks the shape of its kind, and
    the Scene the check parsed when it is the one a caller would (no CR in the text).

    A warning, never a refusal: reading a truncated scene to see what survived is a real
    job. stderr, so ``--json`` stays a clean pipe. CR is normalized for the check alone —
    Scene.parse refuses it, but `header` and `show` are diagnostics that still read one.
    """
    text = read_file(path)
    if path in _warned:
        return text, None
    _warned.add(path)
    lf = text.replace("\r\n", "\n").replace("\r", "\n")
    scene = Scene.parse(lf)
    for f in _validate.findings(scene, file_kind(path)):
        print(f"x32scene: warning: {path}: {f.area} — {f.message}", file=sys.stderr)
    return text, scene if lf == text else None


def read_checked(path: str) -> str:
    """A user-named file's text, warned on as ``_checked`` says."""
    return _checked(path)[0]


def read_listed(path: str) -> str:
    """read_checked for a file a command lists rather than stops on: a read or parse failure
    is warned on stderr, then raised for the caller to list."""
    try:
        text, scene = _checked(path)
        if scene is None:
            Scene.parse(text)
    except (OSError, ValueError) as e:
        print(f"x32scene: warning: {path}: {clean(e)}", file=sys.stderr)
        raise
    return text


def read_lf(path: str) -> str:
    """read_checked for a file an edit parses: CR line endings are refused, naming ``path``."""
    text = read_checked(path)
    if "\r" in text:
        raise ValueError(f"{path}: {CR_ENDINGS}")
    return text


def load_checked(path: str) -> Scene:
    """read_lf, parsed once."""
    text, scene = _checked(path)
    if "\r" in text:
        raise ValueError(f"{path}: {CR_ENDINGS}")
    return scene if scene is not None else Scene.parse(text)
