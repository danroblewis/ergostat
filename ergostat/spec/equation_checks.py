"""What ``check`` says about a model's numbers (SPEC §7b): an equation's units that disagree, a
declared cause an equation leaves out (its size unknown), a cause whose effect in the equation has
the other sign from the one drawn (link polarity is the sign of the partial derivative, Sterman
ch. 5.2), a part an equation uses that the diagram does not draw, a parameter with no value nothing
will estimate, and one nothing uses."""

from __future__ import annotations

from . import equation as eq
from .ir import Ref, Spec


def expected_unit(spec: Spec, kind: str, name: str) -> str | None:
    """What an equation for this part must come out in: a flow's unit per hour, an auxiliary's unit."""
    from .findings import unit_of
    u = unit_of(spec, Ref(kind, name))
    if not u:
        return None
    return f"{u}/h" if kind == "flow" else u


def unit_of_ref(spec: Spec, ref: str) -> dict | None:
    kind, _, name = ref.partition(".")
    u = expected_unit(spec, kind, name)
    return None if u is None else eq.unit(u)


def unit_of_parameter(spec: Spec, name: str) -> dict | None:
    p = spec.parameters.get(name)
    return eq.unit(p.unit) if p is not None and p.unit else None


def units(spec: Spec, kind: str, name: str) -> tuple[dict | None, dict | None, list[str]]:
    """An equation's unit as worked out, the unit it must have, and where its units disagree."""
    x = spec.measured(kind)[name]
    got, problems = eq.units_of(x.equation.tree, lambda r: unit_of_ref(spec, r), lambda n: unit_of_parameter(spec, n),
                                lambda n: unit_of_parameter(spec, n))
    want = expected_unit(spec, kind, name)
    return got, (None if want is None else eq.unit(want)), problems


SIGN_POINTS = (0.25, 0.5, 1.0, 2.0, 4.0, 10.0, 50.0)     # where each cause's effect is tried, every part at once


def signs(spec: Spec, x) -> dict[str, set[int]]:
    """For each part an equation names, the signs of its partial derivative (∂y/∂x, by central
    differences) across a range of operating points: every part at each value of SIGN_POINTS, the
    parameters at their values (1 where they have none), each delay in equilibrium with its input."""
    e = x.equation
    tables = {n: p.table for n, p in spec.parameters.items() if p.table}
    params = {n: (p.value if p.value is not None else 1.0) for n, p in spec.parameters.items()}
    c = eq.Compiled(e.tree, tables)
    out: dict[str, set[int]] = {r: set() for r in e.refs}

    def at(V):
        try:
            return c.fn(V, params, [0.0] * c.slots, [0.0] * c.slots, True)
        except (ArithmeticError, ValueError, KeyError):
            return None
    for v in SIGN_POINTS:
        base = {r: v for r in e.refs}
        for r in e.refs:
            h = 1e-4 * max(1.0, abs(v))
            up, down = at({**base, r: v + h}), at({**base, r: v - h})
            if up is None or down is None:
                continue
            d = (up - down) / (2 * h)
            if abs(d) > 1e-9 * max(1.0, abs(up), abs(down)):
                out[r].add(1 if d > 0 else -1)
    return out


def findings(spec: Spec, say) -> None:
    used: set[str] = set()
    for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for x in table.values():
            e = x.equation
            if e is None:
                continue
            what = f"{kind} {x.name}"
            used |= set(e.parameters)
            got, want, problems = units(spec, kind, x.name)
            for p in problems:
                say("equation-units", f"{what}.equation: {p}. Each term of a sum is counted in one unit; a parameter's unit "
                    f"says how it converts (unit: alerts/ramp)", e.where, f"{kind}.{x.name}")
            if not problems and got is not None and want is not None and got != want:
                say("equation-units", f"{what}.equation comes out in {eq.unit_text(got)}, but {x.name} is in "
                    f"{eq.unit_text(want)}{' (a flow is a rate per hour)' if kind == 'flow' else ''}: a parameter's unit is "
                    f"missing a factor, or one is wrong", e.where, f"{kind}.{x.name}")
            named = set(e.refs)
            for r in x.driven_by:
                if str(r) not in named and not (r.port and f"{r.kind}.{r.name}" in named):
                    say("size-unknown", f"{what}: driven-by {r}, and its equation does not use it: the link is drawn, with "
                        f"its sign, and its size is not known (the equation says {r.name} has no effect). Write it into the "
                        f"equation, or take the link away if it has none", e.where, f"{kind}.{x.name}")
            pol = getattr(x, "polarity", {}) or {}
            if pol:
                found = signs(spec, x)
                for r in x.driven_by:
                    ref = f"{r.kind}.{r.name}"
                    want = pol.get(str(r), pol.get(ref))
                    got = found.get(ref) or set()
                    if want is None or not got or got == {want}:
                        continue
                    drawn_as = "+" if want > 0 else "-"
                    if got == {-want}:
                        say("equation-sign", f"{what}: driven-by {drawn_as}{ref}, but its equation moves it the other way "
                            f"(∂{x.name}/∂{r.name} is {'negative' if want > 0 else 'positive'} wherever it was tried), so every "
                            f"loop drawn through the link has the wrong polarity. Correct the sign in driven-by, or the "
                            f"equation", e.where, f"{kind}.{x.name}")
                    else:
                        say("equation-sign", f"{what}: driven-by {drawn_as}{ref}, and its equation's effect changes sign "
                            f"across the range tried (∂{x.name}/∂{r.name} is positive somewhere and negative elsewhere), so "
                            f"the link has no one polarity: leave its sign off (driven-by: {ref}), or write the equation "
                            f"so it has one", e.where, f"{kind}.{x.name}")
            if kind == "flow" and x.source:
                own = f"stock.{x.source}"
                for n in eq.walk(e.tree):
                    if n[0] == "fn" and n[1] in ("DELAY1", "DELAY3") and own in eq.refs(n[2][0]):
                        say("delay-drains-late", f"{what}: {n[1]}({eq.text(n[2][0])}, ...) takes from {x.source} what its "
                            f"level called for a delay ago, not what is there now, so {x.source} drains late and can be "
                            f"driven below empty. A material delay is what leaves at once arriving later: let {x.name} take "
                            f"{eq.text(n[2][0])} from {x.source} at once, and a flow into "
                            f"{x.target or 'the next stock'} of {n[1]}(flow.{x.name}, its time)", e.where, f"flow.{x.name}")
                        break
            drawn = {f"{r.kind}.{r.name}" for r in x.driven_by}
            for r in e.refs:
                if r not in drawn:
                    say("equation-not-drawn", f"{what}: its equation uses {r}, which its driven-by does not name, so the "
                        f"diagram draws no connector for it and no loop runs through it. Add it with its sign "
                        f"(driven-by: [+{r}])", e.where, f"{kind}.{x.name}")
    for p in spec.parameters.values():
        if p.range and p.value is not None and not p.range[0] <= p.value <= p.range[1]:
            say("parameter-range", f"parameter {p.name}: its value ({p.value:g}) is outside its range ({p.range[0]:g} to "
                f"{p.range[1]:g}), so what it is believed to be and what it might be disagree. Widen the range, or "
                f"correct the value", p.where, f"parameter.{p.name}")
        if p.name not in used:
            say("parameter-unused", f"parameter {p.name}: no equation uses it", p.where, f"parameter.{p.name}")
        elif p.value is None and not p.table and not p.estimate:
            say("parameter-unknown", f"parameter {p.name}: it has no value, and is not to be estimated, so every equation "
                f"using it is left out of the replay: give it a value: (what you believe), or estimate: true (fitted from the "
                f"record)", p.where, f"parameter.{p.name}")
