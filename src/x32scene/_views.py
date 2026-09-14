"""Read-only display commands for the x32 CLI — render a scene to the console.

Pure presentation: each function takes a parsed Scene and prints. No file writes (those
live in cli.py). Kept separate from CLI wiring so cli.py stays parsers + dispatch.
"""

from __future__ import annotations

import sys

from ._views_ports import cmd_ports
from .services import buses as _buses
from .services import fx as _fx
from .services import groups as _groups
from .services import routing as _routing
from .services.describe import describe, describe_all
from .services.diff import Change, diff
from .services.history import history
from .services.show import Show
from .services.snippets import Snippet
from .services.stagebox import InputMove
from .model import Scene
from .tables import SEND_STRIPS, decode_source
from .tables_fx import decode_fx

__all__ = ["cmd_ports"]


def cmd_info(scene: Scene) -> None:
    print(f"title: {scene.name!r}   lines: {len(scene.lines)}")
    print("channels:")
    for n, nm in sorted(_buses.channel_names(scene).items()):
        print(f"  ch{n:02d}  {nm}")
    print("buses:")
    for n, nm in sorted(_buses.bus_names(scene).items()):
        print(f"  bus{n:02d}  {nm}")


def cmd_buses(scene: Scene) -> None:
    """Show the 16 mix buses: stereo-link pairs, names, FX assignment, and send-tap mix."""
    for r in _buses.bus_rows(scene):
        role = "" if r.fx_slot is None else f"-> FX{r.fx_slot} ({decode_fx(r.fx_type)})"
        pair = ("stereo-pair" if r.linked else "mono") if r.bus % 2 else ""
        tapmix = " ".join(f"{k}:{v}" for k, v in r.taps.items() if v)
        print(f"  bus{r.bus:02d} {r.name:<11} {pair:<11} {role:<18} sends[{tapmix}]")


def cmd_inputs(scene: Scene) -> None:
    """Each channel -> resolved physical source (through UIN/userrout indirection)."""
    for cs in _routing.channel_sources(scene):
        flag = "  <- USB/DAW" if "Card" in cs.source else ""
        print(f"  ch{cs.ch:02d} {cs.name:<14} slot {cs.slot:>2} -> {cs.source}{flag}")


def cmd_record_map(scene: Scene) -> None:
    """The 32 USB record tracks the DAW receives, in order."""
    print("USB record tracks (X32 -> DAW):")
    for n, src in _routing.record_map(scene):
        if src not in ("OFF", "?"):
            print(f"  track {n:>2} <- {src}")
    loop = _routing.card_sourced_channels(scene)
    if loop:
        print("\nChannels sourced FROM the card (DAW return / loopback / reamp):")
        for cs in loop:
            print(f"  ch{cs.ch:02d} {cs.name:<14} <- {cs.source}")


_GEQ_ROW = 8  # band=value pairs per wrapped line for GEQ/GEQ2 (31-64 bands, else 1 line)


def cmd_fx(scene: Scene) -> None:
    for f in _fx.read_fx(scene):
        src = f" <- {f.source}" if f.source else ""
        note = "" if f.verified or not f.params else "  (layout from protocol doc, unverified)"
        print(f"  FX{f.slot} {f.name} ({f.code}){src}{note}")
        if not f.params:
            continue
        pairs = [f"{k}={v}" for k, v in f.params.items()]
        if f.code in ("GEQ", "GEQ2"):
            for i in range(0, len(pairs), _GEQ_ROW):
                print("       " + "  ".join(pairs[i:i + _GEQ_ROW]))
        else:
            print("       " + "  ".join(pairs))


def _strip_label(scene: Scene, path: str) -> str:
    """A strip's scribble name, falling back to its path when unnamed."""
    cfg = scene.get(f"{path}/config")
    name = cfg.args[0].strip('"') if cfg and cfg.args else ""
    return name or path


def cmd_dca(scene: Scene) -> None:
    dca_names = _groups.dca_names(scene)
    print("DCA groups:")
    for d, strips in _groups.dca_members(scene).items():
        if strips:
            label = dca_names.get(d, "")
            members = ", ".join(_strip_label(scene, p) for p in strips)
            print(f"  DCA {d} {label:<10} [{members}]")
    print("Mute groups:")
    for m, strips in _groups.mute_members(scene).items():
        if strips:
            members = ", ".join(_strip_label(scene, p) for p in strips)
            print(f"  MG {m}  [{members}]")


def iem_rows(scene: Scene, bus: int) -> list[tuple[float, str, str, list[str]]]:
    """One bus's monitor mix rows, loud -> quiet: (level_db, strip path, label, raw args)."""
    rows = []
    for strip in SEND_STRIPS:
        ln = scene.get(f"{strip}/mix/{bus:02d}")
        if ln is None or len(ln.args) < 2:
            continue
        on, level = ln.args[0], ln.args[1]
        if on == "OFF" or level == "-oo":
            continue
        rows.append((float(level), strip, _strip_label(scene, strip), ln.args))
    rows.sort(key=lambda r: -r[0])
    return rows


def cmd_iem(scene: Scene, bus: int) -> None:
    """One bus's monitor mix, loud -> quiet. Aux-ins and FX returns feed ears too."""
    print(f"bus {bus:02d} mix (loud -> quiet):")
    for level, strip, nm, args in iem_rows(scene, bus):
        print(f"  {level:+6.1f}dB  {strip:<10} {nm:<12} {' '.join(args)}")


def cmd_explain(scene: Scene) -> None:
    """One-shot full-scene readout for troubleshooting."""
    print(f"=== {scene.name!r} ===\n")
    print("# INPUTS (channel -> physical source)")
    cmd_inputs(scene)
    print("\n# BUSES")
    cmd_buses(scene)
    print("\n# OUTPUTS")
    cmd_ports(scene, bank="all")
    print("\n# RECORD MAP")
    cmd_record_map(scene)
    print("\n# FX")
    cmd_fx(scene)
    print("\n# GROUPS")
    cmd_dca(scene)


def cmd_diff(a: Scene, b: Scene) -> None:
    changes = diff(a, b)
    print(f"{len(changes)} changed path(s):")
    for c in changes:
        tag = " (added)" if c.before is None else " (removed)" if c.after is None else ""
        print(f"  {c.path}{tag}")
        if c.before is not None:
            print(f"    - {c.before}")
        if c.after is not None:
            print(f"    + {c.after}")


def _fields_text(d) -> str:
    text = ", ".join(f"{n} {b} -> {a}" for n, b, a in d.fields)
    return text + (f"  ({d.note})" if d.note else "")


def cmd_diff_by_strip(a: Scene, b: Scene) -> None:
    """The a -> b diff in words: one block per strip or console section, one line per
    changed scene line naming only the fields that moved."""
    changes = diff(a, b)
    print(f"{len(changes)} changed path(s):")
    print_by_strip(b, changes)


def print_by_strip(scene: Scene, changes: list[Change], mirrored=frozenset()) -> None:
    """``changes`` in words, one block per strip or section; ``scene`` is the after side.
    A path in ``mirrored`` is marked ``(mirrored)``."""
    group = None
    for d in describe_all(scene, changes):
        if d.group != group:
            group = d.group
            print(d.label)
        mark = "  (mirrored)" if d.path in mirrored else ""
        print(f"  {d.what:<18} {_fields_text(d)}{mark}")


def cmd_history(lib: list[tuple[str, Scene]], paths: list[str]) -> None:
    """Each path's timeline across the library, with the fields that moved between entries."""
    scenes = dict(lib)
    for path in paths:
        print(path)
        entries = history(lib, path)
        if not entries:
            print("  (never present)")
        prev = None
        for name, raw in entries:
            args = raw.split(" ", 1)[1] if raw and " " in raw else ("" if raw else "(absent)")
            moved = ""
            if prev is not None and raw is not None:
                moved = "   " + _fields_text(describe(scenes[name], Change(path, prev, raw)))
            print(f"  [{name}]  {args}{moved}")
            prev = raw


def cmd_snippet(snip: Snippet, out: str) -> None:
    """What the written snippet carries, and what the delta had that a snippet cannot."""
    d = snip.header.describe()
    body = len(snip.scene.lines) - 1
    print(f"wrote {out}: {body} lines")
    print(f"  filters: {', '.join(d['filters']) or '(none)'}")
    for mask in ("channels", "auxbuses", "maingrps"):
        if d[mask]:
            print(f"  {mask}: {', '.join(d[mask])}")
    if snip.skipped:
        print(f"  skipped {len(snip.skipped)} path(s) a snippet cannot carry:")
        for p in snip.skipped:
            print(f"    {p}")


def warn_relinked(pairs: list[tuple[int, int]]) -> None:
    """A snippet that carries lines of a bus pair whose link changed, but not the link."""
    if pairs:
        names = ", ".join(f"{odd}/{even}" for odd, even in pairs)
        print(f"x32scene: warning: the snippet carries lines of bus {names}, whose link "
              "changed, but not /config/buslink; loaded, they land on a pair still in its old "
              "link state", file=sys.stderr)


def _headamp_level(args: tuple[str, ...]) -> str:
    if len(args) >= 2:
        return f"{args[0]} dB, phantom {args[1]}"
    return f"a malformed head amp ({' '.join(args) or 'no fields'})"


def cmd_move_inputs(scene: Scene, moves: list[InputMove], out: str, *,
                    move_gain: bool = True) -> None:
    """One line per re-sourced channel: from where, to where, and the new input's head amp."""
    print(f"moved {len(moves)} channel(s); wrote {out}")
    for m in moves:
        cfg = scene.get(f"/ch/{m.ch:02d}/config")
        name = cfg.args[0].strip('"') if cfg and cfg.args else ""
        if m.headamp is None:
            amp = "no head-amp line for the new input"
        else:
            level = _headamp_level(m.headamp)
            if m.carried:
                amp = f"carried {level}"
            elif not 1 <= m.old_source <= 128:
                amp = f"no head amp to carry; the new input stays {level}"
            elif move_gain:
                amp = (f"{decode_source(m.old_source)} has no head-amp line to carry; "
                       f"the new input stays {level}")
            else:
                amp = f"head amp not carried; the new input stays {level}"
        print(f"  ch{m.ch:02d} {name:<14} {decode_source(m.old_source)} -> "
              f"{decode_source(m.new_source)}   {amp}")
    print("LOAD-TEST on the console before a gig.")


def cmd_header(doc: dict) -> None:
    """A decoded header, one field per line; list fields joined."""
    for k, v in doc.items():
        if k == "sections" and v is None:
            v = "no flag mask, so every scope the body carries applies"
        elif isinstance(v, dict):
            v = "; ".join(f"{a}: {', '.join(b) or '-'}" for a, b in v.items())
        elif isinstance(v, list):
            v = ", ".join(v) or "(none)"
        print(f"{k}: {v}")


def cmd_show(show: Show) -> None:
    """A .shw index: every slot with its decoded safes or filters."""
    print(f"show: {show.name!r}   written by: {show.writer}")
    for e in show.entries:
        if e.kind == "cue":
            d = e.decoded
            links = [f"scene {d['scene']}" if d.get("scene") is not None else "",
                     f"snippet {d['snippet']}" if d.get("snippet") is not None else "",
                     "skip" if d.get("skip") else ""]
            detail = f"   [{', '.join(x for x in links if x) or 'nothing attached'}]"
            print(f"  cue/{e.index:03d}  {d.get('number', '?')} {e.name}{detail}")
            continue
        extra = e.decoded.get("safes", e.decoded.get("filters"))
        detail = f"   [{', '.join(extra) or 'none'}]" if extra is not None else ""
        print(f"  {e.kind}/{e.index:03d}  {e.name}{detail}")

