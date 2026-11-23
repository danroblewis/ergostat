"""How far along each group is (SPEC §5a, *Progress per group*): for a kind's group relation that holds one id per item
(its field folds by ``replace``: a gap's ``milestone``), every group its items name, with its members counted by
status group, read from the item index (the items as folded now, and their moves), never by replaying events.

- **The status groups** (``STACKS``), from each member's status (``precedence.status``): *done* (finished), *in
  progress* (active, or queued in a later state a block takes from), *waiting* (in its first state, or blocked),
  *stopped* (paused, or a dead letter).
- **Left out of the total**: a member in a finished state the relation's ``done_when`` names whose fields do not match
  it (``done_when: {closed: {end: done}}``: a gap closed as a duplicate, or for any other end, or with none said, is
  not done work: it *leaves* the total, counted apart); and a member that is itself a group of members of its kind
  (a split parent, named by another of its kind's group relations: its work is its children's, wherever they are),
  counted as ``summaries``.
- **Each row**: the group's item (its state, title, and the items its precedence relations name that are not
  finished: what it waits on; one not in the record is not known to be finished), or a value that names no item (an
  old label), or the members that name none. Its ``params`` are the Items page's set of exactly its members
  (``where=REL:ID``; for none, ``REL:null`` and ``REL:``), so a row's link lists what its counts read.
- **Order**: by the group item's status (active first, then queued, unblocked, blocked, paused, dead, done), then
  when it was first seen, then id; values naming no item after, the members naming none last.
- **Over time** (``times``, each row's ``done``): how many of its members (as they are grouped now) were in a
  finished state at each of ``points`` moments over the window, from their moves (one with no move by then: not done);
  ``done_when`` read from the fields as they are now.

The answer is a table a chart reads as it is: ``rows`` the categories, ``stacks`` the series stacked in each."""

from __future__ import annotations

import bisect
import threading

from . import items as its
from .item_sets import BadSet
from .relations import ids_in

STACKS = ("done", "in progress", "waiting", "stopped")
OF_STATUS = {"done": "done", "active": "in progress", "queued": "in progress", "unblocked": "waiting",
             "blocked": "waiting", "paused": "stopped", "dead": "stopped"}
ORDER = ("active", "queued", "unblocked", "blocked", "paused", "dead", "done")
MOST = 20_000             # members read; past it the answer is refused, never cut (a count from part of them is wrong)
POINTS = (2, 200)         # moments over the window: the least and the most
_CACHE: dict = {}
_LOCK = threading.Lock()


def offered(kind, rel) -> bool:
    """Whether a relation's groups have a progress answer: a group naming items of one place (no remote's), whose
    field holds one id per item (folded by replace), so ``where=REL:ID`` is exactly its members."""
    return bool(rel.group and not rel.remote and (kind.fold or {}).get(rel.name) == "replace")


def matches(fields: dict, want: dict) -> bool:
    return all(any(its.same(fields.get(f), w) for w in (v if isinstance(v, list) else [v])) for f, v in want.items())


def progress(events, spec, kind: str, by: str, now: float, since: float, points: int | str = 60) -> dict:
    from ..precedence import Kinds, status, title_of
    from .itemindex import index_for
    k = (getattr(spec, "items", None) or {}).get(kind or "")
    if k is None:
        raise BadSet(f"kind={kind}: no such kind of item")
    rel = k.relations.get(by or "")
    if rel is None or not offered(k, rel):
        said = ", ".join(r for r, x in k.relations.items() if offered(k, x)) or "none"
        raise BadSet(f"by={by}: not a group relation of {kind} holding one id per item (folded by replace); "
                     f"its are: {said}")
    points = int(points) if str(points).isascii() and str(points).isdigit() else -1
    if not POINTS[0] <= points <= POINTS[1]:
        raise BadSet(f"points={points}: from {POINTS[0]} to {POINTS[1]}")
    ix = index_for(events, spec, False)
    if ix is None:
        raise BadSet("this record keeps no item index: the progress per group is read from it")
    key = (id(spec), kind, by, getattr(events, "last_seq", lambda: None)(), round(now - since), int(now) // 10, points)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    info = Kinds(spec, ix)
    with ix.lock:
        if ix.count(kind) > MOST:
            raise BadSet(f"{kind}: more than {MOST} items; the progress per group reads every one")
        members = ix.items(kind)
        named = sorted({v for i in members for v in [i.fields.get(by)] if isinstance(v, str) and v})
        groups = {i.id: i for i in ix.items(None, ids=named, moves=False)} if named else {}
        for t in rel.kinds:                     # every group, an empty one too (of 0)
            if ix.count(t) > MOST:
                raise BadSet(f"{t}: more than {MOST} items; the progress per group reads every one")
            groups.update({g.id: g for g in ix.items(t, moves=False)})
        after = sorted({d for g in groups.values() for r in _prec(spec, g.kind) for d in ids_in(g.fields.get(r))})
        targets = {i.id: i for i in ix.items(None, ids=after, moves=False)} if after else {}
    parents = {p for i in members for r, x in k.relations.items() if x.group and r != by
               for p in ids_in(i.fields.get(r)) if p != i.id}
    fin = set(info[kind]["finished"])
    times = [since + (now - since) * n / (points - 1) for n in range(points)]
    rows: dict[str | None, dict] = {}
    odd: list[str] = []
    for i in members:
        v = i.fields.get(by)
        if v is not None and not (isinstance(v, str)):
            odd.append(i.id)                    # (a list, a number: no where= names it; said, never counted as none)
            continue
        row = rows.setdefault(v or None, _row(v or None, kind, by, points))
        if i.id in parents:
            row["summaries"] += 1
            continue
        want = rel.done_when.get(i.state) if i.state in fin else None
        if want is not None and not matches(i.fields, want):
            row["left"] += 1
            continue
        row["counts"][OF_STATUS.get(status(i, info[kind], []), "waiting")] += 1
        row["total"] += 1
        row["done"] = _done_over(row["done"], i, times, fin, rel.done_when)
    for gid, g in groups.items():
        r = rows.setdefault(gid, _row(gid, kind, by, points))
        waits = [d for x in _prec(spec, g.kind) for d in ids_in(g.fields.get(x))
                 if d not in targets or status(targets[d], info[targets[d].kind], []) != "done"]
        r.update(item=True, kind=g.kind, state=g.state, title=title_of(g, []), waits_on=waits, first=g.first,
                 status=status(g, info[g.kind], waits))
    order = lambda r: (r["id"] is None, not r["item"], ORDER.index(r["status"]) if r["status"] in ORDER else len(ORDER),  # noqa: E731
                       r["first"] or 0.0, r["id"] or "")
    out = {"kind": kind, "by": by, "of": rel.kinds, "stacks": list(STACKS), "times": times, "at": now,
           "rows": sorted(rows.values(), key=order), "odd": sorted(odd)[:20], "odd_n": len(odd)}
    with _LOCK:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = out
    return out


def _prec(spec, kind) -> list[str]:
    k = spec.items.get(kind or "")
    return [r.name for r in k.relations.values() if r.precedence] if k else []


def _row(gid: str | None, kind: str, by: str, points: int) -> dict:
    where = [f"{by}:{gid}"] if gid else [f"{by}:null", f"{by}:"]
    return {"id": gid, "item": False, "kind": None, "state": None, "status": None, "title": "", "waits_on": [],
            "first": None, "counts": dict.fromkeys(STACKS, 0), "total": 0, "left": 0, "summaries": 0,
            "done": [0] * points, "params": {"kind": [kind], "where": where}}


def _done_over(done: list[int], i, times: list[float], fin: set, done_when: dict) -> list[int]:
    """``done`` with one member added at each moment it was in a finished state (done work, by ``done_when``), from
    its moves: one finished then and reopened since counts then."""
    moves = sorted(i.moves, key=lambda m: m["time"])
    at = [m["time"] for m in moves]
    ok = lambda s: s in fin and (s not in done_when or matches(i.fields, done_when[s]))   # noqa: E731
    for n, t in enumerate(times):
        j = bisect.bisect_right(at, t) - 1
        if j >= 0 and ok(moves[j]["to"]):
            done[n] += 1
    return done
