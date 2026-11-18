"""The two stores, kept apart (NOTES: few events, many measurements): ``events.db``, the append-only
record of what happened, and ``measurements.db``, what the sensors read. Both are SQLite files in
the project's state directory, ``$ERGOSTAT_HOME/<project>/`` (default ``~/.ergostat``)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

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
MEASUREMENTS = """
create table if not exists samples (
  series text not null,
  time real not null,
  value real not null
);
create index if not exists samples_series on samples(series, time);
create table if not exists forgotten (
  series text not null,
  time real not null,
  value real not null,
  forgotten_at real not null
);
create table if not exists tiers (
  series text not null,
  every real not null,
  t real not null,
  n integer not null,
  sum real not null,
  min real not null,
  max real not null,
  first_t real not null,
  first_v real not null,
  last_t real not null,
  last_v real not null,
  primary key (series, every, t)
) without rowid;
create table if not exists late (series text not null, time real not null, value real not null);
create table if not exists meta (key text primary key, value);
"""


OWN = ("agent", "valve", "controller", "loop", "ergostat")     # ergostat's own event types


def home() -> Path:
    return Path(os.environ.get("ERGOSTAT_HOME") or Path.home() / ".ergostat")


def state_dir(project: str, repo: Path | None = None) -> Path:
    """``<home>/<name>-<8 hex of the repository's path>``: two repositories never share a record,
    even with the same name."""
    import hashlib
    key = project if repo is None else f"{project}-{hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:8]}"
    d = home() / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _connect(path: Path, schema: str) -> sqlite3.Connection:
    c = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)   # lent to one thread at a time
    c.row_factory = sqlite3.Row
    c.execute("pragma busy_timeout=10000")
    c.execute("pragma auto_vacuum=incremental")    # a new file gives back what is forgotten (an old one: vacuum())
    c.execute("pragma journal_mode=wal")
    c.executescript(schema)
    if schema is EVENTS and "change" not in {r[1] for r in c.execute("pragma table_info(events)")}:
        try:                                       # a record from before changesets: every event in it is plain data
            c.execute("alter table events add column change text")
        except sqlite3.OperationalError:           # another connection added it first
            pass
    return c


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
        ev = {"id": id or uuid.uuid4().hex, "time": at if at is not None else time.time(), "type": type, "item": item,
              "source": source, "causedby": causedby, "data": data or {}}
        if patch is not None:
            ev["patch"] = patch
        if set is not None:
            ev["set"] = set
        with self._c() as c:
            cur = c.execute("insert or ignore into events(id, time, type, item, source, causedby, data, change) "
                            "values (?,?,?,?,?,?,?,?)",
                            (ev["id"], ev["time"], type, item, source, causedby, json.dumps(ev["data"]), change))
            ev["seq"] = cur.lastrowid if cur.rowcount else None
        return ev

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
            return c.total_changes - before

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
              before_seq: int | None = None) -> list[dict]:
        """Matching events, oldest first; the newest ``n`` when ``n`` is given. ``type`` may end in
        ``*``, and may be several, joined by commas; types in ``skip`` are left out. ``machine``: from
        that source or one of its instances (``<machine>/<instance>``)."""
        where, args = [], []
        _skipping(skip, where, args)
        if unvoided:                                     # crossings a forgotten reading caused are left out
            where.append("id not in (select j.value from events f, json_each(f.data, '$.voids') j "
                         "where f.type = 'ergostat.forgotten')")
        if type:
            ors = []
            for t in (x.strip() for x in type.split(",") if x.strip()):
                ors.append("type like ?" if t.endswith("*") else "type = ?")
                args.append(t[:-1] + "%" if t.endswith("*") else t)
            where.append("(" + " or ".join(ors) + ")")
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
            if n is None:
                rows = c.execute(sql + " order by seq", args).fetchall()
            else:
                rows = c.execute(sql + " order by seq desc limit ?", [*args, n]).fetchall()[::-1]
        return [self._row(r) for r in rows]

    def get(self, id: str) -> dict | None:
        with self._c() as c:
            r = c.execute("select * from events where id = ? or id like ?", (id, id + "%")).fetchone()
        return self._row(r) if r else None

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

    def prune(self, before: float) -> int:
        """Forget events older than ``before``, except the model's history, which is kept whole, and
        each loop's last crossing (whether it was off is what its hysteresis needs). An item is
        forgotten whole, once nothing about it is newer: until then its older events are its
        snapshot's (``rollup.py`` folds them in first)."""
        with self._c() as c:
            c.execute("begin immediate")
            n = c.execute("delete from events where time < ? and type != 'model.changed' and item not like '%/%' and seq not in "
                          "(select max(seq) from events where type like 'loop.%' group by item)", (before,)).rowcount
            n += c.execute("delete from events where (item is null and time < ? and type != 'model.changed') or item in "
                           "(select item from events where item like '%/%' group by item having max(time) < ?)",
                           (before, before)).rowcount
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
                for item, seqs, snap in changes:
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
                             "         else coalesce(json_extract(data, '$.unread'), 0) end) from events "
                             "where item = ? and type in ('agent.ran', 'agent.failed') and time >= ? and time <= ? group by type",
                             (item, since, until if until is not None else 1e18)).fetchall()
        by = {r[0]: (r[1], r[2] or 0, r[3] or 0) for r in rows}
        ran, failed = by.get("agent.ran", (0, 0, 0)), by.get("agent.failed", (0, 0, 0))
        # what a run by hand refused or could not read is shown to whoever ran it, not kept as a problem
        return {"runs": ran[0] + failed[0], "failed": failed[0], "refused": ran[1] + failed[1], "unread": ran[2] + failed[2]}

    def last_seq(self) -> int:
        with self._c() as c:
            return c.execute("select coalesce(max(seq), 0) from events").fetchone()[0]


class Measurements:
    """Readings, in SQLite: raw for a recent window (``raw``), then rolled up into tiers of buckets
    (each keeping the count, sum, min, max, first and last reading), each kept for its own time
    (``tiers``: ``(every, keep)`` seconds, finest first). ``roll`` makes the buckets and forgets what
    is past its time; the engine calls it as it goes. Every read stitches the sources: raw where it
    is kept, the buckets before that, the coarsest that is fine enough for what is asked."""

    name = "sqlite"

    def __init__(self, directory: Path, raw: float | None = None, tiers: list[tuple[float, float]] | None = None):
        self.path = directory / "measurements.db"
        self._c = _Conns(self.path, MEASUREMENTS)
        self.raw = raw                                     # None: raw readings kept until pruned
        self.tiers = sorted((float(e), float(k)) for e, k in (tiers or []))
        self._marks: tuple[float, dict] = (0.0, {})        # each tier's rolled-up-to, read at most every few seconds
        with self._c():
            pass

    # ---- writing

    def _mark(self) -> dict[float, float]:
        now = time.monotonic()
        if now - self._marks[0] > 5:
            with self._c() as c:
                rows = c.execute("select key, value from meta where key like 'rolled.%'").fetchall()
            self._marks = (now, {float(k.split(".", 1)[1]): v for k, v in rows})
        return self._marks[1]

    def _late(self, c, rows: list[tuple[str, float, float]]) -> None:
        """Readings written into a span already rolled up: kept aside too, to be merged into the
        buckets they belong in at the next roll (``_merge_late``)."""
        mark = self._mark().get(self.tiers[0][0]) if self.tiers else None
        if mark is not None:
            late = [r for r in rows if r[1] < mark]
            if late:
                c.executemany("insert into late(series, time, value) values (?,?,?)", late)

    def add(self, series: str, value: float, at: float | None = None) -> None:
        t = at if at is not None else time.time()
        with self._c() as c:
            c.execute("insert into samples(series, time, value) values (?,?,?)", (series, t, float(value)))
            if at is not None:
                self._late(c, [(series, t, float(value))])

    def add_many(self, rows: list[tuple[str, float, float]]) -> None:
        """Many readings at once, ``(series, time, value)``, in one transaction (a record written whole: the
        benchmark's simulated worlds)."""
        if not rows:
            return
        with self._c() as c:
            c.execute("begin")
            rows = [(s, float(t), float(v)) for s, t, v in rows]
            c.executemany("insert into samples(series, time, value) values (?,?,?)", rows)
            self._late(c, rows)
            c.execute("commit")

    # ---- the sources a span is read from

    def _sources(self, c, series: str, since: float, until: float, fine: float = 0.0) -> list[tuple[float, float, float]]:
        """``(every, lo, hi)``: which source answers each part of ``[since, until]``, oldest part first.
        ``every`` 0 is the raw readings, else a tier, which holds from its oldest bucket of this
        series up to where it was last rolled. Where several hold a part, the coarsest no wider than
        ``fine`` is used, then the raw readings, then the finest wider one."""
        if not self.tiers:
            return [(0.0, since, until)]
        r = c.execute("select min(time) from samples where series = ?", (series,)).fetchone()[0]
        e0 = self.tiers[0][0]                          # raw is forgotten in whole buckets of the finest tier
        held = {0.0: (r // e0 * e0 if r is not None else float("inf"), float("inf"))}
        marks = self._mark()
        for e, _ in self.tiers:
            lo = c.execute("select min(t) from tiers where series = ? and every = ?", (series, e)).fetchone()[0]
            if lo is not None and marks.get(e) is not None:
                held[e] = (lo, marks[e])
        prefer = [e for e, _ in sorted(self.tiers, reverse=True) if 0 < e <= fine] + [0.0] + \
                 [e for e, _ in self.tiers if e > fine]
        prefer = [e for e in prefer if e in held]
        out: list[tuple[float, float, float]] = []
        cursor = since
        while cursor <= until:
            here = [e for e in prefer if held[e][0] <= cursor < held[e][1]]
            if not here:                               # nothing holds this moment: on to where the next one starts
                nxt = min((held[e][0] for e in prefer if held[e][0] > cursor), default=None)
                if nxt is None or nxt > until:
                    break
                cursor = nxt
                continue
            e = here[0]
            better = [held[x][0] for x in prefer[:prefer.index(e)] if held[x][0] > cursor]
            hi = min([held[e][1], *better, until])
            if out and out[-1][0] == e:
                out[-1] = (e, out[-1][1], hi)
            else:
                out.append((e, cursor, hi))
            if hi >= until:
                break
            cursor = hi
        if out and out[-1][0] == 0.0:                  # the raw readings' end is the span's own
            out[-1] = (0.0, out[-1][1], until)
        if out and out[0][0] and out[0][1] == since:   # a bucket that began before the span, and ends in it
            out[0] = (out[0][0], since // out[0][0] * out[0][0], out[0][2])
        return out

    # ---- reading

    def latest(self, series: str, before: float | None = None) -> tuple[float, float] | None:
        before = before if before is not None else 1e18
        with self._c() as c:
            r = c.execute("select time, value from samples where series = ? and time <= ? order by time desc limit 1",
                          (series, before)).fetchone()
            if r is None:
                for e, _ in self.tiers:
                    r = c.execute("select last_t, last_v from tiers where series = ? and every = ? and last_t <= ? "
                                  "order by t desc limit 1", (series, e, before)).fetchone()
                    if r:
                        break
        return (r[0], r[1]) if r else None

    def range(self, series: str, since: float, until: float | None = None, last: int | None = None) -> list[tuple[float, float]]:
        """The readings in a span, oldest first (the newest ``last`` of them when given). Where raw readings
        are no longer kept, each bucket's last reading stands for it."""
        until = until if until is not None else time.time() + 1
        out: list[tuple[float, float]] = []
        with self._c() as c:
            for e, lo, hi in reversed(self._sources(c, series, since, until)):
                if e == 0:
                    sql = "select time, value from samples where series = ? and time >= ? and time <= ? order by time desc"
                    args: tuple = (series, lo, hi)
                else:
                    sql = ("select last_t, last_v from tiers where series = ? and every = ? and t >= ? and t < ? "
                           "and last_t >= ? order by t desc")
                    args = (series, e, lo, hi, since)
                rows = c.execute(sql + (" limit ?" if last else ""), (*args, last - len(out)) if last else args).fetchall()
                out += [(r[0], r[1]) for r in rows]
                if last and len(out) >= last:
                    break
        return out[::-1]

    def count(self, series: str | None = None, since: float | None = None, until: float | None = None) -> int:
        """How many readings: of one series in a span (raw and those its buckets stand for), or every row kept."""
        with self._c() as c:
            if series is None:
                n = c.execute("select count(*) from samples").fetchone()[0]
                return n + (c.execute("select count(*) from tiers").fetchone()[0] if self.tiers else 0)
            total = 0
            for e, lo, hi in self._sources(c, series, since or 0.0, until if until is not None else 1e18):
                if e == 0:
                    total += c.execute("select count(*) from samples where series = ? and time >= ? and time <= ?",
                                       (series, lo, hi)).fetchone()[0]
                else:
                    total += c.execute("select coalesce(sum(n), 0) from tiers where series = ? and every = ? and t >= ? "
                                       "and t < ?", (series, e, lo, hi)).fetchone()[0]
        return total

    def bucketed(self, series: str, since: float, until: float, n: int) -> list[tuple[int, float, float, float]]:
        """The readings in ``n`` equal buckets over a span, by SQLite: (bucket, mean, the last
        reading's time, the last reading's value) for each bucket that has a reading. Old spans are
        read from the coarsest tier whose buckets are no wider than these."""
        width = (until - since) / max(n, 1) or 1.0
        acc: dict[int, list[float]] = {}                 # bucket: [sum, count, last time, last value]
        with self._c() as c:
            for e, lo, hi in self._sources(c, series, since, until, fine=width):
                # one max() among the aggregates: SQLite takes the bare column from the row with the latest time
                if e == 0:
                    rows = c.execute("select min(cast((time - ?) / ? as integer), ?), sum(value), count(*), max(time), value "
                                     "from samples where series = ? and time >= ? and time <= ? group by 1",
                                     (since, width, n - 1, series, lo, hi)).fetchall()
                else:
                    rows = c.execute("select max(min(cast((last_t - ?) / ? as integer), ?), 0), sum(sum), sum(n), max(last_t), last_v "
                                     "from tiers where series = ? and every = ? and t >= ? and t < ? group by 1",
                                     (since, width, n - 1, series, e, lo, hi)).fetchall()
                for b, s, k, t, v in rows:
                    a = acc.setdefault(b, [0.0, 0, -1e18, 0.0])
                    a[0] += s
                    a[1] += k
                    if t >= a[2]:
                        a[2], a[3] = t, v
        return [(b, a[0] / a[1], a[2], a[3]) for b, a in sorted(acc.items()) if a[1]]

    def sampled(self, series: str, since: float, until: float | None = None, points: int = 600) -> list[tuple[float, float]]:
        """The readings in a span, raw when there are few; otherwise averaged into ``points`` buckets
        (each at its readings' last time), with the first and last readings kept exact (a week of
        readings every few seconds never reaches Python one by one)."""
        until = until if until is not None else time.time() + 1
        if self.count(series, since, until) <= points * 2:
            return self.range(series, since, until)
        first, last = self.first(series, since, until), self.latest(series, until)
        mid = [(t, mean) for _, mean, t, _ in self.bucketed(series, since, until, points) if first[0] < t < last[0]]
        return [first, *mid, last]

    def first(self, series: str, since: float, until: float) -> tuple[float, float] | None:
        """The first reading in a span: (time, value)."""
        with self._c() as c:
            for e, lo, hi in self._sources(c, series, since, until):
                if e == 0:
                    r = c.execute("select time, value from samples where series = ? and time >= ? and time <= ? "
                                  "order by time limit 1", (series, lo, hi)).fetchone()
                else:
                    r = c.execute("select first_t, first_v from tiers where series = ? and every = ? and t >= ? "
                                  "and t < ? and first_t >= ? order by t limit 1", (series, e, lo, hi, since)).fetchone()
                if r:
                    return (r[0], r[1])
        return None

    def forget(self, series: str, above: float | None = None, below: float | None = None) -> list[tuple[float, float]]:
        """Set readings aside: those above ``above`` or below ``below``. They are kept in their own
        table, out of every estimate (a wrong reading poisons rates and residuals for the whole
        window). Returns what was set aside. Buckets that held one are made again from what is left
        (or dropped, where the raw readings are gone)."""
        cond, tcond, args = [], [], []
        if above is not None:
            cond.append("value > ?")
            tcond.append("max > ?")
            args.append(above)
        if below is not None:
            cond.append("value < ?")
            tcond.append("min < ?")
            args.append(below)
        if not cond:
            return []
        where = f"series = ? and ({' or '.join(cond)})"
        with self._c() as c:
            c.execute("begin immediate")
            rows = c.execute(f"select time, value from samples where {where}", (series, *args)).fetchall()
            c.execute(f"insert into forgotten(series, time, value, forgotten_at) select series, time, value, ? from samples where {where}",
                      (time.time(), series, *args))
            c.execute(f"delete from samples where {where}", (series, *args))
            redo = c.execute(f"select every, t from tiers where series = ? and ({' or '.join(tcond)})", (series, *args)).fetchall()
            c.execute(f"delete from tiers where series = ? and ({' or '.join(tcond)})", (series, *args))
            for e, t in redo:
                if e == self.tiers[0][0]:
                    self._roll_raw(c, e, t, t + e, series)
            c.execute("commit")
        return [(r[0], r[1]) for r in rows]

    # ---- keeping it bounded

    def _roll_raw(self, c, e: float, lo: float, hi: float, series: str | None = None) -> None:
        c.execute("insert or replace into tiers(series, every, t, n, sum, min, max, first_t, first_v, last_t, last_v) "
                  "select g.series, ?, g.b, g.n, g.s, g.mn, g.mx, g.ft, "
                  "(select value from samples x where x.series = g.series and x.time = g.ft limit 1), g.lt, "
                  "(select value from samples x where x.series = g.series and x.time = g.lt order by rowid desc limit 1) "
                  "from (select series, cast(time / ? as integer) * ? b, count(*) n, sum(value) s, min(value) mn, "
                  "max(value) mx, min(time) ft, max(time) lt from samples where time >= ? and time < ?"
                  + (" and series = ?" if series else "") + " group by series, b) g",
                  (e, e, e, lo, hi, *((series,) if series else ())))

    def _roll_tier(self, c, e: float, prev: float, lo: float, hi: float) -> None:
        c.execute("insert or replace into tiers(series, every, t, n, sum, min, max, first_t, first_v, last_t, last_v) "
                  "select g.series, ?, g.b, g.n, g.s, g.mn, g.mx, g.ft, "
                  "(select first_v from tiers x where x.series = g.series and x.every = ? and x.t >= g.b and x.t < g.b + ? "
                  "and x.first_t = g.ft limit 1), g.lt, "
                  "(select last_v from tiers x where x.series = g.series and x.every = ? and x.t >= g.b and x.t < g.b + ? "
                  "and x.last_t = g.lt limit 1) "
                  "from (select series, cast(t / ? as integer) * ? b, sum(n) n, sum(sum) s, min(min) mn, max(max) mx, "
                  "min(first_t) ft, max(last_t) lt from tiers where every = ? and t >= ? and t < ? group by series, b) g",
                  (e, prev, e, prev, e, e, e, prev, lo, hi))

    def _merge_late(self, c, e: float, mark: float) -> int:
        before = c.total_changes
        c.execute("insert into tiers(series, every, t, n, sum, min, max, first_t, first_v, last_t, last_v) "
                  "select g.series, ?, g.b, g.n, g.s, g.mn, g.mx, g.ft, "
                  "(select value from late x where x.series = g.series and x.time = g.ft limit 1), g.lt, "
                  "(select value from late x where x.series = g.series and x.time = g.lt order by rowid desc limit 1) "
                  "from (select series, cast(time / ? as integer) * ? b, count(*) n, sum(value) s, min(value) mn, "
                  "max(value) mx, min(time) ft, max(time) lt from late where time < ? group by series, b) g where true "
                  "on conflict(series, every, t) do update set n = n + excluded.n, sum = sum + excluded.sum, "
                  "min = min(min, excluded.min), max = max(max, excluded.max), "
                  "first_v = case when excluded.first_t < first_t then excluded.first_v else first_v end, "
                  "first_t = min(first_t, excluded.first_t), "
                  "last_v = case when excluded.last_t >= last_t then excluded.last_v else last_v end, "
                  "last_t = max(last_t, excluded.last_t)", (e, e, e, mark // e * e))
        return c.total_changes - before

    def roll(self, now: float | None = None, chunk: float = 6 * 3600.0) -> dict:
        """Roll the readings up into each tier (whole buckets only, a few hours of record per
        transaction, so writers are never kept waiting long), then forget what each source keeps no
        longer: raw readings past ``raw``, each tier's buckets past its keep (never what the next
        tier has not taken yet). Returns how many rows each step made and forgot."""
        now = now if now is not None else time.time()
        done = {"rolled": 0, "forgot": 0}
        if not self.tiers:
            return done
        with self._c() as c:
            marks = {float(k.split(".", 1)[1]): v for k, v in c.execute("select key, value from meta where key like 'rolled.%'")}
            c.execute("begin immediate")
            for e, _ in self.tiers:                         # late readings first, into the buckets already made
                if marks.get(e) is not None:
                    done["rolled"] += self._merge_late(c, e, marks[e])
            c.execute("delete from late")
            c.execute("commit")
        prev = 0.0
        for e, _ in self.tiers:
            settle = max(prev, 60.0)                        # late readings of the newest bucket: wait a little
            to = (now - settle) // e * e
            with self._c() as c:
                if prev == 0:
                    oldest = c.execute("select min(time) from samples").fetchone()[0]
                else:
                    oldest = c.execute("select min(t) from tiers where every = ?", (prev,)).fetchone()[0]
            start = marks.get(e, oldest if oldest is not None else to) // e * e
            while start < to:
                hi = min(to, start + max(chunk, e))
                hi = hi // e * e if hi < to else to
                with self._c() as c:
                    c.execute("begin immediate")
                    before = c.total_changes
                    if prev == 0:
                        self._roll_raw(c, e, start, hi)
                    else:
                        self._roll_tier(c, e, prev, start, hi)
                    done["rolled"] += c.total_changes - before
                    c.execute("insert into meta(key, value) values (?, ?) on conflict(key) do update set value = max(value, ?)",
                              (f"rolled.{e:g}", hi, hi))
                    c.execute("commit")
                start = hi
            marks[e] = max(marks.get(e, to), to)
            prev = e
        with self._c() as c:
            c.execute("begin immediate")
            if self.raw is not None:
                cut = min(now - self.raw, marks[self.tiers[0][0]]) // self.tiers[0][0] * self.tiers[0][0]
                done["forgot"] += c.execute("delete from samples where time < ?", (cut,)).rowcount
                c.execute("delete from forgotten where time < ?", (cut,))
            for i, (e, keep) in enumerate(self.tiers):
                cut = now - keep
                if i + 1 < len(self.tiers):                 # whole buckets of the next tier only
                    nxt = self.tiers[i + 1][0]
                    cut = min(cut, marks[nxt]) // nxt * nxt
                done["forgot"] += c.execute("delete from tiers where every = ? and t + ? <= ?", (e, e, cut)).rowcount
            c.execute("commit")
        self._marks = (0.0, {})
        if done["forgot"]:
            with self._c() as c:
                c.execute("pragma incremental_vacuum")
                c.execute("pragma wal_checkpoint(truncate)")   # and the write-ahead log, which grew with it
        return done

    def prune(self, before: float) -> int:
        with self._c() as c:
            c.execute("delete from forgotten where time < ?", (before,))
            c.execute("delete from tiers where t < ?", (before,))
            return c.execute("delete from samples where time < ?", (before,)).rowcount

    def series(self) -> list[dict]:
        """Each series: how many readings are kept raw, the last one's time and value."""
        with self._c() as c:
            rows = [dict(r) for r in c.execute(
                "select series, count(*) n, max(time) last, "
                "(select value from samples s2 where s2.series = s.series order by time desc limit 1) value "
                "from samples s group by series order by series")]
            if self.tiers:                                  # a series whose raw readings are all gone, by its buckets
                have = {r["series"] for r in rows}
                for r in c.execute("select series, sum(n) n, max(last_t) last from tiers where every = ? group by series",
                                   (self.tiers[-1][0],)):
                    if r["series"] not in have:
                        rows.append({"series": r["series"], "n": r["n"], "last": r["last"],
                                     "value": (self.latest(r["series"]) or (None, None))[1]})
                rows.sort(key=lambda r: r["series"])
        return rows

    def first_time(self) -> float | None:
        with self._c() as c:
            got = [c.execute("select min(time) from samples").fetchone()[0]]
            if self.tiers:
                got.append(c.execute("select min(first_t) from tiers").fetchone()[0])
        return min((t for t in got if t is not None), default=None)


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

    def __init__(self, model, directory: Path | None = None):
        self.model = model
        self.dir = directory or state_dir(model.name, model.path.parent if model.path else None)
        if model.path:                                      # so `ergostat projects` can find the repository again
            note = self.dir / "repo.json"
            want = json.dumps({"name": model.name, "repo": str(model.path.parent)})
            if not note.exists() or note.read_text() != want:
                note.write_text(want)
        from .storage import Storage, open_events, open_measurements
        self.storage = getattr(model, "storage", None) or Storage()
        self.events = open_events(self.storage, self.dir)
        self.measurements = open_measurements(self.storage, self.dir)

    @property
    def repo(self) -> Path:
        return self.model.path.parent if self.model.path else Path.cwd()
