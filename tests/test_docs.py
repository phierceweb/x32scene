"""Doc-sync gates: every subcommand has a row in `docs/cli.md`, each flag is in its own
command's rows and no row names a flag its command lacks; `docs/README.md` indexes every doc;
relative links resolve, and a `#fragment` to a heading by GitHub's anchor rules."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from x32scene._parsers import _build_parser

DOCS = Path(__file__).resolve().parents[1] / "docs"
CLI_MD = DOCS / "cli.md"


def _subparsers() -> dict:
    action = next(a for a in _build_parser(None)._actions if a.dest == "cmd")
    return action.choices


def _long_flags(parser) -> set[str]:
    return {s for a in parser._actions for s in a.option_strings
            if s.startswith("--") and s != "--help"}


def _rows() -> dict[str, list[str]]:
    """Each command's table rows: those whose first cell starts with the command's name."""
    real = _subparsers()
    rows: dict[str, list[str]] = {}
    for line in CLI_MD.read_text().splitlines():
        m = re.match(r"\|\s*`([a-z][a-z-]*)[\s`\[]", line)
        if m and m.group(1) in real:
            rows.setdefault(m.group(1), []).append(line)
    return rows


def _names(text: str, flag: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text) is not None


def _intro() -> str:
    return " ".join(CLI_MD.read_text().split("\n## ", 1)[0].split())


def test_every_subcommand_has_a_row_in_cli_md():
    missing = sorted(set(_subparsers()) - set(_rows()))
    assert not missing, f"no row in docs/cli.md: {missing}"


def test_every_flag_is_in_its_own_commands_rows():
    """`-o` stands for its long spellings; `--force` on a command with `-o` is the intro's."""
    rows = _rows()
    missing = {}
    for name, sp in _subparsers().items():
        text = "\n".join(rows.get(name, []))
        writes = any("-o" in a.option_strings for a in sp._actions)
        gaps = []
        for a in sp._actions:
            longs = [s for s in a.option_strings if s.startswith("--") and s != "--help"]
            if not longs or (longs == ["--force"] and writes):
                continue
            spellings = ["-o"] if "-o" in a.option_strings else longs
            gaps += [s for s in spellings if not _names(text, s)]
        if gaps:
            missing[name] = gaps
    assert not missing, f"flags missing from their command's rows in docs/cli.md: {missing}"


def test_the_intro_documents_force_for_every_writing_command():
    assert _names(_intro(), "--force") and "Every writing command takes that flag" in _intro()
    lacking = sorted(name for name, sp in _subparsers().items()
                     if any("-o" in a.option_strings for a in sp._actions)
                     and "--force" not in _long_flags(sp))
    assert not lacking, f"the intro says every writing command takes --force: {lacking}"


def test_cli_md_invents_no_flags():
    """A row may only name flags that command actually accepts."""
    real = {name: _long_flags(sp) for name, sp in _subparsers().items()}
    bad = [f"{cmd} {flag}" for cmd, lines in _rows().items() for line in lines
           for flag in re.findall(r"`(--[a-z-]+)", "|".join(re.split(r"(?<!\\)\|", line)[2:]))
           if flag not in real[cmd]]
    assert not bad, f"docs/cli.md documents flags that do not exist: {sorted(set(bad))}"


def test_docs_index_lists_every_doc():
    index = (DOCS / "README.md").read_text()
    missing = [p.name for p in sorted(DOCS.glob("*.md"))
               if p.name != "README.md" and f"]({p.name})" not in index]
    assert not missing, f"missing from docs/README.md: {missing}"


def _anchor(heading: str) -> str:
    """GitHub's rule: lowercase, drop punctuation but hyphens and spaces, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _anchors(doc: Path) -> set[str]:
    """Every heading's anchor outside code fences; a repeated one gains `-1`, `-2`, as on GitHub."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    fenced = False
    for ln in doc.read_text().splitlines():
        if ln.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        m = None if fenced else re.match(r"#{1,6}\s+(.+)$", ln)
        if m:
            slug = _anchor(m.group(1))
            n = seen[slug] = seen.get(slug, -1) + 1
            anchors.add(f"{slug}-{n}" if n else slug)
    return anchors


_TOC_DOCS = [p for p in sorted(DOCS.glob("*.md")) if "## Table of contents" in p.read_text()]


@pytest.mark.parametrize("doc", _TOC_DOCS, ids=lambda p: p.name)
def test_table_of_contents_anchors_resolve(doc):
    lines = doc.read_text().splitlines()
    anchors = _anchors(doc)
    start = lines.index("## Table of contents")
    dead = []
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        m = re.match(r"- \[(.+)\]\(#(.+)\)$", ln)
        if m and m.group(2) not in anchors:
            dead.append(m.group(2))
    assert not dead, f"{doc.name}: table-of-contents anchors match no heading: {dead}"


@pytest.mark.parametrize("doc", sorted(DOCS.glob("*.md")), ids=lambda p: p.name)
def test_link_fragments_resolve(doc):
    """A `#fragment` into a markdown doc, this one or another, names one of its headings."""
    dead = []
    for path, frag in re.findall(r"\]\((?!https?:)([^)#\s]*)#([^)\s]+)\)", doc.read_text()):
        target = doc.parent / path if path else doc
        if target.suffix == ".md" and target.exists() and frag not in _anchors(target):
            dead.append(f"{path}#{frag}")
    assert not dead, f"{doc.name}: link fragments match no heading: {dead}"


@pytest.mark.parametrize("doc", sorted(DOCS.glob("*.md")), ids=lambda p: p.name)
def test_relative_links_resolve(doc):
    dead = []
    for target in re.findall(r"\]\((?!https?:|#)([^)#]+)", doc.read_text()):
        if not (doc.parent / target).exists():
            dead.append(target)
    assert not dead, f"{doc.name}: links to files that do not exist: {dead}"


def test_a_file_the_wheel_ships_names_no_repository_file_by_a_bare_name():
    root = DOCS.parent
    shipped = re.search(r"license-files = \[([^\]]*)\]", (root / "pyproject.toml").read_text())
    names = re.findall(r'"([^"]+)"', shipped.group(1))
    bare = {name: re.findall(r"(?<![/\w])[\w-]+\.md\b", (root / name).read_text())
            for name in names}
    assert not any(bare.values()), f"shipped without the files they name: {bare}"
