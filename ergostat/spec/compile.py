"""From the merged document to the compiled model, refusing what is wrong (SPEC §12's errors), each
error with the file and line it was written at."""

from __future__ import annotations

import re
import time

from ..durations import DurationError, parse_duration
from .ir import BUILTIN, MACHINE, NAME, Agent, Block, Flow, Goal, Ref, Sensor, Setpoint, Source, Spec, Stock
from .load import Document, Map, Problem, Where

COMMON = {"system", "description"}
SENSOR_KEYS = {"run", "query", "manual", "every", "cron", "timeout", "parse", "unit", "description"}
STOCK_KEYS = COMMON | {"unit", "limit", "initial", "sensors", "sensor"}
FLOW_KEYS = COMMON | {"from", "to", "unit", "rate", "sensors", "sensor"}
GOAL_KEYS = COMMON | {"stock", "flow", "hold", "tolerance", "critical", "owner"}
AGENT_KEYS = {"kind", "external", "at-once", "model", "cost", "host", "description"}
AGENT_KINDS = ("person", "ai", "narrow-ai", "decision", "program", "rule")
SOURCE_TYPES = {"prometheus": {"type", "url"}, "command": {"type"}}
BLOCK_COMMON = COMMON | {"type", "in", "out", "role"}
MACHINE_COMMON = {"agent", "max", "min", "timeout", "every", "cron", "mode"}
TYPE_KEYS = {
    "program": MACHINE_COMMON | {"run", "parse"},
    "ai": MACHINE_COMMON | {"prompt", "model", "run", "parse"},
    "person": MACHINE_COMMON | {"ask"},
    "external": {"agent"},
    "onoff": {"goal", "until", "min-on", "min-off"},
    "compare": {"above", "below", "back-above", "back-below"},
    "proportional": {"goal", "gain", "min", "max"},
    "limit": {"min", "max", "rate"},
    "delay": {"delay"},
    "schedule": {"table"},
    "lookup": {"table"},
    "select": {"pick"},
    "expr": {"expr"},
    "timer": {"after"},
    "counter": {"reset"},
    "alarm": {"above", "below", "for"},
}
NEEDS = {"program": ["run"], "ai": ["prompt"], "person": ["ask"], "onoff": ["goal"], "proportional": ["goal", "gain"],
         "delay": ["delay"], "schedule": ["table"], "lookup": ["table"], "select": ["pick"], "expr": ["expr"],
         "timer": ["after"]}
ONE_INPUT = ("compare", "limit", "delay", "lookup", "timer", "counter", "alarm")
KIND_RUNS = {"person": {"person", "external"}, "ai": {"ai", "program", "external"}, "narrow-ai": {"ai", "program", "external"},
             "decision": {"program", "external"}, "program": {"program", "external"}, "rule": {"program", "external"}}


class Compiler:
    def __init__(self, doc: Document):
        self.doc = doc
        self.problems: list[Problem] = list(doc.problems)

    def err(self, msg: str, where: Where | None, code: str = "", about: str = "") -> None:
        self.problems.append(Problem("error", msg, where, code, about))

    # ---- small readers

    def keys(self, m: Map, allowed: set[str], what: str) -> None:
        for k in m:
            if k not in allowed:
                near = [a for a in sorted(allowed) if a[:2] == str(k)[:2]]
                self.err(f"{what}: unknown key {k!r}" + (f" (did you mean {near[0]}?)" if near else
                         f" (known: {', '.join(sorted(allowed))})"), m.at(k), "unknown-key")

    def number(self, m: Map, key: str, what: str, positive: bool = False):
        v = m.get(key)
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, int | float) or (positive and v <= 0):
            self.err(f"{what}.{key}: a number" + (" above 0" if positive else ""), m.at(key), "bad-number")
            return None
        return float(v)

    def duration(self, m: Map, key: str, what: str, default=None):
        v = m.get(key)
        if v is None:
            return default
        try:
            return parse_duration(v, f"{what}.{key}")
        except DurationError as e:
            self.err(f"{e} (like 30s, 5m, 2h, 1d)", m.at(key), "bad-duration")
            return default

    def cron(self, m: Map, key: str, what: str):
        v = m.get(key)
        if v is None:
            return None
        from ..cron import Cron, CronError
        try:
            Cron(str(v)).next_after(time.time())
        except CronError as e:
            self.err(f"{what}.cron: {e}", m.at(key), "bad-cron")
            return None
        return str(v)

    def text(self, m: Map, key: str, default: str = "") -> str:
        v = m.get(key)
        return default if v is None else str(v)

    def ref(self, raw, where: Where | None, what: str, kinds: tuple[str, ...]) -> Ref | None:
        r = Ref.parse(raw)
        if r is None:
            hint = ""
            if isinstance(raw, str) and NAME.match(raw):
                hint = f": write the kind first, like {kinds[0]}.{raw}"
            self.err(f"{what}: {raw!r} is not a reference{hint} (stock.x, flow.x, goal.x, block.x, with an optional .port)",
                     where, "bad-ref")
            return None
        if r.kind not in kinds:
            self.err(f"{what}: {r} is a {r.kind}; here it must be a {' or '.join(kinds)}", where, "wrong-kind")
            return None
        return r

    def refs(self, m: Map, key: str, what: str, kinds: tuple[str, ...]) -> dict[str, list[Ref]]:
        """``in`` or ``out``: one reference, a list, or a map of port → reference (or list)."""
        raw = m.get(key)
        w = m.at(key)
        if raw is None:
            return {}
        if isinstance(raw, str):
            r = self.ref(raw, w, f"{what}.{key}", kinds)
            return {"out" if key == "out" else "in": [r]} if r else {}
        if isinstance(raw, list):
            got = [self.ref(x, w, f"{what}.{key}", kinds) for x in raw]
            got = [g for g in got if g]
            if key == "out":
                return {"out": got} if got else {}
            return {f"in{i + 1}" if len(got) > 1 else "in": [g] for i, g in enumerate(got)}
        if isinstance(raw, dict):
            out = {}
            for port, v in raw.items():
                if not isinstance(port, str) or not NAME.match(port):
                    self.err(f"{what}.{key}: port {port!r}: lowercase letters, digits and -", raw.at(port), "bad-name")
                    continue
                vs = v if isinstance(v, list) else [v]
                got = [self.ref(x, raw.at(port), f"{what}.{key}.{port}", kinds) for x in vs]
                out[port] = [g for g in got if g]
            return out
        self.err(f"{what}.{key}: a reference, a list of them, or a map of port names to them", w, "bad-ref")
        return {}

    # ---- sections

    def sensors(self, owner: Map, of: Ref, what: str) -> dict[str, Sensor]:
        out = {}
        raw = {}
        if "sensor" in owner and "sensors" in owner:
            self.err(f"{what}: sensor: (one) or sensors: (several by name), not both", owner.at("sensor"), "two-sensor-keys")
        if owner.get("sensor") is not None:
            raw = {"main": owner["sensor"]}
            if isinstance(owner["sensor"], Map):
                owner["sensor"].where = owner["sensor"].where or owner.at("sensor")
        elif owner.get("sensors") is not None:
            raw = owner["sensors"]
            if not isinstance(raw, dict):
                self.err(f"{what}.sensors: a map of sensors by name", owner.at("sensors"), "not-a-map")
                return {}
        for name, s in raw.items():
            sw = f"{what} sensor {name}"
            if not isinstance(s, dict):
                self.err(f"{sw}: a map with run:, query: or manual:", owner.at("sensors") or owner.at("sensor"), "not-a-map")
                continue
            if not NAME.match(str(name)):
                self.err(f"{sw}: a name is lowercase letters, digits and -, starting with a letter", s.where, "bad-name")
            self.keys(s, SENSOR_KEYS, sw)
            kinds = [k for k in ("run", "query", "manual") if s.get(k) not in (None, False)]
            if len(kinds) != 1:
                self.err(f"{sw}: exactly one of run:, query: or manual: (it has {', '.join(kinds) or 'none'})", s.where,
                         "sensor-kind")
            q = s.get("query")
            if q is not None:
                if not isinstance(q, dict) or "source" not in q:
                    self.err(f"{sw}.query: a map naming its source: and the source's own fields (promql:)", s.at("query"),
                             "bad-query")
                    q = None
            parse = s.get("parse")
            if parse is not None:
                try:
                    if re.compile(str(parse)).groups != 1:
                        self.err(f"{sw}.parse: one group, around the number: 'cleaned (\\d+)'", s.at("parse"), "bad-parse")
                except re.error as e:
                    self.err(f"{sw}.parse: not a regular expression ({e})", s.at("parse"), "bad-parse")
            out[str(name)] = Sensor(str(name), of, run=s.get("run") and str(s["run"]), query=dict(q) if q else None,
                                    manual=bool(s.get("manual")), every=self.duration(s, "every", sw, 60.0),
                                    cron=self.cron(s, "cron", sw), timeout=self.duration(s, "timeout", sw, 30.0),
                                    parse=str(parse) if parse is not None else None, unit=self.text(s, "unit"),
                                    description=self.text(s, "description"), where=s.where)
        return out

    def named(self, section: str):
        for name, m in self.doc.sections[section].items():
            what = f"{section[:-1]} {name}"
            w = self.doc.defined[(section, name)]
            if not isinstance(name, str) or not NAME.match(name):
                self.err(f"{what}: a name is lowercase letters, digits and -, starting with a letter", w, "bad-name")
                continue
            if not isinstance(m, dict):
                self.err(f"{what}: a map of its keys (block style: one key per line)", w, "not-a-map")
                continue
            if m.where is None:
                m.where = w
            yield name, m, what

    def system(self, section: str, name: str, m: Map) -> str | None:
        return m.get("system") or self.doc.defaults.get((section, name), {}).get("system")

    def run(self) -> Spec:
        d = self.doc
        spec = Spec(d.name, d.root, d.files)
        if d.keep is not None:
            try:
                spec.keep = parse_duration(d.keep, "keep")
            except DurationError as e:
                self.err(str(e), None, "bad-duration")
        for name, m, what in self.named("systems"):
            self.keys(m, {"description"}, what)
            spec.systems[name] = self.text(m, "description")
        for name, m, what in self.named("sources"):
            t = m.get("type")
            if t not in SOURCE_TYPES:
                self.err(f"{what}.type: one of {', '.join(SOURCE_TYPES)}", m.at("type"), "bad-type")
                continue
            self.keys(m, SOURCE_TYPES[t], what)
            if t == "prometheus" and not m.get("url"):
                self.err(f"{what}: a prometheus source needs url:", m.where, "missing-key")
            spec.sources[name] = Source(name, t, self.text(m, "url"), m.where)
        for name, m, what in self.named("stocks"):
            self.keys(m, STOCK_KEYS, what)
            st = Stock(name, self.text(m, "unit"), self.number(m, "limit", what), self.number(m, "initial", what),
                       self.system("stocks", name, m), self.text(m, "description"), where=m.where)
            st.sensors = self.sensors(m, Ref("stock", name), what)
            spec.stocks[name] = st
        for name, m, what in self.named("flows"):
            self.keys(m, FLOW_KEYS, what)
            if m.get("from") is None and m.get("to") is None:
                self.err(f"{what}: give it from:, to:, or both (the stocks it drains and fills; leaving one out means "
                         f"outside the system)", m.where, "flow-without-ends")
            f = Flow(name, m.get("from") and str(m["from"]), m.get("to") and str(m["to"]), self.text(m, "unit"),
                     self.number(m, "rate", what), self.system("flows", name, m), self.text(m, "description"), where=m.where)
            for end, key in ((f.source, "from"), (f.target, "to")):
                if end is not None and end not in d.sections["stocks"]:
                    self.err(f"{what}.{key}: {end!r} is not a stock" + self.suggest(end, d.sections["stocks"]),
                             m.at(key), "unknown-ref", f"stock.{end}")
            f.sensors = self.sensors(m, Ref("flow", name), what)
            spec.flows[name] = f
        for name, m, what in self.named("goals"):
            self.keys(m, GOAL_KEYS, what)
            has = [k for k in ("stock", "flow") if m.get(k) is not None]
            of = None
            if len(has) != 1:
                self.err(f"{what}: say what it is about with exactly one of stock: or flow:", m.where, "goal-of")
            else:
                k = has[0]
                target = str(m[k])
                if target not in d.sections[k + "s"]:
                    self.err(f"{what}.{k}: {target!r} is not a {k}" + self.suggest(target, d.sections[k + "s"]), m.at(k),
                             "unknown-ref", f"{k}.{target}")
                of = Ref(k, target)
            hold = Setpoint.parse(m.get("hold"))
            if hold is None:
                self.err(f"{what}.hold: a setpoint like \"<= 20\", \">= 5\" or \"== 50\", quoted", m.at("hold") or m.where,
                         "bad-setpoint")
            tol = self.number(m, "tolerance", what) or 0.0
            if tol < 0:
                self.err(f"{what}.tolerance: 0 or more", m.at("tolerance"), "bad-number")
            if of and hold:
                spec.goals[name] = Goal(name, of, hold, tol, bool(m.get("critical")), self.text(m, "owner"),
                                        self.system("goals", name, m), self.text(m, "description"), m.where)
        for name, m, what in self.named("agents"):
            self.keys(m, AGENT_KEYS, what)
            kind = m.get("kind")
            if kind is not None and kind not in AGENT_KINDS:
                self.err(f"{what}.kind: one of {', '.join(AGENT_KINDS)}", m.at("kind"), "bad-kind")
                kind = None
            n = m.get("at-once", 1)
            if isinstance(n, bool) or not isinstance(n, int) or n < 1:
                self.err(f"{what}.at-once: a whole number, 1 or more", m.at("at-once"), "bad-number")
                n = 1
            spec.agents[name] = Agent(name, kind, bool(m.get("external")), n, m.get("model") and str(m["model"]),
                                      m.get("cost") and str(m["cost"]), m.get("host") and str(m["host"]),
                                      self.text(m, "description"), m.where)
        for name, m, what in self.named("blocks"):
            b = self.block(name, m, what)
            if b:
                spec.blocks[name] = b
        self.references(spec)
        return spec

    def suggest(self, name: str, among) -> str:
        import difflib
        near = difflib.get_close_matches(name, list(among), n=1)
        return f" (did you mean {near[0]}?)" if near else ""

    def block(self, name: str, m: Map, what: str) -> Block | None:
        t = m.get("type")
        if t not in TYPE_KEYS:
            self.err(f"{what}.type: one of {', '.join(BUILTIN)} (built in) or {', '.join(MACHINE)}"
                     + (f"; it says {t!r}" if t is not None else ""), m.at("type") or m.where, "bad-type")
            return None
        allowed = BLOCK_COMMON | TYPE_KEYS[t]
        for k in m:
            if k in allowed:
                continue
            if t in BUILTIN and k in ("agent", "run", "prompt", "ask"):
                self.err(f"{what}: a built-in block ({t}) is computed by ergostat itself: it has no {k}: (no machine "
                         f"runs it)", m.at(k), "builtin-with-machine")
            elif t == "external" and k in ("run", "prompt", "ask"):
                self.err(f"{what}: an external block is performed by something ergostat does not run, so it has no {k}:",
                         m.at(k), "external-with-run")
            elif k == "model" and t != "ai":
                self.err(f"{what}.model: only an ai block names a model", m.at(k), "model-not-ai")
            else:
                self.keys(_one(m, k), allowed, what)
        for k in NEEDS.get(t, []):
            if m.get(k) is None:
                self.err(f"{what}: a {t} block needs {k}:", m.where, "missing-key")
        if t == "compare" and m.get("above") is None and m.get("below") is None:
            self.err(f"{what}: a compare block needs above: or below:", m.where, "missing-key")
        if t == "alarm" and m.get("above") is None and m.get("below") is None:
            self.err(f"{what}: an alarm needs above: or below:", m.where, "missing-key")
        if t in ("expr", "select") and m.get("in") is None:
            self.err(f"{what}: a {t} block needs in:", m.where, "missing-key")
        mode = m.get("mode", "auto")
        if mode not in ("auto", "advise"):
            self.err(f"{what}.mode: auto or advise", m.at("mode"), "bad-mode")
        role = m.get("role")
        if role is not None and role not in ("controller", "actuator", "logic"):
            self.err(f"{what}.role: controller, actuator or logic", m.at("role"), "bad-role")
        params = {k: v for k, v in m.items() if k in TYPE_KEYS[t] and (t in BUILTIN or k not in MACHINE_COMMON | {"agent"})}
        for k in ("min", "max"):                           # a machine block's limits, or a built-in's clamp
            if m.get(k) is not None:
                self.number(m, k, what)
        for k in ("gain", "above", "below", "back-above", "back-below", "rate"):
            if m.get(k) is not None:
                self.number(m, k, what)
        for k in ("min-on", "min-off", "delay", "after", "reset", "for"):
            if m.get(k) is not None:
                params[k] = self.duration(m, k, what)
        if t == "onoff" and m.get("until") is not None:
            sp = Setpoint.parse(m["until"])
            if sp is None:
                self.err(f"{what}.until: a setpoint like \"<= 15\", quoted", m.at("until"), "bad-setpoint")
            params["until"] = sp
        if t == "select" and m.get("pick") not in (None, "min", "max", "first"):
            self.err(f"{what}.pick: min, max or first", m.at("pick"), "bad-pick")
        if t == "expr" and m.get("expr") is not None:
            from .blocks import ExprError, compile_expr
            try:
                compile_expr(str(m["expr"]))
            except ExprError as e:
                self.err(f"{what}.expr: {e}", m.at("expr"), "bad-expr")
            if m.get("in") is not None and not isinstance(m["in"], dict):
                self.err(f"{what}.in: a map naming each input the expression uses (backlog: stock.backlog)", m.at("in"),
                         "bad-ref")
        if t in ("schedule", "lookup") and m.get("table") is not None:
            from .blocks import TableError, read_table
            try:
                params["table"] = read_table(t, m["table"])
            except TableError as e:
                self.err(f"{what}.table: {e}", m.at("table"), "bad-table")
                params.pop("table", None)
        if t == "ai" and m.get("prompt") is not None:
            p = str(m["prompt"])
            if "\n" not in p and p.endswith((".md", ".txt")) and not (self.doc.root / p).is_file():
                self.err(f"{what}.prompt: {p} is not a file here", m.at("prompt"), "prompt-missing")
        ins = self.refs(m, "in", what, ("stock", "flow", "goal", "block"))
        outs = self.refs(m, "out", what, ("flow", "block", "goal"))
        inputs = {}
        for port, refs in ins.items():
            for r in refs:
                inputs[port] = r
        if t in BUILTIN and any(r.kind == "flow" for rs in outs.values() for r in rs):
            self.err(f"{what}: a built-in block computes a signal; it cannot move a flow. Point it at the block that does "
                     f"(out: block.<worker>)", m.at("out"), "builtin-moves-flow")
        if t in ONE_INPUT and len(inputs) > 1:
            self.err(f"{what}: a {t} block takes one input", m.at("in"), "too-many-inputs")
        if t in ONE_INPUT and not inputs:
            self.err(f"{what}: a {t} block needs in: (the signal it works on)", m.where, "missing-key")
        return Block(name, t, inputs, outs, params, agent=m.get("agent") and str(m["agent"]), role=role,
                     system=self.system("blocks", name, m), description=self.text(m, "description"),
                     every=self.duration(m, "every", what), cron=self.cron(m, "cron", what),
                     timeout=self.duration(m, "timeout", what, 300.0), max=self.number(m, "max", what) if t in MACHINE else None,
                     min=self.number(m, "min", what) if t in MACHINE else None, mode=mode, where=m.where)

    def references(self, spec: Spec) -> None:
        """Every reference resolves, to the right kind of thing; one actuator per flow; no algebraic
        loop among the built-ins; agents can run their blocks; units agree."""
        def exists(r: Ref) -> str | None:
            if r.kind == "stock":
                st = spec.stocks.get(r.name)
                if st is None:
                    return f"{r.name!r} is not a stock" + self.suggest(r.name, spec.stocks)
                if r.port and r.port not in st.sensors:
                    return f"stock {r.name} has no sensor {r.port!r} (it has: {', '.join(st.sensors) or 'none'})"
            elif r.kind == "flow":
                f = spec.flows.get(r.name)
                if f is None:
                    return f"{r.name!r} is not a flow" + self.suggest(r.name, spec.flows)
                if r.port and r.port not in f.sensors:
                    return f"flow {r.name} has no sensor {r.port!r}"
            elif r.kind == "goal":
                if r.name not in spec.goals:
                    return f"{r.name!r} is not a goal" + self.suggest(r.name, spec.goals)
                if r.port not in (None, "error", "off"):
                    return f"a goal's ports are .error and .off ({r} names {r.port!r})"
            elif r.kind == "block":
                b = spec.blocks.get(r.name)
                if b is None:
                    return f"{r.name!r} is not a block" + self.suggest(r.name, spec.blocks)
            return None

        setters: dict[str, str] = {}
        for b in spec.blocks.values():
            what = f"block {b.name}"
            w = b.where
            for r in b.inputs.values():
                if (why := exists(r)) is not None:
                    self.err(f"{what}.in: {why}", w, "unknown-ref", str(r))
                elif r.kind == "block" and r.port:
                    src = spec.blocks[r.name]
                    if src.outputs and r.port not in src.outputs:
                        self.err(f"{what}.in: block {r.name} has no output {r.port!r} (it has: {', '.join(src.outputs)})",
                                 w, "unknown-ref", str(r))
            for r in b.targets():
                if (why := exists(r)) is not None:
                    self.err(f"{what}.out: {why}", w, "unknown-ref", str(r))
                    continue
                if r.kind == "flow":
                    if r.port:
                        self.err(f"{what}.out: a block moves a flow, not its sensor ({r})", w, "wrong-kind")
                    if r.name in setters and setters[r.name] != b.name:
                        self.err(f"{what}.out: flow {r.name} is already set by block {setters[r.name]}; one block sets a "
                                 f"flow (put a select in front, or split the flow)", w, "two-actuators", str(r))
                    setters[r.name] = b.name
                elif r.kind == "goal" and r.port:
                    self.err(f"{what}.out: a block sets a goal's setpoint (goal.{r.name}), not its .{r.port}", w, "wrong-kind")
                elif r.kind == "block" and r.name == b.name:
                    self.err(f"{what}.out: a block cannot command itself", w, "self-command")
            if b.goal and b.goal not in spec.goals:
                self.err(f"{what}.goal: {b.goal!r} is not a goal" + self.suggest(b.goal, spec.goals), w, "unknown-ref",
                         f"goal.{b.goal}")
            if b.agent:
                a = spec.agents.get(b.agent)
                if a is None:
                    if b.type == "external":
                        spec.agents[b.agent] = Agent(b.agent, external=True)     # an external machine, named in passing
                    else:
                        self.err(f"{what}.agent: {b.agent!r} is not an agent; declare it under agents:, or leave agent: out "
                                 f"(the block then runs here, launched by ergostat)", w, "unknown-ref", f"agent.{b.agent}")
                elif a.kind and b.type not in KIND_RUNS[a.kind]:
                    self.err(f"{what}: a {b.type} block cannot run on {b.agent}, which is a {a.kind}", w, "agent-kind")
                elif a.external and b.type != "external":
                    self.err(f"{what}: {b.agent} is external (ergostat never runs it), so its blocks are type: external", w,
                             "agent-external")
        for f in spec.flows.values():
            for end in (f.source, f.target):
                st = spec.stocks.get(end or "")
                if st and f.unit and st.unit and f.unit != st.unit:
                    self.err(f"flow {f.name} is in {f.unit}, but stock {st.name} is in {st.unit}: what moves a stock is "
                             f"counted in its unit", f.where, "units")
            for s in f.sensors.values():
                unit = f.unit or next((spec.stocks[e].unit for e in (f.source, f.target) if e in spec.stocks), "")
                if s.unit and unit and s.unit not in (unit, f"{unit}/h"):
                    self.err(f"flow {f.name} sensor {s.name} reads {s.unit}, but the flow is in {unit} (per hour)", s.where,
                             "units")
        for st in spec.stocks.values():
            for s in st.sensors.values():
                if s.unit and st.unit and s.unit != st.unit:
                    self.err(f"stock {st.name} sensor {s.name} reads {s.unit}, but the stock is in {st.unit}", s.where, "units")
        for s in spec.sensors():
            if s.query and s.query.get("source") not in spec.sources:
                self.err(f"sensor {s.of.name}.{s.name}: source {s.query.get('source')!r} is not under sources:", s.where,
                         "unknown-ref")
            elif s.query and spec.sources[s.query["source"]].type == "prometheus" and not s.query.get("promql"):
                self.err(f"sensor {s.of.name}.{s.name}: a prometheus query needs promql:", s.where, "missing-key")
        self.algebraic(spec)

    def algebraic(self, spec: Spec) -> None:
        """A cycle of built-in blocks with no delay in it has no order to compute in."""
        edges: dict[str, set[str]] = {n: set() for n, b in spec.blocks.items() if b.builtin and b.type != "delay"}
        for n in edges:
            b = spec.blocks[n]
            for t in b.targets():
                if t.kind == "block" and t.name in edges:
                    edges[n].add(t.name)
            for r in b.inputs.values():
                if r.kind == "block" and r.name in edges:
                    edges[r.name].add(n)
        state: dict[str, int] = {}

        def visit(n, path):
            state[n] = 1
            for m in sorted(edges[n]):
                if state.get(m) == 1:
                    cyc = path[path.index(m):] + [m]
                    self.err(f"blocks {' → '.join(cyc)} feed each other with no delay between them (an algebraic loop): "
                             f"put a delay block in the cycle", spec.blocks[m].where, "algebraic-loop")
                    return True
                if state.get(m) is None and visit(m, path + [m]):
                    return True
            state[n] = 2
            return False
        for n in sorted(edges):
            if state.get(n) is None and visit(n, [n]):
                break


def _one(m: Map, k) -> Map:
    one = Map({k: m[k]})
    one.where, one.lines = m.where, {k: m.at(k)}
    return one


def compile_doc(doc: Document) -> tuple[Spec, list[Problem]]:
    c = Compiler(doc)
    spec = c.run()
    return spec, c.problems
