"""The X32 save-scope model — the checkboxes in the Save-as-scene/preset dialog.

Each scope maps to a family of (bare) channel paths.
A `.chn` (or partial scene) contains only the paths whose scope was checked at save time.
"""

from __future__ import annotations

# dialog order. insert/automix have no checkbox of their own, but need a scope or they
# vanish silently from a full preset.
SCOPES = ["ha", "scribble", "gate", "comp", "eq", "sends", "mainfader",
          "insert", "automix"]

SCOPE_LABELS = {
    "ha": "HA Config",
    "scribble": "Scribble Strip",
    "gate": "Gate",
    "comp": "Compressor",
    "eq": "EQ",
    "sends": "Sends",
    "mainfader": "Main/Fader",
    "insert": "Insert",
    "automix": "Automix",
}

# main-mix bare paths that belong to Main/Fader (NOT the numbered /mix/NN sends)
_MAINFADER = {"/mix", "/mix/fader", "/mix/st", "/mix/pan", "/mix/mono", "/mix/mlevel"}


def scope_of(bare_path: str) -> str | None:
    """Classify a bare channel path (``/eq/1``, ``/mix/03``, ``/headamp/000``) into a scope.

    Returns the scope key, or None for paths that aren't part of any save scope
    (e.g. ``/grp`` — DCA/mute membership is not stored in presets).
    """
    if bare_path in _MAINFADER:
        return "mainfader"
    if bare_path == "/config":
        return "scribble"
    if bare_path.startswith("/headamp") or bare_path in ("/preamp", "/delay"):
        return "ha"
    if bare_path.startswith("/gate"):
        return "gate"
    if bare_path.startswith("/dyn"):
        return "comp"
    if bare_path.startswith("/eq"):
        return "eq"
    if bare_path.startswith("/insert"):
        return "insert"
    if bare_path.startswith("/automix"):
        return "automix"
    if bare_path.startswith("/mix/"):
        tail = bare_path[len("/mix/"):]
        if tail.isdigit():
            return "sends"
    return None
