"""Presentation for a preset folder: `presets-diff` and `extract-preset --all`."""

from __future__ import annotations

from .services import preset_library as _lib


def _tokens(args: list[str] | None) -> str:
    return "(absent)" if args is None else " ".join(args)


def _where(r: _lib.PresetCheck) -> str:
    chans = ", ".join(f"ch{ch:02d}" for ch in r.channels)
    if r.status == _lib.UNREADABLE:
        return r.reason
    if r.status == _lib.NO_CHANNEL:
        return f"no channel named {r.name!r}"
    if r.status == _lib.AMBIGUOUS:
        return f"{r.name!r} names {chans}"
    return f"{chans} {r.name}" + ("" if r.compared else "  (nothing in scope to compare)")


def cmd_presets_diff(results: list[_lib.PresetCheck]) -> None:
    for r in results:
        label = r.status
        if r.status == _lib.DRIFT:
            label += f" ({len(r.drift)} path{'' if len(r.drift) == 1 else 's'})"
        print(f"{label:<16} {r.file}  {_where(r)}")
        for d in r.drift:
            print(f"    {d.path}  {_tokens(d.preset)} -> {_tokens(d.scene)}")
        for path in r.uncompared:
            print(f"    {path}  not compared: the channel's source has no head amp")
    counts = {s: sum(r.status == s for r in results) for s in _lib.STATUSES}
    print(", ".join(f"{n} {s}" for s, n in counts.items()))


def shared_name(s: _lib.SharedName) -> str:
    return f"{s.file}: " + ", ".join(f"ch{ch:02d}" for ch in s.channels)


def cmd_extract_library(presets: list[_lib.LibraryPreset], skipped: list[int],
                        shared: list[_lib.SharedName], paths: list[str]) -> None:
    for p, path in zip(presets, paths, strict=True):
        print(f"ch{p.ch:02d}  {p.name:<16} -> {path}")
    if skipped:
        print("skipped, no scribble name: " + ", ".join(f"ch{ch:02d}" for ch in skipped))
    for s in shared:
        print(f"skipped, share {shared_name(s)}")
    print(f"wrote {len(presets)} preset(s)\nLOAD-TEST on the console before a gig.")
