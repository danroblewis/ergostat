"""What ``check`` says about a model's numbers (SPEC §7b): an equation's units that disagree, a
declared cause an equation leaves out (its size unknown), a part an equation uses that the diagram
does not draw, a parameter with no value nothing will estimate, and one nothing uses."""

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
            drawn = {f"{r.kind}.{r.name}" for r in x.driven_by}
            for r in e.refs:
                if r not in drawn:
                    say("equation-not-drawn", f"{what}: its equation uses {r}, which its driven-by does not name, so the "
                        f"diagram draws no connector for it and no loop runs through it. Add it with its sign "
                        f"(driven-by: [+{r}])", e.where, f"{kind}.{x.name}")
    for p in spec.parameters.values():
        if p.name not in used:
            say("parameter-unused", f"parameter {p.name}: no equation uses it", p.where, f"parameter.{p.name}")
        elif p.value is None and not p.table and not p.estimate:
            say("parameter-unknown", f"parameter {p.name}: it has no value, and is not to be estimated, so every equation "
                f"using it is left out of the replay: give it a value: (what you believe), or estimate: true (fitted from the "
                f"record)", p.where, f"parameter.{p.name}")
