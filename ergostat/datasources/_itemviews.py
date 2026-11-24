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
(tests/test_sql_source.py). For each query, on a connection of its own opened read only, the views its text names are
copied into tables of that connection's own; then only SELECT, reading those copies and the functions named in
FUNCTIONS are allowed (SQLite's authorizer), and the query, copies and all, is bounded in time (a progress handler), in
each value's size and in memory (``opened``)."""

from __future__ import annotations

import contextlib
import json
import math
import re
import sqlite3
import time

from ..spec import codec

STABLE = {
    "transitions": ("id", "kind", "at", "from_state", "to_state", "event", "type"),
    "item_fields": ("id", "kind", "field", "value"),
    "item_spans": ("id", "kind", "state", "entered", "left", "entry", "reason"),
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


@contextlib.contextmanager
def opened(ix, spec, deadline: float, text: str | None = None, why: list | None = None):
    """``(connection, why)``: the index's file opened read only, each view ``text`` names (every one, for None) copied
    into a table of the connection's own, and then only SELECT on those allowed, until ``deadline``
    (``time.monotonic()``). ``why``: the words of a refusal, the authorizer's or an aggregate's.

    The copies, and the states each kind's items finish in (``reason``), are read in one read transaction, so they are
    of one state of the index: a catch-up committed meanwhile is seen by none of them, and a query joining two views
    sees each item the same in both.

    (A copy, not a view over the index: SQLite tells the authorizer which view a read is for only while the view is not
    flattened into the query, so a view's reads could not be told from a query's own. Once the copies are made nothing
    of ``main`` may be read at all.)"""
    why = [] if why is None else why
    words ={w.lower() for w in _WORD.findall(text)} if text is not None else None
    with ix.reading() as c:
        c.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        for k, v in ((sqlite3.SQLITE_LIMIT_LENGTH, MOST_VALUE), (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
                     (sqlite3.SQLITE_LIMIT_COLUMN, 200), (sqlite3.SQLITE_LIMIT_WORKER_THREADS, 0)):
            c.setlimit(k, v)
        for p in (f"cache_size = -{CACHE_KB}", f"temp.cache_size = -{CACHE_KB}", "temp_store = file", "mmap_size = 0"):
            c.execute(f"pragma {p}")
        c.create_function("_fields", 1, _fields, deterministic=True)
        c.create_aggregate("median", 1, _ranked(why, 1.0, 0.0, 1.0))
        c.create_aggregate("percentile_cont", 2, _ranked(why, 1.0, 0.0, 1.0))
        c.create_aggregate("percentile", 2, _ranked(why, 0.01, 0.0, 100.0))
        names = set()
        c.execute("begin")                   # (one snapshot of the index, from the first read to the commit)
        finished = _finished(c, spec)
        for view, select in _definitions(spec, finished).items():
            if words is None or view.lower() in words:
                c.execute(f'create temp table "{view}" as {select}')
                names.add(view.lower())
        c.execute("commit")
        c.execute("pragma query_only = 1")

        def denied(what: str) -> int:
            why.append(("refused", f"only a SELECT of the views is allowed, and this {what}"))
            return sqlite3.SQLITE_DENY

        def allowed(action, a, b, db, _inside):
            if action in (_SELECT, _RECURSIVE):
                return sqlite3.SQLITE_OK
            if action == _READ:              # the copies (temp), or what the query names itself (a WITH: no database)
                ok = db is None or (db == "temp" and (a or "").lower() in names)
                return sqlite3.SQLITE_OK if ok else denied(f"reads {db}.{a}")
            if action == _FUNCTION:
                return sqlite3.SQLITE_OK if (b or "").lower() in FUNCTIONS else denied(f"calls {b}")
            return denied(f"is not a SELECT (SQLite's action {action})")
        c.set_authorizer(allowed)
        yield c, why
