"""Extreme-conditions tests (Sterman, *Business Dynamics*, ch. 21.4.6; Forrester and Senge, "Tests for
building confidence in system dynamics models", 1980): a model should behave plausibly however far
its inputs are pushed, because the real system does. Each test runs the model's own equations with
no record at all, the inputs from outside set to an extreme and held, for many of the model's slowest
time constant, and looks for what cannot happen in the world it describes:

- a stock drained below empty (no two-way flow can take it there): an outflow takes more than is
  there;
- a one-way flow whose equation runs backwards;
- an equation that divides by 0, takes the logarithm or square root of a number out of range, or
  overflows (the replay counts each, ``simulate.py``);
- a run that blows up (a value past 10¹², clamped).

The conditions: the stocks empty and nothing coming in; nothing coming in, the stocks where they
start (``initial:``, else 10 of their unit); and a million an hour coming in on every inflow from
outside. An input is a flow from outside the model that no equation works out (it is measured, or a
block moves it), or an auxiliary from outside; a flow between two stocks that no equation works out
is held at 0, since how it would answer is not written. Auxiliaries from outside are held at 1.
These say only what the equations do: what a block would do is not simulated (the replay's rule)."""

from __future__ import annotations

from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

HUGE = 1e6               # an inflow pushed to the extreme, per hour
START = 10.0             # a stock's level where it has no initial:
LEVEL = 1.0              # an auxiliary from outside, held
BUCKETS = 48
CONFIRM = 8             # a failure is confirmed on a grid this many times finer, so a step too coarse is not blamed on the model
TIMES = 10.0             # the run lasts this many of the slowest time constant met
FIRST = 100.0            # hours: the run's length when nothing in the model has a time constant
TOL = 1e-6
FAULT_WORDS = {"divided by 0": "divides by 0", "overflow, or 0 to a negative power": "overflows (or raises 0 to a negative power)",
               "a negative number to a fractional power": "raises a negative number to a fractional power",
               "the logarithm of a number not above 0": "takes the logarithm of a number not above 0",
               "the square root of a negative number": "takes the square root of a negative number"}

CONDITIONS = (
    ("empty", "with every stock empty and nothing coming in"),
    ("zero", "with nothing coming in from outside"),
    ("huge", f"with {HUGE:,.0f} an hour coming in on every inflow from outside"),
)


def _data(spec: Spec, pl: sim.Plan, hours: float, condition: str, buckets: int = BUCKETS) -> ob.Data:
    g = ob.Grid(0.0, hours * 3600.0, buckets)
    d = ob.Data(g)
    n = g.n
    times = g.times()
    for name, s in spec.stocks.items():
        ref = f"stock.{name}"
        level = 0.0 if condition == "empty" else (s.initial if s.initial is not None else START)
        if name in pl.integrate:
            d.started[ref] = (0.0, level)
        else:                                            # a stock no flow moves: where it is
            d.values[ref], d.at[ref] = [level] * n, list(times)
            d.started[ref] = (0.0, level)
    for name in spec.auxiliaries:
        ref = f"auxiliary.{name}"
        if ref not in pl.eqs:
            d.values[ref], d.at[ref] = [LEVEL] * n, list(times)
            d.started[ref] = (0.0, LEVEL)
    for name, f in spec.flows.items():
        ref = f"flow.{name}"
        if ref in pl.eqs:
            continue
        if f.source is None:                             # an inflow from outside: the condition
            rate = HUGE if condition == "huge" else 0.0
        else:                                            # between stocks, or out: as declared, else held at 0
            rate = f.rate if f.rate is not None else 0.0
        d.values[ref] = [rate] * n
    return d


def _slowest(spec: Spec, pl: sim.Plan, condition: str) -> float | None:
    """The slowest time constant at the start (hours): each stock's own drain, each delay's time."""
    d = _data(spec, pl, 1.0, condition, 2)
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


def _run(spec: Spec, pl: sim.Plan, condition: str, buckets: int = BUCKETS) -> sim.Run:
    slow = _slowest(spec, pl, condition)
    hours = min(max(TIMES * slow, 1e-3), 1e5) if slow else FIRST
    return sim.replay(spec, _data(spec, pl, hours, condition, buckets), pl)


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
    for r, c in pl.eqs.items():
        for what in c.faults:
            out[(r, "fault:" + FAULT_WORDS.get(what, what))] = 0.0
    for n in run.invalid:
        out[(n.split(" ", 1)[0], "blew up")] = 0.0
    return out


def findings(spec: Spec, say) -> None:
    """Each part that behaves implausibly under an extreme condition, once, with every condition that
    showed it."""
    pl = sim.plan(spec)
    if not pl.eqs:
        return
    seen: dict[tuple[str, str], list[str]] = {}
    worst: dict[tuple[str, str], float] = {}

    def note(ref: str, what: str, cond: str, value: float = 0.0) -> None:
        k = (ref, what)
        seen.setdefault(k, [])
        if cond not in seen[k]:
            seen[k].append(cond)
        worst[k] = min(worst.get(k, 0.0), value)
    for cond, words in CONDITIONS:
        try:
            got = _failures(spec, pl, _run(spec, pl, cond))
            if got:                                      # confirmed with steps far finer: never the step's fault
                got = {k: v for k, v in _failures(spec, pl, _run(spec, pl, cond, BUCKETS * CONFIRM)).items() if k in got}
        except (ArithmeticError, ValueError, KeyError, RecursionError):
            continue                                     # a model check cannot run is reported by the checks that refuse it
        for (ref, what), v in got.items():
            note(ref, what, words, v)
    for (ref, what), conds in seen.items():
        kind, _, name = ref.partition(".")
        x = (spec.stocks if kind == "stock" else spec.flows if kind == "flow" else spec.auxiliaries).get(name)
        where = (getattr(x, "equation", None) and x.equation.where) or getattr(x, "where", None)
        when = "; and ".join(conds)
        if what == "negative":
            outs = ", ".join(f[5:] for f in pl.flows_out.get(name, []) if f in pl.eqs) or "its outflows"
            msg = (f"stock {name}: {when}, it falls below empty (to {worst[(ref, what)]:.3g}), so {outs} takes more than is "
                   f"there (the extreme-conditions test). Write the outflow so it stops when the stock is empty: first-order "
                   f"in it (stock.{name} / time-in-{name}), or MIN(what it would take, stock.{name} / a time)")
        elif what == "backwards":
            msg = (f"{kind} {name}: {when}, its equation gives a negative rate ({worst[(ref, what)]:.3g}), and it is a one-way "
                   f"flow (the extreme-conditions test). Wrap it in MAX(0, …), or make it two-way: true if it can run back")
        elif what == "blew up":
            msg = (f"{kind} {name}: {when}, the model blows up (a value past 10¹², clamped) (the extreme-conditions test): "
                   f"a reinforcing loop with nothing to limit it, or an outflow that cannot keep up")
        else:
            msg = (f"{kind} {name}: {when}, its equation {what[6:]} (the extreme-conditions test): write ZIDZ(a, b) or "
                   f"XIDZ(a, b, x) where 0 or x is meant, or MAX(…, a floor) under a logarithm or a root")
        say("extreme-conditions", msg, where, ref)
