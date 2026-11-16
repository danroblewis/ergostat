"""The model run as a system dynamics model: a replay of the past and a projection ahead.

**Replay** (partial-model replay, as system dynamics calibrates a model: Homer, "Partial-model
testing as a validation tool", 2012; Oliva 2003): from where each stock was first measured, every
stock is integrated from its flows, every flow and auxiliary with an equation is worked out from
it, and everything without an equation (a flow a block moves, a rate a sensor reads, the weather)
is driven by what was measured. So the replay tests exactly the equations the model writes: where
they are right it follows the record, where they are wrong it drifts, and the drift is the fit.

**Projection**: from the state now (the stocks as last measured, each delay as the replay left it),
forward for a horizon, the inputs held where they were (or carried on along their recent trend).

Euler integration with a step a fraction of the smallest time the model names, deterministic.
Time is in hours, as rates are."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .. import series
from ..spec import equation as eq
from ..spec.ir import Equation, Spec

SUBSTEPS = 8                # Euler steps per bucket, at least
MAX_SUBSTEPS = 200
BIG = 1e12


@dataclass
class Grid:
    since: float            # epoch seconds
    until: float
    n: int

    @property
    def width(self) -> float:
        return (self.until - self.since) / self.n

    def times(self) -> list[float]:
        return series.times(self.since, self.until, self.n)


@dataclass
class Data:
    """What was measured, on the grid: every stock's and auxiliary's level and every flow's rate per
    hour (never the rate the residual estimates: that is the model's own guess), and how each is known."""

    grid: Grid
    values: dict[str, list[float | None]] = field(default_factory=dict)
    how: dict[str, str] = field(default_factory=dict)

    def first(self, ref: str) -> int | None:
        return next((i for i, v in enumerate(self.values.get(ref) or []) if v is not None), None)

    def last(self, ref: str) -> float | None:
        return next((v for v in reversed(self.values.get(ref) or []) if v is not None), None)

    def held(self, ref: str) -> list[float | None]:
        """Each bucket's value, the last one before it carried over a bucket with no reading."""
        out, last = [], None
        for v in self.values.get(ref) or []:
            last = v if v is not None else last
            out.append(last)
        return out


def measured(p, grid: Grid) -> Data:
    spec: Spec = p.model.spec
    d = Data(grid)
    for name in (*spec.stocks, *spec.auxiliaries):
        kind = "stock" if name in spec.stocks else "auxiliary"
        d.values[f"{kind}.{name}"] = series.level(p, name, grid.since, grid.until, grid.n)
        d.how[f"{kind}.{name}"] = "measured"
    for name in spec.flows:
        got = series.rate(p, name, grid.since, grid.until, grid.n, changes=False) if name in p.model.flows else None
        d.values[f"flow.{name}"] = got[0] if got else [None] * grid.n
        d.how[f"flow.{name}"] = got[1] if got else "not measured"
    return d


@dataclass
class Plan:
    """What the run works out (equations, in order), integrates (stocks) and takes as given."""

    params: dict[str, float]
    eqs: dict[str, eq.Compiled]
    order: list[str]
    integrate: list[str]
    flows_in: dict[str, list[str]]
    flows_out: dict[str, list[str]]
    left_out: dict[str, str]            # an equation not run, and why (a parameter with no value)
    shortest: float | None              # the shortest time the model names, in hours (the step follows it)


def plan(spec: Spec, params: dict[str, float] | None = None, extra: dict[str, Equation] | None = None,
         extra_params: dict | None = None, integrate: set[str] | None = None) -> Plan:
    """``params`` overrides a parameter's value (an estimate being tried); ``extra`` adds or replaces
    an equation (a proposal being tried), with ``extra_params`` (name → (value, unit)) it names."""
    values = {n: p.value for n, p in spec.parameters.items() if p.value is not None}
    values.update({n: v for n, (v, _) in (extra_params or {}).items()})
    values.update(params or {})
    tables = {n: p.table for n, p in spec.parameters.items() if p.table}
    written: dict[str, Equation] = {f"flow.{f.name}": f.equation for f in spec.flows.values() if f.equation}
    written |= {f"auxiliary.{a.name}": a.equation for a in spec.auxiliaries.values() if a.equation}
    written |= extra or {}
    eqs, left_out = {}, {}
    for ref, e in written.items():
        missing = [n for n in e.parameters if n not in values and n not in tables]
        if missing:
            left_out[ref] = f"{', '.join(missing)} {'has' if len(missing) == 1 else 'have'} no value"
            continue
        eqs[ref] = eq.Compiled(e.tree, tables)
    order: list[str] = []
    seen: set[str] = set()

    def visit(r: str, path: tuple) -> None:
        if r in seen or r in path:
            return
        for d in eq.instant_refs(written[r].tree):
            if d in eqs:
                visit(d, (*path, r))
        seen.add(r)
        order.append(r)
    for r in sorted(eqs):
        visit(r, ())
    stocks = [s for s in spec.stocks if spec.flows_of(s) and (integrate is None or s in integrate)]
    times = [v for n, v in values.items() if v and v > 0 and (spec.parameters.get(n) and spec.parameters[n].unit == "h"
                                                               or (extra_params or {}).get(n, (0, ""))[1] == "h")]
    return Plan(values, eqs, order, stocks,
                {s: [f"flow.{f.name}" for f in spec.flows_of(s) if f.target == s] for s in stocks},
                {s: [f"flow.{f.name}" for f in spec.flows_of(s) if f.source == s] for s in stocks},
                left_out, min(times) if times else None)


@dataclass
class Run:
    """A replay (or a projection): each part's value at each bucket's middle, and how it was known:
    integrated (a stock), worked out (an equation), or given (measured, and taken as it was)."""

    times: list[float]
    values: dict[str, list[float | None]]
    how: dict[str, str]
    notes: list[str]
    state: dict[str, float]             # the stocks at the end
    hidden: dict[str, list[float]]      # each equation's delays at the end
    steps: int = 0


def _substeps(pl: Plan, width_h: float) -> int:
    k = SUBSTEPS
    if pl.shortest:
        k = max(k, math.ceil(width_h / (pl.shortest / 4)))       # the step a quarter of the shortest time named
    return min(k, MAX_SUBSTEPS)


def replay(spec: Spec, data: Data, pl: Plan | None = None) -> Run:
    pl = pl or plan(spec)
    g = data.grid
    n, w = g.n, g.width / 3600.0
    k = _substeps(pl, w)
    dt = w / k
    held = {r: data.held(r) for r in data.values}
    notes: list[str] = [f"{r}: its equation is not run ({why}); it is taken as measured" for r, why in pl.left_out.items()]
    first = {s: data.first(f"stock.{s}") for s in pl.integrate}
    state: dict[str, float | None] = {s: None for s in pl.integrate}
    S = {r: [0.0] * c.slots for r, c in pl.eqs.items()}
    D = {r: [0.0] * c.slots for r, c in pl.eqs.items()}
    started: set[str] = set()
    out: dict[str, list[float | None]] = {f"stock.{s}": [None] * n for s in pl.integrate}
    out |= {r: [None] * n for r in pl.eqs}
    missing: set[str] = set()
    V: dict[str, float] = {}

    def given(r: str, i: int) -> float:
        v = held[r][i] if r in held else None
        if v is None:
            missing.add(r)
            return 0.0
        return v

    def evaluate(i: int) -> None:
        for r in held:
            if r not in pl.eqs:
                V[r] = given(r, i) if not (r.startswith("stock.") and r[6:] in state) else V.get(r, 0.0)
        for s in pl.integrate:
            V[f"stock.{s}"] = state[s] if state[s] is not None else given(f"stock.{s}", i)
        for r in pl.order:
            init = r not in started
            try:
                v = pl.eqs[r].fn(V, pl.params, S[r], D[r], init)
            except (OverflowError, ValueError, ZeroDivisionError):
                v = 0.0
            V[r] = v if -BIG < v < BIG else math.copysign(BIG, v)
            started.add(r)
    steps = 0
    for i in range(n):
        for s in pl.integrate:                       # a stock starts where it was first measured
            if state[s] is None and first[s] is not None and i >= first[s]:
                state[s] = data.values[f"stock.{s}"][first[s]]
        evaluate(i)
        for s in pl.integrate:
            out[f"stock.{s}"][i] = state[s]
        for r in pl.eqs:
            out[r][i] = V[r]
        if i == n - 1:
            break
        for j in range(k):                           # to the next bucket's middle: the first half in this bucket's inputs
            b = i if j < k / 2 else i + 1
            if j:
                evaluate(b)
            for s in pl.integrate:
                if state[s] is None:
                    continue
                d = sum(V[f] for f in pl.flows_in[s]) - sum(V[f] for f in pl.flows_out[s])
                state[s] = max(-BIG, min(BIG, state[s] + dt * d))
            for r in pl.eqs:
                st, dd = S[r], D[r]
                for x in range(len(st)):
                    st[x] += dt * dd[x]
            steps += 1
    used = {r for c in pl.eqs.values() for r in eq.refs(c.tree)}
    used |= {f for s in pl.integrate for f in (*pl.flows_in[s], *pl.flows_out[s]) if f not in pl.eqs}
    notes += [f"{r} was never measured in the window: taken as 0" for r in sorted(missing & used) if data.first(r) is None]
    never = [s for s in pl.integrate if first[s] is None]
    notes += [f"stock.{s} was never measured in the window: nothing to start its replay from" for s in never]
    how = {f"stock.{s}": "integrated" for s in pl.integrate} | {r: "equation" for r in pl.eqs}
    return Run(g.times(), out, how, notes, {s: v for s, v in state.items() if v is not None},
               {r: list(v) for r, v in S.items()}, steps)


def _trend(vals: list[float | None], times: list[float]) -> tuple[float, float] | None:
    """The last value and its slope per hour over the last quarter of the window (least squares)."""
    pts = [(t, v) for t, v in zip(times, vals, strict=True) if v is not None]
    pts = pts[-max(3, len(pts) // 4):]
    if len(pts) < 2:
        return (pts[-1][1], 0.0) if pts else None
    mt = sum(t for t, _ in pts) / len(pts)
    mv = sum(v for _, v in pts) / len(pts)
    var = sum((t - mt) ** 2 for t, _ in pts)
    slope = sum((t - mt) * (v - mv) for t, v in pts) / var if var else 0.0
    return pts[-1][1], slope * 3600.0


def project(spec: Spec, data: Data, run: Run, horizon: float, pl: Plan | None = None, points: int | None = None,
            inputs: str = "hold") -> Run:
    """From now (``data.grid.until``) for ``horizon`` seconds: stocks from their last reading (the
    replay's end where they have none), delays as the replay left them; every input held at its last
    reading (``inputs="hold"``) or carried on along its recent trend (``"trend"``; a one-way flow
    never below 0)."""
    pl = pl or plan(spec)
    g = data.grid
    n = points or max(2, round(horizon / g.width))
    step = horizon / n
    times = [g.until + (i + 1) * step for i in range(n)]
    k = _substeps(pl, step / 3600.0)
    dt = step / 3600.0 / k
    state = {s: (data.last(f"stock.{s}") if data.last(f"stock.{s}") is not None else run.state.get(s)) for s in pl.integrate}
    S = {r: list(run.hidden.get(r) or [0.0] * c.slots) for r, c in pl.eqs.items()}
    D = {r: [0.0] * c.slots for r, c in pl.eqs.items()}
    fresh = {r for r in pl.eqs if not run.hidden.get(r) and pl.eqs[r].slots}
    ts = g.times()
    ahead: dict[str, tuple[float, float]] = {}
    for r, vals in data.values.items():
        tr = _trend(vals, ts)
        if tr is not None:
            ahead[r] = (tr[0], tr[1] if inputs == "trend" else 0.0)
    one_way = {f"flow.{f.name}" for f in spec.flows.values() if not f.two_way}
    V: dict[str, float] = {r: 0.0 for r in data.values}                 # what was never measured is taken as 0, as in the replay
    out: dict[str, list[float | None]] = {f"stock.{s}": [None] * n for s in pl.integrate} | {r: [None] * n for r in pl.eqs}

    def evaluate(t: float) -> None:
        h = (t - g.until) / 3600.0
        for r, (v0, slope) in ahead.items():
            v = v0 + slope * h
            V[r] = max(0.0, v) if r in one_way and v0 >= 0 else v
        for s in pl.integrate:
            V[f"stock.{s}"] = state[s] if state[s] is not None else 0.0
        for r in pl.order:
            try:
                v = pl.eqs[r].fn(V, pl.params, S[r], D[r], r in fresh)
            except (OverflowError, ValueError, ZeroDivisionError):
                v = 0.0
            V[r] = v if -BIG < v < BIG else math.copysign(BIG, v)
            fresh.discard(r)
    t = g.until
    for i in range(n):
        for _ in range(k):
            evaluate(t)
            for s in pl.integrate:
                if state[s] is None:
                    continue
                d = sum(V[f] for f in pl.flows_in[s]) - sum(V[f] for f in pl.flows_out[s])
                state[s] = max(-BIG, min(BIG, state[s] + dt * d))
            for r in pl.eqs:
                for x in range(len(S[r])):
                    S[r][x] += dt * D[r][x]
            t += step / k
        evaluate(t)
        for s in pl.integrate:
            out[f"stock.{s}"][i] = state[s]
        for r in pl.eqs:
            out[r][i] = V[r]
    how = {f"stock.{s}": "integrated" for s in pl.integrate} | {r: "equation" for r in pl.eqs}
    return Run(times, out, how, [f"inputs {'held where they were' if inputs == 'hold' else 'carried on along their trend'}"],
               {s: v for s, v in state.items() if v is not None}, S)
