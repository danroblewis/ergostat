"""What was measured, on one accounting basis with the model (Sterman ch. 21; Oliva 2003: fit the
model's output to the data through the same aggregation the data went through; Ljung ch. 4, an
output-error predictor includes the measurement's own dynamics).

Each part's record on a grid of equal buckets, and how the record was made, so the replay can be
driven by it and compared with it like with like:

- a **level** (a stock, an auxiliary): its last reading in each bucket, and that reading's time; the
  replay is read at the same moment;
- a **counted** flow (items entering or leaving a state, a valve's openings, a stock's own
  successive changes): the amounts at the times they moved, exactly. The replay is driven by those
  amounts as they happened (so a stock whose flows are all counted replays its own readings), and an
  equation for it is compared with what moved in each bucket, the model's own integral over the
  same bucket on the other side;
- a flow **read** by a sensor as a rate (``run:``, ``query:``, ``manual:``): its readings' mean in
  each bucket, and the window each reading averages over (``averages:``), through which the
  model's rate is passed before it is compared.

The basis never depends on the page's window: a bucket's count is what moved in it."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from .. import series
from ..spec import items as its
from ..spec.ir import Spec

REFERENCE = 24 * 3600.0      # what the fit and the estimates look at: the last day of record, at most
MIN_BUCKET = 10.0            # seconds: a bucket shorter than the sensors' own period says nothing new


@dataclass
class Grid:
    since: float            # epoch seconds
    until: float
    n: int

    @property
    def width(self) -> float:
        return (self.until - self.since) / self.n

    def times(self) -> list[float]:
        return series.times(self.since, self.until, self.n)

    def edges(self) -> list[float]:
        return [self.since + i * self.width for i in range(self.n + 1)]


def reference(p, now: float | None = None, n: int | None = None) -> Grid:
    """The grid the fit and the estimates use, whatever window the page shows: the last day of the
    record (from where it starts, when it is younger), in buckets of at least ten seconds."""
    import time
    until = now if now is not None else time.time()
    oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=None)
    since = max(until - REFERENCE, oldest) if oldest and oldest < until else until - REFERENCE
    span = max(until - since, 1.0)
    want = n or series.POINTS
    return Grid(since, until, max(2, min(want, int(span // MIN_BUCKET))))


@dataclass
class Counted:
    """Amounts at the times they moved, sorted, with their running total for any span's sum."""

    times: list[float]
    total: list[float]          # total[i]: the amounts of the first i

    @classmethod
    def of(cls, moves: list[tuple[float, float]]) -> Counted:
        moves = sorted(moves)
        tot = [0.0]
        for _, a in moves:
            tot.append(tot[-1] + a)
        return cls([t for t, _ in moves], tot)

    def upto(self, t: float) -> float:
        """The amount moved at or before ``t``."""
        return self.total[bisect.bisect_right(self.times, t)]

    def between(self, t0: float, t1: float) -> float:
        """The amount moved after ``t0``, up to and with ``t1``."""
        return self.upto(t1) - self.upto(t0)


@dataclass
class Data:
    """What was measured, on the grid: every stock's and auxiliary's level and every flow's rate per
    hour (never the rate the residual estimates: that is the model's own guess), and how each is known."""

    grid: Grid
    values: dict[str, list[float | None]] = field(default_factory=dict)
    how: dict[str, str] = field(default_factory=dict)
    at: dict[str, list[float | None]] = field(default_factory=dict)       # a level: its reading's time in each bucket
    counted: dict[str, Counted] = field(default_factory=dict)             # a counted flow: what moved, when
    window: dict[str, float] = field(default_factory=dict)                # a read flow: what each reading averages over (s)
    started: dict[str, tuple[float, float]] = field(default_factory=dict)  # a level's first reading: (time, value)

    def first(self, ref: str) -> int | None:
        return next((i for i, v in enumerate(self.values.get(ref) or []) if v is not None), None)

    def last(self, ref: str) -> float | None:
        return next((v for v in reversed(self.values.get(ref) or []) if v is not None), None)

    def recent(self, ref: str, k: int = 3) -> float | None:
        """The mean of the last ``k`` readings: where a projection starts, so one noisy sample does not set it."""
        got = [v for v in (self.values.get(ref) or []) if v is not None][-k:]
        return sum(got) / len(got) if got else None

    def held(self, ref: str) -> list[float | None]:
        """Each bucket's value, the last one before it carried over a bucket with no reading."""
        out, last = [], None
        for v in self.values.get(ref) or []:
            last = v if v is not None else last
            out.append(last)
        return out

    def level_at(self, ref: str, t: float) -> float | None:
        """A level between its readings, by straight lines (held past the last, none before the first)."""
        pts = self._points(ref)
        if not pts:
            return None
        ts = [x for x, _ in pts]
        i = bisect.bisect_right(ts, t)
        if i == 0:
            return None
        if i == len(pts):
            return pts[-1][1]
        (t0, v0), (t1, v1) = pts[i - 1], pts[i]
        return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)

    def _points(self, ref: str) -> list[tuple[float, float]]:
        key = "_pts:" + ref
        got = self.__dict__.get(key)
        if got is None:
            got = [(t, v) for t, v in zip(self.at.get(ref) or [], self.values.get(ref) or [], strict=False)
                   if t is not None and v is not None]
            if ref in self.started and (not got or got[0][0] > self.started[ref][0]):
                got.insert(0, self.started[ref])
            self.__dict__[key] = got
        return got


def _flow_sensors(spec: Spec, name: str) -> list:
    return list(spec.flows[name].sensors.values())


def _item_moves(p, spec: Spec, q: dict, since: float, until: float) -> list[tuple[float, float]] | None:
    if not q or q.get("kind") not in spec.items:
        return None
    key, state = ("to", q["entering"]) if q.get("entering") else ("from", q.get("leaving"))
    where = q.get("where") or {}
    return [(mv["time"], 1.0) for it in its.project(p.events, spec, q["kind"],
                                                   until=until if where else None, fields=tuple(where)) if its.matches(it, where)
            for mv in it.moves if mv[key] == state and since <= mv["time"] <= until]


def _changes(p, spec: Spec, name: str, what: str, since: float, until: float) -> list[tuple[float, float]] | None:
    """A flow measured by its stock's own successive readings: each rise (or fall, or both, in the
    flow's direction) at the reading that showed it."""
    f = spec.flows[name]
    stock = next((s for s in (f.target, f.source) if s and spec.stocks.get(s) and spec.stocks[s].sensors), None)
    if stock is None:
        return None
    sign = 1 if stock == f.target else -1
    raw = sorted(x for s in spec.stocks[stock].sensors.values() for x in p.measurements.range(s.series, since, until))
    out = []
    for (_, a), (t, b) in zip(raw, raw[1:], strict=False):
        d = (b - a) * sign
        if what == "rises":
            d = max(0.0, b - a)
        elif what == "falls":
            d = max(0.0, a - b)
        if d:
            out.append((t, d))
    return out


def measured(p, grid: Grid, spec: Spec | None = None) -> Data:
    """The record on ``grid``, for the model as it is (or ``spec``: a change being tried)."""
    spec = spec or p.model.spec
    d = Data(grid)
    g, w = grid, grid.width
    for name in (*spec.stocks, *spec.auxiliaries):
        kind = "stock" if name in spec.stocks else "auxiliary"
        ref = f"{kind}.{name}"
        vals: list[float | None] = [None] * g.n
        when: list[float | None] = [None] * g.n
        first = None
        for s in spec.measured(kind)[name].sensors.values():
            for b, _mean, t, v in p.measurements.bucketed(s.series, g.since, g.until, g.n):
                if when[b] is None or t >= when[b]:
                    vals[b], when[b] = v, t
            got = p.measurements.first(s.series, g.since, g.until)
            if got and (first is None or got[0] < first[0]):
                first = got
        d.values[ref], d.at[ref], d.how[ref] = vals, when, "measured"
        if first:
            d.started[ref] = first
    valves = {}
    for v in getattr(p.model, "valves", {}).values():
        valves.setdefault(v.flow, []).append(v.name)
    for name, f in spec.flows.items():
        ref = f"flow.{name}"
        sensors = _flow_sensors(spec, name)
        moves, how = None, None
        q = next((s.items for s in sensors if s.items), None)
        ch = next((s.changes for s in sensors if s.changes), None)
        if q:
            moves = _item_moves(p, spec, q, g.since, g.until)
            how = f"items {'entering ' + q['entering'] if q.get('entering') else 'leaving ' + str(q.get('leaving'))}, counted as they moved"
        elif not any(s.run or s.query or s.manual for s in sensors) and valves.get(name):
            moves = [(e["time"], float(e["data"].get("amount", 1) or 0)) for v in valves[name]
                     for e in p.events.query(n=None, type="valve.opened", item=v, since=g.since, until=g.until)]
            how = f"opened by {', '.join(valves[name])}, as it opened"
        elif ch:
            moves = _changes(p, spec, name, ch["what"], g.since, g.until)
            how = "its stock's own changes, as they were read"
        if moves is not None:
            c = d.counted[ref] = Counted.of(moves)
            edges = g.edges()
            d.values[ref] = [c.between(edges[i], edges[i + 1]) * 3600.0 / w for i in range(g.n)]
            d.how[ref] = how
            continue
        read = [s for s in sensors if s.run or s.query or s.manual]
        if read:
            sums, counts = [0.0] * g.n, [0] * g.n
            for s in read:
                for b, mean, _t, _v in p.measurements.bucketed(s.series, g.since, g.until, g.n):
                    sums[b] += mean
                    counts[b] += 1
            if any(counts):
                d.values[ref] = [sums[i] / counts[i] if counts[i] else None for i in range(g.n)]
                d.window[ref] = max(s.window for s in read)
                avg = d.window[ref]
                d.how[ref] = f"measured by {', '.join(s.name for s in read)}" + (f", each reading an average over {series.dur(avg)}"
                                                                               if avg else "")
                continue
        if f.rate is not None:
            d.values[ref], d.how[ref] = [f.rate] * g.n, "declared"
            continue
        d.values[ref], d.how[ref] = [None] * g.n, "not measured"
    return d


def is_counted(data: Data, ref: str) -> bool:
    return ref in data.counted


def from_its_stock(spec: Spec, ref: str) -> bool:
    """A flow measured only by its stock's own changes (``changes:``): its readings are the stock's,
    differenced, so the stock's replay tests its equation, and better."""
    kind, _, name = ref.partition(".")
    f = spec.flows.get(name) if kind == "flow" else None
    return bool(f and f.sensors and all(x.changes for x in f.sensors.values()))
