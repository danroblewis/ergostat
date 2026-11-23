"""``GET /api/items-overview``: the Items page's overview (SPEC §5a, *The overview*): for each item kind, under its
system, how many are unfinished and in all, its states over the window in a few buckets, and its rate in and out.
One answer for the whole page, read from the item index (``itemindex.py``: its counts, its moves, its arrivals) and
never from the event log: an item changed since the moment shown is folded again from its own events only, as every
indexed answer does (``items._late``). A kind the index cannot answer for (no index, or a moment so long past that most
items changed since) says so (``why``), never zero.

Each state is in one of four **state groups** (``state_groups``), which the page draws by default."""

from __future__ import annotations

from .. import series
from ..spec import items as its
from ..spec.finished import finish_of
from ..spec.ir import DEAD

POINTS = 32                                    # a card's chart is small: this many buckets over the window
GROUPS = ("waiting", "working", "stopped", "done")   # stacked in this order: the finished at the bottom


def state_groups(states: list[str], finish: dict) -> dict[str, str]:
    """Each of a kind's states in its group, from the kind's finished states (``finished.finish_of``): **done** the
    finished; **stopped** the paused and the dead letters; **waiting** where its items wait to be taken (its first state,
    and those a block takes from: ``queue``); **working** the rest (a lease's ``leased`` among them)."""
    return {s: "done" if s in finish["finished"] else "stopped" if s in finish["paused"] or s == DEAD
            else "waiting" if s in finish["queue"] else "working" for s in states}


def grouped(counts: dict[str, list[int]], groups: dict[str, str], n: int) -> dict[str, list[int]]:
    """Per-state series summed into their groups (only the groups the kind has, in ``GROUPS`` order)."""
    out = {g: [0] * n for g in GROUPS if g in groups.values()}
    for s, vs in counts.items():
        g = groups.get(s)
        if g is not None:
            out[g] = [a + b for a, b in zip(out[g], vs, strict=True)]
    return out


def overview(p, at: float, window: float, n: int = POINTS) -> dict:
    """The overview's answer, as of ``at`` over the ``window`` before it (from where the record starts, when younger)."""
    from ..spec.item_systems import OTHER, TITLES, groups, kind_systems
    spec = getattr(p.model, "spec", None)
    kinds = its.kinds_of(spec)
    starts = p.events.first_time()
    since, until = series.span(p, {"at": at, "window": window, "starts": starts})
    hours = max(until - since, 1.0) / 3600
    ts = series.times(since, until, n)
    where = kind_systems(spec)
    read: dict[bool, tuple] = {}                 # per index (with transcripts or not): its counts, window, late items

    def of(tr: bool):
        if tr not in read:
            ix = its._index(p.events, spec, tr)
            if ix is None:
                read[tr] = None
            else:
                with ix.lock:
                    late = its._late(ix, p.events, spec, None, until, tr)
                    read[tr] = None if late is None else (ix, ix.counts(until), ix.in_window(since, until), late,
                                                          {k: set(ix.left(k)) for k in kinds})
        return read[tr]
    out = []
    unkinded = 0
    for k in kinds.values():
        got = of(its.asks_transcript([k]))
        card = {"name": k.name, "title": TITLES.get(k.name), "id": k.id, "system": where[k.name]["system"],
                "states": k.states}
        if got is None:
            out.append({**card, "why": "not indexed: open the kind's own page" if its._index(p.events, spec, False) is None
                        else "most items changed since this moment: open the kind's own page"})
            continue
        ix, counts, win, late, left = got
        mine = [i for i in late.values() if i.kind == k.name]
        f = finish_of(spec, k.name, left[k.name] | {mv["from"] for i in mine for mv in i.moves if mv["from"]})
        now = dict(counts.get(k.name, {}))
        for i in mine:
            now[i.state or ""] = now.get(i.state or "", 0) + 1
        arrived, active = win.get(k.name, (0, 0))
        arrived += sum(1 for i in mine if i.moves and since <= i.moves[0]["time"] <= until)
        active += sum(1 for i in mine if i.last >= since)
        total = sum(now.values())
        done = sum(now.get(s, 0) for s in f["finished"])
        flow = series._flow_indexed(p, spec, k, since, until, ts) if k.states else None
        sg = state_groups(k.states, f)
        card.update({"finished": f["finished"], "paused": f["paused"], "finished_from": f["from"],
                     "lives_on": f["lives_on"], "group": sg, "now": now, "total": total, "unfinished": total - done,
                     "arrived": arrived, "rate_in": arrived / hours})
        if k.states and flow is None:
            card["why"] = "most items changed since this moment: open the kind's own page"
        elif flow is not None:
            fc, _, _, fin = flow
            card.update({"counts": fc, "by_group": grouped(fc, sg, n), "left": len(fin), "rate_out": len(fin) / hours,
                         "now_by_group": {g: v[0] for g, v in grouped({s: [now.get(s, 0)] for s in k.states}, sg, 1).items()}})
        card["quiet"] = active == 0 and total - done == 0 and "why" not in card
        out.append(card)
    if read.get(False):
        unkinded = sum(read[False][1].get("", {}).values())
    systems = groups(spec, {**where, **({"": {"system": OTHER}} if unkinded else {})})
    for g in systems:
        g["kinds"] = [x for x in g["kinds"] if x]
    return {"since": since, "until": until, "points": n, "times": [round(t, 3) for t in ts], "groups": list(GROUPS),
            "systems": systems, "kinds": out, "unkinded": unkinded,
            "remotes": [{"name": r, "url": x["url"]} for r, x in (getattr(spec, "remotes", None) or {}).items()]}
