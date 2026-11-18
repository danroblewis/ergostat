"""The Process view (SPEC §5b): the process map of process mining, a directly-follows graph (DFG) read
from the record (van der Aalst, *Process Mining: Data Science in Action*; the map Disco and Celonis
draw), object-centric (van der Aalst's object-centric process mining, OCEL): one map per item kind,
and between the maps the lines where an event on an item of one kind caused (``causedby``) an event on
an item of another, which show work fanning out and joining back.

Each map's nodes are its kind's activities, by one of two readings (``by``):

- ``states``: the states its items entered (a move, from the item index), the lines its moves: what the
  kind declares as its workflow, with every way the items really took through it, rework included;
- ``events``: the event types about its items, a line from each to the next one about the same item.

and two more nodes, where its items start (their first event, in the window) and end (they reached a
state the kind counts as finished). Each node has how many times it happened in the window, each line
how many times and the median time between its two ends. A line from a later step to an earlier one is
rework (``rework``): a loop.

Bounded: the newest ``MOST_EVENTS`` events in the window are read, the moves of at most ``MOST_ITEMS``
items, and the ``MOST_NODES`` most frequent nodes and ``MOST_EDGES`` most frequent lines are drawn; what
was left out is said (``capped``). Plain data: the page lays it out, and the Items page lists the items
behind any node or line (``items_through``, read by ``spec/item_sets.py``)."""

from __future__ import annotations

import fnmatch
from statistics import median

MOST_EVENTS = 50_000          # the newest this many events in the window are read
MOST_ITEMS = 20_000           # the items whose moves are read (states), the latest moved first
MOST_CAUSES = 2_000           # causes looked up from before the window
MOST_NODES = 60               # the most frequent activities drawn, over every kind
MOST_EDGES = 160              # the most frequent lines drawn
CAUSE_HOPS = 4                # a cause followed up through events about no item (a block's run) this far
SKIP = ("claude.*", "ergostat.lease.renewed", "ergostat.item.snapshot")   # a transcript's lines, a lease's heartbeat, a roll-up
START, END = "^", "$"         # the start and end of a kind's map, in a line's ends (``followed=^>open``)
BY = ("states", "events")


def default_by(spec, kinds: list[str]) -> str:
    """States when every kind drawn declares states (the workflow as the owner wrote it: fewer nodes, and the
    same names as the stocks that count them); else events."""
    ks = [spec.items[k] for k in kinds if k in spec.items]
    return "states" if ks and all(k.states for k in ks) else "events"


def kinds_of(spec, system: str | None) -> list[str]:
    """The kinds of the system being viewed (``item_systems.py``: where each kind belongs), in their declared
    order; everything: every kind but ergostat's own."""
    from .spec.item_systems import BUILT_IN, kind_systems
    where = kind_systems(spec)
    out = []
    for k in (getattr(spec, "items", None) or {}):
        sys_ = where.get(k, {}).get("system")
        if system:
            if system in spec.chain(sys_) if sys_ in spec.systems else sys_ == system:
                out.append(k)
        elif not k.startswith(BUILT_IN + "."):
            out.append(k)
    return out


def _kind(spec, kinds: list[str], id: str | None) -> str | None:
    """The kind an item's id is (the first that matches, of all of them), when it is one of ``kinds``."""
    if not id or "/" not in id:
        return None
    for name, k in spec.items.items():
        if fnmatch.fnmatchcase(id, k.id):
            return name if name in kinds else None
    return None


def _done(spec, events, kind) -> set[str]:
    from .spec.itemindex import done_states
    from .spec.items import _index
    declared = getattr(getattr(spec, "messages", None), "done", None)
    ix = _index(events, spec, False)
    left: set[str] = set()
    if ix is not None:
        with ix.lock:
            left = ix.left(kind.name)
    return set(done_states(kind, left, declared)) - {"leased"}       # held by a run is never finished, however new the record


def _folded(events, spec, kind: str, ids) -> dict:
    """The items among ``ids`` with their moves, from the item index (else folded from the record)."""
    from .spec import items as its
    ids = set(ids)
    if not ids:
        return {}
    ix = its._index(events, spec, False)
    if ix is not None:
        with ix.lock:
            return {i.id: i for i in ix.items(kind, ids=ids)}
    return {i.id: i for i in its.project(events, spec, kind, transcript=False) if i.id in ids}


def _moved_ids(events, spec, kind: str, since: float, until: float) -> tuple[list[str], bool]:
    """The items of ``kind`` with a move in the span, the latest moved first, at most ``MOST_ITEMS``; and whether
    there were more."""
    from .spec import items as its
    ix = its._index(events, spec, False)
    if ix is not None:
        with ix.lock:
            k = ix.known(kind)
            if k == -1:
                return [], False
            rows = ix.db.execute("select i.id from moves m join items i on i.rid = m.rid where m.kind = ? and m.t >= ? "
                                 "and m.t <= ? group by m.rid order by max(m.t) desc limit ?",
                                 (k, since, until, MOST_ITEMS + 1)).fetchall()
            return [r[0] for r in rows[:MOST_ITEMS]], len(rows) > MOST_ITEMS
    got = [i for i in its.project(events, spec, kind, transcript=False) if any(since <= m["time"] <= until for m in i.moves)]
    got.sort(key=lambda i: -max(m["time"] for m in i.moves))
    return [i.id for i in got[:MOST_ITEMS]], len(got) > MOST_ITEMS


def _state_after(it, t: float, eid: str | None) -> str | None:
    """The state an item was in just after the event at ``t`` (``eid``)."""
    st = None
    for m in it.moves:
        if m["time"] > t and m["event"] != eid:
            break
        st = m["to"]
        if m["event"] == eid:
            break
    return st


class Window:
    """What the record says of some kinds over a span: each item's steps (its activities in order, by
    ``by``), where it started and ended, and what caused what across items. Read once; the map and every
    item set are made from it."""

    def __init__(self, events, spec, kinds: list[str], since: float, until: float, by: str):
        self.events, self.spec, self.kinds, self.since, self.until, self.by = events, spec, kinds, since, until, by
        self.capped: dict[str, bool] = {"events": False, "items": False}
        self.evs = [e for e in events.query(n=MOST_EVENTS, since=since, until=until, skip=SKIP)]
        self.capped["events"] = len(self.evs) >= MOST_EVENTS
        self.evs.sort(key=lambda e: (e["time"], e.get("seq") or 0))
        self.by_id = {e["id"]: e for e in self.evs}
        self.kind_of: dict[str, str] = {}
        for e in self.evs:
            it = e.get("item")
            if it and it not in self.kind_of:
                k = _kind(spec, kinds, it)
                if k:
                    self.kind_of[it] = k
        # each item: [(time, activity, event id, type)], whether it started in the span, whether it ended in it
        self.steps: dict[str, list[tuple]] = {}
        self.started: dict[str, bool] = {}
        self.ended: dict[str, bool] = {}
        self.before: dict[str, float] = {}       # (states) when it entered the state its first move in the span left
        self.folded: dict[str, object] = {}
        for k in kinds:
            if self.by == "states" and spec.items[k].states:
                self._states(k)
            else:
                self._events(k)
        self.causes = self._causes()

    def _states(self, kind: str) -> None:
        ids, more = _moved_ids(self.events, self.spec, kind, self.since, self.until)
        self.capped["items"] |= more
        got = _folded(self.events, self.spec, kind, ids)
        self.folded.update(got)
        done = _done(self.spec, self.events, self.spec.items[kind])
        for id, it in got.items():
            self.kind_of.setdefault(id, kind)
            steps, prev = [], None
            for m in it.moves:
                if m["time"] > self.until:
                    break
                if m["time"] >= self.since:
                    if not steps:
                        self.started[id] = m["from"] is None
                        if prev is not None:
                            self.before[id] = prev["time"]
                    steps.append((m["time"], m["to"], m["event"], m["type"]))
                prev = m
            if steps:
                self.steps[id] = steps
                self.ended[id] = prev is not None and prev["to"] in done and prev["time"] >= self.since

    def _events(self, kind: str) -> None:
        mine: dict[str, list[tuple]] = {}
        for e in self.evs:
            it = e.get("item")
            if it and self.kind_of.get(it) == kind:
                mine.setdefault(it, []).append((e["time"], e["type"], e["id"], e["type"]))
        k = self.spec.items[kind]
        got = _folded(self.events, self.spec, kind, mine)
        self.folded.update(got)
        done = _done(self.spec, self.events, k) if k.states else set()
        for id, steps in mine.items():
            it = got.get(id)
            self.steps[id] = steps
            self.started[id] = it is not None and it.first >= self.since and steps[0][0] <= it.first
            if it is not None and done:
                st = None
                for m in it.moves:
                    if m["time"] > self.until:
                        break
                    st = m["to"]
                self.ended[id] = st in done
            else:
                self.ended[id] = False

    def _cause(self, e: dict) -> dict | None:
        """The event on another item that caused ``e``: its ``causedby``, followed up through events about no
        item (a block's run) as far as ``CAUSE_HOPS``."""
        cid = e.get("causedby")
        for _ in range(CAUSE_HOPS):
            if not cid:
                return None
            c = self.by_id.get(cid)
            if c is None and self._looked < MOST_CAUSES:
                self._looked += 1
                c = self.events.get(cid)
            if c is None:
                return None
            it = c.get("item")
            if it and "/" in it:
                return c if it != e.get("item") else None
            cid = c.get("causedby")
        return None

    def _causes(self) -> list[tuple]:
        """(cause item, its activity, the cause's type, item, its activity, the effect's type, when, when its cause) of each
        event in the span on an item drawn, caused by an event on another item drawn."""
        self._looked = 0
        out, need = [], []
        for e in self.evs:
            it = e.get("item")
            if not it or it not in self.kind_of or not e.get("causedby"):
                continue
            c = self._cause(e)
            if c is None:
                continue
            ci = c["item"]
            if ci not in self.kind_of:
                k = _kind(self.spec, self.kinds, ci)
                if not k:
                    continue
                self.kind_of[ci] = k
            need.append((c, e))
        if self.by == "states":                      # each end at the state its item was in just after
            missing: dict[str, set[str]] = {}
            for c, e in need:
                for x in (c, e):
                    if x["item"] not in self.folded:
                        missing.setdefault(self.kind_of[x["item"]], set()).add(x["item"])
            for k, ids in missing.items():
                self.folded.update(_folded(self.events, self.spec, k, ids))
        for c, e in need:
            out.append((c["item"], self._act(c), c["type"], e["item"], self._act(e), e["type"], e["time"], c["time"]))
        return out

    def _act(self, e: dict) -> str | None:
        k = self.spec.items.get(self.kind_of.get(e["item"], ""))
        if self.by == "states" and k is not None and k.states:
            it = self.folded.get(e["item"])
            return _state_after(it, e["time"], e["id"]) if it is not None else None
        return e["type"]

    # ---- what went through a node or a line

    def through(self, kind: str, act: str) -> dict[str, list[float]]:
        """The items of ``kind`` that went through ``act`` in the span (``^`` started, ``$`` ended): when."""
        out: dict[str, list[float]] = {}
        for id, steps in self._of(kind):
            if act == START:
                if self.started.get(id):
                    out[id] = [steps[0][0]]
            elif act == END:
                if self.ended.get(id):
                    out[id] = [steps[-1][0]]
            else:
                ts = [t for t, a, _, _ in steps if a == act]
                if ts:
                    out[id] = ts
        return out

    def followed(self, kind: str, a: str, b: str) -> dict[str, list[float]]:
        """The items of ``kind`` on which ``b`` directly followed ``a`` in the span: when ``b`` did."""
        out: dict[str, list[float]] = {}
        for id, steps in self._of(kind):
            for (t0, x, _, _), (t1, y, _, _) in self._pairs(id, steps):
                if x == a and y == b:
                    out.setdefault(id, []).append(t1 if t1 is not None else t0)
        return out

    def caused(self, kind: str, cause_kind: str, a: str, b: str) -> dict[str, list[float]]:
        """The items of ``kind`` on which ``b`` was caused by ``a`` on an item of ``cause_kind``: when."""
        out: dict[str, list[float]] = {}
        for ci, ca, _, ei, ea, _, t, _ in self.causes:
            if self.kind_of.get(ei) == kind and self.kind_of.get(ci) == cause_kind and ca == a and ea == b:
                out.setdefault(ei, []).append(t)
        return out

    def _of(self, kind: str):
        return ((id, s) for id, s in self.steps.items() if self.kind_of.get(id) == kind)

    def _pairs(self, id: str, steps: list[tuple]):
        """Each line an item drew: (time, from), (time, to); its start and end too (a time of None: the end's
        own time is its last step's)."""
        k = self.spec.items[self.kind_of[id]]
        if self.started.get(id):
            yield (None, START, None, None), steps[0]
        elif self.by == "states" and k.states:       # its first move in the span left a state it entered before
            first = self.folded.get(id)
            m = next((m for m in (first.moves if first else []) if m["event"] == steps[0][2]), None)
            if m is not None and m["from"] is not None:
                yield (self.before.get(id), m["from"], None, None), steps[0]
        yield from zip(steps, steps[1:], strict=False)
        if self.ended.get(id):
            yield steps[-1], (None, END, None, None)


def process(events, spec, kinds: list[str], since: float, until: float, by: str | None = None,
            paths: float = 0.0) -> dict:
    """The process map of ``kinds`` over the span: nodes, lines (``follows`` within an item, ``caused``
    between items), each with its count and median time, the more frequent first; lines below ``paths`` (a
    share, 0 to 1, of the most frequent line of their kind) left out, as process mining tools' slider does,
    and the nodes it leaves with no line. Bounded: what was left out is said."""
    by = by if by in BY else default_by(spec, kinds)
    w = Window(events, spec, kinds, since, until, by)
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def nid(kind, act):
        return f"p:{kind}:{act}"

    def node(kind, act):
        x = nodes.get(nid(kind, act))
        if x is None:
            role = "start" if act == START else "end" if act == END else "activity"
            label = {"start": "start", "end": "end"}.get(role, act)
            x = nodes[nid(kind, act)] = {"id": nid(kind, act), "kind": role, "itemKind": kind, "activity": act,
                                         "label": label, "count": 0, "_items": set()}
        return x

    pos: dict[tuple[str, str], list[float]] = {}           # each activity's place in its items' runs: its order
    for id, steps in w.steps.items():
        kind = w.kind_of[id]
        n = len(steps)
        for i, (_t, act, _, _) in enumerate(steps):
            x = node(kind, act)
            x["count"] += 1
            x["_items"].add(id)
            pos.setdefault((kind, act), []).append(i / max(1, n - 1) if n > 1 else 0.0)
        if w.started.get(id):
            x = node(kind, START)
            x["count"] += 1
            x["_items"].add(id)
        if w.ended.get(id):
            x = node(kind, END)
            x["count"] += 1
            x["_items"].add(id)
        for (t0, a, _, _), (t1, b, _, _) in w._pairs(id, steps):
            node(kind, a)
            node(kind, b)
            key = f"f:{kind}:{a}>{b}"
            e = edges.get(key)
            if e is None:
                e = edges[key] = {"id": key, "kind": "follows", "source": nid(kind, a), "target": nid(kind, b),
                                  "itemKind": kind, "from": a, "to": b, "count": 0, "_times": [], "_items": set()}
            e["count"] += 1
            e["_items"].add(id)
            if t0 is not None and t1 is not None and a not in (START,) and b not in (END,):
                e["_times"].append(max(0.0, t1 - t0))
    for ci, ca, cty, ei, ea, ety, t, tc in w.causes:
        if ca is None or ea is None:
            continue
        ck, ek = w.kind_of[ci], w.kind_of[ei]
        node(ck, ca)
        node(ek, ea)
        key = f"c:{ck}:{ca}>{ek}:{ea}"
        e = edges.get(key)
        if e is None:
            e = edges[key] = {"id": key, "kind": "caused", "source": nid(ck, ca), "target": nid(ek, ea), "itemKind": ek,
                              "causeKind": ck, "from": ca, "to": ea, "count": 0, "_times": [], "_items": set(), "_causes": set(),
                              "_types": {}}
        e["count"] += 1
        e["_items"].add(ei)
        e["_causes"].add(ci)
        e["_types"][(cty, ety)] = e["_types"].get((cty, ety), 0) + 1
        e["_times"].append(max(0.0, t - tc))
    # the order of each kind's activities: a state's place in the declared states; an event's, its usual place
    order: dict[str, float] = {}
    for x in nodes.values():
        k = spec.items[x["itemKind"]]
        a = x["activity"]
        if a == START:
            order[x["id"]] = -1.0
        elif a == END:
            order[x["id"]] = 1e9
        elif by == "states" and k.states and a in k.states:
            order[x["id"]] = float(k.states.index(a))
        else:                                  # an event: the state it moves to, else its usual place in its items' runs
            ps = median(pos.get((x["itemKind"], a), [0.5]))
            to = k.on.get(a)
            order[x["id"]] = k.states.index(to) + ps * 0.01 if to in k.states else ps * max(1, len(k.states) or 10)
    for e in edges.values():
        e["rework"] = e["kind"] == "follows" and (e["source"] == e["target"] or order[e["target"]] < order[e["source"]])
        e["self"] = e["source"] == e["target"]
    total = {"nodes": len(nodes), "edges": len(edges)}
    # the frequency filter: lines below the share of their kind's most frequent left out
    hidden = {"nodes": 0, "edges": 0}
    if paths > 0:
        joined = {x for e in edges.values() for x in (e["source"], e["target"])}
        top: dict[str, int] = {}
        for e in edges.values():
            g = e["kind"] if e["kind"] == "caused" else e["itemKind"]
            top[g] = max(top.get(g, 0), e["count"])
        keep = {k: e for k, e in edges.items()
                if e["count"] >= paths * top[e["kind"] if e["kind"] == "caused" else e["itemKind"]]}
        hidden["edges"] = len(edges) - len(keep)
        edges = keep
        ends = {x for e in edges.values() for x in (e["source"], e["target"])}
        kept = {k: x for k, x in nodes.items() if k in ends or k not in joined}   # a node alone before stays
        hidden["nodes"] = len(nodes) - len(kept)
        nodes = kept
    # bounded: the most frequent nodes, and the most frequent lines among them
    capped = dict(w.capped)
    if len(nodes) > MOST_NODES:
        keep_n = sorted(nodes.values(), key=lambda x: (x["kind"] == "activity", -x["count"]))[:MOST_NODES]
        nodes = {x["id"]: x for x in keep_n}
        capped["nodes"] = True
    edges = {k: e for k, e in edges.items() if e["source"] in nodes and e["target"] in nodes}
    if len(edges) > MOST_EDGES:
        edges = dict(sorted(edges.items(), key=lambda kv: -kv[1]["count"])[:MOST_EDGES])
        capped["edges"] = True
    out_nodes = []
    for x in sorted(nodes.values(), key=lambda x: (kinds.index(x["itemKind"]), order[x["id"]], x["activity"])):
        out_nodes.append({**{k: v for k, v in x.items() if not k.startswith("_")}, "items": len(x["_items"]),
                          "order": order[x["id"]]})
    out_edges = []
    for e in sorted(edges.values(), key=lambda e: (e["kind"] != "follows", -e["count"], e["id"])):
        ts = e["_times"]
        d = {k: v for k, v in e.items() if not k.startswith("_")}
        d.update(items=len(e["_items"]), median=median(ts) if ts else None, timed=len(ts))
        if e["kind"] == "caused":
            d.update(causes=len(e["_causes"]),
                     types=[{"cause": a, "effect": b, "count": n} for (a, b), n in sorted(e["_types"].items(), key=lambda kv: -kv[1])])
        out_edges.append(d)
    present = {x["itemKind"] for x in out_nodes}
    info = []
    for k in kinds:
        ki = spec.items[k]
        info.append({"name": k, "states": list(ki.states), "drawn": k in present,
                     "by": by if (by == "events" or ki.states) else "events",
                     "items": sum(1 for id in w.steps if w.kind_of.get(id) == k)})
    return {"kind": "process", "by": by, "paths": paths, "kinds": info, "nodes": out_nodes, "edges": out_edges,
            "since": since, "until": until, "events": len(w.evs), "capped": {k: v for k, v in capped.items() if v},
            "total": total, "hidden": hidden, "most": {"nodes": MOST_NODES, "edges": MOST_EDGES, "events": MOST_EVENTS}}



def items_through(events, spec, kind: str, since: float, until: float, by: str | None = None, through: str | None = None,
                  followed: tuple[str, str] | None = None, caused: list[tuple[str, str, str]] | None = None) -> dict[str, list[float]]:
    """The items of ``kind`` behind a node (``through``: an activity, ``^`` or ``$``), a line within an item
    (``followed``: from, to), or lines from other items (``caused``: each (cause kind, its activity, this kind's
    activity), any of them) over the span, as the map counted them: each with when. Several asked: all of them."""
    kinds = [kind, *(c[0] for c in caused or () if c[0] != kind)]
    by = by if by in BY else default_by(spec, [kind])
    w = Window(events, spec, list(dict.fromkeys(kinds)), since, until, by)
    sets = []
    if through is not None:
        sets.append(w.through(kind, through))
    if followed is not None:
        sets.append(w.followed(kind, *followed))
    if caused:
        got: dict[str, list[float]] = {}
        for ck, a, b in caused:
            for id, ts in w.caused(kind, ck, a, b).items():
                got.setdefault(id, []).extend(ts)
        sets.append(got)
    if not sets:
        return {}
    out = sets[0]
    for x in sets[1:]:
        out = {id: ts for id, ts in out.items() if id in x}
    return {id: sorted(ts) for id, ts in out.items()}
