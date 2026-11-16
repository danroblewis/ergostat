"""The compiled model: the five written types (SPEC §5–§10) as plain objects, references resolved,
and what is derived from them (actuators, controllers, loops, disturbances), never written."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .load import Where

BUILTIN = ("onoff", "compare", "proportional", "limit", "delay", "schedule", "lookup", "select", "expr", "timer",
           "counter", "alarm")
MACHINE = ("program", "ai", "person", "external")
SETPOINT = re.compile(r"^\s*(<=|>=|==|<|>)\s*(-?\d+(?:\.\d+)?)\s*$")
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
REF = re.compile(r"^(stock|flow|variable|goal|block)\.([a-z][a-z0-9-]*)(?:\.([a-z][a-z0-9-]*))?$")


@dataclass(frozen=True)
class Ref:
    kind: str                  # stock, flow, goal, block
    name: str
    port: str | None = None

    def __str__(self) -> str:
        return f"{self.kind}.{self.name}" + (f".{self.port}" if self.port else "")

    @staticmethod
    def parse(text) -> Ref | None:
        m = REF.match(text) if isinstance(text, str) else None
        return Ref(m.group(1), m.group(2), m.group(3)) if m else None


@dataclass
class Setpoint:
    op: str
    value: float

    @staticmethod
    def parse(text) -> Setpoint | None:
        m = SETPOINT.match(str(text)) if isinstance(text, str | int | float) and not isinstance(text, bool) else None
        return Setpoint(m.group(1), float(m.group(2))) if m else None

    def __str__(self) -> str:
        v = int(self.value) if self.value == int(self.value) else self.value
        return f"{self.op} {v}"

    def error(self, y: float, r: float | None = None) -> float:
        """e = r − y: negative when y is too high, positive when too low, 0 on a one-sided
        setpoint's satisfied side."""
        r = self.value if r is None else r
        if self.op in ("<=", "<"):
            return min(0.0, r - y)
        if self.op in (">=", ">"):
            return max(0.0, r - y)
        return r - y

    def outside(self, y: float, band: float = 0.0, r: float | None = None) -> bool:
        r = self.value if r is None else r
        return {"<=": y > r + band, "<": y >= r + band, ">=": y < r - band, ">": y <= r - band}.get(self.op, abs(y - r) > band)


@dataclass
class Sensor:
    name: str
    of: Ref                    # the stock or flow it measures
    run: str | None = None
    query: dict | None = None
    items: dict | None = None  # counted from the record: kind, state, entering, leaving, where, over, measure
    manual: bool = False
    every: float | None = 60.0
    cron: str | None = None
    timeout: float = 30.0
    parse: str | None = None
    unit: str = ""
    description: str = ""
    where: Where | None = None

    @property
    def ref(self) -> Ref:
        return Ref(self.of.kind, self.of.name, self.name)

    @property
    def measured(self) -> bool:
        """Read by ergostat on a schedule (a command, a query, or a count of items), not by hand."""
        return bool(self.run or self.query or self.items)

    @property
    def series(self) -> str:
        return f"sensor/{self.of.name}.{self.name}"


@dataclass
class Stock:
    name: str
    unit: str = ""
    limit: float | None = None
    initial: float | None = None
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    where: Where | None = None


@dataclass
class Flow:
    name: str
    source: str | None = None  # from: a stock, or None (outside)
    target: str | None = None  # to
    unit: str = ""
    rate: float | None = None
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    driven_by: list[Ref] = field(default_factory=list)   # what its rate depends on: other flows, stocks (an influence)
    where: Where | None = None


@dataclass
class Variable:
    """What is measured or set but does not accumulate (SPEC §7a): a ratio, a score, an age, a
    setting. System dynamics' auxiliary; control theory's process variable (measured) or
    manipulated variable (set by a block). Nothing flows into it."""

    name: str
    unit: str = ""
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    driven_by: list[Ref] = field(default_factory=list)
    where: Where | None = None


@dataclass
class Goal:
    name: str
    of: Ref                    # stock.x or flow.x
    hold: Setpoint
    tolerance: float = 0.0
    critical: bool = False
    owner: str = ""
    system: str | None = None
    description: str = ""
    where: Where | None = None

    def status(self, y: float, was_off: bool, r: float | None = None) -> str:
        """Off past the setpoint by more than the tolerance; once off, holding again only back
        within the setpoint (for ==, within half the tolerance)."""
        back = self.tolerance / 2 if self.hold.op == "==" else 0.0
        return "off" if self.hold.outside(y, back if was_off else self.tolerance, r) else "holding"


@dataclass
class Block:
    name: str
    type: str
    inputs: dict[str, Ref] = field(default_factory=dict)        # port → reference
    outputs: dict[str, list[Ref]] = field(default_factory=dict)  # port → where it goes
    params: dict = field(default_factory=dict)                   # the type's own keys, as written
    agent: str | None = None
    role: str | None = None
    system: str | None = None
    description: str = ""
    every: float | None = None
    cron: str | None = None
    timeout: float = 300.0
    max: float | None = None
    min: float | None = None
    mode: str = "auto"
    where: Where | None = None
    implied: bool = False      # put in by ergostat (a machine block's goal:), not written

    @property
    def builtin(self) -> bool:
        return self.type in BUILTIN

    @property
    def machine(self) -> bool:
        return self.type in MACHINE and self.type != "external"

    @property
    def goal(self) -> str | None:
        g = self.params.get("goal")
        return g if isinstance(g, str) else None

    def targets(self) -> list[Ref]:
        return [r for refs in self.outputs.values() for r in refs]

    def reads(self) -> list[Ref]:
        """Every signal it reads: its inputs, and its goal for the types that take one."""
        out = list(self.inputs.values())
        if self.goal:
            out.append(Ref("goal", self.goal))
        return out


@dataclass
class Agent:
    name: str
    kind: str | None = None
    external: bool = False
    at_once: int = 1
    model: str | None = None
    cost: str | None = None
    host: str | None = None
    description: str = ""
    where: Where | None = None


@dataclass
class ItemKind:
    """A kind of item (SPEC §5a): which ids are this kind, the states they move through, and the
    event types that move them."""

    name: str
    id: str                    # a glob over ids: github/pull_request/*
    states: list[str] = field(default_factory=list)   # the first is where a new item starts
    on: dict[str, str] = field(default_factory=dict)   # event type → the state it moves the item to
    show: list[str] = field(default_factory=list)      # fields worth a column
    system: str | None = None
    description: str = ""
    where: Where | None = None

    def matches(self, id: str) -> bool:
        import fnmatch
        return fnmatch.fnmatchcase(id, self.id)


@dataclass
class Source:
    name: str
    type: str
    url: str = ""
    where: Where | None = None


@dataclass
class Loop:
    """A goal's loop: the goal, what measures it, the blocks serving it, and the flows they set."""

    goal: str
    sensors: list[str]         # stock.x.s references
    controllers: list[str]     # blocks that read the goal (or its stock) and command
    actuators: list[str]       # blocks that set a flow of the goal's stock, reached from the controllers
    valves: list[str]          # those flows
    disturbances: list[str]    # the stock's other flows
    through: list[str] = field(default_factory=list)   # when it closes the long way: the path, part by part

    @property
    def closes(self) -> bool:
        return bool(self.sensors and (self.actuators or self.through))


@dataclass
class Spec:
    name: str
    root: Path
    files: list[Path]
    keep: float = 30 * 86400.0
    stocks: dict[str, Stock] = field(default_factory=dict)
    flows: dict[str, Flow] = field(default_factory=dict)
    goals: dict[str, Goal] = field(default_factory=dict)
    blocks: dict[str, Block] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)
    items: dict[str, ItemKind] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    systems: dict[str, str] = field(default_factory=dict)        # name → description
    within: dict[str, str] = field(default_factory=dict)         # a system → the system it is part of
    show: dict[str, list[Ref]] = field(default_factory=dict)     # a system → the measures its box shows (default: its goals')

    # ---- systems: a tree; a part belongs to one, and to every system that one is within

    def chain(self, system: str | None) -> list[str]:
        """The system and every system it is within, innermost first."""
        out: list[str] = []
        while system and system not in out:
            out.append(system)
            system = self.within.get(system)
        return out

    def subsystems(self, system: str | None) -> list[str]:
        """The systems directly within this one (None: the top level)."""
        return sorted(s for s in self.systems if self.within.get(s) == system)

    def owner(self, r: Ref) -> str | None:
        """The system a referenced part belongs to (a sensor: its stock's or flow's)."""
        t = {"stock": self.stocks, "flow": self.flows, "variable": self.variables, "goal": self.goals,
             "block": self.blocks}.get(r.kind, {})
        x = t.get(r.name)
        return getattr(x, "system", None) if x else None

    def inside(self, r: Ref, system: str) -> bool:
        return system in self.chain(self.owner(r))

    def interface(self, system: str) -> list[dict]:
        """What crosses the system's boundary, each crossing a port: worked out, never written.

        In: a setpoint (an outside block sets a goal inside: the cascade), a command (to a block
        inside), an action (an outside block moves a flow inside), a signal (something inside
        reads something outside), material (a flow from an outside stock into one inside), an
        influence (a flow inside driven by something outside). Out: the same, the other way."""
        ports: dict[tuple, dict] = {}

        def port(dir: str, kind: str, inner: Ref, outer: Ref) -> None:
            p = ports.setdefault((dir, kind, str(inner)), {"dir": dir, "kind": kind, "part": str(inner), "peers": []})
            if str(outer) not in p["peers"]:
                p["peers"].append(str(outer))
        for f in self.flows.values():
            ends = [(e, self.inside(Ref("stock", e), system)) for e in (f.source, f.target) if e]
            if len(ends) == 2 and ends[0][1] != ends[1][1]:
                inner, outer = (ends[0][0], ends[1][0]) if ends[0][1] else (ends[1][0], ends[0][0])
                port("out" if ends[0][1] else "in", "material", Ref("flow", f.name), Ref("stock", outer))
            here = self.inside(Ref("flow", f.name), system)
            for r in f.driven_by:
                if self.inside(r, system) != here:
                    port("in", "influence", Ref("flow", f.name), r) if here else port("out", "influence", r, Ref("flow", f.name))
        for b in self.blocks.values():
            if b.implied:                                 # its machine block's goal: says the same
                continue
            me = Ref("block", b.name)
            here = self.inside(me, system)
            for r in b.reads():
                r = Ref(r.kind, r.name)
                if r.kind == "block" or self.inside(r, system) == here:
                    continue
                port("in", "signal", me, r) if here else port("out", "signal", r, me)
            for t in b.targets():
                t = Ref(t.kind, t.name)
                if self.inside(t, system) == here:
                    continue
                kind = {"goal": "setpoint", "block": "command", "flow": "action"}[t.kind]
                port("out", kind, me, t) if here else port("in", kind, t, me)
            for r in b.inputs.values():                  # a block inside reading one outside, or the other way
                if r.kind == "block" and self.inside(Ref("block", r.name), system) != here:
                    port("in", "command", me, Ref("block", r.name)) if here else port("out", "command", Ref("block", r.name), me)
        return sorted(ports.values(), key=lambda p: (p["dir"] != "in", p["kind"], p["part"]))

    def inner_loops(self, system: str) -> list[str]:
        """Goals inside whose setpoint comes from outside and whose measurement goes back out: the
        system is, seen from outside, one block that holds what it is told (a cascade's inner loop)."""
        ports = self.interface(system)
        set_from_outside = {p["part"].split(".", 1)[1] for p in ports if p["dir"] == "in" and p["kind"] == "setpoint"}
        read_outside = {p["part"] for p in ports if p["dir"] == "out" and p["kind"] == "signal"}
        return [g for g in sorted(set_from_outside) if g in self.goals and
                (str(self.goals[g].of) in read_outside or f"goal.{g}" in read_outside)]

    # ---- lookups: the reverse relations, never written

    def measured(self, kind: str) -> dict:
        """The table of things a sensor may measure, by kind."""
        return {"stock": self.stocks, "flow": self.flows, "variable": self.variables}.get(kind, {})

    def sensors(self) -> list[Sensor]:
        return [s for t in (*self.stocks.values(), *self.flows.values(), *self.variables.values()) for s in t.sensors.values()]

    def sensor(self, ref: Ref) -> Sensor | None:
        t = self.measured(ref.kind).get(ref.name)
        return t.sensors.get(ref.port or "") if t else None

    def setter_of(self, variable: str) -> Block | None:
        return next((b for b in self.blocks.values() if Ref("variable", variable) in b.targets()), None)

    def flows_of(self, stock: str) -> list[Flow]:
        return [f for f in self.flows.values() if stock in (f.source, f.target)]

    def actuator_of(self, flow: str) -> Block | None:
        return next((b for b in self.blocks.values() if Ref("flow", flow) in b.targets()), None)

    def commanders_of(self, block: str) -> list[Block]:
        """The blocks that command ``block``: those that output to it, and those whose output it
        reads (the wire may be written on either end)."""
        reads = {r.name for r in self.blocks[block].inputs.values() if r.kind == "block"}
        return [b for b in self.blocks.values() if b.name != block and
                (b.name in reads or any(t.kind == "block" and t.name == block for t in b.targets()))]

    def downstream(self, block: str) -> list[Block]:
        """Blocks that read ``block``'s output, and those it outputs to directly."""
        out = {t.name for t in self.blocks[block].targets() if t.kind == "block"}
        out |= {b.name for b in self.blocks.values() if any(r.kind == "block" and r.name == block for r in b.inputs.values())}
        return [self.blocks[n] for n in sorted(out) if n in self.blocks]

    def agent_blocks(self, agent: str) -> list[Block]:
        return [b for b in self.blocks.values() if b.agent == agent]

    def role(self, b: Block) -> str:
        if b.role:
            return b.role
        if any(t.kind in ("flow", "variable") for t in b.targets()):
            return "actuator"
        reads_state = any(r.kind in ("goal", "stock", "flow") for r in b.reads())
        commands = any(t.kind in ("block", "goal") for t in b.targets())
        return "controller" if reads_state and commands else "logic"

    def goal_value_ref(self, goal: str) -> Ref:
        return self.goals[goal].of

    def loop(self, goal: str) -> Loop:
        g = self.goals[goal]
        what = g.of
        t = self.measured(what.kind).get(what.name)
        sensors = [str(s.ref) for s in (t.sensors.values() if t else [])]
        stock_flows = [f.name for f in self.flows_of(what.name)] if what.kind == "stock" else [what.name]
        hit = lambda r: (r.kind == "flow" and what.kind != "variable" and r.name in stock_flows) or \
            (r.kind == "variable" and what.kind == "variable" and r.name == what.name)        # noqa: E731
        # controllers: blocks reading the goal, or its stock or flow directly
        ctl = [b for b in self.blocks.values()
               if any((r.kind == "goal" and r.name == goal) or (r.kind == what.kind and r.name == what.name) for r in b.reads())]
        reach: list[Block] = []
        seen: set[str] = set()
        todo = list(ctl)
        while todo:
            b = todo.pop(0)
            if b.name in seen:
                continue
            seen.add(b.name)
            reach.append(b)
            todo += self.downstream(b.name)
        actuators = [b.name for b in reach if any(hit(t) for t in b.targets())]
        valves = sorted({t.name for b in reach for t in b.targets() if hit(t)})
        controllers = [b.name for b in ctl if b.name not in actuators or any(t.kind == "block" for t in b.targets())]
        if not controllers and actuators:   # an actuator reading the goal itself: it is its own controller
            controllers = [a for a in actuators if a in {b.name for b in ctl}]
        dist = [f for f in stock_flows if f not in valves] if what.kind != "variable" else []
        toward = set()                     # the flows that move the stock toward its goal: the path should end on one
        if what.kind == "stock":
            down = g.hold.op in ("<=", "<")
            toward = {f"flow.{f.name}" for f in self.flows_of(what.name) if (f.source == what.name) == down}
        targets = {f"variable.{what.name}"} if what.kind == "variable" else {f"flow.{f}" for f in stock_flows}
        through = [] if actuators else self.long_way(ctl, targets, what, toward)
        return Loop(goal, sensors, controllers, actuators, valves, dist, through)

    def readers(self, kind: str, name: str) -> list[Block]:
        """Blocks reading a stock (or a goal on it), a flow, or a goal."""
        goals = {g for g, x in self.goals.items() if x.of == Ref(kind, name)} if kind in ("stock", "flow", "variable") else set()
        return [b for b in self.blocks.values() if any((r.kind == kind and r.name == name) or
                                                         (r.kind == "goal" and (r.name in goals or (kind == "goal" and r.name == name)))
                                                         for r in b.reads())]

    def long_way(self, ctl: list[Block], targets: set[str], what: Ref, toward: set[str] | None = None) -> list[str]:
        """A loop may close through other stocks and other systems: its controller files work into
        a queue, that queue's own loop works it off, and what that work moves drives a flow of the
        goal's stock (``driven-by``). The shortest such path, from the controller to a flow of the
        goal's stock (or to the goal's variable); empty when there is none. ``targets`` and ``toward``
        are references (flow.x, variable.y)."""
        drives: dict[str, list[str]] = {}
        for kind, table in (("flow", self.flows), ("variable", self.variables)):
            for f in table.values():
                for r in f.driven_by:
                    drives.setdefault(f"{r.kind}.{r.name}", []).append(f"{kind}.{f.name}")
        start = [f"block.{b.name}" for b in ctl]
        prev: dict[str, str | None] = {s: None for s in start}
        todo = list(start)
        fallback: list[str] = []
        while todo:
            n = todo.pop(0)
            kind, name = n.split(".", 1)
            nxt: list[str] = []
            if n in targets:
                path, at = [], n
                while at is not None:
                    path.append(at)
                    at = prev[at]
                if not toward or n in toward:
                    return path[::-1]
                fallback = fallback or path[::-1]              # it reaches the stock, the wrong way: keep looking
                continue
            if kind == "block":
                b = self.blocks[name]
                nxt += [f"block.{d.name}" for d in self.downstream(name)]
                nxt += [str(Ref(t.kind, t.name)) for t in b.targets() if t.kind in ("flow", "goal", "variable")]
            elif kind == "goal":
                nxt += [f"block.{b.name}" for b in self.readers("goal", name)]
            elif kind == "flow":
                f = self.flows[name]
                nxt += [f"stock.{s}" for s in (f.target, f.source) if s and s != what.name]
                nxt += drives.get(n, [])
            elif kind in ("stock", "variable"):
                nxt += [f"block.{b.name}" for b in self.readers(kind, name)]
                nxt += drives.get(n, [])
            for x in nxt:
                if x not in prev:
                    prev[x] = n
                    todo.append(x)
        return fallback

    def loops(self) -> list[Loop]:
        return [self.loop(g) for g in self.goals]
