"""The model: what ``ergostat.toml`` declares, as plain objects, and what follows from it.

The file declares parts (stocks, flows, disturbances, valves, sensors, controllers) and the agents
that fill their roles. Loops are not declared: each controller that holds a stock is a loop, and it
closes when one of its sensors measures that stock (or a flow of it) and one of its valves acts on
a flow of it. Systems are named selections that may overlap."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .durations import parse_duration

FILE = "ergostat.toml"
SHELL_WORDS = {"for", "if", "while", "until", "case", "[", "[[", "{", "(", "!", "test", "exec", "cd", "export", "set"}  # a shell line
KINDS = ("person", "ai", "narrow-ai", "decision", "program", "rule")   # the ladder, top to bottom
RUNG = {k: i for i, k in enumerate(KINDS)}
MODES = ("auto", "advise", "manual")
SETPOINT = re.compile(r"^\s*(<=|>=|==|<|>|=)\s*(-?\d+(?:\.\d+)?)\s*$")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def cron_words(expr: str) -> str:
    """A cron schedule in plain words when it is a common one; else as written."""
    common = {"* * * * *": "every minute", "0 * * * *": "every hour", "0 0 * * *": "daily at 00:00"}
    if expr in common:
        return common[expr]
    p = expr.split()
    if len(p) == 5 and p[0].startswith("*/") and p[1:] == ["*", "*", "*", "*"]:
        return f"every {p[0][2:]} minutes"
    if len(p) == 5 and p[0].isdigit() and p[1:] == ["*", "*", "*", "*"]:
        return f"hourly at :{int(p[0]):02d}"
    if len(p) == 5 and p[0].isdigit() and p[1].startswith("*/") and p[2:] == ["*", "*", "*"]:
        return f"every {p[1][2:]} hours at :{int(p[0]):02d}"
    if len(p) == 5 and p[0].isdigit() and p[1].isdigit() and p[2:] == ["*", "*", "*"]:
        return f"daily at {int(p[1]):02d}:{int(p[0]):02d}"
    if len(p) == 5 and p[0].isdigit() and p[1].isdigit() and p[2:4] == ["*", "*"] and p[4] == "1-5":
        return f"weekdays at {int(p[1]):02d}:{int(p[0]):02d}"
    return f"cron {expr}"


class ModelError(Exception):
    pass


@dataclass
class Part:
    name: str
    description: str = ""
    systems: list[str] = field(default_factory=list)

    kind = "part"


@dataclass
class Stock(Part):
    unit: str = ""
    kind = "stock"


@dataclass
class Flow(Part):
    source: str | None = None          # a stock, or None: outside the boundary
    target: str | None = None
    unit: str = ""
    disturbance: bool = False          # an input no valve controls
    rate: float | None = None          # a disturbance's known rate per hour, when it is declared
    agent: str | None = None           # a disturbance's: whose doing it is (the load), never a role it fills
    kind = "flow"


@dataclass
class Valve(Part):
    flow: str = ""
    agent: str | None = None
    mode: str = "auto"
    mode_set: bool = field(default=False, metadata={"history": False})   # how it was read, not declared
    kind = "valve"


@dataclass
class Sensor(Part):
    measures: str = ""                 # a stock or a flow
    agent: str | None = None
    unit: str = ""
    kind = "sensor"


@dataclass
class Controller(Part):
    holds: str = ""                    # the stock it holds at its setpoint
    setpoint: str = ""                 # "<= 80", ">= 1", "== 0"
    tolerance: float = 0.0
    reads: list[str] = field(default_factory=list)      # sensors
    drives: list[str] = field(default_factory=list)     # valves
    agent: str | None = None
    kind = "controller"

    def target(self) -> tuple[str, float]:
        m = SETPOINT.match(self.setpoint)
        assert m, self.setpoint
        op = "==" if m.group(1) == "=" else m.group(1)
        return op, float(m.group(2))

    def error(self, value: float) -> float:
        """e = r − y, the control convention: negative when ``value`` is too high, positive when
        too low, and 0 on a one-sided setpoint's satisfied side."""
        op, x = self.target()
        if op in ("<=", "<"):
            return min(0.0, x - value)
        if op in (">=", ">"):
            return max(0.0, x - value)
        return x - value

    def violated(self, value: float, band: float = 0.0) -> bool:
        """Outside the setpoint widened by ``band`` on the side that matters; a strict bound
        (``<``, ``>``) counts the bound itself as outside."""
        op, x = self.target()
        if op == "<=":
            return value > x + band
        if op == "<":
            return value >= x + band
        if op == ">=":
            return value < x - band
        if op == ">":
            return value <= x - band
        return abs(value - x) > band

    def status(self, value: float, was_off: bool = False) -> str:
        """Off past the setpoint by more than the tolerance; once off, holding again only back
        within the setpoint itself (the tolerance is a hysteresis band, so a loop near its
        setpoint does not chatter)."""
        return "off" if self.violated(value, 0.0 if was_off else self.tolerance) else "holding"

    def band_text(self) -> str:
        """The tolerance, on the side it applies: ``(+2)`` for <=, ``(−2)`` for >=, ``(±2)`` for ==."""
        if not self.tolerance:
            return ""
        op, _ = self.target()
        sign = "+" if op in ("<=", "<") else "−" if op in (">=", ">") else "±"
        t = self.tolerance
        return f" ({sign}{int(t) if t == int(t) else t})"


@dataclass
class Agent:
    name: str
    kind: str = "program"
    command: str = ""
    every: float | None = None
    on: list[str] = field(default_factory=list)
    description: str = ""
    cron: str | None = None
    timeout: float = 300.0

    @property
    def schedule(self) -> str:
        """How it runs, in a few words."""
        from .durations import human
        parts = ([f"every {human(self.every)}"] if self.every else []) + ([cron_words(self.cron)] if self.cron else []) + \
                ([f"on {', '.join(self.on)}"] if self.on else [])
        return " · ".join(parts)

    @property
    def rung(self) -> int:
        return RUNG[self.kind]


@dataclass
class System:
    name: str
    description: str = ""


@dataclass
class Loop:
    """A controller's loop: what it holds, through which sensors and valves, and whether that
    path closes."""

    name: str
    controller: Controller
    stock: str
    sensors: list[str]
    valves: list[str]
    flows: list[str]
    gaps: list[str]                    # why it cannot close; empty when it can

    @property
    def closes(self) -> bool:
        return not self.gaps


@dataclass
class Model:
    name: str
    path: Path | None
    stocks: dict[str, Stock] = field(default_factory=dict)
    flows: dict[str, Flow] = field(default_factory=dict)
    valves: dict[str, Valve] = field(default_factory=dict)
    sensors: dict[str, Sensor] = field(default_factory=dict)
    controllers: dict[str, Controller] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    systems: dict[str, System] = field(default_factory=dict)
    keep: float = 30 * 86400.0                 # how long the record is kept (the model's history always)

    # ---- lookups

    def tables(self) -> dict[str, dict]:
        return {"stock": self.stocks, "flow": self.flows, "valve": self.valves, "sensor": self.sensors,
                "controller": self.controllers}

    def part(self, name: str) -> Part | None:
        for t in self.tables().values():
            if name in t:
                return t[name]
        return None

    def disturbances(self) -> dict[str, Flow]:
        return {n: f for n, f in self.flows.items() if f.disturbance}

    def valve_of(self, flow: str) -> Valve | None:
        return next((v for v in self.valves.values() if v.flow == flow), None)

    def flows_of(self, stock: str) -> list[Flow]:
        return [f for f in self.flows.values() if stock in (f.source, f.target)]

    def roles_of(self, agent: str) -> list[Part]:
        return [p for t in (self.sensors, self.controllers, self.valves) for p in t.values() if p.agent == agent]

    def loops(self) -> list[Loop]:
        out = []
        for c in self.controllers.values():
            flows = {f.name for f in self.flows_of(c.holds)}
            sensors = [s for s in c.reads if s in self.sensors and (self.sensors[s].measures == c.holds
                                                                       or self.sensors[s].measures in flows)]
            valves = [v for v in c.drives if v in self.valves and self.valves[v].flow in flows]
            gaps = []
            if c.holds not in self.stocks:
                gaps.append(f"holds {c.holds!r}, which is not a stock")
            if not sensors:
                gaps.append(f"none of its sensors measures {c.holds} or a flow of it")
            if not valves:
                gaps.append(f"none of its valves acts on a flow of {c.holds}")
            out.append(Loop(c.name, c, c.holds, sensors, valves, sorted(self.valves[v].flow for v in valves), gaps))
        return out

    def loop(self, name: str) -> Loop | None:
        return next((lp for lp in self.loops() if lp.name == name), None)

    # ---- systems: selections, which may overlap

    def members(self, system: str | None) -> set[str]:
        """Every part in ``system`` (None: every part). A part is in a system when it is tagged
        with it, or attached to a stock that is: that stock's flows, their valves, the sensors
        measuring it or its flows, and the controllers holding it."""
        everything = {n for t in self.tables().values() for n in t}
        if system is None:
            return everything
        tagged = {n for n in everything if system in self.part(n).systems}
        stocks = {n for n in tagged if n in self.stocks}
        out = set(tagged)
        for s in stocks:
            for f in self.flows_of(s):
                out.add(f.name)
                if (v := self.valve_of(f.name)) is not None:
                    out.add(v.name)
            out |= {n for n, x in self.sensors.items() if x.measures == s or x.measures in out}
            out |= {n for n, c in self.controllers.items() if c.holds == s}
        return out

    def system_names(self) -> list[str]:
        named = set(self.systems)
        for t in self.tables().values():
            for p in t.values():
                named |= set(p.systems)
        return sorted(named)


# ---- reading the file

def _names(raw, where: str) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return raw
    raise ModelError(f"{where}: expected a name or a list of names")


def _take(row: dict, allowed: set[str], where: str) -> dict:
    unknown = sorted(set(row) - allowed)
    if unknown:
        raise ModelError(f"{where}: unknown key {unknown[0]!r} (known: {', '.join(sorted(allowed))})")
    if not isinstance(row.get("name"), str) or not NAME.match(row["name"]):
        raise ModelError(f"{where}: a name is required: lowercase letters, digits, - and _")
    return row


COMMON = {"name", "description", "systems"}


def parse(data: dict, path: Path | None = None, default_name: str = "ergostat") -> Model:
    known = {"name", "keep", "stock", "flow", "disturbance", "valve", "sensor", "controller", "agent", "system"}
    if extra := sorted(set(data) - known):
        raise ModelError(f"unknown table {extra[0]!r} (known: {', '.join(sorted(known - {'name'}))})")
    m = Model(name=str(data.get("name") or default_name), path=path,
              keep=parse_duration(data["keep"], "keep") if data.get("keep") is not None else 30 * 86400.0)
    seen: dict[str, str] = {}

    def rows(key):
        v = data.get(key, [])
        if not isinstance(v, list):
            raise ModelError(f"[[{key}]]: write each one as [[{key}]]")
        return v

    def add(table: dict, obj, key: str):
        if obj.name in seen:
            raise ModelError(f"[[{key}]] {obj.name}: the name is already used by a {seen[obj.name]}")
        seen[obj.name] = key
        table[obj.name] = obj

    def common(r, where):
        return {"name": r["name"], "description": str(r.get("description", "")),
                "systems": _names(r.get("systems"), f"{where}.systems")}

    for i, r in enumerate(rows("stock")):
        w = f"[[stock]] #{i + 1}"
        _take(r, COMMON | {"unit"}, w)
        add(m.stocks, Stock(**common(r, w), unit=str(r.get("unit", ""))), "stock")
    for i, r in enumerate(rows("flow")):
        w = f"[[flow]] #{i + 1}"
        _take(r, COMMON | {"from", "to", "unit"}, w)
        add(m.flows, Flow(**common(r, w), source=r.get("from"), target=r.get("to"), unit=str(r.get("unit", ""))), "flow")
    for i, r in enumerate(rows("disturbance")):
        w = f"[[disturbance]] #{i + 1}"
        _take(r, COMMON | {"into", "out_of", "unit", "rate", "agent"}, w)
        if bool(r.get("into")) == bool(r.get("out_of")):
            raise ModelError(f"{w} {r['name']}: say which stock it pushes: into = \"...\" or out_of = \"...\"")
        rate = r.get("rate")
        if rate is not None and (isinstance(rate, bool) or not isinstance(rate, int | float)):
            raise ModelError(f"{w} {r['name']}.rate: a number per hour")
        add(m.flows, Flow(**common(r, w), source=r.get("out_of"), target=r.get("into"), unit=str(r.get("unit", "")),
                          disturbance=True, rate=float(rate) if rate is not None else None, agent=r.get("agent")), "disturbance")
    for i, r in enumerate(rows("valve")):
        w = f"[[valve]] #{i + 1}"
        _take(r, COMMON | {"flow", "agent", "mode"}, w)
        mode = r.get("mode", "auto")
        if mode not in MODES:
            raise ModelError(f"{w} {r['name']}.mode: one of {', '.join(MODES)}")
        add(m.valves, Valve(**common(r, w), flow=str(r.get("flow", "")), agent=r.get("agent"), mode=mode,
                            mode_set="mode" in r), "valve")
    for i, r in enumerate(rows("sensor")):
        w = f"[[sensor]] #{i + 1}"
        _take(r, COMMON | {"measures", "agent", "unit"}, w)
        add(m.sensors, Sensor(**common(r, w), measures=str(r.get("measures", "")), agent=r.get("agent"),
                              unit=str(r.get("unit", ""))), "sensor")
    for i, r in enumerate(rows("controller")):
        w = f"[[controller]] #{i + 1}"
        _take(r, COMMON | {"holds", "setpoint", "tolerance", "reads", "drives", "agent"}, w)
        sp = str(r.get("setpoint", ""))
        if not SETPOINT.match(sp):
            raise ModelError(f"{w} {r['name']}.setpoint: like \"<= 80\", \">= 1\" or \"== 0\"")
        add(m.controllers, Controller(**common(r, w), holds=str(r.get("holds", "")), setpoint=sp,
                                      tolerance=float(r.get("tolerance", 0)), reads=_names(r.get("reads"), f"{w}.reads"),
                                      drives=_names(r.get("drives"), f"{w}.drives"), agent=r.get("agent")), "controller")
    for i, r in enumerate(rows("agent")):
        w = f"[[agent]] #{i + 1}"
        _take(r, {"name", "kind", "command", "every", "on", "cron", "timeout", "description"}, w)
        kind = r.get("kind", "program")
        if kind not in KINDS:
            raise ModelError(f"{w} {r['name']}.kind: one of {', '.join(KINDS)}")
        if r["name"] in m.agents:
            raise ModelError(f"{w} {r['name']}: the name is already used by an agent")
        cron = r.get("cron")
        if cron is not None:
            from .cron import Cron, CronError
            try:
                Cron(str(cron)).next_after(__import__("time").time())     # one that never matches is refused here
            except CronError as e:
                raise ModelError(f"{w} {r['name']}.cron: {e}") from None
        m.agents[r["name"]] = Agent(r["name"], kind, str(r.get("command", "")),
                                    parse_duration(r.get("every"), f"{w}.every") if r.get("every") is not None else None,
                                    _names(r.get("on"), f"{w}.on"), str(r.get("description", "")),
                                    str(cron) if cron is not None else None,
                                    parse_duration(r["timeout"], f"{w}.timeout") if r.get("timeout") is not None else 300.0)
    for v in m.valves.values():                       # a valve a person fills is manual unless the file says otherwise
        if v.agent in m.agents and m.agents[v.agent].kind == "person" and not v.mode_set:
            v.mode = "manual"
    for i, r in enumerate(rows("system")):
        w = f"[[system]] #{i + 1}"
        _take(r, {"name", "description"}, w)
        m.systems[r["name"]] = System(r["name"], str(r.get("description", "")))
    return m


def find(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / FILE).is_file():
            return d / FILE
    return None


def load(start: Path | None = None) -> Model:
    here = (start or Path.cwd()).resolve()
    path = find(here)
    if path is None:
        raise FileNotFoundError(FILE)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ModelError(f"{path.name}: {e}") from e
    return parse(data, path, default_name=path.parent.name)


# ---- checking what the types alone do not

def check(m: Model) -> list[tuple[str, str]]:
    """(level, message): errors are references that do not resolve; warnings are loops that cannot
    close, parts nothing fills, and agents with nothing to do."""
    out: list[tuple[str, str]] = []

    def err(s):
        out.append(("error", s))

    def warn(s):
        out.append(("warn", s))
    for f in m.flows.values():
        what = "disturbance" if f.disturbance else "flow"
        for end in (f.source, f.target):
            if end is not None and end not in m.stocks:
                err(f"{what} {f.name}: {end!r} is not a stock")
        if f.source is None and f.target is None:
            err(f"{what} {f.name}: it connects nothing: give it from, to, or both")
    for v in m.valves.values():
        if v.flow not in m.flows:
            err(f"valve {v.name}: flow {v.flow!r} is not a flow; declare it: [[flow]] name = \"{v.flow}\" "
                f"with from = (the stock it drains) or to = (the stock it fills)")
        elif m.flows[v.flow].disturbance:
            err(f"valve {v.name}: {v.flow} is a disturbance, which no valve controls; make it a [[flow]]")
    for s in m.sensors.values():
        if s.measures not in m.stocks and s.measures not in m.flows:
            err(f"sensor {s.name}: {s.measures!r} is neither a stock nor a flow; declare it: [[stock]] name = \"{s.measures}\"")
    for c in m.controllers.values():
        for x in c.reads:
            if x not in m.sensors:
                err(f"controller {c.name}: reads {x!r}, which is not a sensor; declare it: [[sensor]] name = \"{x}\" "
                    f"measures = \"{c.holds}\"")
        for x in c.drives:
            if x not in m.valves:
                err(f"controller {c.name}: drives {x!r}, which is not a valve; declare it: [[valve]] name = \"{x}\" "
                    f"flow = (a flow of {c.holds})")
    for t in (m.sensors, m.controllers, m.valves):
        for p in t.values():
            if p.agent and p.agent not in m.agents:
                err(f"{p.kind} {p.name}: agent {p.agent!r} is not an agent; declare it: [[agent]] name = \"{p.agent}\" "
                    f"with a kind and a command")
            if not p.agent:
                warn(f"{p.kind} {p.name}: no agent fills it")
    for f in m.flows.values():
        if f.agent and f.agent not in m.agents:
            err(f"disturbance {f.name}: agent {f.agent!r} is not an agent; declare it, or leave agent out (a load nobody runs)")
    for v in m.valves.values():
        flows = [f for f in m.flows.values() if f.name == v.flow]
        if flows and not any(v.name in c.drives for c in m.controllers.values()):
            warn(f"valve {v.name}: no controller drives it (open loop)")
    for f in m.flows.values():
        if not f.disturbance and m.valve_of(f.name) is None:
            warn(f"flow {f.name}: no valve acts on it; if nothing controls it, declare it a [[disturbance]]")
    if not any(e == "error" for e, _ in out):
        for lp in m.loops():
            for g in lp.gaps:
                warn(f"loop {lp.name}: cannot close: {g}")
    import shlex
    import shutil
    for a in m.agents.values():
        if a.command and a.kind != "person":
            try:
                first = shlex.split(a.command)[0]
            except (ValueError, IndexError):
                first = ""
            base = m.path.parent if m.path else Path.cwd()
            if first in SHELL_WORDS or re.match(r"^[A-Za-z_]\w*=", first):   # a shell line, not one program
                continue
            if not first or not (shutil.which(first) or ("/" in first and (base / first).exists())):
                warn(f"agent {a.name}: {first or 'its command'} not found" + ("" if "/" in first else " on PATH"))
        if not m.roles_of(a.name) and not any(f.agent == a.name for f in m.flows.values()):
            out.append(("note", f"agent {a.name}: fills no role; if it is a load, name it on its disturbance: agent = \"{a.name}\""))
        if a.kind in ("person",) and a.command:
            warn(f"agent {a.name}: a person has no command; ergostat never runs it")
        if a.kind not in ("person",) and a.command and a.every is None and not a.on and not a.cron:
            warn(f"agent {a.name}: has a command but no every, cron or on, so it never runs")
    for s in m.system_names():
        if not m.members(s):
            warn(f"system {s}: selects nothing")
    return out
