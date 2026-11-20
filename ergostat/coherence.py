"""Coherence (SPEC §12l): one system drawn three ways, held against each other. The **Process** view is what the record
says the items did (``process.py``: each item's moves between states, a lease's hold folded out); **Dynamics** is what
the model says accumulates and moves (a kind's state stocks, chained by flows: ``spec/chains.py``); **Blocks** is what
the model says moves it (the blocks and their ``out:`` flows and ``takes:``, the goals and their loops). Each pair is
compared, and each disagreement is a finding with the file and line to change, the change when it is clear, and the
pair that disagrees:

- **Process ↔ Dynamics**: every move the record shows between two states with stocks is carried by the chain's flows
  (``chains.py``'s own findings, given the window's moves, say which are not, with their fixes: a move backward is
  rework, one past a stock the chain passes through is a skip, one against the chain's direction contradicts it);
  arrivals come in where the chain starts, completions leave where it ends; every flow of the chain is seen moving,
  or the record has not exercised it (said, not counted against it: quiet is not absent).
- **Dynamics ↔ Blocks**: every stock where work waits has a goal and a loop that closes; every flow work moves is
  moved by a block (its ``out:``, or the runs of a block that takes the items there), by ergostat's leases (an item
  given back), or is an observed rate from outside (a collector's, a sensor's); the loops share the chain's stocks
  (``check``'s missing-feedback, no-visible-effect and loops-not-connected findings, linked here, not said again).
- **Blocks ↔ Process**: every move is attributed to the block whose run caused it (its ``source``, or ``causedby`` its
  run), to a collector (a sensor recording what it saw), to ergostat's own leases, or to the outside world; a block
  seen moving items it does not declare (no ``takes:`` there, no ``out:`` flow carrying it), a move from outside
  where the model says a block moves it, and a block declared to move work that was there and never seen moving it.

It compares only where there is record to compare against: a kind with fewer than ``MIN_MOVES`` moves (or
``MIN_ITEMS`` items) in the window says how many more it needs. Each kind's score is its agreements over its
comparisons. Bounded: the window is read once by ``process.Window`` (its caps), the moves from the item index."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

PAIRS = {"process-dynamics": "Process ↔ Dynamics", "dynamics-blocks": "Dynamics ↔ Blocks",
         "blocks-process": "Blocks ↔ Process"}
WINDOW = 86400.0               # the record compared, by default: the last day
MIN_MOVES = 10                 # a kind's moves in the window before the record is compared with the model
MIN_ITEMS = 3                  # and its items
CAUSE_HOPS = 4                 # a move's cause followed up through events about no item (a block's run) this far
LEASE_STATES = ("leased", "dead")
ACTED = ("agent.started", "agent.ran", "person.asked", "valve.opened")   # a block's own events: it ran, or was asked


@dataclass
class Finding:
    pair: str
    code: str
    kind: str
    about: str
    message: str
    where: object = None
    fix: str = ""
    links: list[str] = field(default_factory=list)   # findings check already reports about the same thing (their ids)
    level: str = "mismatch"                          # mismatch (counted against) or note (said, not counted)

    def as_dict(self) -> dict:
        return {"pair": self.pair, "code": self.code, "kind": self.kind, "about": self.about, "id": f"{self.code}@{self.about}",
                "message": self.message, "fix": self.fix, "links": self.links, "level": self.level,
                "file": str(self.where.file) if self.where else None, "line": self.where.line if self.where else None}


@dataclass
class Score:
    agree: dict = field(default_factory=lambda: Counter())
    compared: dict = field(default_factory=lambda: Counter())

    def add(self, pair: str, ok: bool) -> None:
        self.compared[pair] += 1
        self.agree[pair] += int(ok)

    def total(self) -> tuple[int, int]:
        return sum(self.agree.values()), sum(self.compared.values())


# ---- who moved an item

def _who(spec, w, eid: str | None, looked: list[int]) -> tuple[str, str]:
    """What caused the event that moved an item: ``("block", NAME)`` (its run: the event's ``source``, or ``causedby``
    the run, up through events about no item), ``("collector", flow.SENSOR)`` (a sensor recording what it saw),
    ``("ergostat", "")`` (ergostat's own: a lease handed back, expired, a dead letter), or ``("outside", SOURCE)``."""
    e = w.by_id.get(eid) if eid else None
    if e is None and eid and looked[0] < 2000:
        looked[0] += 1
        e = w.events.get(eid)
    if e is None:
        return "outside", "?"
    src = e.get("source") or ""
    if src in spec.blocks:
        return "block", src
    cid = e.get("causedby")
    for _ in range(CAUSE_HOPS):
        if not cid:
            break
        c = w.by_id.get(cid)
        if c is None and looked[0] < 2000:
            looked[0] += 1
            c = w.events.get(cid)
        if c is None:
            break
        if c["type"].startswith("agent.") and c.get("item") in spec.blocks:
            return "block", c["item"]
        if (c.get("source") or "") in spec.blocks:
            return "block", c["source"]
        if c.get("item") and "/" in c["item"]:
            break                                   # caused by an event on an item: not a run
        cid = c.get("causedby")
    if e["type"].startswith("ergostat.") or src == "ergostat":
        return "ergostat", ""
    of, _, sensor = src.partition(".")
    if sensor and (of in spec.flows or of in spec.stocks):
        return "collector", src
    return "outside", src or "?"


def _said(who: tuple[str, str]) -> str:
    kind, name = who
    return {"block": f"block {name}", "collector": f"the collector {name}", "ergostat": "ergostat's leases",
            "outside": f"outside ergostat ({name})"}[kind]


# ---- the chain, as flows

class Chain:
    """A kind's chain (``chains.Chain``) and the flows of the model about it: which carry a move, which are its."""

    def __init__(self, spec, c, kind_def):
        from .spec import chains
        self.spec, self.c, self.k = spec, c, c.kind
        self.kd = kind_def
        self.stocks = set(c.stock_of.values()) | c.stages
        self.flows = [f for f in spec.flows.values() if f.source in self.stocks or f.target in self.stocks]
        self.counts = chains._counts

    def path(self, a: str | None, b: str | None) -> set[str]:
        """The flows on a path from stock ``a`` to stock ``b`` through the stocks of items being worked (``None``: outside)."""
        st = self.c.stages
        flows = self.spec.flows.values()
        if a is None:
            return {f.name for f in flows if f.source is None and f.target == b} | \
                {f.name for f in flows if f.source is None and f.target in st and b in self._out(f.target)}
        fw, todo = {a}, [a]
        while todo:
            x = todo.pop()
            for f in flows:
                if f.source == x and f.target in st and f.target not in fw:
                    fw.add(f.target)
                    todo.append(f.target)
        return {f.name for f in flows if f.source in fw and (f.target == b or (f.target in st and b in self._out(f.target)))}

    def _out(self, stage: str) -> set:
        return {f.target for f in self.spec.flows.values() if f.source == stage}

    def carrying(self, p: str | None, s: str) -> set[str]:
        """The flows that carry items of the kind from state ``p`` to ``s`` (``None``: arriving): a path of flows between
        their stocks, a flow from ``p``'s stock to outside when ``s`` has none, and any flow whose own sensor counts
        exactly these (entering ``s``, its lease taken at ``p`` when it says so; or leaving ``p``)."""
        so = self.c.stock_of
        a, b = (so.get(p) if p else None), so.get(s)
        out: set[str] = set()
        if b is not None and (p is None or a is not None) and a != b:
            out |= self.path(a, b)
        if b is None and a is not None:
            out |= self.path(a, None)
        st = self.c.stages
        for f in self.flows:
            if not ((f.source is None or f.source == a or f.source in st) and (f.target is None or f.target == b or f.target in st)):
                continue                              # a flow between other stocks: its sensor counts others' moves too
            for s_ in f.sensors.values():
                q = s_.items
                if not q or q.get("kind") != self.k:
                    continue
                back = (q.get("where") or {}).get("lease.back")
                if q.get("entering") == s and (back is None or back == p) and \
                        (len(q.get("where") or {}) == (1 if back else 0)):
                    out.add(f.name)
                if p and q.get("leaving") == p and not (q.get("where") or {}):
                    out.add(f.name)
        return out

    def mover(self, flow: str) -> tuple[str, str] | None:
        """What moves a flow, as the model says: ``("block", NAME)`` (its ``out:``; or a block taking the items at the
        flow's source state to its target's), ``("lease", "")`` (out of the stock of items being worked and not by a
        block: a lease handed back or expired, ergostat's own), ``("outside", how)`` (an observed rate from outside:
        a collector's or a sensor's), or None."""
        spec, f = self.spec, self.spec.flows[flow]
        b = spec.actuator_of(flow)
        if b is not None:
            return "block", b.name
        so = self.c.stock_of
        src = [s for s, x in so.items() if x == f.source]
        dst = [s for s, x in so.items() if x == f.target]
        for bl in spec.blocks.values():
            t = bl.takes
            if t and t.kind == self.k and any(s in t.at for s in src) and (not t.to or any(s in t.to for s in dst)):
                return "block", bl.name
        if f.source in self.c.stages:
            return "lease", ""
        if any(s.run or s.query for s in f.sensors.values()) and (f.source is None or f.target is None):
            return "outside", "a collector"
        if f.sensors:
            return "outside", "observed by its sensor"
        if f.rate is not None or f.equation is not None:
            return "outside", "a rate the model states"
        return None


def _fix_flow(spec, chains, k: str, a: str | None, b: str | None, state: str, why: str) -> str:
    taken = set(spec.flows)
    name = f"{a or b}-{'arriving' if a is None else 'done' if b is None else 'to-' + b}"
    i = 2
    base = name
    while name in taken:
        name, i = f"{base}-{i}", i + 1
    return chains.Fix("add", flow=name, source=a, target=b, kind=k, entering=state, description=why).said()


# ---- the comparison

def compare(spec, events, since: float | None = None, until: float | None = None, problems=None, quiet=None) -> dict:
    """The three views of ``spec`` held against each other over the record in ``events`` from ``since`` to ``until``
    (the last ``WINDOW``). ``problems``: what ``check`` found (to link to, not say again); ``quiet``: the parts the
    record has not exercised (``numbers/exercised.py``), when known."""
    from . import process as pm
    from .spec import chains
    from .spec import findings as fd
    until = time.time() if until is None else until
    since = until - WINDOW if since is None else since
    if problems is None:
        try:
            problems = fd.find(spec, extremes=False)
        except Exception:
            problems = []
    have = {f"{p.code}@{p.about}" for p in problems if getattr(p, "code", "")}
    quiet = quiet or {}
    found: list[Finding] = []
    scores: dict[str, Score] = {}
    kinds_info: dict[str, dict] = {}
    movers: dict[str, dict] = {}
    built = {k: c for k, c in chains._kinds(spec).items()}
    state_kinds = [k for k in pm.kinds_of(spec, None) if spec.items[k].states]
    state_kinds += [k for k in built if k not in state_kinds]          # ergostat's own kinds, where the model chains them
    w = None
    if events is not None and state_kinds:
        try:
            w = pm.Window(events, spec, state_kinds, since, until, "states")
        except Exception:                                 # a record that cannot be read now says nothing either way
            w = None
    looked = [0]
    active = {e["item"] for e in (w.evs if w is not None else ()) if e.get("item") in spec.blocks and e["type"] in ACTED} | \
        {e["source"] for e in (w.evs if w is not None else ()) if e.get("source") in spec.blocks}
    # each kind's moves in the window: (from, to) → how many, and who made them
    moves: dict[str, Counter] = {k: Counter() for k in state_kinds}
    by: dict[str, dict[tuple, Counter]] = {k: {} for k in state_kinds}
    items: dict[str, set] = {k: set() for k in state_kinds}
    if w is not None:
        for id, steps in w.steps.items():
            k = w.kind_of.get(id)
            if k not in moves:
                continue
            pairs = []
            for (_t0, a, _, _), (_t1, b, eid, _) in w._pairs(id, steps):
                if b == pm.END:
                    continue
                p = None if a == pm.START else a
                if pairs and pairs[-1][0] is None and pairs[-1][1] == p and pairs[-1][2] == eid:
                    pairs[-1] = (None, b, eid)        # its first event moved it at once: it arrived in that state
                    continue
                pairs.append((p, b, eid))
            for p, b, eid in pairs:
                moves[k][(p, b)] += 1
                items[k].add(id)
                by[k].setdefault((p, b), Counter())[_who(spec, w, eid, looked)] += 1
    window_moves = {k: Counter({m: n for m, n in moves[k].items() if not set(m) & set(LEASE_STATES)}) for k in moves}
    chain_found = chains.analyse(spec, {k: v for k, v in window_moves.items()}) if built else []
    have |= {f"{x.code}@{x.about}" for x in chain_found}      # what check says of these moves, from the record

    def link(code: str, about: str) -> list[str]:
        i = f"{code}@{about}"
        return [i] if i in have else []

    for k in sorted(set(built) | set(state_kinds), key=lambda x: list(spec.items).index(x) if x in spec.items else 99):
        sc = scores.setdefault(k, Score())
        n_moves = sum(window_moves.get(k, Counter()).values())          # arrivals too: each is a move from outside
        n_items = len(items.get(k, ()))
        need = None
        if events is None or w is None:
            need = "a record (none yet)"
        elif n_moves < MIN_MOVES or n_items < MIN_ITEMS:
            parts = []
            if n_moves < MIN_MOVES:
                parts.append(f"{MIN_MOVES - n_moves} more move{'s' if MIN_MOVES - n_moves != 1 else ''}")
            if n_items < MIN_ITEMS:
                parts.append(f"{MIN_ITEMS - n_items} more item{'s' if MIN_ITEMS - n_items != 1 else ''}")
            need = f"{' and '.join(parts)} of {k} in the window (has {n_moves} move{'s' if n_moves != 1 else ''} of " \
                   f"{n_items} item{'s' if n_items != 1 else ''}; needs {MIN_MOVES} moves of {MIN_ITEMS} items)"
        kinds_info[k] = {"moves": n_moves, "items": n_items, "needs": need, "chained": k in built,
                         "moved": {f"{a or 'arrived'} -> {b}": n for (a, b), n in window_moves.get(k, Counter()).most_common(24)}}
        if k not in built:
            if need is None and n_moves:
                stocked = sorted({s for st in spec.stocks.values() for x in st.sensors.values()
                                  if x.items and x.items.get("kind") == k for s in (x.items.get("state") or [])})
                found.append(Finding("process-dynamics", "kind-not-chained", k, f"items.{k}",
                                     f"items {k}: {n_moves} moves of {n_items} items in the window, but "
                                     + (f"only {', '.join(stocked)} has a stock" if stocked else "no stock counts its states")
                                     + ": the Dynamics view does not show how its items move. If they are work that waits "
                                     "and moves, give each state where they wait a stock (items: " + k + ", state: S) and "
                                     "chain them with flows; if they are a status, not work, nothing is wrong",
                                     spec.items[k].where, level="note"))
            continue
        ch = Chain(spec, built[k], spec.items[k])
        so = ch.c.stock_of
        rank = {s: i for i, s in enumerate(ch.c.order)}
        mine = [x for x in chain_found if any(f.kind == k for f in x.fixes) or x.about in
                {f"stock.{s}" for s in ch.stocks} | {f"flow.{f.name}" for f in ch.flows}]
        # ---- Dynamics ↔ Blocks (the model alone)
        last = ch.c.order[-1] if ch.c.order else None
        declared = (getattr(getattr(spec, "messages", None), "done", None) or {}).get(k)
        finished = set(declared or ()) | ({last} if last else set())    # as the model says: never what a short record does
        moved_by: dict[str, tuple] = {}
        for f in ch.flows:
            m = ch.mover(f.name)
            moved_by[f.name] = m
            sc.add("dynamics-blocks", m is not None)
            if m is not None:
                continue
            inner = f.source in ch.stocks and f.target in ch.stocks
            found.append(Finding("dynamics-blocks", "flow-moved-by-nothing", k, f"flow.{f.name}",
                                 f"flow {f.name}: moves items of {k} "
                                 + (f"from {f.source} to {f.target}" if inner else
                                    f"{'out of ' + f.source if f.source else 'into ' + str(f.target)}")
                                 + ", but no block moves it and nothing measures it: the model does not say what moves "
                                 "this work, nor how much", f.where,
                                 fix=f"the block that moves it (out: flow.{f.name}, or one taking the items there: takes: "
                                     f"{{kind: {k}, at: ...}}); if it is moved outside ergostat, an external block (type: "
                                     f"external, out: flow.{f.name}) or a sensor that observes it (items: {k}, entering: ...)"))
        movers[k] = {f: ("block " + m[1] + (" (external)" if spec.blocks[m[1]].type == "external" else "")
                         if m[0] == "block" else "ergostat's leases" if m[0] == "lease" else f"outside ({m[1]})")
                     for f, m in moved_by.items() if m}
        said_stocks: set[str] = set()
        for state, st in sorted(so.items(), key=lambda x: rank.get(x[0], 99)):
            if st in said_stocks or state in finished or spec.stocks[st].cumulative:
                continue
            said_stocks.add(st)
            ours = sorted({m[1] for f in spec.flows.values() if f.source == st and (m := moved_by.get(f.name) or ch.mover(f.name))
                           and m[0] == "block" and spec.blocks[m[1]].type != "external"} |
                          {b.name for b in spec.blocks.values() if b.takes and b.takes.kind == k and state in b.takes.at
                           and b.type != "external"})
            if not ours:
                continue                              # items wait on the world here: every flow out is from outside
            if all(spec.blocks[b].type == "judge" for b in ours):
                sc.add("dynamics-blocks", True)       # the judge works them off on its own clock (SPEC §12e)
                continue
            filling = {m[1] for f in spec.flows.values() if f.target == st and (m := moved_by.get(f.name) or ch.mover(f.name))
                       and m[0] == "block"}
            emptying = {m[1] for f in spec.flows.values() if f.source == st and (m := moved_by.get(f.name) or ch.mover(f.name))
                        and m[0] == "block"}
            if emptying and emptying <= filling:
                continue                              # a run's own work in progress: what it took in, it moves on
            goals = _goals_on(spec, st)
            if not goals and any(r.kind == "stock" and r.name == st for b in ours for r in spec.blocks[b].inputs.values()):
                sc.add("dynamics-blocks", True)       # a loop with no setpoint: the block reads the stock it works off
                continue
            if not goals:
                sc.add("dynamics-blocks", False)
                found.append(Finding("dynamics-blocks", "waiting-without-goal", k, f"stock.{st}",
                                     f"stock {st}: items of {k} wait here (in {state}) for block{'s' if len(ours) > 1 else ''} "
                                     f"{', '.join(ours)} to move them on, but no goal says how many may wait, so no loop works it off: "
                                     f"the Blocks view has no loop for this step", spec.stocks[st].where,
                                     fix=f"goals: {{{st}-clear: {{stock: {st}, hold: \"<= 0\"}}}}, served by the block that "
                                         f"moves them on (goal: {st}-clear on it)"))
                continue
            closes = [g for g in goals if spec.loop(g.name).closes]
            sc.add("dynamics-blocks", bool(closes))
            if not closes:
                g = goals[0]
                found.append(Finding("dynamics-blocks", "goal-without-loop", k, f"goal.{g.name}",
                                     f"stock {st}: items of {k} wait here (in {state}) and goal {g.name} holds it, but no "
                                     f"loop closes: nothing it commands moves a flow of {st}", g.where,
                                     fix=f"goal: {g.name} on the block that moves them on ({ours[0]})",
                                     links=link("missing-feedback", f"goal.{g.name}")))
        lnc = [x for x in mine if x.code == "loops-not-connected"]
        goals_here = [g for g in spec.goals.values() if g.of.kind == "stock" and g.of.name in ch.stocks]
        if len(goals_here) >= 2:
            sc.add("dynamics-blocks", not lnc)
        for x in lnc:
            found.append(Finding("dynamics-blocks", "loops-not-connected", k, x.about, x.message, x.where,
                                 fix="; ".join(f.said() for f in x.fixes), links=link(x.code, x.about)))
        for bl in spec.blocks.values():
            if (bl.takes and bl.takes.kind == k) and not bl.outputs:
                found.append(Finding("dynamics-blocks", "block-moves-no-flow", k, f"block.{bl.name}",
                                     f"block {bl.name}: takes items of {k} at {', '.join(bl.takes.at)}, but has no out: "
                                     f"the Dynamics view cannot show what its runs move", bl.where,
                                     fix=f"out: the flow that carries the items it moves (from {so.get(bl.takes.at[0], '?')})",
                                     links=link("no-visible-effect", f"block.{bl.name}")))
                sc.add("dynamics-blocks", False)
        if need is not None:
            continue
        # ---- Process ↔ Dynamics (the record's moves against the chain)
        seen_flows: set[str] = set()
        wm = window_moves[k]
        for p, s in moves[k]:
            seen_flows |= ch.carrying(p, s)
        for (p, s), n in sorted(wm.items(), key=lambda m: (rank.get(m[0][0], -1), rank.get(m[0][1], 99))):
            ts = "time" if n == 1 else "times"
            a, b = (so.get(p) if p else None), so.get(s)
            if p is None:
                if b is None:
                    continue
                ok = any(f.source is None and f.target == b for f in spec.flows.values()) or bool(ch.carrying(None, s))
                sc.add("process-dynamics", ok)
                if not ok:
                    cf = next((x for x in mine if (None, s) in x.moves), None)
                    found.append(Finding("process-dynamics", "arrival-not-modelled", k, f"stock.{b}",
                                         f"stock {b}: {n} item{'s' if n != 1 else ''} of {k} arrived in {s} in the window "
                                         f"(their first event), but no flow brings them into {b} from outside: the chain "
                                         f"does not start where the record does", spec.stocks[b].where,
                                         fix=cf.fixes[0].said() if cf else _fix_flow(spec, chains, k, None, b, s,
                                                                                    f"items of {k} arriving in {s}"),
                                         links=link(cf.code, cf.about) if cf else []))
                continue
            if b is None and a is not None and s in finished:
                ok = bool(ch.path(a, None)) or bool(ch.carrying(p, s))
                sc.add("process-dynamics", ok)
                if not ok:
                    found.append(Finding("process-dynamics", "completion-not-modelled", k, f"stock.{a}",
                                         f"stock {a}: {n} item{'s' if n != 1 else ''} of {k} finished ({p} to {s}) in the "
                                         f"window, but no flow takes them out of {a}: the chain does not end where the "
                                         f"record does", spec.stocks[a].where,
                                         fix=_fix_flow(spec, chains, k, a, None, s, f"items of {k} finished ({s})")))
                continue
            if a is None or b is None or a == b:
                continue
            cf = next((x for x in mine if (p, s) in x.moves), None)
            sc.add("process-dynamics", cf is None)
            if cf is None:
                continue
            back = rank.get(s, 99) < rank.get(p, -1)
            fwd = ch.path(a, b) or _reach(spec, a, b, ch.stocks)
            rev = _reach(spec, b, a, ch.stocks)
            if back:
                code, words = "rework-without-flow", (f"rework: {n} {ts} in the window items of {k} went back from {p} to "
                                                      f"{s}, but no flow carries them back from {a} to {b}")
            elif fwd:
                via = _via(spec, a, b, ch.stocks)
                code, words = "chain-skipped", (f"{n} {ts} in the window items of {k} went from {p} straight to {s}, but "
                                                f"the chain carries them from {a} to {b} only through "
                                                f"{', '.join(via) or 'other stocks'}: the record skips "
                                                f"{'that step' if len(via) == 1 else 'those steps'}")
            elif rev:
                code, words = "order-contradicted", (f"{n} {ts} in the window items of {k} went from {p} to {s}, but the "
                                                     f"chain's flows run the other way, from {b} to {a}: the model's "
                                                     f"order contradicts the record's")
            else:
                code, words = "move-without-flow", (f"{n} {ts} in the window items of {k} went from {p} to {s}, and no "
                                                    f"flow carries them from {a} to {b}")
            found.append(Finding("process-dynamics", code, k, cf.about, words + f" ({cf.code}: check says so too)",
                                 cf.where, fix="; ".join(x.said() for x in cf.fixes if x.source == a or x.op == "retarget"
                                                         or x.target == b) or "; ".join(x.said() for x in cf.fixes),
                                 links=link(cf.code, cf.about)))
        unseen, unexercised = [], []
        for f in ch.flows:
            if f.name in seen_flows:
                sc.add("process-dynamics", True)
            elif f"flow.{f.name}" in quiet:
                unexercised.append(f.name)
            else:
                unseen.append(f.name)
        if unseen or unexercised:
            names = unseen + unexercised
            found.append(Finding("process-dynamics", "flow-not-seen", k, f"items.{k}",
                                 f"items {k}: no item moved along {'this flow' if len(names) == 1 else 'these flows'} in the "
                                 f"window: {', '.join(names)}"
                                 + (f" ({', '.join(unexercised)}: not exercised by the record)" if unexercised else "")
                                 + ". Quiet is not absent: a path taken rarely (a retry, a dead letter, a step later than "
                                 "the window reaches) may not have been taken yet; if one never is, the model has a path "
                                 "the work does not take", spec.items[k].where,
                                 links=[x for f in unexercised for x in link("not-exercised", f"flow.{f}")], level="note"))
            kinds_info[k]["unseen"] = names
        # ---- Blocks ↔ Process (who moved them, against who the model says does)
        acted: dict[str, Counter] = {}
        undeclared: dict[str, list] = {}
        unblocked: dict[str, list] = {}
        for (p, s), who in sorted(by[k].items(), key=lambda m: (rank.get(m[0][0], -1), rank.get(m[0][1], 99))):
            if p in LEASE_STATES or s in LEASE_STATES:
                continue
            carriers = ch.carrying(p, s)
            for (wk, wn), n in who.items():
                ts = "time" if n == 1 else "times"
                if wk == "block":
                    acted.setdefault(wn, Counter())[(p, s)] += n
                    bl = spec.blocks[wn]
                    t = bl.takes
                    declared = (t is not None and t.kind == k and (p is None or p in t.at) and (not t.to or s in t.to)) or \
                        any(r.kind == "flow" and (r.name in carriers or _measures_entering(spec, r.name, k, s))
                            for r in bl.targets())
                    sc.add("blocks-process", declared)
                    if not declared:
                        what = (f"takes items of {k} at {', '.join(t.at)}" + (f" to {', '.join(t.to)}" if t.to else "")
                                if t is not None and t.kind == k else
                                f"moves {', '.join(str(r) for r in bl.targets() if r.kind == 'flow') or 'no flow'}")
                        undeclared.setdefault(wn, []).append(
                            (f"{'into ' + s if p is None else 'from ' + p + ' to ' + s} {n} {ts}", what,
                             _undeclared_fix(k, p, s, t, carriers)))
                    continue
                if wk == "ergostat":
                    continue
                if p is None and not carriers:
                    continue                          # an arrival with no flow: Process ↔ Dynamics says it
                if not carriers:
                    continue                          # a move no flow carries: Process ↔ Dynamics says it
                ms = {moved_by.get(f) or ch.mover(f) for f in carriers}
                blocks = sorted({m[1] for m in ms if m and m[0] == "block" and spec.blocks[m[1]].type != "external"})
                ok = not blocks or any(m and m[0] in ("outside", "lease") for m in ms)
                if not ok and wk in ("collector", "outside") and any(b in active or spec.blocks[b].type == "person"
                                                                      for b in blocks):
                    ok = True                         # the block acted in the world (a person may, unasked), and it was seen
                    for b in blocks:
                        if b in active or spec.blocks[b].type == "person":
                            acted.setdefault(b, Counter())[(p, s)] += n
                sc.add("blocks-process", ok)
                if not ok:
                    f0 = sorted(carriers)[0]
                    unblocked.setdefault(f0, []).append(
                        (f"{'into ' + s if p is None else 'from ' + p + ' to ' + s} {n} {ts} by {_said((wk, wn))}", blocks,
                         len(carriers)))
        for wn, xs in undeclared.items():
            bl = spec.blocks[wn]
            found.append(Finding("blocks-process", "acts-undeclared", k, f"block.{wn}",
                                 f"block {wn}: its runs moved items of {k} {', and '.join(x[0] for x in xs)} in the window, "
                                 f"but it declares that it {xs[0][1]}: the Blocks view does not show this work", bl.where,
                                 fix="; ".join(dict.fromkeys(x[2] for x in xs))))
        for f0, xs in unblocked.items():
            blocks = sorted({b for x in xs for b in x[1]})
            found.append(Finding("blocks-process", "moved-without-its-block", k, f"flow.{f0}",
                                 f"flow {f0}: items of {k} moved {', and '.join(x[0] for x in xs)} in the window, with no "
                                 f"block's run behind them, but the model says block {', '.join(blocks)} moves "
                                 f"{'it' if xs[0][2] == 1 else 'them'}", spec.flows[f0].where,
                                 fix=(f"if {blocks[0]} does this work, record its events from its runs (an event line, or "
                                      f"$ERGOSTAT_CMD event --add during the run); if it is done outside ergostat, say so: "
                                      f"an external block (type: external, out: flow.{f0}) in place of {blocks[0]}'s out:")))
        idle: list[str] = []
        for bl in spec.blocks.values():
            t = bl.takes if bl.takes and bl.takes.kind == k else None
            outs = [r.name for r in bl.targets() if r.kind == "flow" and r.name in {f.name for f in ch.flows}]
            if t is None and not outs:
                continue
            if bl.type == "external":
                continue
            if acted.get(bl.name):
                sc.add("blocks-process", True)
                continue
            work = sum(n for (p, s), n in wm.items() if t and s in t.at) if t else 0
            moved = [f for f in outs if f in seen_flows]
            if not work and not moved:
                idle.append(bl.name)
                continue
            others = Counter()
            for (p, s), who in by[k].items():
                if (t and p in t.at) or ch.carrying(p, s) & set(outs):
                    for x, n in who.items():
                        if x[0] != "ergostat":
                            others[_said(x)] += n
            there = (f"{work} arrived at {', '.join(t.at)}" if t and work else ", ".join(moved) + " moved")
            what = f"takes them at {', '.join(t.at)}" if t else f"out: {', '.join(outs)}"
            if not others:
                found.append(Finding("blocks-process", "not-seen-acting", k, f"block.{bl.name}",
                                     f"block {bl.name}: declared to move items of {k} ({what}); there was work for it in "
                                     f"the window ({there}) and none was moved on yet, by it or anything else: it may be "
                                     f"working on them, held, or waiting for an approval", bl.where, level="note"))
                continue
            sc.add("blocks-process", False)
            did = ", ".join(f"{w_} {n} time{'s' if n != 1 else ''}" for w_, n in others.most_common(3))
            found.append(Finding("blocks-process", "declared-not-seen-acting", k, f"block.{bl.name}",
                                 f"block {bl.name}: declared to move items of {k} ({what}), and there was work for it in the "
                                 f"window ({there}), but no run of it moved any: they were moved by {did}", bl.where,
                                 fix="if it runs, its events are not recorded as its own (an event line from its run, or "
                                     "$ERGOSTAT_CMD event --add during the run, so causedby names it); if something else "
                                     "does the work, the model should say so (that block's out:, or an external block)"))
        if idle:
            found.append(Finding("blocks-process", "not-seen-acting", k, f"items.{k}",
                                 f"items {k}: no work reached {'this block' if len(idle) == 1 else 'these blocks'} in the "
                                 f"window (no item came to the states they take, nor moved along their flows), so none "
                                 f"was seen acting: {', '.join(idle)}", spec.items[k].where, level="note"))
            kinds_info[k]["idle"] = idle
    out_kinds = {}
    for k, info in kinds_info.items():
        a, c = scores[k].total()
        out_kinds[k] = {**info, "agree": a, "compared": c, "movers": movers.get(k, {}),
                        "pairs": {p: {"agree": scores[k].agree[p], "compared": scores[k].compared[p]} for p in PAIRS}}
    return {"since": since, "until": until, "kinds": out_kinds, "findings": [f.as_dict() for f in found],
            "pairs": PAIRS, "most": {"moves": MIN_MOVES, "items": MIN_ITEMS},
            "capped": dict(w.capped) if w is not None else {}}


def _goals_on(spec, stock: str) -> list:
    """The goals on a stock, or on an auxiliary it drives (directly, or through other auxiliaries)."""
    drives, todo = {f"stock.{stock}"}, True
    while todo:
        todo = False
        for a in spec.auxiliaries.values():
            if f"auxiliary.{a.name}" not in drives and any(str(r) in drives for r in a.driven_by):
                drives.add(f"auxiliary.{a.name}")
                todo = True
    return [g for g in spec.goals.values() if str(g.of) in drives]


def _measures_entering(spec, flow: str, kind: str, state: str) -> bool:
    """A flow measured as the items of a kind entering a state: what a block that names it in ``out:`` says it moves."""
    f = spec.flows.get(flow)
    return f is not None and any((x.items or {}).get("kind") == kind and (x.items or {}).get("entering") == state
                                 for x in f.sensors.values())


def _undeclared_fix(k: str, p: str | None, s: str, t, carriers: set[str]) -> str:
    """What a block seen moving items from ``p`` to ``s`` should declare."""
    out = f"; or out: flow.{sorted(carriers)[0]}, the flow that carries it" if carriers else \
        " (and a flow that carries it: Process ↔ Dynamics says which)"
    if p is None:
        return f"out: flow.{sorted(carriers)[0]}" if carriers else f"a flow from outside into {s}'s stock, as its out:"
    if t is None or t.kind != k:
        return f"takes: {{kind: {k}, at: {p}, to: [{s}]}}{out}"
    if p in t.at:
        return f"add {s} to its takes: to:{out}"
    return f"add {p} to its takes: at: (and {s} to its to:){out}"


def _ends(f) -> str:
    return f"from {f.source or 'outside'} to {f.target or 'outside'}"


def _reach(spec, a: str, b: str, through: set[str]) -> bool:
    todo, been = [a], {a}
    while todo:
        x = todo.pop()
        for f in spec.flows.values():
            if f.source == x:
                if f.target == b:
                    return True
                if f.target in through and f.target not in been:
                    been.add(f.target)
                    todo.append(f.target)
    return False


def _via(spec, a: str, b: str, through: set[str]) -> list[str]:
    """The stocks on the shortest path of flows from ``a`` to ``b`` (through these stocks), between them."""
    prev, todo = {a: None}, [a]
    while todo:
        x = todo.pop(0)
        for f in spec.flows.values():
            if f.source == x and f.target and f.target not in prev and (f.target == b or f.target in through):
                prev[f.target] = x
                if f.target == b:
                    out, y = [], x
                    while y is not None and y != a:
                        out.append(y)
                        y = prev[y]
                    return out[::-1]
                todo.append(f.target)
    return []


# ---- where the record is

def record_of(spec):
    """The project's record, opened read-only from its state directory (as ``chains.recorded`` finds it); None when
    there is none yet."""
    from .spec.chains import record_dir
    d = record_dir(spec)
    if d is None:
        return None
    from .storage import Storage, open_events
    return open_events(getattr(spec, "storage", None) or Storage(), d)


def of_spec(spec, problems=None, since: float | None = None) -> dict:
    """``compare`` over the project's own record (``check``, which reads the model alone)."""
    try:
        events = record_of(spec)
    except Exception:
        events = None
    until = time.time()
    return compare(spec, events, until - (since or WINDOW), until, problems)


def of_project(p, spec, window: float | None = None, at: float | None = None) -> dict:
    """``compare`` over a project's record, with check's findings and what the record has not exercised."""
    until = time.time() if at is None else at
    quiet = {}
    try:
        from .numbers import exercised as ex
        _, quiet = ex.of_project(p, spec, until)
    except Exception:
        quiet = {}
    problems = [x for x in (getattr(p.model, "_problems", None) or []) if x.level != "error"]   # as it compiled: no extremes run
    return compare(spec, p.events, until - (window or WINDOW), until, problems, quiet)


# ---- said

def score_line(k: str, x: dict) -> str:
    if x.get("needs") and not x["compared"]:
        return f"{k}: needs {x['needs']}"
    a, c = x["agree"], x["compared"]
    if not c:
        return f"{k}: nothing to compare" + ("" if x.get("chained") else " (no chain of state stocks models it)")
    tail = f"; the record not compared yet: needs {x['needs']}" if x.get("needs") else ""
    return f"{k}: {a} of {c} agree ({round(100 * a / c) if c else 100}%){tail}"


def lines(got: dict) -> list[tuple[str, str]]:
    """The section as (style, line) pairs: each kind's score, then the findings grouped by pair."""
    out: list[tuple[str, str]] = []
    for k, x in got["kinds"].items():
        out.append(("ok" if x["agree"] == x["compared"] and not x.get("needs") else "warn" if x["compared"] else "dim",
                    score_line(k, x)))
    for pair, title in PAIRS.items():
        mine = [f for f in got["findings"] if f["pair"] == pair]
        if not mine:
            continue
        out.append(("head", title))
        for f in mine:
            where = f"{_short(f['file'])}:{f['line']}: " if f["file"] else ""
            out.append(("warn" if f["level"] == "mismatch" else "dim", f"{f['code']}  {where}{f['message']}"))
            if f["fix"]:
                out.append(("dim", f"    fix: {f['fix']}"))
            if f["links"]:
                out.append(("dim", f"    see: {', '.join(f['links'])}"))
    return out


def _short(path: str) -> str:
    from pathlib import Path
    return Path(path).name
