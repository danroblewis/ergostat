"""``ergostat explain``: the model, or one part of it, in sentences: what it is, what it is
connected to, and (with a project) what it is doing now. Written for a person new to the system,
and for an AI agent asked to change it."""

from __future__ import annotations

from ..durations import human
from .ir import Block, Ref, Spec


def _sp(g, r=None) -> str:
    v = g.hold.value if r is None else r
    tol = f" (give or take {g.tolerance:g})" if g.tolerance else ""
    return f"{g.hold.op} {v:g}{tol}"


def _when(x) -> str:
    if getattr(x, "cron", None):
        return f"on cron {x.cron}"
    if getattr(x, "every", None):
        return f"every {human(x.every)}"
    return ""


def _items(q: dict) -> str:
    where = "".join(f", {k} {'/'.join(map(str, v)) if isinstance(v, list) else v}" for k, v in (q.get("where") or {}).items())
    if q.get("entering") or q.get("leaving"):
        verb = "entering" if q.get("entering") else "leaving"
        return f"counts {q['kind']} items {verb} {q.get('entering') or q.get('leaving')}{where} (per hour, over " \
               f"{human(q.get('over') or 3600)})"
    states = " or ".join(q.get("state") or []) or "any state"
    if q.get("measure") == "oldest":
        return f"reads the hours the oldest {q['kind']} item has been in {states}{where}"
    return f"counts the {q['kind']} items in {states}{where}"


def _sensor(s) -> str:
    how = (f"runs `{s.run}`" if s.run else f"queries {s.query.get('source')}" if s.query else _items(s.items) if s.items
           else "is read by a person" if s.manual else f"is {s.description}" if s.description else "is not read")
    when = _when(s) if not s.manual else ""
    return f"{s.of.kind}.{s.of.name}.{s.name} {how}" + (f" {when}" if when else "")


class Explainer:
    def __init__(self, spec: Spec, project=None):
        self.s, self.p = spec, project
        self.now = None
        if project is not None:
            from .engine import Engine
            e = Engine(project, say=lambda _: None)
            e._initial()
            e.measure()
            self.signals, self.status = e.signals, e.status
            for name, g in spec.goals.items():  # the status as recorded, without recording anything
                y = e.signals.get(str(g.of))
                if y is not None:
                    self.signals[f"goal.{name}.error"] = g.hold.error(y)
        else:
            self.signals, self.status = {}, {}

    def value(self, ref: str) -> str:
        v = self.signals.get(ref)
        return "" if v is None else f"{v:g}"

    def model(self) -> str:
        s = self.s
        def n(k, w):
            return f"{k} {w}{'' if k == 1 else 's'}"
        out = [f"{s.name}: {n(len(s.stocks), 'stock')}, {n(len(s.flows), 'flow')}, "
               + (f"{n(len(s.variables), 'variable')}, " if s.variables else "") + f"{n(len(s.goals), 'goal')}, "
               f"{n(len(s.blocks), 'block')} ({', '.join(str(f.name) for f in s.files)})."]
        if s.systems:
            def walk(parent, depth):
                out_ = []
                for x in s.subsystems(parent):
                    ins = sum(1 for p in s.interface(x) if p["dir"] == "in")
                    outs = sum(1 for p in s.interface(x) if p["dir"] == "out")
                    out_.append(f"{'  ' * depth}- {x}: {ins} in, {outs} out")
                    out_ += walk(x, depth + 1)
                return out_
            out.append("Systems (explain system.NAME for one):")
            out += walk(None, 1)
        if s.items:
            out.append("Items: " + "; ".join(f"{k.name} ({k.id}" + (f": {' → '.join(k.states)}" if k.states else "") + ")"
                                            for k in s.items.values()) + ".")
        for g in s.goals:
            lp = s.loop(g)
            out.append("")
            out.append(self.goal(g, brief=True) + ("" if lp.closes else ""))
        loose = [b for b in s.blocks.values() if not any(b.name in s.loop(g).actuators + s.loop(g).controllers for g in s.goals)]
        if loose:
            out.append("")
            out.append("Blocks serving no goal: " + "; ".join(self.block_line(b) for b in loose) + ".")
        return "\n".join(out)

    def block_line(self, b: Block) -> str:
        outs = ", ".join(str(t) for t in b.targets()) or "nothing"
        when = _when(b)
        return f"{b.name} ({b.type}{', ' + when if when else ''}) → {outs}"

    def goal(self, name: str, brief: bool = False) -> str:
        s, g = self.s, self.s.goals[name]
        lp = s.loop(name)
        what = g.of
        head = f"Goal {name}{' (critical)' if g.critical else ''}: {what} {_sp(g)}."
        lines = [head]
        if g.owner:
            lines.append(f"  Owner: {g.owner}.")
        if lp.sensors:
            t = s.measured(what.kind)[what.name]
            lines.append("  Measured: " + "; ".join(_sensor(x) for x in t.sensors.values()) + ".")
        else:
            lines.append(f"  Nothing measures {what}: nobody can tell whether this goal holds.")
        if lp.controllers:
            parts = []
            for c in lp.controllers:
                b = s.blocks[c]
                desc = self.describe_controller(b)
                parts.append(desc)
            lines.append("  Served: " + "; ".join(parts) + ".")
        if lp.actuators:
            lines.append("  Acting: " + "; ".join(
                f"{a} ({s.blocks[a].type}) moves " + ", ".join(str(t) for t in s.blocks[a].targets() if t.kind == "flow")
                for a in lp.actuators) + ".")
        elif lp.through:
            lines.append("  Closes the long way, through other stocks: " + " → ".join(lp.through) +
                         ". Each stock along it is a queue the loop waits on, so it answers only as fast as they drain.")
        else:
            lines.append("  Missing feedback: nothing ergostat can see acts on it when it is off.")
        if lp.disturbances:
            ds = []
            for f in lp.disturbances:
                setter = s.actuator_of(f)
                ds.append(f"{f}" + (f" (set by {setter.name}, {setter.type})" if setter else
                                    f" (declared {s.flows[f].rate:g}/h)" if s.flows[f].rate is not None else " (unmeasured)"))
            lines.append("  Disturbances: " + ", ".join(ds) + ".")
        if self.p is not None:
            y = self.value(str(what))
            st = self.status.get(name, "unknown")
            if y:
                e = self.signals.get(f"goal.{name}.error")
                lines.append(f"  Now: {what} is {y}; {st}" + (f", error {e:g}" if e else "") + ".")
            else:
                lines.append("  Now: no reading yet.")
        return "\n".join(lines)

    def describe_controller(self, b: Block) -> str:
        targets = ", ".join(t.name for t in b.targets() if t.kind == "block") or ", ".join(str(t) for t in b.targets())
        if b.type == "onoff":
            until = b.params.get("until")
            of = self.s.goals[b.params["goal"]].of
            core = f"runs {targets} while the goal is off, until " + (f"{of} {until}" if until else "it holds")
        elif b.type == "proportional":
            core = f"commands {targets} with {b.params['gain']}× the size of the error"
            if b.params.get("max") is not None:
                core += f", at most {b.params['max']}"
        elif b.type == "expr":
            core = f"computes {b.params['expr']} → {targets}"
        elif any(t.kind == "flow" for t in b.targets()):
            moves = ", ".join(t.name for t in b.targets() if t.kind == "flow")
            core = f"({b.type}) reads it and moves {moves}"
        elif b.machine:
            core = f"a {b.type} that decides for {targets}" + (f" ({_when(b)})" if _when(b) else "")
        else:
            core = f"a {b.type} → {targets}"
        return f"{b.name} {('(implied by ' + targets + ' naming the goal) ') if b.implied else ''}{core}"

    def block(self, name: str) -> str:
        s, b = self.s, self.s.blocks[name]
        role = s.role(b)
        article = "an" if b.type[0] in "aeiou" else "a"
        lines = [f"Block {name}: {article} {b.type} block, {role}" + (f", on agent {b.agent}" if b.agent else "")
                 + (" (implied: ergostat put it there)" if b.implied else "") + "."]
        if b.description:
            lines.append(f"  {b.description}")
        if b.type == "program":
            lines.append(f"  Runs: `{b.params.get('run')}`")
        elif b.type == "ai":
            lines.append(f"  Prompt: {str(b.params.get('prompt'))[:120]}")
        elif b.type == "person":
            lines.append(f"  Asks: {b.params.get('ask')}")
        elif b.type == "external":
            lines.append("  Performed by something ergostat does not run: it is judged by the sensors on what it moves.")
        cmd = s.commanders_of(name)
        if b.goal and b.machine:
            lines.append(f"  Runs while goal {b.goal} is off (through {', '.join(c.name for c in cmd)}).")
        elif cmd:
            lines.append(f"  Commanded by {', '.join(c.name for c in cmd)}: it runs while that is nonzero, once per reading.")
        elif b.machine and _when(b):
            lines.append(f"  Nothing commands it: it runs {_when(b)} (an open loop).")
        if b.inputs:
            lines.append("  Reads: " + ", ".join(f"{r}" + (f" = {self.value(str(r))}" if self.value(str(r)) else "")
                                                for r in b.inputs.values()) + ".")
        if b.targets():
            lines.append("  Outputs to: " + ", ".join(str(t) for t in b.targets()) + ".")
        if b.max is not None:
            lines.append(f"  Its commands are clamped to {b.max:g}.")
        served = [g for g in s.goals if name in s.loop(g).actuators + s.loop(g).controllers]
        if served:
            lines.append(f"  Serves: {', '.join('goal.' + g for g in served)}.")
        if self.p is not None:
            runs = self.p.events.query(n=1, item=name, type="agent.ran")
            if runs:
                d = runs[-1]["data"]
                lines.append(f"  Last run: moved {d.get('moved') or 'nothing'}" +
                             (f" of {d['commanded']:g} commanded" if "commanded" in d else "") + ".")
        return "\n".join(lines)

    def stock(self, name: str) -> str:
        s, st = self.s, self.s.stocks[name]
        lines = [f"Stock {name}" + (f" ({st.unit})" if st.unit else "") + (f": {st.description}" if st.description else "") + "."]
        if st.limit is not None:
            lines.append(f"  It fails at {st.limit:g}.")
        if st.sensors:
            lines.append("  Measured: " + "; ".join(_sensor(x) for x in st.sensors.values()) + ".")
        ins = [f.name for f in s.flows_of(name) if f.target == name]
        outs = [f.name for f in s.flows_of(name) if f.source == name]
        if ins:
            lines.append(f"  Filled by: {', '.join(ins)}.")
        if outs:
            lines.append(f"  Drained by: {', '.join(outs)}.")
        goals = [g for g, x in s.goals.items() if x.of == Ref("stock", name)]
        lines.append(f"  Goals: {', '.join(goals)}." if goals else "  No goal is about it.")
        if self.p is not None and self.value(f"stock.{name}"):
            lines.append(f"  Now: {self.value(f'stock.{name}')}.")
        return "\n".join(lines)

    def variable(self, name: str) -> str:
        s, v = self.s, self.s.variables[name]
        lines = [f"Variable {name}" + (f" ({v.unit})" if v.unit else "") + (f": {v.description}" if v.description else "") + ". "
                 "It is measured or set, and nothing flows into it."]
        setter = s.setter_of(name)
        if setter:
            lines.append(f"  Set by block {setter.name} ({setter.type}): a manipulated variable, a knob.")
        real = [x for x in v.sensors.values() if not (x.name == "set" and setter and not x.measured and not x.manual)]
        if real:
            lines.append("  Measured: " + "; ".join(_sensor(x) for x in real) + ".")
        if v.driven_by:
            lines.append("  It follows " + ", ".join(str(r) for r in v.driven_by) + " (driven-by: declared, not yet checked).")
        readers = [b.name for b in s.blocks.values() if Ref("variable", name) in [Ref(r.kind, r.name) for r in b.reads()]]
        if readers:
            lines.append(f"  Read by: {', '.join(readers)}.")
        goals = [g for g, x in s.goals.items() if x.of == Ref("variable", name)]
        lines.append(f"  Goals: {', '.join(goals)}." if goals else "  No goal is about it.")
        if self.p is not None and self.value(f"variable.{name}"):
            lines.append(f"  Now: {self.value(f'variable.{name}')}.")
        return "\n".join(lines)

    def flow(self, name: str) -> str:
        s, f = self.s, self.s.flows[name]
        ends = f"from {f.source or 'outside'} to {f.target or 'outside'}"
        setter = s.actuator_of(name)
        lines = [f"Flow {name}: {ends}."]
        if setter:
            lines.append(f"  Set by block {setter.name} ({setter.type}).")
        else:
            lines.append("  Nothing in the model sets it: " + (f"a declared rate of {f.rate:g}/h." if f.rate is not None else
                                                               "a disturbance, estimated from what its stocks do."))
        if f.driven_by:
            lines.append("  Its rate follows " + ", ".join(str(r) for r in f.driven_by) + " (driven-by: an influence, declared, "
                         "not yet checked against the record).")
        if f.sensors:
            lines.append("  Measured: " + "; ".join(_sensor(x) for x in f.sensors.values()) + " (a rate per hour).")
        return "\n".join(lines)

    def system(self, name: str) -> str:
        s = self.s
        kids = s.subsystems(name)
        mine = lambda table: [x for x in table.values() if name in s.chain(x.system)]   # noqa: E731
        stocks, goals, blocks = mine(s.stocks), mine(s.goals), [b for b in mine(s.blocks) if not b.implied]
        lines = [f"System {name}" + (f": {s.systems[name]}" if s.systems.get(name) else "") + "."]
        if s.within.get(name):
            lines.append(f"  Within {' → '.join(s.chain(s.within[name]))}.")
        lines.append(f"  Holds {len(stocks)} stocks, {len(goals)} goals, {len(blocks)} blocks" +
                     (f"; systems inside: {', '.join(kids)}" if kids else "") + ".")
        ports = s.interface(name)
        for d, title in (("in", "In"), ("out", "Out")):
            ps = [p for p in ports if p["dir"] == d]
            if not ps:
                lines.append(f"  {title}: nothing" + (" (nothing outside reaches in)" if d == "in" else " (nothing outside sees it)") + ".")
                continue
            lines.append(f"  {title}:")
            for p in ps:
                peers = ", ".join(p["peers"])
                if d == "in":
                    what = (f"{p['part']} reads {peers}" if p["kind"] == "signal" else
                            f"{peers} → {p['part']} ({p['kind']})")
                else:
                    what = (f"{peers} reads {p['part']}" if p["kind"] == "signal" else
                            f"{p['part']} → {peers} ({p['kind']})")
                lines.append(f"    {what}")
        inner = s.inner_loops(name)
        if inner:
            lines.append(f"  Seen from outside, it is an inner loop: it is given a setpoint for {', '.join(inner)} and holds it, "
                         f"and what it holds is read back out. An outer loop can treat it as one block (a cascade).")
        if self.p is not None and goals:
            st = [self.status.get(g.name, "unknown") for g in goals]
            lines.append("  Now: " + ", ".join(f"{st.count(k)} {k}" for k in ("holding", "off", "unknown") if st.count(k)) + ".")
        return "\n".join(lines)

    def ref(self, text: str) -> str:
        if text.startswith("system.") or (text in self.s.systems and Ref.parse(text) is None and not any(
                text in t for t in (self.s.goals, self.s.blocks, self.s.stocks, self.s.flows))):
            name = text.removeprefix("system.")
            if name not in self.s.systems:
                raise KeyError(f"no system {name!r} (systems: {', '.join(sorted(self.s.systems)) or 'none'})")
            return self.system(name)
        r = Ref.parse(text)
        if r is None:
            for kind, table in (("goal", self.s.goals), ("block", self.s.blocks), ("stock", self.s.stocks),
                                ("flow", self.s.flows), ("variable", self.s.variables)):
                if text in table:
                    r = Ref(kind, text)
                    break
        if r is None:
            raise KeyError(f"no part named {text!r}: name a goal, block, stock, flow or variable (goal.inbox-short, or "
                           f"inbox-short)")
        table = {"goal": self.s.goals, "block": self.s.blocks, "stock": self.s.stocks, "flow": self.s.flows,
                 "variable": self.s.variables}[r.kind]
        if r.name not in table:
            raise KeyError(f"no {r.kind} {r.name!r}")
        return getattr(self, r.kind)(r.name)


def explain(spec: Spec, what: str | None = None, project=None) -> str:
    e = Explainer(spec, project)
    return e.model() if not what else e.ref(what)
