"""Engine shards (SPEC §9.8): every part of the model assigned to one shard, by top-level system, worked out from the
graph and never declared (invariant 8). Shards are merged where a process-local lock would be split (a shared agent, a
taken kind, a daemon); every value one shard reads from another that exists only in memory is listed as a wire.

Pure: ``plan(spec)`` reads the compiled model and changes nothing. Every loop runs over sorted names, so the same
model gives the same plan whatever ``PYTHONHASHSEED`` is."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .ir import Ref
from .observer import PORTS, opted

MAX_SHARDS = 16
LEAD = "lead"
SAFE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PARTS = ("stock", "flow", "auxiliary", "goal", "block")
_LEAD = (0, "")                      # the lead shard's seed; a system's is (1, name): sorted, the lead comes first


@dataclass(frozen=True, order=True)
class Wire:
    ref: str                         # what is carried: goal.x.error, block.a.out, auxiliary.y ...
    source: str                      # the shard that owns it
    target: str                      # the shard that reads it
    kind: str                        # goal, setpoint, command, cascade, equation, memory


@dataclass
class Shard:
    name: str
    systems: list[str]               # the top-level systems in it, sorted
    parts: list[str]                 # its parts' keys, sorted


@dataclass
class Plan:
    lead: str
    shards: dict[str, Shard]
    why: dict[str, list[dict]]
    wires: list[Wire]
    where: dict[str, str] = field(repr=False)     # a part's key → its shard

    def of(self, ref) -> str:
        """The shard a part is in: a Ref, or a key (stock.x, stock.x.sensor, goal.x, agent.x, kind.x). KeyError if
        not in the spec: never a default. A stock's estimate or uncertainty is the stock's (its observer's)."""
        r = ref if isinstance(ref, Ref) else Ref.parse(ref)
        if r is not None and r.kind == "stock" and r.port in PORTS and key(r) not in self.where:
            return self.where[f"stock.{r.name}"]
        return self.where[key(ref)]

    def json(self) -> dict:
        return {"lead": self.lead, "why": self.why, "wires": [vars(w) for w in self.wires],
                "shards": {n: {"systems": s.systems, "parts": s.parts} for n, s in self.shards.items()}}


def key(ref) -> str:
    """A part's key: a block's or goal's port is the part; a stock's, flow's or auxiliary's port is its sensor."""
    r = ref if isinstance(ref, Ref) else Ref.parse(ref)
    if r is None:
        return str(ref)
    return str(r) if r.kind in ("stock", "flow", "auxiliary") else f"{r.kind}.{r.name}"


def safe(name: str) -> str:
    low = name.lower()
    return low if SAFE.match(low) else "s-" + hashlib.sha256(name.encode()).hexdigest()[:12]


def _table(spec, kind: str) -> dict:
    return {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries, "goal": spec.goals,
            "block": spec.blocks}[kind]


def plan(spec, most: int = MAX_SHARDS) -> Plan:
    most = max(1, min(MAX_SHARDS, int(most)))
    seed: dict[str, tuple] = {}                  # a part's key → its seed
    for kind in PARTS:
        for name in sorted(_table(spec, kind)):
            chain = spec.chain(spec.owner(Ref(kind, name)))
            seed[f"{kind}.{name}"] = (1, chain[-1]) if chain else _LEAD
    for kind in ("stock", "flow", "auxiliary"):
        for name, part in sorted(_table(spec, kind).items()):
            for s in sorted(part.sensors):
                seed[f"{kind}.{name}.{s}"] = seed[f"{kind}.{name}"]    # not its series: a stock and a flow may share a name
    tops = [*spec.systems, *(k.system for n, k in spec.items.items() if k.system and not n.startswith("ergostat."))]
    seeds = sorted({_LEAD, *seed.values(), *((1, spec.chain(s)[-1]) for s in tops)})
    parent = {s: s for s in seeds}
    why: dict[tuple, list[dict]] = {s: [] for s in seeds}
    names = {_LEAD: LEAD}
    for s in seeds[1:]:                          # each system's own name: safe, and never another's
        n = cand = safe(s[1])
        for i in range(2, len(seeds) + 2):
            if cand not in names.values():
                break
            cand = f"{n}-{i}" if SAFE.match(f"{n}-{i}") else safe(f"{n}-{i}")
        names[s] = cand

    def find(s):
        while parent[s] != s:
            s = parent[s]
        return s

    def union(a, b, because, via):               # a root is its group's first seed: the lead, or its first system
        ra, rb = sorted((find(a), find(b)))
        if ra != rb:
            parent[rb] = ra
            why[ra] += [{"joined": names[rb], "because": because, "via": via}, *why.pop(rb)]

    # the three merges: what is locked inside one process
    joined = _join_kinds(spec)
    shared: dict[tuple, list] = {}
    for name, b in sorted(spec.blocks.items()):
        s = seed[f"block.{name}"]
        if b.agent:
            shared.setdefault(("agent", b.agent), []).append(s)
        if b.takes:
            shared.setdefault(("kind", joined.get(b.takes.kind, b.takes.kind)), []).append(s)
        if isinstance(b.params.get("daemon"), str):
            shared.setdefault(("daemon", b.params["daemon"]), []).append(s)
    for (because, via), ss in sorted(shared.items()):
        for s in sorted(set(ss))[1:]:
            union(min(ss), s, because, via)

    # agents and kinds: with the blocks that run on or take them; else a kind with its system; else the lead
    for name in sorted(spec.agents):
        on = sorted(n for n, b in spec.blocks.items() if b.agent == name)
        seed[f"agent.{name}"] = seed[f"block.{on[0]}"] if on else _LEAD
    for name, k in sorted(spec.items.items()):
        group = joined.get(name, name)
        on = sorted(n for n, b in spec.blocks.items() if b.takes and joined.get(b.takes.kind, b.takes.kind) == group)
        chain = spec.chain(k.system) if not name.startswith("ergostat.") else []
        seed[f"kind.{name}"] = seed[f"block.{on[0]}"] if on else (1, chain[-1]) if chain else _LEAD

    # the ceiling: the two smallest (in parts; ties by name) merge until there are at most `most`
    size = dict.fromkeys(sorted({find(s) for s in seeds}), 0)
    for s in seed.values():
        size[find(s)] += 1
    while len(size) > most:                      # sizes kept as they merge: linear in parts, not their square
        a, b = sorted(size, key=lambda r: (size[r], names[r]))[:2]
        union(a, b, "ceiling", names[max(a, b)])
        size[min(a, b)] = size.pop(a) + size.pop(b)

    where = {k: names[find(s)] for k, s in seed.items()}
    shards = {names[r]: Shard(names[r], sorted(s[1] for s in seeds if s != _LEAD and find(s) == r),
                              sorted(k for k, n in where.items() if n == names[r]))
              for r in sorted({find(s) for s in seeds})}
    p = Plan(LEAD, dict(sorted(shards.items())), {names[r]: w for r, w in sorted(why.items()) if w}, [], where)
    p.wires = _wires(spec, p)
    return p


def _join_kinds(spec) -> dict[str, str]:
    """Kinds tied by a join (a parent and the kinds whose relation names it), each to its group's first kind by name:
    a block taking one watches the others' moves."""
    up: dict[str, str] = {}

    def find(x):
        while up.get(x, x) != x:
            x = up[x]
        return x

    for name, k in sorted(spec.items.items()):
        for j in k.join:
            for child, ck in sorted(spec.items.items()):
                if name in getattr(ck.relations.get(j.children), "kinds", ()):
                    a, b = sorted((find(name), find(child)))
                    up[b] = a
    return {x: find(x) for x in sorted(spec.items)}


def _wires(spec, p: Plan) -> list[Wire]:
    """Every in-memory value read across shards. Reading a part with sensors is reading the measurements: never a wire;
    a stock's estimate and uncertainty are its observer's, in memory: a wire."""
    out: set[Wire] = set()

    def read(reader: str, r: Ref):
        k = key(Ref(r.kind, r.name))
        if k not in p.where or p.where[k] == p.where[reader]:
            return
        if r.kind in ("stock", "flow", "auxiliary"):
            part = _table(spec, r.kind)[r.name]
            if r.kind == "stock" and r.port in PORTS and r.port not in part.sensors:
                kind = "estimate"
            elif r.port or part.sensors:
                return
            else:
                kind = "equation" if getattr(part, "equation", None) else "memory"
        else:
            kind = "goal" if r.kind == "goal" else "cascade"
        out.add(Wire(str(r), p.where[k], p.where[reader], kind))

    for name, g in sorted(spec.goals.items()):
        read(f"goal.{name}", g.of)
    for kind in ("flow", "auxiliary"):
        for name, part in sorted(_table(spec, kind).items()):
            for text in sorted(part.equation.refs if part.equation else []):
                if (r := Ref.parse(text)) is not None:
                    read(f"{kind}.{name}", r)
    for name in opted(spec).stocks:             # the observer adds up an estimated stock's flows (observer.rates)
        for f in sorted(spec.flows_of(name), key=lambda f: f.name):
            read(f"stock.{name}", Ref("flow", f.name))
    served = {g: spec.loop(g).actuators for g in sorted(spec.goals)}
    for name, b in sorted(spec.blocks.items()):
        goals = {r.name for r in b.reads() if r.kind == "goal"} | {g for g, a in served.items() if name in a}
        for g in sorted(goals & set(spec.goals)):  # a block is given each goal it reads or serves (Engine.context)
            read(f"block.{name}", Ref("goal", g))
            read(f"block.{name}", spec.goals[g].of)
        for r in b.reads():
            read(f"block.{name}", r)
        for t in b.targets():
            tk = key(Ref(t.kind, t.name))
            if tk in p.where and p.where[tk] != p.where[f"block.{name}"]:
                out.add(Wire(str(t), p.where[f"block.{name}"], p.where[tk], "setpoint" if t.kind == "goal" else "command"))
    return sorted(out)
