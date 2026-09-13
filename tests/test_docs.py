"""Doc-sync gates. `docs/cli.md` is the CLI's published contract and `docs/README.md` the
index readers treat as exhaustive; both were kept in step by hand until these failed."""

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


# -o is documented as `-o OUT`; --dir is show-build's own spelling of it
_SYNONYMS = {"--out", "--dir"}


def test_every_subcommand_is_in_cli_md():
    text = CLI_MD.read_text()
    missing = [name for name in _subparsers() if f"`{name} " not in text
               and f"`{name}`" not in text and f"`{name} [" not in text]
    assert not missing, f"not documented in docs/cli.md: {sorted(missing)}"


def test_every_flag_is_in_cli_md():
    text = CLI_MD.read_text()
    missing = {name: sorted(f for f in _long_flags(sp) - _SYNONYMS if f not in text)
               for name, sp in _subparsers().items()}
    missing = {k: v for k, v in missing.items() if v}
    assert not missing, f"flags not documented in docs/cli.md: {missing}"


def test_cli_md_invents_no_flags():
    """A row's Flags column may only name flags that command actually accepts."""
    real = {name: _long_flags(sp) for name, sp in _subparsers().items()}
    bad = []
    for line in CLI_MD.read_text().splitlines():
        m = re.match(r"\|\s*`([a-z-]+)[^`]*`\s*\|(.*)\|(.*)\|\s*$", line)
        if not m or m.group(1) not in real:
            continue
        cmd = m.group(1)
        for flag in re.findall(r"`(--[a-z-]+)", m.group(2) + m.group(3)):
            if flag not in real[cmd]:
                bad.append(f"{cmd} {flag}")
    assert not bad, f"docs/cli.md documents flags that do not exist: {sorted(set(bad))}"


def test_docs_index_lists_every_doc():
    index = (DOCS / "README.md").read_text()
    missing = [p.name for p in sorted(DOCS.glob("*.md"))
               if p.name != "README.md" and f"]({p.name})" not in index]
    assert not missing, f"missing from docs/README.md: {missing}"


def _anchor(heading: str) -> str:
    s = heading.strip().lower().replace("`", "")
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip())


@pytest.mark.parametrize("doc", sorted(DOCS.glob("*.md")), ids=lambda p: p.name)
def test_table_of_contents_anchors_resolve(doc):
    lines = doc.read_text().splitlines()
    if "## Table of contents" not in lines:
        pytest.skip("no table of contents")
    anchors = {_anchor(ln.lstrip("#").strip()) for ln in lines if ln.startswith("#")}
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
def test_relative_links_resolve(doc):
    dead = []
    for target in re.findall(r"\]\((?!https?:|#)([^)#]+)", doc.read_text()):
        if not (doc.parent / target).exists():
            dead.append(target)
    assert not dead, f"{doc.name}: links to files that do not exist: {dead}"
