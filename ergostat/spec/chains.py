"""Item-state stocks not chained (SPEC §12, *A kind's states, chained*): when a kind's states are each counted by a
stock (``items: KIND, state: S``), the items that move from one state to the next must flow from one stock to the
next. A stock per state with each move written as an outflow to a cloud draws a row of separate stocks, each filled
by nothing, and a loop per step that shares no stock with the next: what the items do is not in the model.

What says an item moves from P to S, strongest first: the record (each move the item index kept, a lease's hold
taken out: into ``leased`` from P and out of it to S is one move, P to S); a block that takes the items at P and
moves them to S (``takes: {at: P, to: [S]}``); a flow's own sensor (an outflow from P's stock counting the items
entering S); and, for a stock nothing fills and nothing else explains, the kind's state order (the state before it).

A move is carried when a path of flows leads from P's stock to S's (through stocks of the items being worked,
``state: leased``, the steps template's work-in-progress), or when one side is an aggregate the other side can
rely on: a stock filled from outside by every item ``entering: S`` from two or more states (a stock of stopped
items, set aside from any step), or drained to outside by every item ``leaving: P`` to two or more. ergostat's own
lease states (``leased``, ``dead``) are not the kind's states and are left out.

Each finding names its fix, and ``fixes`` gives it as data, which ``numbers/structural.py`` makes an edit.

The boundary, crossed once (``arrivals``, ``boundary``): a kind's items brought in from clouds into two states or more
(``kind-enters-many-times``), and a model with many inflows from clouds for its stocks (``many-cloud-inflows``)."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .ir import Spec

LEASE_STATES = ("leased", "dead")
CACHE_FOR = 15.0                  # seconds a record's moves are kept per process (check, the pages, the improver)


@dataclass
class Fix:
    """One change that carries a move: a flow re-pointed (``retarget``: its ``key``, from or to, set to ``stock``), or
    a flow added (``add``) from one stock to another, measured as the items of ``kind`` entering ``state``."""

    op: str                                  # retarget | add | remove | stock (a stock added, counting kind in entering)
    flow: str = ""                           # retarget: the flow; add: the new flow's name
    key: str = ""                            # retarget: from | to
    stock: str = ""                          # retarget: the stock it now names
    source: str | None = None                # add: from (None: outside)
    target: str | None = None                # add: to
    kind: str = ""
    entering: str = ""
    where: dict = field(default_factory=dict)
    description: str = ""
    remove: str = ""                         # retarget: a flow it makes a double of (the same count, from outside), taken out
    unit: str = ""                           # stock: its unit

    def said(self) -> str:
        if self.op == "remove":
            return f"flow {self.flow} taken out"
        if self.op == "stock":
            return f"stock {self.stock}, counting the items of {self.kind} in {self.entering}"
        if self.op == "retarget":
            out = f"{self.key}: {self.stock} on flow {self.flow}"
            return out + (f", and flow {self.remove} taken out (it counts the same moves from outside)" if self.remove else "")
        w = "".join(f", {k}: {v}" for k, v in self.where.items())
        ends = " ".join(x for x in ((f"from {self.source}" if self.source else "from outside"),
                                    (f"to {self.target}" if self.target else "to outside")))
        return f"flow {self.flow} {ends}, measured as items of {self.kind} entering {self.entering}{w}"


@dataclass
class Found:
    code: str
    about: str
    where: object
    message: str
    fixes: list[Fix] = field(default_factory=list)
    moves: list[tuple] = field(default_factory=list)     # the moves (from, to) it says no flow carries (None: arrivals)


# ---- the record's moves

_CACHE: dict[str, tuple[float, dict]] = {}
_READING = threading.Lock()        # one reading of the record's moves at a time; the others wait and take it


def record_dir(spec: Spec) -> Path | None:
    """The project's state directory (``store.state_dir``, without making it), when there is a record in it."""
    from ..store import home
    try:
        root = Path(spec.root).resolve()
    except (TypeError, OSError):
        return None
    d = home() / f"{spec.name}-{hashlib.sha256(str(root).encode()).hexdigest()[:8]}"
    return d if (d / "events.db").exists() or (d / "events").is_dir() else None


def recorded(spec: Spec) -> dict[str, Counter]:
    """Per kind, how many times its items moved from one state to another in the record (``(None, S)``: arrivals, in
    the state their first event left them in), a lease's hold taken out. Empty when the project has no record yet."""
    kinds = [k for k in _kinds(spec)]
    if not kinds:
        return {}
    d = record_dir(spec)
    if d is None:
        return {}
    key = f"{d}|{','.join(sorted(kinds))}"
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_FOR:
        return hit[1]
    with _READING:                          # a model loaded by many threads at once reads the record once, not once each
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_FOR:
            return hit[1]
        out: dict[str, Counter] = {}
        try:
            from ..storage import Storage, open_events
            from .itemindex import index_for
            ix = index_for(open_events(getattr(spec, "storage", None) or Storage(), d), spec, False)
            if ix is not None:
                with ix.lock:               # the index's connection is the process's: one thread at a time on it
                    out = {k: ix.transitions(k, at_once=True) for k in kinds}
        except Exception:                   # a record that cannot be read now says nothing about the structure
            out = {}
        _CACHE[key] = (time.time(), out)
    return out


# ---- the kinds whose states are stocks

@dataclass
class Chain:
    kind: str
    order: list[str]                          # the kind's states, its own order (lease states left out)
    stock_of: dict[str, str]                  # state → the stock counting it
    stages: set[str]                          # stocks of its items being worked (state: leased)
    ages: dict[str, object] = field(default_factory=dict)   # stocks in the chain read as an age: name → its sensor
    where: object = None


def _count_sensor(st, spec: Spec):
    """A stock's sensor counting items in a state; and one reading their age (``oldest``, ``age``) when flows fill or
    drain the stock all the same: it stands in the chain, wrongly read (``chain-stock-not-a-count``)."""
    for s in st.sensors.values():
        q = s.items
        if q and q.get("state") and (q.get("measure", "count") == "count" or spec.flows_of(st.name)):
            yield s, q


def _kinds(spec: Spec) -> dict[str, Chain]:
    """The kinds with two or more of their states counted by stocks of their own: the chains."""
    return {k: c for k, c in _counted(spec).items() if len(set(c.stock_of.values())) >= 2}


def _counted(spec: Spec) -> dict[str, Chain]:
    """Every kind with a state a stock counts, whether or not another of its states has a stock."""
    out: dict[str, Chain] = {}
    for st in spec.stocks.values():
        for _, q in _count_sensor(st, spec):
            k = q["kind"]
            kd = spec.items.get(k)
            if kd is None:
                continue
            c = out.setdefault(k, Chain(k, [s for s in kd.states if s not in LEASE_STATES], {}, set(), where=kd.where))
            states = q["state"]
            where = {f: v for f, v in (q.get("where") or {}).items() if f != "lease.back"}
            if set(states) <= {"leased"}:
                c.stages.add(st.name)
                continue
            if where or any(s in LEASE_STATES for s in states):
                continue                      # a part of a state (only some fields), or ergostat's own: not the chain
            for s in states:
                c.stock_of.setdefault(s, st.name)
            if q.get("measure", "count") != "count":
                c.ages[st.name] = q
    return out


def _item_sensors(f):
    for s in f.sensors.values():
        if s.items:
            yield s.items


def _counts(f, kind: str, key: str) -> str | None:
    """The state a flow's sensor counts items of ``kind`` entering (``key`` "entering") or leaving, with no where."""
    for q in _item_sensors(f):
        if q["kind"] == kind and q.get(key) and not {x for x in (q.get("where") or {}) if x != "lease.back"}:
            return q[key]
    return None


# ---- the analysis

def analyse(spec: Spec, moves: dict[str, Counter] | None = None) -> list[Found]:
    moves = recorded(spec) if moves is None else moves
    out: list[Found] = []
    ix = _Index(spec)
    counted = _counted(spec)
    for k, kd in spec.items.items():                 # every kind, counted or not: an arrival may name only its state
        if k not in counted:
            counted[k] = Chain(k, [s for s in kd.states if s not in LEASE_STATES], {}, set(), where=kd.where)
    for c in counted.values():
        seen = moves.get(c.kind) or Counter()
        found = _one(spec, c, seen, ix) if len(set(c.stock_of.values())) >= 2 else []
        out += arrivals(spec, c, seen, ix, found) + found
    return out


class _Index:
    """The flows into and out of each stock, and the blocks taking each kind, in the model's order: once for every
    kind's chain, not scanned for each (docs/proposals/scale.md, #7)."""

    def __init__(self, spec: Spec):
        self.place = {n: i for i, n in enumerate(spec.flows)}
        self.into: dict[str | None, list] = {}
        self.out_of: dict[str | None, list] = {}
        for f in spec.flows.values():
            self.into.setdefault(f.target, []).append(f)
            self.out_of.setdefault(f.source, []).append(f)
        self.names = frozenset(spec.flows) | set(spec.stocks) | set(spec.auxiliaries) | set(spec.parameters) | \
            set(spec.goals) | set(spec.blocks)
        self.takers: dict[str, list] = {}
        for b in spec.blocks.values():
            if b.takes:
                self.takers.setdefault(b.takes.kind, []).append(b)

    def touching(self, stocks: set[str]) -> list:
        """The flows with an end in these stocks, in the model's order."""
        got = {f.name: f for s in stocks for f in (*self.into.get(s, ()), *self.out_of.get(s, ()))}
        return [got[n] for n in sorted(got, key=self.place.__getitem__)]


def _one(spec: Spec, c: Chain, seen: Counter, ix: _Index | None = None) -> list[Found]:
    ix = ix or _Index(spec)
    k = c.kind
    stocks = set(c.stock_of.values()) | c.stages
    rank = {s: i for i, s in enumerate(c.order)}
    modelled = sorted(c.stock_of, key=lambda s: rank.get(s, len(rank)))
    inflows = {s: list(ix.into.get(s, ())) for s in stocks}
    outflows = {s: list(ix.out_of.get(s, ())) for s in stocks}

    def reach(a: str, b: str, through: set[str]) -> bool:
        """A path of flows from stock a to stock b, through these stocks only."""
        todo, been = [a], {a}
        while todo:
            x = todo.pop()
            for f in outflows.get(x, []):
                t = f.target
                if t == b:
                    return True
                if t in through and t not in been:
                    been.add(t)
                    todo.append(t)
        return False

    # every move something says happens, between two states with stocks of their own, and what says so
    why: dict[tuple[str, str], list[str]] = {}

    raw: dict[tuple[str, str], list[str]] = {}       # every move said, between any two of the kind's states

    def says(p, s, what):
        if p != s and p not in LEASE_STATES and s not in LEASE_STATES:
            raw.setdefault((p, s), []).append(what)
        if p in c.stock_of and s in c.stock_of and p != s and c.stock_of[p] != c.stock_of[s]:
            why.setdefault((p, s), []).append(what)
    for (p, s), n in seen.items():
        if p is not None:
            says(p, s, f"{n} move{'s' if n != 1 else ''} in the record")
    for b in ix.takers.get(k, ()):
        t = b.takes
        if t and t.kind == k:
            for p in t.at:
                for s in t.to:
                    says(p, s, f"block {b.name} takes them at {p} to {s}")
    for f in ix.touching(stocks):
        if f.source in stocks and f.target is None and (s := _counts(f, k, "entering")):
            for p in [x for x, st in c.stock_of.items() if st == f.source][:1]:
                says(p, s, f"flow {f.name} counts them entering {s}")
        if f.target in stocks and f.source is None and (p := _counts(f, k, "leaving")):
            for s in [x for x, st in c.stock_of.items() if st == f.target][:1]:
                says(p, s, f"flow {f.name} counts them leaving {p}")
    for i, x in enumerate(c.order):            # a state with no stock that items leave, and nothing says how they come
        if i and x not in c.stock_of and any(a == x for a, _ in raw) and not any(b == x for _, b in raw):
            says(c.order[i - 1], x, f"the kind's states, {c.order[i - 1]} before {x}")
    for p in modelled:                         # moves through states with no stock: P to S by way of them
        todo, been = [(p, [])], {p}
        while todo:
            x, via = todo.pop(0)
            for a, b in raw:
                if a != x or b in been:
                    continue
                been.add(b)
                if b in c.stock_of:
                    if via and c.stock_of[b] != c.stock_of[p] and (p, b) not in why:
                        why[(p, b)] = [f"{'; '.join(raw[(p, via[0])][:1])}, then on through {', '.join(via)} (no stock of "
                                       f"{'its' if len(via) == 1 else 'their'} own: give "
                                       f"{'it' if len(via) == 1 else 'each'} a stock in the chain if items wait there)"]
                else:
                    todo.append((b, via + [b]))
    for i, s in enumerate(modelled):           # a stock nothing fills, and nothing else explains: the state before it
        if i == 0 or inflows[c.stock_of[s]] or any(m[1] == s for m in why):
            continue
        before = [x for x in modelled[:i] if c.stock_of[x] != c.stock_of[s]]
        if before:
            says(before[-1], s, f"the kind's states, {before[-1]} before {s}")

    origins = {s: {p for p, x in why if x == s} for s in c.stock_of}
    dests = {p: {s for x, s in why if x == p} for p in c.stock_of}

    def gathers(s: str) -> bool:             # filled from outside by every item entering s, from two states or more
        return len(origins[s]) >= 2 and any(f.source is None and _counts(f, k, "entering") == s for f in inflows[c.stock_of[s]])

    def scatters(p: str) -> bool:
        """Drained to outside by every item leaving p, to two states or more (or a side stock, gathered from any state
        and sent back to any)."""
        return (len(dests[p]) >= 2 or gathers(p)) and \
            any(f.target is None and _counts(f, k, "leaving") == p for f in outflows[c.stock_of[p]])

    def carried(p: str, s: str) -> bool:
        """A move from p to s carried by the flows. One the record saw is direct, so its path may pass only through the
        stocks of items being worked; one a block or the order implies may pass through other states (a block taking
        at proposed to testing may move them through building on the way)."""
        a, b = c.stock_of[p], c.stock_of[s]
        direct = any(x.endswith("in the record") for x in why.get((p, s), []))
        return reach(a, b, c.stages if direct else stocks) or (gathers(s) and bool(outflows[a])) or (scatters(p) and bool(inflows[b]))

    found: list[Found] = []
    for name, q in c.ages.items():
        found.append(Found("chain-stock-not-a-count", f"stock.{name}", spec.stocks[name].where,
                           f"stock {name}: flows move items of {k} into or out of it, but its sensor reads the hours the "
                           f"{'oldest has waited' if q.get('measure') == 'oldest' else 'oldest has been seen'} "
                           f"(measure: {q.get('measure')}). A stock in the chain counts the items in its state: "
                           f"measure: count (the default); keep the age as a stock of its own beside the chain "
                           f"({name}-oldest: {{sensor: {{items: {k}, state: {', '.join(q['state'])}, measure: oldest}}}}), "
                           f"with no flows, for a goal on how long they wait"))
    by_about: dict[tuple[str, str], Found] = {}
    taken: set[str] = set()                     # the names given here, over the model's own (ix.names)

    def free(name: str) -> str:
        out, i = name, 2
        while out in ix.names or out in taken:
            out, i = f"{name}-{i}", i + 1
        taken.add(out)
        return out

    def add(code, about, where, msg, fix, evidence="", move=None):
        x = by_about.get((code, about))
        if x is None:
            x = by_about[(code, about)] = Found(code, about, where, msg, [fix])
            found.append(x)
        else:
            x.message += f"; and also {fix.said()}" + (f" ({evidence})" if evidence else "")
            x.fixes.append(fix)
        if move is not None:
            x.moves.append(move)

    first = c.order[0] if c.order else None    # arrivals: the kind's first state, filled from outside
    if first in c.stock_of and not inflows[c.stock_of[first]]:
        b = c.stock_of[first]
        fix = Fix("add", flow=free(f"{b}-arriving"), source=None, target=b, kind=k, entering=first,
                  description=f"items of {k} arriving (in {first}, the kind's first state)")
        add("state-stock-without-inflow", f"stock.{b}", spec.stocks[b].where,
            f"stock {b}: nothing fills it, but every item of {k} arrives in {first}, the kind's first state. The chain "
            f"starts with arrivals from outside: {fix.said()} (or the collector's flow that finds the work, to: {b})", fix,
            move=(None, first))

    retargeted: set[str] = set()
    for (p, s), ev in sorted(why.items(), key=lambda m: (rank.get(m[0][0], 99), rank.get(m[0][1], 99))):
        if carried(p, s):
            continue
        a, b = c.stock_of[p], c.stock_of[s]
        evidence = "; ".join(ev)
        cloud_out = [f for f in outflows[a] if f.target is None and f.name not in retargeted and not scatters(p)]
        cloud_in = [f for f in inflows[b] if f.source is None]
        g = next((f for f in cloud_out if _counts(f, k, "entering") == s), None) or \
            next((f for f in cloud_out if dests[p] == {s} and _counts(f, k, "leaving") in (p, None)
                  and _counts(f, k, "entering") in (None, s)), None)
        if g is not None:
            retargeted.add(g.name)
            twin = next((h for h in cloud_in if spec.actuator_of(h.name) is None and (_counts(h, k, "entering") == s or (
                not any(q.get("kind") == k for q in _item_sensors(h)) and origins[s] == {p}))), None)
            fix = Fix("retarget", flow=g.name, key="to", stock=b, remove=twin.name if twin else "")
            add("outflow-not-chained", f"flow.{g.name}", g.where,
                f"flow {g.name}: drains {a} to outside, but the items of {k} it moves go on to {s}, counted by stock "
                f"{b} ({evidence}). A move from one state to the next is a flow from one stock to the next: write "
                f"{fix.said()}", fix, move=(p, s))
            continue
        arrive = s == (c.order[0] if c.order else None) or seen.get((None, s))      # it counts arrivals too: not moves
        h = None if arrive else next((f for f in cloud_in if origins[s] == {p} and _counts(f, k, "entering") in (s, None)), None)
        if h is not None:
            fix = Fix("retarget", flow=h.name, key="from", stock=a)
            add("inflow-not-chained", f"flow.{h.name}", h.where,
                f"flow {h.name}: fills {b} from outside, but the items of {k} it brings come from {p}, counted by stock "
                f"{a} ({evidence}). A move from one state to the next is a flow from one stock to the next: write "
                f"{fix.said()}", fix, move=(p, s))
            continue
        many = len(origins[s]) >= 2
        lease = any(bl.takes and bl.takes.kind == k and p in bl.takes.at for bl in spec.blocks.values())
        fix = Fix("add", flow=free(f"{a}-to-{b}"), source=a, target=b, kind=k, entering=s,
                  where={"lease.back": p} if many and lease else {},
                  description=f"items of {k} moving from {p} to {s}")
        st = spec.stocks[b]
        note = (f" (items enter {s} from {', '.join(sorted(origins[s]))}: entering {s} alone counts them all"
                + ("; the lease's back state tells this one apart)" if fix.where else ", so share it out or tell them apart)")) \
            if many else ""
        if not inflows[b]:
            add("state-stock-without-inflow", f"stock.{b}", st.where,
                f"stock {b}: nothing fills it, but items of {k} arrive in {s} from {p}, counted by stock {a} ({evidence}). "
                f"Chain them: {fix.said()}{note}", fix, evidence, (p, s))
        else:
            add("move-without-flow", f"stock.{b}", st.where,
                f"stock {b}: items of {k} move into {s} from {p} ({evidence}), and no flow carries them from {a} to {b}. "
                f"Add {fix.said()}{note}", fix, evidence, (p, s))

    fixes = [x for f in found for x in f.fixes]
    joins = [x for x in fixes if x.op == "retarget" or x.source]     # (pieces no move joins: a state with no stock between)
    pieces = _pieces(c, spec, carried, why)
    if len(pieces) > 1 and joins:
        shown = "; ".join("[" + ", ".join(p) + "]" for p in pieces)
        head = c.stock_of[modelled[0]]
        found.append(Found("state-stocks-disconnected", f"stock.{head}", c.where,
                           f"items {k}: its state stocks are {len(pieces)} pieces that no flow joins ({shown}). Its items "
                           f"move from state to state, so their stocks are one chain: arrivals from outside into the "
                           f"first, a flow from each state's stock to the next, completions out of the last. "
                           + (f"The changes that join them: {'; '.join(x.said() for x in fixes)}" if fixes else
                              "Nothing says which state follows which: give the kind's states in order, and a flow "
                              "for each move"), fixes))
    lp = _loops(spec, c, gathers) if joins else None
    if lp is not None:
        groups, g0 = lp
        found.append(Found("loops-not-connected", f"stock.{spec.goals[g0].of.name}", spec.goals[g0].where,
                           f"items {k}: the loops of its {sum(len(g) for g in groups)} goals are {len(groups)} groups that "
                           f"share no stock ({'; '.join('[' + ', '.join(g) + ']' for g in groups)}). The steps of one "
                           f"workflow pass the items on, so each step's loop should end in the stock the next step's loop "
                           f"holds: the chain of its state stocks is missing"
                           + (f" ({len(fixes)} change{'s' if len(fixes) != 1 else ''} join it: "
                              f"{'; '.join(x.said() for x in fixes)})" if fixes else ""), fixes))
    return found


def _pieces(c: Chain, spec: Spec, carried, why) -> list[list[str]]:
    """The kind's state stocks in groups joined by flows (through the stocks of items being worked) or by a carried
    move; each group in the kind's state order."""
    stocks = sorted(set(c.stock_of.values()), key=lambda st: min(c.order.index(s) if s in c.order else 99
                                                                  for s, x in c.stock_of.items() if x == st))
    parent = {s: s for s in [*stocks, *c.stages]}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a, b):
        parent[root(a)] = root(b)
    for f in spec.flows.values():
        if f.source in parent and f.target in parent:
            join(f.source, f.target)
    for p, s in why:
        if carried(p, s):
            join(c.stock_of[p], c.stock_of[s])
    groups: dict[str, list[str]] = {}
    for s in stocks:
        groups.setdefault(root(s), []).append(s)
    return list(groups.values())


def _loops(spec: Spec, c: Chain, gathers) -> tuple[list[list[str]], str] | None:
    """The goals on the kind's stocks grouped by the stocks their loops share; None when they are one group (or fewer
    than two goals). A stock that gathers items from every state (an aggregate inflow) shares the stocks it gathers from."""
    stocks = set(c.stock_of.values()) | c.stages
    goals = [g for g in spec.goals.values() if g.of.kind == "stock" and g.of.name in stocks]
    if len(goals) < 2:
        return None
    sets = {}
    for g in goals:
        lp = spec.loop(g.name)
        mine = {g.of.name}
        for a in lp.actuators:                 # the flows its loop's blocks set, and the stocks at their ends
            for r in spec.blocks[a].targets():
                f = spec.flows.get(r.name) if r.kind == "flow" else None
                if f is not None:
                    mine |= {x for x in (f.source, f.target) if x}
        for s, st in c.stock_of.items():
            if st == g.of.name and gathers(s):
                mine |= set(c.stock_of.values())
        sets[g.name] = mine
    names = list(sets)
    parent = {n: n for n in names}

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if sets[a] & sets[b]:
                parent[root(a)] = root(b)
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(root(n), []).append(n)
    if len(groups) < 2:
        return None
    return list(groups.values()), goals[0].name


# ---- a kind entering from outside more than once (SPEC §12, *The boundary, crossed once*)

def entries(spec: Spec, c: Chain, ix: _Index) -> dict[str, list]:
    """The inflows from a cloud measured as items of the kind, by the state they enter: a sensor counting the items
    ``entering:`` it, or, with no sensor of the kind, the stock it fills when that stock counts a state of the kind
    (its first, by the kind's order). A two-way flow (a setting stepped, a measure smoothed) is no arrival, and a sensor
    with a ``where`` counts a part of the kind (some of its fields), as the chain leaves out a stock of a part."""
    rank = {s: i for i, s in enumerate(c.order)}
    states_of: dict[str, list[str]] = {}
    for x, st in c.stock_of.items():
        states_of.setdefault(st, []).append(x)
    out: dict[str, list] = {}
    for f in ix.out_of.get(None, ()):
        if f.target is None or f.two_way:
            continue
        mine = [q for q in _item_sensors(f) if q["kind"] == c.kind]
        if any({x for x in (q.get("where") or {}) if x != "lease.back"} for q in mine):
            continue
        state = next((q["entering"] for q in mine if q.get("entering")), None)
        if state is None and (mine or not any(True for _ in _item_sensors(f))):
            state = min(states_of.get(f.target, ()), key=lambda x: rank.get(x, len(rank)), default=None)
        if state and state not in LEASE_STATES:
            out.setdefault(state, []).append(f)
    return out


def _first(c: Chain, entered, seen: Counter) -> str:
    """The state the kind arrives in: of those its inflows from clouds enter, the first by the kind's order among the
    states the record saw items arrive in (their first event), else the first by the kind's order."""
    rank = {s: i for i, s in enumerate(c.order)}
    came = [s for s in entered if seen.get((None, s))]
    return min(came or list(entered), key=lambda x: rank.get(x, len(rank)))


@dataclass
class _Origin:
    """Where the items entering a state come from inside the model: each stocked state with the states between that
    have no stock of their own (``via``), what says so, and how many reach it from outside through such states only."""

    came: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    why: str = ""
    moved: list[int] = field(default_factory=list)   # the record: how many moved in from each of ``came``
    outside: int = 0                 # the record: items whose first state with a stock is this one
    unstocked: bool = False          # the order: no state before it has a stock, so they cross the boundary into it


def _came_from(c: Chain, s: str, h, seen: Counter, ix: _Index) -> _Origin:
    """The states the items entering ``s`` come from, strongest first: the flow's own sensor (``leaving: P``), the
    record's moves (back through states with no stock of their own, to one with a stock or to the boundary), a block
    taking them at P to S, an outflow from P's stock counting them entering S, and the kind's state order (back to the
    nearest state before S with a stock of its own)."""
    p = _counts(h, c.kind, "leaving")
    if p and p != s and p in c.stock_of:
        return _Origin([(p, ())], f"flow {h.name} counts them leaving {p}")
    rec: Counter = Counter()
    outside = 0
    todo, been = [(s, (), 0)], {s}
    while todo:                                   # back through the record's moves, past states with no stock
        x, via, n0 = todo.pop(0)
        for (a, b), n in sorted(seen.items(), key=lambda m: (m[0][0] or "", m[0][1])):
            if b != x or a in LEASE_STATES:
                continue
            if a is None:
                outside += (n0 or n) if via else 0
                continue
            if a in been:
                continue
            been.add(a)
            if a in c.stock_of:
                rec[(a, via)] += n0 or n
            else:
                todo.append((a, (a, *via), n0 or n))
    if rec or outside:
        why = "; ".join(f"{n} move{'s' if n != 1 else ''} from {a}" + (f" through {', '.join(v)}" if v else "") +
                        " in the record" for (a, v), n in rec.most_common())
        return _Origin([m for m, _ in rec.most_common()], why, [n for _, n in rec.most_common()], outside)
    took = [(b.name, p) for b in ix.takers.get(c.kind, ()) if b.takes and s in b.takes.to for p in b.takes.at
            if p != s and p in c.stock_of]
    if took:
        return _Origin([(p, ()) for p in dict.fromkeys(p for _, p in took)],
                       "; ".join(f"block {n} takes them at {p} to {s}" for n, p in took))
    by_flow: list[tuple[str, str]] = []
    for st in dict.fromkeys(c.stock_of.values()):
        for g in ix.out_of.get(st, ()):
            if g.target is None and _counts(g, c.kind, "entering") == s:
                by_flow += [(g.name, x) for x, y in c.stock_of.items() if y == st][:1]
    if by_flow:
        return _Origin([(p, ()) for p in dict.fromkeys(p for _, p in by_flow)],
                       "; ".join(f"flow {n} counts them entering {s} as they leave {c.stock_of[p]}" for n, p in by_flow))
    if s in c.order:
        via: tuple[str, ...] = ()
        for x in reversed(c.order[:c.order.index(s)]):
            if x in c.stock_of:
                return _Origin([(x, via)], f"the kind's states, {', '.join((x, *via))} before {s}")
            via = (x, *via)
    return _Origin(unstocked=True)


def _said_origins(c: Chain, s: str, seen: Counter, ix: _Index) -> set[str]:
    """Every state with a stock the record or a block says items enter ``s`` from (the chain's ``gathers``)."""
    out = {a for (a, b), n in seen.items() if b == s and n and a in c.stock_of and a != s}
    return out | {p for b in ix.takers.get(c.kind, ()) if b.takes and s in b.takes.to for p in b.takes.at
                  if p != s and p in c.stock_of}


def _free(name: str, ix: _Index, taken: set[str]) -> str:
    out, i = name, 2
    while out in ix.names or out in taken:
        out, i = f"{name}-{i}", i + 1
    taken.add(out)
    return out


def arrivals(spec: Spec, c: Chain, seen: Counter, ix: _Index, chained: list[Found]) -> list[Found]:
    """``kind-enters-many-times``: the kind's items brought in from clouds into two states or more. A cloud is the
    system's boundary, so this counts the same items twice, or draws their moves between the kind's own stocks as
    arrivals. The arrival into the first state is kept; each other inflow is re-pointed ``from:`` the stock of the state
    its items come from (taken out when that is the stock it fills; through a state with no stock between, that state
    given one, so the outflow into it and the inflow out of it meet there). The chain's own finding on the same flow
    (``inflow-not-chained``, taken out of ``chained``) is this one; a flow ``outflow-not-chained`` already takes out
    (a twin) is left to it, and so is a stock filled by every item entering it from two states or more (the chain's
    aggregate: stopped, set aside from any step). A state the record shows items arriving in directly, or through
    states with no stock only, is a real arrival: a note, not a fault. So is one no state with a stock comes before
    (the items cross the boundary through states the model keeps no stock of, and branch)."""
    k = c.kind
    entered = entries(spec, c, ix)
    if len(entered) < 2:
        return []
    rank = {s: i for i, s in enumerate(c.order)}
    keep = _first(c, entered, seen)
    twins = {x.remove for f in chained for x in f.fixes if x.op == "retarget" and x.remove}
    filled = {x.stock for f in chained for x in f.fixes if x.op == "retarget" and x.key == "to"} | \
        {x.target for f in chained for x in f.fixes if x.op == "add" and x.source}     # moves into it the chain carries
    inflow = {f.about.removeprefix("flow."): f for f in chained if f.code == "inflow-not-chained"}
    fixes: list[Fix] = []
    moves: list[tuple] = []
    said: list[str] = []
    real: list[str] = []
    absorbed: list[Found] = []
    taken: set[str] = set()
    for s in sorted(entered, key=lambda x: rank.get(x, len(rank))):
        if s == keep:
            continue
        for h in entered[s]:
            if h.name in twins or h.target in filled:
                continue                       # the chain's own finding carries these moves: one finding, not two
            o = _came_from(c, s, h, seen, ix)
            n = seen.get((None, s), 0) + o.outside
            if n:
                inside = sum(o.moved)
                real.append(f"flow {h.name} into {s}: the record shows {n} item{'s' if n != 1 else ''} whose first event "
                            f"puts {'it' if n == 1 else 'them'} in {s}"
                            + (" (or in states with no stock before it)" if o.outside else "")
                            + " (arriving from the outside system already there: reopened, say), so that arrival is real"
                            + (f"; {inside} more moved into {s} from {', '.join(a for a, _ in o.came) or 'its other states'}"
                               f", so make sure {h.name} counts only the arrivals, and a flow from stock to stock carries "
                               f"the moves" if inside else ""))
                continue
            if o.unstocked:
                continue                       # no state with a stock comes before it: the boundary is crossed here
            if _counts(h, k, "entering") == s and len(_said_origins(c, s, seen, ix) | {a for a, _ in o.came}) >= 2:
                continue                       # the chain's aggregate: every item entering s, from any state
            x = inflow.get(h.name)
            if x is not None:
                absorbed.append(x)
                fixes += x.fixes
                moves += x.moves
                said.append(f"flow {h.name} into {s}: its items come from {', '.join(a for a, _ in o.came)} ({o.why}): "
                            f"write {'; '.join(f.said() for f in x.fixes)}")
                continue
            if len(o.came) >= 2:
                said.append(f"flow {h.name} into {s}: its items come from {', '.join(a for a, _ in o.came)} ({o.why}): "
                            f"a flow from each of those states' stocks to {h.target}, measured as items of {k} entering "
                            f"{s} (told apart, or shared out), and {h.name} taken out, since it counts them all again")
                continue
            p, via = o.came[0]
            a = c.stock_of[p]
            g = next((f for f in ix.out_of.get(a, ()) if f.target is None and len(via) == 1
                      and _counts(f, k, "entering") == via[0]), None)
            if g is not None:                  # P's stock drains into a state with no stock, and h fills from it
                st = spec.stocks[a]
                new = _free(f"{k}-{via[0]}", ix, taken)
                made = [Fix("stock", stock=new, source=a, kind=k, entering=via[0], unit=st.unit,
                            description=f"items of {k} in {via[0]}, between {p} and {s}"),
                        Fix("retarget", flow=g.name, key="to", stock=new),
                        Fix("retarget", flow=h.name, key="from", stock=new)]
                said.append(f"flow {h.name} into {s}: its items come from {via[0]} ({o.why}), which has no stock of its "
                            f"own, and flow {g.name} drains {a} to outside as they enter it: the move {p} to {via[0]} to "
                            f"{s} drawn as a departure and an arrival. Give {via[0]} its stock: "
                            f"{'; '.join(f.said() for f in made)}")
                fixes += made
                moves += [(p, via[0]), (via[0], s)]
                continue
            fix = Fix("remove", flow=h.name) if a == h.target else Fix("retarget", flow=h.name, key="from", stock=a)
            if a == h.target:
                said.append(f"flow {h.name} into {s}: its items come from {p} ({o.why}), already counted by {a}, the "
                            f"stock it fills, so it counts them twice: {fix.said()}")
            else:
                said.append(f"flow {h.name} into {s}: its items come from {p} ({o.why}): write {fix.said()}"
                            + (f" (they pass through {', '.join(via)}, with no stock of "
                               f"{'its' if len(via) == 1 else 'their'} own: give {'it' if len(via) == 1 else 'each'} a "
                               f"stock in the chain if items wait there)" if via else ""))
            fixes.append(fix)
            moves.append((p, s))
    if not said and not real:
        return []
    for x in absorbed:
        chained.remove(x)
    names = "; ".join(f"{', '.join(f.name for f in entered[s])} into {s}"
                      for s in sorted(entered, key=lambda x: rank.get(x, len(rank))))
    head = (f"items {k}: flows bring its items in from outside (a cloud) into {len(entered)} different states ({names}). "
            f"A cloud is the system's boundary, so the items cross it once: one arrival into {keep}, "
            f"{'the state the record sees them arrive in' if seen.get((None, keep)) else 'its first state'}, and a flow "
            f"from stock to stock for every move after that")
    where = spec.items[k].where if k in spec.items else c.where
    if not said:
        return [Found("kind-enters-many-times", f"items.{k}", where, f"{head}. A note, not a fault: {'; '.join(real)}")]
    msg = (f"{head}. Arriving again in a later state either counts the same items twice (once as they arrive, again as "
           f"they reach it) or draws a move between {k}'s own stocks as an arrival, so those stocks relate only through "
           f"information links. Keep the arrival into {keep}; {'; '.join(said)}"
           + (f". A note: {'; '.join(real)}" if real else ""))
    return [Found("kind-enters-many-times", f"items.{k}", where, msg, fixes, moves)]


MANY_CLOUDS = 5            # inflows from clouds, beyond each kind's one arrival, before there are many to look at


def boundary(spec: Spec, moves: dict[str, Counter] | None = None) -> Found | None:
    """``many-cloud-inflows``: more inflows from clouds than half the model's stocks (and at least ``MANY_CLOUDS``), not
    counting each item kind's arrival into the state it arrives in (the boundary, rightly crossed once per kind) nor a
    two-way flow (a setting stepped, a measure smoothed: an adjustment, not an arrival), nor the parts a template made
    (its own boundary). Most stocks then fill from outside, so they pass little to each other and the model explains
    little of what comes in."""
    if not spec.stocks:
        return None
    moves = moves or {}
    ix = _Index(spec)
    counted = _counted(spec)
    proper: set[str] = set()
    for k, kd in spec.items.items():
        c = counted.get(k) or Chain(k, [s for s in kd.states if s not in LEASE_STATES], {}, set(), where=kd.where)
        entered = entries(spec, c, ix)
        if entered:
            proper |= {f.name for f in entered[_first(c, entered, moves.get(k) or Counter())]}

    from .ir import once_made  # a once template's part: its boundary, not the model's
    extra = [f.name for f in ix.out_of.get(None, ()) if f.target and not f.two_way and f.name not in proper
             and not once_made(spec, f)]
    stocks = [st for st in spec.stocks.values() if not once_made(spec, st)]
    if len(extra) < MANY_CLOUDS or 2 * len(extra) <= len(stocks):
        return None
    from .load import Where
    return Found("many-cloud-inflows", "model", Where(spec.files[0], 1) if spec.files else None,
                 f"the model has {len(extra)} inflows from outside (clouds) for its {len(stocks)} stocks, beyond each item "
                 f"kind's one arrival: {', '.join(extra)}. A cloud is the model's boundary: what comes from it is "
                 f"taken as given, not explained. Draw the boundary chart (Sterman, ch. 3: what the model explains, what "
                 f"it takes as given, what it leaves out) and decide what is really outside: something that leaves one "
                 f"of the model's stocks and fills another is a flow from the one to the other, not an arrival into "
                 f"each; a quantity that arrives from outside stays a cloud")


def findings(spec: Spec, say, moves: dict[str, Counter] | None = None) -> None:
    moves = recorded(spec) if moves is None else moves
    for x in analyse(spec, moves):
        say(x.code, x.message, x.where, x.about)
    b = boundary(spec, moves)
    if b is not None:
        say(b.code, b.message, b.where, b.about)
