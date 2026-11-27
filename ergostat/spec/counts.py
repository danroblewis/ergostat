"""Counts of items kept as the record folds (docs/proposals/scale.md, #4): what a ``projection:`` sensor reads, at once,
instead of asking the item index for every reading (SPEC §5a, §9.1).

The item index (``itemindex.py``) already records every item (``items``) and every move of every item (``moves``),
whichever process folded them. ``Counts`` follows those two tables as they grow, by their row numbers:

- **how many** of each projection are in each state: a move takes one from the state it left and adds one to the state it
  reached; an item of a projection without states is counted when its row first appears;
- **groups**, for a sensor on a stock that needs more than a plain count (``where:``, ``measure: oldest`` or
  ``age``): the members themselves, with when each entered its state and was first seen, the oldest of each found in
  a heap. An item a move or an event touched is read again, so one whose fields or state changed joins or leaves;
- **windows**, for a sensor on a flow (``entering:`` or ``leaving:`` over ``over:``): the times of the moves into (or
  out of) the state, kept for the longest window asked; with ``where:``, each with its item, and whether that item
  matches now.

A count is of the record as the index has folded it: an event stamped later than the reading (another machine's
clock ahead of ours) counts at once, where a count asked of the index "as of now" leaves it out until its time.

Everything is rebuilt from the index when it starts, when the index was made again (its ``epoch``), when the record
went back, was rolled up or pruned (its generation), and when the model's kinds or its sensors change.
``tests/test_counts.py`` holds every value against a fresh count of the index."""

from __future__ import annotations

import bisect
import heapq
import json
import threading
import time
from types import SimpleNamespace

from . import codec
from .items import TRANSCRIPT_TYPES, asks_transcript, matches

SLACK = 60.0           # seconds of moves kept past the longest window (a reading's "now" is a little behind the clock)
INF = float("inf")


def transcript_of(spec, s) -> bool:
    """Which fold a sensor counts from: with a transcript's lines, when its projection moves on them or its ``where`` reads
    a field they fold into (as ``items.measure`` decides)."""
    q = s.items or {}
    k = spec.items.get(q.get("kind"))
    return bool(k) and asks_transcript([k], tuple(q.get("where") or {}))


def _wkey(where: dict | None) -> str:
    return json.dumps(where or {}, sort_keys=True, default=str)


def _wants(where: dict, fields: dict) -> bool:
    return matches(SimpleNamespace(fields=fields), where)


class Group:
    """The items of a projection in some states (``()``: any) matching ``where``: who they are, when each entered its state
    and was first seen."""

    def __init__(self, kind: str, states: tuple, where: dict):
        self.kind, self.where = kind, where
        self.states = frozenset(states) if states else None
        self.members: dict[int, tuple[float | None, float | None]] = {}
        self.heaps: tuple[list, list] = ([], [])        # (entered, rid), (first, rid): stale entries left until on top

    def put(self, rid: int, state, entered, first, fields) -> None:
        """An item read again: a member or not, as it is now."""
        if (self.states is None or state in self.states) and (not self.where or _wants(self.where, fields())):
            if self.members.get(rid) != (entered, first):
                self.members[rid] = (entered, first)
                for h, t in zip(self.heaps, (entered, first), strict=True):
                    if t is not None:
                        heapq.heappush(h, (t, rid))
        else:
            self.members.pop(rid, None)
        if len(self.heaps[0]) > 4 * len(self.members) + 64:     # mostly stale: made again from the members
            for i, h in enumerate(self.heaps):
                h[:] = [(m[i], r) for r, m in self.members.items() if m[i] is not None]
                heapq.heapify(h)

    def least(self, i: int) -> float | None:
        """The members' earliest time entered (0) or first seen (1)."""
        h = self.heaps[i]
        while h:
            t, rid = h[0]
            m = self.members.get(rid)
            if m is not None and m[i] == t:
                return t
            heapq.heappop(h)
        return None


class Window:
    """The moves of a projection's items into (``dst``) or out of (``frm``) a state, for the last ``over`` seconds at least:
    ``(time, item)``, in time order. With ``where``: whether each of their items matches it now."""

    def __init__(self, kind: str, col: str, state: str, where: dict, over: float):
        self.kind, self.col, self.state, self.where, self.over = kind, col, state, where, over
        self.moves: list[tuple[float, int]] = []
        self.rids: dict[int, int] = {}                  # item → its moves kept
        self.match: dict[int, bool] = {}

    def add(self, t: float, rid: int) -> None:
        bisect.insort(self.moves, (t, rid))
        self.rids[rid] = self.rids.get(rid, 0) + 1

    def trim(self, now: float) -> None:
        cut = bisect.bisect_right(self.moves, (now - self.over - SLACK, INF))
        for _, rid in self.moves[:cut]:
            left = self.rids[rid] - 1
            if left:
                self.rids[rid] = left
            else:
                del self.rids[rid]
                self.match.pop(rid, None)
        del self.moves[:cut]

    def count(self, since: float, until: float) -> int:
        lo = bisect.bisect_right(self.moves, (since, INF))
        hi = bisect.bisect_right(self.moves, (until, INF))
        if not self.where:
            return hi - lo
        return sum(1 for _, rid in self.moves[lo:hi] if self.match.get(rid))


class Counts:
    """One fold's counts (the item index with or without a transcript's lines), followed by ``follow`` and read by
    ``value``; used by one thread at a time (``lock``)."""

    def __init__(self, transcript: bool = False):
        self.transcript = transcript
        self.lock = threading.Lock()
        self.ix = None
        self.epoch = self.gen = self.shape = None
        self.n: dict[tuple, int] = {}                  # (kind, state) → how many
        self.total: dict[str | None, int] = {}         # kind → how many
        self.groups: dict[tuple, Group] = {}
        self.windows: dict[tuple, Window] = {}
        self.mv = self.rid = self.seq = 0             # the last move, item and event followed
        self.stateless: set = set()
        self.builds = 0

    @staticmethod
    def shape_of(sensors) -> tuple[dict, dict]:
        """The groups and windows these sensors read: ``(kind, states, where)`` and ``(kind, col, state, where)``."""
        groups: dict[tuple, dict] = {}
        windows: dict[tuple, tuple[dict, float]] = {}
        for s in sensors:
            q = s.items or {}
            where = q.get("where") or {}
            if not (q.get("entering") or q.get("leaving")):
                if where or q.get("measure") in ("oldest", "age"):
                    groups[(q["kind"], tuple(sorted(q.get("state") or ())), _wkey(where))] = where
            else:
                col, st = ("dst", q["entering"]) if q.get("entering") else ("frm", q.get("leaving"))
                key = (q["kind"], col, st, _wkey(where))
                over = float(q.get("over") or 3600.0)
                windows[key] = (where, max(over, windows.get(key, (None, 0.0))[1]))
        return groups, windows

    # ---- following the index

    def follow(self, events, spec, sensors, now: float | None = None) -> bool:
        """Brought up to date with the record (the index caught up first). False: there is no index (a record kept
        nowhere on disk): the caller counts as before."""
        from .itemindex import index_for
        ix = index_for(events, spec, self.transcript)
        if ix is None:
            return False
        now = time.time() if now is None else now
        groups, windows = self.shape_of(sensors)
        shape = (frozenset(groups), frozenset((k, o) for k, (_, o) in windows.items()))
        gen = events.generation() if hasattr(events, "generation") else None
        with self.lock, ix.lock:
            ix.guard(lambda: self._follow(ix, events, spec, gen, shape, groups, windows, now))
        return True

    def _follow(self, ix, events, spec, gen, shape, groups, windows, now: float) -> None:
        epoch = ix._meta("epoch")                       # (built again when the index was: its epoch is new)
        if ix is not self.ix or (epoch, gen, shape) != (self.epoch, self.gen, self.shape) or not self._apply(ix, events, now):
            self._build(ix, spec, groups, windows, now)
            self.ix, self.epoch, self.gen, self.shape = ix, epoch, gen, shape
        if gen is not None and events.generation() != gen:   # rolled up or pruned meanwhile: read whole next time
            self.gen = None

    def _build(self, ix, spec, groups: dict, windows: dict, now: float) -> None:
        db = ix.db
        self.builds += 1
        self.stateless = {None, *(k.name for k in spec.items.values() if not k.states)}
        db.execute("begin")                             # one moment of the index, whatever other processes fold
        try:
            self.mv = db.execute("select coalesce(max(rowid), 0) from moves").fetchone()[0]
            self.rid = db.execute("select coalesce(max(rid), 0) from items").fetchone()[0]
            self.seq = int(ix._meta("seq", 0))
            self.n, self.total = {}, {}
            for k, s, c in db.execute("select kind, state, count(*) from items group by kind, state").fetchall():
                kn, sn = ix.name(k), ix.name(s)
                self.n[(kn, sn)] = self.n.get((kn, sn), 0) + c
                self.total[kn] = self.total.get(kn, 0) + c
            self.groups = {}
            for (kind, states, wk), where in groups.items():
                g = self.groups[(kind, states, wk)] = Group(kind, states, where)
                k = ix.known(kind)
                if k == -1:
                    continue
                sql, args = "select rid, state, entered, first, body from items where kind = ?", [k]
                if states:
                    ids = [x for x in (ix.known(s) for s in states) if x != -1]
                    if not ids:
                        continue
                    sql += f" and state in ({','.join('?' * len(ids))})"
                    args += ids
                for rid, st, entered, first, body in db.execute(sql, args).fetchall():
                    g.put(rid, ix.name(st), entered, first, lambda b=body: codec.unpack(b)["f"])
            self.windows = {}
            for (kind, col, state, wk), (where, over) in windows.items():
                w = self.windows[(kind, col, state, wk)] = Window(kind, col, state, where, over)
                k, s = ix.known(kind), ix.known(state)
                if k == -1 or s == -1:
                    continue
                for t, rid in db.execute(f"select t, rid from moves where kind = ? and {col} = ? and t > ?",
                                         (k, s, now - over - SLACK)).fetchall():
                    w.add(t, rid)
                if where:
                    self._matched(ix, [w], set(w.rids))
        finally:
            db.execute("commit")

    def _matched(self, ix, ws: list[Window], rids: set[int]) -> None:
        """Whether each of these items matches each window's ``where``, as it is now."""
        rids = list(rids)
        for i in range(0, len(rids), 500):
            part = rids[i:i + 500]
            for rid, body in ix.db.execute(f"select rid, body from items where rid in ({','.join('?' * len(part))})", part):
                f = codec.unpack(body)["f"]
                for w in ws:
                    if rid in w.rids:
                        w.match[rid] = _wants(w.where, f)

    def _apply(self, ix, events, now: float) -> bool:
        """What the index folded since: False when it cannot be followed (it went back), and must be read whole."""
        db = ix.db
        name = ix.name
        db.execute("begin")
        try:
            seq = int(ix._meta("seq", 0))
            top = db.execute("select coalesce(max(rowid), 0) from moves").fetchone()[0]
            if seq < self.seq or top < self.mv:
                return False
            for rid, k in db.execute("select rid, kind from items where rid > ? order by rid", (self.rid,)).fetchall():
                kn = name(k)
                self.total[kn] = self.total.get(kn, 0) + 1
                if kn in self.stateless:
                    self.n[(kn, None)] = self.n.get((kn, None), 0) + 1
                self.rid = rid
            by_kind: dict[str, list[Group]] = {}
            for g in self.groups.values():
                by_kind.setdefault(g.kind, []).append(g)
            win: dict[tuple, list[Window]] = {}
            matched: dict[str, list[Window]] = {}
            for w in self.windows.values():
                win.setdefault((w.kind, w.col, w.state), []).append(w)
                if w.where:
                    matched.setdefault(w.kind, []).append(w)
            touched: set[int] = set()
            for row, rid, k, t, f, d in db.execute("select rowid, rid, kind, t, frm, dst from moves where rowid > ? "
                                                   "order by rowid", (self.mv,)).fetchall():
                kn, fn, dn = name(k), name(f), name(d)
                if f is not None:
                    self.n[(kn, fn)] = self.n.get((kn, fn), 0) - 1
                self.n[(kn, dn)] = self.n.get((kn, dn), 0) + 1
                for w in win.get((kn, "dst", dn), ()):
                    w.add(t, rid)
                if f is not None:
                    for w in win.get((kn, "frm", fn), ()):
                        w.add(t, rid)
                if kn in by_kind or kn in matched:
                    touched.add(rid)
                self.mv = row
            fielded = {g.kind for g in self.groups.values() if g.where} | set(matched)
            if fielded and seq > self.seq:              # an item's fields change without a move: its events say so
                skip = () if self.transcript else (TRANSCRIPT_TYPES,)
                ids = set()
                for e in events.of_items(None, after_seq=self.seq, skip=skip):
                    if e["seq"] <= seq:
                        if any(k is not None and k.name in fielded for k in ix.kinds_of(e["item"])):
                            ids.add(e["item"])
                ids = list(ids)
                for i in range(0, len(ids), 500):
                    part = ids[i:i + 500]
                    touched |= {r[0] for r in db.execute(f"select rid from items where id in ({','.join('?' * len(part))})", part)}
            self.seq = max(self.seq, seq)
            if touched:
                rids = list(touched)
                for i in range(0, len(rids), 500):
                    part = rids[i:i + 500]
                    for rid, k, st, entered, first, body in db.execute(
                            f"select rid, kind, state, entered, first, body from items where rid in ({','.join('?' * len(part))})",
                            part).fetchall():
                        kn = name(k)
                        got: list = []

                        def fields(b=body, got=got):
                            if not got:
                                got.append(codec.unpack(b)["f"])
                            return got[0]
                        for g in by_kind.get(kn, ()):
                            g.put(rid, name(st), entered, first, fields)
                        for w in matched.get(kn, ()):
                            if rid in w.rids:
                                w.match[rid] = _wants(w.where, fields())
            for w in self.windows.values():
                w.trim(now)
            return True
        finally:
            db.execute("commit")

    # ---- reading them

    def value(self, spec, s, now: float | None = None) -> tuple[float | None, str]:
        """A sensor that counts items, from what is kept (after ``follow``): as ``items.measure`` counts it."""
        q = s.items or {}
        now = time.time() if now is None else now
        kind = q.get("kind")
        if kind not in spec.items:
            return 0.0, ""
        where = q.get("where") or {}
        if not (q.get("entering") or q.get("leaving")):
            states = q.get("state") or None
            m = q.get("measure")
            if not where and m not in ("oldest", "age"):
                n = sum(self.n.get((kind, x), 0) for x in dict.fromkeys(states)) if states else self.total.get(kind, 0)
                return float(n), ""
            g = self.groups[(kind, tuple(sorted(states or ())), _wkey(where))]
            if m == "age":
                first = g.least(1)
                return ((now - first) / 3600 if g.members and first is not None else 0.0), ""
            if m == "oldest":
                entered = g.least(0)
                return ((now - entered) / 3600 if g.members and entered is not None else 0.0), ""
            return float(len(g.members)), ""
        over = float(q.get("over") or 3600.0)
        col, st = ("dst", q["entering"]) if q.get("entering") else ("frm", q.get("leaving"))
        w = self.windows[(kind, col, st, _wkey(where))]
        return w.count(now - over, now) * (3600.0 / over if s.of.kind == "flow" else 1.0), ""   # an auxiliary: how many
