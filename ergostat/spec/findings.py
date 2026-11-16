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
        target = spec.measured(what.kind).get(what.name)
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
        commanded = spec.commanders_of(name) or [r for r in b.inputs.values() if r.kind in ("goal", "stock", "flow", "auxiliary")]
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
        if not spec.flows_of(st.name):
            say("stock-without-flows", f"stock {st.name}: no flow fills or drains it, so nothing in the model moves it. A "
                f"stock has memory: its value persists, and changes only through its flows. A quantity without memory, "
                f"determined at each moment by others (a ratio, a score), is an auxiliary: give it its flows, or move it "
                f"to auxiliaries:",
                st.where, f"stock.{st.name}")
        if st.limit is not None and not any(g.of == Ref("stock", st.name) for g in spec.goals.values()):
            say("unguarded-limit", f"stock {st.name}: has a limit ({st.limit:g}) but no goal: nothing keeps it from it",
                st.where, f"stock.{st.name}")
    unsigned(spec, say)
    for s in spec.sensors():
        if not s.measured and not s.manual:
            continue
    return out


def unsigned(spec: Spec, say) -> None:
    """The causal links whose sign the model could say and does not (SPEC §12a): what a machine
    block reads, where no goal it serves tells the sign, and an unsigned driven-by. Each makes every
    feedback loop through it of unknown polarity. One finding per part, naming each link."""
    from .causal import input_sign, served
    serves = served(spec)
    for b in spec.blocks.values():
        if b.builtin or b.type == "external" and not b.inputs:
            continue
        bare = [str(r) for port, r in b.inputs.items()
                if r.kind in ("stock", "flow", "auxiliary") and input_sign(spec, b, r, port, serves) is None]
        if bare:
            say("unsigned-link", f"block {b.name}: reads {', '.join(bare)} with no sign, so every feedback loop through "
                f"{'it' if len(bare) == 1 else 'them'} is of unknown polarity: write the sign on each (in: "
                f"+{bare[0]} when {b.name} does more as it rises, -{bare[0]} when less)", b.where, f"block.{b.name}")
    for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for x in table.values():
            bare = [str(r) for r in x.driven_by if str(r) not in x.polarity     # (an exogenous input is in no loop)
                    and not (r.kind == "auxiliary" and r.name in spec.auxiliaries and spec.auxiliaries[r.name].exogenous)]
            if bare:
                say("unsigned-link", f"{kind} {x.name}: driven-by {', '.join(bare)} with no sign, so every feedback loop "
                    f"through {'it' if len(bare) == 1 else 'them'} is of unknown polarity: write the sign on each "
                    f"(+{bare[0]} or -{bare[0]})", x.where, f"{kind}.{x.name}")
