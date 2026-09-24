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
    for ch, other in sorted(rep.get("preset_partners", {}).items()):
        print(f"ch{ch:02d} preset: the stereo-linked ch{other:02d} is not given the same preset, "
              "so it keeps its own processing: a load that reconciles the pair can end at "
              f"ch{max(ch, other):02d}'s; give ch{other:02d} the same preset in the plan")
    for row in rep.get("record", []):
        first, *rest = record_lines(row)
        print("\n".join([f"record {first}", *rest]))
    print_by_strip(edited, diff(template, edited), frozenset(rep["mirrored"]))
