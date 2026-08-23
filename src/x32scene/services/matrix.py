"""Every monitor mix at once: senders down, monitor buses across.

A stereo-linked bus pair is one column, read off its odd bus; a pair whose two sides
disagree is flagged, since the console reverts one side on recall. Buses feeding an FX
slot are sends, not monitors, and stay out of the default column set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model import Scene
from ..tables import SEND_STRIPS, send_is_live
from .channelfx import pair_linked


@dataclass
class Column:
    bus: int                 # the odd (or only) bus
    buses: tuple[int, ...]   # (odd, even) for a linked pair
    label: str               # "1/2 Guitar L", "13 Plate"


@dataclass
class Cell:
    level: str | None = None    # the odd side's level token when live, else None
    asym: bool = False          # a linked pair whose sides disagree on on/level
    before: str | None = None   # compare(): the other scene's level
    changed: bool = False


@dataclass
class Row:
    strip: str
    label: str
    cells: dict[int, Cell] = field(default_factory=dict)


@dataclass
class Matrix:
    columns: list[Column]
    rows: list[Row]
    compare: bool = False


def fx_fed_buses(scene: Scene) -> set[int]:
    """Buses named as an FX slot's source (``/fx/N/source MIX13 MIX13``)."""
    out: set[int] = set()
    for ln in scene.find("/fx/"):
        if ln.path.endswith("/source"):
            for tok in ln.args:
                m = re.match(r"^MIX(\d+)$", tok)
                if m:
                    out.add(int(m.group(1)))
    return out


def _pair(scene: Scene, bus: int) -> tuple[int, ...]:
    if pair_linked(scene, f"/bus/{bus:02d}") is None:
        return (bus,)
    odd = bus if bus % 2 else bus - 1
    return (odd, odd + 1)


def _name(scene: Scene, path: str) -> str:
    cfg = scene.get(f"{path}/config")
    return cfg.args[0].strip('"') if cfg and cfg.args else ""


def monitor_buses(scene: Scene, buses: list[int] | None = None) -> list[Column]:
    """The matrix columns: the requested buses, or every bus that is not an FX send.
    A requested bus that is half of a linked pair yields the pair."""
    wanted = list(buses) if buses is not None else [b for b in range(1, 17)
                                                  if b not in fx_fed_buses(scene)]
    cols: list[Column] = []
    seen: set[int] = set()
    for b in wanted:
        if not 1 <= b <= 16:
            raise ValueError(f"bus must be 1-16, got {b}")
        group = _pair(scene, b)
        if group[0] in seen:
            continue
        seen.add(group[0])
        name = _name(scene, f"/bus/{group[0]:02d}")
        label = "/".join(str(x) for x in group) + (f" {name}" if name else "")
        cols.append(Column(group[0], group, label))
    return cols


def _cell(scene: Scene, strip: str, col: Column) -> Cell:
    ln = scene.get(f"{strip}/mix/{col.bus:02d}")
    if ln is None or len(ln.args) < 2:
        return Cell()
    asym = False
    if len(col.buses) == 2:
        other = scene.get(f"{strip}/mix/{col.buses[1]:02d}")
        asym = other is None or other.args[:2] != ln.args[:2]
    return Cell(ln.args[1] if send_is_live(ln.args) else None, asym)


def _row_label(scene: Scene, strip: str) -> str:
    return f"{strip.strip('/').replace('/', '')} {_name(scene, strip)}".rstrip()


def iem_matrix(scene: Scene, buses: list[int] | None = None, *,
               all_rows: bool = False) -> Matrix:
    """Rows are the send strips with a live send in some column, or every strip."""
    cols = monitor_buses(scene, buses)
    rows = []
    for strip in SEND_STRIPS:
        cells = {c.bus: _cell(scene, strip, c) for c in cols}
        if all_rows or any(cell.level is not None for cell in cells.values()):
            rows.append(Row(strip, _row_label(scene, strip), cells))
    return Matrix(cols, rows)


def compare(a: Scene, b: Scene, buses: list[int] | None = None) -> Matrix:
    """``b``'s matrix with each cell also carrying ``a``'s level and whether it moved;
    rows are the senders live in either scene."""
    before = {r.strip: r for r in iem_matrix(a, buses, all_rows=True).rows}
    after = iem_matrix(b, buses, all_rows=True)
    rows = []
    for row in after.rows:
        prev = before.get(row.strip)
        for bus, cell in row.cells.items():
            cell.before = prev.cells[bus].level if prev and bus in prev.cells else None
            cell.changed = cell.before != cell.level
        if any(c.level is not None or c.before is not None for c in row.cells.values()):
            rows.append(row)
    return Matrix(after.columns, rows, compare=True)
