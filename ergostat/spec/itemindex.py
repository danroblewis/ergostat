"""The item index (SPEC §4b, §5a): every item's fold kept on disk, followed as events arrive.

``<state>/items/<key>.db``, one SQLite file per fold (the model's item kinds, and whether a
transcript's lines are folded in), shared by every process on the record (the runner, the page,
the command line): whichever asks first after events arrive folds them, under SQLite's write lock,
a chunk at a time, and the others read what it wrote. A process that starts reads the index; it
folds only what is newer than it.

- ``items``: per item its kind, state, times, counts and its document (``body``: its fields and
  what was refused, packed by ``codec.py``); kinds, states and event types are numbers (``names``).
- ``moves``: every move of every item (when, from, to, by which event), so a flow counted from
  items reads only its window, and a count of items in a state reads only that state.
- ``left`` and ``reached``: each kind's states some item has left, and has reached, so what a kind
  counts as finished is known without reading every move.
- ``items.text``: its searchable text (``items.text_of``: its fields' strings, casefolded, capped), on its own row, so
  written and replaced with it: an item has no text row to lose.
- ``links``: every item's relations to other items (SPEC §5a, *Relations*), one row per link (the item, the
  relation, the id it names), indexed both ways, so an item's links and the links to it (the inverse: ``blocks``,
  ``children``) are both one lookup. A kind that declares ``about:`` keeps there too, as relation ``@about``, each
  part of the model its items name (``goal.x``), as its field now holds them: "the items about goal.x" is one lookup.
- ``number_log`` and ``numbers``: each change of an item's numeric field (when, the value, by how much) and each
  item's value now (``itemnumbers.py``), so a chart of a field reads its kind, field and window and decodes no body.
- ``records``, ``marks``, ``voids``, ``asks``: what the status answer reads from the record (``projections.py``),
  followed in the same transactions.

In memory, only items still open are kept folded (their fold state, a few thousand at most, the
latest touched): an item in a finished state, or with no event for ``storage: items: idle``, is
read from disk when an event about it arrives. The record stays the truth: the index is rebuilt
from it when it is missing, when the record went back (a fresh record, events gone that it held),
or on ``ergostat compact --reindex``; it is checked against a fresh fold in
``tests/test_item_index.py``. A roll-up leaves it as it is (a snapshot folds to what its events
folded to); a prune takes out the items whose events are all gone.

Several processes share an index file, so none deletes one another still has open (unlinking a
SQLite file, its WAL or its shared memory while in use corrupts it): every process holds a shared
``flock`` on ``<file>.lock`` while it has the file open, and a file is deleted (``_tidy``,
``reindex``, healing) only under the exclusive lock, taken without waiting. A file that cannot be
deleted now is *retired* (``<file>.retired``): it is not opened again, and the next name
(``<hash>.1.db``, ...) is built in its place. Being a cache, an index that cannot be read (not a
database, malformed) is built again from the record where it is found (``_heal``); the record
itself (``events.db``, ``measurements.db``) never is (``store.RecordDamaged``)."""

from __future__ import annotations

import contextlib
import fcntl
import functools
import hashlib
import logging
import os
import re
import sqlite3
import stat
import sys
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

from ..leases import PREFIX as LEASE_PREFIX
from ..store import damaged
from . import codec, itemnumbers, projections
from .about import parts_named
from .items import SNAPSHOT, TRANSCRIPT_TYPES, Item, fold, kind_of, text_of
from .relations import links_of

VERSION = 8                 # of the index's layout: a different one is rebuilt (4: items.text; 5: the @about links;
#                             6: the numbers, or what the status reads, on the two branches that each took 6;
#                             7: both; 8: records.last, latest, ticks, each item's fields touched)
ABOUT = "@about"            # the links of an item to the parts of the model it is about (never a relation's name)
CHUNK = 50_000              # events folded per transaction: other processes read and write between them
CACHED = 4096               # open items kept folded in memory, the latest touched
IDLE = 86400.0              # an item with no event for this long is not kept in memory (storage: items: idle)
KEPT_FILES = 6              # index files kept per record (a few models' kinds at once)
TIDY_AGE = 3600.0           # an index file changed more recently than this is never tidied away
MOST_FILES = 64             # the most index files ``use: upkeep``'s tidier may be told to keep
NAME = re.compile(r"^[0-9a-f]{16}(\.[0-9]+)?\.db$")   # an index file's name: <hash>.db, <hash>.<n>.db

log = logging.getLogger("ergostat")

SCHEMA = """
create table if not exists meta (key text primary key, value);
create table if not exists names (id integer primary key, name text unique not null);
create table if not exists items (
    rid integer primary key, id text unique not null, kind integer, state integer,
    first real, last real, newest real, entered real, n integer, latest integer,
    arrived real, raw integer, raw_first real, body blob, text text);
create index if not exists items_kind_state_last on items(kind, state, last);
create index if not exists items_kind_last on items(kind, last);
create index if not exists items_last on items(last);
create index if not exists items_textless on items(rid) where text is null;
create index if not exists items_newest on items(newest);
create table if not exists moves (rid integer, kind integer, t real, frm integer, dst integer, event text, type integer);
create index if not exists moves_rid on moves(rid);
create index if not exists moves_dst on moves(kind, dst, t);
create index if not exists moves_frm on moves(kind, frm, t);
create table if not exists left (kind integer, state integer, primary key (kind, state)) without rowid;
create table if not exists reached (kind integer, state integer, primary key (kind, state)) without rowid;
create table if not exists links (rid integer, rel integer, dst text);
create index if not exists links_rid on links(rid);
create index if not exists links_dst on links(dst);
create table if not exists number_log (kind integer, field integer, t real, rid integer, value real, delta real,
    primary key (kind, field, t, rid)) without rowid;
create index if not exists number_log_rid on number_log(rid);
create table if not exists numbers (rid integer, field integer, kind integer, value real, t real,
    primary key (rid, field)) without rowid;
create index if not exists numbers_kind on numbers(kind, field, value);
"""

COLS = "rid, id, kind, state, first, last, newest, entered, n, latest, arrived, raw, raw_first, body"


def touches(e: dict) -> list[str]:
    """The top-level fields an event may change in its item's fold (``*``: any; more is safe, never fewer): a snapshot
    or a ``set`` any, a lease event its ``lease``, a patch the first key of each path, plain data its keys."""
    if e["type"] == SNAPSHOT or e.get("set") is not None:
        return ["*"]
    if e["type"].startswith(LEASE_PREFIX):
        return ["lease"]
    if e.get("patch") is not None:
        ops, out = e["patch"], []
        for o in ops if isinstance(ops, list) else [None]:
            for p in ((o.get("path"), *([o["from"]] if "from" in o else [])) if isinstance(o, dict) else [None]):
                if not isinstance(p, str) or not p.startswith("/"):
                    return ["*"]
                out.append(p[1:].split("/")[0].replace("~1", "/").replace("~0", "~"))
        return out
    d = e.get("data")
    return list(d) if isinstance(d, dict) else [] if d is None else ["*"]


def kinds_key(spec) -> tuple:
    """What a fold depends on in the model: its item kinds (a change being tried shares the index
    when it leaves them as they are)."""
    return tuple((k.name, k.id, tuple(k.states), tuple(sorted(k.on.items())), tuple(sorted(k.fold.items())),
                  tuple(sorted(getattr(k, "relations", None) or {})), getattr(k, "about", None),
                  *((tuple(sorted(k.moves_from.items())),) if getattr(k, "moves_from", None) else ()),
                  *((("if-unchanged", tuple(k.if_unchanged)),) if getattr(k, "if_unchanged", None) else ()),
                  *((("final", tuple(sorted(k.final))),) if getattr(k, "final", None) else ()))
                 for k in (getattr(spec, "items", None) or {}).values())


def state_dir(events) -> Path | None:
    """The record's state directory, where its index is kept; None for a record without one."""
    d = getattr(events, "dir", None)              # the segmented log: <state>/events
    if d is not None:
        return Path(d).parent
    p = getattr(events, "path", None)             # SQLite: <state>/events.db
    return Path(p).parent if p is not None and str(p) != ":memory:" else None


def done_states(kind, left: set[str], declared: dict | None = None) -> list[str]:
    """What a kind counts as finished: the states ``messages: {done:}`` declares for it (``declared``);
    else the states after the first that no item has left (``left``), or its last state when every
    one has been left."""
    if declared and declared.get(kind.name):
        return list(declared[kind.name])
    if not kind.states:
        return []
    done = [s for s in kind.states[1:] if s not in left]
    return done or kind.states[-1:]


def _lock_path(path: Path) -> Path:
    return path.with_suffix(".lock")             # <hash>.db: <hash>.lock


def _retired(path: Path) -> Path:
    return path.with_suffix(".retired")


def _hold(path: Path) -> int:
    """A shared lock on the index file's lock file, held while the file is open: no other process
    deletes the file meanwhile. Waits out one that is deleting it, and then holds the new one."""
    lp = _lock_path(path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    while True:
        fd = os.open(lp, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            if os.fstat(fd).st_ino == os.stat(lp).st_ino:
                return fd
        except FileNotFoundError:
            pass                                    # deleted while we waited: take the new one
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)


def _take(path: Path) -> int | None:
    """The exclusive lock on an index file, without waiting: None while any process has it open."""
    lp = _lock_path(path)
    try:
        fd = os.open(lp, os.O_RDWR | os.O_CREAT, 0o644)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.fstat(fd).st_ino == os.stat(lp).st_ino:
            return fd
    except OSError:
        pass
    os.close(fd)
    return None


def _remove(path: Path, fd: int) -> None:
    """An index file deleted, with its WAL, shared memory and lock file, under its exclusive lock ``fd``."""
    try:
        for suf in ("", "-wal", "-shm"):
            Path(str(path) + suf).unlink(missing_ok=True)
        _lock_path(path).unlink(missing_ok=True)
    finally:
        os.close(fd)


def _current(d: Path, h: str) -> Path:
    """The file this fold's index is kept in: ``<hash>.db``, or the next name after those retired."""
    n = 0
    while True:
        p = d / (f"{h}.db" if n == 0 else f"{h}.{n}.db")
        if not _retired(p).exists():
            return p
        n += 1


def retired(p: Path) -> bool:
    """Whether an index file is retired: its mark ``<hash>[.n].retired`` stands beside it (it is never opened again)."""
    return _retired(p).exists()


def files(d: Path) -> tuple[list[Path], list[Path]]:
    """The index files in the items folder ``d``, (live, retired): only regular files named ``<hash>[.n].db`` directly
    in ``d`` (resolved), never a symlink or anything else. OSError when ``d`` is missing or cannot be listed."""
    root = d.resolve(strict=True)
    live, old = [], []
    for e in os.scandir(root):
        p = root / e.name
        try:
            if NAME.match(e.name) and stat.S_ISREG(os.lstat(p).st_mode) and p.resolve().parent == root:
                (old if retired(p) else live).append(p)
        except FileNotFoundError:
            pass                                     # deleted meanwhile by another process's tidy
    return live, old


def _touched(p: Path) -> float:
    """When an index file last changed: its WAL takes the writes between checkpoints."""
    t = 0.0
    for suf in ("", "-wal", "-shm"):
        try:
            t = max(t, os.lstat(str(p) + suf).st_mtime)
        except OSError:
            pass
    return t


_GUARD = threading.local()


def _healing(f):
    """An index method, run under the index's lock, that, when the file cannot be read (not a database, malformed),
    builds it again from the record and runs once more; the caller never sees the error. The lock: the index's one
    connection is shared by the process's threads (the page's requests, the engine, the estimates), and two of them
    stepping it at once break each other's reads (the same query run twice at once shares SQLite's prepared
    statement, and one is handed a row of nothing: ``not enough values to unpack``)."""
    @functools.wraps(f)
    def run(self, *a, **k):
        with self.lock:
            if getattr(_GUARD, "on", False):         # inside another guarded call: the outermost heals
                return f(self, *a, **k)
            _GUARD.on = True
            try:
                return f(self, *a, **k)
            except sqlite3.DatabaseError as e:
                if not damaged(e, io=True):
                    raise
                self._heal(e)
                return f(self, *a, **k)
            finally:
                _GUARD.on = False
    return run


class Index:
    """One fold's index: followed by ``catch_up``, read by the queries below (each after one)."""

    def __init__(self, path: Path, spec, transcript: bool, idle: float = IDLE):
        self.path, self.spec, self.transcript, self.idle = path, spec, transcript, idle
        self.kinds = dict(getattr(spec, "items", None) or {})
        self.lock = threading.RLock()
        self._db: sqlite3.Connection | None = None
        self._held: int | None = None                 # the shared lock on ``<file>.lock`` while open
        self._events = None                           # the record last followed (to build it again from)
        self._kind_of: dict[str, object] = {}
        self._forget()

    def _forget(self) -> None:
        """Nothing of the index kept in memory: read again from disk when next asked."""
        self.names: dict[str | None, int | None] = {None: None}
        self.rnames: dict[int | None, str | None] = {None: None}
        self.cache: OrderedDict[str, tuple[Item, int, float | None]] = OrderedDict()   # id: (fold state, raw, raw_first)
        self.seq, self.gen = -1, None
        self._left: dict[str, set[str]] = {}

    @property
    def db(self) -> sqlite3.Connection:
        """The index's connection, opened when first used (and again after ``close``). Used under ``lock``."""
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self._held is None:
                self._held = _hold(self.path)
            c = sqlite3.connect(str(self.path), timeout=600, isolation_level=None, check_same_thread=False)
            try:
                c.execute("pragma journal_mode=wal")
                c.execute("pragma synchronous=normal")
                c.execute("pragma cache_size=-16000")         # 16 MB of pages, at most
                c.execute("pragma temp_store=memory")
                c.executescript(SCHEMA + projections.SCHEMA)   # (an older layout is another file: its name holds VERSION)
            except BaseException:
                c.close()
                raise
            self._db = c
            self._forget()
            self._load_names()
        return self._db

    # ---- names: kinds, states and types as numbers

    def _load_names(self) -> None:
        with self.lock:                                  # (a name asked for by any thread: see ``_healing``)
            for i, n in self.db.execute("select id, name from names"):
                self.names[n], self.rnames[i] = i, n

    def nid(self, name: str | None) -> int | None:
        got = self.names.get(name, -1)
        if got != -1:
            return got
        with self.lock:
            self.db.execute("insert or ignore into names(name) values (?)", (name,))
            i = self.db.execute("select id from names where name = ?", (name,)).fetchone()[0]
        name = sys.intern(name)
        self.names[name], self.rnames[i] = i, name
        return i

    def name(self, i: int | None) -> str | None:
        if i is not None and i not in self.rnames:          # (none is no name: never read them all again for it)
            self._load_names()
        return self.rnames.get(i)

    def known(self, name: str | None) -> int | None:
        """A name's number, or -1 when nothing in the index has it (a query of it matches nothing)."""
        if name not in self.names:
            self._load_names()
        return self.names.get(name, -1)

    def kind(self, id: str):
        k = self._kind_of.get(id, False)
        if k is False:
            k = kind_of(self.spec, id) if self.kinds else None
            if len(self._kind_of) > 200_000:
                self._kind_of.clear()
            self._kind_of[id] = k
        return k

    # ---- following the record

    def _meta(self, key: str, default=None):
        with self.lock:
            r = self.db.execute("select value from meta where key = ?", (key,)).fetchone()
        return r[0] if r else default

    def _set_meta(self, **kv) -> None:
        for k, v in kv.items():
            self.db.execute("insert into meta(key, value) values (?, ?) on conflict(key) do update set value = excluded.value",
                            (k, v))

    @_healing
    def catch_up(self, events) -> None:
        """Fold what the record holds that the index does not (by ``seq``), a chunk per transaction."""
        self._events = events
        gen, last = events.generation(), events.last_seq()
        if gen == self.gen and last == self.seq:
            return
        skip = () if self.transcript else (TRANSCRIPT_TYPES,)
        with self.lock:
            while True:
                self.db.execute("begin immediate")
                try:
                    gen, last = events.generation(), events.last_seq()     # read again under the lock: another process
                    done = self._step(events, gen, last, skip)             # may have folded what came after
                    self.db.execute("commit")
                except BaseException:
                    try:
                        self.db.execute("rollback")
                    except sqlite3.Error:
                        pass                                       # (a file that cannot be read: healed above)
                    self.cache.clear()
                    self.seq = -1
                    raise
                if done:
                    return

    def _heal(self, e: Exception) -> None:
        """The file cannot be read: deleted (or, while another process has it open, retired for the
        next name) and built again from the record."""
        with self.lock:
            log.warning("ergostat: the item index %s could not be read (%s); building it again from the record",
                        self.path, e)
            self.close()
            fd = _take(self.path)
            if fd is not None:
                _remove(self.path, fd)
            else:
                _retired(self.path).touch()
                self.path = _current(self.path.parent, self.path.name.split(".")[0])
            self._forget()
            if self._events is not None:
                self.catch_up.__wrapped__(self, self._events)

    def guard(self, fn):
        """``fn()``, which reads the index's file directly, under the index's lock, healed and run again when the file
        cannot be read."""
        return _healing(lambda self: fn())(self)

    @contextlib.contextmanager
    def reading(self):
        """A connection of its own to the index's file, opened read only (``mode=ro``), under the file's shared lock, so
        no process deletes the file while it is read; closed after (the SQL data source: datasources/sql.py)."""
        with self.lock:
            path = self.path
        held = _hold(path)
        try:
            c = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False, timeout=5,
                                isolation_level=None)
            try:
                yield c
            finally:
                c.close()
        finally:
            os.close(held)

    def moved_to(self, path: Path) -> None:
        """Another process retired this file: the next one is opened instead."""
        with self.lock:
            self.close()
            self.path = path
            self._forget()

    def _step(self, events, gen: int, last: int, skip) -> bool:
        """Under the write lock: one chunk folded. True when the index is up to ``last``."""
        seq = int(self._meta("seq", 0))
        if seq != self.seq:                                 # another process wrote it: what is kept here may be stale
            self.cache.clear()
            self._left.clear()
        if self._meta("version") != VERSION or self._meta("gen") is None or last < seq or gen < int(self._meta("gen")):
            self._reset()                                   # a new index, or a record that went back: fold it all again
            seq = 0
        elif int(self._meta("gen")) != gen:
            self._reconcile(events)                         # events taken out (rolled up, pruned): items gone go
            projections.again(self, events, seq)            # and what the status reads folded again from what is left
        self._set_meta(gen=gen)
        new = events.of_items(None, after_seq=seq, skip=skip, limit=CHUNK)
        top = max([seq, *(e["seq"] for e in new)])
        finished = len(new) < CHUNK
        if finished:
            top = max(top, last)                            # every item event up to ``last`` is folded
        got, other = projections.loose(events, seq, top, CHUNK)
        if len(got) >= CHUNK:                             # as many of the status's own: up to the last of them
            top, finished = got[-1]["seq"], False
            new = [e for e in new if e["seq"] <= top]
        self._fold(new)
        projections.follow(self, sorted(new + other, key=lambda e: e["seq"]))
        self._set_meta(seq=top)
        self.seq, self.gen = top, gen
        return finished

    def _reset(self) -> None:
        for t in ("items", "moves", "left", "reached", "links", "number_log", "numbers", "names", "meta", *projections.TABLES):
            self.db.execute(f"delete from {t}")
        self.names, self.rnames = {None: None}, {None: None}
        self.cache.clear()
        self._left.clear()
        self._set_meta(version=VERSION, epoch=uuid.uuid4().hex)   # (what follows its rows sees it was made again: counts.py)

    def _reconcile(self, events) -> None:
        """After events were taken out: an item none of whose events is left is forgotten."""
        live = events.item_ids()
        gone = [(rid,) for rid, id in self.db.execute("select rid, id from items") if id not in live]
        if gone:
            self.db.executemany("delete from moves where rid = ?", gone)
            self.db.executemany("delete from links where rid = ?", gone)
            self.db.executemany("delete from number_log where rid = ?", gone)
            self.db.executemany("delete from numbers where rid = ?", gone)
            self.db.executemany("delete from items where rid = ?", gone)
            dead = {r[0] for r in gone}
            for id in [i for i, (it, *_) in self.cache.items() if getattr(it, "rid", None) in dead]:
                self.cache.pop(id, None)

    def _fold(self, new: list[dict]) -> None:
        by: dict[str, list[dict]] = {}
        for e in new:
            by.setdefault(e["item"], []).append(e)
        if not by:
            return
        have = {id: x for id in by if (x := self.cache.pop(id, None)) is not None}
        rows = self._rows_of([id for id in by if id not in have])
        now = time.time()
        for id, evs in by.items():
            k = self.kind(id)
            got = have.get(id)
            row = rows.get(id)
            if got is not None:
                it, raw, raw_first = got
                rid, arrived, newest = it.rid, it.arrived, it.newest            # type: ignore[attr-defined]
            elif row is not None:
                it = self._item(row)
                rid, arrived, newest, raw, raw_first = row[0], row[10], row[6], row[11], row[12]
            else:
                it, rid, arrived, newest, raw, raw_first = None, None, None, None, 0, None
            touched, dis = (dict(getattr(it, "touched", {})), getattr(it, "dis", None)) if it is not None else ({}, None)
            it, numbered, renumbered = itemnumbers.follow(id, evs, k, it, self.transcript, fold)
            restored = False
            for e in evs:
                if e["type"] == SNAPSHOT:
                    raw, raw_first, restored = 0, None, True
                else:
                    if not raw:
                        raw_first = e["time"]
                    raw += 1
                if newest is not None and e["time"] < newest:     # out of time order: around it, what came by a
                    dis = [min(dis[0], e["time"]), max(dis[1], newest)] if dis else [e["time"], newest]   # moment
                newest = e["time"] if newest is None else max(newest, e["time"])                 # is no seq's prefix
                for f in touches(e):
                    touched[f] = max(touched.get(f, e["time"]), e["time"])
            it.touched, it.dis = touched, dis                                        # type: ignore[attr-defined]
            if (restored or arrived is None) and it.moves:
                arrived = it.moves[0]["time"]
            values = (self.nid(it.kind), self.nid(it.state), it.first, it.last, newest, it.entered, it.n,
                      self.nid(it.latest), arrived, raw, raw_first,
                      codec.pack({"f": it.fields, "r": it.refused, "o": it.rolled, "t": touched, "d": dis}),
                      text_of(it.fields))
            if rid is None:
                rid = self.db.execute("insert into items(id, kind, state, first, last, newest, entered, n, latest, arrived, "
                                      "raw, raw_first, body, text) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (id, *values)).lastrowid
            else:
                self.db.execute("update items set kind=?, state=?, first=?, last=?, newest=?, entered=?, n=?, latest=?, "
                                "arrived=?, raw=?, raw_first=?, body=?, text=? where rid=?", (*values, rid))
            if restored:
                self.db.execute("delete from moves where rid = ?", (rid,))
            self._keep_numbers(rid, it, numbered, renumbered)
            if k is not None and (k.relations or k.about):     # its links, as its fields now hold them
                self.db.execute("delete from links where rid = ?", (rid,))
                got = links_of(k, it.fields) + [(ABOUT, t) for t in parts_named(it.fields.get(k.about) if k.about else None)]
                if got:
                    self.db.executemany("insert into links(rid, rel, dst) values (?,?,?)",
                                        [(rid, self.nid(r), t) for r, t in got])
            if it.moves:
                kn = self.nid(it.kind)
                self.db.executemany("insert into moves(rid, kind, t, frm, dst, event, type) values (?,?,?,?,?,?,?)",
                                    [(rid, kn, m["time"], self.nid(m["from"]), self.nid(m["to"]), m["event"], self.nid(m["type"]))
                                     for m in it.moves])
                left = {(kn, self.nid(m["from"])) for m in it.moves if m["from"] is not None}
                self.db.executemany("insert or ignore into left(kind, state) values (?, ?)", left)
                self.db.executemany("insert or ignore into reached(kind, state) values (?, ?)",
                                    {(kn, self.nid(m["to"])) for m in it.moves})
                if left and it.kind in self._left:
                    self._left[it.kind] |= {m["from"] for m in it.moves if m["from"] is not None}
                it.moves = []                                # on disk: what is kept in memory is the rest of the fold
            it.rid, it.arrived, it.newest = rid, arrived, newest                 # type: ignore[attr-defined]
            if self._open(it, k, now):
                self.cache[id] = (it, raw, raw_first)
        while len(self.cache) > CACHED:
            self.cache.popitem(last=False)

    def _keep_numbers(self, rid: int, it: Item, rows: list[tuple], restored: bool) -> None:
        """An item's changes of its numeric fields written (``restored``: a snapshot's history in place of what was
        kept), and its value now of each. Two changes of one field at one moment are one row: the last value, their
        deltas added, however the events were split into chunks."""
        if restored:
            self.db.execute("delete from number_log where rid = ?", (rid,))
            self.db.execute("delete from numbers where rid = ?", (rid,))
        if not rows or it.kind is None:              # an item of no kind has no field to chart
            return
        kn = self.nid(it.kind)
        self.db.executemany(
            "insert into number_log(kind, field, t, rid, value, delta) values (?,?,?,?,?,?) "
            "on conflict(kind, field, t, rid) do update set value = excluded.value, delta = delta + excluded.delta",
            [(kn, self.nid(f), t, rid, v, d) for f, t, v, d in rows])
        latest: dict[str, float] = {}
        for f, t, _, _ in rows:
            latest[f] = max(t, latest.get(f, t))
        now = itemnumbers.values(it.fields)
        self.db.executemany("delete from numbers where rid = ? and field = ?",
                            [(rid, self.nid(f)) for f in latest if f not in now])
        self.db.executemany(
            "insert into numbers(rid, field, kind, value, t) values (?,?,?,?,?) "
            "on conflict(rid, field) do update set value = excluded.value, t = max(t, excluded.t)",
            [(rid, self.nid(f), kn, now[f], t) for f, t in latest.items() if f in now])

    def _open(self, it: Item, k, now: float) -> bool:
        """Whether an item is kept folded in memory: not finished, and touched within ``idle``."""
        if now - it.last > self.idle:
            return False
        if k is None or not k.states:
            return True
        declared = getattr(getattr(self.spec, "messages", None), "done", None)
        return it.state not in done_states(k, self.left(k.name), declared)

    def _rows_of(self, ids: list[str]) -> dict[str, tuple]:
        out = {}
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            for r in self.db.execute(f"select {COLS} from items where id in ({','.join('?' * len(part))})", part):
                out[r[1]] = r
        return out

    def _item(self, r: tuple, moves: list[dict] | None = None) -> Item:
        body = codec.unpack(r[13])
        it = Item(r[1], self.name(r[2]), self.name(r[3]), body["f"], r[4], r[5], r[7], r[8], self.name(r[9]) or "",
                  moves if moves is not None else [], [], body["r"], body.get("o", 0))
        it.touched, it.dis = body.get("t", {"*": 1e300}), body.get("d")          # type: ignore[attr-defined]
        return it

    # ---- reading it (after catch_up)

    @_healing
    def left(self, kind: str) -> set[str]:
        """The states of ``kind`` some item has left."""
        got = self._left.get(kind)
        if got is None:
            k = self.known(kind)
            got = {self.name(s) for (s,) in self.db.execute("select state from left where kind = ?", (k,))}
            self._left[kind] = got
        return got

    @_healing
    def reached(self, kind: str) -> set[str]:
        """The states of ``kind`` some item has reached."""
        k = self.known(kind)
        return {self.name(s) for (s,) in self.db.execute("select state from reached where kind = ?", (k,))}

    @_healing
    def changed_after(self, t: float | None) -> bool:
        """Whether any item has an event after ``t`` (else nothing need be left out as of then)."""
        return t is not None and self.db.execute("select 1 from items where newest > ? limit 1", (t,)).fetchone() is not None

    def _where(self, kind: str | None, states=None, until: float | None = None, words=()) -> tuple[str, list]:
        """``kind`` (None: any; ``""``: items of no kind), in ``states`` (None: any; ``""`` among them: no state), whose
        text holds every one of ``words`` (casefolded: ``items.words``)."""
        sql, args = [], []
        if words and self.db.execute("select 1 from items where text is null limit 1").fetchone():
            self._set_meta(version=0)                       # a row without its text (items_textless: one lookup) is
            #                                                 never read as no match: rebuilt
            self.seq = -1
            self.catch_up.__wrapped__(self, self._events)
        for w in words:
            sql.append("instr(text, ?) > 0")                # a plain substring: no wildcard to escape
            args.append(w)
        if kind == "":
            sql.append("kind is null")
        elif kind is not None:
            sql.append("kind = ?")
            args.append(self.known(kind))
        if states is not None:
            named = [self.known(x) for x in states if x]
            parts = [f"state in ({','.join('?' * len(named))})"] if named else []
            args += named
            if any(not x for x in states):
                parts.append("state is null")
            sql.append("(" + " or ".join(parts) + ")" if parts else "0")
        if until is not None and self.changed_after(until):
            sql.append("newest <= ?")                       # only when some item changed since: else it reads every row
            args.append(until)
        return (" where " + " and ".join(sql)) if sql else "", args

    @_healing
    def late(self, until: float, kind: str | None = None, limit: int | None = None) -> list[str]:
        """The items with an event after ``until`` (``kind``'s only, when given)."""
        w, a = self._where(kind)
        w = (w + " and " if w else " where ") + "newest > ?"
        return [r[0] for r in self.db.execute(f"select id from items{w}" + (f" limit {int(limit)}" if limit else ""), (*a, until))]

    @_healing
    def still(self, ids, keys, at: float) -> set[str]:
        """Of ``ids``, those whose fields ``keys`` (``lease.back``: ``lease``'s too) no event after ``at`` may have
        changed (``touches``), and whose events came in time order around ``at``: what came by then is a prefix of
        their fold, so those fields now, and their moves up to ``at``, are theirs as of then."""
        roots = {"*", *keys, *(k.split(".", 1)[0] for k in keys)}
        out = set()
        for r in self._rows_of(list(ids)).values():
            b = codec.unpack(r[13])
            t, d = b.get("t", {"*": 1e300}), b.get("d")
            if all(t.get(k, -1e300) <= at for k in roots) and not (d and d[0] <= at < d[1]):
                out.add(r[1])
        return out

    @_healing
    def total(self, kind: str | None = None) -> int:
        w, a = self._where(kind)
        return self.db.execute(f"select count(*) from items{w}", a).fetchone()[0]

    @_healing
    def counts(self, until: float | None = None) -> dict[str, dict[str, int]]:
        """Per kind (``""``: none), how many items in each state (``""``: none)."""
        w, a = self._where(None, until=until)
        out: dict[str, dict[str, int]] = {}
        for k, s, n in self.db.execute(f"select kind, state, count(*) from items{w} group by kind, state", a):
            c = out.setdefault(self.name(k) or "", {})
            c[self.name(s) or ""] = c.get(self.name(s) or "", 0) + n
        return out

    @_healing
    def in_window(self, since: float, until: float) -> dict[str, tuple[int, int]]:
        """Per kind, of the items with no event after ``until``: how many arrived in ``[since, until]``, and how many had
        an event in it (the Items page's overview, ``items_overview.py``)."""
        w, a = self._where(None, until=until)
        w = (w + " and " if w else " where ") + "last >= ? and first <= ?"
        rows = self.db.execute(f"select kind, sum(arrived >= ? and arrived <= ?), count(*) from items{w} group by kind",
                               (since, until, *a, since, until))
        return {self.name(k) or "": (int(n_in or 0), n) for k, n_in, n in rows}

    @_healing
    def count(self, kind: str | None, states=None, until: float | None = None, words=()) -> int:
        w, a = self._where(kind, states, until, words)
        return self.db.execute(f"select count(*) from items{w}", a).fetchone()[0]

    @_healing
    def items(self, kind: str | None = None, states=None, until: float | None = None, n: int | None = None,
              offset: int = 0, moves: bool = True, ids=None, has: str | None = None, words=()) -> list[Item]:
        """Items, the latest first (by their last event): ``n`` of them from ``offset``, with their moves;
        among ``ids``, with ``has`` in their id, or holding every one of ``words``, when given."""
        w, a = self._where(kind, states, until, words)
        if has is not None:
            w = (w + " and " if w else " where ") + "instr(id, ?) > 0"
            a = [*a, has]
        if ids is not None:
            ids = list(ids)
            if not ids:
                return []
            rows = []
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                ww = (w + " and " if w else " where ") + f"id in ({','.join('?' * len(part))})"
                rows += self.db.execute(f"select {COLS} from items{ww}", (*a, *part)).fetchall()
            rows.sort(key=lambda r: -r[5])
        else:
            lim = f" limit {int(n)} offset {int(offset)}" if n is not None else ""
            rows = self.db.execute(f"select {COLS} from items{w} order by last desc{lim}", a).fetchall()
        mv = self.moves_of([r[0] for r in rows]) if moves else {}
        return [self._item(r, mv.get(r[0], [])) for r in rows]

    @_healing
    def moves_of(self, rids: list[int]) -> dict[int, list[dict]]:
        out: dict[int, list[dict]] = {}
        if len(rids) > 2000:
            got = self.db.execute("select rid, t, frm, dst, event, type from moves order by rowid")
            want = set(rids)
            rows = (r for r in got if r[0] in want)
        else:
            rows = (r for i in range(0, len(rids), 500) for r in self.db.execute(
                f"select rid, t, frm, dst, event, type from moves where rid in ({','.join('?' * len(rids[i:i + 500]))}) "
                "order by rowid", rids[i:i + 500]))
        for rid, t, f, d, ev, ty in rows:
            out.setdefault(rid, []).append({"time": t, "from": self.name(f), "to": self.name(d), "event": ev, "type": self.name(ty)})
        return out

    @_healing
    def moved(self, kind: str, key: str, state: str | None, since: float, until: float,
              until_newest: float | None = None) -> list[tuple[str, float]]:
        """(item, time) of each move of ``kind``'s items into (``key`` "to") or out of ("from") ``state``,
        with ``since <= time <= until``; items with an event after ``until_newest`` left out."""
        col = "dst" if key == "to" else "frm"
        k, s = self.known(kind), self.known(state)
        if k == -1 or s == -1:
            return []
        if not self.changed_after(until_newest):
            until_newest = None
        extra, args = "", [k, s, since, until]
        if until_newest is not None:
            extra = " and i.newest <= ?"
            args.append(until_newest)
        return self.db.execute(f"select i.id, m.t from moves m join items i on i.rid = m.rid where m.kind = ? and m.{col} = ? "
                               f"and m.t >= ? and m.t <= ?{extra} order by m.t", args).fetchall()

    @_healing
    def transitions(self, kind: str, at_once: bool = False) -> dict:
        """How many times ``kind``'s items moved from one state to another (``(None, S)``: arrivals), a lease's hold
        taken out: a move into ``leased`` and the move out of it are one move, from the state it was taken from.
        ``at_once``: an item whose first event moved it on from the kind's first state (it arrived in a later state:
        reopened in the outside system, say) counts as arriving in the state that event left it in."""
        from collections import Counter
        out: Counter = Counter()
        with self.lock:                                  # (its connection is shared by the process's threads)
            k = self.known(kind)
            if k == -1:
                return out
            rid0, back, came = None, None, None
            for rid, f, d, ev in self.db.execute("select rid, frm, dst, event from moves where kind = ? order by rid, rowid",
                                                 (k,)):
                if rid != rid0:
                    rid0, back, came = rid, None, None
                frm, to = self.name(f), self.name(d)
                if at_once and came is not None and ev == came[0] and frm == came[1] and to != "leased":
                    out[(None, frm)] -= 1                 # the event it arrived by moved it on: it arrived there
                    if not out[(None, frm)]:
                        del out[(None, frm)]
                    out[(None, to)] += 1
                    came = (ev, to)
                    continue
                came = (ev, to) if frm is None else None
                if to == "leased":
                    back = frm if frm != "leased" else back
                    continue
                if frm == "leased":
                    frm = back
                if frm != to:
                    out[(frm, to)] += 1
        return out

    @_healing
    def tally(self, kind: str, state: str, key: str, before: float, until_newest: float | None = None) -> int:
        """How many moves of ``kind``'s items into (or out of) ``state`` were at or before ``before``."""
        col = "dst" if key == "to" else "frm"
        k, s = self.known(kind), self.known(state)
        if k == -1 or s == -1:
            return 0
        if not self.changed_after(until_newest):
            until_newest = None
        if until_newest is None:
            return self.db.execute(f"select count(*) from moves where kind = ? and {col} = ? and t <= ?", (k, s, before)).fetchone()[0]
        return self.db.execute(f"select count(*) from moves m join items i on i.rid = m.rid where m.kind = ? and m.{col} = ? "
                               "and m.t <= ? and i.newest <= ?", (k, s, before, until_newest)).fetchone()[0]

    @_healing
    def finished(self, kind: str, done: list[str], since: float, until: float,
                 until_newest: float | None = None) -> list[tuple[str, float, float]]:
        """(item, when it first entered a finished state, when it arrived) for each of ``kind``'s items
        that first finished between ``since`` and ``until``."""
        k = self.known(kind)
        ds = [x for x in (self.known(d) for d in done) if x != -1]
        if k == -1 or not ds:
            return []
        if not self.changed_after(until_newest):
            until_newest = None
        into = f"m.kind = ? and m.dst in ({','.join('?' * len(ds))})"
        extra, args = "", [k, *ds, k, *ds, since, until]
        if until_newest is not None:
            extra = " and i.newest <= ?"
            args.append(until_newest)
        rows = self.db.execute(                       # those that finished in the window: then when each first did
            f"select i.id, min(m.t), i.arrived from moves m join items i on i.rid = m.rid where {into} and m.rid in "
            f"(select m.rid from moves m where {into} and m.t >= ? and m.t <= ?){extra} group by m.rid", args).fetchall()
        return [r for r in rows if since <= r[1] <= until]

    @_healing
    def links_from(self, ids) -> list[tuple[str, str, str]]:
        """(item, relation, the id it names) of each link the items ``ids`` hold (the ``@about`` links are not to items)."""
        ids, out = list(ids), []
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            out += [(a, self.name(r), d) for a, r, d in self.db.execute(
                f"select i.id, l.rel, l.dst from links l join items i on i.rid = l.rid where i.id in ({','.join('?' * len(part))})",
                part) if self.name(r) != ABOUT]
        return out

    @_healing
    def links_to(self, ids) -> list[tuple[str, str, str]]:
        """(item, relation, the id it names) of each link naming one of ``ids``: the inverse direction."""
        ids, out = list(ids), []
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            out += [(a, self.name(r), d) for a, r, d in self.db.execute(
                f"select i.id, l.rel, l.dst from links l join items i on i.rid = l.rid where l.dst in ({','.join('?' * len(part))})",
                part) if self.name(r) != ABOUT]
        return out

    @_healing
    def about(self, parts=None) -> list[tuple[str, str]]:
        """(item, part) for each item that names one of the model's ``parts`` (None: any) in its kind's ``about:`` field:
        the link rows only, by the index on the part named."""
        rel = self.known(ABOUT)
        if rel == -1:
            return []
        sql, args = "select i.id, l.dst from links l join items i on i.rid = l.rid where l.rel = ?", [rel]
        if parts is None:
            return [tuple(r) for r in self.db.execute(sql, args)]
        parts, out = list(parts), []
        for i in range(0, len(parts), 500):
            part = parts[i:i + 500]
            out += [tuple(r) for r in self.db.execute(f"{sql} and l.dst in ({','.join('?' * len(part))})", (*args, *part))]
        return out

    @_healing
    def links(self, rels=None, limit: int | None = None) -> list[tuple[str, str, str]]:
        """Every link (of the relations ``rels``, when given): (item, relation, the id it names)."""
        sql, args = "select i.id, l.rel, l.dst from links l join items i on i.rid = l.rid", []
        if rels is not None:
            named = [x for x in (self.known(r) for r in rels) if x != -1]
            if not named:
                return []
            sql += f" where l.rel in ({','.join('?' * len(named))})"
            args = named
        if limit:
            sql += f" limit {int(limit)}"
        return [(a, self.name(r), d) for a, r, d in self.db.execute(sql, args)]

    @_healing
    def stays(self, kind: str, most: int = 2000, finished=(), until: float | None = None
              ) -> tuple[dict[str, list[float]], dict[str, int], int]:
        """How long ``kind``'s items stayed in each state they left (a lease's hold, ``leased``, is a state of its own
        here: the work), over the moves of its ``most`` latest items; and, of those now in a ``finished`` state, how
        many stays each state had and how many such items there are (how often an item visits each state). With
        ``until``: as of then, only the moves at or before it, the ``most`` items whose latest such move is latest, and
        finished meaning their last move by then was into a finished state."""
        k = self.known(kind)
        if k == -1:
            return {}, {}, 0
        fin = {x for x in (self.known(f) for f in finished) if x != -1}
        if until is None:
            rows = self.db.execute(
                "select m.rid, m.t, m.dst, i.state from moves m join items i on i.rid = m.rid where m.kind = ? and m.rid in "
                "(select rid from items where kind = ? order by last desc limit ?) order by m.rid, m.rowid", (k, k, int(most)))
        else:
            rows = self.db.execute(
                "select rid, t, dst, null from moves where kind = ? and t <= ? and rid in (select rid from moves where "
                "kind = ? and t <= ? group by rid order by max(t) desc limit ?) order by rid, rowid", (k, until, k, until, int(most)))
        by: dict[int, list[tuple]] = {}
        for rid, t, d, now in rows:
            by.setdefault(rid, []).append((t, d, now))
        out: dict[str, list[float]] = {}
        visits: dict[str, int] = {}
        done: set[int] = set()
        for rid, ms in by.items():
            now = ms[-1][1] if until is not None else ms[-1][2]        # its state now, or its last move's by then
            for (t0, st0, _), (t, _, _) in zip(ms, ms[1:], strict=False):
                if st0 is None:
                    continue
                name = self.name(st0)
                out.setdefault(name, []).append(max(0.0, t - t0))
                if now in fin:
                    visits[name] = visits.get(name, 0) + 1
                    done.add(rid)
        return out, visits, len(done)

    @_healing
    def candidates(self) -> list[tuple[str, str | None, float]]:
        """(item, kind, the time of its first event since its snapshot) of each item with events a
        roll-up could take (``rollup.plan``)."""
        return [(id, self.name(k), t) for id, k, t in self.db.execute("select id, kind, raw_first from items where raw > 0")]

    @_healing
    def rolled(self, rest: dict[str, list[tuple[int, float]]]) -> None:
        """After a roll-up: each item's events left outside its snapshot (seq, time), so it is a
        candidate again only once one of them is due (those the index has not folded yet count when it does)."""
        with self.lock:
            self.db.execute("begin immediate")
            try:
                seq = int(self._meta("seq", 0))
                rows = []
                for id, evs in rest.items():
                    mine = [t for q, t in sorted(evs) if q <= seq]
                    rows.append((len(mine), mine[0] if mine else None, id))
                    got = self.cache.get(id)
                    if got is not None:
                        self.cache[id] = (got[0], len(mine), mine[0] if mine else None)
                self.db.executemany("update items set raw = ?, raw_first = ? where id = ?", rows)
                self.db.execute("commit")
            except BaseException:
                self.db.execute("rollback")
                raise

    records = _healing(projections.records)          # what the status reads (projections.py)
    marked = _healing(projections.marked)
    asked = _healing(projections.asked)
    newer = _healing(projections.newer)
    latest_of = _healing(projections.latest_of)
    ticks_of = _healing(projections.ticks_of)
    ticked = _healing(projections.ticked)
    amounts = _healing(projections.amounts)

    def close(self) -> None:
        """Its file closed (opened again when next used)."""
        with self.lock:
            if self._db is not None:
                self._db.close()
                self._db = None
            if self._held is not None:
                os.close(self._held)                  # (closing it lets the lock go)
                self._held = None


_OPEN: OrderedDict[str, Index] = OrderedDict()     # by fold (<items>/<hash>): one per process, whatever opened the record
_OPEN_LOCK = threading.Lock()
OPEN_MOST = 12                                      # indexes kept open at once (each holds its file, WAL and shm)


_PIN = threading.local()


@contextlib.contextmanager
def pinned():
    """Within it (on this thread), each index ``index_for`` gives is caught up once, by its first call: one answer (the
    status's) reads the record at one moment, and its hundreds of reads do not each look for what is new."""
    if getattr(_PIN, "got", None) is not None:
        yield
        return
    _PIN.got = {}
    try:
        yield
    finally:
        _PIN.got = None


def index_for(events, spec, transcript: bool) -> Index | None:
    """The index of this record's items for these kinds (opened once per process), caught up (once, while
    ``pinned``); None for a record kept nowhere on disk."""
    pin = getattr(_PIN, "got", None)
    key = (id(events), id(spec), transcript)
    if pin is not None and key in pin:
        return pin[key]
    ix = _index_for(events, spec, transcript)
    if pin is not None:
        pin[key] = ix
    return ix


def _index_for(events, spec, transcript: bool) -> Index | None:
    d = state_dir(events)
    if d is None or not hasattr(events, "generation"):
        return None
    key = kinds_key(spec)
    h = hashlib.sha1(repr((key, transcript, VERSION)).encode()).hexdigest()[:16]
    path = _current(d / "items", h)
    at = str(d / "items" / h)
    storage = getattr(spec, "storage", None)
    idle = getattr(storage, "item_idle", None) or IDLE
    with _OPEN_LOCK:
        ix = _OPEN.get(at)
        if ix is None:
            if not path.exists() and not upkept(spec):  # (under use: upkeep its tidier does it: SPEC §2a, Upkeep)
                with contextlib.suppress(OSError):    # (a folder that cannot be listed: nothing tidied, as before)
                    _tidy(path.parent, new=True)
            ix = _OPEN[at] = Index(path, spec, transcript, idle)
            while len(_OPEN) > OPEN_MOST:
                _OPEN.popitem(last=False)[1].close()
        elif ix.path != path:
            ix.moved_to(path)                       # retired by another process (healed, reindexed)
        _OPEN.move_to_end(at)
        ix.spec, ix.kinds, ix.idle = spec, dict(getattr(spec, "items", None) or {}), idle
    ix.catch_up(events)
    return ix


def upkept(spec) -> bool:
    """Whether the model hands the index files to ``use: upkeep`` (ergostat's own template): then the engine does not
    tidy them; the template's ``index-tidier`` block does (``library/run/upkeep.py``)."""
    return any(isinstance(u, dict) and u.get("template") == "upkeep" and not u.get("owners")
               for u in (getattr(spec, "uses", None) or {}).values())


def _tidy(d: Path, keep: int | None = None, new: bool = False) -> dict:
    """At most ``keep`` (``KEPT_FILES``) indexes per record, one fewer when one is about to be made (``new``): the
    least recently changed go, but only those no process has open (the exclusive lock taken without waiting) and none
    changed in ``TIDY_AGE``, checked again once the lock is held. Retired files go as soon as no process has them
    open, whatever their age (never opened again). Only index files (``files``) are touched. Returns how many live
    files were removed, retired ones removed, live ones left, and how many skipped as held or young; OSError when
    ``d`` exists and cannot be listed."""
    keep = KEPT_FILES if keep is None else keep
    out = {"removed": 0, "retired": 0, "left": 0, "held": 0, "young": 0}
    if not d.exists():
        return out
    live, old = files(d)
    for p in old:
        if (fd := _take(p)) is not None:
            _remove(p, fd)                          # (its mark stays: the name is not used again)
            out["retired"] += 1
        else:
            out["held"] += 1
    got = sorted(live, key=_touched)
    for p in got[:max(0, len(got) - keep + (1 if new else 0))]:
        if time.time() - _touched(p) < TIDY_AGE:
            out["young"] += 1
            continue
        if (fd := _take(p)) is None:
            out["held"] += 1
            continue
        if time.time() - _touched(p) < TIDY_AGE:     # changed between the look and the lock: kept
            os.close(fd)
            out["young"] += 1
            continue
        _remove(p, fd)
        out["removed"] += 1
    _unmark(d)
    out["left"] = len(files(d)[0])
    return out


def _unmark(d: Path) -> None:
    """The retired marks of a fold none of whose files is left: its next index starts at ``<hash>.db``."""
    for m in d.glob("*.retired"):
        h = m.name.split(".")[0]
        if not any(d.glob(f"{h}.*db")):
            m.unlink(missing_ok=True)


def reindex(events, spec) -> dict:
    """``ergostat compact --reindex``: every index of this record dropped, and this model's folds made
    again from the record. Returns how many items each holds and how long it took."""
    d = state_dir(events)
    if d is None:
        return {}
    with _OPEN_LOCK:
        for k in [k for k in _OPEN if Path(k).parent == d / "items"]:
            _OPEN.pop(k).close()
    for p in (d / "items").glob("*.db") if (d / "items").exists() else ():
        if (fd := _take(p)) is not None:
            _remove(p, fd)
        else:
            _retired(p).touch()                     # another process has it open: built again under the next name
    if (d / "items").exists():
        _unmark(d / "items")
    out = {}
    for tr in (False, True):
        t = time.time()
        ix = index_for(events, spec, tr)
        if ix is not None:
            with ix.lock:
                n = ix.total()
        out["transcript" if tr else "items"] = {"items": n if ix else 0, "seconds": round(time.time() - t, 2)}
    return out
