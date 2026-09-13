"""Reading a JSON document a user wrote: a band-setup plan, a preflight config, a stage
sidecar."""

from __future__ import annotations

import json
from pathlib import Path


def read_json(path: str | Path) -> object:
    """The parsed document. Nesting past the interpreter's recursion limit raises
    ValueError naming the file: a RecursionError would escape the CLI as a traceback."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except RecursionError as e:
        raise ValueError(f"{path}: JSON nests too deeply to read") from e
