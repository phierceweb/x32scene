"""What band-setup wrote: the summary line, then every changed path by strip."""

from __future__ import annotations

from ._cli_record import record_lines
from ._views import print_by_strip
from .model import Scene
from .services.diff import diff


def cmd_band_setup(template: Scene, edited: Scene, rep: dict, out: str) -> None:
    print(f"applied plan: {rep['lines_changed']} line(s) over "
          f"{len(rep['changed'])} path(s); wrote {out}")
    for ch, scopes in sorted(rep.get("preset_skipped", {}).items()):
        print(f"ch{ch:02d} preset: skipped {', '.join(scopes)}: its header does not flag "
              "them present")
    for row in rep.get("record", []):
        first, *rest = record_lines(row)
        print("\n".join([f"record {first}", *rest]))
    print_by_strip(edited, diff(template, edited), frozenset(rep["mirrored"]))
