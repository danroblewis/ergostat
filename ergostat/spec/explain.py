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
           else "is read by a person")
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
        out = [f"{s.name}: {n(len(s.stocks), 'stock')}, {n(len(s.flows), 'flow')}, {n(len(s.goals), 'goal')}, "
               f"{n(len(s.blocks), 'block')} ({', '.join(str(f.name) for f in s.files)})."]
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
            t = (s.stocks if what.kind == "stock" else s.flows)[what.name]
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
            core = f"({b.type}) reads the goal and acts on it itself"
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
        if f.sensors:
            lines.append("  Measured: " + "; ".join(_sensor(x) for x in f.sensors.values()) + " (a rate per hour).")
        return "\n".join(lines)

    def ref(self, text: str) -> str:
        r = Ref.parse(text)
        if r is None:
            for kind, table in (("goal", self.s.goals), ("block", self.s.blocks), ("stock", self.s.stocks),
                                ("flow", self.s.flows)):
                if text in table:
                    r = Ref(kind, text)
                    break
        if r is None:
            raise KeyError(f"no part named {text!r}: name a goal, block, stock or flow (goal.inbox-short, or inbox-short)")
        table = {"goal": self.s.goals, "block": self.s.blocks, "stock": self.s.stocks, "flow": self.s.flows}[r.kind]
        if r.name not in table:
            raise KeyError(f"no {r.kind} {r.name!r}")
        return getattr(self, r.kind)(r.name)


def explain(spec: Spec, what: str | None = None, project=None) -> str:
    e = Explainer(spec, project)
    return e.model() if not what else e.ref(what)
