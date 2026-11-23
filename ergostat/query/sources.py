"""The five sources a query reads. Each returns its groups' rows in the window: ``Rows`` (things that happened, to be
aggregated in their buckets) or ``Levels`` (one value per bucket already). Only ``events`` reads the event log."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..spec import items as its
from ..spec import numberreads
from . import labels
from .buckets import Grid, aggregate
from .parse import Query

EVENTS_MOST = 20_000        # events one query may read from the log
READINGS_MOST = 20_000      # a series' readings read for a percentile
ANY = "all"
OHLC_SOURCES = ("items", "series", "moves")   # what has values in time; a level or a count of events has no open and close


class Unanswerable(Exception):
    """This query cannot be answered from this record: its result says why."""


@dataclass
class Read:
    rows: dict[str, list[tuple]] | None = None    # group: [(time, value, amount)], value for last/avg/..., amount for sum
    levels: dict[str, list] | None = None         # group: one value per bucket
    order: list[str] = field(default_factory=list)   # groups in their natural order (a kind's states), when they have one
    unit: str = ""
    before: float | None = None                   # a series' last reading ahead of the window
    truncated: bool = False
    read_log: bool = False
    note: str | None = None


def kinds(spec, q: Query) -> list:
    """The kinds a query is over: the one it names, or all."""
    every = its.kinds_of(spec)
    if q.kind is None:
        return list(every.values())
    if q.kind not in every:
        raise Unanswerable(f"kind {q.kind!r} is not in the model")
    return [every[q.kind]]


def _index(p, spec, k, fields=()):
    ix = its._index(p.events, spec, its.asks_transcript([k], tuple(fields)))
    if ix is None:
        raise Unanswerable("this record has no item index")
    return ix


def _all(ix, sql: str, args: tuple) -> list:
    """A read of the index, under its lock."""
    return ix.guard(lambda: ix.db.execute(sql, args).fetchall())


def _named(q: Query) -> tuple:
    return tuple(n for n, _ in q.where) + ((q.group_by,) if q.group_by not in (None, "state", "kind") else ())


def items(p, spec, q: Query, g: Grid) -> Read:
    out: dict[str, list] = {}
    states: list[str] = []
    found = False
    for k in kinds(spec, q):
        ix = _index(p, spec, k, (q.field, *_named(q)))
        found = found or any(f["field"] == q.field for f in numberreads.fields_of(ix).get(k.name, ()))
        rows = numberreads.changes(ix, k.name, q.field, g.since, g.until)
        if not rows:
            continue
        ok = labels.allowed(ix, k.name, q.where)
        label = labels.labeller(ix, k.name, q.group_by) if q.group_by else None
        states += [s for s in k.states if s not in states]
        for t, rid, v, d in rows:
            if ok is None or ok(rid):
                out.setdefault(label(rid) if label else q.field, []).append((t, v, d))
    if not found:
        raise Unanswerable(f"field {q.field!r} is not a numeric field of {q.kind or 'any kind'}")
    return Read(rows=out, order=states if q.group_by == "state" else [], unit=_field_unit(q))


def _field_unit(q: Query) -> str:
    from ..spec.itemnumbers import unit_of
    return "items" if q.agg == "count" else unit_of(q.field)


def _state_ids(ix, k, q: Query, moved: set) -> list[int]:
    names = [s for s in q.state if s in moved] if q.state else sorted(x for x in moved if x)
    return [x for x in (ix.known(s) for s in names) if x != -1]


def _moves_of(ix, k, q: Query, g: Grid) -> list[tuple]:
    """(time, rid, state, value) of the query's moves."""
    kn = ix.known(k.name)
    if kn == -1:
        return []
    col = "dst" if q.measure == "entries" else "frm"
    ids = _state_ids(ix, k, q, ix.reached(k.name) if q.measure == "entries" else ix.left(k.name))
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    if q.measure == "time_in_state":
        sql = (f"select m.t, m.rid, m.frm, m.t - (select max(x.t) from moves x where x.rid = m.rid and x.dst = m.frm and x.t <= m.t) "
               f"from moves m where m.kind = ? and m.frm in ({marks}) and m.t >= ? and m.t <= ? order by m.t")
    else:
        sql = f"select t, rid, {col}, 1.0 from moves where kind = ? and {col} in ({marks}) and t >= ? and t <= ? order by t"
    return _all(ix, sql, (kn, *ids, g.since, g.until))


def moves(p, spec, q: Query, g: Grid) -> Read:
    out: dict[str, list] = {}
    order: list[str] = []
    for k in kinds(spec, q):
        if q.state and not q.kind and not set(q.state) & set(k.states):
            continue
        if q.kind and q.state and (bad := [s for s in q.state if s not in k.states]):
            raise Unanswerable(f"state {bad[0]!r} is not a state of {k.name}")
        ix = _index(p, spec, k, _named(q))
        rows = _moves_of(ix, k, q, g)
        ok = labels.allowed(ix, k.name, tuple(x for x in q.where))
        label = None if q.group_by in (None, "state") else labels.labeller(ix, k.name, q.group_by)
        order += [s for s in k.states if s not in order]
        for t, rid, st, v in rows:
            if v is None or (ok is not None and not ok(rid)):
                continue
            name = ix.name(st) if q.group_by == "state" else label(rid) if label else q.measure
            out.setdefault(name, []).append((t, v, v))
    return Read(rows=out, order=order if q.group_by == "state" else [],
                unit="seconds" if q.measure == "time_in_state" else "items")


def _level_key(ix, k, q: Query, by: str):
    """(rid, state id) -> the group a move counts toward."""
    if by == "state":
        return lambda _rid, st: ix.name(st)
    label = labels.labeller(ix, k.name, by)
    return lambda rid, _st: label(rid)


def counts(p, spec, q: Query, g: Grid) -> Read:
    by = q.group_by or "state"
    if q.measure:
        raise Unanswerable("counts takes no measure")
    wanted = set(q.state) if q.state else None
    diffs: dict[str, list[int]] = {}
    base: dict[str, int] = {}
    order: list[str] = []
    for k in kinds(spec, q):
        if q.kind and wanted and (bad := sorted(wanted - set(k.states))):
            raise Unanswerable(f"state {bad[0]!r} is not a state of {k.name}")
        ix = _index(p, spec, k, tuple(n for n, _ in q.where) + ((by,) if by not in ("state", "kind") else ()))
        kn = ix.known(k.name)
        if kn == -1:
            continue
        order += [s for s in k.states if s not in order]
        ok = labels.allowed(ix, k.name, q.where)
        key = _level_key(ix, k, q, by)
        names = {r: ix.name(r) for (r,) in _all(ix, "select distinct dst from moves where kind = ?", (kn,)) if r is not None}
        keep = {st for st, n in names.items() if wanted is None or n in wanted}
        for rid, frm, dst in _all(ix, "select rid, frm, dst from moves where kind = ? and t < ?", (kn, g.since)):
            if ok is None or ok(rid):
                for st, sign in ((dst, 1), (frm, -1)):
                    if st in keep:
                        name = key(rid, st)
                        base[name] = base.get(name, 0) + sign
        for t, rid, frm, dst in _all(ix, "select t, rid, frm, dst from moves where kind = ? and t >= ? and t <= ? order by t",
                                    (kn, g.since, g.until)):
            if ok is None or ok(rid):
                for st, sign in ((dst, 1), (frm, -1)):
                    if st in keep:
                        diffs.setdefault(key(rid, st), [0] * g.n)[g.at(t)] += sign
    levels: dict[str, list] = {}
    for name in base.keys() | diffs.keys():
        level, row = base.get(name, 0), []
        d = diffs.get(name) or [0] * g.n
        for i in range(g.n):
            level += d[i]
            row.append(float(level))
        if any(row):
            levels[name] = row
    note = None if q.agg == "last" else "counts are the level at each bucket's end: the aggregation does not apply"
    return Read(levels=levels, order=order if by == "state" else [], unit="items", note=note)


def series(p, spec, q: Query, g: Grid) -> Read:
    if q.group_by or q.where:
        raise Unanswerable("a series has no groups or filters: its readings carry no labels")
    m = p.measurements
    if m.latest(q.series, g.until) is None and m.latest(q.series) is None:
        raise Unanswerable(f"series {q.series!r} has no readings")
    before = m.latest(q.series, g.since - 1e-6)
    unit = _series_unit(p, q.series)
    if q.agg.startswith("p"):
        rows = [(t, v, v) for t, v in m.sampled(q.series, g.since, g.until, points=READINGS_MOST // 2)]
        return Read(rows={q.series: rows} if rows else {}, unit=unit, before=before and before[1],
                    note="percentiles over rolled-up spans read their buckets' means")
    return Read(levels={q.series: _rolled(m, q, g)}, unit=unit, before=before and before[1])


def _rolled(m, q: Query, g: Grid) -> list:
    row: list = [None] * g.n
    if hasattr(m, "rollups"):
        pick = {"count": 1, "sum": 2, "min": 3, "max": 4, "last": 5}
        for r in m.rollups(q.series, g.since, g.until, g.start, g.step, g.n):
            row[r[0]] = r[2] / r[1] if q.agg == "avg" else float(r[pick[q.agg]])
        return row
    if q.agg not in ("avg", "last"):
        raise Unanswerable(f"this metrics store answers avg and last for a series, not {q.agg}")
    for b, mean, _, last in m.bucketed(q.series, g.start, g.start + g.n * g.step, g.n):
        row[b] = mean if q.agg == "avg" else last
    return row


def _series_unit(p, name: str) -> str:
    """The unit the model gives the part a series reads (``sensor/PART.READING``, ``stock.PART``), where it gives one."""
    m = p.model
    tail = name.split("/", 1)[-1]
    kind, _, rest = tail.partition(".")
    named = {"stock": m.stocks, "flow": m.flows, "auxiliary": getattr(m, "auxiliaries", None) or {}}
    if kind in named and rest:
        return getattr(named[kind].get(rest), "unit", "") or ""
    return next((x.unit for parts in named.values() if (x := parts.get(kind)) is not None and x.unit), "")


def events(p, spec, q: Query, g: Grid) -> Read:
    if q.group_by not in (None, "type") or q.where:
        raise Unanswerable("events are counted by type only: group_by may be type, and there are no filters")
    skip = () if q.type else (its.TRANSCRIPT_TYPES,)
    got = p.events.query(n=EVENTS_MOST + 1, type=q.type, since=g.since, until=g.until, skip=skip)
    cut = len(got) > EVENTS_MOST
    out: dict[str, list] = {}
    for e in got[-EVENTS_MOST:]:
        out.setdefault(e["type"] if q.group_by else (q.type or ANY), []).append((e["time"], 1.0, 1.0))
    note = f"only the latest {EVENTS_MOST} events in the window were read" if cut else None
    return Read(rows=out, unit="events", truncated=cut, read_log=True, note=note)


READERS = {"items": items, "moves": moves, "counts": counts, "series": series, "events": events}


def bucketed(rows: list[tuple], agg: str, g: Grid) -> list:
    """One value per bucket from rows of (time, value, amount): ``sum`` adds the amounts, the rest read the values."""
    cells: list[list] = [[] for _ in range(g.n)]
    for t, v, amount in rows:
        x = amount if agg == "sum" else v
        if x is not None:
            cells[g.at(t)].append(x)
    return [aggregate(agg, c) for c in cells]
