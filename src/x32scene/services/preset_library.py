"""A folder of channel presets (`.chn`) against a scene: which ones still match the channel
they are named for, and the folder regenerated from the scene.

A preset is matched to a channel by name and never by guess, and compared by tokens only
over the paths it carries — what an ``apply_preset`` of it would touch.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from ..model import HEADER_RE, Scene, read_file
from . import validate
from .presets import extract_preset, mirrored_sends, preset_selects, unflagged_scopes
from .routing import channel_headamp_index
from .snippets import MIX_FIELD

MATCH, DRIFT, NOTHING_COMPARED, NO_CHANNEL, AMBIGUOUS, UNREADABLE = (
    "MATCH", "DRIFT", "NOTHING COMPARED", "NO CHANNEL", "AMBIGUOUS", "UNREADABLE")
STATUSES = (MATCH, DRIFT, NOTHING_COMPARED, NO_CHANNEL, AMBIGUOUS, UNREADABLE)

_ILLEGAL = re.compile(r'[/\\:*?"<>|]')
_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]) *(?:\.|$)",
                     re.IGNORECASE)


@dataclass
class Drift:
    """One path whose preset tokens differ from the scene's; ``scene`` None when absent."""

    path: str
    preset: list[str]
    scene: list[str] | None


@dataclass
class PresetCheck:
    """One preset file's verdict. ``channels`` holds the match, or every candidate when
    AMBIGUOUS; ``uncompared`` the paths that had nothing to compare against; ``skipped``
    the scopes the header leaves out (:func:`~.presets.unflagged_scopes`)."""

    file: str
    status: str
    name: str = ""
    channels: list[int] = field(default_factory=list)
    compared: int = 0
    drift: list[Drift] = field(default_factory=list)
    uncompared: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class LibraryPreset:
    ch: int
    name: str
    file: str
    text: str


@dataclass
class SharedName:
    """Channels whose presets land on one file name; ``file`` is the first channel's."""

    file: str
    channels: list[int]


def _norm(name: str) -> str:
    return name.strip().strip('"').strip().casefold()


def channel_name(scene: Scene, ch: int) -> str:
    """A channel's scribble name without quotes or surrounding space; "" when it has none."""
    cfg = scene.get(f"/ch/{ch:02d}/config")
    return cfg.args[0].strip('"').strip() if cfg and cfg.args else ""


def match_channels(scene: Scene, name: str, *, stem: bool = False) -> list[int]:
    """Every channel 1-32 whose scribble name is ``name``, ignoring case, quotes and
    surrounding space. An empty name matches nothing. With ``stem``, ``name`` is a file
    stem, and also matches a channel whose ``preset_filename`` has that stem."""
    want = _norm(name)

    def names(ch: int) -> set[str]:
        have = channel_name(scene, ch)
        return {_norm(have), _norm(_stem(have))} if stem else {_norm(have)}

    return [ch for ch in range(1, 33) if want and want in names(ch)]


def _scene_tokens(scene: Scene, ch: int, path: str) -> list[str] | None:
    """The scene's tokens for a preset path on channel ``ch``; a desk-written preset splits
    the main mix one sub-path per field (``/mix/fader``), the scene keeps one ``/mix`` line."""
    head, _, sub = path.rpartition("/")
    if head == "/mix" and sub in MIX_FIELD:
        mix, i = scene.get(f"/ch/{ch:02d}/mix"), MIX_FIELD[sub]
        return [mix.args[i]] if mix and len(mix.args) > i else None
    target = scene.get(f"/ch/{ch:02d}{path}")
    return None if target is None else list(target.args)


def _tally(res: PresetCheck, path: str, want: list[str], have: list[str] | None) -> None:
    res.compared += 1
    if want != have:
        res.drift.append(Drift(path, want, have))


def _compare(scene: Scene, ch: int, preset: Scene, selects: Callable[[str], bool],
             mirrors: list[tuple[str, str]]) -> PresetCheck:
    """``mirrors`` is :func:`~.presets.mirrored_sends`: those sends are compared on the on
    and level an apply gives them, a partner bus the preset has no line for included; the
    partner channel's sends are not compared."""
    res = PresetCheck("", MATCH)
    own = f"/ch/{ch:02d}"
    took = {path[len(own):]: src for path, src in mirrors if path.startswith(own + "/")}
    by_path = {ln.path: ln for ln in preset.lines}
    for ln in preset.lines:
        if not ln.path or HEADER_RE.match(ln.path) or not selects(ln.path):
            continue
        path, want = ln.path, list(ln.args)
        if path in took:
            want[:2] = by_path[took.pop(path)].args[:2]
        if path.startswith("/headamp"):
            idx = channel_headamp_index(scene, ch)
            if idx is None:
                res.uncompared.append(path)
                continue
            path = f"/headamp/{idx:03d}"
            target = scene.get(path)
            have = None if target is None else list(target.args)
        else:
            have = _scene_tokens(scene, ch, path)
        if path == "/config" and have and len(want) in (len(have), len(have) - 1):
            # the source slot is never compared: apply_preset keeps the target's, and the
            # desk leaves it out of a preset it writes
            want, have = want[:len(have) - 1], have[:-1]
        elif (have and 2 <= len(want) < len(have) and path.startswith("/mix/")
              and path[len("/mix/"):].isdigit()):
            have = have[:len(want)]   # a send line short of its bus's fields leaves the rest
        _tally(res, path, want, have)
    for path, src in took.items():
        want = list(by_path[src].args[:2])
        _tally(res, path, want, _scene_tokens(scene, ch, path)[:len(want)])
    res.status = DRIFT if res.drift else MATCH if res.compared else NOTHING_COMPARED
    return res


def check_preset(scene: Scene, file: str, text: str,
                 scopes: list[str] | None = None) -> PresetCheck:
    """Match one preset's text to a channel of ``scene`` and compare it there.

    The name is the preset's own ``/config`` scribble, or the ``file`` stem when that is
    missing or empty. Without ``scopes``, a header's section flags choose what is compared,
    as they choose what an apply writes, a send on a stereo-linked bus pair included; a
    preset with nothing to compare is NOTHING_COMPARED. Never raises for a malformed preset:
    it comes back UNREADABLE. A scene with no ``/config/buslink`` compares each send on its
    own bus.
    """
    try:
        preset = Scene.parse(text)
    except ValueError as e:
        return PresetCheck(file, UNREADABLE, reason=str(e))
    problems = validate.findings(preset, "chn")
    if problems:
        return PresetCheck(file, UNREADABLE, reason="; ".join(f.message for f in problems))
    cfg = preset.get("/config")
    name = cfg.args[0].strip('"').strip() if cfg and cfg.args else ""
    from_file = not name
    name = name or os.path.splitext(os.path.basename(file))[0].strip()
    channels = match_channels(scene, name, stem=from_file)
    if len(channels) != 1:
        return PresetCheck(file, AMBIGUOUS if channels else NO_CHANNEL, name, channels)
    linked = scene.get("/config/buslink") is not None
    res = _compare(scene, channels[0], preset, preset_selects(text, scopes),
                   mirrored_sends(scene, channels[0], text, scopes) if linked else [])
    res.file, res.name, res.channels = file, name, channels
    res.skipped = unflagged_scopes(text, scopes)
    return res


def check_library(scene: Scene, directory: str, scopes: list[str] | None = None, *,
                  read: Callable[[str], str] = read_file) -> list[PresetCheck]:
    """``check_preset`` for every ``.chn`` regular file directly in ``directory``, by file
    name. A ``._`` AppleDouble sidecar is skipped, and so is a FIFO, which would block a read.

    ``read`` fetches a file's text; one that raises OSError or ValueError is UNREADABLE.
    Raises OSError when ``directory`` itself cannot be listed.
    """
    out = []
    for file in sorted(os.listdir(directory), key=str.casefold):
        path = os.path.join(directory, file)
        if (validate.kind_of(file) != "chn" or file.startswith("._")
                or not os.path.isfile(path)):
            continue
        try:
            text = read(path)
        except (OSError, ValueError) as e:
            out.append(PresetCheck(file, UNREADABLE, reason=str(e)))
            continue
        out.append(check_preset(scene, file, text, scopes))
    return out


def _stem(name: str) -> str:
    stem = re.sub(r"^\.", "_", _ILLEGAL.sub("_", name.strip()))
    return "_" + stem if _DEVICE.match(stem) else stem


def preset_filename(name: str) -> str:
    """The file a preset named ``name`` is written as: characters macOS or Windows refuse
    in a file name become ``_``, and so does a leading ``.``, which would hide the file. A
    Windows device name (``AUX``, ``CON.x``, ``nul .``, ``CONIN$``, ``COM¹``) gains a leading ``_``."""
    return _stem(name) + ".chn"


def extract_library(scene: Scene, scopes: list[str] | None = None, *, header: bool = False
                    ) -> tuple[list[LibraryPreset], list[int], list[SharedName]]:
    """One preset per channel with a scribble name, the channels skipped for having none, and
    the channels skipped for landing on one file name with another.

    File names are compared without case or Unicode normalization, as a macOS volume does;
    every channel on a shared name is skipped, so none of them wins by channel order.
    """
    skipped, by_key = [], {}
    for ch in range(1, 33):
        name = channel_name(scene, ch)
        if not name:
            skipped.append(ch)
            continue
        file = preset_filename(name)
        key = unicodedata.normalize("NFC", file.casefold())
        by_key.setdefault(key, []).append((ch, name, file))
    presets, shared = [], []
    for group in by_key.values():
        if len(group) > 1:
            shared.append(SharedName(group[0][2], [ch for ch, _, _ in group]))
            continue
        ch, name, file = group[0]
        presets.append(LibraryPreset(ch, name, file, extract_preset(scene, ch, scopes,
                                                                    header=header)))
    return presets, skipped, shared
