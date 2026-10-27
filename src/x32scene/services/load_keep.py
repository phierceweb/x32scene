"""What `load --keep-bus` and `--keep` leave as the desk holds it: the paths of a mix or of a
pattern, widened to every line the desk would copy a write onto, and the link lines and
link preferences a file must not rewrite around them."""

from __future__ import annotations

import re
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from ..model import Line, Scene
from ..tables import LINK_LINES, LINKCFG
from .channelfx import link_pref_on, pair_linked
from .routing import channel_headamp_index
from .transplant import bus_mix_paths, glob_paths

_KINDS = {"/config/chlink": "ch", "/config/auxlink": "aux-in", "/config/fxlink": "FX return",
          "/config/buslink": "bus", "/config/mtxlink": "matrix"}
LINKCFG_PATH = "/config/linkcfg"
_STRIP = re.compile(r"^(/(?:ch|auxin|fxrtn|bus|mtx)/\d\d)(?:/(.+))?$")
_SEND = re.compile(r"^(?P<src>/(?:ch|auxin|fxrtn|bus)/\d\d|/main/(?:st|m))/mix/(?P<dest>\d\d)$")
_HEADAMP = re.compile(r"^/headamp/(\d{3})$")
# the /config/linkcfg preference a strip line mirrors under; the sends, the key filters and a
# line not named here mirror whatever the preferences say
_GATE = {"preamp": "hadly", "delay": "hadly", "eq": "eq", "dyn": "dyn", "gate": "dyn",
         "insert": "dyn", "grp": "fdrmute", "mix": "fdrmute"}
_UNGATED = re.compile(r"^(mix/\d\d|(dyn|gate)/filter)$")
_HEADAMP_ROUTING = ("/config/routing", "/config/routing/IN", "/config/routing/PLAY",
                    "/config/userrout/in", *(f"/ch/{c:02d}/config" for c in range(1, 33)))


def _other(n: int) -> int:
    return n + 1 if n % 2 else n - 1


def _headamp(view: Scene, ch: int) -> int | None:
    try:
        return channel_headamp_index(view, ch)
    except ValueError:
        return None


def _token(ln: Line, strip: str) -> str | None:
    i = (int(strip[-2:]) - 1) // 2
    return ln.args[i] if i < len(ln.args) else None


def _pair(strip: str) -> str:
    """``/bus/14`` -> ``bus 13/14``."""
    odd = int(strip[-2:]) - (0 if int(strip[-2:]) % 2 else 1)
    return f"{_KINDS[LINK_LINES[strip[:-3]]]} {odd}/{odd + 1}"


class _Mirror:
    """Where the desk copies a write: across the pairs ``desk`` links, under the link
    preferences and head-amp routing of the desk or of the file written over it, a
    ``kept`` line staying the desk's."""

    def __init__(self, target: Scene, desk: Scene, kept: AbstractSet[str] = frozenset()):
        self.desk = desk
        self.prefs = {p: link_pref_on(desk, p) or link_pref_on(target, p) for p in LINKCFG}
        lines = {ln.path: ln for ln in desk.lines if ln.path}
        lines.update((ln.path, ln) for ln in target.lines
                     if ln.path.startswith("/") and ln.path not in kept)
        self.heads: dict[int, set[tuple[str, str | None]]] = {}
        for view in (desk, Scene(list(lines.values()))):
            for ch in range(1, 33):
                if (i := _headamp(view, ch)) is not None:
                    o = _headamp(view, _other(ch))
                    self.heads.setdefault(i, set()).add(
                        (f"/ch/{ch:02d}", None if o is None else f"/headamp/{o:03d}"))

    def pairs(self, path: str) -> list[tuple[str, str | None, str | None]]:
        """``(strip, the line on its pair's other side, the preference gating the copy)`` per
        pair a write to ``path`` is copied across: its strip's, a send's destination's, and
        for a head amp the channel's it feeds."""
        out: list[tuple[str, str | None, str | None]] = []
        if m := _STRIP.match(path):
            strip, sub = m[1], m[2]
            gate = None if sub is None or _UNGATED.match(sub) else _GATE.get(sub.split("/")[0])
            other = f"{strip[:-2]}{_other(int(strip[-2:])):02d}" + (f"/{sub}" if sub else "")
            out.append((strip, other, gate))
        if m := _SEND.match(path):
            fam, d = ("/mtx" if m["src"].startswith(("/bus", "/main")) else "/bus"), int(m["dest"])
            out.append((f"{fam}/{d:02d}", f"{m['src']}/mix/{_other(d):02d}", None))
        if m := _HEADAMP.match(path):
            out += [(ch, other, "hadly") for ch, other in sorted(
                self.heads.get(int(m[1]), ()), key=lambda t: (t[0], t[1] or ""))]
        return out

    def widen(self, paths: list[str], order: dict[str, int]) -> list[str]:
        seen, todo = set(paths), list(paths)
        while todo:
            for strip, other, gate in self.pairs(todo.pop()):
                if (other and other not in seen and pair_linked(self.desk, strip)
                        and (gate is None or self.prefs[gate])):
                    seen.add(other)
                    todo.append(other)
        return sorted((p for p in seen if p in order), key=order.__getitem__)


@dataclass
class Keep:
    """The mixes (``buses``, 1-16) and path patterns (``globs``) a load leaves alone."""

    buses: list[int] = field(default_factory=list)
    globs: list[str] = field(default_factory=list)

    LINKS = tuple(_KINDS)
    REQUIRED = (*LINKS, LINKCFG_PATH)

    def check(self, target: Scene) -> None:
        """Raise ValueError for a bus outside 1-16 and a pattern no line of ``target`` matches."""
        for bus in self.buses:
            if not 1 <= bus <= 16:
                raise ValueError(f"--keep-bus wants a bus 1-16, got {bus}")
        for g in self.globs:
            if not glob_paths(target, [g]):
                raise ValueError(f"--keep {g!r} matches no line of the file")

    def desk_paths(self, target: Scene) -> list[str]:
        """The desk lines :meth:`resolve` reads beyond the file's own: ``REQUIRED``, and for
        a kept head amp the routing that names its channel."""
        heads = any(_HEADAMP.match(p) for p in glob_paths(target, self.globs))
        return [*self.REQUIRED, *(_HEADAMP_ROUTING if heads else ())]

    def resolve(self, target: Scene, desk: Scene) -> list[tuple[str, list[str]]]:
        """``(what, paths)`` per kept mix and pattern, paths in file order, each widened to
        every line the desk (``desk``, its lines as :meth:`desk_paths` names them) copies a
        write onto. Raises ValueError for a mix the file has no line of, for a link change
        on a pair a kept line belongs to, and for a link preference the load would change
        that decides what a kept line's linked pair shares."""
        # a strip line widens by the desk's links alone, so the first pass settles which
        # config lines are kept and the second models the head amps with them as the desk's
        out, _ = self._widen(target, desk, set(glob_paths(target, self.globs)))
        out, mirror = self._widen(target, desk, {p for _, ps in out for p in ps})
        kept = {p for _, ps in out for p in ps}
        self._refuse(target, desk, mirror, kept)
        self._refuse_prefs(target, desk, mirror, kept)
        return out

    def _widen(self, target: Scene, desk: Scene,
               kept: set[str]) -> tuple[list[tuple[str, list[str]]], _Mirror]:
        mirror = _Mirror(target, desk, kept=kept)
        order = {ln.path: i for i, ln in enumerate(target.lines)}
        out: list[tuple[str, list[str]]] = []
        done: set[tuple[int, ...]] = set()
        for bus in self.buses:
            group = (min(bus, _other(bus)), max(bus, _other(bus))) if pair_linked(
                desk, f"/bus/{bus:02d}") else (bus,)
            if group not in done:
                done.add(group)
                paths = mirror.widen(bus_mix_paths(target, bus, group=group), order)
                if not paths:
                    raise ValueError(f"--keep-bus {bus}: the file has no line of that mix")
                out.append(("bus " + "/".join(map(str, group)), paths))
        for g in self.globs:
            matched = glob_paths(target, [g])
            paths = mirror.widen(matched, order)
            out.append((g if len(paths) == len(matched) else f"{g} and its linked sides", paths))
        return out, mirror

    @staticmethod
    def _refuse(target: Scene, desk: Scene, mirror: _Mirror, kept: set[str]) -> None:
        """A link write rewrites the pair's lines; a token re-sent unchanged moves nothing."""
        for line in _KINDS:
            want, have = target.get(line), desk.get(line)
            if line in kept or want is None:
                continue
            if have is None:
                raise ValueError(f"no {line} from the desk to check the file's against")
            if want.args == have.args:
                continue
            changed = [(s, p) for p in sorted(kept) for s, _, _ in mirror.pairs(p)
                       if LINK_LINES[s[:-3]] == line and _token(want, s) != _token(have, s)]
            if changed:
                strip, hit = changed[0]
                raise ValueError(f"the file changes the {_pair(strip)} link, and a link write "
                                 f"rewrites the pair's lines, kept {hit} among them; keep "
                                 f"{line} too to leave the link as the desk holds it")

    @staticmethod
    def _refuse_prefs(target: Scene, desk: Scene, mirror: _Mirror, kept: set[str]) -> None:
        """Whether changing a preference copies across a pair already linked is unwatched."""
        want, have = target.get(LINKCFG_PATH), desk.get(LINKCFG_PATH)
        if LINKCFG_PATH in kept or want is None:
            return
        if have is None:
            raise ValueError(f"no {LINKCFG_PATH} from the desk to check the file's against")
        changed = {p for p, i in LINKCFG.items() if want.args[i:i + 1] != have.args[i:i + 1]}
        for path in sorted(kept):
            for strip, _, gate in mirror.pairs(path):
                if gate in changed and pair_linked(desk, strip):
                    raise ValueError(
                        f"the file changes the {gate} preference in {LINKCFG_PATH}, which "
                        f"decides what the desk copies across linked {_pair(strip)}, the pair "
                        f"kept {path} belongs to; keep {LINKCFG_PATH} too to leave the "
                        "preferences as the desk holds them")
