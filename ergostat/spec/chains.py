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

Each finding names its fix, and ``fixes`` gives it as data, which ``numbers/structural.py`` makes an edit."""

from __future__ import annotations

import hashlib
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

    op: str                                  # retarget | add
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

    def said(self) -> str:
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


# ---- the record's moves

_CACHE: dict[str, tuple[float, dict]] = {}


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
    """Per kind, how many times its items moved from one state to another in the record (``(None, S)``: arrivals),
    a lease's hold taken out. Empty when the project has no record yet."""
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
    out: dict[str, Counter] = {}
    try:
        from ..storage import Storage, open_events
        from .itemindex import index_for
        ix = index_for(open_events(getattr(spec, "storage", None) or Storage(), d), spec, False)
        if ix is not None:
            out = {k: ix.transitions(k) for k in kinds}
    except Exception:                       # a record that cannot be read now says nothing about the structure
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
    where: object = None


def _count_sensor(st):
    for s in st.sensors.values():
        q = s.items
        if q and q.get("measure", "count") == "count" and q.get("state"):
            yield s, q


def _kinds(spec: Spec) -> dict[str, Chain]:
    out: dict[str, Chain] = {}
    for st in spec.stocks.values():
        for _, q in _count_sensor(st):
            k = q["kind"]
            kd = spec.items.get(k)
            if kd is None:
                continue
            c = out.setdefault(k, Chain(k, [s for s in kd.states if s not in LEASE_STATES], {}, set(), kd.where))
            states = q["state"]
            where = {f: v for f, v in (q.get("where") or {}).items() if f != "lease.back"}
            if set(states) <= {"leased"}:
                c.stages.add(st.name)
                continue
            if where or any(s in LEASE_STATES for s in states):
                continue                      # a part of a state (only some fields), or ergostat's own: not the chain
            for s in states:
                c.stock_of.setdefault(s, st.name)
    return {k: c for k, c in out.items() if len(set(c.stock_of.values())) >= 2}


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
    for c in _kinds(spec).values():
        out += _one(spec, c, moves.get(c.kind) or Counter())
    return out


def _one(spec: Spec, c: Chain, seen: Counter) -> list[Found]:
    k = c.kind
    stocks = set(c.stock_of.values()) | c.stages
    rank = {s: i for i, s in enumerate(c.order)}
    modelled = sorted(c.stock_of, key=lambda s: rank.get(s, len(rank)))
    inflows = {s: [f for f in spec.flows.values() if f.target == s] for s in stocks}
    outflows = {s: [f for f in spec.flows.values() if f.source == s] for s in stocks}

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
    for b in spec.blocks.values():
        t = b.takes
        if t and t.kind == k:
            for p in t.at:
                for s in t.to:
                    says(p, s, f"block {b.name} takes them at {p} to {s}")
    for f in spec.flows.values():
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
    by_about: dict[tuple[str, str], Found] = {}
    taken = set(spec.flows) | set(spec.stocks) | set(spec.auxiliaries) | set(spec.parameters) | set(spec.goals) | set(spec.blocks)

    def free(name: str) -> str:
        out, i = name, 2
        while out in taken:
            out, i = f"{name}-{i}", i + 1
        taken.add(out)
        return out

    def add(code, about, where, msg, fix, evidence=""):
        x = by_about.get((code, about))
        if x is None:
            x = by_about[(code, about)] = Found(code, about, where, msg, [fix])
            found.append(x)
        else:
            x.message += f"; and also {fix.said()}" + (f" ({evidence})" if evidence else "")
            x.fixes.append(fix)

    first = c.order[0] if c.order else None    # arrivals: the kind's first state, filled from outside
    if first in c.stock_of and not inflows[c.stock_of[first]]:
        b = c.stock_of[first]
        fix = Fix("add", flow=free(f"{b}-arriving"), source=None, target=b, kind=k, entering=first,
                  description=f"items of {k} arriving (in {first}, the kind's first state)")
        add("state-stock-without-inflow", f"stock.{b}", spec.stocks[b].where,
            f"stock {b}: nothing fills it, but every item of {k} arrives in {first}, the kind's first state. The chain "
            f"starts with arrivals from outside: {fix.said()} (or the collector's flow that finds the work, to: {b})", fix)

    retargeted: set[str] = set()
    for (p, s), ev in sorted(why.items(), key=lambda m: (rank.get(m[0][0], 99), rank.get(m[0][1], 99))):
        if carried(p, s):
            continue
        a, b = c.stock_of[p], c.stock_of[s]
        evidence = "; ".join(ev)
        cloud_out = [f for f in outflows[a] if f.target is None and f.name not in retargeted and not scatters(p)]
        cloud_in = [f for f in inflows[b] if f.source is None]
        g = next((f for f in cloud_out if _counts(f, k, "entering") == s), None) or \
            next((f for f in cloud_out if dests[p] == {s} and _counts(f, k, "leaving") in (p, None)), None)
        if g is not None:
            retargeted.add(g.name)
            twin = next((h for h in cloud_in if spec.actuator_of(h.name) is None and (_counts(h, k, "entering") == s or (
                not any(q.get("kind") == k for q in _item_sensors(h)) and origins[s] == {p}))), None)
            fix = Fix("retarget", flow=g.name, key="to", stock=b, remove=twin.name if twin else "")
            add("outflow-not-chained", f"flow.{g.name}", g.where,
                f"flow {g.name}: drains {a} to outside, but the items of {k} it moves go on to {s}, counted by stock "
                f"{b} ({evidence}). A move from one state to the next is a flow from one stock to the next: write "
                f"{fix.said()}", fix)
            continue
        arrive = s == (c.order[0] if c.order else None) or seen.get((None, s))      # it counts arrivals too: not moves
        h = None if arrive else next((f for f in cloud_in if origins[s] == {p} and _counts(f, k, "entering") in (s, None)), None)
        if h is not None:
            fix = Fix("retarget", flow=h.name, key="from", stock=a)
            add("inflow-not-chained", f"flow.{h.name}", h.where,
                f"flow {h.name}: fills {b} from outside, but the items of {k} it brings come from {p}, counted by stock "
                f"{a} ({evidence}). A move from one state to the next is a flow from one stock to the next: write "
                f"{fix.said()}", fix)
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
                f"Chain them: {fix.said()}{note}", fix, evidence)
        else:
            add("move-without-flow", f"stock.{b}", st.where,
                f"stock {b}: items of {k} move into {s} from {p} ({evidence}), and no flow carries them from {a} to {b}. "
                f"Add {fix.said()}{note}", fix, evidence)

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


def findings(spec: Spec, say, moves: dict[str, Counter] | None = None) -> None:
    for x in analyse(spec, moves):
        say(x.code, x.message, x.where, x.about)
