"""What the items' relations say about the work (SPEC §5a, *Relations*): each item's derived status, the critical
path through the unfinished work, each item's slack, and a schedule projected from the record. Read from the item
index (its links, both ways, and its moves); nothing is declared for it but the relations themselves.

- **Status.** *paused*: in a state its kind declares paused (``messages: paused:``): not finished, not moving, its
  dependents blocked by it. *done*: in a state its kind counts as finished (``spec/finished.py``: ``messages: done:``,
  else the states no item has left yet; never a state a block takes from, its first, ``leased`` or ``dead``; a kind
  with one state lives on). *active*: leased, or in a working state (one
  that is neither its kind's first state, nor a state a block takes from, nor finished). *blocked*: a precedence
  relation names an item not finished (nor in a state the relation's ``starts_at`` names: a start-to-start link, for
  status and for ``takes: {unblocked: true}`` only). *queued*: started, and waiting in a later state a block takes from (review).
  *unblocked*: in its first state, nothing it waits on unfinished. *dead*: a dead letter.
- **Durations.** Each kind's time per state, the median of every stay its latest items made in it (``leased``, a
  run's hold, counted as the work it is), weighted by how often its items visit the state. An item's expected
  duration is that of every state after its first that is not finished (the wait in its first state is the
  schedule's to say, not the item's); a started item's is what is left of its state and the states after it. A
  kind with no stays yet takes the median of the kinds that have them, else ``ASSUMED``, said as assumed.
- **The critical path** (CPM: Kelley and Walker's critical path method): a forward pass over the unfinished items
  in precedence order (each starts once its unfinished predecessors are expected to end; an active one now), a
  backward pass from the last end, and each item's slack, how long it may slip without moving the end. Every link
  is finish-to-start here, ``starts_at`` or not (conservative: a dependent is projected after its target ends). The
  critical items have none. Not levelled: a pool's limit is in the completion estimates (``numbers/eta.py``), whose
  levelled run the Timeline draws in place of this projection once it is worked out.
- **Cycles.** Items whose precedence relations go round, or round through a parent (a summary ends after its
  children, which start after it starts: a descendant depending on its ancestor, or an ancestor on its descendant, at
  any depth), are a finding: they are left out of the projection,
  and a block that takes unblocked items takes none of them.
- **The schedule** (the Timeline): each item's actual segments, its states over time from its moves, and for the
  unfinished, projected segments from the forward pass, state by state.

Bounded: the unfinished items of the kinds asked (``MOST_OPEN``), the finished in the window (``MOST_DONE``), and
the items their relations reach, of any kind (``MOST_PULLED``, ``HOPS`` links away; a system's, only along precedence
and parent relations, of its own kinds, another system's a stub); what was cut is said."""

from __future__ import annotations

from statistics import median

from .spec.ir import DEAD, LEASED
from .spec.relations import ids_in

MOST_OPEN = 600          # unfinished items of the kinds asked, the latest first
MOST_DONE = 400          # finished in the window, the latest first
MOST_PULLED = 400        # items of any kind their relations reach
HOPS = 6                 # links followed out from the items asked
STAYS = 2000             # the latest items whose stays give a kind's medians
ASSUMED = 600.0          # an item's duration when nothing is known of any kind's (seconds)
EPS = 1e-6
END = "\0end"          # a summary's end, in the critical path


class Kinds:
    """Each kind's states as the relations read them: finished, queue, working; and its medians per state."""

    def __init__(self, spec, ix):
        self.spec, self.ix, self.got = spec, ix, {}

    def __getitem__(self, name: str | None) -> dict:
        if name not in self.got:
            self.got[name] = self._info(name)
        return self.got[name]

    def _info(self, name: str | None) -> dict:
        from .spec.finished import finish_of
        k = (getattr(self.spec, "items", None) or {}).get(name or "")
        if k is None or not k.states:
            return {"name": name, "finished": [], "queue": [], "working": [], "paused": [], "medians": {}, "weights": {},
                    "duration": None, "relations": {}}
        fin = finish_of(self.spec, name, self.ix.left(name) if self.ix else set())
        queue, paused, finished = fin["queue"], fin["paused"], fin["finished"]
        working = [s for s in k.states[1:] if s not in finished and s != DEAD and s not in paused]   # time spent in
        stays, visits, n = self.ix.stays(name, STAYS, finished) if self.ix else ({}, {}, 0)
        medians = {s: median(v) for s, v in stays.items() if v}
        # how often a finished item stayed in each state (a rework state, seldom; a state visited twice, twice);
        # with none finished yet, once each
        weights = {s: (visits.get(s, 0) / n if n else 1.0) for s in medians}
        known = [s for s in working if s in medians]
        return {"name": name, "finished": finished, "queue": queue, "working": working,
                "paused": paused, "medians": medians, "weights": weights,
                "duration": sum(medians[s] * weights[s] for s in known) if known else None,
                "relations": {r.name: {"kinds": r.kinds, "precedence": r.precedence, "inverse": r.inverse, "group": r.group,
                                       "starts_at": r.starts_at} for r in k.relations.values()}}

    def expected(self, name: str | None) -> float | None:
        return self[name]["duration"]


def held(fields: dict) -> dict | None:
    lease = fields.get("lease")
    return lease if isinstance(lease, dict) and lease.get("holder") else None


def status(it, info: dict, waiting: list[str]) -> str:
    """done, paused, active, blocked, queued, unblocked, or dead (above)."""
    if it.state == DEAD:
        return "dead"
    if it.state is not None and it.state in info.get("paused", ()):
        return "paused"
    if it.state is not None and it.state in info["finished"]:
        return "done"
    if held(it.fields) or it.state == LEASED or (it.state in info["working"] and it.state not in info["queue"]):
        return "active"
    if waiting:
        return "blocked"
    return "queued" if it.state in info["queue"] and it.state != info["queue"][0] else "unblocked"


def started(it, info: dict) -> bool:
    """Whether an unfinished item's work has begun: it is past its kind's first state, and not waiting in a state a
    block takes from (a queue: its work there begins when it is taken), or it is held."""
    return (bool(info["working"]) and it.state in info["working"] and it.state not in info["queue"]
            or held(it.fields) is not None)


def remaining(it, info: dict, now: float, fallback: float) -> tuple[float, list[tuple[str, float]], bool]:
    """What is left of an unfinished item's work: seconds, its states ahead with each one's expected time, and
    whether that is known (else ``fallback``, assumed)."""
    med, w = info["medians"], info["weights"]
    work = info["working"]
    if not work or not any(s in med for s in work):
        return fallback, [], False
    est = lambda s_: med[s_] * w[s_]                                     # noqa: E731
    gone = lambda s_: max(0.0, med.get(s_, 0.0) - max(0.0, now - (it.entered or now)))   # noqa: E731
    lease = it.fields.get("lease") if isinstance(it.fields.get("lease"), dict) else {}
    if it.state == LEASED:                     # held: the hold, then what comes after where it was taken from
        back = lease.get("back")
        after = work[work.index(back) + 1:] if back in work else work
        ahead = [(LEASED, gone(LEASED))] + [(s_, est(s_)) for s_ in after if s_ != LEASED and s_ in med and w[s_] > 0]
    elif it.state in work:
        at = work.index(it.state)
        ahead = [(it.state, gone(it.state))] + [(s_, est(s_)) for s_ in work[at + 1:] if s_ != LEASED and s_ in med and w[s_] > 0]
    else:
        ahead = [(s_, est(s_)) for s_ in work if s_ in med and w[s_] > 0]
    return sum(x for _, x in ahead), ahead, True


def cycles(nodes, edges) -> list[list[str]]:
    """The cycles among ``edges`` (``(a, b)``: a before b): each strongly connected set of more than one item, or an
    item before itself (Tarjan's algorithm, iterative)."""
    succ: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        succ.setdefault(a, []).append(b)
        succ.setdefault(b, [])
    index, low, on, stack, out = {}, {}, set(), [], []
    n = 0
    for root in succ:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            v, i = work.pop()
            if i == 0:
                index[v] = low[v] = n
                n += 1
                stack.append(v)
                on.add(v)
            ks = succ[v]
            if i < len(ks):
                work.append((v, i + 1))
                w = ks[i]
                if w not in index:
                    work.append((w, 0))
                elif w in on:
                    low[v] = min(low[v], index[w])
                continue
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1 or v in succ[v]:
                    out.append(sorted(comp))
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
    return out


def cpm(durations: dict[str, float], edges, started=()) -> dict[str, dict]:
    """The critical path method over ``durations`` (item: seconds) and ``edges`` (``(a, b)``: a must finish before b
    starts), from 0: each item's earliest start and finish, latest start and finish, slack, and whether it is
    critical; an item in ``started`` starts at 0 whatever comes before it. The edges must be acyclic among the items
    (``cycles`` first); an edge to or from an item not in ``durations`` is left out."""
    preds: dict[str, list[str]] = {n: [] for n in durations}
    succs: dict[str, list[str]] = {n: [] for n in durations}
    for a, b in edges:
        if a in durations and b in durations and a != b:
            preds[b].append(a)
            succs[a].append(b)
    order, deg = [], {n: len(p) for n, p in preds.items()}
    ready = sorted(n for n, d in deg.items() if not d)
    while ready:
        n = ready.pop(0)
        order.append(n)
        for s in succs[n]:
            deg[s] -= 1
            if not deg[s]:
                ready.append(s)
    started = set(started)
    es, ef = {}, {}
    for n in order:
        es[n] = 0.0 if n in started else max([ef[p] for p in preds[n]] or [0.0])
        ef[n] = es[n] + durations[n]
    end = max(ef.values() or [0.0])
    lf, ls = {}, {}
    for n in reversed(order):
        lf[n] = min([ls[s] for s in succs[n] if s not in started] or [end])
        ls[n] = lf[n] - durations[n]
    tol = EPS * max(1.0, end)
    return {n: {"es": es[n], "ef": ef[n], "ls": ls[n], "lf": lf[n], "slack": max(0.0, ls[n] - es[n]),
                "critical": ls[n] - es[n] <= tol, "end": end} for n in order}


def title_of(it, show) -> str:
    for f in ("title", "summary", "name", *show):
        v = it.fields.get(f)
        if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip() and not str(v).startswith("file:"):
            return str(v)[:120]
    return ""


def _segments(it, now: float, finished) -> list[list]:
    """An item's states over time, from its moves: ``[state, from, to]``, the last to now when it is unfinished (a
    finished item's last state is where it ended: no bar)."""
    out = []
    ms = it.moves or []
    for i, m in enumerate(ms):
        end = ms[i + 1]["time"] if i + 1 < len(ms) else None
        if end is None:
            if m["to"] in finished:
                break
            end = now
        if end > m["time"]:
            out.append([m["to"], m["time"], end])
    return out


def build(events, spec, kinds: list[str], now: float, since: float, ix=None, until: float | None = None,
          own: list[str] | None = None) -> dict:
    """The items of ``kinds`` (unfinished, and finished since ``since``) and the items their relations reach, with
    their links, each one's status, expected duration, its place on the critical path and its schedule. With
    ``until``, as they stood then: every read of the index through ``spec/asof.py``. With ``own`` (a system's
    kinds), its dependency network only: reached along precedence and parent relations, of those kinds; such a
    target of another kind is ``outside`` (a stub: its id, kind, system and status), and no other relation is an
    edge (``about`` lists what they name)."""
    from .spec.itemindex import index_for
    ix = ix if ix is not None else index_for(events, spec, False)
    out = {"now": now, "since": since, "kinds": [], "items": [], "edges": [], "cycles": [], "critical": [], "end": now,
           "capped": {}, "assumed": None}
    if ix is None:
        out["note"] = "this record keeps no item index: relations are read from it"
        return out
    if until is not None:
        from .spec.asof import AsOf
        ix = AsOf(ix, events, spec, until)
    info = Kinds(spec, ix)
    kinds = [k for k in kinds if k in spec.items]
    rels = {n: k.relations for n, k in spec.items.items()}
    mine = set(own) & set(spec.items) if own is not None else None
    walks = {r.name for kk in mine or () for r in rels[kk].values() if r.precedence or r.group}

    def walk(kind, r) -> bool:                           # a link followed out: any; a system's, precedence or parent
        rel = (rels.get(kind or "") or {}).get(r)
        return mine is None or rel is not None and (rel.precedence or rel.group)
    got: dict[str, object] = {}
    other: set[str] = set()                              # read, and of another system's kind: not read again
    with ix.lock:
        for k in kinds:
            fin = info[k]["finished"]
            if spec.items[k].states:
                open_states = [s for s in spec.items[k].states if s not in fin]
                opened = ix.items(k, open_states, n=MOST_OPEN + 1)
                if len(opened) > MOST_OPEN:
                    out["capped"]["open"] = out["capped"].get("open", 0) + ix.count(k, open_states) - MOST_OPEN
                done = [i for i in ix.items(k, fin, n=MOST_DONE + 1) if i.last >= since] if fin else []
                if len(done) > MOST_DONE:
                    out["capped"]["done"] = True
                for i in opened[:MOST_OPEN] + done[:MOST_DONE]:
                    got[i.id] = i
            else:
                for i in ix.items(k, n=MOST_OPEN):
                    got[i.id] = i
        frontier, pulled = set(got), 0
        for _ in range(HOPS):
            if not frontier:
                break
            near = {d for a, r, d in ix.links_from(frontier) if walk(got[a].kind, r)}
            back: dict[str, set[str]] = {}                       # what names these, by which relation
            for a, r, _ in ix.links_to(frontier):
                if mine is None or r in walks:
                    back.setdefault(a, set()).add(r)
            new = sorted(x for x in near | set(back) if x not in got and x not in other)   # sorted: not hash order
            if not new:
                break
            room = MOST_PULLED - pulled
            if room <= 0:
                out["capped"]["pulled"] = True
                break
            fetched = ix.items(None, ids=new[:room])
            if mine is not None:                                 # a system's: its own kinds, along its own relations
                other.update(i.id for i in fetched if i.kind not in mine)
                fetched = [i for i in fetched if i.kind in mine
                           and (i.id in near or any(walk(i.kind, r) for r in back.get(i.id, ())))]
            for i in fetched:
                got[i.id] = i
            pulled += len(fetched)
            frontier = {i.id for i in fetched}
        links = ix.links_from(list(got))
        # a precedence target the cap cut is read by id (one call, at most one per link held): the cap limits what is
        # drawn, never what is eligible. One not found at all stays unfinished (below)
        # (a system's: a parent of another kind too, drawn as a stub)
        cut = sorted({d for a, r, d in links if d not in got
                      and (getattr((rels.get(got[a].kind or "") or {}).get(r), "precedence", False)
                           or mine is not None and walk(got[a].kind, r))})
        beyond = {i.id: i for i in ix.items(None, ids=cut, moves=False)} if cut else {}     # (status reads no moves)
    outside = {d: i for d, i in beyond.items() if mine is not None and i.kind not in mine}
    if mine is not None:
        from .spec.item_systems import kind_systems
        where = kind_systems(spec)
        sys_of = lambda kk: (where.get(kk or "") or {}).get("system")      # noqa: E731
        out["outside"] = [{"id": d, "kind": i.kind, "system": sys_of(i.kind), "state": i.state, "outside": True,
                           "status": status(i, info[i.kind], []), "title": title_of(i, [])}
                          for d, i in sorted(outside.items())[:MOST_PULLED]]    # (past it: their status still counts)
        if len(outside) > MOST_PULLED:
            out["capped"]["outside"] = len(outside) - MOST_PULLED
        # whether these kinds wait on anything at all, and what else their relations name (listed, not drawn)
        out["waits"] = bool(walks)
        out["about"] = [{"kind": kk, "rel": r.name, "to": t, "system": sys_of(t)} for kk in mine
                        for r in (rels.get(kk) or {}).values() if not (r.precedence or r.group) for t in r.kinds]
    # the links: precedence (the target first), group (the parent), any other (from the item to what it names)
    out_of: dict[str, dict[str, list[str]]] = {}
    into: dict[str, dict[str, list[str]]] = {}
    before: list[tuple[str, str]] = []
    for a, r, d in links:
        it = got[a]
        rel = (rels.get(it.kind or "") or {}).get(r)
        if rel is None:
            continue
        out_of.setdefault(a, {}).setdefault(r, []).append(d)
        into.setdefault(d, {}).setdefault(rel.inverse, []).append(a)
        if d in outside and (rel.precedence or rel.group):
            out["edges"].append({"from": d, "to": a, "rel": r, "kind": "outside"})
        if d not in got:
            continue
        if rel.precedence:
            before.append((d, a))
            out["edges"].append({"from": d, "to": a, "rel": r, "kind": "precedence"})
        elif rel.group:
            out["edges"].append({"from": d, "to": a, "rel": r, "kind": "group"})
        elif mine is None:                                  # (a system's: listed on its card, not drawn)
            out["edges"].append({"from": a, "to": d, "rel": r, "kind": "other"})
    # statuses: blocked by a predecessor not finished (one past the cap by its own status; one not found at all is not
    # known to be finished)
    def finished(d: str, rel) -> bool:          # (or in a state its relation's ``starts_at`` names: start-to-start)
        i = got.get(d) or beyond.get(d)
        return i is not None and (status(i, info[i.kind], []) == "done" or starts(i, rel))
    durs = {kk: info.expected(kk) for kk in {i.kind for i in got.values()}}
    known = [d for d in durs.values() if d]
    fallback = median(known) if known else ASSUMED
    out["assumed"] = None if known else ASSUMED
    st: dict[str, str] = {}
    waiting: dict[str, list[str]] = {}
    for a, it in got.items():
        mine = rels.get(it.kind or "") or {}
        waiting[a] = [d for r, ds in (out_of.get(a) or {}).items() if mine.get(r) is not None and mine[r].precedence
                      for d in ds if not finished(d, mine[r])]
    for a, it in got.items():
        st[a] = status(it, info[it.kind], waiting[a])
    found = cycles(list(got), before)
    # the critical path, over the unfinished items outside any cycle. A parent with unfinished children is a summary:
    # its work is theirs (a start and an end of no time, its children between), and what comes before or after it
    # comes before its children start, or after they all end. Cycles are then sought over exactly the pairs the
    # critical path reads (a parent's start and end nodes included), again until none is left, so a loop through a
    # parent either way (a descendant depending on its ancestor, or an ancestor on its descendant) never reaches cpm;
    # such a cycle holds the items between too (a middle generation lies on the loop), and none of them is taken
    todo = {a for a, s in st.items() if s not in ("done", "paused")} - {x for c in found for x in c}   # (paused: not projected)
    while True:
        kids: dict[str, list[str]] = {}
        for e in out["edges"]:
            if e["kind"] == "group" and e["from"] in todo and e["to"] in todo:
                kids.setdefault(e["from"], []).append(e["to"])
        end_of = lambda a, kids=kids: a + END if a in kids else a        # noqa: E731
        pairs = [(end_of(x), y) for x, y in before if x in todo and y in todo]
        for p_, cs in kids.items():
            pairs += [(p_, c) for c in cs] + [(end_of(c), p_ + END) for c in cs]
        more = [sorted({n.removesuffix(END) for n in c}) for c in cycles([], pairs)]
        if not more:
            break
        found += more
        todo -= {x for c in more for x in c}
    out["cycles"] = found
    in_cycle = {x for c in found for x in c}
    ahead, d, sure = {}, {}, {}
    for a in todo:
        it = got[a]
        if a in kids:
            d[a], ahead[a], sure[a] = 0.0, [], True
            d[a + END] = 0.0
            continue
        d[a], ahead[a], sure[a] = remaining(it, info[it.kind], now, fallback)
    plan = cpm(d, pairs, [a for a in todo if st[a] in ("active", "queued") or (st[a] == "blocked" and started(got[a], info[got[a].kind]))
                          and a not in kids])
    end = max([p["ef"] for p in plan.values()] or [0.0])
    out["end"] = now + end
    crit = sorted((a for a, p in plan.items() if p["critical"] and d[a] > 0), key=lambda a: (plan[a]["es"], a))
    out["critical"] = crit
    tol = EPS * max(1.0, end)
    for e in out["edges"]:
        p, q = plan.get(end_of(e["from"])), plan.get(e["to"])
        e["critical"] = bool(e["kind"] == "precedence" and p and q and p["critical"] and q["critical"]
                             and abs(p["ef"] - q["es"]) <= tol)
    for p_ in kids:
        plan[p_] = {**plan[p_], "ef": plan[p_ + END]["ef"], "lf": plan[p_ + END]["lf"], "slack": plan[p_ + END]["slack"],
                    "critical": plan[p_ + END]["critical"], "summary": True}
        d[p_] = plan[p_]["ef"] - plan[p_]["es"]
        ahead[p_] = [("children", d[p_])]
    for a, it in got.items():
        k = spec.items.get(it.kind or "")
        lease = held(it.fields)
        x = {"id": a, "kind": it.kind, "state": it.state, "status": st[a], "title": title_of(it, k.show if k else []),
             "entered": it.entered, "first": it.first, "last": it.last,
             "holder": lease.get("block") if lease else None,
             "links": out_of.get(a, {}), "inverse": into.get(a, {}), "waiting": waiting[a],
             "group": next((ds[0] for r, ds in (out_of.get(a) or {}).items()
                            if (rels.get(it.kind or "") or {}).get(r) and rels[it.kind][r].group and ds), None),
             "segments": _segments(it, now, info[it.kind]["finished"]), "cycle": a in in_cycle}
        p = plan.get(a)
        kn = [e["to"] for e in out["edges"] if e["kind"] == "group" and e["from"] == a]
        if kn:
            x["children"] = {"total": len(kn), "done": sum(1 for c in kn if st.get(c) == "done")}
        if p is not None:
            x.update(duration=d[a], known=sure[a], es=now + p["es"], ef=now + p["ef"], ls=now + p["ls"], lf=now + p["lf"],
                     slack=p["slack"], critical=p["critical"] and d[a] > 0, summary=bool(p.get("summary")))
            t, proj = now + p["es"], []
            for s_, secs in (ahead[a] or [(it.state or "", d[a])]):
                if secs > 0:
                    proj.append([s_, t, t + secs])
                    t += secs
            x["projected"] = proj
        out["items"].append(x)
    out["items"].sort(key=lambda x: (x.get("es", x["first"]), x["first"], x["id"]))
    seen_kinds = list(dict.fromkeys([*kinds, *(i.kind for i in got.values() if i.kind)]))
    for kk in seen_kinds:
        i = info[kk]
        k = spec.items.get(kk)
        out["kinds"].append({"name": kk, "states": k.states if k else [], "finished": i["finished"], "queue": i["queue"],
                             "working": i["working"], "medians": i["medians"], "duration": i["duration"],
                             "relations": i["relations"], "asked": kk in kinds})
    return out


def order_ready(events, spec, kind: str, items: list, now: float) -> list:
    """For a block that takes only unblocked items (``takes: {unblocked: true}``): of ``items`` (those it may take,
    in its order), those whose precedence relations name only finished items (or ones in a ``starts_at`` state),
    the critical first (the least slack,
    then the longest path ahead: the bottom level), the block's own order kept among equals."""
    from .spec.itemindex import index_for
    ix = index_for(events, spec, False)
    if ix is None or not items:
        return items
    g = _cached(events, spec, kind, now, ix)
    by = {x["id"]: x for x in g["items"]}
    out = []
    for n, it in enumerate(items):
        x = by.get(it.id)
        if x is None:                                         # not in the graph (past its caps): its links read alone
            with ix.lock:
                prec = _prec(spec, it.kind)
                links = [(r, d) for _, r, d in ix.links_from([it.id]) if r in prec]
                by_id = {i.id: i for i in ix.items(None, ids=[d for _, d in links])} if links else {}
            if any(d not in by_id or (status(by_id[d], Kinds(spec, ix)[by_id[d].kind], []) != "done"
                                      and not starts(by_id[d], prec[r])) for r, d in links):
                continue
            out.append((float("inf"), 0.0, n, it))
            continue
        if x["waiting"] or x.get("cycle"):
            continue
        out.append((x.get("slack", float("inf")), -(x.get("lf", now) - x.get("es", now)), n, it))
    return [it for *_, it in sorted(out, key=lambda t: t[:3])]


def starts(i, rel) -> bool:
    """Whether item ``i`` is in a state ``rel.starts_at`` names; a leased one by the state it was taken from (its
    lease's ``back``), so a target taken from ``approved`` still counts as approved while it is held."""
    s = i.state
    if s == LEASED:
        lease = i.fields.get("lease") if isinstance(i.fields.get("lease"), dict) else {}
        s = lease.get("back")
    return bool(rel.starts_at) and s in rel.starts_at


def _prec(spec, kind) -> dict:
    k = spec.items.get(kind or "")
    return {r.name: r for r in k.relations.values() if r.precedence} if k else {}


_CACHE: dict = {}


def _cached(events, spec, kind: str, now: float, ix) -> dict:
    """The graph of a kind's unfinished items, kept until the record changes (or for a second at most: an active
    item's remaining time moves with the clock)."""
    key = (id(spec), kind, getattr(events, "last_seq", lambda: 0)())
    got = _CACHE.get(key)
    if got is not None and now - got[0] < 1.0:
        return got[1]
    g = build(events, spec, [kind], now, now, ix)
    _CACHE.clear()
    _CACHE[key] = (now, g)
    return g


def relation_cycles(events, spec, most: int = 50_000) -> list[list[str]]:
    """Every cycle of precedence relations in the record (a finding: these items can never all be ready)."""
    from .spec.itemindex import index_for
    from .spec.relations import precedence_names
    names = {r for rs in precedence_names(spec).values() for r in rs}
    if not names:
        return []
    ix = index_for(events, spec, False)
    if ix is None:
        return []
    with ix.lock:
        links = ix.links(names, limit=most)
    edges = [(d, a) for a, _, d in links]
    return cycles({x for e in edges for x in e}, edges)


__all__ = ["build", "cpm", "cycles", "ids_in", "order_ready", "relation_cycles", "remaining", "status"]
