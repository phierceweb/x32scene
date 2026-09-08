"""Does a loaded file have the shape of the kind it claims to be?

``Scene.parse`` accepts any LF text on purpose, so the structural question is asked here,
above the model, where a command can report it without the parser refusing the file.

Each kind has its own shape, so the kind is decided first; an unrecognized one is only
checked for being empty.
"""

from __future__ import annotations

import os

from ..model import HEADER_RE, HEADER_WIDTH, Scene
from .preflight_config import Finding

# A whole console: 32 channels, 128 head amps (local + both AES50 links), 16 mix buses.
FULL_DESK = (32, 128, 16)

KINDS = ("scn", "snp", "chn", "efx", "rou", "shw")
_PADDED_HEADER = ("scn", "snp", "efx", "rou")   # .shw's header is the bare tag


def kind_of(path: str) -> str | None:
    """The file kind from the extension, or None when it is not one we know."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext if ext in KINDS else None


def strip_counts(scene: Scene) -> tuple[int, int, int]:
    """(channels, head amps, mix buses) actually present."""
    return (sum(1 for ln in scene.find("/ch/") if ln.path.endswith("/config")),
            len(scene.find("/headamp/")),
            sum(1 for ln in scene.find("/bus/") if ln.path.endswith("/config")))


def findings(scene: Scene, kind: str | None) -> list[Finding]:
    """Structural problems. Empty means the file looks like its kind.

    What a caller does about one is the caller's: ``audit`` exits 1, a single-file read
    warns. Never raises — a file too broken to describe is the case this reports.
    """
    if not scene.lines:
        return [Finding("FAIL", "file", "empty file — nothing was read")]
    if kind is None:
        return []

    out: list[Finding] = []
    header = scene.lines[0]
    has_header = bool(HEADER_RE.match(header.path))

    # a .chn from an export carries no header; every other kind must
    if not has_header and kind != "chn":
        out.append(Finding("FAIL", "header",
                           f"no firmware header — first line is {header.raw[:40]!r}"))
    if has_header and kind in _PADDED_HEADER and len(header.raw) != HEADER_WIDTH:
        out.append(Finding("FAIL", "header",
                           f"header width {len(header.raw)} != {HEADER_WIDTH}"))

    if kind == "scn":
        counts = strip_counts(scene)
        if counts != FULL_DESK:
            got = "/".join(str(c) for c in counts)
            want = "/".join(str(c) for c in FULL_DESK)
            out.append(Finding("FAIL", "strips",
                               f"ch/headamp/bus = {got}, not {want} — truncated, "
                               "or not a whole-console scene"))
    else:
        # A .efx body is `type`/`source`/`par` and a .shw's `show`/`cue/000` — not OSC
        # paths, so the question is whether there is a body, not what its lines are called.
        body = scene.lines[1:] if has_header else scene.lines
        if not any(ln.raw.strip() for ln in body):
            out.append(Finding("FAIL", "body", "header only — no parameter lines"))

    return out
