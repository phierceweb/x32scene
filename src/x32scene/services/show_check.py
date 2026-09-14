"""Does a show hold together: every cue's scene and snippet slot is in the index, and every
slot's ``<show>.NNN.scn`` / ``.snp`` companion is there, has its kind's shape and, for a
snippet, the header its ``snippet/NNN`` line copies."""

from __future__ import annotations

from collections.abc import Callable

from ..model import Line, Scene
from . import validate
from .headers import decode_header
from .preflight_config import Finding
from .show import Show, ShowEntry

_EXT = {"scene": "scn", "snippet": "snp"}


def companion(stem: str, entry: ShowEntry) -> str:
    """The file a scene or snippet slot lives in, named after the show file's stem."""
    return f"{stem}.{entry.index:03d}.{_EXT[entry.kind]}"


def check_cues(show: Show) -> list[Finding]:
    """A FAIL for each cue that is not a whole cue line or names a slot the index lacks."""
    slots = {kind: {e.index for e in show.of(kind)} for kind in _EXT}
    out: list[Finding] = []
    for cue in show.of("cue"):
        line = f"cue/{cue.index:03d}"
        if not cue.decoded:
            out.append(Finding("FAIL", "cue", "not a cue line: needs number, name, skip, "
                                              "and a scene and snippet number", line))
            continue
        for kind in _EXT:
            slot = cue.decoded[kind]
            if slot is not None and slot not in slots[kind]:
                out.append(Finding("FAIL", "cue",
                                   f"cue {cue.decoded['number']} {cue.name!r}: {kind} {slot} "
                                   f"has no {kind}/{slot:03d} line in the show", line))
    return out


def check_show(show: Show, stem: str, read: Callable[[str], str]) -> list[Finding]:
    """A FAIL when the file has no ``show`` line, then ``check_cues`` plus every slot's
    companion. ``read(name)`` returns a companion's text and raises FileNotFoundError when it
    is absent."""
    out = [] if show.has_show_line else [
        Finding("FAIL", "show", "no show line: not a .shw index (an empty or header-only file, "
                                "or another kind of file)", "show")]
    out += check_cues(show)
    for entry in show.of("scene") + show.of("snippet"):
        name = companion(stem, entry)
        line = f"{entry.kind}/{entry.index:03d}"
        try:
            text = read(name)
        except FileNotFoundError:
            out.append(Finding("FAIL", "companion", f"{name} is missing", line))
            continue
        except (OSError, ValueError) as e:
            out.append(Finding("FAIL", "companion", f"{name}: {e}", line))
            continue
        out += _companion(entry, name, text, line)
    return out


def _companion(entry: ShowEntry, name: str, text: str, line: str) -> list[Finding]:
    try:
        scene = Scene.parse(text)
    except ValueError as e:
        return [Finding("FAIL", "companion", f"{name}: {e}", line)]
    out = [Finding("FAIL", "shape", f"{name}: {f.area} — {f.message}", line)
           for f in validate.findings(scene, _EXT[entry.kind])]
    header = decode_header(text)
    if header is None:
        return out
    if header["kind"] != entry.kind:
        out.append(Finding("FAIL", "header",
                           f"{name}: header reads as a {header['kind']}, not a {entry.kind}",
                           line))
    elif entry.kind == "snippet":
        fields = Line.parse(text.split("\n", 1)[0]).args
        if fields != entry.args:
            out.append(Finding("FAIL", "header",
                               f"{name}: header {' '.join(fields)} does not match "
                               f"{line} {' '.join(entry.args)}", line))
    return out


def counts(show: Show) -> dict[str, int]:
    return {"cues": len(show.of("cue")), "scenes": len(show.of("scene")),
            "snippets": len(show.of("snippet"))}


def report(show: Show, findings: list[Finding]) -> str:
    c = counts(show)
    tally = f"{c['cues']} cue(s), {c['scenes']} scene(s), {c['snippets']} snippet(s)"
    if not findings:
        return f"SHOW OK — {tally}"
    lines = [f"  {f.severity}  {f.path:11s} {f.message}" for f in findings]
    return "\n".join(lines + [f"\n{len(findings)} FAIL — {tally}"])
