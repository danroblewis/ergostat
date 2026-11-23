"""One request answered: each query read from its source, grouped and capped, aggregated into the grid, transformed,
and kept under the query and the version of the data it read."""

from __future__ import annotations

import logging
import threading
import time
import weakref
from collections import OrderedDict

from . import transforms as tf
from .buckets import Grid, grid
from .parse import RATE_PER, Query, decode, parse
from .sources import READERS, Read, Unanswerable, bucketed, series_grid

MOST_GROUPS = 12
OTHER = "other"
LIVE_EVERY = 5.0            # a window ending now ends on a multiple of this: requests in between share an answer
MOST_CELLS = 400_000        # values kept in the cache, in all
log = logging.getLogger("ergostat")


class Kept:
    """Answers by query and data version, the least recently used dropped past ``MOST_CELLS`` values."""

    def __init__(self):
        self.lock = threading.Lock()
        self.got: OrderedDict = OrderedDict()
        self.cells = 0

    def get(self, key):
        with self.lock:
            v = self.got.get(key)
            if v is not None:
                self.got.move_to_end(key)
            return v

    def put(self, key, value: dict) -> None:
        size = 1 + sum(len(s["values"]) for s in value.get("series", ()))
        with self.lock:
            if key in self.got:
                return
            self.got[key] = (value, size)
            self.cells += size
            while self.cells > MOST_CELLS and len(self.got) > 1:
                _, (_, n) = self.got.popitem(last=False)
                self.cells -= n


_KEPT: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_KEPT_LOCK = threading.Lock()


def _kept(live) -> Kept:
    with _KEPT_LOCK:
        got = _KEPT.get(live)
        if got is None:
            got = _KEPT[live] = Kept()
        return got


def capped(read: Read) -> tuple[dict, int]:
    """At most ``MOST_GROUPS`` groups, the largest, the rest added up as ``other``; and how many were folded in."""
    groups = read.rows if read.rows is not None else read.levels
    if len(groups) <= MOST_GROUPS:
        return groups, 0
    size = (lambda r: len(r)) if read.rows is not None else (lambda r: max((abs(x) for x in r if x is not None), default=0))
    ranked = sorted(groups, key=lambda n: (-size(groups[n]), n))
    keep, rest = ranked[:MOST_GROUPS], ranked[MOST_GROUPS:]
    out = {n: groups[n] for n in keep}
    if read.rows is not None:
        out[OTHER] = sorted((r for n in rest for r in groups[n]), key=lambda r: r[0])
    else:
        cols = zip(*(groups[n] for n in rest), strict=True)
        out[OTHER] = [None if all(x is None for x in c) else sum(x or 0.0 for x in c) for c in cols]
    return out, len(rest)


def _ordered(names, order: list[str]) -> list[str]:
    at = {n: i for i, n in enumerate(order)}
    return sorted(names, key=lambda n: (n == OTHER, at.get(n, len(at)), n))


def _before_record(values: list, g: Grid, first: float | None) -> list:
    """A bucket wholly before the record began holds nothing, not zero."""
    if first is None:
        return [None] * g.n
    return [None if g.start + (i + 1) * g.step <= first else v for i, v in enumerate(values)]


def _transformed(q: Query, read: Read, values: list, g: Grid) -> list:
    """Per second, for a rate: its unit of time is chosen over all the groups."""
    if q.transform == "delta":
        return tf.delta(values)
    if q.transform == "cumulative":
        return tf.cumulative(values)
    if q.transform == "moving_avg":
        return tf.moving_avg(values, q.window)
    if q.transform != "rate":
        return values
    if q.source == "series" and q.agg == "last":
        cut = g.spans[0] < g.step and read.before_t is not None
        return tf.counter_rate(values, g.spans, read.before, g.since - read.before_t if cut else 0.0)
    if q.source == "counts":
        return tf.plain_rate(tf.delta(values), g.spans)
    return tf.plain_rate(values, g.spans)


def _result(q: Query, read: Read, g: Grid, first: float | None) -> dict:
    groups, folded = capped(read)
    zero_fills = read.rows is not None and q.agg in ("count", "sum")
    names = _ordered(groups, read.order)
    if not names and not q.group_by and read.levels is None:
        names, groups = [q.field or q.measure or q.type or q.source], {q.field or q.measure or q.type or q.source: []}
    out = []
    for n in names:
        values = bucketed(groups[n], q.agg, g) if read.rows is not None else list(groups[n])
        if zero_fills:                                # nothing happened in a bucket: a sum of none is 0
            values = [0.0 if v is None else v for v in values]
        if zero_fills or q.source == "counts":
            values = _before_record(values, g, first)
        if read.read_from is not None:                # a bucket not wholly read is unknown, never a zero
            values = [None if g.start + i * g.step < read.read_from else v for i, v in enumerate(values)]
        out.append((n, _transformed(q, read, values, g)))
    unit = read.unit
    if q.transform == "rate":
        per = q.rate_per or tf.per_for([x for _, v in out for x in v])
        scale = RATE_PER[per]
        out = [(n, [None if x is None else x * scale for x in v]) for n, v in out]
        unit = f"{unit}/{tf.SHORT[per]}" if unit else f"/{tf.SHORT[per]}"
    got = {"id": q.id, "times": g.times, "step": g.step, "series": [{"name": n, "values": v} for n, v in out],
           "unit": unit, "capped": folded, "read_log": read.read_log}
    if read.truncated:
        got["truncated"] = True
    if read.note:
        got["note"] = read.note
    return got


def _version(p, q: Query) -> tuple:
    ev = p.events
    if q.source == "series":
        m = p.measurements
        return ("m", m.version()) if hasattr(m, "version") else ("m", None)
    return ("e", ev.generation() if hasattr(ev, "generation") else None, ev.last_seq() if hasattr(ev, "last_seq") else ev.count())


def _one(live, p, q: Query, since: float, until: float, points: int, first: float | None) -> dict:
    g = series_grid(p.measurements, q.series, since, until, points, q.bucket) if q.source == "series" else \
        grid(since, until, points, q.bucket)
    kept = _kept(live)
    key = (q, g.since, g.until, g.step, getattr(live, "mtime", None), _version(p, q))
    if (got := kept.get(key)) is not None:
        return got[0]
    spec = getattr(p.model, "spec", None)
    try:
        got = _result(q, READERS[q.source](p, spec, q, g), g, first)
    except Unanswerable as e:
        return {"id": q.id, "error": f"{q.source}: {e}", "read_log": q.source == "events"}
    except Exception as e:                            # one query's failure is its own: the others still answer
        log.warning("ergostat: query %s (%s) failed: %s", q.id, q.source, e)
        return {"id": q.id, "error": f"{q.source}: could not be read ({type(e).__name__}: {e})",
                "read_log": q.source == "events"}
    kept.put(key, got)
    return got


def answer(live, p, raw: str | None) -> dict:
    """``GET /api/query``: a malformed request raises ``BadQuery``; a query that cannot be answered says so in its result."""
    asked = parse(decode(raw))
    now = time.time()
    until = asked.until if asked.until is not None else now // LIVE_EVERY * LIVE_EVERY
    since = until - asked.since
    first = p.events.first_time()
    return {"now": now, "since": since, "until": until, "step": grid(since, until, asked.points).step,
            "results": [_one(live, p, q, since, until, asked.points, first) for q in asked.queries]}
