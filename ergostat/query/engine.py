"""One request answered: each query read from its source, grouped and capped, aggregated into the grid, transformed,
and kept under the query and the version of the data it read."""

from __future__ import annotations

import logging
import threading
import time
import weakref
from collections import OrderedDict
from dataclasses import replace

from .. import datasources
from . import shaped, sources
from . import transforms as tf
from .buckets import Grid, grid
from .parse import RATE_PER, Query, Refused, SourceQuery, decode, parse
from .sources import READERS, Read, Unanswerable, bucketed, series_grid

MOST_GROUPS = 12
OTHER = "other"
LIVE_EVERY = 5.0            # a window ending now ends on a multiple of this: requests in between share an answer
MOST_CELLS = 400_000        # values kept in the cache, in all
REQUEST_SECONDS = 10.0      # a request stops starting queries after this: what is left answers that it was not read
LOG_READS = 4               # distinct reads of the event log one request may make
LOG_AT_ONCE = 2             # reads of the event log at once, in all: the web server's workers are never all held by them
log = logging.getLogger("ergostat")


def _cells(value: dict) -> int:
    """How many numbers an answer holds, whatever its shape."""
    lists = [*(value.get("frequency") or {}).values(), *(x for s in value.get("series", ()) for x in s.values())]
    return 1 + sum(len(x) for x in lists if isinstance(x, list))


class Kept:
    """Answers by query and data version, the least recently used dropped past ``MOST_CELLS`` values."""

    def __init__(self):
        self.lock = threading.Lock()
        self.got: OrderedDict = OrderedDict()
        self.cells = 0
        self.log_gate = threading.BoundedSemaphore(LOG_AT_ONCE)

    def get(self, key):
        with self.lock:
            v = self.got.get(key)
            if v is not None:
                self.got.move_to_end(key)
            return v

    def put(self, key, value: dict) -> None:
        size = _cells(value)
        with self.lock:
            if key in self.got:
                return
            self.got[key] = (value, size)
            self.cells += size
            while self.cells > MOST_CELLS and len(self.got) > 1:
                _, (_, n) = self.got.popitem(last=False)
                self.cells -= n


class Work:
    """One request's budget: a deadline, and a few reads of the event log, the same read shared by its queries. A read
    that would wait for another is refused at once, so abandoned requests cannot hold the server's workers."""

    def __init__(self, kept: Kept):
        self.deadline = time.monotonic() + REQUEST_SECONDS
        self.gate = kept.log_gate
        self.read: dict = {}

    def late(self) -> bool:
        return time.monotonic() > self.deadline

    def log(self, p, n, type_, since, until, skip) -> list:
        key = (n, type_, since, until, skip)
        if key in self.read:
            return self.read[key]
        if len(self.read) >= LOG_READS:
            raise Unanswerable(f"busy: this request already read the event log {LOG_READS} times; ask for fewer event charts")
        if not self.gate.acquire(blocking=False):
            raise Unanswerable("busy: the event log is being read for other charts; try again shortly")
        try:
            got = self.read[key] = p.events.moments(n=n, type=type_, since=since, until=until, skip=skip)
        finally:
            self.gate.release()
        return got


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


def _read(p, spec, q: Query, g: Grid, work: Work) -> Read:
    if q.source == "events":
        return sources.events(p, spec, q, g, lambda n, ty, a, b, skip: work.log(p, n, ty, a, b, skip))
    return READERS[q.source](p, spec, q, g)


def _one(live, p, q: Query, since: float, until: float, points: int, first: float | None,
         work: Work | None = None) -> dict:
    g = series_grid(p.measurements, q.series, since, until, points, q.bucket) if q.source == "series" else \
        grid(since, until, points, q.bucket)
    kept = _kept(live)
    key = (q, g.since, g.until, g.step, getattr(live, "mtime", None), _version(p, q))
    if (got := kept.get(key)) is not None:
        return got[0]
    work = work or Work(kept)
    if work.late():
        return {"id": q.id, "error": f"{q.source}: busy: this request ran past {REQUEST_SECONDS:g} s; try again",
                "read_log": False}
    spec = getattr(p.model, "spec", None)
    try:
        got = _result(q, _read(p, spec, q, g, work), g, first)
    except Unanswerable as e:
        return {"id": q.id, "error": f"{q.source}: {e}", "read_log": q.source == "events"}
    except Exception as e:                            # one query's failure is its own: the others still answer
        log.warning("ergostat: query %s (%s) failed: %s", q.id, q.source, e)
        return {"id": q.id, "error": f"{q.source}: could not be read ({type(e).__name__}: {e})",
                "read_log": q.source == "events"}
    kept.put(key, got)
    return got


def _resolved(q: Query, by_id: dict[str, Query], refused: set[str]) -> Query:
    """Its X's query, in place of that query's id; the query it names must be a plain one in time."""
    if q.x is None or not isinstance(q.x.query, str):
        ref = q.x.query if q.x is not None else None
    else:
        if q.x.query == q.id:
            raise Unanswerable("its X cannot be itself")
        ref = by_id.get(q.x.query)
        if q.x.query in refused:
            raise Unanswerable(f"its X, query {q.x.query!r}, is itself refused")
        if ref is None:
            raise Unanswerable(f"its X names query {q.x.query!r}, which is not in this request")
        if isinstance(ref, SourceQuery):
            raise Unanswerable(f"its X, query {ref.id!r}, reads a data source; an X is one of ergostat's own queries")
        q = replace(q, x=replace(q.x, query=ref))
    if ref is not None and (ref.x is not None or ref.source == "frequency" or ref.agg == "ohlc"):
        raise Unanswerable(f"its X, query {ref.id!r}, must be a plain query in time")
    return q


def _versions(p, q: Query) -> tuple:
    if q.source == "frequency":
        return () if q.model else (_version(p, q.input), _version(p, q.output))
    return (_version(p, q), _version(p, q.x.query)) if q.x is not None and isinstance(q.x.query, Query) else (_version(p, q),)


def _build(a: shaped.Asking, q: Query, first) -> dict:
    if q.source == "frequency":
        return shaped.response(a, q)
    if q.agg == "ohlc":
        if q.x is not None:
            raise Unanswerable("candles need a time X")
        return shaped.ohlc(a, q, first)
    return {"query": shaped.paired, "field": shaped.by_field, "category": shaped.category, "bins": shaped.binned}[q.x.type](a, q)


def _shaped(live, p, q: Query, by_id: dict, refused: set, since: float, until: float, points: int, first: float | None,
            work: Work) -> dict:
    """A query that is not one value per time bucket: kept like the rest, and failing alone."""
    uses_log = "events" in (q.source, getattr(q.input, "source", None), getattr(q.output, "source", None))
    try:
        q = _resolved(q, by_id, refused)
        uses_log = uses_log or getattr(getattr(q.x, "query", None), "source", None) == "events"
        kept = _kept(live)
        key = ("shaped", q, since, until, points, getattr(live, "mtime", None), _versions(p, q))
        if (got := kept.get(key)) is not None:
            return got[0]
        if work.late():
            raise Unanswerable(f"busy: this request ran past {REQUEST_SECONDS:g} s; try again")
        spec = getattr(p.model, "spec", None)
        a = shaped.Asking(p, spec, since, until, points, lambda sub, n: _one(live, p, sub, since, until, n, first, work),
                          lambda sub, g: _read(p, spec, sub, g, work))
        got = _build(a, q, first)
    except Unanswerable as e:
        return {"id": q.id, "error": f"{q.source}: {e}", "read_log": uses_log}
    except Exception as e:                            # one query's failure is its own: the others still answer
        log.warning("ergostat: query %s (%s) failed: %s", q.id, q.source, e)
        return {"id": q.id, "error": f"{q.source}: could not be read ({type(e).__name__}: {e})", "read_log": uses_log}
    kept.put(key, got)
    return got


def _from_source(p, q: SourceQuery, since: float, until: float, points: int, work: Work) -> dict:
    """A query in a data source's own language, asked of it through the server; never kept, its data having no version."""
    try:
        got = datasources.query(getattr(p.model, "spec", None), q.source, q.text, grid(since, until, points),
                                work.deadline - time.monotonic())
    except datasources.SourceError as e:
        return {"id": q.id, "error": f"{q.source}: {e}", "error_kind": e.kind, "read_log": False}
    except Exception as e:                            # (its type only: the words may hold the source's address)
        log.warning("ergostat: query %s (source %s) failed: %s", q.id, q.source, type(e).__name__)
        return {"id": q.id, "error": f"{q.source}: could not be read ({type(e).__name__})", "read_log": False}
    return {"id": q.id, **got}


def answer(live, p, raw: str | None) -> dict:
    """``GET /api/query``: a malformed request raises ``BadQuery``; a query that is malformed or unanswerable says so in its result."""
    asked = parse(decode(raw))
    now = time.time()
    until = asked.until if asked.until is not None else now // LIVE_EVERY * LIVE_EVERY
    since = until - asked.since
    first = p.events.first_time()
    by_id = {q.id: q for q in asked.queries if isinstance(q, Query | SourceQuery)}
    refused = {q.id for q in asked.queries if isinstance(q, Refused)}
    work = Work(_kept(live))
    plain = lambda q: q.x is None and q.source != "frequency" and q.agg != "ohlc"   # noqa: E731
    return {"now": now, "since": since, "until": until, "step": grid(since, until, asked.points).step,
            "results": [{"id": q.id, "error": q.error, "read_log": False} if isinstance(q, Refused)
                        else _from_source(p, q, since, until, asked.points, work) if isinstance(q, SourceQuery)
                        else _one(live, p, q, since, until, asked.points, first, work) if plain(q)
                        else _shaped(live, p, q, by_id, refused, since, until, asked.points, first, work)
                        for q in asked.queries]}
