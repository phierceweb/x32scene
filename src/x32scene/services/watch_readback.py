"""A watch's ``/node`` read-backs: how long to wait for a reply, learned from the replies as
TCP learns its retransmission timeout (RFC 6298), and which read-back a reply answers."""

from __future__ import annotations

from collections.abc import Iterable

CAP = 4        # in floors: holds the end read-back to 8 --timeouts; a slower desk wants a larger one
MARGIN = 0.25  # of the floor: the least the timer sits above SRTT (RFC 6298's G)
LATE = 6       # round-trip estimates after which a read-back's reply is taken as lost


class RoundTrip:
    """``estimate`` is SRTT + max(G, 4·RTTVAR) over clean samples; ``rto``, the retry
    interval, is the estimate doubled by each timeout until the next clean sample. Both stay
    within [floor, CAP·floor] and start at ``floor``. A sample is clean only when one query
    was out (Karn): a reply to a retried or overlapping exchange could answer either query."""

    def __init__(self, floor: float):
        self.floor = floor
        self.srtt: float | None = None
        self.rttvar = 0.0
        self.estimate = self.rto = floor

    def sample(self, rtt: float) -> None:
        if self.srtt is None:
            self.srtt, self.rttvar = rtt, rtt / 2
        else:
            self.rttvar = 0.75 * self.rttvar + 0.25 * abs(self.srtt - rtt)
            self.srtt = 0.875 * self.srtt + 0.125 * rtt
        spread = max(MARGIN * self.floor, 4 * self.rttvar)
        self.estimate = self.rto = self._bound(self.srtt + spread)

    def timed_out(self, rto: float) -> None:
        """A query sent with timer ``rto`` went unanswered. Queries that time out together
        back the timer off once, not once each."""
        self.rto = max(self.rto, self._bound(2 * rto))

    def seed(self, round_trips: Iterable[float | None]) -> None:
        """Replay a start pull's replies in order: a round trip, or None for a reply that
        came after its path was asked again, at a timer of ``floor``."""
        for rtt in round_trips:
            if rtt is None:
                self.timed_out(self.floor)
            else:
                self.sample(rtt)

    def _bound(self, t: float) -> float:
        return min(max(t, self.floor), CAP * self.floor)


class Readbacks:
    """The read-backs still out per node, each tagged with the node's leaf count when sent.
    A reply names no query, so it settles a line only when every read-back it could answer
    carries one count, and none sent before a differing settle is still out; otherwise it
    is held until each read-back out has had its one reply or has lapsed."""

    def __init__(self, timer: RoundTrip):
        self._timer = timer
        self._out: dict[str, list[tuple[float, int, float]]] = {}  # node -> (sent, seq, estimate)
        self._heard: dict[str, int] = {}     # node -> replies held, less read-backs lapsed since
        self._settled: dict[str, float] = {}  # node -> when a reply settled it with some still out

    def sent(self, node: str, now: float, seq: int) -> None:
        self._outstanding(node, now).append((now, seq, self._timer.estimate))

    def credit(self, node: str, line: str, known: str, now: float) -> tuple[bool, float | None]:
        """Whether a reply carrying ``line`` settles ``node`` (last settled as ``known``), and
        when to ask again if it is held. Neither for a reply nothing asked for."""
        out = self._outstanding(node, now)
        if not out:
            return False, None
        settled = self._settled.get(node)
        disputed = (settled is not None and line != known
                    and any(q[0] < settled for q in out))
        if len({q[1] for q in out}) > 1 or disputed:
            self._heard[node] = self._heard.get(node, 0) + 1
            # a re-ask while one is still out would start the ambiguity over
            return False, now if self._all_heard(node, out) else max(map(self._lapse, out))
        if len(out) == 1:
            self._timer.sample(now - out[0][0])
        out.remove(min(out))   # the oldest, so what stays outstanding lapses last
        self._all_heard(node, out)
        if out:
            self._settled[node] = now
        else:
            self._settled.pop(node, None)
        return True, None

    def _outstanding(self, node: str, now: float) -> list[tuple[float, int, float]]:
        out = self._out.get(node, [])
        kept = self._out[node] = [q for q in out if now < self._lapse(q)]
        # a lapsed read-back may be one a held reply answered, so the count cannot overstate
        heard = self._heard.pop(node, 0) - (len(out) - len(kept))
        if kept and heard > 0:
            self._heard[node] = heard
        return kept

    def _lapse(self, query: tuple[float, int, float]) -> float:
        """When a read-back's reply is taken as lost; a longer round trip learned since it
        was sent extends it."""
        sent, _, estimate = query
        return sent + LATE * max(estimate, self._timer.estimate)

    def _all_heard(self, node: str, out: list) -> bool:
        """Every read-back out has had its one reply, so nothing still out can answer."""
        if not out or self._heard.get(node, 0) < len(out):
            return False
        out.clear()
        self._heard.pop(node, None)
        self._settled.pop(node, None)
        return True
