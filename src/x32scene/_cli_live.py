"""CLI glue for `watch`: the start snapshot, the live log, the summary and the snippet."""

from __future__ import annotations

import os
import sys

from . import _json
from . import _views
from . import _views_desk as _vdesk
from ._cli_files import load_checked, refuse_overwrite, refuse_unwritable
from .services import buslink as _buslink
from .services import osc as _osc
from .services import snippets as _snippets
from .services import watch as _watch


def run_watch(args) -> int:
    """Exit 2 when the desk does not answer the start snapshot; Ctrl-C ends a watch with 0."""
    if args.snippet is not None:
        refuse_unwritable(args.snippet, "--snippet")
        refuse_overwrite(args.snippet, args.reference, force=args.force, flag="--snippet")
    ref = load_checked(args.reference)
    port = _osc.X32_PORT
    with _watch.UdpTransport(args.ip, port) as link:
        sub = _watch.subscribe(link)
        try:
            start, unanswered = _osc.pull_scene_like(ref, args.ip, port=port,
                                                     timeout=args.timeout, between=sub)
            sub()
        except _osc.OscError as e:
            print(f"watch failed: {e}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print("stopped during the start pull; nothing watched", file=sys.stderr)
            return 0
        if unanswered:
            head = ", ".join(unanswered[:8]) + (" …" if len(unanswered) > 8 else "")
            print(f"unanswered paths, not watched ({len(unanswered)}): {head}", file=sys.stderr)
        w = _watch.Watch(ref, start, reply_timeout=args.timeout)
        nodes = sum(ln.path.startswith("/") for ln in start.lines)
        print(f"watching {nodes} path(s) on {args.ip}; Ctrl-C to stop", file=sys.stderr)

        def log(events) -> None:
            for ev in events:
                if args.json:
                    _json.dump_line(_json.watch_change_doc(ev, w.end_scene()))
                else:
                    _vdesk.cmd_watch_change(ev, w.end_scene())

        lost = None
        try:
            log(w.run(link, seconds=args.seconds, backlog=sub.backlog))
        except KeyboardInterrupt:
            try:
                log(w.flush(link))
            except KeyboardInterrupt:
                pass
            except OSError as e:
                lost = _link_error(e)
        except OSError as e:
            lost = _link_error(e)
    summary, end = w.summary(), w.end_scene()
    snip = None
    if args.snippet and summary.net:
        snip = _snippets.make_snippet(start, end, os.path.splitext(os.path.basename(args.snippet))[0],
                                      {c.path for c in summary.net}.__contains__)
    carried = snip is not None and len(snip.scene.lines) > 1
    written = False
    try:
        if carried:
            snip.scene.save(args.snippet)
            written = True
            _views.warn_relinked(
                _buslink.relinked_pairs(start, end, [ln.path for ln in snip.scene.lines]))
    finally:
        _summarize(args, summary, end, snip, carried, written)
    if lost is not None:
        print(f"watch stopped: the link to the desk failed ({lost}); the summary covers what "
              "was read before it", file=sys.stderr)
        return 1
    return 0


def _link_error(e: OSError) -> OSError:
    """The send to the desk failed (no route, network down); a closed stdout is not that."""
    if isinstance(e, BrokenPipeError):
        raise e
    return e


def _summarize(args, summary, end, snip, carried: bool, written: bool) -> None:
    """Printed even when the snippet write fails, so a long watch's net change survives it."""
    if args.json:
        _json.dump_line(_json.watch_summary_doc(summary, end, args.snippet, snip, written))
        return
    _vdesk.cmd_watch_summary(summary, end)
    if written:
        _views.cmd_snippet(snip, args.snippet)
        if summary.unanswered:
            _vdesk.cmd_watch_incomplete_snippet(summary)
    elif args.snippet and not carried:
        _vdesk.cmd_watch_no_snippet(snip, args.snippet, summary)
