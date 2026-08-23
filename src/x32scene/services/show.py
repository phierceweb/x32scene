"""Show files: the ``.shw`` index X32-Edit writes next to its ``<show>.NNN.scn`` and
``<show>.NNN.snp`` companions. One line per slot, carrying that slot's file header
fields, so the index alone says what each scene safes and each snippet filters."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Line
from .headers import decode_header


@dataclass
class ShowEntry:
    kind: str          # "scene", "snippet", "cue"
    index: int
    args: list[str]
    decoded: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.decoded.get("name") or next((a.strip('"') for a in self.args
                                                 if a.startswith('"')), "")


@dataclass
class Show:
    name: str
    writer: str
    entries: list[ShowEntry]

    def of(self, kind: str) -> list[ShowEntry]:
        return [e for e in self.entries if e.kind == kind]


def read_show(text: str) -> Show:
    """Parse a ``.shw``: the ``show`` line, then ``scene/NNN``, ``snippet/NNN`` and
    ``cue/NNN`` lines. A scene or snippet line decodes like that file's own header."""
    name = writer = ""
    entries: list[ShowEntry] = []
    for raw in text.split("\n"):
        ln = Line.parse(raw)
        if not ln.path or ln.path.startswith("#"):
            continue
        if ln.path == "show":
            name = ln.args[0].strip('"') if ln.args else ""
            writer = ln.args[-1].strip('"') if len(ln.args) > 1 else ""
            continue
        kind, _, idx = ln.path.partition("/")
        if kind not in ("scene", "snippet", "cue") or not idx.isdigit():
            continue
        decoded = {}
        if kind in ("scene", "snippet"):
            decoded = decode_header("#4.0# " + " ".join(ln.args)) or {}
            decoded.pop("version", None)
        if kind == "cue" and len(ln.args) >= 5:
            numb, scene, snippet = ln.args[0], ln.args[3], ln.args[4]
            decoded = {"name": ln.args[1].strip('"'),
                       "number": (f"{int(numb) // 100}.{int(numb) // 10 % 10}.{int(numb) % 10}"
                                  if numb.isdigit() else numb),
                       "skip": ln.args[2] == "1",
                       "scene": None if scene == "-1" else int(scene),
                       "snippet": None if snippet == "-1" else int(snippet)}
        entries.append(ShowEntry(kind, int(idx), ln.args, decoded))
    return Show(name, writer, entries)


# ---- writing a show ----------------------------------------------------------------
@dataclass
class Cue:
    number: str            # "1", "1.2", "1.2.3" as the desk displays it
    name: str = ""
    scene: int | None = None
    snippet: int | None = None
    skip: bool = False

    def numb(self) -> int:
        """The desk's cue integer: 1.2.3 -> 123, 1 -> 100."""
        parts = self.number.split(".") + ["0", "0"]
        if len(parts) > 5 or not all(p.isdigit() for p in parts) or not 0 <= int(parts[0]) <= 500:
            raise ValueError(f"cue number must look like 1, 1.2 or 1.2.3 (0-500), got {self.number!r}")
        if int(parts[1]) > 9 or int(parts[2]) > 9:
            raise ValueError(f"cue sub-numbers run 0-9, got {self.number!r}")
        return int(parts[0]) * 100 + int(parts[1]) * 10 + int(parts[2])

    def line(self, index: int) -> str:
        sc = -1 if self.scene is None else self.scene
        sn = -1 if self.snippet is None else self.snippet
        return f'cue/{index:03d} {self.numb()} "{self.name}" {int(self.skip)} {sc} {sn} 0 1 0 0'


def parse_cue(text: str) -> Cue:
    """``"1 Opener scene=0 snippet=2 skip"`` -> Cue. The name is every word that is not
    a key=value or ``skip``."""
    words = text.split()
    if not words:
        raise ValueError("empty cue")
    cue = Cue(words[0])
    name: list[str] = []
    for w in words[1:]:
        if w == "skip":
            cue.skip = True
        elif w.startswith("scene=") or w.startswith("snippet="):
            key, _, val = w.partition("=")
            if not val.isdigit() or not 0 <= int(val) <= 99:
                raise ValueError(f"cue {cue.number}: {key} must be a slot 0-99, got {val!r}")
            setattr(cue, key, int(val))
        else:
            name.append(w)
    cue.name = " ".join(name)
    cue.numb()
    return cue


def _header_fields(text: str, kind: str, path: str) -> str:
    first = text.split("\n", 1)[0]
    ln = Line.parse(first)
    d = decode_header(text)
    if d is None or d.get("kind") != kind:
        raise ValueError(f"{path}: not a {kind} file (its header says "
                         f"{d.get('kind') if d else 'nothing'})")
    return " ".join(ln.args)


def build_show(name: str, scenes: list[tuple[str, str]], snippets: list[tuple[str, str]],
               cues: list[Cue], writer: str = "x32scene") -> dict[str, str]:
    """{filename: text} for a show: the ``.shw`` index plus one companion per scene and
    snippet, named as X32-Edit names them. ``scenes``/``snippets`` are (path, text)."""
    if len(scenes) > 100 or len(snippets) > 100 or len(cues) > 100:
        raise ValueError("a show holds at most 100 scenes, 100 snippets and 100 cues")
    for cue in cues:
        if cue.scene is not None and cue.scene >= len(scenes):
            raise ValueError(f"cue {cue.number}: scene {cue.scene} is not in this show")
        if cue.snippet is not None and cue.snippet >= len(snippets):
            raise ValueError(f"cue {cue.number}: snippet {cue.snippet} is not in this show")
    files: dict[str, str] = {}
    lines = ["#4.0#", f'show "{name}" 0 0 0 0 0 0 0 0 0 0 "{writer}"']
    lines += [cue.line(i) for i, cue in enumerate(cues)]
    for i, (path, text) in enumerate(scenes):
        lines.append(f"scene/{i:03d} {_header_fields(text, 'scene', path)}")
        files[f"{name}.{i:03d}.scn"] = text
    for i, (path, text) in enumerate(snippets):
        lines.append(f"snippet/{i:03d} {_header_fields(text, 'snippet', path)}")
        files[f"{name}.{i:03d}.snp"] = text
    files[f"{name}.shw"] = "\n".join(lines) + "\n"
    return files
