"""A person's to-dos grouped by where they must be done (``use: todo``): one batch for each access context.

    todo batches --kind K --batch-kind B --met done,answered [--states ready,in-progress]

Reads the to-dos of kind ``K`` in those states and groups them by their ``where`` (a host, a bastion, a VPN;
``anywhere`` when it names none), so that everything for one place is done in one sitting. Each group is the item
``B/<where>``: its to-dos in the order to do them (the earliest ``due`` first, then the longest ready, then by id)
and every one's instructions in order, as one text (``sitting``). Says ``B.grouped`` for a group that is new or
changed, and ``B.cleared`` for one with nothing left in it; a group as the record already has it is not said again.
First, a waiting to-do whose wait (what its ``waits_on`` named since it last entered waiting) is over, every item
named in a ``--met`` state (done, answered), is said ready again (``K.freed``, which the kind's ``moves-from:`` lets
move it only out of waiting, and its ``if-unchanged:`` only when nothing was recorded of the to-do since it was read:
its ``read`` is the count of events judged, so a drop or a new wait since stays as recorded), grouped on the next pass;
one whose prerequisite ended without happening (dropped) stays waiting, said in its ``stuck`` field (``K.stuck``).
It reads the record and prints lines; it runs nothing and writes nowhere else."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys

from ...spec.relations import ids_in
from .common import items, project, say

ANYWHERE = "anywhere"
FIELDS = ("where", "title", "count", "todos", "due", "sitting")


def where_of(it) -> str:
    w = it.fields.get("where")
    return " ".join(str(w).split()) if w not in (None, "") and not isinstance(w, dict | list) else ANYWHERE


def key_of(where: str) -> str:
    """The batch's id under its kind: the place as it was written when that is already an id's name, else its
    letters and digits and a short hash of the whole text (so two places that read alike never share a batch)."""
    slug = re.sub(r"[^a-z0-9]+", "-", where.lower()).strip("-")[:48]
    if slug == where:
        return slug
    return f"{slug or 'place'}-{hashlib.sha256(where.encode()).hexdigest()[:8]}"


def step_lines(n: int, s) -> list[str]:
    """One instruction: what to do, the command to run and how to check it worked."""
    if isinstance(s, dict):
        do = s.get("do") or s.get("step") or s.get("text") or ""
        out = [f"{n}. {' '.join(str(do).split())}".rstrip()]
        if s.get("run") or s.get("command"):
            out += [f"   $ {line}" for line in str(s.get("run") or s.get("command")).splitlines()]
        if s.get("check"):
            out.append(f"   check: {' '.join(str(s['check']).split())}")
        return out
    return [f"{n}. {' '.join(str(s).split())}"]


def todo_lines(it) -> list[str]:
    f = it.fields
    said = [x for x in (f.get("requester") and f"for {f['requester']}", f.get("due") and f"due {f['due']}",
                        it.state != "ready" and it.state) if x]
    out = [f"## {it.id}: {f.get('title') or '(no title)'}" + (f" ({', '.join(map(str, said))})" if said else "")]
    steps = f.get("instructions")
    if steps is None:
        out.append("(no instructions written)")
    elif not isinstance(steps, list):
        out.append("(its instructions cannot be read: not a list of steps)")
    else:
        for n, s in enumerate(steps, 1):
            out += step_lines(n, s)
    return out


def order(it) -> tuple:
    due = it.fields.get("due")
    return (due is None or due == "", str(due or ""), it.entered or it.first, it.id)


def groups(todos: list) -> dict[str, dict]:
    """Each place's batch, by its key: its fields as ``B.grouped`` says them."""
    by: dict[str, list] = {}
    for it in todos:
        by.setdefault(where_of(it), []).append(it)
    out = {}
    for where, its in by.items():
        its = sorted(its, key=order)
        dues = [str(i.fields["due"]) for i in its if i.fields.get("due") not in (None, "")]
        text = [f"# {where}: {len(its)} to-do{'s' if len(its) != 1 else ''}, in this order", ""]
        for it in its:
            text += [*todo_lines(it), ""]
        out[key_of(where)] = {"where": where, "title": f"{where}: {len(its)} to-do{'s' if len(its) != 1 else ''}",
                              "count": len(its), "todos": [i.id for i in its], "due": min(dues) if dues else None,
                              "sitting": "\n".join(text).rstrip() + "\n"}
    return out


def batches(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="todo batches")
    ap.add_argument("--kind", required=True)
    ap.add_argument("--batch-kind", required=True)
    ap.add_argument("--states", default="ready,in-progress")
    ap.add_argument("--met", required=True,
                    help="the states in which what a to-do waits on has happened (done,answered); finished any other "
                         "way (dropped), its to-do stays waiting")
    ap.add_argument("--flow", help="the flow the to-dos freed move along (said as the block's out)")
    a = ap.parse_args(argv)
    p = project()
    freed = free(p, a.kind, {s for s in a.met.split(",") if s})
    want = groups(items(p, a.kind, [s for s in a.states.split(",") if s]))
    have = {i.id: i for i in items(p, a.batch_kind)}
    for key, data in sorted(want.items()):
        iid = f"{a.batch_kind}/{key}"
        was = have.get(iid)
        if was is None or was.state != "open" or any(was.fields.get(k) != data[k] for k in FIELDS):
            say({"event": f"{a.batch_kind}.grouped", "item": iid, "data": data})
    for iid, was in sorted(have.items()):
        if was.state == "open" and iid.split("/", 1)[1] not in want:
            say({"event": f"{a.batch_kind}.cleared", "item": iid,
                 "data": {"where": was.fields.get("where"), "title": f"{was.fields.get('where')}: nothing left",
                          "count": 0, "todos": [], "due": None, "sitting": ""}})
    if a.flow:
        say({"out": a.flow, "moved": freed})
    return 0


def named(v) -> set[str]:
    """The ids one event's ``waits_on`` names: an id, a list of them, or a relation's ``{set, add}``."""
    if isinstance(v, dict):
        return {x for k in ("set", "add") for x in ids_in(v.get(k))}
    return set(ids_in(v))


def waits_now(it, evs: list[dict]) -> list[str] | None:
    """What a waiting to-do waits on this time: the ids in its ``waits_on`` named by the event that last moved it
    into waiting or by one after it (a wait named before, and already over, is not this wait). None when that move
    cannot be found in its events (rolled up): not known, so it stays waiting."""
    into = [m.get("event") for m in it.moves if m.get("to") == "waiting"]
    at = next((n for n, e in enumerate(evs) if into and e.get("id") == into[-1]), None)
    if at is None:
        return None
    since = set().union(*(named((e.get("data") or {}).get("waits_on")) for e in evs[at:]))
    return [t for t in ids_in(it.fields.get("waits_on")) if t in since]


def free(p, kind: str, met: set[str]) -> int:
    """Each waiting to-do whose wait (``waits_now``) names only items in a ``met`` state (done, answered: what it
    waited on happened) is ready again (``K.freed``). One that names an item never recorded, or one not yet met,
    stays waiting; one that names nothing, or whose wait ended without happening (a prerequisite dropped), stays
    waiting, and its ``stuck`` field says why, said once. Returns how many were freed."""
    from ...spec import items as its
    spec, n = p.model.spec, 0
    waiting = items(p, kind, ["waiting"])
    if not waiting:
        return 0
    known = {i.id: i for i in its.project(p.events, spec)}
    for was in waiting:
        evs = p.events.query(item=was.id, n=None)          # the to-do folded from the very events judged: what is
        it = its.fold(was.id, evs, spec.items[kind])       # said carries their count (read), and the kind's
        if it.state != "waiting":                          # if-unchanged: refuses it once another lands (SPEC §5a)
            continue
        on = waits_now(it, evs)
        got = [known.get(t) for t in on or ()]
        if on and all(t is not None and t.state in met for t in got):
            say({"event": f"{kind}.freed", "item": it.id,
                 "data": {"freed": "what it waited on happened: " + ", ".join(on), "stuck": None, "read": it.n}})
            n += 1
            continue
        stuck = ("it cannot be told what it waits on since it last entered waiting (its events are rolled up)"
                 if on is None else f"nothing it waits on was named when it last entered waiting or since: record "
                 f"{kind}.waiting with a waits_on to name it, or {kind}.ready when it can go on" if not on else "; ".join(
                     f"{t.id} ended {t.state}, not {' or '.join(sorted(met))}: record {kind}.ready to do it anyway, "
                     f"{kind}.waiting with a new waits_on, or {kind}.dropped"
                     for t in got if t is not None and t.state not in met and t.state in finished(spec, t.kind))) or None
        if stuck != it.fields.get("stuck"):
            say({"event": f"{kind}.stuck", "item": it.id, "data": {"stuck": stuck, "read": it.n}})
    return n


def finished(spec, kind: str) -> list[str]:
    from ...spec.finished import finish_of
    f = finish_of(spec, kind, set())
    return f["finished"] if f["from"] == "declared" else []


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "batches":
        print("usage: python -m ergostat.library.run todo batches --kind K --batch-kind B --met S,... [--states S,...]",
              file=sys.stderr)
        return 2
    return batches(argv[1:])
