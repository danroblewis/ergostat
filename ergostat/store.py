"""The two stores, kept apart (NOTES: few events, many measurements): the events, the append-only record of what
happened, here (``events.db``, SQLite; or the segmented log, segments.py) in the project's state directory,
``$ERGOSTAT_HOME/<project>/`` (default ``~/.ergostat``); and the measurements, what the sensors read, in
VictoriaMetrics (victoria.py), with the ledger of what was backfilled (``LEDGER``) beside the events."""

from __future__ import annotations

import contextvars
import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .notify import key_of, written

EVENTS = """
create table if not exists events (
  seq integer primary key autoincrement,
  id text unique not null,
  time real not null,
  type text not null,
  item text,
  source text,
  causedby text,
  data text,
  change text
);
create index if not exists events_item on events(item, seq);
create index if not exists events_type on events(type, seq);
create index if not exists events_time on events(time);
create index if not exists events_cause on events(causedby);
create index if not exists events_item_type_time on events(item, type, time);
create index if not exists events_item_own on events(item, seq) where (type < 'claude.' or type >= 'claude/');
create table if not exists meta (key text primary key, value);
"""
OWN_LINES = "(type < 'claude.' or type >= 'claude/')"     # not a transcript's line: events_item_own holds just these
KEPT = "ergostat.operating."     # never rolled up nor forgotten: the spells a trip answered, the clocks it started
LEDGER = """
create table if not exists backfills (id text primary key, series text not null, src text, written_at, first real, last real, count int);
create table if not exists backfilled (series text not null, at real not null, id text, primary key (series, at)) without rowid;
"""                                                       # never rolled, pruned or forgotten: what was backfilled, kept
MOST_BACKFILLED = 200_000                                 # readings in one backfill, at most


def ledger_write(conns, series: str, rows: list[tuple[float, float]], src: str | None, write, replace=None) -> dict:
    """One backfill: ``rows`` (at, value; of one at, the last kept) not yet in the ledger written by ``write(c, rows)``
    and recorded, all in one transaction held from the ledger's read to its write (two at once: the second waits, then
    skips what the first wrote). What is skipped is said by the ledger alone, never by the buckets. With ``replace``
    (``replace(c, series, first, last, rows, why) -> how many set aside``, which writes ``rows`` too), every reading from the
    first ``at`` to the last is set aside first, and the ledger's entries there are this call's (earlier backfills
    there marked ``replaced``, with when)."""
    now = time.time()
    last = {float(t): float(v) for t, v in rows}
    if len(last) > MOST_BACKFILLED or not all(math.isfinite(t) and math.isfinite(v) and t <= now for t, v in last.items()):
        raise ValueError(f"a backfill is at most {MOST_BACKFILLED} readings, each a finite value at a finite past time")
    if replace and not src:
        raise ValueError("a replacing backfill says where it came from (--from)")
    gone = None
    with conns() as c:
        c.execute("begin immediate")
        try:
            if replace and last:
                span = (series, min(last), max(last))
                c.execute("update backfills set replaced = ? where series = ? and replaced is null and count > 0 and "
                          "last >= ? and first <= ?", (now, series, span[1], span[2]))
                c.execute("delete from backfilled where series = ? and at >= ? and at <= ?", span)
            have = {r[0] for r in c.execute("select at from backfilled where series = ?", (series,))}
            new = sorted((t, v) for t, v in last.items() if t not in have)
            got = {"id": uuid.uuid4().hex, "series": series, "from": src, "written_at": now,
                   "first": new[0][0] if new else None, "last": new[-1][0] if new else None, "count": len(new)}
            c.execute("insert into backfills(id, series, src, written_at, first, last, count) values (?,?,?,?,?,?,?)",
                      tuple(got.values()))
            c.executemany("insert into backfilled(series, at, id) values (?,?,?)", [(series, t, got["id"]) for t, _ in new])
            if replace and last:
                gone = replace(c, *span, [(series, t, v) for t, v in new], src)
            elif new:
                write(c, [(series, t, v) for t, v in new])
            c.execute("commit")
        except BaseException:
            c.execute("rollback")
            raise
    return {**got, "skipped": len(last) - len(new), "repeated": len(rows) - len(last), "replaced": gone}


def ledger_read(conns, series: str) -> list[dict]:
    """A series' backfills, in the order they were made (``replaced``: when a later one replaced its span, or None)."""
    with conns() as c:
        return [dict(r) for r in c.execute('select id, series, src as "from", written_at, first, last, count, replaced '
                                           "from backfills where series = ? order by rowid", (series,))]


OWN = ("agent", "valve", "controller", "loop", "ergostat")     # ergostat's own event types


def home() -> Path:
    return Path(os.environ.get("ERGOSTAT_HOME") or Path.home() / ".ergostat")


def state_dir(project: str, repo: Path | None = None, make: bool = True) -> Path:
    """``<home>/<name>-<8 hex of the repository's path>``: two repositories never share a record,
    even with the same name. ``make=False``: not made when it is not there."""
    import hashlib
    key = project if repo is None else f"{project}-{hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:8]}"
    d = home() / key
    if make:
        d.mkdir(parents=True, exist_ok=True)
    return d


def damaged(e: BaseException, io: bool = False) -> bool:
    """Whether a SQLite error says the file itself is damaged (not a database, malformed), not that it is
    busy; ``io``: a failed read or write of it counts too (a file deleted while open, say)."""
    if not isinstance(e, sqlite3.DatabaseError):
        return False
    code = getattr(e, "sqlite_errorcode", None)
    if code is not None:
        return (code & 0xFF) in ((11, 26, 10) if io else (11, 26))    # SQLITE_CORRUPT, _NOTADB, _IOERR
    text = str(e).lower()
    return any(w in text for w in ("not a database", "malformed", *(("disk i/o error",) if io else ())))


class RecordDamaged(sqlite3.DatabaseError):
    """``events.db`` (or another of the record's SQLite files) cannot be read. They are the record, never rebuilt: what to do is said."""

    def __init__(self, path: Path, e: BaseException):
        super().__init__(
            f"{path} is damaged ({e}). It is the record and ergostat does not rebuild it. Stop ergostat "
            f"(ergostat run --stop, and close its pages), copy {path.name} with its -wal and -shm somewhere safe, "
            f"then recover what SQLite can: sqlite3 {path} .recover | sqlite3 {path}.recovered, and move "
            f"{path.name}.recovered in place of {path.name} (removing the old -wal and -shm); or restore it from a "
            f"backup; or start over with ergostat reset.")
        self.path = path


def _connect(path: Path, schema: str) -> sqlite3.Connection:
    c = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)   # lent to one thread at a time
    c.row_factory = sqlite3.Row
    c.execute("pragma busy_timeout=10000")
    c.execute("pragma auto_vacuum=incremental")    # a new file gives back what is forgotten (an old one: vacuum())
    c.execute("pragma journal_mode=wal")
    c.executescript(schema)
    for table, col in ADDED.items():               # a file from before the column (events: before changesets)
        if f"exists {table} (" in schema and col.split()[0] not in {r[1] for r in c.execute(f"pragma table_info({table})")}:
            try:
                c.execute(f"alter table {table} add column {col}")
            except sqlite3.OperationalError:       # another connection added it first
                pass
    return c


ADDED = {"events": "change text", "forgotten": "why text", "backfills": "replaced real"}   # columns newer than the tables


def _after(p: str) -> str:
    """The least string after every string starting with ``p``: ``p`` read as a range, which an index serves."""
    return p[:-1] + chr(ord(p[-1]) + 1)


def _types(type: str, args: list) -> str:
    """Types joined by commas, each exact or a prefix ending in ``*`` (as written: no ``_`` or ``%`` wildcards), as an
    indexed condition."""
    ors = []
    for t in (x.strip() for x in type.split(",") if x.strip()):
        if t == "*":
            ors.append("1")
        elif t.endswith("*"):
            ors.append("(type >= ? and type < ?)")
            args += [t[:-1], _after(t[:-1])]
        else:
            ors.append("type = ?")
            args.append(t)
    return "(" + " or ".join(ors) + ")"


def _skipping(skip: tuple[str, ...], where: list[str], args: list) -> None:
    """Leave out these types; one ending in ``*`` is a prefix (``claude.*``)."""
    exact = [t for t in skip if not t.endswith("*")]
    if exact:
        where.append(f"type not in ({','.join('?' * len(exact))})")
        args.extend(exact)
    for t in skip:
        if t == "claude.*":                        # as events_item_own says it, so a fold of items reads only that index
            where.append(OWN_LINES)
        elif t.endswith("*"):                      # a range, so the type index serves it
            lo = t[:-1]
            where.append("not (type >= ? and type < ?)")
            args += [lo, lo[:-1] + chr(ord(lo[-1]) + 1)]


LINE: contextvars.ContextVar[list | None] = contextvars.ContextVar("ergostat_journal_line", default=None)


def line_id() -> str | None:
    """The next id of an event made by the journal line being taken (SPEC §9.1, *Runs taken up again*): from the run,
    the line's place in its journal and the count of events it made so far, so a line taken again (an engine killed
    between its events and its saved offset) makes the same ids, which the record keeps once. None outside a line."""
    got = LINE.get()
    if got is None or got[0] is None:
        return None
    got[1] += 1
    return hashlib.sha256(f"{got[0]}:{got[1]}".encode()).hexdigest()[:32]


class ChangesetError(ValueError):
    pass


def changeset(data, patch, set_) -> str | None:
    """An event's changeset other than plain data, as stored: ``{"patch": [...]}`` or ``{"set": {...}}``.
    Only one form; ``ChangesetError`` says why not."""
    given = [n for n, v in (("data", data), ("patch", patch), ("set", set_)) if v not in (None, {}, [])]
    if len(given) > 1:
        raise ChangesetError(f"an event changes its item one way: {' or '.join(given)}, not both")
    if patch is not None:
        if not isinstance(patch, list) or not all(isinstance(o, dict) and "op" in o and "path" in o for o in patch):
            raise ChangesetError("patch: a JSON Patch, a list of operations ({\"op\": \"add\", \"path\": \"/x\", \"value\": 1})")
        return json.dumps({"patch": patch})
    if set_ is not None:
        if not isinstance(set_, dict):
            raise ChangesetError("set: the whole document, a JSON object")
        return json.dumps({"set": set_})
    return None


class _Conns:
    """A few connections, kept open and lent to one thread at a time. Not one per thread: a runner
    with dozens of agents and a page with its pool of threads would hold two files per connection
    each (the database and its WAL), past macOS's default of 256 open files. Not opened and closed
    for every use either: that, from many threads at once, can deadlock inside SQLite's locking.
    A thread that already holds one (a call inside a call) uses the same one."""

    SIZE = 6

    def __init__(self, path: Path, schema: str):
        import queue
        self.path, self.schema = path, schema
        self.local = threading.local()
        self.free: queue.LifoQueue = queue.LifoQueue()
        self.made, self.lock = 0, threading.Lock()

    @contextmanager
    def __call__(self):
        try:
            with self._lend() as c:
                yield c
        except RecordDamaged:
            raise
        except sqlite3.DatabaseError as e:
            if damaged(e):
                raise RecordDamaged(self.path, e) from e
            raise

    @contextmanager
    def _lend(self):
        held = getattr(self.local, "c", None)
        if held is not None:                       # already lent to this thread: the same one
            yield held
            return
        c = None
        with self.lock:
            if self.free.empty() and self.made < self.SIZE:
                self.made += 1
                c = _connect(self.path, self.schema)
        if c is None:
            c = self.free.get()                    # wait for one to come back
        self.local.c = c
        try:
            yield c
        finally:
            self.local.c = None
            if c.in_transaction:                   # an error inside one: nothing half done is lent on
                c.rollback()
            self.free.put(c)


class Events:
    def __init__(self, directory: Path):
        self.path = directory / "events.db"
        self._nkey = key_of(directory)                     # its waiters' board (notify.py)
        self._c = _Conns(self.path, EVENTS)
        with self._c():
            pass

    def add(self, type: str, *, item: str | None = None, source: str | None = None, data: dict | None = None,
            causedby: str | None = None, at: float | None = None, id: str | None = None, patch: list | None = None,
            set: dict | None = None) -> dict:
        """Record an event. About an item, it changes it one way (SPEC §5a): plain ``data``, folded by
        its kind's rules; a JSON ``patch``; or ``set``, its whole document. An event already recorded
        (the same ``id``) is not recorded again: its ``seq`` is None."""
        change = changeset(data, patch, set)
        if change and (not isinstance(item, str) or "/" not in item):
            raise ChangesetError("a patch or a set changes an item: name it (an id with a /, ticket/12)")
        ev = {"id": id or line_id() or uuid.uuid4().hex, "time": at if at is not None else time.time(), "type": type,
              "item": item, "source": source, "causedby": causedby, "data": data or {}}
        if patch is not None:
            ev["patch"] = patch
        if set is not None:
            ev["set"] = set
        with self._c() as c:
            cur = c.execute("insert or ignore into events(id, time, type, item, source, causedby, data, change) "
                            "values (?,?,?,?,?,?,?,?)",
                            (ev["id"], ev["time"], type, item, source, causedby, json.dumps(ev["data"]), change))
            ev["seq"] = cur.lastrowid if cur.rowcount else None
        written(self._nkey)
        return ev

    def board(self):
        """What waits for this record's new events wakes on (``notify.py``): written here, or by another process."""
        from .notify import board
        b = board(self.path.parent)
        if b.watcher is None:
            b.watch([Path(str(self.path) + "-wal"), self.path])
        return b

    name = "sqlite"

    def add_many(self, evs: list[dict], new: bool = False) -> int:
        """Several events at once, in one transaction (a transcript's lines): each a dict of ``add``'s
        arguments with ``type``. Those already recorded are skipped. Returns how many were new."""
        rows = []
        for e in evs:
            rows.append((e.get("id") or uuid.uuid4().hex, e["at"] if e.get("at") is not None else time.time(), e["type"],
                         e.get("item"), e.get("source"), e.get("causedby"), json.dumps(e.get("data") or {}),
                         changeset(e.get("data"), e.get("patch"), e.get("set"))))
        with self._c() as c:
            before = c.total_changes
            c.execute("begin immediate")
            try:
                c.executemany("insert or ignore into events(id, time, type, item, source, causedby, data, change) "
                              "values (?,?,?,?,?,?,?,?)", rows)
                c.execute("commit")
            except BaseException:
                c.execute("rollback")
                raise
            got = c.total_changes - before
        written(self._nkey)
        return got

    def known(self, ids: list[str]) -> set[str]:
        """Which of these event ids are recorded."""
        out: set[str] = set()
        with self._c() as c:
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                out |= {r[0] for r in c.execute(f"select id from events where id in ({','.join('?' * len(part))})", part)}
        return out

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["data"] = json.loads(d["data"] or "{}")
        change = d.pop("change", None)
        if change:
            d.update(json.loads(change))           # "patch": [...] or "set": {...}
        return d

    def query(self, *, n: int | None = 100, type: str | None = None, item: str | None = None, source: str | None = None,
              since: float | None = None, after_seq: int | None = None, until: float | None = None,
              skip: tuple[str, ...] = (), unvoided: bool = False, machine: str | None = None,
              before_seq: int | None = None, first: int | None = None) -> list[dict]:
        """Matching events, oldest first; the newest ``n`` when ``n`` is given, the oldest ``first`` (over ``n``)
        when that is. ``type`` may end in
        ``*``, and may be several, joined by commas; types in ``skip`` are left out. ``machine``: from
        that source or one of its instances (``<machine>/<instance>``)."""
        where, args = [], []
        _skipping(skip, where, args)
        if unvoided:                                     # crossings a forgotten reading caused are left out
            where.append("id not in (select j.value from events f, json_each(f.data, '$.voids') j "
                         "where f.type = 'ergostat.forgotten')")
        if type:
            where.append(_types(type, args))
        if machine:
            where.append("(source = ? or source like ?)")
            args += [machine, machine + "/%"]
        for col, v in (("item", item), ("source", source)):
            if v is not None:
                where.append(f"{col} = ?")
                args.append(v)
        if since is not None:
            where.append("time >= ?")
            args.append(since)
        if after_seq is not None:
            where.append("seq > ?")
            args.append(after_seq)
        if before_seq is not None:
            where.append("seq < ?")
            args.append(before_seq)
        if until is not None:
            where.append("time <= ?")
            args.append(until)
        sql = "select * from events" + (" where " + " and ".join(where) if where else "")
        with self._c() as c:
            if first is not None:
                rows = c.execute(sql + " order by seq limit ?", [*args, max(first, 0)]).fetchall()
            elif n is None:
                rows = c.execute(sql + " order by seq", args).fetchall()
            else:
                rows = c.execute(sql + " order by seq desc limit ?", [*args, n]).fetchall()[::-1]
        return [self._row(r) for r in rows]

    def moments(self, *, n: int, type: str | None = None, since: float | None = None, until: float | None = None,
                skip: tuple[str, ...] = ()) -> list[tuple[float, str]]:
        """(time, type) of the newest ``n`` matching events, oldest first, no event's data read: what a chart of events needs."""
        where, args = [], []
        _skipping(skip, where, args)
        if type:
            where.append(_types(type, args))
        if since is not None:
            where.append("time >= ?")
            args.append(since)
        if until is not None:
            where.append("time <= ?")
            args.append(until)
        sql = "select time, type from events" + (" where " + " and ".join(where) if where else "") + " order by seq desc limit ?"
        with self._c() as c:
            return [(r[0], r[1]) for r in c.execute(sql, [*args, n]).fetchall()[::-1]]

    def get(self, id: str) -> dict | None:
        with self._c() as c:
            r = c.execute("select * from events where id = ?", (id,)).fetchone() or (id and c.execute(
                "select * from events where id >= ? and id < ? order by id limit 1", (id, _after(id))).fetchone())
        return self._row(r) if r else None

    def times(self, items: list[str], type: str, since: float, until: float) -> dict[str, list[tuple[float, str, int]]]:
        """For each of ``items``, (time, type, seq) of its events of ``type`` in the span, in seq order."""
        out: dict[str, list] = {i: [] for i in items}
        args: list = []
        ors = _types(type, args)
        for i in range(0, len(items), 500):
            part = items[i:i + 500]
            with self._c() as c:
                for it, t, ty, q in c.execute(f"select item, time, type, seq from events where {ors} and "
                                              f"time >= ? and time <= ? and item in ({','.join('?' * len(part))}) order by seq",
                                              (*args, since, until, *part)):
                    out[it].append((t, ty, q))
        return out

    def caused_by(self, id: str) -> list[dict]:
        with self._c() as c:
            return [self._row(r) for r in c.execute("select * from events where causedby = ? order by seq", (id,))]

    def items(self, since: float | None = None, own: bool = False) -> list[dict]:
        """Each item (an id with a ``/`` in it: ``ticket/12``): how many events, the first and last,
        and the latest type. With ``own``, also the parts ergostat's own events are about."""
        sql = ("select item, sum(case when type = 'ergostat.item.snapshot' then "
               "coalesce(json_extract(data, '$.rollup.n'), 1) else 1 end) n, "
               "min(coalesce(json_extract(data, '$.rollup.first'), time)) first, max(time) last, "
               "(select type from events e2 where e2.item = e.item order by seq desc limit 1) latest "
               "from events e where item is not null" + ("" if own else " and item like '%/%'") +
               (" and time >= ?" if since else "") + " group by item order by last desc")
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, (since,) if since else ())]

    def item_ids(self) -> set[str]:
        """Every item (an id with a ``/``) the record holds an event about."""
        with self._c() as c:
            return {r[0] for r in c.execute("select distinct item from events where item like '%/%'")}

    def of_items(self, globs: list[str] | None = None, until: float | None = None, skip: tuple[str, ...] = (),
                 after_seq: int | None = None, limit: int | None = None, ids=None) -> list[dict]:
        """Every event about an item (an id with a ``/``), or about ids matching one of ``globs`` (or
        among ``ids``), oldest first; types in ``skip`` (``claude.*``: a prefix) left out; after
        ``after_seq`` when given (what is new since a fold)."""
        if ids is not None:
            ids = sorted(set(ids))
            out = []
            for i in range(0, len(ids), 500):
                out += self._of_items(globs, until, skip, after_seq, None, ids[i:i + 500])
            out.sort(key=lambda e: e["seq"])
            return out[:limit] if limit else out
        return self._of_items(globs, until, skip, after_seq, limit, None)

    def _of_items(self, globs, until, skip, after_seq, limit, ids) -> list[dict]:
        where, args = ["item like '%/%'"], []
        if after_seq:
            where.append("seq > ?")
            args.append(after_seq)
        _skipping(skip, where, args)
        if globs:
            where.append("(" + " or ".join("item glob ?" for _ in globs) + ")")
            args += globs
        if ids is not None:
            where.append(f"item in ({','.join('?' * len(ids))})")
            args += ids
        if until is not None:
            where.append("time <= ?")
            args.append(until)
        with self._c() as c:
            return [self._row(r) for r in c.execute("select * from events where " + " and ".join(where) + " order by seq"
                                                    + (f" limit {int(limit)}" if limit else ""), args)]

    def counted(self, prefix: str, until: float | None = None) -> dict[str, tuple[int, float]]:
        """Per item, how many events of types starting ``prefix`` (``claude.*``) and the latest one's time,
        counted by SQLite on the type index."""
        lo = prefix.rstrip("*")
        hi = lo[:-1] + chr(ord(lo[-1]) + 1)
        with self._c() as c:
            rows = c.execute("select item, count(*), max(time) from events where type >= ? and type < ? and time <= ? "
                             "group by item", (lo, hi, until if until is not None else 1e18)).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows if r[0]}

    def count(self) -> int:
        with self._c() as c:
            return c.execute("select count(*) from events").fetchone()[0]

    def first_time(self) -> float | None:
        with self._c() as c:
            return c.execute("select min(time) from events").fetchone()[0]

    _KEEP = f"substr(type, 1, {len(KEPT)}) != '{KEPT}'"
    _LOOSE = ("time < ? and type != 'model.changed' and item not like '%/%' and seq not in "
              f"(select max(seq) from events where type like 'loop.%' group by item) and {_KEEP}")
    _WHOLE = (f"{_KEEP} and ((item is null and time < ? and type != 'model.changed') or item in "
              "(select item from events where item like '%/%' group by item having max(time) < ?))")

    def prunable(self, before: float) -> int:
        """How many events ``prune(before)`` would forget, counted without forgetting any."""
        with self._c() as c:
            return (c.execute(f"select count(*) from events where {self._LOOSE}", (before,)).fetchone()[0]
                    + c.execute(f"select count(*) from events where {self._WHOLE}", (before, before)).fetchone()[0])

    def prune(self, before: float) -> int:
        """Forget events older than ``before``, except the model's history, which is kept whole, and
        each loop's last crossing (whether it was off is what its hysteresis needs) and ``KEPT``. An item is
        forgotten whole, once nothing about it is newer: until then its older events are its
        snapshot's (``rollup.py`` folds them in first)."""
        with self._c() as c:
            c.execute("begin immediate")
            n = c.execute(f"delete from events where {self._LOOSE}", (before,)).rowcount
            n += c.execute(f"delete from events where {self._WHOLE}", (before, before)).rowcount
            if n:
                self._bump(c)
            c.execute("commit")
            return n

    def _bump(self, c) -> None:
        c.execute("insert into meta(key, value) values ('generation', 1) "
                  "on conflict(key) do update set value = value + 1")

    def generation(self) -> int:
        """Changed whenever events are taken out of the record (pruned, rolled up): a fold kept from
        before is folded again."""
        with self._c() as c:
            r = c.execute("select value from meta where key = 'generation'").fetchone()
        return r[0] if r else 0

    def replace(self, changes: list[tuple[str, list[int], dict]]) -> None:
        """Roll up (``rollup.py``): for each ``(item, seqs, snapshot)``, those events of the item out of
        the record and the snapshot in their place, at the last one's ``seq`` (so it folds where they
        did); all in one transaction."""
        with self._c() as c:
            c.execute("begin immediate")
            try:
                from .segments import unpacked
                for item, seqs, snap in changes:
                    snap = unpacked(snap)
                    for i in range(0, len(seqs), 500):
                        part = seqs[i:i + 500]
                        c.execute(f"delete from events where item = ? and seq in ({','.join('?' * len(part))})", (item, *part))
                    c.execute("insert into events(seq, id, time, type, item, source, causedby, data, change) "
                              "values (?,?,?,?,?,?,?,?,?)",
                              (max(seqs), snap["id"], snap["time"], snap["type"], item, snap.get("source"), None,
                               json.dumps(snap.get("data") or {}), json.dumps({"set": snap["set"]})))
                self._bump(c)
                c.execute("commit")
            except BaseException:
                c.execute("rollback")
                raise

    def opened(self, valve: str, since: float, until: float | None = None) -> dict:
        """A valve's openings in a span: how many, the amount they moved, and the last one's time."""
        with self._c() as c:
            r = c.execute("select count(*), coalesce(sum(coalesce(json_extract(data, '$.amount'), 1)), 0), max(time) from events "
                          "where item = ? and type = 'valve.opened' and time >= ? and time <= ?",
                          (valve, since, until if until is not None else 1e18)).fetchone()
        return {"count": r[0], "amount": float(r[1]), "last": r[2]}

    def last_opening(self, valve: str, until: float | None = None) -> dict | None:
        """A valve's last opening (up to ``until``): the run that opened it last, with what that whole
        run moved (an agent may report each thing it moves as its own line). None when it never opened."""
        until = until if until is not None else 1e18
        with self._c() as c:
            last = c.execute("select time, causedby, coalesce(json_extract(data, '$.amount'), 1) from events where item = ? "
                             "and type = 'valve.opened' and time <= ? order by time desc, seq desc limit 1",
                             (valve, until)).fetchone()
            if last is None:
                return None
            if last[1] is None:
                return {"time": last[0], "count": 1, "amount": float(last[2])}
            r = c.execute("select count(*), coalesce(sum(coalesce(json_extract(data, '$.amount'), 1)), 0) from events "
                          "where item = ? and type = 'valve.opened' and causedby = ? and time <= ?",
                          (valve, last[1], until)).fetchone()
        return {"time": last[0], "count": r[0], "amount": float(r[1])}

    def decided(self, controller: str, since: float, until: float | None = None) -> list[tuple[str, int]]:
        """A controller's decisions in a span, grouped by their words."""
        with self._c() as c:
            return [(r[0] or "", r[1]) for r in c.execute(
                "select json_extract(data, '$.decision'), count(*) from events "
                "where item = ? and type = 'controller.decided' and time >= ? and time <= ? group by 1",
                (controller, since, until if until is not None else 1e18))]

    def runs(self, item: str, since: float, until: float | None = None) -> dict:
        """An agent's runs in a span, counted by SQLite: runs, failed, and lines refused."""
        with self._c() as c:
            rows = c.execute("select type, count(*), "
                             "sum(case when json_extract(data, '$.why') = 'by hand' then 0 "
                             "         else coalesce(json_extract(data, '$.refused'), 0) end), "
                             "sum(case when json_extract(data, '$.why') = 'by hand' then 0 "
                             "         else coalesce(json_extract(data, '$.unread'), 0) end), "
                             "sum(type = 'agent.ran' and json_extract(data, '$.note') like 'workspace pool % has none free for %') "
                             "from events where item = ? and type in ('agent.ran', 'agent.failed') and time >= ? and time <= ? "
                             "group by type", (item, since, until if until is not None else 1e18)).fetchall()
        by = {r[0]: (r[1], r[2] or 0, r[3] or 0, r[4] or 0) for r in rows}
        ran, failed = by.get("agent.ran", (0, 0, 0, 0)), by.get("agent.failed", (0, 0, 0, 0))
        # what a run by hand refused or could not read is shown to whoever ran it, not kept as a problem
        return {"runs": ran[0] + failed[0], "failed": failed[0], "refused": ran[1] + failed[1], "unread": ran[2] + failed[2],
                "pool_full": ran[3]}           # runs that found their workspace pool full: given back, not failed (§12k)

    def last_seq(self) -> int:
        with self._c() as c:
            return c.execute("select coalesce(max(seq), 0) from events").fetchone()[0]


def vacuum(store) -> int:
    """A SQLite store's file made as small as what it holds, when much of it is free (rows forgotten,
    in a file made before it gave pages back as it went). Returns the bytes given back."""
    if getattr(store, "name", None) != "sqlite":
        return 0
    with store._c() as c:
        c.execute("pragma wal_checkpoint(truncate)")
        free, pages, size = (c.execute(f"pragma {k}").fetchone()[0] for k in ("freelist_count", "page_count", "page_size"))
        if pages and free / pages > 0.2:
            before = store.path.stat().st_size
            c.execute("vacuum")
            if c.execute("pragma auto_vacuum").fetchone()[0] != 2:
                c.execute("pragma auto_vacuum=incremental")
                c.execute("vacuum")
            return max(0, before - store.path.stat().st_size)
    return 0


class Project:
    """A repository's model and its two stores."""

    def __init__(self, model, directory: Path | None = None, note: bool = True):
        self.model = model
        self.dir = directory or state_dir(model.name, model.path.parent if model.path else None)
        if model.path and note:                             # so `ergostat projects` can find the repository again
            note = self.dir / "repo.json"
            want = json.dumps({"name": model.name, "repo": str(model.path.parent)})
            if not note.exists() or note.read_text() != want:
                note.write_text(want)
        from .storage import Storage, open_events, open_measurements
        self.storage = getattr(model, "storage", None) or Storage()
        self.events = open_events(self.storage, self.dir)
        self.measurements = open_measurements(self.storage, self.dir)
        if hasattr(self.measurements, "spec_of"):         # (its readings named for the model as it is: promnames.py)
            self.measurements.spec_of = lambda: getattr(self.model, "spec", None)

    @property
    def repo(self) -> Path:
        return self.model.path.parent if self.model.path else Path.cwd()
