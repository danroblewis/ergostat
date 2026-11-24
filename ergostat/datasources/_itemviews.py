"""The views the SQL data source answers from (sql.py; SPEC §4e, *The SQL source*): documented, stable and read only,
over the item index (spec/itemindex.py), whose own tables are never readable.

- ``transitions(id, kind, at, from_state, to_state, event, type)``: every move of every item; an arrival has no
  ``from_state``.
- ``item_fields(id, kind, field, value)``: each item's fields now, one row a top-level field (a list or a map as JSON).
- ``item_spans(id, kind, state, entered, left, entry, reason)``: one row per move of an item into a state: when it
  ``entered``, when it ``left`` (null while it is there: an open item's current span), ``entry`` (1 the first time it is
  in that state, 2 when it came back, ...) and ``reason``: the finished state the item ended in (null while it is open).
- one view per item kind, named for the kind (``-`` read as ``_``; a name that is not then a plain word, or that is one
  of the views above, has none): ``(id, state, first, last, entered, events, <the kind's show: fields>)``.

Times are Unix seconds. Each view names its columns, so a change of the index's own tables (a column or a table added,
the columns in another order, the file built again) leaves what a view answers as it was
(tests/test_sql_source.py). Each query's text is first prepared on an empty stand-in of the index (``check``), where
only SELECT, reads of the views and the text's own ``WITH`` names, and the functions named in FUNCTIONS are allowed
(SQLite's authorizer). Only a text that passed is run, on a connection of its own opened read only, where each view is
a temp view over the index's tables and reads of only those tables are allowed (``opened``). Both are bounded in time
(a progress handler), in each value's size and in memory (tests/test_sql_views.py)."""

from __future__ import annotations

import contextlib
import json
import math
import re
import sqlite3
import time

from .. import stages
from ..spec import codec

STABLE = {
    "transitions": ("id", "kind", "at", "from_state", "to_state", "event", "type"),
    "item_fields": ("id", "kind", "field", "value"),
    "item_spans": ("id", "kind", "state", "entered", "left", "entry", "reason"),
    **stages.COLUMNS,                                   # (made from the items' stages, here: _stage_tables)
}
KIND_COLUMNS = ("id", "state", "first", "last", "entered", "events")
FUNCTIONS = frozenset((
    "abs char coalesce concat concat_ws format glob hex ifnull iif instr length like likely unlikely likelihood lower "
    "ltrim max min nullif octet_length printf quote replace round rtrim sign substr substring trim typeof unicode upper "
    "date time datetime julianday unixepoch strftime timediff "
    "avg count group_concat string_agg sum total "
    "row_number rank dense_rank percent_rank cume_dist ntile lag lead first_value last_value nth_value "
    "acos asin atan atan2 ceil ceiling cos degrees exp floor ln log log10 log2 mod pi pow power radians sin sqrt tan trunc "
    "json json_array json_array_length json_extract json_object json_type json_valid json_quote json_group_array "
    "json_group_object -> ->> "
    "median percentile percentile_cont").split())
MOST_VALUE = 16 * 2**20         # bytes of one string or blob a query may make (SQLITE_LIMIT_LENGTH)
MOST_VALUES = 1_000_000         # numbers one median or percentile may hold
CACHE_KB = 8000                 # SQLite's page cache, for the index and for the query's own temporaries each
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SELECT, _READ, _FUNCTION = sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION
_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def kind_views(spec) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Each kind's view: its name, the kind and the ``show:`` fields that are columns (plain words, not taken)."""
    out = {}
    for name, k in sorted((getattr(spec, "items", None) or {}).items()):
        view = name.replace("-", "_")
        if _WORD.fullmatch(view) and view not in STABLE and view.lower() not in out:
            out[view] = (name, tuple(dict.fromkeys(f for f in k.show if _WORD.fullmatch(f) and f not in KIND_COLUMNS)))
    return out


def views(spec) -> dict[str, tuple[str, ...]]:
    """Every view a query may read, and its columns, in order."""
    return {**STABLE, **{v: (*KIND_COLUMNS, *shown) for v, (_, shown) in kind_views(spec).items()}}


def _definitions(spec, finished: dict[str, list[str]]) -> dict[str, str]:
    """Each view's SELECT over the index's tables, as they are laid out now (spec/itemindex.py, ``SCHEMA``)."""
    names = "left join main.names {a} on {a}.id = {c}"
    ended = " ".join(f"when k.name = {_q(k)} and n.name in ({', '.join(map(_q, fs))}) then n.name"
                     for k, fs in sorted(finished.items()) if fs)
    out = {
        "transitions": "select i.id as id, k.name as kind, m.t as at, f.name as from_state, d.name as to_state, "
        "m.event as event, y.name as type from main.moves m join main.items i on i.rid = m.rid "
        + " ".join(names.format(a=a, c=c) for a, c in (("k", "m.kind"), ("f", "m.frm"), ("d", "m.dst"), ("y", "m.type"))),
        "item_fields": "select i.id as id, k.name as kind, j.key as field, j.value as value "
        f"from main.items i {names.format(a='k', c='i.kind')} join json_each(_fields(i.body)) j",
        "item_spans": "select i.id as id, k.name as kind, d.name as state, s.t as entered, s.nxt as \"left\", "
        f"s.entry as entry, {f'case {ended} end' if ended else 'null'} as reason from (select rid, kind, dst, t, "
        "lead(t) over (partition by rid order by rowid) as nxt, row_number() over (partition by rid, dst order by rowid) "
        "as entry from main.moves) s join main.items i on i.rid = s.rid "
        + " ".join(names.format(a=a, c=c) for a, c in (("k", "s.kind"), ("d", "s.dst"), ("n", "i.state"))),
    }
    for view, (kind, shown) in kind_views(spec).items():
        cols = "".join(f", json_extract(_fields(i.body), '$.{f}') as \"{f}\"" for f in shown)
        out[view] = (f"select i.id as id, n.name as state, i.first as first, i.last as last, i.entered as entered, "
                     f"i.n as events{cols} from main.items i join main.names k on k.id = i.kind and k.name = {_q(kind)} "
                     + names.format(a="n", c="i.state"))
    return out


def _fields(body):
    """An item's fields, as JSON (its document as the index packs it)."""
    return json.dumps(codec.unpack(body)["f"], default=str) if body is not None else "{}"


def _ranked(why: list, scale: float, lo: float, hi: float):
    """An aggregate over a group's numbers, at the fraction ``p * scale`` of the way through them, interpolated
    linearly between the two nearest (as PostgreSQL's ``percentile_cont``); null for no numbers."""
    class Ranked:
        def __init__(self):
            self.xs, self.p = [], None

        def step(self, x, p=0.5 / scale):
            if self.p is None:
                if isinstance(p, bool) or not isinstance(p, int | float) or not lo <= p <= hi:
                    why.append(("refused", f"a percentile is a number from {lo:g} to {hi:g}, not {p!r}"))
                    raise ValueError(p)
                self.p = p
            elif p != self.p:
                why.append(("refused", "a percentile is one number for the whole group"))
                raise ValueError(p)
            if x is None:
                return
            if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x):
                why.append(("refused", f"a median or percentile takes numbers, not {x!r}"))
                raise ValueError(x)
            if len(self.xs) >= MOST_VALUES:
                why.append(("limit", f"a median or percentile holds at most {MOST_VALUES:,} numbers"))
                raise OverflowError(len(self.xs))
            self.xs.append(float(x))

        def finalize(self):
            if not self.xs:
                return None
            xs = sorted(self.xs)
            h = (len(xs) - 1) * self.p * scale
            i = math.floor(h)
            return xs[i] if i + 1 >= len(xs) else xs[i] + (h - i) * (xs[i + 1] - xs[i])
    return Ranked


def _finished(c, spec) -> dict[str, list[str]]:
    """Each kind's finished states (spec/finished.py), from the states its items have left as ``c`` reads them."""
    from ..spec.finished import finish_of
    left: dict[str, set[str]] = {}
    for kind, state in c.execute('select k.name, s.name from main."left" l join main.names k on k.id = l.kind '
                                 "join main.names s on s.id = l.state"):
        left.setdefault(kind, set()).add(state)
    return {k: finish_of(spec, k, left.get(k, set()))["finished"] for k in spec.items}


def stage_rows(c, spec, finished: dict[str, list[str]], now: float) -> list[dict]:
    """The stages of the items of each kind that declares ``pipeline:`` (stages.rows), as ``c`` reads the index."""
    kinds = [k for k, x in spec.items.items() if x.pipeline is not None]
    if not kinds:
        return []
    got = c.execute("select i.id, k.name, n.name, i.body from main.items i join main.names k on k.id = i.kind "
                    f"left join main.names n on n.id = i.state where k.name in ({', '.join('?' * len(kinds))})", kinds)
    return stages.rows(((i, k, s not in finished.get(k, []), codec.unpack(b)["f"] if b is not None else {})
                        for i, k, s, b in got), now)


def stage_metrics(p) -> str:
    """``GET /api/stages/metrics``: the finished stages of each kind declaring ``pipeline:``, as Prometheus histograms
    (stages.exposition), read in one snapshot of the item index; a record kept nowhere on disk raises, never empty."""
    from ..spec.itemindex import index_for
    spec = getattr(p.model, "spec", None)
    declared = {n: k.pipeline["stages"] for n, k in (getattr(spec, "items", None) or {}).items() if k.pipeline}
    if not declared:
        return stages.exposition([], {})
    if (ix := index_for(p.events, spec, False)) is None:
        raise RuntimeError("this project's record is kept nowhere on disk, so its stages cannot be read")
    with ix.reading() as c:
        c.execute("begin")
        rs = stage_rows(c, spec, _finished(c, spec), time.time())
        c.execute("commit")
    return stages.exposition(rs, declared)


def _stage_tables(c, spec, finished: dict[str, list[str]], now: float) -> None:
    rs = stage_rows(c, spec, finished, now)
    est = stages.estimates(rs)
    made = {"item_stages": rs, "item_progress": stages.progress(rs, est, now),
            "stage_estimates": [{"kind": k, "run_kind": rk, "stage": s, "expected": e, "samples": n}
                                for (k, rk, s), (e, n) in sorted(est.items())]}
    for view, cols in stages.COLUMNS.items():
        c.execute(f'create temp table "{view}" ({", ".join(chr(34) + x + chr(34) for x in cols)})')
        c.executemany(f'insert into temp."{view}" values ({", ".join("?" * len(cols))})',
                      [tuple(r[x] for x in cols) for r in made[view]])


def _bounded(c, deadline: float, why: list) -> None:
    """A query's connection's bounds (time, values, memory; no ATTACH) and its aggregates."""
    c.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    for k, v in ((sqlite3.SQLITE_LIMIT_LENGTH, MOST_VALUE), (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
                 (sqlite3.SQLITE_LIMIT_COLUMN, 200), (sqlite3.SQLITE_LIMIT_WORKER_THREADS, 0)):
        c.setlimit(k, v)
    for p in (f"cache_size = -{CACHE_KB}", f"temp.cache_size = -{CACHE_KB}", "temp_store = file", "mmap_size = 0"):
        c.execute(f"pragma {p}")
    c.create_aggregate("median", 1, _ranked(why, 1.0, 0.0, 1.0))
    c.create_aggregate("percentile_cont", 2, _ranked(why, 1.0, 0.0, 1.0))
    c.create_aggregate("percentile", 2, _ranked(why, 0.01, 0.0, 100.0))


def _authorizer(why: list, readable, functions=FUNCTIONS, own: set | None = None):
    """Only SELECT, reads ``readable(db, table)`` allows, and ``functions``; anything else is refused, its words in
    ``why``. A name read for no column (``count(*)``) comes with no database, whether it is a table or a ``WITH`` name:
    it is allowed if it is in ``own``; with no ``own``, it is kept in ``.unsure`` and the ``WITH`` names seen (a
    SELECT inside one) in ``.ctes``, for the caller to judge once the text is prepared."""
    unsure, ctes = set(), set()

    def denied(what: str) -> int:
        why.append(("refused", f"only a SELECT of the views is allowed, and this {what}"))
        return sqlite3.SQLITE_DENY

    def allowed(action, a, b, db, inside):
        if action in (_SELECT, _RECURSIVE):
            ctes.add((inside or "").lower())
            return sqlite3.SQLITE_OK
        if action == _READ and db is None and own is None:
            unsure.add((a or "").lower())
            return sqlite3.SQLITE_OK
        if action == _READ:
            ok = (a or "").lower() in own if db is None else readable(db, (a or "").lower())
            return sqlite3.SQLITE_OK if ok else denied(f"reads {db or 'main'}.{a}")
        if action == _FUNCTION:
            return sqlite3.SQLITE_OK if (b or "").lower() in functions else denied(f"calls {b}")
        return denied(f"is not a SELECT (SQLite's action {action})")
    allowed.unsure, allowed.ctes = unsure, ctes
    return allowed


def _prepared(deadline: float):
    """The check's progress handler: stop at the first step, since the authorizer has run when the text was prepared."""
    return lambda: 1


def _resolves(c, name: str) -> bool:
    """Whether ``name`` names a table, a schema table or a table-valued function on the stand-in (any error but no such
    table: yes)."""
    try:
        c.execute(f'select 1 from "{name.replace(chr(34), chr(34) * 2)}" limit 0')
    except sqlite3.OperationalError as e:
        return "no such table" not in str(e)
    return True


def check(spec, deadline: float, text: str, params: dict, why: list) -> set[str]:
    """Prepare ``text`` on a stand-in of the index: an in-memory database of the index's own tables, empty, in its
    ``main`` (so a name resolves as on the index, and is refused by the same words) and an empty temp table per view
    (its name and columns), bounded and authorized as a query is. Returns, only if the text passed, the names it may
    read with no database: the views, and its ``WITH`` names that name nothing else (so each read of one is a ``WITH``'s,
    wherever it is); raises otherwise (a refusal's words in ``why``)."""
    from ..spec import itemindex, projections
    c = sqlite3.connect(":memory:", isolation_level=None)
    try:
        c.executescript(itemindex.SCHEMA + projections.SCHEMA)
        _bounded(c, deadline, why)
        every = views(spec)
        for view, cols in every.items():
            c.execute(f'create temp table "{view}" ({", ".join(chr(34) + x + chr(34) for x in cols)})')
        names = {v.lower() for v in every}
        auth = _authorizer(why, lambda db, a: db == "temp" and a in names)
        c.set_authorizer(auth)
        c.set_progress_handler(_prepared(deadline), 1)
        try:
            c.execute(text, params)
        except sqlite3.OperationalError as e:
            if why or "interrupted" not in str(e) or time.monotonic() > deadline:
                raise
        c.set_authorizer(None)
        c.set_progress_handler(None, 0)
        own = names | {n for n in auth.unsure & auth.ctes if not _resolves(c, n)}
        if bad := sorted(auth.unsure - own):
            why.append(("refused", f"only a SELECT of the views is allowed, and this reads main.{bad[0]}"))
        if why or time.monotonic() > deadline:
            raise sqlite3.OperationalError("interrupted")
        return own
    finally:
        c.close()


@contextlib.contextmanager
def opened(ix, spec, deadline: float, text: str | None = None, why: list | None = None, own: set | None = None):
    """``(connection, why)``: the index's file opened read only, each view a temp view over the index's tables, and then
    only SELECT allowed, reading those views' own tables, until ``deadline`` (``time.monotonic()``). ``why``: the words
    of a refusal, the authorizer's or an aggregate's. A text is run here only after it passed ``check``: SQLite does
    not tell the authorizer which view a read is for, so here a query's own read of ``main.items`` would pass.

    The stages' views, made in Python, are copied into temp tables, only when ``text`` (every one, for None) names one.
    The states each kind's items finish in (``reason``) and the query are read in one read transaction, committed on
    leaving, so a catch-up committed meanwhile is not seen, and a query joining two views sees each item the same in
    both."""
    why = [] if why is None else why
    words = {w.lower() for w in _WORD.findall(text)} if text is not None else None
    with ix.reading() as c:
        _bounded(c, deadline, why)
        c.create_function("_fields", 1, _fields, deterministic=True)
        c.execute("begin")                   # (one snapshot of the index, from the first read to the commit)
        finished = _finished(c, spec)
        names = set()
        for view, select in _definitions(spec, finished).items():
            c.execute(f'create temp view "{view}" as {select}')
            names.add(view.lower())
        if words is None or words & set(stages.COLUMNS):
            _stage_tables(c, spec, finished, time.time())
            names |= set(stages.COLUMNS)
        c.execute("pragma query_only = 1")
        tables = {"items", "moves", "names", "json_each"}   # (what the definitions read; json_each is item_fields')
        c.set_authorizer(_authorizer(why, lambda db, a: (db == "main" and a in tables) or (db == "temp" and a in names),
                                     FUNCTIONS | {"_fields", "json_each"}, names | (own or set())))
        yield c, why
        c.set_authorizer(None)
        c.execute("commit")
