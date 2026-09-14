"""Routing edits: the input/output routing banks, a channel's source, an output's source
and tap, a card record track's source, and routing presets (`.rou`) out and in.
``routing.py`` is the read side."""

from __future__ import annotations

from ..model import HEADER_WIDTH, Scene, check_token
from ..tables import (
    OUTPUT_BANKS, OUTPUT_POS, ROUTING_BLOCKS, SOURCE_DOMAINS, decode_out_source, decode_source,
    decode_tap, routing_block_names, routing_vocab,
)
from .routing import record_map, user_out_readers

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
        ln.require(names.index(label) + 1)
        ln.args[names.index(label)] = value
    ln.rebuild()
    return list(blocks)


def set_routswitch(scene: Scene, mode: str) -> str:
    """``/config/routing REC|PLAY``, in either case: which input bank set is live. Returns
    the spelling written."""
    if mode.upper() not in ("REC", "PLAY"):
        raise ValueError(f"routing switch is REC or PLAY, not {mode!r}")
    ln = scene.get("/config/routing")
    if ln is None:
        raise KeyError("no /config/routing")
    ln.args = [mode.upper()]
    ln.rebuild()
    return ln.args[0]


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
    if cfg is None:
        raise KeyError(f"no /ch/{ch:02d}/config")
    cfg.require(4)
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
    if ln is None:
        raise KeyError(f"no /outputs/{bank}/{n:02d}")
    ln.require(nfields)
    if src is not None:
        ln.args[0] = str(encode_tap(src))
    if pos is not None:
        if pos.upper() not in OUTPUT_POS:
            raise ValueError(f"tap point must be one of {', '.join(OUTPUT_POS)}, got {pos!r}")
        ln.args[1] = pos.upper()
    if invert is not None:
        if nfields < 3:
            raise ValueError(f"{bank} outputs carry no polarity field")
        ln.args[2] = "ON" if invert else "OFF"
    ln.rebuild()
    words = f"{decode_tap(int(ln.args[0]))} {ln.args[1]}"
    return words + (f" invert {ln.args[2].lower()}" if nfields >= 3 else "")


_OUT_SOURCE_BY_NAME = {decode_out_source(n).lower(): n for n in range(209)}
_OUT_KINDS = {"output": (169, 16), "out": (169, 16), "p16": (185, 16), "aux out": (201, 6)}


def encode_out_source(text: str | int) -> int:
    """A user-out source number (0-208) from the words ``record-map`` prints
    (``"Output 9"``, ``"P16 5"``, ``"Aux Out 2"``, ``"Monitor L"``), the words
    ``encode_input_source`` takes, or a bare number."""
    if isinstance(text, bool):
        raise ValueError(f"user-out source must be a name or a number, got {text!r}")
    if isinstance(text, int) or str(text).strip().isdigit():
        n = int(text)
        if not 0 <= n <= 208:
            raise ValueError(f"user-out source number must be 0-208, got {n}")
        return n
    key = " ".join(str(text).lower().split())
    if key in _OUT_SOURCE_BY_NAME:
        return _OUT_SOURCE_BY_NAME[key]
    kind, _, num = key.rpartition(" ")
    if kind in _OUT_KINDS and num.isdigit():
        base, size = _OUT_KINDS[kind]
        if not 1 <= int(num) <= size:
            raise ValueError(f"{kind} sources run 1-{size}, got {num}")
        return base + int(num) - 1
    if kind in _SOURCE_KINDS and num.isdigit():
        return encode_input_source(key)
    raise ValueError(f"unknown user-out source {text!r}; use the words `record-map` prints "
                     "(Local input 5, Card 7, Output 9, P16 5, Aux Out 2, Monitor L), "
                     "local/aes50-a/aes50-b/card/aux N, or 0-208")


def record_slot(scene: Scene, track: int) -> int:
    """The user-out slot (1-48) card record track ``track`` (1-32) reads through its
    ``/config/routing/CARD`` block; a block that is not UOUT has no slot and is refused."""
    if isinstance(track, bool) or not isinstance(track, int) or not 1 <= track <= 32:
        raise ValueError(f"record track must be 1-32, got {track!r}")
    card = scene.get("/config/routing/CARD")
    if card is None:
        raise KeyError("no /config/routing/CARD")
    b = (track - 1) // 8
    card.require(b + 1)
    tok, label = card.args[b], routing_block_names("CARD")[b]
    if tok.rstrip("0123456789-") != "UOUT":
        raise ValueError(f"track {track}: CARD block {label} is {tok}, not a UOUT block, so no "
                         f"user-out slot feeds it; set-routing CARD {label}=UOUT… re-patches it")
    return int(tok[4:].split("-")[0]) + (track - 1) % 8


def set_record(scene: Scene, track: int, source: str | int) -> str:
    """Point card record track ``track`` at ``source`` by writing the user-out slot its UOUT
    block reads; returns the source in the words ``record-map`` prints."""
    num = encode_out_source(source)
    slot = record_slot(scene, track)
    ln = scene.get("/config/userrout/out")
    if ln is None:
        raise KeyError("no /config/userrout/out")
    ln.set_arg(slot - 1, str(num))
    return decode_out_source(num)


def record_row(scene: Scene, track: int, before: str) -> dict:
    """Card record track ``track`` once written: its source ``before`` and after, its user-out
    slot, and every other destination that slot feeds (``user_out_readers``)."""
    slot = record_slot(scene, track)
    return {"track": track, "before": before, "after": dict(record_map(scene))[track],
            "slot": slot, "also_feeds": [r for r in user_out_readers(scene, slot)
                                         if r != f"CARD track {track}"]}


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

