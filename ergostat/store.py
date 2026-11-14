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
    c = sqlite3.connect(path, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("pragma journal_mode=wal")
    c.execute("pragma busy_timeout=10000")
    c.executescript(schema)
    return c


class _Conns:
    """One connection per thread, kept open: opening and closing connections from many threads at
    once can deadlock inside SQLite's file locking."""

    def __init__(self, path: Path, schema: str):
        self.path, self.schema = path, schema
        self.local = threading.local()

    @contextmanager
    def __call__(self):
        c = getattr(self.local, "c", None)
        if c is None:
            c = self.local.c = _connect(self.path, self.schema)
        yield c


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
              since: float | None = None, after_seq: int | None = None, until: float | None = None) -> list[dict]:
        """Matching events, oldest first; the newest ``n`` when ``n`` is given. ``type`` may end in
        ``*``."""
        where, args = [], []
        if type:
            if type.endswith("*"):
                where.append("type like ?")
                args.append(type[:-1] + "%")
            else:
                where.append("type = ?")
                args.append(type)
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
        """Each item: how many events, the first and last, and the latest type. Items that only
        ergostat's own events are about (agents, valves, controllers, loops) are left out unless
        ``own``."""
        theirs = "sum(case when " + " or ".join(f"type like '{p}.%'" for p in OWN) + " then 0 else 1 end)"
        sql = ("select item, count(*) n, min(time) first, max(time) last, " + theirs + " theirs, "
               "(select type from events e2 where e2.item = e.item order by seq desc limit 1) latest "
               "from events e where item is not null" + (" and time >= ?" if since else "") +
               " group by item" + ("" if own else " having theirs > 0") + " order by last desc")
        with self._c() as c:
            return [dict(r) for r in c.execute(sql, (since,) if since else ())]

    def count(self) -> int:
        with self._c() as c:
            return c.execute("select count(*) from events").fetchone()[0]

    def first_time(self) -> float | None:
        with self._c() as c:
            return c.execute("select min(time) from events").fetchone()[0]

    def prune(self, before: float) -> int:
        """Forget events older than ``before``, except the model's history, which is kept whole."""
        with self._c() as c:
            return c.execute("delete from events where time < ? and type != 'model.changed'", (before,)).rowcount

    def opened(self, valve: str, since: float, until: float | None = None) -> dict:
        """A valve's openings in a span: how many, the amount they moved, and the last one's time."""
        with self._c() as c:
            r = c.execute("select count(*), coalesce(sum(coalesce(json_extract(data, '$.amount'), 1)), 0), max(time) from events "
                          "where item = ? and type = 'valve.opened' and time >= ? and time <= ?",
                          (valve, since, until if until is not None else 1e18)).fetchone()
        return {"count": r[0], "amount": float(r[1]), "last": r[2]}

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
            rows = c.execute("select type, count(*), sum(coalesce(json_extract(data, '$.refused'), 0)) from events "
                             "where item = ? and type in ('agent.ran', 'agent.failed') and time >= ? and time <= ? group by type",
                             (item, since, until if until is not None else 1e18)).fetchall()
        by = {r[0]: (r[1], r[2] or 0) for r in rows}
        ran, failed = by.get("agent.ran", (0, 0)), by.get("agent.failed", (0, 0))
        return {"runs": ran[0] + failed[0], "failed": failed[0], "refused": ran[1] + failed[1]}

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

    def prune(self, before: float) -> int:
        with self._c() as c:
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
        self.events = Events(self.dir)
        self.measurements = Measurements(self.dir)

    @property
    def repo(self) -> Path:
        return self.model.path.parent if self.model.path else Path.cwd()
