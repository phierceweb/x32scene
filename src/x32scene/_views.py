"""Read-only display commands for the x32 CLI — render a scene to the console.

Pure presentation: each function takes a parsed Scene and prints. No file writes (those
live in cli.py). Kept separate from CLI wiring so cli.py stays parsers + dispatch.
"""

from __future__ import annotations

from ._views_ports import bus_names as _bus_names
from ._views_ports import cmd_ports
from .services import fx as _fx
from .services import groups as _groups
from .services import routing as _routing
from .services.describe import describe, describe_all
from .services.diff import Change, diff
from .services.history import history
from .services.show import Show
from .services.snippets import Snippet
from .model import Scene
from .tables import SEND_STRIPS
from .tables_fx import decode_fx

__all__ = ["cmd_ports"]


def cmd_info(scene: Scene) -> None:
    print(f"title: {scene.name!r}   lines: {len(scene.lines)}")
    print("channels:")
    for ln in scene.find("/ch/"):
        if ln.path.endswith("/config"):
            n = int(ln.path.split("/")[2])
            print(f"  ch{n:02d}  {ln.args[0].strip(chr(34))}")
    print("buses:")
    for n, nm in sorted(_bus_names(scene).items()):
        print(f"  bus{n:02d}  {nm}")


def cmd_buses(scene: Scene) -> None:
    """Show the 16 mix buses: stereo-link pairs, names, FX assignment, and send-tap mix."""
    names = _bus_names(scene)
    bl = scene.get("/config/buslink")  # 8 tokens, one per pair 1/2 … 15/16
    linked = {2 * i + 1: (bl.args[i] == "ON") for i in range(8)} if bl else {}
    fx_src = {}
    for ln in scene.find("/fx/"):
        if ln.path.endswith("/source") and ln.args and ln.args[0].startswith("MIX"):
            fx_src[int(ln.args[0][3:])] = ln.path.split("/")[2]
    fx_type = {int(ln.path.split("/")[2]): ln.args[0]
               for ln in scene.find("/fx/") if len(ln.path.split("/")) == 3 and ln.args}
    for n in range(1, 17):
        taps = {"PRE": 0, "POST": 0}
        for strip in SEND_STRIPS:
            ln = scene.get(f"{strip}/mix/{n:02d}")
            if ln and len(ln.args) >= 4 and ln.args[0] == "ON":
                taps[ln.args[3]] = taps.get(ln.args[3], 0) + 1
        role = ""
        if n in fx_src:
            role = f"-> FX{fx_src[n]} ({decode_fx(fx_type.get(int(fx_src[n]), '?'))})"
        pair = ""
        if n % 2 == 1:
            pair = "stereo-pair" if linked.get(n) else "mono"
        tapmix = " ".join(f"{k}:{v}" for k, v in taps.items() if v)
        print(f"  bus{n:02d} {names.get(n, ''):<11} {pair:<11} {role:<18} sends[{tapmix}]")


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
    group = None
    for d in describe_all(b, changes):
        if d.group != group:
            group = d.group
            print(d.label)
        print(f"  {d.what:<18} {_fields_text(d)}")


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


def cmd_header(doc: dict) -> None:
    """A decoded header, one field per line; list fields joined."""
    for k, v in doc.items():
        if isinstance(v, dict):
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

