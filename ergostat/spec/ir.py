"""The compiled model: the five written types (SPEC §5–§10) as plain objects, references resolved,
and what is derived from them (actuators, controllers, loops, disturbances), never written."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .load import Where

BUILTIN = ("onoff", "compare", "proportional", "limit", "delay", "schedule", "lookup", "select", "expr", "timer",
           "counter", "alarm", "judge")   # judge: ergostat's judge of changes to the model (SPEC §12e), on the program rung
MACHINE = ("program", "ai", "person", "external")
FORMATS = ("image", "markdown", "code", "text", "json", "claude-session")   # how a file an item names is shown
SETPOINT = re.compile(r"^\s*(<=|>=|==|<|>)\s*(-?\d+(?:\.\d+)?)\s*$")
NAME = re.compile(r"^[a-z][a-z0-9-]*$")
REF = re.compile(r"^(stock|flow|auxiliary|variable|goal|block)\.([a-z][a-z0-9-]*)(?:\.([a-z][a-z0-9-]*))?$")
OLD_KIND = {"variable": "auxiliary"}     # what a kind was called before (SPEC §7a): still read, with a finding


@dataclass(frozen=True)
class Ref:
    kind: str                  # stock, flow, auxiliary, goal, block
    name: str
    port: str | None = None

    def __str__(self) -> str:
        return f"{self.kind}.{self.name}" + (f".{self.port}" if self.port else "")

    @staticmethod
    def parse(text) -> Ref | None:
        m = REF.match(text) if isinstance(text, str) else None
        return Ref(OLD_KIND.get(m.group(1), m.group(1)), m.group(2), m.group(3)) if m else None

    @staticmethod
    def signed(text) -> tuple[Ref | None, int | None]:
        """``+stock.x`` or ``-auxiliary.y``: a reference with its polarity (+1, -1), or None when
        unsigned (not known)."""
        sign = None
        if isinstance(text, str) and text[:1] in "+-":
            sign, text = (1 if text[0] == "+" else -1), text[1:]
        return Ref.parse(text), sign


def sign_text(sign: int | None) -> str | None:
    """+1, -1, None as the graph and the explanations write them: "+", "-", None (not known)."""
    return None if sign is None else "+" if sign > 0 else "-"


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


MEASURE = re.compile(r"^ergostat\.model\.([a-z][a-z0-9-]*)$")   # a built-in measure, beside stock.x, flow.x, auxiliary.x
MODEL_MEASURES = {                 # the model's own quality (SPEC §12e), read by a sensor: builtin: ergostat.model.fit
    "ergostat.model.fit": "the scaled error of the model's replay on the reference window (the Fit page's total; lower is "
                          "better)",
    "ergostat.model.unexplained": "the share of the stocks' change over the last hour that their flows do not explain (the "
                                  "residuals), averaged over the stocks that moved",
    "ergostat.model.unidentified-loops": "the goals whose loop closes and whose process the model does not hold (no process:)",
    "ergostat.model.open-findings": "the findings ergostat check reports (structure, signs, control), errors aside",
    # how the improvement loop itself is doing (SPEC §12f, numbers/meta.py), over the last week
    "ergostat.model.accepted-per-day": "changes written to the model a day, over the last week",
    "ergostat.model.regressed": "changes written over the last week that the prediction check flagged for revert",
    "ergostat.model.verified-share": "of the changes the prediction check scored over the last week, the share whose "
                                     "forecasts held",
    "ergostat.model.fit-gained": "what the changes written over the last week lowered the scaled error by, together",
    "ergostat.model.cost-per-accepted": "dollars the blocks that make changes spent over the last week, over the changes "
                                        "written",
}
MODEL_CHANGE = "ergostat.model-change"   # the built-in item kind: every change to the model, made, judged and decided
MODEL_CHANGE_STATES = ["made", "checked", "testing", "passed", "accepted", "refused", "failed", "dismissed", "superseded",
                       "verified", "regressed"]   # verified, regressed: an accepted change scored again later (SPEC §12f)
JUDGE_PORTS = ("testing", "passed", "failed", "accepted")


@dataclass
class Improve:
    """The judge block's policy (SPEC §12e): who writes a change it passed, by its kind (``auto``: the judge writes
    it; ``owner``: it waits in the review queue), the least fall in scaled error that counts in every window, how much
    record after a change it is judged on, and how that record is split into windows (1: whole; 2: halves; ...)."""
    accept: dict[str, str] = field(default_factory=lambda: {"parameter": "owner", "equation": "owner", "structure": "owner"})
    threshold: float = 0.02
    hold_out: float = 600.0
    windows: list[int] = field(default_factory=lambda: [1, 2, 4])
    warm_up: float = 6 * 3600.0     # each window replayed from this long before it, its stocks and delays warm
    block: str | None = None


def model_change_kind() -> ItemKind:
    on = {f"{MODEL_CHANGE}.{s}": s for s in MODEL_CHANGE_STATES if s != "made"}
    on[f"{MODEL_CHANGE}.made"] = "made"
    return ItemKind(MODEL_CHANGE, f"{MODEL_CHANGE}/*", list(MODEL_CHANGE_STATES), on,
                    ["title", "kind", "made_by", "confidence", "verdict"], {}, None,
                    "every change to the model: made by a block, ergostat's own finders or the owner; checked, judged, "
                    "and accepted or not (built in, SPEC §12e)")


@dataclass
class Sensor:
    name: str
    of: Ref                    # the stock or flow it measures
    run: str | None = None
    query: dict | None = None
    items: dict | None = None  # counted from the record: kind, state, entering, leaving, where, over, measure
    changes: dict | None = None   # a flow's rate from its stock's own readings: what (rises, falls, net), over, stock
    manual: bool = False
    every: float | None = 60.0
    cron: str | None = None
    timeout: float = 30.0
    parse: str | None = None
    unit: str = ""
    description: str = ""
    where: Where | None = None
    averages: float | None = None    # on a flow: its reading is the average rate over this window (seconds) before it
    builtin: str | None = None  # a built-in measure (MODEL_MEASURES: ergostat.model.fit), read by ergostat (``run`` says how)

    @property
    def window(self) -> float:
        """How far back a reading of a flow's rate looks (seconds; 0: the rate at that moment): what
        ``averages:`` says, or the ``over:`` an items or changes sensor counts over."""
        if self.items and self.of.kind == "flow":
            return float(self.items.get("over") or 3600.0)
        if self.changes:
            return float(self.changes.get("over") or 3600.0)
        return float(self.averages or 0.0)

    @property
    def ref(self) -> Ref:
        return Ref(self.of.kind, self.of.name, self.name)

    @property
    def measured(self) -> bool:
        """Read by ergostat on a schedule (a command, a query, or a count of items), not by hand."""
        return bool(self.run or self.query or self.items or self.changes)

    @property
    def series(self) -> str:
        return f"sensor/{self.of.name}.{self.name}"


@dataclass
class Parameter:
    """A number an equation names (SPEC §7b): declared with its value and unit, to be fitted from
    the record (``estimate: true``), or not known yet (no value). A ``table`` makes it a lookup:
    points, linear between them."""

    name: str
    value: float | None = None
    unit: str = ""
    estimate: bool = False
    table: list[tuple[float, float]] | None = None
    description: str = ""
    system: str | None = None
    where: Where | None = None
    defined: Where | None = None       # the line its name is on
    value_at: Where | None = None      # the line its value is on (what an accepted estimate rewrites)
    duration: bool = False             # its value was written as a duration (40s): an estimate is written back as one
    range: tuple[float, float] | None = None   # what it might be (low, high): sensitivity analysis samples it there

    @property
    def provenance(self) -> str:
        """declared (its value is written), or unknown (none is, yet); an estimate is kept apart, in
        the state directory, until it is accepted."""
        return "declared" if self.value is not None or self.table else "unknown"


@dataclass
class Equation:
    """What a flow's rate (per hour) or an auxiliary's value is, as written (``equation:``): its text,
    its tree (spec/equation.py), what it names."""

    text: str
    tree: tuple
    refs: list[str] = field(default_factory=list)          # the parts it names: stock.x, flow.y, auxiliary.z
    parameters: list[str] = field(default_factory=list)    # the parameters it names
    where: Where | None = None


@dataclass
class Stock:
    name: str
    unit: str = ""
    limit: float | None = None
    initial: float | None = None
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    cumulative: bool = False   # a running total that by its nature never drains (spent so far): no outflow is missing
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
    polarity: dict[str, int] = field(default_factory=dict)   # str(ref) → +1 or -1, for the driven-by written with a sign
    instant: set[str] = field(default_factory=set)       # str(ref) of the driven-by declared immediate (instant: true)
    two_way: bool = False      # it may run either way (system dynamics' biflow): a block may move it by a negative amount
    equation: Equation | None = None   # its rate per hour, as an equation of parameters and parts (SPEC §7b)
    where: Where | None = None
    defined: Where | None = None       # the line its name is on


@dataclass
class Auxiliary:
    """A quantity without memory (SPEC §7a): determined at each moment by others, through an
    equation that may be unknown, and so measured (a score, a ratio, a share of traffic). System
    dynamics' auxiliary. What has memory, whose value persists and changes only through its flows,
    is a stock, even when it is a setting. Process variable and manipulated variable are roles a
    part plays in a loop, not kinds of quantity."""

    name: str
    unit: str = ""
    system: str | None = None
    description: str = ""
    sensors: dict[str, Sensor] = field(default_factory=dict)
    driven_by: list[Ref] = field(default_factory=list)
    polarity: dict[str, int] = field(default_factory=dict)
    instant: set[str] = field(default_factory=set)
    exogenous: bool = False    # an input from outside the model: nothing in it drives it (the weather, the mix of customers)
    equation: Equation | None = None   # its value, as an equation (SPEC §7b); without one it is measured
    where: Where | None = None
    defined: Where | None = None       # the line its name is on


@dataclass
class Goal:
    name: str
    of: Ref                    # stock.x, flow.x or auxiliary.x
    hold: Setpoint
    tolerance: float = 0.0
    critical: bool = False
    owner: str = ""
    system: str | None = None
    description: str = ""
    where: Where | None = None
    process: dict | None = None    # the loop's process, u to y (SPEC §8): form, gain, tau and theta (s), identified

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
    signs: dict[str, int] = field(default_factory=dict)         # port → +1 or -1, for an input written with a sign (+stock.x)

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
    formats: dict[str, str] = field(default_factory=dict)   # field → how its file is shown (FORMATS); else by its extension
    system: str | None = None
    description: str = ""
    where: Where | None = None
    fold: dict[str, str] = field(default_factory=dict)   # field → how plain data folds into it (changes.RULES); else replace

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
class NamedLoop:
    """A feedback loop the model names (``loops:``): the loop through every part in ``through``, or
    the one that seeks ``goal``; the shortest such loop takes the name."""

    name: str
    through: list[Ref] = field(default_factory=list)
    goal: str | None = None
    description: str = ""
    where: Where | None = None


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
    auxiliaries: dict[str, Auxiliary] = field(default_factory=dict)
    systems: dict[str, str] = field(default_factory=dict)        # name → description
    within: dict[str, str] = field(default_factory=dict)         # a system → the system it is part of
    show: dict[str, list[Ref]] = field(default_factory=dict)     # a system → the measures its box shows (default: its goals')
    named_loops: dict[str, NamedLoop] = field(default_factory=dict)   # loops: the feedback loops the model names (SPEC §12a)
    parameters: dict[str, Parameter] = field(default_factory=dict)    # the numbers equations name (SPEC §7b)
    improve: Improve = field(default_factory=Improve)                  # the judge block's policy (SPEC §12e)

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
        t = {"stock": self.stocks, "flow": self.flows, "auxiliary": self.auxiliaries, "goal": self.goals,
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
        return {"stock": self.stocks, "flow": self.flows, "auxiliary": self.auxiliaries}.get(kind, {})

    def sensors(self) -> list[Sensor]:
        return [s for t in (*self.stocks.values(), *self.flows.values(), *self.auxiliaries.values()) for s in t.sensors.values()]

    def sensor(self, ref: Ref) -> Sensor | None:
        t = self.measured(ref.kind).get(ref.name)
        return t.sensors.get(ref.port or "") if t else None

    def setter_of(self, auxiliary: str) -> Block | None:
        """The block that states an auxiliary's value each run, when one does."""
        return next((b for b in self.blocks.values() if Ref("auxiliary", auxiliary) in b.targets()), None)

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
        if any(t.kind in ("flow", "auxiliary") for t in b.targets()):
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
        hit = lambda r: (r.kind == "flow" and what.kind != "auxiliary" and r.name in stock_flows) or \
            (r.kind == "auxiliary" and what.kind == "auxiliary" and r.name == what.name)        # noqa: E731
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
        dist = [f for f in stock_flows if f not in valves] if what.kind != "auxiliary" else []
        toward = set()                     # the flows that move the stock toward its goal: the path should end on one
        if what.kind == "stock":
            down = g.hold.op in ("<=", "<")
            either = g.hold.op == "=="     # held at a level: a flow either way moves it toward the goal
            toward = {f"flow.{f.name}" for f in self.flows_of(what.name) if (f.source == what.name) == down or f.two_way or either}
        targets = {f"auxiliary.{what.name}"} if what.kind == "auxiliary" else {f"flow.{f}" for f in stock_flows}
        through = [] if actuators else self.long_way(ctl, targets, what, toward)
        if through:                        # the flow it closes through is its way in, not a disturbance
            dist = [f for f in dist if f"flow.{f}" != through[-1]]
        return Loop(goal, sensors, controllers, actuators, valves, dist, through)

    def readers(self, kind: str, name: str) -> list[Block]:
        """Blocks reading a stock (or a goal on it), a flow, or a goal."""
        goals = {g for g, x in self.goals.items() if x.of == Ref(kind, name)} if kind in ("stock", "flow", "auxiliary") else set()
        return [b for b in self.blocks.values() if any((r.kind == kind and r.name == name) or
                                                         (r.kind == "goal" and (r.name in goals or (kind == "goal" and r.name == name)))
                                                         for r in b.reads())]

    def long_way(self, ctl: list[Block], targets: set[str], what: Ref, toward: set[str] | None = None) -> list[str]:
        """A loop may close through other stocks and other systems: its controller files work into
        a queue, that queue's own loop works it off, and what that work moves drives a flow of the
        goal's stock (``driven-by``). The shortest such path, from the controller to a flow of the
        goal's stock (or to the goal's auxiliary); empty when there is none. ``targets`` and ``toward``
        are references (flow.x, auxiliary.y).

        A controller that steps a setting closes this way too: it moves a two-way flow into a stock
        (the setting, which keeps its value between steps: integral action), and what the goal
        holds is driven by that stock."""
        drives: dict[str, list[str]] = {}
        for kind, table in (("flow", self.flows), ("auxiliary", self.auxiliaries)):
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
                nxt += [str(Ref(t.kind, t.name)) for t in b.targets() if t.kind in ("flow", "goal", "auxiliary")]
            elif kind == "goal":
                nxt += [f"block.{b.name}" for b in self.readers("goal", name)]
            elif kind == "flow":
                f = self.flows[name]
                nxt += [f"stock.{s}" for s in (f.target, f.source) if s and s != what.name]
                nxt += drives.get(n, [])
            elif kind in ("stock", "auxiliary"):
                nxt += [f"block.{b.name}" for b in self.readers(kind, name)]
                nxt += drives.get(n, [])
            for x in nxt:
                if x not in prev:
                    prev[x] = n
                    todo.append(x)
        return fallback

    def loops(self) -> list[Loop]:
        return [self.loop(g) for g in self.goals]
