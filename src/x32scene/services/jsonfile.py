"""Reading a JSON document a user wrote: a band-setup plan, a preflight config, a stage
sidecar."""

from __future__ import annotations

import json
from pathlib import Path


def read_json(path: str | Path) -> object:
    """The parsed document, refusing a key repeated in one object with ValueError naming
    the key and file. Nesting past the interpreter's recursion limit raises
    ValueError naming the file: a RecursionError would escape the CLI as a traceback."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path}: not a JSON document (byte {e.start} is not UTF-8)") from None
    try:
        return json.loads(text, object_pairs_hook=lambda pairs: _unique(path, pairs))
    except RecursionError as e:
        raise ValueError(f"{path}: JSON nests too deeply to read") from e


def _unique(path: str | Path, pairs: list[tuple[str, object]]) -> dict:
    doc: dict = {}
    for key, value in pairs:
        if key in doc:
            raise ValueError(f"{path}: duplicate key {json.dumps(key)}")
        doc[key] = value
    return doc
