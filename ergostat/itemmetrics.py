"""Item counts, transitions and durations as metrics (SPEC §4b, *Item metrics*): kept from the item index
(``spec/itemindex.py``), never by replaying the log for a request and never one sample per event, and written once a
minute to a store that keeps labels (VictoriaMetrics: ``Victoria.put``), so a panel asks them in PromQL.

- ``ergostat_items{kind,state[,milestone]}``: a gauge, how many items are in each state (a stock);
- ``ergostat_item_transitions_total{kind,from,to}``: a counter of moves (a flow). The system's two edges are states
  of their own: an arrival (a move with no ``from``) is ``from="(new)"``, an item the index forgets (its events all
  pruned) is ``to="(gone)"``, so a gauge's change equals its net transitions;
- ``ergostat_item_last_transition_timestamp_seconds{kind,from,to}``: when the latest such move was (``time() -
  max(...{kind="gap",to="merged"})``: how long since the last merge);
- ``ergostat_item_time_in_state_seconds{kind,state}``: a histogram (``_bucket{le}``, ``_sum``, ``_count``) of how long
  items stayed in a state, observed when they leave it: work still in the state is not in it (``HELP``);
- ``ergostat_item_field_total{kind,field}``: what items' numeric fields went up by, added (a fall is not counted);
- ``ergostat_events_total{type,source}``: the events the index folded (those about items).

Each is a function of the index as of the minute: the moves, numeric changes and event counts at or before it, and
what the index carried for items it forgot (``carry``: from when they were forgotten). A minute is written once: the
checkpoint (``itemmetrics.json``) says the last, so a restart writes on from it, and a first run backfills from the
index's first minute, saying what pruned history it cannot recover. The checkpoint also keeps the index's epoch and
the counters as last written: an index made again (a kind edited, a new layout, a damaged file built again) has lost
what it carried, so each counter is held at least at what was written (``hold``) and goes on from there. Labels
are bounded: only those in ``LABELS`` (an item's id, a branch, a session or a commit never is one), and a label with
more than ``MOST_VALUES`` values in a kind's metric (``refused``) is left out of it, its series added together."""

from __future__ import annotations

import fcntl
import heapq
import json
import math
import os
import time

NEW, GONE = "(new)", "(gone)"
ITEMS, TRANS = "ergostat_items", "ergostat_item_transitions_total"
LAST = "ergostat_item_last_transition_timestamp_seconds"
STAY = "ergostat_item_time_in_state_seconds"
FIELD, EVENTS = "ergostat_item_field_total", "ergostat_events_total"
LE = (60, 300, 900, 3600, 4 * 3600, 86400, 3 * 86400, 7 * 86400, 30 * 86400)
LABELS = frozenset({"kind", "state", "from", "to", "le", "field", "type", "source", "milestone"})
MOST_VALUES = 100            # values of one label in one kind's metric: past it, the label is refused
MOST_MINUTES = 1440          # minutes written by one pass (a backfill goes on at the next)
MOST_SAMPLES = 500_000       # samples written by one pass, at most (one minute at the least)
MINUTE = 60.0
MOST_WAIT = 3600.0           # the longest wait after faults in a row before the next pass (``kept``)
STATE = "itemmetrics.json"

HELP = {
    ITEMS: "Items of a kind in each state now (a stock).",
    TRANS: "Moves of a kind's items from one state to another (a flow); from=\"(new)\" is an arrival, to=\"(gone)\" an "
           "item the index forgot when its events were pruned.",
    LAST: "When the latest move of a kind's items from one state to another was, in seconds since the epoch.",
    STAY: "How long a kind's items stayed in a state, observed when they leave it: an item still in the state is not "
          "counted, so this cannot see stuck work (ask the item views in SQL, open items censored, for that).",
    FIELD: "What a kind's items' numeric field went up by, added over its items (a fall is not counted).",
    EVENTS: "Events about items the index folded, by type and source.",
}


class Refused(ValueError):
    """A label outside ``LABELS``: never written."""


class Tally:
    """Every metric's value as the rows are fed in time order: ``v[(name, labels)]``."""

    def __init__(self, refused: frozenset = frozenset(), held: dict | None = None):
        self.refused = refused                       # (kind or None, label): left out
        self.v: dict[tuple, float] = dict(held or {})   # (what an index made again no longer counts: ``hold``)
        self.entered: dict[int, float] = {}          # item (rid) -> when its last move was

    def key(self, name: str, labels: dict) -> tuple:
        bad = set(labels) - LABELS
        if bad:
            raise Refused(f"{name}: {', '.join(sorted(bad))} is never a label")
        k = labels.get("kind")
        return name, tuple(sorted((a, str(b)) for a, b in labels.items() if b is not None and (k, a) not in self.refused))

    def add(self, name: str, labels: dict, x: float) -> None:
        k = self.key(name, labels)
        self.v[k] = self.v.get(k, 0.0) + x

    def most(self, name: str, labels: dict, x: float) -> None:
        k = self.key(name, labels)
        self.v[k] = max(self.v.get(k, x), x)

    def move(self, rid: int, kind: str, t: float, frm: str | None, to: str, milestone: str | None = None) -> None:
        if frm == to:
            return
        if frm is not None:
            self.add(ITEMS, {"kind": kind, "state": frm, "milestone": milestone}, -1)
        self.add(ITEMS, {"kind": kind, "state": to, "milestone": milestone}, 1)
        self.add(TRANS, {"kind": kind, "from": frm or NEW, "to": to}, 1)
        self.most(LAST, {"kind": kind, "from": frm or NEW, "to": to}, t)
        if frm is not None and rid in self.entered:
            self.stay(kind, frm, t - self.entered[rid])
        self.entered[rid] = t

    def stay(self, kind: str, state: str, d: float) -> None:
        d = max(0.0, d)
        for le in LE:
            self.add(STAY + "_bucket", {"kind": kind, "state": state, "le": f"{le:g}"}, 1 if d <= le else 0)
        self.add(STAY + "_bucket", {"kind": kind, "state": state, "le": "+Inf"}, 1)
        self.add(STAY + "_sum", {"kind": kind, "state": state}, d)
        self.add(STAY + "_count", {"kind": kind, "state": state}, 1)

    def gone(self, kind: str, state: str, t: float) -> None:
        self.add(TRANS, {"kind": kind, "from": state, "to": GONE}, 1)
        self.most(LAST, {"kind": kind, "from": state, "to": GONE}, t)

    def carried(self, name: str, labels: dict, x: float) -> None:
        (self.most if name == LAST else self.add)(name, labels, x)


def _in(c, sql: str, ids: list) -> list:
    out = []
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        out += c.execute(sql.replace("(?)", f"({','.join('?' * len(part))})"), part).fetchall()
    return out


def carry(db, rids: list[int], name, now: float) -> int:
    """What the items ``rids``, about to be forgotten by the index (``Index._reconcile``), counted, kept in its
    ``carried`` table: their moves, stays and fields, and a move of each to ``(gone)`` now. Not the gauge: they leave
    it, though each of its series they were in is kept, at nothing added. Returns the rows kept."""
    t = Tally()
    for rid, k, at, f, d in _in(db, "select rid, kind, t, frm, dst from moves where rid in (?) order by rid, rowid", rids):
        t.move(rid, name(k), at, name(f), name(d))
    for k, f, d in _in(db, "select kind, field, delta from number_log where rid in (?)", rids):
        t.add(FIELD, {"kind": name(k), "field": name(f)}, max(0.0, d or 0.0))
    for k, s in _in(db, "select kind, state from items where rid in (?)", rids):
        if k is not None and s is not None:
            t.gone(name(k), name(s), now)
    rows = [(now, n, json.dumps(dict(lb)), 0.0 if n == ITEMS else v) for (n, lb), v in t.v.items()]   # (a gauge's
    #                                                                                     series stays, at no items)
    db.executemany("insert into carried(t, name, labels, value) values (?,?,?,?)", rows)
    return len(rows)


def refused(c, names: dict, milestoned: set[str]) -> frozenset:
    """The labels left out, (kind or None, label): each with more than ``MOST_VALUES`` values in the index."""
    out = set()
    for k, n in c.execute("select kind, count(distinct s) from (select kind, frm s from moves union "
                          "select kind, dst from moves) group by kind"):
        if n > MOST_VALUES:
            out |= {(names.get(k), a) for a in ("state", "from", "to")}
    for k, n in c.execute("select kind, count(distinct field) from number_log group by kind"):
        if n > MOST_VALUES:
            out.add((names.get(k), "field"))
    for a in ("type", "source"):
        if c.execute(f"select count(distinct {a}) from event_counts").fetchone()[0] > MOST_VALUES:
            out.add((None, a))
    rel = next((i for i, n in names.items() if n == "milestone"), None)
    for k, n in c.execute("select i.kind, count(distinct l.dst) from links l join items i on i.rid = l.rid "
                          "where l.rel = ? group by i.kind", (rel,)):
        if names.get(k) in milestoned and n > MOST_VALUES:
            out.add((names.get(k), "milestone"))
    return frozenset(out)


def milestoned(spec) -> set[str]:
    """The kinds that have a milestone: a group relation named ``milestone`` holding one id per item."""
    from .spec.grouptally import offered
    return {k.name for k in (getattr(spec, "items", None) or {}).values()
            if (r := (getattr(k, "relations", None) or {}).get("milestone")) is not None and offered(k, r)}


def sweep(c, minutes: list[float], spec, most: int = MOST_SAMPLES, held: dict | None = None,
          base: tuple[float, dict] | None = None) -> tuple[list[tuple[dict, float, float]], frozenset, dict, dict]:
    """Every metric at each of ``minutes`` (ascending), read from the index's connection ``c`` (one moment of it):
    ``(labels with __name__, minute, value)``, stopping past ``most`` samples (after one minute at the least). What the
    index carried counts from the first of ``minutes`` or when it was carried, whichever is earlier. ``held`` is added
    to the counters (and is a floor under the last-move times) from the start; ``base``, ``(minute, values written
    then)`` before ``minutes``, raises each to what was written at that minute and holds the rise (an index made again
    without what it carried: ``hold``). Also returns the values at the last minute and what is held after."""
    names = dict(c.execute("select id, name from names"))
    ms_kinds = milestoned(spec)
    out_refused = refused(c, names, ms_kinds)
    held = dict(held or {})
    t = Tally(out_refused, held)
    if base is not None:
        minutes = [base[0], *minutes]
    rel = next((i for i, n in names.items() if n == "milestone"), None)
    ms = {rid: dst for rid, dst, k in c.execute("select l.rid, l.dst, i.kind from links l join items i on i.rid = l.rid "
                                                 "where l.rel = ?", (rel,)) if names.get(k) in ms_kinds}
    top, first = minutes[-1], minutes[0]
    rows = heapq.merge(
        c.execute("select t, 0, rid, kind, frm, dst from moves where t <= ? order by t, rowid", (top,)),
        c.execute("select t, 1, kind, field, delta, 0 from number_log where t <= ? order by t", (top,)),
        c.execute("select at, 2, type, source, n, 0 from event_counts where at <= ? order by at", (top,)),
        c.execute("select min(t, ?) a, 3, name, labels, value, 0 from carried order by a", (first,)),
        key=lambda r: (r[0], r[1]))
    out: list[tuple[dict, float, float]] = []
    final: dict = {}
    row = next(rows, None)
    for m in minutes:
        while row is not None and row[0] <= m:
            at, what, a, b, x, y = row
            if what == 0:
                t.move(a, names.get(b), at, names.get(x), names.get(y), ms.get(a))
            elif what == 1:
                t.add(FIELD, {"kind": names.get(a), "field": names.get(b)}, max(0.0, x or 0.0))
            elif what == 2:
                t.add(EVENTS, {"type": a, "source": b or None}, x)
            else:
                t.carried(a, json.loads(b), x)
            row = next(rows, None)
        if base is not None and m == base[0]:
            held = hold(t.v, held, base[1])
            continue
        if out and len(out) + len(t.v) > most:
            break
        out += [({"__name__": n, **dict(lb)}, m, v) for (n, lb), v in t.v.items()]
        final = dict(t.v)
    return out, out_refused, final, held


def hold(v: dict, held: dict, written: dict) -> dict:
    """Each counter in ``v`` raised to what was written (``written``) where it counts less, a last-move time to the
    latest written, in place: ``held`` and the rises, so the counters never fall when the index is made again (a kind
    edited, a new layout, a damaged file built again) without what it carried for items it forgot. A gauge's series
    is kept, at nothing added."""
    held = dict(held)
    for k, x in written.items():
        now = v.get(k, 0.0)
        if k[0] == ITEMS:
            v.setdefault(k, 0.0)
            held.setdefault(k, 0.0)
        elif k[0] == LAST:
            v[k] = held[k] = max(x, v.get(k, x))
        elif x > now:
            v[k] = x
            held[k] = held.get(k, 0.0) + x - now
    return held


def _keys(rows) -> dict:
    return {(n, tuple(tuple(p) for p in lb)): x for n, lb, x in rows or []}


def _rows(d: dict) -> list:
    return [[n, [list(p) for p in lb], x] for (n, lb), x in d.items()]


def keep(p, spec, now: float | None = None, say=None) -> dict | None:
    """The minutes not yet written, written (a first run: from the index's first): the checkpoint after, or None where
    there is nothing to write to (a store without labels: SQLite) or from (no index). A store that refuses the write
    leaves the checkpoint as it was, so the same minutes are written next time; a checkpoint that cannot be read stops
    it (a fresh backfill would write every minute again)."""
    store = getattr(p, "measurements", None)
    if not hasattr(store, "put") or not getattr(spec, "items", None):
        return None
    from .spec.itemindex import index_for
    ix = index_for(p.events, spec, False)
    if ix is None:
        return None
    now = time.time() if now is None else now
    top = math.floor(now / MINUTE) * MINUTE
    path = p.dir / STATE
    with open(p.dir / "itemmetrics.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)              # (the check, the write and the checkpoint under one hold)
        st = json.loads(path.read_text()) if path.exists() else {}
        if not isinstance(st, dict):
            raise ValueError(f"{path}: not a checkpoint")
        last = st.get("minute")
        if last is not None and last >= top:
            return st
        with ix.reading() as c:
            c.execute("begin")                        # (one moment of the index, whatever folds meanwhile)
            try:
                start = last + MINUTE if last is not None else _first(c)
                if start is None or start > top:
                    return st or None
                n = int(min(MOST_MINUTES, (top - start) / MINUTE + 1))
                epoch = (c.execute("select value from meta where key = 'epoch'").fetchone() or [None])[0]
                again = last is not None and st.get("epoch") != epoch     # the index made again since: re-based
                rows, out, final, held = sweep(c, [start + MINUTE * i for i in range(n)], spec,
                                               held=_keys(st.get("held")),
                                               base=(last, _keys(st.get("written"))) if again else None)
            finally:
                c.execute("commit")
        if rows:
            store.put(rows)
        new = {**st, "minute": max(r[1] for r in rows) if rows else start + MINUTE * (n - 1),
               "refused": sorted(f"{k or 'every kind'}: {a}" for k, a in out),
               "epoch": epoch, "written": _rows(final) if rows else st.get("written", []), "held": _rows(held)}
        if last is None:
            new["backfill"] = {"from": start, "not recovered": _lost(p.events)}
            if say and new["backfill"]["not recovered"]:
                say(f"item metrics: backfilled from {start:.0f}; {new['backfill']['not recovered']}")
        tmp = path.with_name(STATE + ".tmp")
        tmp.write_text(json.dumps(new))
        os.replace(tmp, path)
        return new


def _first(c) -> float | None:
    got = [r[0] for r in c.execute("select min(t) from moves union all select min(at) from event_counts "
                                   "union all select min(t) from carried") if r[0] is not None]
    return math.ceil(min(got) / MINUTE) * MINUTE if got else None


def _lost(events) -> str:
    """What a backfill cannot recover: what was taken out of the record before the index was built."""
    gen = events.generation() if hasattr(events, "generation") else 0
    if not gen:
        return ""
    return (f"events were taken out of the record {gen} time(s) (rolled up or pruned): items pruned before this index "
            "was built are in no metric, a rolled-up item's events count as none, and items pruned since count, "
            "as carried, only from when they were forgotten")


_due: dict = {}                  # a project's folder -> (faults in a row, the time before which no pass runs)


def kept(p, spec, say, now: float | None = None) -> None:
    """``keep``, as the engine's lead calls it every few seconds, but at most once a minute (a backfill goes on a day
    of minutes a minute): a fault said, never raised, and the next pass not before a wait that doubles with each fault
    in a row, from a minute to ``MOST_WAIT``."""
    now = time.time() if now is None else now
    faults, due = _due.get(p.dir, (0, 0.0))
    if now < due:
        return
    try:
        keep(p, spec, now=now, say=say)
    except Exception as e:                            # (the server away, a checkpoint that cannot be read: later)
        wait = min(MOST_WAIT, MINUTE * 2 ** min(faults, 16))
        _due[p.dir] = (faults + 1, now + wait)
        say(f"item metrics: {type(e).__name__}: {e} (tried again in {wait:.0f} s)")
        return
    _due[p.dir] = (0, (math.floor(now / MINUTE) + 1) * MINUTE)
