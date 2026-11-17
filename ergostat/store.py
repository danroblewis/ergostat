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
  data text
);
create index if not exists events_item on events(item, seq);
create index if not exists events_type on events(type, seq);
create index if not exists events_time on events(time);
create index if not exists events_cause on events(causedby);
create index if not exists events_item_type_time on events(item, type, time);
"""
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
    c.execute("pragma journal_mode=wal")
    c.execute("pragma busy_timeout=10000")
    c.executescript(schema)
    return c


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
            causedby: str | None = None, at: float | None = None, id: str | None = None) -> dict:
        ev = {"id": id or uuid.uuid4().hex, "time": at if at is not None else time.time(), "type": type, "item": item,
              "source": source, "causedby": causedby, "data": data or {}}
        with self._c() as c:
            cur = c.execute("insert or ignore into events(id, time, type, item, source, causedby, data) values (?,?,?,?,?,?,?)",
                            (ev["id"], ev["time"], type, item, source, causedby, json.dumps(ev["data"])))
            ev["seq"] = cur.lastrowid if cur.rowcount else None
        return ev

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["data"] = json.loads(d["data"] or "{}")
        return d

    def query(self, *, n: int | None = 100, type: str | None = None, item: str | None = None, source: str | None = None,
              since: float | None = None, after_seq: int | None = None, until: float | None = None,
              skip: tuple[str, ...] = (), unvoided: bool = False, machine: str | None = None) -> list[dict]:
        """Matching events, oldest first; the newest ``n`` when ``n`` is given. ``type`` may end in
        ``*``, and may be several, joined by commas; types in ``skip`` are left out. ``machine``: from
        that source or one of its instances (``<machine>/<instance>``)."""
        where, args = [], []
        if skip:
            where.append(f"type not in ({','.join('?' * len(skip))})")
            args.extend(skip)
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
        sql = ("select item, count(*) n, min(time) first, max(time) last, "
               "(select type from events e2 where e2.item = e.item order by seq desc limit 1) latest "
               "from events e where item is not null" + ("" if own else " and item like '%/%'") +
               (" and time >= ?" if since else "") + " group by item order by last desc")
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, (since,) if since else ())]

    def of_items(self, globs: list[str] | None = None, until: float | None = None) -> list[dict]:
        """Every event about an item (an id with a ``/``), or about ids matching one of ``globs``,
        oldest first."""
        where, args = ["item like '%/%'"], []
        if globs:
            where.append("(" + " or ".join("item glob ?" for _ in globs) + ")")
            args += globs
        if until is not None:
            where.append("time <= ?")
            args.append(until)
        with self._c() as c:
            return [self._row(r) for r in c.execute("select * from events where " + " and ".join(where) + " order by seq", args)]

    def count(self) -> int:
        with self._c() as c:
            return c.execute("select count(*) from events").fetchone()[0]

    def first_time(self) -> float | None:
        with self._c() as c:
            return c.execute("select min(time) from events").fetchone()[0]

    def prune(self, before: float) -> int:
        """Forget events older than ``before``, except the model's history, which is kept whole, and
        each loop's last crossing (whether it was off is what its hysteresis needs)."""
        with self._c() as c:
            return c.execute("delete from events where time < ? and type != 'model.changed' and seq not in "
                             "(select max(seq) from events where type like 'loop.%' group by item)", (before,)).rowcount

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
    def __init__(self, directory: Path):
        self.path = directory / "measurements.db"
        self._c = _Conns(self.path, MEASUREMENTS)
        with self._c():
            pass

    def add(self, series: str, value: float, at: float | None = None) -> None:
        with self._c() as c:
            c.execute("insert into samples(series, time, value) values (?,?,?)",
                      (series, at if at is not None else time.time(), float(value)))

    def latest(self, series: str, before: float | None = None) -> tuple[float, float] | None:
        with self._c() as c:
            r = c.execute("select time, value from samples where series = ? and time <= ? order by time desc limit 1",
                          (series, before if before is not None else 1e18)).fetchone()
        return (r[0], r[1]) if r else None

    def range(self, series: str, since: float, until: float | None = None) -> list[tuple[float, float]]:
        with self._c() as c:
            rows = c.execute("select time, value from samples where series = ? and time >= ? and time <= ? order by time",
                             (series, since, until if until is not None else time.time() + 1)).fetchall()
        return [(r[0], r[1]) for r in rows]

    def sampled(self, series: str, since: float, until: float | None = None, points: int = 600) -> list[tuple[float, float]]:
        """The readings in a span, raw when there are few; otherwise averaged into ``points`` buckets
        by SQLite, with the first and last readings kept exact (a week of readings every few
        seconds never reaches Python one by one)."""
        until = until if until is not None else time.time() + 1
        with self._c() as c:
            n = c.execute("select count(*) from samples where series = ? and time >= ? and time <= ?", (series, since, until)).fetchone()[0]
            if n <= points * 2:
                return self.range(series, since, until)
            width = (until - since) / points
            rows = c.execute("select avg(time), avg(value) from samples where series = ? and time >= ? and time <= ? "
                             "group by cast((time - ?) / ? as integer) order by 1", (series, since, until, since, width)).fetchall()
            first = c.execute("select time, value from samples where series = ? and time >= ? order by time limit 1",
                              (series, since)).fetchone()
            last = c.execute("select time, value from samples where series = ? and time <= ? order by time desc limit 1",
                             (series, until)).fetchone()
        mid = [(r[0], r[1]) for r in rows if first[0] < r[0] < last[0]]
        return [(first[0], first[1]), *mid, (last[0], last[1])]

    def first(self, series: str, since: float, until: float) -> tuple[float, float] | None:
        """The first reading in a span: (time, value)."""
        with self._c() as c:
            r = c.execute("select time, value from samples where series = ? and time >= ? and time <= ? order by time limit 1",
                          (series, since, until)).fetchone()
        return (r[0], r[1]) if r else None

    def bucketed(self, series: str, since: float, until: float, n: int) -> list[tuple[int, float, float, float]]:
        """The readings in ``n`` equal buckets over a span, by SQLite: (bucket, mean, the last
        reading's time, the last reading's value) for each bucket that has a reading."""
        width = (until - since) / max(n, 1) or 1.0
        with self._c() as c:
            # one max() among the aggregates: SQLite takes the bare column from the row with the latest time
            rows = c.execute("select min(cast((time - ?) / ? as integer), ?), avg(value), max(time), value from samples "
                             "where series = ? and time >= ? and time <= ? group by 1 order by 1",
                             (since, width, n - 1, series, since, until)).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def forget(self, series: str, above: float | None = None, below: float | None = None) -> list[tuple[float, float]]:
        """Set readings aside: those above ``above`` or below ``below``. They are kept in their own
        table, out of every estimate (a wrong reading poisons rates and residuals for the whole
        window). Returns what was set aside."""
        cond, args = [], []
        if above is not None:
            cond.append("value > ?")
            args.append(above)
        if below is not None:
            cond.append("value < ?")
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
            c.execute("commit")
        return [(r[0], r[1]) for r in rows]

    def prune(self, before: float) -> int:
        with self._c() as c:
            c.execute("delete from forgotten where time < ?", (before,))
            return c.execute("delete from samples where time < ?", (before,)).rowcount

    def series(self) -> list[dict]:
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "select series, count(*) n, max(time) last, "
                "(select value from samples s2 where s2.series = s.series order by time desc limit 1) value "
                "from samples s group by series order by series")]

    def count(self) -> int:
        with self._c() as c:
            return c.execute("select count(*) from samples").fetchone()[0]

    def first_time(self) -> float | None:
        with self._c() as c:
            return c.execute("select min(time) from samples").fetchone()[0]


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
        self.events = Events(self.dir)
        self.measurements = Measurements(self.dir)

    @property
    def repo(self) -> Path:
        return self.model.path.parent if self.model.path else Path.cwd()
