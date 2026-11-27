"""The built-in query kinds as query generators (NOTES.md, 2026-11-25, the owner's decision): each writes the dashboard's
or the YAML's shortcut as one query in a data source's own language and asks it of that source, never reading a store
of its own. Item fields, item moves, items per state and events are SQL over the item views (``sql``:
datasources/_itemviews.py); a metric series is PromQL over the readings (``promql``: datasources/promql.py). What
each wrote is returned with what it read (``Read.compiled``: ``[{"source", "text"}]``), and the answer carries it, so
a reader sees it is just SQL or PromQL and can ask the same text of the source itself (``:since`` and ``:until`` are
the panel's window, as there).

Each returns its groups' rows in the window: ``Rows`` (things that happened, to be aggregated in their buckets) or
``Levels`` (one value per bucket already). Grouping and filtering by a label (``state``, ``projection``, a field,
``state_group``) are joins in the SQL (``item_list``, ``item_labels``, ``item_state_groups``)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..spec import items as its
from .buckets import Grid, aggregate, grid
from .labels import STATE_GROUP
from .parse import Query

ANY = "all"
OHLC_SOURCES = ("items", "series", "moves")   # what has values in time; a level or a count of events has no open and close
GENERATED_ROWS = 2_000_000  # rows one generated SQL query may answer (bucketed here, never sent as they are)
SECONDS = 10.0              # what a generated query may take, when the request gives no budget
MINUTE = 60.0               # events are counted per minute (the item index's ``event_counts``)
EPS = 0.001                 # a bucket is [start, end): PromQL's window (t - step, t] is read a millisecond early


class Unanswerable(Exception):
    """This query cannot be answered from this record: its result says why."""


@dataclass
class Read:
    rows: dict[str, list[tuple]] | None = None    # group: [(time, value, amount)], value for last/avg/..., amount for sum
    levels: dict[str, list] | None = None         # group: one value per bucket
    order: list[str] = field(default_factory=list)   # groups in their natural order (a projection's states), when they have one
    unit: str = ""
    before: float | None = None                   # a series' last reading ahead of the window
    before_t: float | None = None                 # ... and when it was
    truncated: bool = False
    read_log: bool = False
    note: str | None = None
    read_from: float | None = None                # only what happened from here on was read: earlier buckets are unknown
    agg: str | None = None                        # the aggregation the rows are read by, when not the query's own
    compiled: list[dict] = field(default_factory=list)   # what was asked: [{"source": "sql" | "promql", "text"}]


def kinds(spec, q: Query) -> list:
    """The projections a query is over: the one it names, or all."""
    every = its.kinds_of(spec)
    if q.kind is None:
        return list(every.values())
    if q.kind not in every:
        raise Unanswerable(f"projection {q.kind!r} is not in the model")
    return [every[q.kind]]


def _index(p, spec, k, fields=()):
    ix = its._index(p.events, spec, its.asks_transcript([k], tuple(fields)))
    if ix is None:
        raise Unanswerable("this record has no item index")
    return ix


def _named(q: Query) -> tuple:
    return tuple(n for n, _ in q.where) + ((q.group_by,) if q.group_by not in (None, "state", "projection") else ())


# ---- writing SQL

def lit(v) -> str:
    """A value as an SQL literal."""
    return "'" + str(v).replace("'", "''") + "'"


def _in(col: str, values) -> str:
    return f"{col} in ({', '.join(lit(v) for v in values)})"


class _Labels:
    """The joins and the expressions that label a row of ``alias`` (its ``id`` and ``projection``) by ``state``, ``projection``,
    ``state_group`` or a field, as the query engine groups and filters by them (query/labels.py): an item with no value
    for one is ``none``."""

    def __init__(self, alias: str):
        self.alias, self.joins, self.made = alias, [], {}

    def __call__(self, name: str) -> str:
        if name == "projection":
            return f"{self.alias}.projection"
        if name in self.made:
            return self.made[name]
        n = len(self.made)
        if name == "state":
            self.joins.append(f"left join item_list s{n} on s{n}.id = {self.alias}.id")
            got = f"coalesce(s{n}.state, 'none')"
        elif name == STATE_GROUP:
            self.joins.append(f"left join item_state_groups s{n} on s{n}.id = {self.alias}.id")
            got = f"coalesce(s{n}.state_group, 'none')"
        else:
            self.joins.append(f"left join item_labels s{n} on s{n}.id = {self.alias}.id and s{n}.label = {lit(name)}")
            got = f"coalesce(s{n}.value, 'none')"
        self.made[name] = got
        return got


def _labelled(base: str, cols: str, q: Query, group: str | None, order: str = "b.at") -> str:
    """``select cols[, the group's label as grp] from (base) b`` with the filter ``q.where`` and the group's label
    joined; ordered by ``order``."""
    lab = _Labels("b")
    conds = [_in(lab(name), vals) for name, vals in q.where]
    grp = f", {lab(group)} as grp" if group else ""
    return (f"select {cols}{grp} from ({base}) b" + "".join(f" {j}" for j in lab.joins)
            + (f" where {' and '.join(conds)}" if conds else "") + (f" order by {order}" if order else ""))


def _kind_cond(q: Query, col: str = "projection") -> list[str]:
    return [f"{col} = {lit(q.kind)}"] if q.kind else []


def _sql(p, spec, text: str, g: Grid, seconds: float, transcript: bool = False) -> list[tuple]:
    """The rows ``text`` answers over the window, asked of the ``sql`` source as any SQL query is."""
    from ..datasources import SourceError, sql
    if seconds <= 0:
        raise Unanswerable("busy: this request has no time left to ask; try again")
    try:
        _, rows = sql.rows(p, spec, text, {"since": g.since, "until": g.until, "step": g.step}, seconds, transcript,
                           GENERATED_ROWS)
    except SourceError as e:
        raise Unanswerable(str(e)) from e
    return rows


def _shown(text: str) -> list[dict]:
    return [{"source": "sql", "text": text}]


# ---- the generators

def items(p, spec, q: Query, g: Grid, seconds: float = SECONDS) -> Read:
    """A numeric field's changes: each one's time, the value it took and by how much it moved (``item_numbers``)."""
    ks = kinds(spec, q)
    conds = [*_kind_cond(q), f"field = {lit(q.field)}", "at >= :since", "at <= :until"]
    base = f"select at, id, projection, value, delta from item_numbers where {' and '.join(conds)}"
    text = _labelled(base, "b.at, b.value, b.delta", q, q.group_by)
    transcript = its.asks_transcript(ks, (q.field, *_named(q)))
    rows = _sql(p, spec, text, g, seconds, transcript)
    if not rows:
        held = f"select count(*) from item_numbers where {' and '.join([*_kind_cond(q), f'field = {lit(q.field)}'])}"
        if not _sql(p, spec, held, g, seconds, transcript)[0][0]:
            raise Unanswerable(f"field {q.field!r} is not a numeric field of {q.kind or 'any projection'}")
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r[3] if q.group_by else q.field, []).append((r[0], r[1], r[2]))
    states = list(dict.fromkeys(s for k in ks for s in k.states))
    return Read(rows=out, order=states if q.group_by == "state" else [], unit=_field_unit(q), compiled=_shown(text))


def _field_unit(q: Query) -> str:
    from ..spec.itemnumbers import unit_of
    return "items" if q.agg == "count" else unit_of(q.field)


def _states(q: Query, col: str) -> str:
    return _in(col, q.state) if q.state else f"{col} is not null"


def _moves_base(q: Query) -> str:
    """``(at, id, projection, st, v)`` of the query's moves: when, the item, its projection, the state and the value."""
    k = _kind_cond(q)
    window = ["at >= :since", "at <= :until"]
    if q.include_open:                  # time in state, of those that left and those still in the state at the end
        left = ("select t.at, t.id, t.projection, t.from_state as st, t.at - (select max(x.at) from transitions x where "
                "x.id = t.id and x.to_state = t.from_state and x.at <= t.at) as v from transitions t where "
                + " and ".join([*_kind_cond(q, "t.projection"), _states(q, "t.from_state"), "t.at >= :since", "t.at <= :until"]))
        now = ("select :until as at, o.id, o.projection, o.to_state as st, :until - o.at as v from (select id, projection, to_state, "
               "max(at) as at from transitions where " + " and ".join([*k, "at <= :until"]) + " group by id) o where "
               + _states(q, "o.to_state"))
        return f"{left} union all {now}"
    if q.first_only:                    # an item's first time in the state: never a return to it
        return ("select first as at, id, projection, to_state as st, 1.0 as v from (select min(at) as first, id, projection, to_state "
                f"from transitions where {' and '.join([*k, _states(q, 'to_state')])} group by id, to_state) "
                "where first >= :since and first <= :until")
    if q.measure == "time_in_state":
        return ("select t.at, t.id, t.projection, t.from_state as st, t.at - (select max(x.at) from transitions x where "
                "x.id = t.id and x.to_state = t.from_state and x.at <= t.at) as v from transitions t where "
                + " and ".join([*_kind_cond(q, "t.projection"), _states(q, "t.from_state"), "t.at >= :since", "t.at <= :until"]))
    col = "to_state" if q.measure == "entries" else "from_state"
    return f"select at, id, projection, {col} as st, 1.0 as v from transitions where {' and '.join([*k, _states(q, col), *window])}"


def moves(p, spec, q: Query, g: Grid, seconds: float = SECONDS) -> Read:
    """Moves into a state (``entries``), out of one (``exits``), or how long items stayed in one (``time_in_state``),
    from ``transitions``."""
    ks = kinds(spec, q)
    if q.kind and q.state and (bad := [s for s in q.state if s not in ks[0].states]):
        raise Unanswerable(f"state {bad[0]!r} is not a state of {q.kind}")
    group = None if q.group_by in (None, "state") else q.group_by
    text = _labelled(_moves_base(q), "b.at, b.v, b.st", q, group)
    rows = _sql(p, spec, text, g, seconds, its.asks_transcript(ks, _named(q)))
    out: dict[str, list] = {}
    for r in rows:
        if r[1] is None:
            continue
        name = r[2] if q.group_by == "state" else r[3] if group else q.measure
        out.setdefault(name, []).append((r[0], r[1], r[1]))
    order = list(dict.fromkeys(s for k in ks for s in k.states))
    return Read(rows=out, order=order if q.group_by == "state" else [],
                unit="seconds" if q.measure == "time_in_state" else "items", compiled=_shown(text))


def counts(p, spec, q: Query, g: Grid, seconds: float = SECONDS) -> Read:
    """How many items are in each state at each bucket's end: the running total of the moves into it (+1) and out of it
    (−1), from ``transitions``; those before the window added up in the SQL."""
    by = q.group_by or "state"
    if q.measure:
        raise Unanswerable("counts takes no measure")
    ks = kinds(spec, q)
    if q.kind and q.state and (bad := sorted(set(q.state) - set(ks[0].states))):
        raise Unanswerable(f"state {bad[0]!r} is not a state of {q.kind}")
    k = _kind_cond(q)
    into = " and ".join([*k, "at <= :until", _states(q, "to_state")])
    out_of = " and ".join([*k, "at <= :until", _states(q, "from_state")])
    base = (f"select at, id, projection, to_state as st, 1 as v from transitions where {into} union all "
            f"select at, id, projection, from_state as st, -1 as v from transitions where {out_of}")
    lab = _Labels("b")
    conds = [_in(lab(name), vals) for name, vals in q.where]
    key = "b.st" if by == "state" else lab(by)
    moved = (f"select b.at as at, {key} as grp, b.v as v from ({base}) b" + "".join(f" {j}" for j in lab.joins)
             + (f" where {' and '.join(conds)}" if conds else ""))
    text = (f"with moved as ({moved}) select null as at, grp, sum(v) from moved where at < :since group by grp "
            "union all select at, grp, v from moved where at >= :since")
    rows = _sql(p, spec, text, g, seconds, its.asks_transcript(ks, tuple(n for n, _ in q.where)
                                                               + ((by,) if by not in ("state", "projection") else ())))
    base_n: dict[str, float] = {}
    diffs: dict[str, list[float]] = {}
    for at, grp, v in rows:
        if at is None:
            base_n[grp] = base_n.get(grp, 0) + v
        else:
            diffs.setdefault(grp, [0] * g.n)[g.at(at)] += v
    levels: dict[str, list] = {}
    for name in base_n.keys() | diffs.keys():
        level, row = base_n.get(name, 0), []
        d = diffs.get(name) or [0] * g.n
        for i in range(g.n):
            level += d[i]
            row.append(float(level))
        if any(row):
            levels[name] = row
    order = list(dict.fromkeys(s for k in ks for s in k.states))
    note = None if q.agg == "last" else "counts are the level at each bucket's end: the aggregation does not apply"
    return Read(levels=levels, order=order if by == "state" else [], unit="items", note=note, compiled=_shown(text))


def item_points(p, spec, q: Query, xf: str, yf: str | None, since: float, until: float, size: str | None = None,
                color: str | None = None, seconds: float = SECONDS) -> tuple[list[tuple], str]:
    """One point per item for an X of a field (or binning one): each item's value of ``xf`` (and ``yf``) at the window's
    end, for the items that changed in the window, with its group's label, its ``size`` and ``color``, latest last:
    ``[(id, t, x, y, size, color, group)]``, and the SQL that read them (over ``item_numbers``)."""
    def held(field: str) -> str:
        return ("select id, projection, max(at) as t, value from item_numbers where "
                + " and ".join([*_kind_cond(q), f"field = {lit(field)}", "at <= :until"]) + " group by id")
    two = bool(yf) and yf != xf
    withs = [f"x as ({held(xf)})", *([f"y as ({held(yf)})"] if two else []), *([f"sz as ({held(size)})"] if size else [])]
    lab = _Labels("b")
    conds = [_in(lab(name), vals) for name, vals in q.where]
    t = "max(b.t, y.t)" if two else "b.t"
    yv = "y.value" if two else "b.value" if yf else "null"
    cols = [f"{t} as t", "b.value as x", f"{yv} as y", "sz.value as size" if size else "null as size",
            f"{lab(color)} as color" if color else "null as color", f"{lab(q.group_by)} as grp" if q.group_by else "null as grp"]
    text = (f"with {', '.join(withs)} select b.id, {', '.join(cols)} from x b"
            + (" join y on y.id = b.id and y.value is not null" if two else "")
            + (" left join sz on sz.id = b.id" if size else "") + "".join(f" {j}" for j in lab.joins)
            + f" where b.value is not null and {t} >= :since" + "".join(f" and {c}" for c in conds) + f" order by {t}, b.id")
    g = Grid(since, until, max(until - since, 1.0), since, 1)
    ks = kinds(spec, q)
    named = (xf, *([yf] if yf else []), *([size] if size else []), *_named(q))
    rows = _sql(p, spec, text, g, seconds, its.asks_transcript(ks, named))
    if not rows:
        for f in (xf, *([yf] if yf else [])):
            have = f"select count(*) from item_numbers where {' and '.join([*_kind_cond(q), f'field = {lit(f)}'])}"
            if not _sql(p, spec, have, g, seconds)[0][0]:
                raise Unanswerable(f"no projection has both numeric fields {xf!r} and {yf!r}" if yf else
                                   f"{xf!r} is not a numeric field of any projection")
    return rows, text


def _types(type_: str) -> str:
    """An events query's ``type``: types joined by commas, each exact or a prefix ending in ``*`` (store._types)."""
    ors = []
    for t in (x.strip() for x in type_.split(",") if x.strip()):
        ors.append("1" if t == "*" else f"type glob {lit(t)}" if t.endswith("*") else f"type = {lit(t)}")
    return "(" + " or ".join(ors or ["1"]) + ")"


def events(p, spec, q: Query, g: Grid, seconds: float = SECONDS) -> Read:
    """How many events of each type happened, counted per minute as the item index folds them (``events``): each
    minute's count is read at the minute's start."""
    if q.group_by not in (None, "type") or q.where:
        raise Unanswerable("events are counted by type only: group_by may be type, and there are no filters")
    conds = [f"at > :since", f"at - {MINUTE:g} <= :until"]
    conds.append(_types(q.type) if q.type else f"type not glob {lit(its.TRANSCRIPT_TYPES)}")
    text = f"select at - {MINUTE:g} as at, type, n from events where {' and '.join(conds)} order by at"
    rows = _sql(p, spec, text, g, seconds, bool(q.type and "claude." in q.type))
    out: dict[str, list] = {}
    for at, ty, n in rows:
        out.setdefault(ty if q.group_by else (q.type or ANY), []).append((max(at, g.since), float(n), float(n)))
    note = (f"events are counted per minute: a bucket of {g.step:g} s holds each minute's count in the bucket the "
            "minute starts in") if g.step < MINUTE else None
    return Read(rows=out, unit="events", note=note, agg="sum" if q.agg == "count" else None, compiled=_shown(text))


def series_grid(m, name: str, since: float, until: float, points: int, asked: float | None) -> Grid:
    """The grid for a series: every reading is kept (VictoriaMetrics), so any step answers it."""
    return grid(since, until, points, asked)


OVER_TIME = {"count": "count_over_time", "sum": "sum_over_time", "avg": "avg_over_time", "min": "min_over_time",
             "max": "max_over_time", "last": "last_over_time"}


def series_promql(q: Query, step: float) -> str:
    """The PromQL a series' buckets are: its readings over each bucket's window (``series`` names it; the server holds
    the query to this project's)."""
    sel = '{series="' + q.series.replace("\\", "\\\\").replace('"', '\\"') + '"}'
    win = f"[{step:g}s]"
    if q.agg.startswith("p"):
        return f"quantile_over_time({float(q.agg[1:]) / 100:g}, {sel}{win})"
    return f"{OVER_TIME[q.agg]}({sel}{win})"


def series(p, spec, q: Query, g: Grid, seconds: float = SECONDS) -> Read:
    """A metric series' readings in each bucket, aggregated by VictoriaMetrics: PromQL, asked of ``promql``."""
    from .. import datasources
    from ..datasources import SourceError, promql
    if q.group_by or q.where:
        raise Unanswerable("a series has no groups or filters: its readings carry no labels")
    m = p.measurements
    if m.latest(q.series, g.until) is None and m.latest(q.series) is None:
        raise Unanswerable(f"series {q.series!r} has no readings")
    before = m.latest(q.series, g.since - 1e-6)
    unit = _series_unit(p, q.series)
    text = series_promql(q, g.step)
    row = _buckets(m, q, text, g, seconds)
    return Read(levels={q.series: row}, unit=unit, before=before and before[1], before_t=before and before[0],
                compiled=[{"source": "promql", "text": text}])


def _buckets(m, q: Query, text: str, g: Grid, seconds: float) -> list:
    """``text`` asked of ``promql`` at each bucket's end (its window the bucket, read a millisecond early so a bucket is
    [start, end)): one value per bucket, None where it has no reading."""
    from .. import datasources
    from ..datasources import SourceError, promql
    if seconds <= 0:
        raise Unanswerable("busy: this request has no time left to ask; try again")
    try:
        src, _ = datasources._source(datasources.PROMQL, m)
        if hasattr(m, "_sync_reads"):
            m._sync_reads()                     # (what this process wrote, sent before it is read)
        w = datasources.Window(g.since, g.until, g.start + g.step - EPS, g.step, g.n, min(seconds, datasources.MOST_SECONDS))
        got = promql.query(src, text, w)
    except SourceError as e:
        raise Unanswerable(f"{e}") from e
    if isinstance(got, dict):
        raise Unanswerable(f"series {q.series!r} answered as a histogram's buckets, not one series")
    row: list = [None] * g.n
    for _, pts in got:                         # (one series under two names, an old and the model's: the first kept)
        for t, v in pts:
            b = min(g.n - 1, max(0, round((t + EPS - g.start) / g.step) - 1))
            if v is not None and row[b] is None:
                row[b] = float(v)
    return row


CANDLE = {"count": "count_over_time", "open": "first_over_time", "high": "max_over_time", "low": "min_over_time",
          "close": "last_over_time"}


def series_candles(p, q: Query, g: Grid, seconds: float = SECONDS) -> tuple[dict[int, list], list[dict]]:
    """A series' candles, each bucket's count, open, high, low and close worked out by VictoriaMetrics (PromQL, one query
    each): ``{bucket: [count, sum, low, high, open time, open, close time, close]}`` as candles.py makes them (the sum
    and times not read), and what was asked."""
    sel = '{series="' + q.series.replace("\\", "\\\\").replace('"', '\\"') + '"}'
    texts = {k: f"{f}({sel}[{g.step:g}s])" for k, f in CANDLE.items()}
    deadline = time.monotonic() + seconds
    got = {k: _buckets(p.measurements, q, t, g, deadline - time.monotonic()) for k, t in texts.items()}
    out = {b: [int(got["count"][b]), None, got["low"][b], got["high"][b], None, got["open"][b], None, got["close"][b]]
           for b in range(g.n) if got["count"][b]}
    return out, [{"source": "promql", "text": t} for t in texts.values()]


def _series_unit(p, name: str) -> str:
    """The unit the model gives the part a series reads (``sensor/PART.READING``, ``stock.PART``), where it gives one."""
    m = p.model
    tail = name.split("/", 1)[-1]
    kind, _, rest = tail.partition(".")
    named = {"stock": m.stocks, "flow": m.flows, "auxiliary": getattr(m, "auxiliaries", None) or {}}
    if kind in named and rest:
        return getattr(named[kind].get(rest), "unit", "") or ""
    return next((x.unit for parts in named.values() if (x := parts.get(kind)) is not None and x.unit), "")


READERS = {"items": items, "moves": moves, "counts": counts, "series": series, "events": events}


def bucketed(rows: list[tuple], agg: str, g: Grid) -> list:
    """One value per bucket from rows of (time, value, amount): ``sum`` adds the amounts, the rest read the values."""
    cells: list[list] = [[] for _ in range(g.n)]
    for t, v, amount in rows:
        x = amount if agg == "sum" else v
        if x is not None:
            cells[g.at(t)].append(x)
    return [aggregate(agg, c) for c in cells]


def deadline_seconds(deadline: float | None) -> float:
    """What is left of a request's budget (``time.monotonic()`` deadline), or the whole of a generated query's."""
    return SECONDS if deadline is None else deadline - time.monotonic()
