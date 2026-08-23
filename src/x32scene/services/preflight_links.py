"""preflight family ``links``: stereo-pair state per strip family (keyed by the odd member),
the four link preferences, and — opt-in — send symmetry across every linked bus pair.

The console reconciles a linked pair on recall, so a one-sided send survives round-trip,
diff and verify and is then reverted on the desk. Symmetry is opt-in because that
reconciliation is inferred from files, not proven on hardware.
"""

from __future__ import annotations

from ..model import Scene
from ..tables import LINK_LINES, LINK_WIDTHS, LINKCFG, SEND_STRIPS
from .preflight_config import Finding, fail_unknown, mapping, numbered_items, want_bool

SECTIONS = frozenset({"links"})
_FAMILIES = {"ch": 32, "bus": 16, "auxin": 8, "fxrtn": 8, "mtx": 6}   # strips per family
_KEYS = frozenset({*_FAMILIES, "linkcfg", "require_send_symmetry"})
_LINE_AREA = {line: f"link {fam.lstrip('/')}" for fam, line in LINK_LINES.items()}
_LINE_AREA["/config/linkcfg"] = "linkcfg"


def _shape(scene: Scene, out: list[Finding]) -> None:
    for path, width in LINK_WIDTHS.items():
        area = _LINE_AREA[path]
        ln = scene.get(path)
        if ln is None:
            out.append(Finding("FAIL", area, f"{path} missing — cannot tell stereo pairs apart",
                               path))
        elif len(ln.args) != width:
            out.append(Finding("FAIL", area, f"carries {len(ln.args)} token(s), not {width}", path))
        else:
            bad = [a for a in ln.args if a not in ("ON", "OFF")]
            if bad:
                out.append(Finding("FAIL", area, f"token {bad[0]!r} is not ON/OFF", path))


def _pairs(scene: Scene, links: dict, out: list[Finding]) -> None:
    for fam, size in _FAMILIES.items():
        pins = numbered_items(mapping(links, fam, "links", out), f"link {fam}", out, lo=1, hi=size)
        if not pins:
            continue
        line = LINK_LINES[f"/{fam}"]
        ln = scene.get(line)
        for n, want in pins:
            area = f"link {fam} {n:02d}"
            if n % 2 == 0:
                out.append(Finding("FAIL", area, "pairs are keyed by their odd member — "
                                   f"declare {n - 1} for the {n - 1}/{n} pair"))
                continue
            if not isinstance(want, bool):
                out.append(Finding("FAIL", area, f"expected true or false, got {want!r}"))
                continue
            idx = (n - 1) // 2
            if ln is None or idx >= len(ln.args):
                out.append(Finding("FAIL", area, f"{line} missing — cannot verify pairing", line))
            elif (ln.args[idx] == "ON") is not want:
                out.append(Finding("FAIL", area, f"pair {n}/{n + 1} is {ln.args[idx]}, "
                                   f"expected {'ON' if want else 'OFF'}", line))


def _linkcfg(scene: Scene, cfg: dict, out: list[Finding]) -> None:
    fail_unknown(cfg, LINKCFG, "linkcfg", out)
    path = "/config/linkcfg"
    ln = scene.get(path)
    for name, idx in LINKCFG.items():
        want = want_bool(cfg, name, "linkcfg", out)
        if want is None:
            continue
        if ln is None or idx >= len(ln.args):
            out.append(Finding("FAIL", "linkcfg", f"{path} missing — cannot verify", path))
        elif (ln.args[idx] == "ON") is not want:
            out.append(Finding("FAIL", "linkcfg", f"{name} is {ln.args[idx]}, expected "
                               f"{'ON' if want else 'OFF'}", path))


def _send_symmetry(scene: Scene, out: list[Finding]) -> None:
    bl = scene.get("/config/buslink")
    if bl is None:
        return   # the shape pass has already reported it
    for i, tok in enumerate(bl.args):
        if tok != "ON":
            continue
        odd, even = 2 * i + 1, 2 * i + 2
        area = f"link bus {odd:02d}"
        diffs: list[str] = []
        missing: list[str] = []
        first = ""
        for strip in SEND_STRIPS:
            a = scene.get(f"{strip}/mix/{odd:02d}")
            b = scene.get(f"{strip}/mix/{even:02d}")
            if a is None or b is None:
                missing.append(strip)
            elif a.args[:2] != b.args[:2]:
                first = first or strip
                diffs.append(f"{strip} {' '.join(a.args[:2])} vs {' '.join(b.args[:2])}")
        if missing:
            out.append(Finding("FAIL", area, f"cannot verify send symmetry: {len(missing)} "
                               f"send line(s) missing ({missing[0]} …)"))
        if diffs:
            out.append(Finding("FAIL", area, f"{len(diffs)} send(s) differ between the linked "
                               f"pair {odd}/{even} — the console reverts one side on recall: "
                               f"{'; '.join(diffs[:3])}{' …' if len(diffs) > 3 else ''}",
                               f"{first}/mix/{odd:02d}"))


def check(scene: Scene, expected: dict, out: list[Finding]) -> None:
    _shape(scene, out)
    links = mapping(expected, "links", "config", out)
    fail_unknown(links, _KEYS, "links", out)
    _pairs(scene, links, out)
    _linkcfg(scene, mapping(links, "linkcfg", "links", out), out)
    if want_bool(links, "require_send_symmetry", "links", out):
        _send_symmetry(scene, out)
