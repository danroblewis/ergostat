"""What a system contains (SPEC §4a, *What a system contains*): computed from the graph of the model, never declared.

A thing is *defined in* one system: its ``system:``, or its file's ``defaults: system:``; a thing that says neither is
defined at the top level (``TOP``, the default system, the root above the top-level systems). That is only where it
is written. What it *belongs to* is worked out here, and it may belong to many systems:

1. **Defined.** A thing defined in a system is in that system.
2. **Crossing.** Every edge of the model joins some things (a flow its stocks, a sensor its part and the projection it
   counts, ...: ``EDGES`` below). The systems the things are defined in are nodes of the system tree; the edge is in
   every system on the paths from each of them up to their lowest common ancestor (LCA), that ancestor included, and
   so is every thing it joins. An edge inside one system touches that system alone and adds nothing. One between a
   parent's two subsystems is in both and in the parent (a subsystem is a component of its parent: what crosses
   between its parts is the parent's business); one between a subsystem and its parent is in both (and in every
   system between them, when the subsystem is deeper); one between two top-level systems is in both and at the top
   level. What stays inside a subsystem is not in its parent: nothing percolates up but what an edge carries.
3. **Carried.** A few things come with the part they belong to, wherever that part is: a sensor is in every system
   its stock, flow or auxiliary is in, and the projection the sensor counts with it (the items that flow along a
   flow crossing from intake to delivery are in both, as the flow is); an agent is in every system a block it fills
   is in. Never the other way: filling a role never changes the role (NOTES.md: agents fill roles; they are not
   roles), so a block is never brought into the system its agent is defined in.

Nothing is transitive beyond this: a thing in a system because an edge brought it there brings only its sensors
(and what they count) and its agent with it, never what it is joined to. A QA subsystem's own projection stays in
QA until a part counting it is used outside QA; a stock in QA that its parent reads is in the parent, and the flow
that drains it inside QA is not.

A thing in a system it is not defined in is **ancillary** there, and says why (each edge that brought it). Ergostat's
own projections (``ergostat.*``, and any the model did not write) are defined nowhere: such a one is in each system
whose parts use it, ancillary there, and in none otherwise (ergostat adds nothing of its own accord).

Left out: dashboards (scoped to a system by where they are written, not by the graph), events (in no system), a
projection's ``about:`` (names parts item by item, in the record, not in the model), a block's ``on:`` (event types)
and ``takes: faults: healthy:``; a join's children are a relation's (counted as that relation).
"""

from __future__ import annotations

from .ir import Ref, Spec

TOP = ""                        # the top level: the default system, everything defined in no system
OWN = None                      # defined nowhere: ergostat's own projections, until the model uses one

KINDS = (("stock", "stocks"), ("flow", "flows"), ("auxiliary", "auxiliaries"), ("parameter", "parameters"),
         ("goal", "goals"), ("block", "blocks"), ("sensor", "sensors"), ("projection", "projections"),
         ("agent", "agents"))
PLURAL = dict(KINDS)


def scope(spec: Spec) -> dict:
    """Every system's contents: ``{SYSTEM: {"within": PARENT, "systems": [CHILD, ...], "contains": {KINDS: [{"name",
    "status": "defined" | "ancillary", "defined_in", "why": [...]}]}}}``, the top level under ``TOP`` (its
    ``within`` None; a top-level system's ``TOP``). Worked out once per version of the model (kept with its lookups:
    read it, never change it)."""
    kept = spec.lookups().kept
    key = (id(spec.items), len(spec.items), id(spec.agents), len(spec.agents), id(spec.parameters),
           len(spec.parameters), tuple(spec.systems), tuple(sorted(spec.within.items())))
    got = kept.get("scope")
    if got is None or got[0] != key:
        got = kept["scope"] = (key, _Scope(spec).work())
    return got[1]


def where(system: str) -> str:
    return "the top level" if system == TOP else system


class _Scope:
    def __init__(self, spec: Spec):
        self.s = spec
        self.tables = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries,
                       "parameter": spec.parameters, "goal": spec.goals,
                       "block": {n: b for n, b in spec.blocks.items() if not b.implied},   # its goal's: the goal says it
                       "projection": spec.items, "agent": spec.agents,
                       "sensor": {str(x.ref): x for x in spec.sensors()}}
        self.systems = [TOP, *spec.systems]
        self.homes: dict[tuple, str | None] = {}
        for kind, table in self.tables.items():
            for name, x in table.items():
                self.homes[(kind, name)] = self._home(kind, x)
        for h in set(self.homes.values()):          # a system named only by a part's system: (not described)
            if h is not None and h not in self.systems:
                self.systems.append(h)
        self.order = {node: i for i, node in enumerate(self.homes)}
        self.got: dict[str, dict[tuple, list[str]]] = {s: {} for s in self.systems}

    def _home(self, kind: str, x) -> str | None:
        if kind == "sensor":
            return self.home(Ref(x.of.kind, x.of.name))
        if kind == "projection" and not x.system and (x.where is None or x.name.startswith("ergostat.")):
            return OWN
        return getattr(x, "system", None) or TOP

    def home(self, r: Ref | tuple) -> str | None:
        node = (r.kind, r.name) if isinstance(r, Ref) else r
        return self.homes.get(node, OWN)

    def node(self, r: Ref) -> tuple | None:
        """A reference as a node, when it names a thing there is (a block's port, a sensor's: the block, the part)."""
        n = (r.kind, r.name)
        return n if n in self.homes else None

    def said(self, node: tuple) -> str:
        h = self.homes[node]
        return f"{node[0]} {node[1]} ({'ergostat' if h is OWN else where(h)})"

    # ---- the system tree, the top level its root

    def path(self, system: str) -> list[str]:
        """The system and every system it is within, innermost first, ending at the top level."""
        return [*(self.s.chain(system) if system else []), TOP]

    def touched(self, homes) -> list[str]:
        """Every system on the paths from each home up to their lowest common ancestor, that ancestor included."""
        homes = [h for h in dict.fromkeys(homes) if h is not OWN]
        if not homes:
            return []
        paths = [self.path(h) for h in homes]
        lca = next(x for x in paths[0] if all(x in p for p in paths[1:]))
        return list(dict.fromkeys(x for p in paths for x in p[:p.index(lca) + 1]))

    def put(self, system: str, node: tuple, why: str) -> None:
        said = self.got.setdefault(system, {}).setdefault(node, [])
        if why not in said:
            said.append(why)

    def edge(self, nodes, why: str) -> None:
        nodes = [n for n in dict.fromkeys(nodes) if n is not None]
        if len(nodes) < 2:
            return
        for system in self.touched(self.homes[n] for n in nodes):
            for n in nodes:
                if self.homes[n] != system:
                    self.put(system, n, why)

    # ---- the edges

    def edges(self) -> None:
        s = self.s
        for f in s.flows.values():
            me = ("flow", f.name)
            ends = [self.node(Ref("stock", x)) if x else None for x in (f.source, f.target)]
            text = (f"{self.said(me)} runs from " + (self.said(ends[0]) if ends[0] else "outside") + " to "
                    + (self.said(ends[1]) if ends[1] else "outside"))
            self.edge([me, *ends], text)
        for kind, table in (("flow", s.flows), ("auxiliary", s.auxiliaries)):
            for x in table.values():
                me = (kind, x.name)
                for r in x.driven_by:
                    if (n := self.node(r)):
                        self.edge([me, n], f"{self.said(me)} is driven by {self.said(n)}")
                if x.equation is not None:
                    names = [n for r in x.equation.refs if (n := self.node(Ref.parse(r) or Ref("", "")))]
                    names += [("parameter", p) for p in x.equation.parameters if ("parameter", p) in self.homes]
                    for n in names:
                        self.edge([me, n], f"{self.said(me)}'s equation names {self.said(n)}")
        for x in s.sensors():
            part = self.node(Ref(x.of.kind, x.of.name))
            me = f"sensor {x.ref}"
            if x.items and ("projection", k := x.items.get("kind")) in self.homes:
                self.edge([part, ("projection", k)], f"{me} on {self.said(part)} counts {self.said(('projection', k))}")
            if x.changes and (st := self.node(Ref("stock", x.changes.get("stock") or ""))):
                self.edge([part, st], f"{me} on {self.said(part)} reads the readings of {self.said(st)}")
        for g in s.goals.values():
            me = ("goal", g.name)
            if (of := self.node(g.of)):
                self.edge([me, of], f"{self.said(me)} holds {self.said(of)}")
            lp = s.loop(g.name)
            parts = [("block", b) for b in (*lp.controllers, *lp.actuators)] + [("flow", v) for v in lp.valves]
            parts += [n for r in lp.through if (n := self.node(Ref.parse(r) or Ref("", "")))]
            for n in parts:
                if n in self.homes and n != of:
                    self.edge([me, n], f"{self.said(me)}'s loop runs through {self.said(n)}")
        verbs = {"flow": "moves", "goal": "sets", "block": "commands", "auxiliary": "sets", "stock": "sets"}
        for b in s.blocks.values():
            if b.implied:
                continue
            me = ("block", b.name)
            for r in b.reads():
                if (n := self.node(r)) and n != me:
                    self.edge([me, n], f"{self.said(me)} reads {self.said(n)}")
            if b.pool_now is not None and (n := self.node(b.pool_now)):
                self.edge([me, n], f"{self.said(me)} reads its pool from {self.said(n)}")
            for t in b.targets():
                if (n := self.node(t)) and n != me:
                    self.edge([me, n], f"{self.said(me)} {verbs.get(t.kind, 'writes')} {self.said(n)}")
            if b.takes is not None and ("projection", b.takes.kind) in self.homes:
                p = ("projection", b.takes.kind)
                self.edge([me, p], f"{self.said(me)} takes {self.said(p)} items")
        for k in s.items.values():
            me = ("projection", k.name)
            for rel in k.relations.values():
                for q in rel.kinds:
                    if q != k.name and ("projection", q) in self.homes:
                        self.edge([me, ("projection", q)],
                                  f"{self.said(me)}'s relation {rel.name} names {self.said(('projection', q))}")

    def carried(self) -> None:
        """Sensors with their part and the projection a sensor counts with it, agents with the blocks they fill,
        wherever those are."""
        for name, x in self.tables["sensor"].items():
            part = (x.of.kind, x.of.name)
            counted = ("projection", x.items.get("kind")) if x.items else None
            for system in self.systems:
                if self.homes.get(part) != system and part in self.got[system]:
                    self.put(system, ("sensor", name), f"sensor {name} is on {self.said(part)}")
                    if counted in self.homes and self.homes[counted] != system:
                        self.put(system, counted, f"sensor {name} on {self.said(part)} counts {self.said(counted)}")
        for b in self.tables["block"].values():
            if not b.agent or ("agent", b.agent) not in self.homes:
                continue
            me, a = ("block", b.name), ("agent", b.agent)
            for system in self.systems:
                if (me in self.got[system] or self.homes[me] == system) and self.homes[a] != system:
                    self.put(system, a, f"{self.said(a)} fills {self.said(me)}")

    def work(self) -> dict:
        self.edges()
        self.carried()
        out = {}
        for system in self.systems:
            contains: dict[str, list] = {plural: [] for _, plural in KINDS}
            rows = [(n, "defined", [f"defined in {where(system)}"]) for n, h in self.homes.items() if h == system]
            rows += [(n, "ancillary", why) for n, why in self.got[system].items() if self.homes[n] != system]
            for n, status, why in sorted(rows, key=lambda r: self.order[r[0]]):
                h = self.homes[n]
                contains[PLURAL[n[0]]].append({"name": n[1], "status": status, "defined_in": h, "why": list(why)})
            out[system] = {"within": None if system == TOP else (self.s.within.get(system) or TOP),
                           "systems": [x for x in self.systems if x != TOP and system ==
                                       (None if x == TOP else (self.s.within.get(x) or TOP))],
                           "contains": {k: v for k, v in contains.items() if v}}
        return out


def ancillary(spec: Spec, system: str) -> list[tuple[str, dict]]:
    """The system's ancillary things, each ``(kind, row)``."""
    got = scope(spec).get(system, {}).get("contains", {})
    return [(k, r) for k, rows in got.items() for r in rows if r["status"] == "ancillary"]


def lines(spec: Spec, system: str | None = None, indent: str = "  ") -> list[str]:
    """``explain``'s words for what each system (or one) contains: what it defines, counted, and each ancillary
    thing with why it is there."""
    sc = scope(spec)
    out: list[str] = []
    for name in ([system] if system is not None else list(sc)):
        got = sc.get(name)
        if got is None:
            continue
        rows = [(k, r) for k, rs in got["contains"].items() for r in rs]
        mine = [r for _, r in rows if r["status"] == "defined"]
        anc = [(k, r) for k, r in rows if r["status"] == "ancillary"]
        title = "The top level" if name == TOP else f"System {name}"
        within = "" if got["within"] is None else f", within {where(got['within'])}"
        out.append(f"{title}{within}: {len(rows)} things, {len(mine)} defined here, {len(anc)} ancillary.")
        if mine:
            out.append(f"{indent}Defined here: " + "; ".join(
                f"{k} {', '.join(r['name'] for r in rs if r['status'] == 'defined')}"
                for k, rs in got["contains"].items() if any(r["status"] == "defined" for r in rs)) + ".")
        for k, r in anc:
            src = "ergostat's own" if r["defined_in"] is OWN else f"defined in {where(r['defined_in'])}"
            out.append(f"{indent}Ancillary {k[:-1] if k != 'auxiliaries' else 'auxiliary'} {r['name']} ({src}): "
                       + "; ".join(r["why"]) + ".")
    return out
