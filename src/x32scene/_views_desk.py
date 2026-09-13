"""Views of the desk as a whole rather than one scene's strips: the console-wide settings,
the running desk, the vocabularies and the effect types. Presentation only."""

from __future__ import annotations

import time

from pf_core.exceptions import InvalidInputError

from ._views import _fields_text, print_by_strip
from .model import Scene
from .services import fx as _fx
from .services.console import console_sections
from .services.describe import describe
from .services.desk import LIB_KINDS, DeskInfo, state_words
from .services.diff import Change
from .services.meters import Peaks, fmt_db, slot_names, to_db
from .services.snippets import Snippet
from .services.watch import Changed, Summary
from .tables import ROUTING_BLOCKS, SOURCE_DOMAINS, decode_tap, routing_block_names, routing_vocab
from .tables_fx import FX_SIDE_RACK_TYPES, FX_TYPES, decode_fx


def cmd_fx_types(code: str | None) -> None:
    """Every effect type with where it may go, or one type's parameters and defaults."""
    if code is None:
        for c in FX_TYPES:
            rack = "1-8" if c in FX_SIDE_RACK_TYPES else "1-4"
            print(f"  {c:6} {decode_fx(c):22} slots {rack}  {len(_fx.param_names(c))} params")
        return
    if code not in FX_TYPES:
        raise InvalidInputError(f"unknown FX type {code!r}")
    rack = "1-8" if code in FX_SIDE_RACK_TYPES else "1-4"
    print(f"{code}  {decode_fx(code)}  (slots {rack})")
    for i, (name, tok) in enumerate(zip(_fx.param_names(code), _fx.fx_defaults(code), strict=False), start=1):
        print(f"  {i:2}  {name:22} default {tok}")


def cmd_vocab(what: str, key: str | None) -> None:
    """The console's words: routing bank tokens per block, output sources, input sources."""
    if what == "routing":
        keys = [key] if key else list(ROUTING_BLOCKS)
        for k in keys:
            if k not in ROUTING_BLOCKS:
                raise InvalidInputError(f"routing key must be one of {', '.join(ROUTING_BLOCKS)}")
            print(f"/config/routing/{k}")
            for label in routing_block_names(k):
                print(f"  {label:6} " + " ".join(routing_vocab(k, label)))
        return
    if what == "taps":
        for i in range(77):
            print(f"  {i:2}  {decode_tap(i)}")
        return
    for lo, hi, label in SOURCE_DOMAINS:
        print(f"  {lo:3}-{hi:<3} {label}" + ("" if lo == hi else f" 1-{hi - lo + 1}"))
    print("  167-168 Talkback Int, Talkback Ext")


def cmd_console(scene: Scene) -> None:
    """The console-wide settings, one section per screen of the desk's Setup/Monitor pages."""
    for sec in console_sections(scene):
        print(sec.title)
        width = max([12, *(len(k) for k, _ in sec.rows)])
        for k, v in sec.rows:
            print(f"  {k:<{width}}  {v}")


def cmd_desk(info: DeskInfo) -> None:
    """The running desk: who it is, what it is doing, and what its memory holds."""
    print(f"{info.name}  {info.model}  firmware {info.firmware}  at {info.ip}")
    for k, v in state_words(info.stat).items():
        print(f"  {k:<16} {v}")
    prefs = {k.split("/", 1)[1]: v for k, v in info.prefs.items()}
    if prefs:
        print("preferences")
        for k in ("name", "clockrate", "clocksource", "show_control", "hardmute", "dcamute",
                  "safe_masterlevels", "scene_advance", "confirm_sceneload", "rec_control",
                  "remote/enable", "remote/protocol", "ip/dhcp", "ip/addr"):
            if k in prefs:
                print(f"  {k:<18} {prefs[k]}")
    if info.show:
        print(f"show  {info.show}")
    for kind in ("scene", "snippet", "cue", *LIB_KINDS):
        slots = info.slots.get(kind, [])
        label = LIB_KINDS.get(kind, kind + "s")
        print(f"{label}: {len(slots)}")
        for idx, name, extra in slots:
            print(f"  {idx:3}  {name:<18} {extra}")


def cmd_meters(peaks: Peaks, scene: Scene | None, *, show_all: bool = False) -> None:
    """Each slot's peak over the window in dBFS; silent slots hidden unless asked."""
    print(f"/meters/{peaks.meter}: {peaks.frames} frame(s)")
    for slot, v in peaks.peak.items():
        reduction = slot.endswith(" GR")   # gain-reduction meters read 1.0 when idle
        quiet = v >= 1.0 if reduction else v <= 0
        if quiet and not show_all:
            continue
        name = slot_names(scene, slot)
        bar = "" if reduction or v <= 0 else "#" * max(0, min(40, int(40 + to_db(v) * 40 / 60)))
        print(f"  {slot:<12} {name:<12} {fmt_db(v):>6}  {bar}")
    if not any(v > 0 for v in peaks.peak.values()):
        print("  (silence on every slot)")


def clock_text(at: float) -> str:
    """Local wall-clock time as HH:MM:SS.mmm."""
    return time.strftime("%H:%M:%S", time.localtime(at)) + f".{int(at * 1000) % 1000:03d}"


def cmd_watch_change(ev: Changed, scene: Scene) -> None:
    """One logged change: when, which node, the fields that moved. Flushed, so a pipe sees it live."""
    d = describe(scene, Change(ev.path, ev.before, ev.after))
    print(f"{clock_text(ev.at)}  {ev.path}  {d.label}  {_fields_text(d)}", flush=True)


def cmd_watch_summary(summary: Summary, end: Scene) -> None:
    print(f"summary: {summary.logged} change(s) logged; {summary.transient} path(s) changed and "
          f"came back; {summary.ignored} message(s) ignored (no watched path)")
    unknown = summary.unanswered
    if summary.net:
        print(f"net: {len(summary.net)} changed path(s):")
        print_by_strip(end, summary.net)
    elif unknown:
        print("net: nothing differs from the start among the paths that answered")
    else:
        print("net: nothing differs from the start")
    if unknown:
        head = ", ".join(unknown[:8]) + (" …" if len(unknown) > 8 else "")
        print(f"{len(unknown)} path(s) did not answer; their net change is unknown: {head}")


def cmd_watch_incomplete_snippet(summary: Summary) -> None:
    print(f"the snippet may be incomplete: {len(summary.unanswered)} path(s) did not answer")


def cmd_watch_no_snippet(snip: Snippet | None, out: str, summary: Summary) -> None:
    """Why --snippet wrote nothing: no net change, or none a snippet can carry."""
    if snip is None and summary.unanswered:
        print(f"no net change among the paths that answered; nothing written to {out}")
    elif snip is None:
        print(f"no net change; nothing written to {out}")
    else:
        print(f"the net change has nothing a snippet can carry "
              f"({', '.join(snip.skipped)}); nothing written to {out}")
