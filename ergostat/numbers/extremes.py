"""Extreme-conditions tests (Sterman, *Business Dynamics*, ch. 21, the extreme-conditions test of
Table 21-4; Forrester and Senge, "Tests for building confidence in system dynamics models", 1980): a
model should behave plausibly however far its inputs and its parameters are pushed, because the real
system does. Each test runs the model's own equations with no record at all, from one condition held,
for many of the model's slowest time constant, and looks for what cannot happen in the world it
describes:

- a stock drained below empty (no two-way flow can take it there): an outflow takes more than is
  there;
- a one-way flow whose equation runs backwards;
- an equation that divides by 0, takes the logarithm or square root of a number out of range, or
  overflows (the replay counts each, ``simulate.py``);
- a run that blows up (a value past 10¹², clamped).

The conditions, each a change from where the model usually is (every stock at its ``initial:``, else
10 of its unit; every input at its usual level): every stock empty and nothing coming in; nothing coming
in; then **each input alone** at 0 and at ``PUSH`` times its largest (zero capacity, workforce or
productivity in a denominator is found this way, and one input's failure is not masked by another's);
and **each parameter alone** that is estimated, a time, or has a ``range:``, at its range's ends, else
at a hundredth and a hundred times its value (a time constant to almost 0 and to almost forever). An
input is a flow from outside the model that no equation works out (it is measured, or a block moves
it), or an auxiliary from outside; its usual level and its largest are the record's when the caller
has it (``scales``), else its declared rate (a flow, else ``START`` an hour) or ``LEVEL`` (an
auxiliary). A flow between two stocks, or out, that no equation works out is held at 0 (or its declared
rate): how it would answer is not written. What a block would do is not simulated (the replay's rule).
A failure that the model shows with everything as usual is said once, as that, and not blamed on each
input; every other is said with the input or parameter that caused it."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

PUSH = 100.0             # an input pushed to the extreme: this many times its largest
LOW, HIGH = 0.01, 100.0  # a parameter with no range pushed to these multiples of its value
START = 10.0             # a stock's level where it has no initial:
LEVEL = 1.0              # an auxiliary from outside, usually
BUCKETS = 48
CONFIRM = 8              # a failure is confirmed on a grid this many times finer, so a step too coarse is not blamed on the model
TIMES = 10.0             # the run lasts this many of the slowest time constant met
FIRST = 100.0            # hours: the run's length when nothing in the model has a time constant
TOL = 1e-6
FAULT_WORDS = {"divided by 0": "divides by 0", "overflow, or 0 to a negative power": "overflows (or raises 0 to a negative power)",
               "a negative number to a fractional power": "raises a negative number to a fractional power",
               "the logarithm of a number not above 0": "takes the logarithm of a number not above 0",
               "the square root of a negative number": "takes the square root of a negative number",
               "failed to compute": "fails to compute"}


@dataclass
class Condition:
    """One extreme condition: where the stocks start, the inputs set apart from their usual level, the
    parameters set apart from their value, and how it is said."""

    key: str
    words: str
    empty: bool = False
    inputs: dict[str, float] = field(default_factory=dict)
    params: dict[str, float] = field(default_factory=dict)
    usual: bool = False                   # everything as usual: what fails here is the model's own, not an input's


def inputs_of(spec: Spec, pl: sim.Plan) -> list[str]:
    """The inputs from outside the model the equations read or a stock takes in: inflows from outside no
    equation works out, auxiliaries no equation works out."""
    out = [f"flow.{n}" for n, f in sorted(spec.flows.items()) if f.source is None and f"flow.{n}" not in pl.eqs]
    out += [f"auxiliary.{n}" for n in sorted(spec.auxiliaries) if f"auxiliary.{n}" not in pl.eqs]
    return out


def usual(spec: Spec, ref: str, scales: dict | None = None) -> tuple[float, float]:
    """An input's usual level and its largest: the record's (``scales``: ref → (typical, largest)), else
    a declared rate, else ``START`` an hour for a flow, ``LEVEL`` for an auxiliary."""
    if scales and ref in scales and scales[ref][1] is not None:
        typ, big = scales[ref]
        return (typ if typ is not None else big), big
    kind, _, name = ref.partition(".")
    if kind == "flow":
        f = spec.flows[name]
        v = f.rate if f.rate is not None else START
        return v, v
    return LEVEL, LEVEL


def pushed(spec: Spec, pl: sim.Plan) -> list[str]:
    """The parameters pushed to their extremes: each an equation uses that is estimated, a time, or has a range."""
    used = {n for c in pl.eqs.values() for n in _names(c)}
    return sorted(n for n, p in spec.parameters.items()
                  if n in used and not p.table and p.value is not None and (p.estimate or p.duration or p.range or p.unit == "h"))


def _names(c) -> set[str]:
    from ..spec import equation as eq
    return set(eq.names(c.tree))


def conditions(spec: Spec, pl: sim.Plan, scales: dict | None = None) -> list[Condition]:
    out = [Condition("usual", "with everything as usual (each input at its usual level)", usual=True),
           Condition("empty", "with every stock empty and nothing coming in", empty=True,
                     inputs={r: 0.0 for r in inputs_of(spec, pl) if r.startswith("flow.")}),
           Condition("zero", "with nothing coming in from outside", inputs={r: 0.0 for r in inputs_of(spec, pl) if r.startswith("flow.")})]
    for r in inputs_of(spec, pl):
        _, big = usual(spec, r, scales)
        out.append(Condition(f"{r}=0", f"with {r} at 0 (the rest as usual)", inputs={r: 0.0}))
        if big:
            out.append(Condition(f"{r}=push", f"with {r} at {PUSH:g} times its largest ({PUSH * big:.3g}; the rest as usual)",
                                 inputs={r: PUSH * big}))
    for n in pushed(spec, pl):
        p = spec.parameters[n]
        lo, hi = p.range if p.range else (p.value * LOW, p.value * HIGH)
        for v, end in ((lo, "low"), (hi, "high")):
            if v == p.value:
                continue
            how = (f"the {end} end of its range" if p.range else f"{LOW if end == 'low' else HIGH:g} times its value")
            out.append(Condition(f"parameter.{n}={end}", f"with parameter {n} at {_said(p, v)} ({how}; the rest as usual)", params={n: v}))
    return out


def _said(p, v: float) -> str:
    if p.duration:
        from ..durations import human
        return human(v * 3600)
    return f"{v:.3g}"


def _data(spec: Spec, pl: sim.Plan, hours: float, cond: Condition, scales: dict | None, buckets: int = BUCKETS) -> ob.Data:
    g = ob.Grid(0.0, hours * 3600.0, buckets)
    d = ob.Data(g)
    n = g.n
    times = g.times()
    for name, s in spec.stocks.items():
        ref = f"stock.{name}"
        level = 0.0 if cond.empty else (s.initial if s.initial is not None else START)
        if name in pl.integrate:
            d.started[ref] = (0.0, level)
        else:                                            # a stock no flow moves: where it is
            d.values[ref], d.at[ref] = [level] * n, list(times)
            d.started[ref] = (0.0, level)
    for name in spec.auxiliaries:
        ref = f"auxiliary.{name}"
        if ref not in pl.eqs:
            v = cond.inputs.get(ref, usual(spec, ref, scales)[0])
            d.values[ref], d.at[ref] = [v] * n, list(times)
            d.started[ref] = (0.0, v)
    for name, f in spec.flows.items():
        ref = f"flow.{name}"
        if ref in pl.eqs:
            continue
        if f.source is None:                             # an inflow from outside: as usual, or the condition's
            rate = cond.inputs.get(ref, usual(spec, ref, scales)[0])
        else:                                            # between stocks, or out: as declared, else held at 0
            rate = f.rate if f.rate is not None else 0.0
        d.values[ref] = [rate] * n
    return d


def _slowest(spec: Spec, pl: sim.Plan, cond: Condition, scales: dict | None) -> float | None:
    """The slowest time constant at the start (hours): each stock's own drain, each delay's time."""
    d = _data(spec, pl, 1.0, cond, scales, 2)
    st = sim._Stepper(pl, pl.integrate)
    for r, vals in d.values.items():
        st.V[r] = vals[0] if vals[0] is not None else 0.0
    state: dict[str, float | None] = {s: d.started[f"stock.{s}"][1] for s in pl.integrate}
    for s, v in state.items():
        st.V[f"stock.{s}"] = v
    try:
        st.evaluate()
        st.rates(state)
    except (ArithmeticError, ValueError):
        return None
    taus = [1.0 / x for x in st.diag.values() if x > 0]
    taus += [sum(1.0 / x for x in c.decay) for c in pl.eqs.values() if c.decay and all(c.decay)]
    return max(taus, default=None)


def _run(spec: Spec, pl: sim.Plan, cond: Condition, scales: dict | None, buckets: int = BUCKETS) -> sim.Run:
    slow = _slowest(spec, pl, cond, scales)
    hours = min(max(TIMES * slow, 1e-3), 1e5) if slow else FIRST
    return sim.replay(spec, _data(spec, pl, hours, cond, scales, buckets), pl)


def _failures(spec: Spec, pl: sim.Plan, run: sim.Run) -> dict[tuple[str, str], float]:
    """What went wrong in one run: (part, what) → the worst value."""
    out: dict[tuple[str, str], float] = {}
    one_way = {f"flow.{f.name}" for f in spec.flows.values() if not f.two_way}

    def low_of(vals):
        vals = [v for v in vals if v is not None]
        low = min(vals, default=0.0)
        return low if low < -TOL * max(1.0, max((abs(v) for v in vals), default=1.0)) else None
    for s in pl.integrate:
        if any(spec.flows[f[5:]].two_way for f in (*pl.flows_in[s], *pl.flows_out[s])):
            continue
        if (low := low_of(run.at_edges.get(f"stock.{s}") or [])) is not None:
            out[(f"stock.{s}", "negative")] = low
    for r in pl.eqs:
        if r in one_way and (low := low_of([*(run.values.get(r) or []), *(run.at_edges.get(r) or [])])) is not None:
            out[(r, "backwards")] = low
    for r, got in run.faults.items():
        for what in got:
            out[(r, "fault:" + FAULT_WORDS.get(what, what))] = 0.0
    for n in run.invalid:
        out[(n.split(" ", 1)[0], "blew up")] = 0.0
    return out


def failures(spec: Spec, params: dict[str, float] | None = None, scales: dict | None = None) -> dict[tuple[str, str], dict]:
    """Each implausible thing the equations do under an extreme condition: (part, what) → the conditions
    that showed it, in words, and the worst value. With ``params``, the model with those values (a what-if);
    ``scales`` are the inputs' usual levels and largest from the record (ref → (typical, largest))."""
    base = sim.plan(spec)
    if not base.eqs:
        return {}
    seen: dict[tuple[str, str], dict] = {}
    plain: set[tuple[str, str]] = set()                  # what it does with everything as usual: its own, said once
    for cond in conditions(spec, base, scales):
        pl = sim.plan(spec, {**(params or {}), **cond.params})
        try:
            got = _failures(spec, pl, _run(spec, pl, cond, scales))
            if got:                                      # confirmed with steps far finer: never the step's fault
                got = {k: v for k, v in _failures(spec, pl, _run(spec, pl, cond, scales, BUCKETS * CONFIRM)).items() if k in got}
        except (ArithmeticError, ValueError, KeyError, RecursionError):
            continue                                     # a model check cannot run is reported by the checks that refuse it
        for k, v in got.items():
            if k in plain:
                continue
            if cond.usual:
                plain.add(k)
            x = seen.setdefault(k, {"conditions": [], "causes": [], "worst": 0.0})
            x["conditions"].append(cond.words)
            x["causes"] += [*cond.inputs, *(f"parameter.{n}" for n in cond.params)]
            x["worst"] = min(x["worst"], v)
    return seen


def findings(spec: Spec, say, scales: dict | None = None) -> None:
    """Each part that behaves implausibly under an extreme condition, once, with every condition that
    showed it (the input or parameter pushed, by name)."""
    pl = sim.plan(spec)
    for (ref, what), x in failures(spec, None, scales).items():
        say("extreme-conditions", message(spec, pl, ref, what, x), _where(spec, ref), ref)


def _where(spec: Spec, ref: str):
    kind, _, name = ref.partition(".")
    x = (spec.stocks if kind == "stock" else spec.flows if kind == "flow" else spec.auxiliaries).get(name)
    return (getattr(x, "equation", None) and x.equation.where) or getattr(x, "where", None)


def message(spec: Spec, pl: sim.Plan, ref: str, what: str, x: dict) -> str:
    kind, _, name = ref.partition(".")
    when = "; and ".join(x["conditions"])
    worst = x["worst"]
    if what == "negative":
        outs = ", ".join(f[5:] for f in pl.flows_out.get(name, []) if f in pl.eqs) or "its outflows"
        return (f"stock {name}: {when}, it falls below empty (to {worst:.3g}), so {outs} takes more than is "
                f"there (the extreme-conditions test). Write the outflow so it stops when the stock is empty: first-order "
                f"in it (stock.{name} / time-in-{name}), or MIN(what it would take, stock.{name} / a time)")
    if what == "backwards":
        return (f"{kind} {name}: {when}, its equation gives a negative rate ({worst:.3g}), and it is a one-way "
                f"flow (the extreme-conditions test). Wrap it in MAX(0, …), or make it two-way: true if it can run back")
    if what == "blew up":
        return (f"{kind} {name}: {when}, the model blows up (a value past 10¹², clamped) (the extreme-conditions test): "
                f"a reinforcing loop with nothing to limit it, or an outflow that cannot keep up")
    return (f"{kind} {name}: {when}, its equation {what[6:]} (the extreme-conditions test): write ZIDZ(a, b) or "
            f"XIDZ(a, b, x) where 0 or x is meant, or MAX(…, a floor) under a logarithm or a root")


def scales_of(data: ob.Data, spec: Spec) -> dict[str, tuple[float | None, float | None]]:
    """Each input's usual level (its median) and its largest |value| in the record."""
    out = {}
    for r, vals in data.values.items():
        got = sorted(abs(v) for v in vals if v is not None)
        if got:
            out[r] = (got[len(got) // 2], got[-1] or None)
    return out
