"""Routing edits: the input/output routing banks, a channel's source, an output's source
and tap, and routing presets (`.rou`) out and in. ``routing.py`` is the read side."""

from __future__ import annotations

from ..model import HEADER_WIDTH, Scene, check_token
from ..tables import (
    OUTPUT_BANKS, OUTPUT_POS, ROUTING_BLOCKS, SOURCE_DOMAINS, decode_source, decode_tap,
    routing_block_names, routing_vocab,
)

ROUTING_PRESET_KEYS = ("IN", "AES50A", "AES50B", "CARD")   # what the console's library holds
_SOURCE_KINDS = {"off": 0, "local": 1, "an": 1, "local input": 1, "aes50-a": 33, "a": 33,
                 "aes50a": 33, "aes50-b": 81, "b": 81, "aes50b": 81, "card": 129, "usb": 129,
                 "aux": 161, "aux in": 161}


def set_routing(scene: Scene, key: str, blocks: dict[str, str]) -> list[str]:
    """Set blocks of ``/config/routing/<key>`` by label (``{"1-8": "A1-8"}``); returns
    the labels changed. Every value is checked against the console's vocabulary."""
    if key not in ROUTING_BLOCKS:
        raise ValueError(f"routing key must be one of {', '.join(ROUTING_BLOCKS)}, got {key!r}")
    ln = scene.get(f"/config/routing/{key}")
    if ln is None:
        raise KeyError(f"no /config/routing/{key}")
    names = routing_block_names(key)
    for label, value in blocks.items():
        if label not in names:
            raise ValueError(f"{key} has blocks {', '.join(names)}, not {label!r}")
        vocab = routing_vocab(key, label)
        if value not in vocab:
            raise ValueError(f"{key}/{label} takes one of {', '.join(vocab)}, not {value!r}")
        ln.args[names.index(label)] = value
    ln.rebuild()
    return list(blocks)


def set_routswitch(scene: Scene, mode: str) -> None:
    """``/config/routing REC|PLAY``: which input bank set is live."""
    if mode not in ("REC", "PLAY"):
        raise ValueError(f"routing switch is REC or PLAY, not {mode!r}")
    ln = scene.get("/config/routing")
    if ln is None:
        raise KeyError("no /config/routing")
    ln.args = [mode]
    ln.rebuild()


def encode_input_source(text: str | int) -> int:
    """An input source number from ``"AES50-A 3"``, ``"local 5"``, ``"card 7"``, ``"aux 2"``,
    ``"off"`` or a bare number (0-168)."""
    if isinstance(text, bool):   # bool passes isinstance(int): false would read as "no input"
        raise ValueError(f"input source must be a name or a number, got {text!r}")
    if isinstance(text, int) or str(text).strip().isdigit():
        n = int(text)
        if not 0 <= n <= 168:
            raise ValueError(f"input source number must be 0-168, got {n}")
        return n
    words = str(text).strip().lower().split()
    if words == ["off"]:
        return 0
    if len(words) < 2 or not words[-1].isdigit():
        raise ValueError(f"input source: '<kind> <n>' with kind local/aes50-a/aes50-b/card/aux,"
                         f" or a number; got {text!r}")
    kind, n = " ".join(words[:-1]), int(words[-1])
    base = _SOURCE_KINDS.get(kind)
    if base is None:
        raise ValueError(f"unknown input kind {kind!r}; use local, aes50-a, aes50-b, card or aux")
    hi = next(h - lo + 1 for lo, h, _ in SOURCE_DOMAINS if lo == base)
    if not 1 <= n <= hi:
        raise ValueError(f"{kind} inputs run 1-{hi}, got {n}")
    return base + n - 1


def set_input(scene: Scene, ch: int, source: str | int) -> str:
    """Point a channel at an input source; returns the decoded name."""
    cfg = scene.get(f"/ch/{ch:02d}/config")
    if cfg is None or len(cfg.args) < 4:
        raise KeyError(f"no /ch/{ch:02d}/config")
    num = encode_input_source(source)
    cfg.args[-1] = str(num)
    cfg.rebuild()
    return decode_source(num)


_TAP_BY_NAME = {decode_tap(i).lower(): i for i in range(77)}


def encode_tap(text: str | int) -> int:
    """An output source number from its name (``"Bus 9"``, ``"Main L"``, ``"Matrix 2"``,
    ``"Direct Out Ch 5"``, ``"off"``) or a bare number (0-76)."""
    if isinstance(text, bool):   # bool passes isinstance(int): false would unpatch the output
        raise ValueError(f"output source must be a name or a number, got {text!r}")
    if isinstance(text, int) or str(text).strip().isdigit():
        n = int(text)
        if not 0 <= n <= 76:
            raise ValueError(f"output source number must be 0-76, got {n}")
        return n
    key = " ".join(str(text).lower().split())
    if key in _TAP_BY_NAME:
        return _TAP_BY_NAME[key]
    raise ValueError(f"unknown output source {text!r}; `x32scene vocab taps` lists them")


def set_output(scene: Scene, bank: str, n: int, *, src: str | int | None = None,
               pos: str | None = None, invert: bool | None = None) -> str:
    """Set an output's source, tap point and polarity; returns the resulting line's fields
    in words."""
    if bank not in OUTPUT_BANKS:
        raise ValueError(f"bank must be one of {', '.join(OUTPUT_BANKS)}, got {bank!r}")
    size, nfields = OUTPUT_BANKS[bank]
    if not 1 <= n <= size:
        raise ValueError(f"{bank} outputs run 1-{size}, got {n}")
    ln = scene.get(f"/outputs/{bank}/{n:02d}")
    if ln is None or len(ln.args) < nfields:
        raise KeyError(f"no /outputs/{bank}/{n:02d}")
    if src is not None:
        ln.args[0] = str(encode_tap(src))
    if pos is not None:
        if pos not in OUTPUT_POS:
            raise ValueError(f"tap point must be one of {', '.join(OUTPUT_POS)}, got {pos!r}")
        ln.args[1] = pos
    if invert is not None:
        if nfields < 3:
            raise ValueError(f"{bank} outputs carry no polarity field")
        ln.args[2] = "ON" if invert else "OFF"
    ln.rebuild()
    words = f"{decode_tap(int(ln.args[0]))} {ln.args[1]}"
    return words + (f" invert {ln.args[2].lower()}" if nfields >= 3 else "")


def extract_routing(scene: Scene, name: str) -> str:
    """The input routing banks as a routing preset (`.rou`), the shape the console's
    library exports."""
    check_token(f'"{name}"')
    lines = [f'#4.0# 1 "{name}" 2 %0000000000000000 1'.ljust(HEADER_WIDTH)]
    for key in ROUTING_PRESET_KEYS:
        ln = scene.get(f"/config/routing/{key}")
        if ln is None:
            raise KeyError(f"no /config/routing/{key}")
        lines.append(ln.raw)
    return "\n".join(lines) + "\n"


def apply_routing(scene: Scene, text: str, banks: list[str] | None = None) -> list[str]:
    """Load a routing preset's banks into the scene (all it carries, or just ``banks``);
    returns the keys applied."""
    body = {ln.path: ln for ln in Scene.parse(text).lines
            if ln.path.startswith("/config/routing/") and ln.path.count("/") == 3}
    if not body:
        raise ValueError("not a routing preset: no /config/routing/<bank> lines")
    applied = []
    for path, src in body.items():
        key = path.rsplit("/", 1)[1]
        if banks is not None and key not in banks:
            continue
        dst = scene.get(path)
        if dst is None:
            raise KeyError(f"scene has no {path}")
        names = routing_block_names(key)
        for label, value in zip(names, src.args, strict=False):
            if value not in routing_vocab(key, label):
                raise ValueError(f"{key}/{label}: {value!r} is not in the console's vocabulary")
        dst.args = list(src.args)
        dst.rebuild()
        applied.append(key)
    return applied


def routing_line_words(scene: Scene, key: str) -> list[tuple[str, str]]:
    """(block label, token) pairs for one routing line — the view's raw material."""
    ln = scene.get(f"/config/routing/{key}")
    args = ln.args if ln else []
    return list(zip(routing_block_names(key), args, strict=False))

