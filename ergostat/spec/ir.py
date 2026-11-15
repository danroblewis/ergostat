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
REF = re.compile(r"^(stock|flow|goal|block)\.([a-z][a-z0-9-]*)(?:\.([a-z][a-z0-9-]*))?$")


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

    @property
    def closes(self) -> bool:
        return bool(self.sensors and self.actuators)


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
    systems: dict[str, str] = field(default_factory=dict)

    # ---- lookups: the reverse relations, never written

    def sensors(self) -> list[Sensor]:
        return [s for t in (*self.stocks.values(), *self.flows.values()) for s in t.sensors.values()]

    def sensor(self, ref: Ref) -> Sensor | None:
        t = (self.stocks if ref.kind == "stock" else self.flows).get(ref.name)
        return t.sensors.get(ref.port or "") if t else None

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
        if any(t.kind == "flow" for t in b.targets()):
            return "actuator"
        reads_state = any(r.kind in ("goal", "stock", "flow") for r in b.reads())
        commands = any(t.kind in ("block", "goal") for t in b.targets())
        return "controller" if reads_state and commands else "logic"

    def goal_value_ref(self, goal: str) -> Ref:
        return self.goals[goal].of

    def loop(self, goal: str) -> Loop:
        g = self.goals[goal]
        what = g.of
        sensors = [str(s.ref) for s in (self.stocks if what.kind == "stock" else self.flows).get(what.name, Stock("")).sensors.values()]
        stock_flows = [f.name for f in self.flows_of(what.name)] if what.kind == "stock" else [what.name]
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
        actuators = [b.name for b in reach if any(t.kind == "flow" and t.name in stock_flows for t in b.targets())]
        valves = sorted({t.name for b in reach for t in b.targets() if t.kind == "flow" and t.name in stock_flows})
        controllers = [b.name for b in ctl if b.name not in actuators or any(t.kind == "block" for t in b.targets())]
        if not controllers and actuators:   # an actuator reading the goal itself: it is its own controller
            controllers = [a for a in actuators if a in {b.name for b in ctl}]
        dist = [f for f in stock_flows if f not in valves]
        return Loop(goal, sensors, controllers, actuators, valves, dist)

    def loops(self) -> list[Loop]:
        return [self.loop(g) for g in self.goals]
