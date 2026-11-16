"""The compiled model as the objects the status, the page and the diagrams already draw from
(``ergostat.model``), so a YAML project is shown like any other while those move to the new model.

The mapping is SPEC §14 read backwards: a goal on a stock and the blocks serving it become a
controller; a block moving a flow becomes that flow's valve; a flow no block moves is a
disturbance; every block is the agent filling its own role (a built-in is a rule)."""

from __future__ import annotations

from .. import model as mdl
from .ir import Spec, sign_text

KIND = {"program": "program", "ai": "ai", "person": "person", "external": "program"}


def sensor_name(stock_or_flow: str, sensor: str) -> str:
    return f"{stock_or_flow}.{sensor}"


def valve_name(spec: Spec, block: str, flow: str) -> str:
    """A valve is named for its block; a block moving several flows has one valve per flow."""
    flows = [t.name for t in spec.blocks[block].targets() if t.kind == "flow"]
    return block if len(flows) == 1 else f"{block}.{flow}"


def to_model(spec: Spec, problems) -> mdl.Model:
    m = mdl.Model(name=spec.name, path=spec.files[0] if spec.files else None, keep=spec.keep)
    tags = lambda x: spec.chain(x.system)                     # noqa: E731 - its system and every one that is within
    for name, desc in spec.systems.items():
        m.systems[name] = mdl.System(name, desc, spec.within.get(name))
    for st in spec.stocks.values():
        m.stocks[st.name] = mdl.Stock(st.name, st.description, tags(st), unit=st.unit)
    for v in spec.auxiliaries.values():                   # drawn and judged like a stock's level; it has no memory
        setter = spec.setter_of(v.name)
        m.stocks[v.name] = mdl.Stock(v.name, v.description, tags(v), unit=v.unit, auxiliary=True, exogenous=v.exogenous,
                                     setter=setter.name if setter else None, driven_by=[r.name for r in v.driven_by],
                                     polarity={r.name: sign_text(v.polarity[str(r)]) for r in v.driven_by if str(r) in v.polarity})
    for f in spec.flows.values():
        setter = spec.actuator_of(f.name)
        m.flows[f.name] = mdl.Flow(f.name, f.description, tags(f), source=f.source, target=f.target, unit=f.unit,
                                   disturbance=setter is None, rate=f.rate if setter is None else None,
                                   driven_by=[r.name for r in f.driven_by], two_way=f.two_way,
                                   polarity={r.name: sign_text(f.polarity[str(r)]) for r in f.driven_by if str(r) in f.polarity})
    for s in spec.sensors():
        m.sensors[sensor_name(s.of.name, s.name)] = mdl.Sensor(sensor_name(s.of.name, s.name), s.description,
                                                               spec.chain(spec.owner(s.of)),
                                                               measures=s.of.name, agent=None, unit=s.unit,
                                                               implied=s.of.kind == "auxiliary" and s.name == "set"
                                                               and not s.measured and not s.manual)
    for b in spec.blocks.values():
        kind = spec.agents[b.agent].kind if b.agent in spec.agents and spec.agents[b.agent].kind else \
            "rule" if b.builtin else KIND[b.type]
        command = b.params.get("run") or ""
        if b.type == "ai" and not command:
            command = f"(prompt: {str(b.params.get('prompt', ''))[:60]})"
        if b.type == "person":
            command = ""
        m.agents[b.name] = mdl.Agent(b.name, kind, str(command), b.every, [], b.description or
                                     (f"built in: {b.type}" if b.builtin else ""), b.cron, b.timeout, b.params.get("parse"))
        for t in b.targets():
            if t.kind == "flow":
                v = valve_name(spec, b.name, t.name)
                m.valves[v] = mdl.Valve(v, b.description, tags(b), flow=t.name, agent=b.name,
                                        mode="manual" if b.type == "person" else b.mode, max=b.max)
    for g in spec.goals.values():
        if g.of.kind not in ("stock", "auxiliary"):
            continue
        lp = spec.loop(g.name)
        drives = [valve_name(spec, a, t.name) for a in lp.actuators for t in spec.blocks[a].targets()
                  if t.kind == "flow" and t.name in lp.valves]
        if lp.through:                           # the long way: it acts on the first flow along the path
            first = next((p.split(".", 1)[1] for p in lp.through if p.startswith("flow.")), None)
            setter = spec.actuator_of(first) if first else None
            drives = [valve_name(spec, setter.name, first)] if setter else []
        agent = lp.controllers[0] if lp.controllers else None
        m.controllers[g.name] = mdl.Controller(
            g.name, g.description, tags(g), holds=g.of.name, setpoint=str(g.hold), tolerance=g.tolerance,
            reads=[sensor_name(g.of.name, s) for s in spec.measured(g.of.kind)[g.of.name].sensors], drives=drives, agent=agent,
            through=list(lp.through) or ([f"block.{lp.actuators[0]}", f"auxiliary.{g.of.name}"]     # it sets the auxiliary itself
                                         if g.of.kind == "auxiliary" and lp.actuators else []))
    m.spec = spec
    m.problems = problems
    m.files = list(spec.files)
    return m
