"""The ``iem_copy`` and ``iem_sends`` sections of a band-swap plan."""

from __future__ import annotations

from ..model import Scene
from ..services import iem as I
from ..services import transforms as T
from ..tables import SEND_STRIPS
from ._schema import _send_strip


def send_targets(scene: Scene, plan: dict) -> dict[tuple[str, int], tuple[dict, tuple]]:
    """Every send line the plan's ``iem_sends`` write, mapped to ``(set_iem_send kwargs,
    the target the record itself named)``.

    ``apply_sends`` and ``allowed_sends`` both expand through this, so the write set and
    the whitelist cannot drift. They agree on link state because no plan key writes
    /config/chlink or /config/buslink.
    """
    targets: dict[tuple[str, int], tuple[dict, tuple]] = {}
    for rec in plan.get("iem_sends", []):
        named = (_send_strip(rec["strip"]), int(rec["bus"]))
        kwargs = {"on": rec.get("on"),
                  "level_db": T.parse_level(rec["level"]) if "level" in rec else None}
        for tgt in I.iem_send_targets(scene, named[0], named[1]):
            if tgt != named and scene.get(f"{tgt[0]}/mix/{tgt[1]:02d}") is None:
                continue   # a mirror the scene lacks is not the plan's problem
            if tgt in targets:
                other = targets[tgt][1]
                raise ValueError(
                    f"iem_sends: {named[0]} -> bus {named[1]} and {other[0]} -> bus "
                    f"{other[1]} both write {tgt[0]} bus {tgt[1]} — a stereo-linked pair "
                    "shares one send, so name only one side of it")
            targets[tgt] = (kwargs, named)
    return targets


def apply_sends(scene: Scene, plan: dict) -> None:
    """``iem_copy``, then ``iem_sends``: a copy replaces the destination send wholesale, so
    a trim only survives by running after it."""
    for cp in plan.get("iem_copy", []):
        I.copy_iem_mix(scene, int(cp["src"]), int(cp["dst"]))
    for (path, bus), (kw, named) in send_targets(scene, plan).items():
        line = scene.get(f"{path}/mix/{bus:02d}")
        if line is None:
            raise KeyError(f"no send {path}->bus{bus}")
        line.require(1)
        # only the send the plan NAMED has to be on: a mirror may sit OFF on its own
        if (path, bus) == named and kw["on"] is None and line.args[0] == "OFF":
            raise ValueError(f"iem_sends: {path} -> bus {bus}: send is OFF, so a level "
                             'alone changes nothing — add "on": true')
        I.set_iem_send(scene, path, bus, **kw)


def allowed_sends(template: Scene, plan: dict) -> set[str]:
    """The send paths :func:`apply_sends` may change: exactly the buses each copy writes (a
    wider grant lets a stray send pass unflagged) and every ``iem_sends`` target."""
    allowed: set[str] = set()
    for cp in plan.get("iem_copy", []):
        for bus in I.copy_iem_dst_buses(template, int(cp["src"]), int(cp["dst"])):
            allowed.update(f"{strip}/mix/{bus:02d}" for strip in SEND_STRIPS)
    allowed.update(f"{path}/mix/{bus:02d}" for path, bus in send_targets(template, plan))
    return allowed


def mirrored_and_named(template: Scene, plan: dict) -> tuple[set[str], set[str]]:
    """``(mirrors, named)``: the send paths the two sections write only because the console
    mirrors a stereo-linked pair, and the ones a record or a copy names itself."""
    mirrors, named = set(), set()
    for (path, bus), (_, rec) in send_targets(template, plan).items():
        (named if (path, bus) == rec else mirrors).add(f"{path}/mix/{bus:02d}")
    for cp in plan.get("iem_copy", []):
        dst = int(cp["dst"])
        for bus in I.copy_iem_dst_buses(template, int(cp["src"]), dst):
            (named if bus == dst else mirrors).update(f"{s}/mix/{bus:02d}" for s in SEND_STRIPS)
    return mirrors, named
