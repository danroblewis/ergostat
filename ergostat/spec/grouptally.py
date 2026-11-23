"""How far along each group is (SPEC §5a, *Progress per group*): for a kind's group relation that holds one id per item
(its field folds by ``replace``: a gap's ``milestone``), every group its items name, with its members counted by
status group, read from the item index (the items as folded now, and their moves), never by replaying events.

- **The status groups** (``STACKS``), from each member's status (``precedence.status``): *done* (finished), *in
  progress* (active, or queued in a later state a block takes from), *waiting* (in its first state, or blocked:
  an item its precedence relations name is not finished, as ``precedence.build`` reads it, or its group has not
  started, in its first state: a milestone still waiting), *stopped* (paused, or a dead letter). An active member
  stays in progress whatever it waits on: its work has begun. Each item's group is the query engine's
  ``state_group`` label too (``stages``), so a chart's counts are these.
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
LEFT, SUMMARY, ODD = "left", "summary", "odd"   # out of the total: closed as no work done; a split parent; not one id
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
                     f"offered for: {said}")
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
    members, groups, waits, staged = _read(ix, spec, info, k, rel)
    fin = set(info[kind]["finished"])
    times = [since + (now - since) * n / (points - 1) for n in range(points)]
    rows: dict[str | None, dict] = {}
    odd: list[str] = []
    for i in members:
        v, stage = staged[i.id]
        if stage == ODD:
            odd.append(i.id)                    # (a list, a number: no where= names it; said, never counted as none)
            continue
        row = rows.setdefault(v, _row(v, kind, by, points))
        if stage in (LEFT, SUMMARY):
            row["left" if stage == LEFT else "summaries"] += 1
            continue
        row["counts"][stage] += 1
        row["total"] += 1
        row["done"] = _done_over(row["done"], i, times, fin, rel.done_when)
    for gid, g in groups.items():
        r = rows.setdefault(gid, _row(gid, kind, by, points))
        r.update(item=True, kind=g.kind, state=g.state, title=title_of(g, []), waits_on=waits[gid], first=g.first,
                 status=status(g, info[g.kind], waits[gid]))
    order = lambda r: (r["id"] is None, not r["item"], ORDER.index(r["status"]) if r["status"] in ORDER else len(ORDER),  # noqa: E731
                       r["first"] or 0.0, r["id"] or "")
    out = {"kind": kind, "by": by, "of": rel.kinds, "stacks": list(STACKS), "times": times, "at": now,
           "rows": sorted(rows.values(), key=order), "odd": sorted(odd)[:20], "odd_n": len(odd)}
    with _LOCK:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = out
    return out


def _read(ix, spec, info, k, rel) -> tuple[list, dict, dict, dict]:
    """The kind's members; the groups ``rel`` names (by id, an empty one too); what each group waits on; and each
    member's (row, stage): one of ``STACKS``, ``LEFT``, ``SUMMARY``, or ``ODD``. Read under the index's lock."""
    from ..precedence import starts, status
    by = rel.name if rel is not None else None
    with ix.lock:
        if ix.count(k.name) > MOST:
            raise BadSet(f"{k.name}: more than {MOST} items; the progress per group reads every one")
        members = ix.items(k.name)
        named = sorted({v for i in members for v in [i.fields.get(by)] if by and isinstance(v, str) and v})
        groups = {i.id: i for i in ix.items(None, ids=named, moves=False)} if named else {}
        for t in rel.kinds if rel is not None else ():     # every group, an empty one too (of 0)
            if ix.count(t) > MOST:
                raise BadSet(f"{t}: more than {MOST} items; the progress per group reads every one")
            groups.update({g.id: g for g in ix.items(t, moves=False)})
        known = {i.id: i for i in members} | groups
        after = sorted({d for i in known.values() for _, d in _prec(spec, i)} - set(known))
        known |= {i.id: i for i in ix.items(None, ids=after, moves=False)} if after else {}

    def unfinished(i) -> list[str]:         # its precedence targets not finished (one not in the record: not known to be)
        return [d for r, d in _prec(spec, i) if (t := known.get(d)) is None
                or not (status(t, info[t.kind], []) == "done" or starts(t, r))]
    waits = {gid: unfinished(g) for gid, g in groups.items()}
    held = {gid for gid, g in groups.items() if status(g, info[g.kind], waits[gid]) in ("blocked", "unblocked")}
    parents = {p for i in members for r, x in k.relations.items() if x.group and r != by
               for p in ids_in(i.fields.get(r)) if p != i.id}
    fin = set(info[k.name]["finished"])
    staged: dict[str, tuple] = {}
    for i in members:
        v = i.fields.get(by) if by else None
        if v is not None and not isinstance(v, str):
            staged[i.id] = (None, ODD)
            continue
        want = rel.done_when.get(i.state) if rel is not None and i.state in fin else None
        # held: what it waits on unfinished, and its group when that has not started (a milestone still waiting)
        stage = SUMMARY if i.id in parents else LEFT if want is not None and not matches(i.fields, want) else \
            OF_STATUS.get(status(i, info[k.name], unfinished(i) + ([v] if v in held else [])), "waiting")
        staged[i.id] = (v or None, stage)
    return members, groups, waits, staged


def stages(ix, spec, kind: str) -> dict[str, str]:
    """Each of ``kind``'s items' stage (``state_group``, a label the query engine groups and filters by): as its
    progress counts it under the kind's first group relation offered one (``offered``), else by its status alone."""
    from ..precedence import Kinds
    k = (getattr(spec, "items", None) or {}).get(kind or "")
    if k is None:
        return {}
    rel = next((x for x in k.relations.values() if offered(k, x)), None)
    return {i: s for i, (_, s) in _read(ix, spec, Kinds(spec, ix), k, rel)[3].items()}


def _prec(spec, i) -> list[tuple]:
    """(relation, id) of each item ``i``'s precedence relations names."""
    k = spec.items.get(i.kind or "")
    return [(r, d) for r in k.relations.values() if r.precedence for d in ids_in(i.fields.get(r.name))] if k else []


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
