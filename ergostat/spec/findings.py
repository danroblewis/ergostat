"""What ``check`` reports about a model that compiles (SPEC §12's findings): not errors, but the
places where the system is not doing what it seems to say. Some need the record (a stock heading
for its limit, a critical goal decaying); those take a project."""

from __future__ import annotations

from .ir import Ref, Spec
from .load import Problem


def find(spec: Spec) -> list[Problem]:
    out: list[Problem] = []

    def say(code, msg, where, about):
        out.append(Problem("finding", msg, where, code, about))
    for name, g in spec.goals.items():
        lp = spec.loop(name)
        what = g.of
        target = (spec.stocks if what.kind == "stock" else spec.flows).get(what.name)
        has_sensor = bool(target and target.sensors) or (what.kind == "flow" and target and target.rate is not None)
        if not has_sensor:
            say("unjudgeable-goal", f"goal {name}: {what} has no sensor, so nothing can tell whether the goal holds",
                g.where, f"goal.{name}")
        if not lp.actuators and not lp.through:
            serving = [b for b in spec.blocks.values() if any(r.kind == "goal" and r.name == name for r in b.reads())]
            why = (f"{', '.join(b.name for b in serving)} read{'s' if len(serving) == 1 else ''} it, but nothing it commands "
                   f"moves a flow of {what.name}") if serving else "no block reads it"
            say("missing-feedback", f"goal {name}{' (critical)' if g.critical else ''}: missing feedback: {why}", g.where,
                f"goal.{name}")
    for name, b in spec.blocks.items():
        if not b.outputs:
            say("no-visible-effect", f"block {name}: no output, so it has no visible effect: either it does nothing worth "
                f"modelling, or the flow it changes is missing (out: flow.<name>)", b.where, f"block.{name}")
        if b.type == "external":
            continue
        moves = [t for t in b.targets() if t.kind == "flow"]
        commanded = spec.commanders_of(name) or [r for r in b.inputs.values() if r.kind in ("goal", "stock", "flow")]
        if moves and not commanded and spec.role(b) == "actuator":
            say("acting-on-its-own", f"block {name}: moves {', '.join(str(t) for t in moves)} on its own schedule; nothing "
                f"commands it (an open loop)", b.where, f"block.{name}")
        cmd = [c for c in spec.commanders_of(name) if spec.role(c) == "controller"]
        if len(cmd) > 1:
            say("competing-commands", f"block {name}: commanded by {', '.join(c.name for c in cmd)}; put a select in front "
                f"to say how they combine", b.where, f"block.{name}")
    for name, g in spec.goals.items():
        if g.of.kind != "stock":
            continue
        lp = spec.loop(name)
        for a in lp.actuators:
            for t in spec.blocks[a].targets():
                f = spec.flows.get(t.name) if t.kind == "flow" else None
                if f is None or f.name in lp.valves:
                    continue
                if f.target == g.of.name and g.hold.op in ("<=", "<"):
                    say("own-disturbance", f"block {a}: serves goal {name} but also adds to {g.of.name} (flow {f.name}): "
                        f"it is its own disturbance", spec.blocks[a].where, f"block.{a}")
    for st in spec.stocks.values():
        if st.limit is not None and not any(g.of == Ref("stock", st.name) for g in spec.goals.values()):
            say("unguarded-limit", f"stock {st.name}: has a limit ({st.limit:g}) but no goal: nothing keeps it from it",
                st.where, f"stock.{st.name}")
    for s in spec.sensors():
        if not s.measured and not s.manual:
            continue
    return out
