"""Report-style views: the IEM matrix grid, and the markdown snapshot `report` renders.
Presentation only — every fact comes from a service or a domain table."""

from __future__ import annotations

from ._views_ports import bus_names, ports_rows
from .model import Scene
from .services import fx as _fx
from .services.console import console_sections
from .services import groups as _groups
from .services import routing as _routing
from .services.channelfx import pair_linked
from .services.matrix import Cell, Matrix, iem_matrix
from .tables_fx import decode_fx

_SILENT = "·"
_NONE = "—"


def _cell_text(cell: Cell, compare: bool) -> str:
    if compare and cell.changed:
        return f"{cell.before or _SILENT}>{cell.level or _SILENT}"
    return (cell.level or _SILENT) + ("*" if cell.asym else "")


def cmd_iem_matrix(m: Matrix) -> None:
    """Senders down, monitor buses across; a compare matrix shows before>after."""
    width = max([11, *(len(c.label) for c in m.columns)])
    label_w = max([10, *(len(r.label) for r in m.rows)])
    print(" " * label_w + "  " + "  ".join(f"{c.label:>{width}}" for c in m.columns))
    for r in m.rows:
        cells = "  ".join(f"{_cell_text(r.cells[c.bus], m.compare):>{width}}" for c in m.columns)
        print(f"{r.label:<{label_w}}  {cells}")
    if m.compare:
        print(f"\n(before>after where a send moved; {_SILENT} = silent)")
    else:
        print(f"\n({_SILENT} = silent; * = the linked pair's two sides differ)")


# ---- markdown report --------------------------------------------------------------
def _table(headers: list[str], rows: list[list[str]]) -> None:
    def cell(v: str) -> str:
        return v.replace("|", "\\|")
    print("| " + " | ".join(headers) + " |")
    print("|" + "---|" * len(headers))
    for row in rows:
        print("| " + " | ".join(cell(v) for v in row) + " |")
    print()


def _on(line) -> str:
    return "on" if line and line.args and line.args[0] == "ON" else "off"


def _short(strip: str) -> str:
    return strip.strip("/").replace("/", "")


def _channels(scene: Scene) -> None:
    in_dca: dict[str, list[str]] = {}
    for n, strips in _groups.dca_members(scene).items():
        for s in strips:
            in_dca.setdefault(s, []).append(str(n))
    rows = []
    for cs in _routing.channel_sources(scene):
        p = f"/ch/{cs.ch:02d}"
        idx = _routing.channel_headamp_index(scene, cs.ch)
        ha = scene.get(f"/headamp/{idx:03d}") if idx is not None else None
        gain = ha.args[0] if ha and ha.args else _NONE
        phantom = ("on" if ha.args[1] == "ON" else "off") if ha and len(ha.args) > 1 else _NONE
        pre = scene.get(f"{p}/preamp")
        lowcut = (f"{pre.args[4]} Hz" if pre and len(pre.args) > 4 and pre.args[2] == "ON"
                  else "off")
        mix = scene.get(f"{p}/mix")
        main = ("in" if mix and len(mix.args) > 2 and mix.args[0] == "ON"
                and mix.args[1] != "-oo" and mix.args[2] == "ON" else "out")
        rows.append([f"{cs.ch:02d}", cs.name, cs.source, gain, phantom, lowcut,
                     _on(scene.get(f"{p}/gate")), _on(scene.get(f"{p}/dyn")),
                     ", ".join(in_dca.get(p, [])) or _NONE, main])
    print("## Channels\n")
    _table(["Ch", "Name", "Source", "Gain", "+48V", "Low cut", "Gate", "Comp", "DCA", "Main"],
           rows)


def _buses(scene: Scene) -> None:
    names = bus_names(scene)
    fed: dict[int, str] = {}
    for ln in scene.find("/fx/"):
        if ln.path.endswith("/source"):
            slot = ln.path.split("/")[2]
            tline = scene.get(f"/fx/{slot}")
            code = tline.args[0] if tline and tline.args else "?"
            for tok in ln.args:
                if tok.startswith("MIX") and tok[3:].isdigit():
                    fed[int(tok[3:])] = f"FX {slot} send ({decode_fx(code)})"
    rows = []
    for n in range(1, 17):
        partner = pair_linked(scene, f"/bus/{n:02d}")
        odd = n if n % 2 else n - 1
        pair = f"{odd}/{odd + 1}" if partner else "mono"
        rows.append([f"{n:02d}", names.get(n, ""), pair, fed.get(n, "monitor")])
    print("## Buses\n")
    _table(["Bus", "Name", "Pair", "Role"], rows)


def _outputs(scene: Scene, physical: int | None, stage: dict | None) -> None:
    rows = []
    for r in ports_rows(scene, "all", stage):
        out = f"{r['bank']} {r['n']:02d}"
        if physical is not None and r["bank"] == "main":
            out += " (XLR)" if r["n"] <= physical else " (virtual)"
        where = ""
        if r["stage"]:
            e = r["stage"]
            who = " / ".join(x for x in (e.get("device"), e.get("wearer")) if x)
            where = f"{e.get('jack', '?')} -> {who or '?'}"
        rows.append([out, r["label"], r["pos"] or "", " + ".join(r["mirrors"]), where])
    print("## Outputs\n")
    _table(["Out", "Source", "Tap", "Mirror", "Stage"], rows)


def _matrix(scene: Scene) -> None:
    m = iem_matrix(scene)
    print("## Monitor mixes\n")
    _table(["Sender", *(c.label for c in m.columns)],
           [[r.label, *(_cell_text(r.cells[c.bus], False) for c in m.columns)] for r in m.rows])


def _fx_table(scene: Scene) -> None:
    print("## FX\n")
    _table(["Slot", "Effect", "Source"],
           [[str(f.slot), f"{f.name} ({f.code})", f.source or ""] for f in _fx.read_fx(scene)])


def _group_table(scene: Scene) -> None:
    names = _groups.dca_names(scene)
    rows = [[f"DCA {n}", names.get(n, ""), ", ".join(_short(s) for s in strips)]
            for n, strips in _groups.dca_members(scene).items() if strips]
    rows += [[f"MG {n}", "", ", ".join(_short(s) for s in strips)]
             for n, strips in _groups.mute_members(scene).items() if strips]
    print("## Groups\n")
    _table(["Group", "Name", "Members"], rows)


def _console(scene: Scene) -> None:
    print("## Console\n")
    for sec in console_sections(scene):
        print(f"### {sec.title}\n")
        _table(["Setting", "Value"], [[k.strip(), v] for k, v in sec.rows])


def cmd_report(scene: Scene, physical: int | None = None, stage: dict | None = None) -> None:
    """The scene as a markdown snapshot: channels, buses, outputs, monitor mixes, FX and
    groups — the document a rig keeps by hand, generated instead."""
    print(f"# {scene.name or 'scene'}\n")
    print(f"Snapshot generated by x32scene from {len(scene.lines)} lines.\n")
    _channels(scene)
    _buses(scene)
    _outputs(scene, physical, stage)
    _matrix(scene)
    _fx_table(scene)
    _group_table(scene)
    _console(scene)
