"""What the status reads from the event log, kept as tables of the item index (SPEC §4b), folded with it.

The item index (``itemindex.py``) folds the model's item kinds; beside them it keeps, in the same file, under the same
write lock and in the same transaction as the chunk they came in, the record's own items and events that the status
answer (``state.py``: the inbox and its stats, interventions, actions, requests, proposals, lease attention,
crossings, unrouted messages, drafted reports) reads with ``events.query``:

- ``records``: ergostat's own items (``FAMILIES``: actions, messages, reports, model changes, modelling requests,
  model requests), one row each, folded by their built-in kind from their family's events as each module's
  ``stored()`` folds them; their state and class (an action's class, a change's kind, a request's code) are indexed
  columns, the rest of the fold is ``body``.
- ``marks``: every event of the types those answers read by type and time (``MARKS``: loop crossings, breakers, step
  tests, daemons given up, leases expired, the events of model changes and modelling requests), whole, indexed by
  type, item and time; ``voids``: the ids an ``ergostat.forgotten`` set aside (``unvoided``).
- ``asks``: each time a person block was asked or an advised block advised, and how it was answered
  (``inbox.entries.asks``), per block and chain.

What depends on the model's blocks, goals or files (which entries wait, a class's record, an alarm's readings) is
worked out from these when read: the index is shared by every model with the same item kinds. The record stays the
truth: the tables are emptied and built again with the index, and after events are taken out (a roll-up, a prune: the
record's generation changed) ``records``, ``marks`` and ``voids`` are folded again from what the record still holds,
and an ask whose event is gone is dropped. ``tests/test_index_projections.py`` holds each equal to a fresh read."""

from __future__ import annotations

import functools

from ..leases import EXPIRED
from ..reports.kind import REPORT, report_kind
from ..store import _types
from . import codec
from .ir import (
    ACTION,
    MESSAGE,
    MODEL_CHANGE,
    MODEL_REQUEST,
    MODELLING_REQUEST,
    action_kind,
    message_kind,
    model_change_kind,
    model_request_kind,
    modelling_request_kind,
)
from .items import SNAPSHOT, Item, fold

FAMILIES = {                 # name: (item prefix and type prefix, its kind, the event it must start with, its class field)
    "action": (ACTION, action_kind, f"{ACTION}.requested", ("class", "action")),
    "message": (MESSAGE, message_kind, None, ()),
    "report": (REPORT, report_kind, f"{REPORT}.drafted", ()),
    "change": (MODEL_CHANGE, model_change_kind, None, ("kind",)),
    "request": (MODELLING_REQUEST, modelling_request_kind, None, ("code",)),
    "model-request": (MODEL_REQUEST, model_request_kind, None, ("class",)),
}
FORGOTTEN = "ergostat.forgotten"
MARKS = ("loop.*", "trigger.tripped", "trigger.reset", "steptest.offered", "steptest.approved", "ergostat.daemon.failed",
         "ergostat.daemon.started", EXPIRED, f"{MODEL_CHANGE}.*", f"{MODELLING_REQUEST}.*", FORGOTTEN)
CHAINS = {"person.asked": (0, True), "agent.ran": (0, False),            # type: (chain, whether it asks)
          "block.advised": (1, True), "block.approved": (1, False), "block.denied": (1, False)}
LOOSE = ",".join((*MARKS, *CHAINS))  # the types read beside the items' events (theirs without a ``/`` in their item)

SCHEMA = """
create table if not exists records (fam text, id text, state text, cls text, first real, seq0 integer, start integer,
    body blob, primary key (fam, id));
create index if not exists records_state on records(fam, state, seq0);
create index if not exists records_cls on records(fam, cls, state);
create table if not exists marks (seq integer primary key, type text, item text, time real, eid text, body blob);
create index if not exists marks_type_item on marks(type, item, seq);
create index if not exists marks_type_time on marks(type, time);
create table if not exists voids (eid text primary key) without rowid;
create table if not exists asks (block text, chain integer, seq integer, time real, answered real, verdict text,
    how integer, by text, note text, data blob, primary key (block, chain, seq));
"""
TABLES = ("records", "marks", "voids", "asks")


@functools.cache
def _kind(fam: str):
    return FAMILIES[fam][1]()


def family(e: dict) -> str | None:
    """The family an event folds into (a message's snapshot too: its ``stored()`` reads a rolled-up message whole)."""
    t, item = e["type"], str(e.get("item") or "")
    for fam, (pre, *_) in FAMILIES.items():
        if item.startswith(pre + "/") and (t.startswith(pre + ".") or (fam == "message" and t == SNAPSHOT)):
            return fam
    return None


def _marked(t: str) -> bool:
    return any(t.startswith(m[:-1]) if m.endswith("*") else t == m for m in MARKS)


def loose(events, after: int, top: int, most: int) -> tuple[list[dict], list[dict]]:
    """The events of ``LOOSE`` types in ``(after, top]`` (the oldest ``most``), and those of them whose item has no
    ``/`` (the rest come with the items')."""
    got = events.query(n=None, type=LOOSE, after_seq=after, before_seq=top + 1, first=most)
    return got, [e for e in got if "/" not in str(e.get("item") or "")]


def follow(ix, evs: list[dict], asks: bool = True) -> None:
    """Under the index's write transaction: ``evs`` (oldest first, each once) folded into the tables."""
    db, by = ix.db, {}
    for e in evs:
        fam = family(e)
        if fam is not None:
            by.setdefault((fam, e["item"]), []).append(e)
        if _marked(e["type"]):
            db.execute("insert or replace into marks(seq, type, item, time, eid, body) values (?,?,?,?,?,?)",
                       (e["seq"], e["type"], e.get("item"), e["time"], e["id"], codec.pack(e)))
            if e["type"] == FORGOTTEN:
                db.executemany("insert or ignore into voids(eid) values (?)",
                               [(str(v),) for v in ((e.get("data") or {}).get("voids") or [])])
        if asks and e["type"] in CHAINS and e.get("item") is not None:
            _ask(db, e)
    for (fam, id), es in by.items():
        _record(db, fam, id, es)


def _ask(db, e: dict) -> None:
    chain, asking = CHAINS[e["type"]]
    last = db.execute("select seq, how from asks where block = ? and chain = ? order by seq desc limit 1",
                      (e["item"], chain)).fetchone()
    open_ = last is not None and last[1] == 0
    if asking:
        if open_:
            db.execute("update asks set answered = ?, verdict = 'superseded', how = 1, by = null where block = ? and "
                       "chain = ? and seq = ?", (e["time"], e["item"], chain, last[0]))
        db.execute("insert or replace into asks(block, chain, seq, time, how, data) values (?,?,?,?,0,?)",
                   (e["item"], chain, e["seq"], e["time"], codec.pack(e.get("data") or {})))
    elif open_:
        db.execute("update asks set answered = ?, verdict = ?, how = 2, by = ?, note = ? where block = ? and chain = ? "
                   "and seq = ?", (e["time"], "denied" if e["type"] == "block.denied" else "approved", e.get("source"),
                                   (e.get("data") or {}).get("note") or None, e["item"], chain, last[0]))


def _packed(it: Item | None):
    return None if it is None else (it.state, it.fields, it.first, it.last, it.entered, it.n, it.latest, it.moves, [],
                                    it.refused, it.rolled)


def _record(db, fam: str, id: str, es: list[dict]) -> None:
    """One item of a family folded further: from its family's events (``it``) as its ``stored()`` reads them, and,
    for a message rolled up, from its snapshot on (``whole``: read so when its first message event is not its
    receipt)."""
    kind, row = _kind(fam), db.execute("select body from records where fam = ? and id = ?", (fam, id)).fetchone()
    b = codec.unpack(row[0]) if row else {"i": None, "w": None, "x": {"start": None, "moved": None, "was": None}}
    x, it, whole = b["x"], b["i"] and Item(id, kind.name, *b["i"]), b["w"] and Item(id, kind.name, *b["w"])
    cut = max((i for i, e in enumerate(es) if e["type"] == SNAPSHOT), default=None)
    if cut is not None:                             # (the snapshot is the first of what the record holds of it)
        it, x, es = None, {"start": None, "moved": None, "was": None, "w0": (es[cut]["id"], es[cut]["time"])}, es[cut:]
        whole = fold(id, es[:1], kind)
    typed = [e for e in es if e["type"] != SNAPSHOT]
    if typed and x["start"] is None:
        x.update(start=typed[0]["type"], i0=(typed[0]["id"], typed[0]["time"]), seq0=typed[0]["seq"])
    it = fold(id, typed, kind, it=it)
    whole = whole and fold(id, typed, kind, it=whole)
    for e in typed:                                 # the seq of its last move (``requests._moved_at``)
        to = kind.on.get(e["type"])
        if to is not None and (to != x["was"] or e["type"].endswith(".reopened")):
            x["moved"] = e.get("seq")
        x["was"] = to if to is not None else x["was"]
    read = whole if whole is not None and x["start"] != f"{MESSAGE}.received" else it
    cls = next((read.fields[f] for f in FAMILIES[fam][3] if read.fields.get(f)), None)
    db.execute("insert or replace into records(fam, id, state, cls, first, seq0, start, body) values (?,?,?,?,?,?,?,?)",
               (fam, id, read.state, None if cls is None else str(cls), (x["i0"] if read is it else x["w0"])[1],
                x.get("seq0"), int(it.n > 0 and FAMILIES[fam][2] in (None, x["start"])),
                codec.pack({"i": _packed(it), "w": _packed(whole), "x": x})))


def again(ix, events, seq: int) -> None:
    """After events were taken out of the record: ``records``, ``marks`` and ``voids`` folded again from what it holds
    up to ``seq`` (what the index has folded), and the asks whose event is gone dropped."""
    db = ix.db
    for t in ("records", "marks", "voids"):
        db.execute(f"delete from {t}")
    mine = [e for e in events.of_items([f"{pre}/*" for pre, *_ in FAMILIES.values()]) if e["seq"] <= seq]
    marks = events.query(n=None, type=",".join(MARKS), before_seq=seq + 1)
    got = {e["seq"]: e for e in mine + marks}
    follow(ix, [got[q] for q in sorted(got)], asks=False)
    kept = {e["seq"] for e in events.query(n=None, type="person.asked,block.advised", before_seq=seq + 1)}
    gone = [(q,) for (q,) in db.execute("select seq from asks") if q not in kept]
    db.executemany("delete from asks where seq = ?", gone)


# ---- reading them (each the index's method, after ``catch_up``)

def _view(fam: str, id: str, it: Item, eid0: str, moved: int | None):
    """(key, value): the family's entry as its module's ``stored()`` gives it."""
    if fam in ("action", "message", "report"):
        d = {**it.fields, "id": it.id, "state": it.state, "time": it.first, "last": it.last, "entered": it.entered,
             "moves": it.moves}
        if fam == "action":
            ignored = [r["type"].rsplit(".", 1)[1] for r in it.refused if r["form"] == "final"]
            d.update({"ignored": ignored} if ignored else {})
        if fam == "message":
            d["received_event"] = eid0
        return id, d
    short = id.split("/", 1)[1]
    if fam == "change":
        return short, (it.state, it.fields)
    if fam == "request":
        return short, {**it.fields, "id": short, "state": it.state, "moved": moved}
    return it.fields.get("class") or id, {**it.fields, "id": id, "state": it.state, "moves": it.moves}


def records(ix, fam: str, states=None, cls: str | None = None, since: float | None = None) -> dict:
    """The family's items, oldest first, keyed as its module keys them; only those in ``states``, of class ``cls``,
    or whose first event is at or after ``since``, when given (by the indexed columns)."""
    if fam not in FAMILIES:
        raise ValueError(f"no family {fam!r}: {', '.join(FAMILIES)}")
    sql, args = ["fam = ?", "start = 1"], [fam]
    if states is not None:
        states = list(states)
        sql.append(f"state in ({','.join('?' * len(states))})")
        args += states
    if cls is not None:
        sql.append("cls = ?")
        args.append(cls)
    if since is not None:
        sql.append("first >= ?")
        args.append(since)
    out, kind = {}, _kind(fam)
    for id, body in ix.db.execute(f"select id, body from records where {' and '.join(sql)} order by seq0", args):
        b = codec.unpack(body)
        whole = b["w"] is not None and b["x"]["start"] != f"{MESSAGE}.received"
        k, v = _view(fam, id, Item(id, kind.name, *b["w" if whole else "i"]), b["x"]["w0" if whole else "i0"][0],
                     b["x"]["moved"])
        out[k] = v
    return out


def marked(ix, type: str, item: str | None = None, since: float | None = None, until: float | None = None,
           n: int | None = 100, unvoided: bool = False, after_seq: int | None = None) -> list[dict]:
    """``events.query`` of the ``MARKS`` types, read from ``marks``: matching events, oldest first, the newest ``n``."""
    args: list = []
    sql = [_types(type, args)]
    for cond, v in (("item = ?", item), ("time >= ?", since), ("time <= ?", until), ("seq > ?", after_seq)):
        if v is not None:
            sql.append(cond)
            args.append(v)
    if unvoided:
        sql.append("eid not in (select eid from voids)")
    q = f"select body from marks where {' and '.join(sql)} order by seq desc" + (f" limit {int(n)}" if n is not None else "")
    return [codec.unpack(b) for (b,) in ix.db.execute(q, args)][::-1]


def asked(ix, block: str, person: bool, since: float | None = None, until: float | None = None) -> list[dict]:
    """``inbox.entries.asks`` read from ``asks``: an answer after ``until`` is not known as of then."""
    sql, args = ["block = ?", "chain = ?"], [block, 0 if person else 1]
    for cond, v in (("time >= ?", since), ("time <= ?", until)):
        if v is not None:
            sql.append(cond)
            args.append(v)
    out = []
    for seq, t, ans, verdict, how, by, note, data in ix.db.execute(
            f"select seq, time, answered, verdict, how, by, note, data from asks where {' and '.join(sql)} order by seq",
            args):
        x = {"seq": seq, "time": t, "data": codec.unpack(data), "answered": None, "verdict": None}
        if how and (until is None or ans <= until):
            x.update(answered=ans, verdict=verdict, by=by, **({"note": note} if how == 2 else {}))
        out.append(x)
    return out
