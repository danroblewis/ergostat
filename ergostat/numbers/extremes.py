"""Extreme-conditions tests (Sterman, *Business Dynamics*, ch. 21, the extreme-conditions test of
Table 21-4; Forrester and Senge, "Tests for building confidence in system dynamics models", 1980): a
model should behave plausibly however far its inputs and its parameters are pushed, because the real
system does. Each test runs the closed-loop projection (``closedloop.closed``: the goals and built-ins on
the engine's own code, each machine block by its model identified from no record, so each an assumption)
from the model's own start, under one condition held, for many of its slowest time constant, and looks for
what cannot happen in the world it describes:

- a stock drained below empty (no two-way flow can take it there);
- an outflow still running from an empty stock: it takes more than is there;
- a stock fed only from outside that rises while nothing comes in (its inputs at 0, or an inflow whose equation
  is a constant, which no condition can turn off: made from nothing);
- a one-way flow whose equation runs backwards;
- an equation that divides by 0, takes the logarithm or square root of a number out of range, or
  overflows (the projection counts each);
- a run that blows up (a value past 10¹², clamped) or runs away (it grows faster and faster);
- a controller's law with no limits still moving what it sets at the end: it does not saturate.

The conditions, each a change from where the model usually is (every stock at its ``initial:``, else
10 of its unit; every input at its usual level): every stock empty and nothing coming in; nothing coming
in; **each input alone** at 0 and at ``PUSH`` times its largest; **each block that takes items** with a
pool of 0; **each goal's setpoint** at its limits (0, and its stock's ``limit:``, else ``PUSH`` times the
setpoint); and **each parameter alone** that is estimated, a time, or has a ``range:``, at its range's ends,
else at a hundredth and a hundred times its value. An input is a flow from outside the model that no
equation works out and no block moves (it is measured), or an auxiliary from outside; its usual level and
its largest are the record's when the caller has it (``scales``), else its declared rate (a flow, else
``START`` an hour) or ``LEVEL`` (an auxiliary). A flow between two stocks, or out, that no equation works
out and no block moves is held at 0 (or its declared rate). A failure that the model shows with everything
as usual is said once, as that, and not blamed on each condition; every other is said with the condition
that caused it. Each condition's result is kept (``extremes_cache.py``), so only what changed runs again."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

PUSH = 10.0              # an input pushed to the extreme: this many times its largest (and a setpoint with no limit)
LOW, HIGH = 0.01, 100.0  # a parameter with no range pushed to these multiples of its value
START = 10.0             # a stock's level where it has no initial:
LEVEL = 1.0              # an auxiliary from outside, usually
BUCKETS = 48
CONFIRM = 256            # a failure is confirmed with at least this many steps to each of the BUCKETS points
TIMES = 10.0             # the run lasts this many of the slowest time constant met
FIRST = 100.0            # hours: the run's length when nothing in the model has a time constant
RUNAWAY = 10.0           # a stock that ends past this many times its start (or 1), growing faster each quarter, runs away
TOL = 1e-6
FAULT_WORDS = {"divided by 0": "divides by 0", "overflow, or 0 to a negative power": "overflows (or raises 0 to a negative power)",
               "a negative number to a fractional power": "raises a negative number to a fractional power",
               "the logarithm of a number not above 0": "takes the logarithm of a number not above 0",
               "the square root of a negative number": "takes the square root of a negative number",
               "failed to compute": "fails to compute"}


@dataclass
class Condition:
    """One extreme condition: where the stocks start, the inputs set apart from their usual level, the
    parameters set apart from their value, the pools emptied and the setpoints moved, how it is said, and the
    part it pushes (None: the whole model)."""

    key: str
    words: str
    empty: bool = False
    inputs: dict[str, float] = field(default_factory=dict)
    params: dict[str, float] = field(default_factory=dict)
    usual: bool = False                   # everything as usual: what fails here is the model's own, not an input's
    pools: list[str] = field(default_factory=list)
    setpoints: dict[str, float] = field(default_factory=dict)
    part: str | None = None


def inputs_of(spec: Spec, pl: sim.Plan) -> list[str]:
    """The inputs from outside the model the equations read or a stock takes in: inflows from outside no
    equation works out and no block moves, auxiliaries no equation works out."""
    from .blockmodels import actuated
    act = actuated(spec)
    out = [f"flow.{n}" for n, f in sorted(spec.flows.items()) if f.source is None and f"flow.{n}" not in pl.eqs
           and f"flow.{n}" not in act]
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
    ins = inputs_of(spec, pl)
    zero = {r: 0.0 for r in ins if r.startswith("flow.")}
    out = [Condition("usual", "with everything as usual (each input at its usual level)", usual=True),
           Condition("empty", "with every stock empty and nothing coming in", empty=True, inputs=zero),
           Condition("zero", "with nothing coming in from outside", inputs=zero)]
    for r in ins:
        _, big = usual(spec, r, scales)
        out.append(Condition(f"{r}=0", f"with {r} at 0 (the rest as usual)", inputs={r: 0.0}, part=r))
        if big:
            out.append(Condition(f"{r}=push", f"with {r} at {PUSH:g} times its largest ({PUSH * big:.3g}; the rest as usual)",
                                 inputs={r: PUSH * big}, part=r))
    for b in sorted(n for n, b in spec.blocks.items() if b.takes):
        out.append(Condition(f"block.{b}=empty-pool", f"with {b}'s pool at 0 (no run at once; the rest as usual)", pools=[b],
                             part=f"block.{b}"))
    for g, gl in sorted(spec.goals.items()):
        st = spec.stocks.get(gl.of.name) if gl.of.kind == "stock" else None
        hi = st.limit if st is not None and st.limit is not None else PUSH * max(abs(gl.hold.value), 1.0)
        for v, end in ((0.0, "low"), (hi, "high")):
            if v != gl.hold.value:
                out.append(Condition(f"goal.{g}={end}", f"with goal {g}'s setpoint at {v:g} (its {end} limit; the rest as usual)",
                                     setpoints={g: v}, part=f"goal.{g}"))
    for n in pushed(spec, pl):
        p = spec.parameters[n]
        lo, hi = p.range if p.range else (p.value * LOW, p.value * HIGH)
        for v, end in ((lo, "low"), (hi, "high")):
            if v == p.value:
                continue
            how = (f"the {end} end of its range" if p.range else f"{LOW if end == 'low' else HIGH:g} times its value")
            out.append(Condition(f"parameter.{n}={end}", f"with parameter {n} at {_said(p, v)} ({how}; the rest as usual)",
                                 params={n: v}, part=f"parameter.{n}"))
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
        if ref in pl.eqs:                                # worked out; set for a block's model that runs it (closedloop)
            rate = 0.0
        elif f.source is None:                             # an inflow from outside: as usual, or the condition's
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


class _NoRecord:
    """A record with nothing in it: each machine block's model is then an assumption (``blockmodels.identify``)."""

    class events:
        query = staticmethod(lambda *a, **k: [])

    class measurements:
        latest = staticmethod(lambda *a, **k: None)
        range = staticmethod(lambda *a, **k: [])


def _run(spec: Spec, pl: sim.Plan, cond: Condition, scales: dict | None, buckets: int = BUCKETS, fine: int = 0):
    """The closed-loop projection from the model's own start, under ``cond``."""
    from . import closedloop as cl
    slow = _slowest(spec, pl, cond, scales)
    hours = min(max(TIMES * slow, 1e-3), 1e5) if slow else FIRST
    d = _data(spec, pl, 1 / 60, cond, scales, 2)
    models = cl.identify(_NoRecord, spec, ob.Data(d.grid))
    draw = {"models": {r: {"servers": 0} for r, m in models.items() if m.block in cond.pools}}
    at = sim.Run([], {}, {}, [], {r[6:]: v for r, (_, v) in d.started.items()}, {})   # every stock where it starts
    return cl.closed(spec, d, at, hours * 3600.0, pl, buckets, models, cl.Start(), "hold", cl.WhatIf(setpoints=dict(cond.setpoints)),
                     draw, fine=fine)


def _quarters(start: float, vals: list) -> list[float]:
    q = len(vals) // 4
    return [vals[(i + 1) * q - 1] - (vals[i * q - 1] if i else start) for i in range(4)] if q else []


def _failures(spec: Spec, pl: sim.Plan, run, zeros: set, d0: dict) -> dict[tuple[str, str], tuple[float, str]]:
    """What went wrong in one run: (part, what) → (the worst value, the projection's numbers in words)."""
    out: dict[tuple[str, str], tuple[float, str]] = {}
    one_way = {f"flow.{f.name}" for f in spec.flows.values() if not f.two_way}
    h = (run.times[-1] - run.times[0]) / 3600.0 * len(run.times) / max(len(run.times) - 1, 1) if run.times else 0.0

    def low_of(vals):
        vals = [v for v in vals if v is not None]
        low = min(vals, default=0.0)
        return low if low < -TOL * max(1.0, max((abs(v) for v in vals), default=1.0)) else None
    for s in pl.integrate:
        ref, vals = f"stock.{s}", [v for v in run.values.get(f"stock.{s}") or [] if v is not None]
        if not vals:
            continue
        start = d0.get(ref, 0.0)
        said = f"from {start:.3g} to {vals[-1]:.3g} over {h:.3g}h"
        two = any(spec.flows[f[5:]].two_way for f in (*pl.flows_in[s], *pl.flows_out[s]))
        if not two and (low := low_of(vals)) is not None:
            out[(ref, "negative")] = (low, f"{said}, lowest {low:.3g}")
        def rate(f, i):
            v = (run.values.get(f) or [None] * (i + 1))[i]
            return d0.get(f, 0.0) if v is None else v
        w, was = h / max(len(vals), 1), start
        for i, v in enumerate(run.values.get(ref) or []):    # empty, its one-way outflows took more than it held and took in
            ins, outs = sum(rate(f, i) for f in pl.flows_in[s]), [f for f in pl.flows_out[s] if f in one_way]
            took = sum(max(0.0, rate(f, i)) for f in outs)
            held, was = max(0.0, was or 0.0), v
            if v is not None and v <= TOL and took * w > (held + ins * w) * (1 + 1e-3) + TOL:
                for f in outs:
                    out.setdefault((f, "takes-from-empty"), (took, f"{', '.join(x[5:] for x in outs)} at {took:.3g}/h while "
                                                             f"{s} is at {v:.3g} and {ins:.3g}/h comes in"))
                break
        if pl.flows_in[s] and set(pl.flows_in[s]) <= zeros and vals[-1] > start + TOL * max(1.0, abs(start)):
            out[(ref, "rises")] = (vals[-1], said)
        q = _quarters(start, vals)
        if q and q[3] > 2 * q[1] > 0 and q[2] > 0 and vals[-1] > RUNAWAY * max(abs(start), 1.0):
            out[(ref, "runs away")] = (vals[-1], f"{said}, each quarter's rise {', '.join(f'{x:.3g}' for x in q)}")
    for r in pl.eqs:
        if r in one_way and (low := low_of(run.values.get(r) or [])) is not None:
            out[(r, "backwards")] = (low, f"{r[5:]} down to {low:.3g}/h")
    for m in (getattr(run, "models", None) or {}).values():
        vals = run.values.get(f"stock.{m.target}") or [] if m.form == "law" and not m.limits and m.target else []
        q = _quarters(d0.get(f"stock.{m.target}", 0.0), vals) if len(vals) >= 4 else []
        if q and abs(q[3]) > TOL * max(1.0, abs(vals[-1])) and q[3] * q[2] > 0:
            out[(f"block.{m.block}", "winds up")] = (vals[-1], f"its setting, {m.target}, at {vals[-1]:.3g} and still "
                                                     f"moving ({q[3]:+.3g} in the last quarter of {h:.3g}h)")
    for r, got in run.faults.items():
        for what in got:
            out[(r, "fault:" + FAULT_WORDS.get(what, what))] = (0.0, "")
    for n in run.invalid:
        out[(n.split(" ", 1)[0], "blew up")] = (0.0, "")
    return out


def condition_result(spec: Spec, cond: Condition, params: dict | None, scales: dict | None) -> list[list] | None:
    """One condition run: each failure as [part, what, worst, numbers]; None when it could not be run (never kept)."""
    pl = sim.plan(spec, {**(params or {}), **cond.params})
    d = _data(spec, pl, 1 / 60, cond, scales, 2)
    d0 = {r: v[0] for r, v in d.values.items() if v} | {r: v for r, (_, v) in d.started.items()}
    zeros = {r for r in inputs_of(spec, pl) if d0.get(r) == 0.0}    # nothing coming in: inputs at 0, and constants
    zeros |= {f"flow.{n}" for n, f in spec.flows.items() if f.source is None and f.equation and not f.equation.refs}
    try:
        got = _failures(spec, pl, _run(spec, pl, cond, scales), zeros, d0)
        if got:                                          # confirmed with far finer steps: never the step's fault
            fine = _failures(spec, pl, _run(spec, pl, cond, scales, BUCKETS, CONFIRM), zeros, d0)
            got = {k: v for k, v in fine.items() if k in got}
    except (ArithmeticError, ValueError, KeyError, RecursionError):
        return None                                      # a model check cannot run is reported by the checks that refuse it
    return [[r, w, v, said] for (r, w), (v, said) in got.items()]


def merge(spec: Spec, results: list[tuple[Condition, list[list]]]) -> dict[tuple[str, str], dict]:
    """Each implausible thing: (part, what) → the conditions that showed it, in words, the parts they pushed, the
    worst value and the first condition's numbers. What fails as usual is said once, as that."""
    seen: dict[tuple[str, str], dict] = {}
    plain = {(r, w) for c, got in results if c.usual for r, w, _, _ in got}
    for cond, got in results:
        for r, w, v, said in got:
            if (r, w) in plain and not cond.usual:
                continue
            x = seen.setdefault((r, w), {"conditions": [], "causes": [], "worst": v, "numbers": said})
            x["conditions"].append(cond.words)
            x["causes"] += [*cond.inputs, *(f"parameter.{n}" for n in cond.params), *(f"block.{b}" for b in cond.pools),
                            *(f"goal.{g}" for g in cond.setpoints)]
            x["worst"] = max(x["worst"], v, key=abs)
    return seen


def failures(spec: Spec, params: dict[str, float] | None = None, scales: dict | None = None, budget: float | None = None,
             progress=None) -> dict[tuple[str, str], dict]:
    """Each implausible thing the model does under an extreme condition: (part, what) → the conditions that showed
    it, in words, and the worst value. With ``params``, the model with those values (a what-if); ``scales`` are the
    inputs' usual levels and largest from the record (ref → (typical, largest)). Each condition's result comes from
    the cache when the part of the model it reaches is unchanged (``extremes_cache.py``); ``budget`` bounds the
    seconds spent running the rest, and ``progress(done, of)`` is told after each."""
    from . import extremes_cache as xc
    from .blockmodels import has_controllers
    base = sim.plan(spec)
    if not base.eqs and not has_controllers(spec):
        return {}
    return merge(spec, xc.results(spec, conditions(spec, base, scales), params, scales, budget, progress))


def findings(spec: Spec, say, wait: float | None = None) -> dict:
    """Each part that behaves implausibly under an extreme condition, once, with every condition that showed it
    (the input, pool, setpoint or parameter pushed, by name). The conditions run in the background
    (``extremes_cache.background``); ``wait`` seconds at most for them (None: until done). Returns where it is:
    ``{"running", "done", "of", "skipped"}``."""
    from . import extremes_cache as xc
    got, status = xc.background(spec, wait)
    pl = sim.plan(spec)
    for (ref, what), x in got.items():
        say("extreme-conditions", message(spec, pl, ref, what, x), _where(spec, ref), ref)
    return status


def _where(spec: Spec, ref: str):
    kind, _, name = ref.partition(".")
    x = {"stock": spec.stocks, "flow": spec.flows, "block": spec.blocks, "goal": spec.goals}.get(kind, spec.auxiliaries).get(name)
    return (getattr(x, "equation", None) and x.equation.where) or getattr(x, "where", None)


def message(spec: Spec, pl: sim.Plan, ref: str, what: str, x: dict) -> str:
    kind, _, name = ref.partition(".")
    when = "; and ".join(x["conditions"])
    worst = x["worst"]
    seen = f" (the projection, with the loops running: {x['numbers']})" if x.get("numbers") else ""
    if what == "negative":
        outs = ", ".join(f[5:] for f in pl.flows_out.get(name, []) if f in pl.eqs) or "its outflows"
        return (f"stock {name}: {when}, it falls below empty (to {worst:.3g}), so {outs} takes more than is "
                f"there (the extreme-conditions test{seen}). Write the outflow so it stops when the stock is empty: first-order "
                f"in it (stock.{name} / time-in-{name}), or MIN(what it would take, stock.{name} / a time)")
    if what == "takes-from-empty":
        return (f"flow {name}: {when}, it still runs while its stock is empty: it takes more than the stock holds (the "
                f"extreme-conditions test{seen}). Make it stop when its stock is empty: first-order in it, or MIN(…, the stock / a time)")
    if what == "rises":
        return (f"stock {name}: {when}, it rises with nothing coming in (the extreme-conditions test{seen}): with its "
                f"inputs at 0 it should drain, or hold where a loop stops draining it. An inflow is made from nothing: "
                f"a constant inflow is an input from outside (a sensor, or an exogenous auxiliary), not an equation")
    if what == "runs away":
        return (f"stock {name}: {when}, it runs away, growing faster each quarter (the extreme-conditions test{seen}): a "
                f"reinforcing loop with nothing to limit it. Give it a limit: a capacity, or an outflow that grows with it")
    if what == "winds up":
        return (f"block {name}: {when}, its law does not saturate (the extreme-conditions test{seen}): with no limits it "
                f"keeps moving what it sets. Give it limits: [low, high]")
    if what == "backwards":
        return (f"{kind} {name}: {when}, its equation gives a negative rate ({worst:.3g}), and it is a one-way "
                f"flow (the extreme-conditions test{seen}). Wrap it in MAX(0, …), or make it two-way: true if it can run back")
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
