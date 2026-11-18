"""What ``check`` reports about a model that compiles (SPEC §12's findings): not errors, but the
places where the system is not doing what it seems to say. Some need the record (a stock heading
for its limit, a critical goal decaying); those take a project."""

from __future__ import annotations

from .ir import Ref, Spec
from .load import Problem


def find(spec: Spec, extremes: bool = True) -> list[Problem]:
    """Every finding; ``extremes=False`` leaves out the extreme-conditions tests (``late``), which run the
    model's equations many times over (a second or more on a large model) and are wanted only where
    findings are shown."""
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
        commanded = spec.commanders_of(name) or [r for r in b.inputs.values() if r.kind in ("goal", "stock", "flow", "auxiliary")] \
            or b.takes                                   # the items it takes start it: the queue commands it (SPEC §9.5)
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
    structure(spec, say)
    from .equation_checks import findings as numbers
    numbers(spec, say)
    if extremes:
        out += late(spec)
    return out


def late(spec: Spec) -> list[Problem]:
    """The findings that run the model: its extreme-conditions tests (``numbers/extremes.py``)."""
    from ..numbers import extremes
    out: list[Problem] = []
    extremes.findings(spec, lambda code, msg, where, about: out.append(Problem("finding", msg, where, code, about)))
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


# ---- the structure system dynamics asks of a model (SPEC §12): Sterman, *Business Dynamics*, ch. 21's
# structure assessment, dimensional consistency and extreme-condition tests, done on the structure alone

DIMENSIONLESS = {"", "share", "fraction", "ratio", "%", "percent", "1", "points", "score"}


def base_unit(u: str) -> str | None:
    """A unit as a plain count of something, singular, with any per-hour taken off (``alerts/h`` →
    ``alert``); None when it is a ratio, a share or a compound, whose conversion cannot be told."""
    u = (u or "").strip().lower()
    for tail in ("/h", "/hour", " per hour", "/hr"):
        if u.endswith(tail):
            u = u[: -len(tail)].strip()
    if u in DIMENSIONLESS or "/" in u or " per " in u or "*" in u or " " in u:
        return None
    return u[:-1] if u.endswith("s") and len(u) > 3 else u


def unit_of(spec: Spec, r: Ref) -> str:
    x = spec.measured(r.kind).get(r.name)
    if x is None:
        return ""
    if r.kind == "flow" and not x.unit:
        return next((spec.stocks[e].unit for e in (x.source, x.target) if e in spec.stocks), "")
    return x.unit


def _through_a_delay(f) -> set[str]:
    """The causes a flow's equation takes in only through a delay: the delay's own stocks are what lies
    between, so the link is not a rate following a rate at once."""
    from .equation import delayed_refs
    return set(delayed_refs(f.equation.tree)) if f.equation else set()


def _units_said(spec: Spec, f) -> bool:
    """A flow whose equation says, in units that check, how its causes convert into it (a coflow's
    alerts-per-outage)."""
    if f.equation is None:
        return False
    from .equation_checks import units
    got, want, problems = units(spec, "flow", f.name)
    return not problems and got is not None and got == want


def _drains_by_delay(spec: Spec, f) -> bool:
    """An outflow that is a material delay of what flows into its own stock (DELAY3(flow.in, T)): the
    delay's stages hold what is in the stock, so with it empty nothing comes out."""
    if f.equation is None or not f.source:
        return False
    from .equation import delayed_refs
    inflows = {f"flow.{g.name}" for g in spec.flows_of(f.source) if g.target == f.source}
    parts = set(f.equation.refs)
    return bool(parts) and parts <= set(delayed_refs(f.equation.tree, material=True)) and parts <= inflows


def structure(spec: Spec, say) -> None:
    for f in spec.flows.values():
        delayed = _through_a_delay(f)
        rates = [r for r in f.driven_by if r.kind == "flow" and str(r) not in f.instant and f"flow.{r.name}" not in delayed]
        if rates:
            r = rates[0]
            say("rate-driven-by-rate",
                f"flow {f.name}: driven-by {', '.join(str(x) for x in rates)}, a rate following a rate. A connector acts at "
                f"once, so this says {f.name} now depends on {r.name} now. A cause acting over time goes through a stock: "
                f"what {r.name} moves accumulates somewhere (a stock it fills), and {f.name} follows that stock "
                f"(driven-by: +stock.<what accumulates>), or drains it as a flow of its own. If the dependence really is "
                f"immediate ({f.name} changes in the same moment as {r.name}, with nothing between), say so on the link: "
                f"driven-by: [{{cause: +{r}, instant: true}}]",
                f.where, f"flow.{f.name}")
        mine = base_unit(unit_of(spec, Ref("flow", f.name)))
        converted = any(r.kind == "auxiliary" or r == Ref("stock", f.source or "") for r in f.driven_by) or _units_said(spec, f)
        odd = [r for r in f.driven_by if r.kind == "flow" and mine and (b := base_unit(unit_of(spec, r))) and b != mine]
        if odd and not converted:
            r = odd[0]
            u, v = unit_of(spec, Ref("flow", f.name)).split("/")[0].strip(), base_unit(unit_of(spec, r))
            ratio = f"{u}-per-{v}".replace(" ", "-")
            take = (f"; or, since it drains {f.source}, drive it from {f.source} too (driven-by: +stock.{f.source}): "
                    f"then it takes a share of what is there" if f.source else "")
            say("units-mismatch",
                f"flow {f.name}: in {u}, driven-by {r} in {unit_of(spec, r)}, with nothing between that converts one "
                f"into the other. A rate that follows a rate of something else moves so many of its own units for each "
                f"of the other's (a coflow): say how many with an auxiliary (auxiliaries: {{{ratio}: {{unit: {u}/{v}}}}}) "
                f"and drive the flow from both (driven-by: [+{r}, +auxiliary.{ratio}]){take}",
                f.where, f"flow.{f.name}")
        if f.source and f.driven_by and spec.actuator_of(f.name) is None and not f.two_way and not depends_on(spec, f, f.source) \
                and not _drains_by_delay(spec, f):
            say("outflow-ignores-stock",
                f"flow {f.name}: drains {f.source}, but its rate follows {', '.join(str(r) for r in f.driven_by)} and not "
                f"{f.source} itself, so with {f.source} empty it would still run and take it below zero. An outflow "
                f"takes what is there: add the stock to what drives it (driven-by: [+stock.{f.source}, ...])",
                f.where, f"flow.{f.name}")
    for st in spec.stocks.values():
        fl = spec.flows_of(st.name)
        if not fl or st.cumulative:
            continue
        if not any(f.source == st.name or f.two_way for f in fl):
            say("stock-without-outflow",
                f"stock {st.name}: flows fill it ({', '.join(f.name for f in fl)}) and nothing drains it, so in the model "
                f"it can only grow. If what is in it leaves (is finished, expires, is thrown away), give it that outflow "
                f"(flows: {{<name>: {{from: {st.name}}}}}); if it is a running total that by its nature never drains "
                f"(spent so far, kept so far), say so: cumulative: true",
                st.where, f"stock.{st.name}")
    for a in spec.auxiliaries.values():
        if not a.driven_by and not a.exogenous and spec.setter_of(a.name) is None and a.equation is None:
            say("auxiliary-without-causes",
                f"auxiliary {a.name}: nothing drives it and it is not marked as an input from outside, so the model "
                f"cannot say why it changes. Name what it is worked out from (driven-by: [+stock.x, ...]), or, if "
                f"nothing in the model moves it (the weather, a price, a constant), say so: exogenous: true",
                a.where, f"auxiliary.{a.name}")


def depends_on(spec: Spec, f, stock: str, seen: frozenset = frozenset()) -> bool:
    """Whether a flow's rate follows the stock, directly or through an auxiliary that does."""
    for r in f.driven_by:
        if r.kind == "stock" and r.name == stock:
            return True
        if r.kind == "auxiliary" and r.name not in seen and r.name in spec.auxiliaries:
            if depends_on(spec, spec.auxiliaries[r.name], stock, seen | {r.name}):
                return True
    return False
