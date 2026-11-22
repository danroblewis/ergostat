"""The model run as a system dynamics model: a replay of the past and a projection ahead.

**Replay** (Homer, "Partial-model testing as a validation tool", 2012; Oliva 2003): every stock with
flows is integrated from its flows, from the moment it was first read; every flow and auxiliary with
an equation is worked out; everything without one (a flow a block moves, a rate a sensor reads, the
weather) is driven by what was measured, on the accounting basis of ``observe.py`` (counted flows by
what moved, when it moved). So the replay tests exactly the equations the model writes: where they
are right it follows the record, where they are wrong it drifts, and the drift is the fit. With
``integrate=set()`` no stock is integrated: every input is as measured, and each equation is judged
on its own (the partial-model test proper).

**The step** follows the model's own dynamics, never the units its parameters are written in
(Sterman, *Business Dynamics*, app. A: a step of a quarter to a tenth of the shortest time
constant). At each bucket the replay works out how fast each stock answers itself and the others
(|∂net flow/∂stock|, by finite differences of the compiled equations at the operating point, bounded
by Gershgorin's circles) and takes a step a quarter of the fastest. A delay whose stages (T/order)
drain faster than that is stepped through each step in smaller steps of its own, so what leaves its
stages is exactly what its flow moves. When a stock would need more than ``MAX_SUBSTEPS`` steps a
bucket, its own drain is integrated implicitly (linearly implicit Euler), which settles what is
faster than a step at once and stays stable, and the run's notes say so; a run whose coupling
between stocks is too fast for its step, or that hit the clamp, is marked not valid.

**Projection**: open loop. From the state now (each stock as it was last read, averaged over its
last few readings; each delay as the replay left it), forward for a horizon, the inputs held where
they were (or carried on along their recent trend). The blocks are not simulated: a flow a
controller sets is held like any other input, so what lies downstream of one is left out.

Time is in hours, as rates are; deterministic."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..spec import equation as eq
from ..spec.ir import Equation, Spec
from .observe import Data, Grid, measured  # noqa: F401  (the replay's inputs, and where they come from)

SUBSTEPS = 8                # Euler steps per bucket, at least (even)
MAX_SUBSTEPS = 256          # ... and at most: past it, a stock faster than that settles at once (implicitly)
QUARTER = 4                 # a step is at most a quarter of the shortest time constant
MICRO = 1000                # a delay faster than its step is stepped within it, at most this many times
BIG = 1e12                  # a value beyond this is clamped, and the run is not valid


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


def plan(spec: Spec, params: dict[str, float] | None = None, extra: dict[str, Equation] | None = None,
         extra_params: dict | None = None, integrate: set[str] | None = None, given: set[str] | None = None) -> Plan:
    """``params`` overrides a parameter's value (an estimate being tried); ``extra`` adds or replaces
    an equation (a proposal being tried), with ``extra_params`` (name → (value, unit)) it names;
    ``integrate`` limits the stocks integrated (``set()``: none, the partial-model test); ``given`` are
    parts whose equations are not run, taken as measured (a system calibrated alone: what comes in from
    outside it is what was measured)."""
    values = {n: p.value for n, p in spec.parameters.items() if p.value is not None}
    values.update({n: v for n, (v, _) in (extra_params or {}).items()})
    values.update(params or {})
    tables = {n: p.table for n, p in spec.parameters.items() if p.table}
    written: dict[str, Equation] = {f"flow.{f.name}": f.equation for f in spec.flows.values() if f.equation}
    written |= {f"auxiliary.{a.name}": a.equation for a in spec.auxiliaries.values() if a.equation}
    written |= extra or {}
    eqs, left_out = {}, {}
    for ref in given or ():
        written.pop(ref, None)
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
    return Plan(values, eqs, order, stocks,
                {s: [f"flow.{f.name}" for f in spec.flows_of(s) if f.target == s] for s in stocks},
                {s: [f"flow.{f.name}" for f in spec.flows_of(s) if f.source == s] for s in stocks},
                left_out)


@dataclass
class Run:
    """A replay (or a projection): each part's value at each bucket's middle and at its edges, what
    each equation's flow moved in each bucket, and how each was known: integrated (a stock), worked
    out (an equation), or given (measured, and taken as it was)."""

    times: list[float]
    values: dict[str, list[float | None]]
    how: dict[str, str]
    notes: list[str]
    state: dict[str, float]             # the stocks at the end
    hidden: dict[str, list[float]]      # each equation's delays at the end
    steps: int = 0
    edges: list[float] = field(default_factory=list)
    at_edges: dict[str, list[float | None]] = field(default_factory=dict)
    moved: dict[str, list[float | None]] = field(default_factory=dict)
    invalid: list[str] = field(default_factory=list)        # why the run is not to be trusted, when it is not
    at_reading: dict[str, list[float | None]] = field(default_factory=dict)   # each stock at its bucket's reading's moment
    time_constants: dict[str, float] = field(default_factory=dict)   # hours: each stock's, each delayed equation's
    started: dict[str, float] = field(default_factory=dict)          # when each stock's replay started
    fastest: float | None = None         # the fastest rate it met, per hour (its step followed it)
    faults: dict[str, dict[str, int]] = field(default_factory=dict)  # each equation's faults, each taken as 0: what, how often
    trace: list[tuple[int, dict[str, float | None]]] = field(default_factory=list)   # (bucket, values) at each step, when asked

    @property
    def valid(self) -> bool:
        return not self.invalid

    def value_at(self, ref: str, t: float) -> float | None:
        """A part's value at a moment, between the edges by a straight line."""
        vals = self.at_edges.get(ref)
        if not vals or not self.edges or t < self.edges[0] or t > self.edges[-1]:
            return None
        w = (self.edges[-1] - self.edges[0]) / (len(self.edges) - 1)
        i = min(int((t - self.edges[0]) / w), len(self.edges) - 2)
        a, b = vals[i], vals[i + 1]
        if a is None or b is None:
            return b if a is None else a
        return a + (b - a) * (t - self.edges[i]) / w


class _Stepper:
    """The arithmetic a replay and a projection share: equations worked out at the moment's values,
    the stocks' and delays' rates, the step those rates allow, and one step."""

    def __init__(self, pl: Plan, stocks: list[str]):
        self.pl = pl
        self.stocks = stocks
        self.V: dict[str, float] = dict.fromkeys(pl.eqs, 0.0)     # a delay's equilibrium may read one not worked out yet
        self.S = {r: [0.0] * c.slots for r, c in pl.eqs.items()}
        self.D = {r: [0.0] * c.slots for r, c in pl.eqs.items()}
        self.fresh = set(pl.eqs)
        self.errors: dict[str, int] = {}
        self.clamped: dict[str, int] = {}
        read = {r for c in pl.eqs.values() for r in eq.refs(c.tree)}
        self.felt = [s for s in stocks if f"stock.{s}" in read]          # stocks an equation reads: they answer themselves
        self.diag: dict[str, float] = {s: 0.0 for s in stocks}
        self.coupling = 0.0
        self.advanced: set[str] = set()     # delays already stepped through this step (evaluate, with dt)
        self.coarse = 0.0                   # the fastest delay that needed more than MICRO steps in one

    def evaluate(self, dt: float | None = None) -> None:
        """Every equation at the moment's values. With ``dt``, the step about to be taken: a delay whose
        stages drain faster than a quarter of it is stepped through it in smaller steps of its own, its
        input held, and gives the mean of what came out (so what leaves its stages is exactly what its
        flow moves: nothing is made or lost)."""
        V, P = self.V, self.pl.params
        for r in self.pl.order:
            init = r in self.fresh
            c, S, D = self.pl.eqs[r], self.S[r], self.D[r]
            fast = max(c.decay) if (dt and c.decay and not init) else 0.0
            try:
                if fast and fast * dt > 1.0 / QUARTER:
                    m = math.ceil(fast * dt * QUARTER)
                    if m > MICRO:
                        self.coarse = max(self.coarse, fast)
                        m = MICRO
                    h, acc = dt / m, 0.0
                    for _ in range(m):
                        acc += c.fn(V, P, S, D, False)
                        for x in range(len(S)):
                            S[x] += h * D[x] / (1.0 + h * c.decay[x]) if m == MICRO else h * D[x]
                    v = acc / m
                    self.advanced.add(r)
                else:
                    v = c.fn(V, P, S, D, init)
            except (OverflowError, ValueError, ZeroDivisionError):
                self.errors[r] = self.errors.get(r, 0) + 1
                v = 0.0
            if not -BIG < v < BIG:
                self.clamped[r] = self.clamped.get(r, 0) + 1
                v = 0.0 if v != v else math.copysign(BIG, v)
            V[r] = v
            if init:
                self.fresh.discard(r)

    def net(self, s: str) -> float:
        V, x = self.V, 0.0
        for f in self.pl.flows_in[s]:
            x += V[f]
        for f in self.pl.flows_out[s]:
            x -= V[f]
        return x

    def jacobian(self, state: dict[str, float | None], full: bool = True) -> tuple[dict[tuple[str, str], float], list[str]]:
        """∂(net inflow of stock i)/∂(level of stock j), per hour, over the live stocks, by forward differences
        of the compiled equations at the moment's values; with ``full``, a column no equation reads is written as 0,
        and the equations that faulted, failed, or gave NaN or a value past ±BIG while a stock was moved (each taken
        as 0 or clamped, so that entry is not to be trusted) are listed. Without it (``rates``, on the replay path)
        neither is, and the list is empty. The faults counted before are kept."""
        live = [s for s in self.stocks if state.get(s) is not None]
        felt = [s for s in self.felt if state.get(s) is not None]
        J: dict[tuple[str, str], float] = {}
        faulted: list[str] = []
        if felt:
            saved = {r: dict(c.faults) for r, c in self.pl.eqs.items()}
            errors, clamped = (dict(self.errors), dict(self.clamped)) if full else ({}, {})
            for c in self.pl.eqs.values():
                c.faults.clear()
            base = {s: self.net(s) for s in live}
            for j in felt:
                x = state[j]
                h = max(abs(x) * 1e-4, 1e-6)
                self.V[f"stock.{j}"] = x + h
                self.evaluate()
                for i in live:
                    J[(i, j)] = (self.net(i) - base[i]) / h
                self.V[f"stock.{j}"] = x
            if full:
                faulted = [r for r, c in self.pl.eqs.items() if c.faults or self.errors.get(r, 0) > errors.get(r, 0)
                           or self.clamped.get(r, 0) > clamped.get(r, 0)]
            self.evaluate()
            for r, c in self.pl.eqs.items():
                c.faults.clear()
                c.faults.update(saved[r])
        if full:                                         # rates sums |entries| and is hot: its zeros add nothing
            moved = set(felt)
            for j in live:
                if j not in moved:
                    for i in live:
                        J[(i, j)] = 0.0
        return J, faulted

    def rates(self, state: dict[str, float | None]) -> float:
        """How fast the stocks move here, per hour: Gershgorin's bound on their Jacobian (``jacobian``).
        Keeps each stock's own drain for the implicit step. (A delay's stages are stepped through within a
        step, ``evaluate``.)"""
        live = [s for s in self.stocks if state.get(s) is not None]
        rows = {s: 0.0 for s in live}
        off = {s: 0.0 for s in live}
        self.diag = {s: 0.0 for s in self.stocks}
        for (i, j), d in self.jacobian(state, full=False)[0].items():
            rows[i] += abs(d)
            if i == j:
                self.diag[i] = max(0.0, -d)
            else:
                off[i] += abs(d)
        self.coupling = max(off.values(), default=0.0)
        return max(rows.values(), default=0.0)

    def step(self, state: dict[str, float | None], dt: float) -> None:
        for s in self.stocks:
            x = state[s]
            if x is None:
                continue
            x += dt * self.net(s) / (1.0 + dt * self.diag.get(s, 0.0))
            if not -BIG < x < BIG:
                self.clamped[f"stock.{s}"] = self.clamped.get(f"stock.{s}", 0) + 1
                x = 0.0 if x != x else math.copysign(BIG, x)
            state[s] = x
        for r in self.pl.eqs:
            if r in self.advanced:
                continue
            st, dd = self.S[r], self.D[r]
            for x in range(len(st)):
                st[x] += dt * dd[x]
        self.advanced.clear()

    def faults(self) -> list[str]:
        """What was substituted, per equation: for the run's notes."""
        out = []
        for r, c in self.pl.eqs.items():
            said = [f"{what} {n} time{'s' if n > 1 else ''}" for what, n in sorted(c.faults.items())]
            if self.errors.get(r):
                said.append(f"failed to compute {self.errors[r]} time{'s' if self.errors[r] > 1 else ''}")
            if said:
                hint = " (write ZIDZ(a, b) where 0 is meant)" if "divided by 0" in c.faults else ""
                out.append(f"{r}: {'; '.join(said)}, each taken as 0{hint}")
        return out

    def counted(self) -> dict[str, dict[str, int]]:
        """Each equation's faults in this run (each was taken as 0), and how often."""
        out = {}
        for r, c in self.pl.eqs.items():
            got = dict(c.faults)
            if self.errors.get(r):
                got["failed to compute"] = self.errors[r]
            if got:
                out[r] = got
        return out

    def clamps(self) -> list[str]:
        return [f"{r} ran past ±{BIG:.0e} {n} time{'s' if n > 1 else ''} and was clamped: the run blew up there"
                for r, n in sorted(self.clamped.items())]


Stepper = _Stepper           # the same arithmetic, for what steps the model's equations live (spec/observer.py)


def _substeps(rate: float, width_h: float) -> tuple[int, bool]:
    """Steps for a bucket: a quarter of the fastest time constant (1/rate), at least SUBSTEPS, at
    most MAX_SUBSTEPS (and whether it had to stop there)."""
    want = max(SUBSTEPS, math.ceil(width_h * rate * QUARTER)) if rate > 0 else SUBSTEPS
    want += want % 2
    return min(want, MAX_SUBSTEPS), want > MAX_SUBSTEPS


def _hours(h: float) -> str:
    from ..durations import human
    return human(h * 3600.0)


def replay(spec: Spec, data: Data, pl: Plan | None = None, trace: set[str] | None = None) -> Run:
    """The model run over the record (the module's docstring). With ``trace``, the values of those parts at
    every integration step are kept (``Run.trace``: (bucket, {part: value})), for what is computed per step
    of the simulation itself, as loop dominance is (Schoenberg et al. 2020: link scores per DT)."""
    pl = pl or plan(spec)
    g = data.grid
    n, w_s = g.n, g.width
    w = w_s / 3600.0
    edges = g.edges()
    notes: list[str] = [f"{r}: its equation is not run ({why}); it is taken as measured" for r, why in pl.left_out.items()]
    for c in pl.eqs.values():
        c.faults.clear()
    st = _Stepper(pl, pl.integrate)
    V = st.V
    integrated = {f"stock.{s}" for s in pl.integrate}
    levels = [r for r in data.values if r.split(".", 1)[0] in ("stock", "auxiliary") and r not in pl.eqs and r not in integrated]
    counted = {r: c for r, c in data.counted.items() if r not in pl.eqs}
    read = [r for r in data.values if r.startswith("flow.") and r not in pl.eqs and r not in counted]
    held = {r: data.held(r) for r in read}
    start = {s: data.started.get(f"stock.{s}") for s in pl.integrate}
    state: dict[str, float | None] = {s: None for s in pl.integrate}
    out: dict[str, list[float | None]] = {f"stock.{s}": [None] * n for s in pl.integrate} | {r: [None] * n for r in pl.eqs}
    at_edges: dict[str, list[float | None]] = {r: [None] * (n + 1) for r in out}
    moved: dict[str, list[float | None]] = {r: [0.0] * n for r in pl.eqs if r.startswith("flow.")}
    at_reading: dict[str, list[float | None]] = {f"stock.{s}": [None] * n for s in pl.integrate}
    reading = {s: data.at.get(f"stock.{s}") or [None] * n for s in pl.integrate}
    missing: set[str] = set()
    taus: dict[str, list[float]] = {s: [] for s in pl.integrate}
    capped: list[tuple[float, float, int]] = []          # (dt·rate, rate, bucket) where the step stopped at its most
    traced: list[tuple[int, dict[str, float | None]]] = []
    tracing = sorted(trace or ())
    unstable = False
    steps, fastest = 0, 0.0

    def given(t: float, i: int) -> None:
        for r in levels:
            v = data.level_at(r, t)
            if v is None:
                missing.add(r)
                v = 0.0
            V[r] = v
        for r in read:
            v = held[r][i]
            if v is None:
                missing.add(r)
                v = 0.0
            V[r] = v

    def begin(t1: float) -> None:
        """Each stock not yet started whose first reading is by ``t1`` starts at it, with what its
        counted flows moved since that reading."""
        for s in pl.integrate:
            if state[s] is None and start[s] is not None and start[s][0] <= t1:
                t0, v0 = start[s]
                x = v0
                for f in pl.flows_in[s]:
                    if f in counted:
                        x += counted[f].between(t0, t1)
                for f in pl.flows_out[s]:
                    if f in counted:
                        x -= counted[f].between(t0, t1)
                state[s] = x

    def stocks_in() -> None:
        for s in pl.integrate:
            if state[s] is not None:
                V[f"stock.{s}"] = state[s]
            elif f"stock.{s}" not in V:
                V[f"stock.{s}"] = 0.0

    for r in counted:
        V[r] = 0.0
    begin(edges[0])
    for i in range(n):
        t0 = edges[i]
        given(t0 + w_s / 4, i)
        stocks_in()
        st.evaluate()
        rate = st.rates(state)
        for s in pl.integrate:
            if state[s] is not None and st.diag.get(s, 0.0) > 0:
                taus[s].append(1.0 / st.diag[s])
        k, cap = _substeps(rate, w)
        dt, dt_s = w / k, w_s / k
        fastest = max(fastest, rate)
        if cap:
            capped.append((dt * rate, rate, i))
            unstable = unstable or dt * st.coupling > 1.0
        quiet = {r: c.between(t0, edges[i + 1]) == 0.0 for r, c in counted.items()}
        for j in range(k):
            t = t0 + j * dt_s
            if j == k // 2:
                given(t0 + 3 * w_s / 4, i)
            for r, c in counted.items():
                V[r] = 0.0 if quiet[r] else c.between(t, t + dt_s) / dt
            stocks_in()
            st.evaluate(dt)
            if j == 0:
                for r in at_edges:
                    at_edges[r][i] = state[r[6:]] if r in integrated else V[r]
            if j == k // 2:
                for r in out:
                    out[r][i] = state[r[6:]] if r in integrated else V[r]
            for r in moved:
                moved[r][i] += V[r] * dt
            if tracing:
                traced.append((i, {r: (state.get(r[6:]) if r in integrated else V.get(r)) for r in tracing}))
            for s in pl.integrate:                       # a stock at its reading's moment, to be compared there exactly
                tr = reading[s][i]
                if tr is not None and t < tr <= t + dt_s and state[s] is not None:
                    x = state[s] + (tr - t) / 3600.0 * (sum(V[f] for f in pl.flows_in[s] if f not in counted) -
                                                       sum(V[f] for f in pl.flows_out[s] if f not in counted))
                    x += sum(counted[f].between(t, tr) for f in pl.flows_in[s] if f in counted)
                    x -= sum(counted[f].between(t, tr) for f in pl.flows_out[s] if f in counted)
                    at_reading[f"stock.{s}"][i] = x
            st.step(state, dt)
            begin(t + dt_s)
            steps += 1
    given(edges[-1], n - 1)
    stocks_in()
    st.evaluate()
    for r in at_edges:
        at_edges[r][n] = state[r[6:]] if r in integrated else V[r]
    for s in pl.integrate:                               # nothing is said of a stock before its replay started
        if start[s] is None:
            continue
        for i in range(n):
            if edges[i + 1] <= start[s][0]:
                out[f"stock.{s}"][i] = None
        for i in range(n + 1):
            if edges[i] < start[s][0]:
                at_edges[f"stock.{s}"][i] = None
    used = {r for c in pl.eqs.values() for r in eq.refs(c.tree)}
    used |= {f for s in pl.integrate for f in (*pl.flows_in[s], *pl.flows_out[s]) if f not in pl.eqs}
    notes += [f"{r} was never measured in the window: taken as 0" for r in sorted(missing & used) if data.first(r) is None]
    never = [s for s in pl.integrate if start[s] is None]
    notes += [f"stock.{s} was never measured in the window: nothing to start its replay from" for s in never]
    notes += st.faults()
    invalid = st.clamps()
    if capped:
        worst = max(capped)
        notes.append(f"the fastest time constant met ({_hours(1 / worst[1])}) is shorter than four steps of "
                     f"{_hours(w / MAX_SUBSTEPS)} in {len(capped)} of {n} buckets: what is faster than a step is taken as "
                     f"settled at once (each stock's own drain integrated implicitly), which buckets of "
                     f"{_hours(w)} cannot resolve anyway")
    if st.coarse:
        notes.append(f"a delay's stages ({_hours(1 / st.coarse)} each) are far shorter than a step of the window: "
                     f"stepped through in {MICRO} steps each, and settled at once (implicitly) past that")
        if unstable:
            invalid.append(f"stocks drive each other faster than a step of {_hours(w / MAX_SUBSTEPS)} can follow: the "
                           f"replay is not to be trusted at this resolution (a shorter window has shorter steps)")
    tc = {f"stock.{s}": sorted(v)[len(v) // 2] for s, v in taus.items() if v}
    for r, c in pl.eqs.items():
        if c.decay and all(c.decay):
            tc[r] = sum(1.0 / d for d in c.decay)
    how = {f"stock.{s}": "integrated" for s in pl.integrate} | {r: "equation" for r in pl.eqs}
    for s in pl.integrate:                               # a reading at the first moment of the replay is where it started
        for i in range(n):
            tr = reading[s][i]
            if tr is not None and at_reading[f"stock.{s}"][i] is None and start[s] is not None and tr == start[s][0]:
                at_reading[f"stock.{s}"][i] = start[s][1]
    return Run(g.times(), out, how, notes, {s: v for s, v in state.items() if v is not None},
               {r: list(v) for r, v in st.S.items()}, steps, edges, at_edges, moved, invalid, at_reading, tc,
               {s: v[0] for s, v in start.items() if v is not None}, fastest or None, st.counted(), traced)


def _trend(vals: list[float | None], times: list[float]) -> tuple[float, float] | None:
    """The value now (the mean of the last few) and its slope per hour over the last quarter of the
    window (least squares)."""
    pts = [(t, v) for t, v in zip(times, vals, strict=True) if v is not None]
    pts = pts[-max(3, len(pts) // 4):]
    if len(pts) < 2:
        return (pts[-1][1], 0.0) if pts else None
    mt = sum(t for t, _ in pts) / len(pts)
    mv = sum(v for _, v in pts) / len(pts)
    var = sum((t - mt) ** 2 for t, _ in pts)
    slope = sum((t - mt) * (v - mv) for t, v in pts) / var if var else 0.0
    now = mv + slope * (pts[-1][0] - mt)                 # the fitted line at the last point, not one raw sample
    return now, slope * 3600.0


def _rescale(pl: Plan, was: Plan, st: _Stepper) -> None:
    """Each material delay's stages scaled from the time ``was`` gives them to the time ``pl`` does (decay is one
    over a stage's time), the inputs as they are now."""
    for r, c in pl.eqs.items():
        old = was.eqs.get(r)
        if old is None or not any(c.material) or old.slots != c.slots:
            continue
        saved = dict(old.faults)
        try:
            old.fn(st.V, was.params, list(st.S[r]), [0.0] * old.slots, False)
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        finally:
            old.faults.clear()
            old.faults.update(saved)
        for j in range(c.slots):
            if c.material[j] and c.decay[j] > 0 and old.decay[j] > 0:
                st.S[r][j] *= old.decay[j] / c.decay[j]


def controlled(spec: Spec) -> set[str]:
    """What lies downstream of a flow a block sets: that flow, the stocks it fills or drains, and every
    equation and stock that follows from them. An open-loop projection holds the controller, so it
    says nothing true about these."""
    out: set[str] = set()
    for f in spec.flows.values():
        if spec.actuator_of(f.name) is not None:
            out.add(f"flow.{f.name}")
            out |= {f"stock.{s}" for s in (f.source, f.target) if s}
    grew = True
    while grew:
        grew = False
        for table, kind in ((spec.flows, "flow"), (spec.auxiliaries, "auxiliary")):
            for x in table.values():
                r = f"{kind}.{x.name}"
                if r in out or not x.equation or not out & set(x.equation.refs):
                    continue
                out.add(r)
                grew = True
                if kind == "flow":
                    out |= {f"stock.{s}" for s in (x.source, x.target) if s}
    return out


def project(spec: Spec, data: Data, run: Run, horizon: float, pl: Plan | None = None, points: int | None = None,
            inputs: str = "hold", rescale: Plan | None = None, held: set[str] | None = None,
            override: dict[str, float] | None = None, control=None) -> Run:
    """From now (``data.grid.until``) for ``horizon`` seconds, open loop: stocks from their last
    readings (the mean of the last few; the replay's end where they have none), delays as the replay
    left them; every input held where it was (``inputs="hold"``) or carried on along its recent trend
    (``"trend"``; a one-way flow never below 0). What a controller's flow moves is left out.

    ``rescale`` is the plan the replay ran with, when this one has other values (a sensitivity sample): a
    material delay's contents are then rescaled to this plan's delay time at the same outflow (what is in a
    pipeline at a given throughput is that throughput times its time: Sterman ch. 11), so a sample with
    another delay time starts in its own steady state and the projection does not jump at now; a smoothed
    value (SMOOTH) is a perceived level, the same whatever its time, and is kept.

    ``override`` holds some inputs at other values (a what-if's rate, a Monte Carlo draw). ``control`` closes the
    loops (closedloop.py): it sets the flows it names (``control.flows``) at every step, before the equations are worked
    out (``control.begin(V, state, moving, k, n, step)`` returns the steps a point it needs; ``control.step(t, dt)``;
    ``control.point(i)`` at each point's end; ``control.notes()``)."""
    pl = pl or plan(spec)
    g = data.grid
    n = points or max(2, round(horizon / g.width))
    step = horizon / n
    times = [g.until + (i + 1) * step for i in range(n)]
    saved = {r: dict(c.faults) for r, c in pl.eqs.items()}     # the replay's own, kept for it; the projection counts its own
    for c in pl.eqs.values():
        c.faults.clear()
    st = _Stepper(pl, pl.integrate)
    V = st.V
    state: dict[str, float | None] = {}
    for s in pl.integrate:
        got = data.recent(f"stock.{s}")
        state[s] = got if got is not None else run.state.get(s)
    for r in pl.eqs:
        if run.hidden.get(r):
            st.S[r] = list(run.hidden[r])
            st.fresh.discard(r)
    ts = g.times()
    ahead: dict[str, tuple[float, float]] = {}
    for r, vals in data.values.items():
        tr = _trend(vals, ts)
        if tr is not None:
            ahead[r] = (tr[0], tr[1] if inputs == "trend" else 0.0)
    one_way = {f"flow.{f.name}" for f in spec.flows.values() if not f.two_way}
    for r in data.values:
        V[r] = 0.0                                       # what was never measured is taken as 0, as in the replay
    held = controlled(spec) if held is None else held
    out: dict[str, list[float | None]] = {f"stock.{s}": [None] * n for s in pl.integrate} | {r: [None] * n for r in pl.eqs}
    for r, v in (override or {}).items():
        ahead[r] = (v, 0.0)
    mine = control.flows if control is not None else set()
    moving = [(r, v0, slope) for r, (v0, slope) in ahead.items() if (slope or inputs != "hold") and r not in mine]
    for r, (v0, _) in ahead.items():                     # held where they were: set once (an equation's own value wins)
        if r not in mine:
            V[r] = max(0.0, v0) if r in one_way and v0 >= 0 else v0

    def inputs_at(t: float) -> None:
        h = (t - g.until) / 3600.0
        for r, v0, slope in moving:
            v = v0 + slope * h
            V[r] = max(0.0, v) if r in one_way and v0 >= 0 else v
        for s in pl.integrate:
            V[f"stock.{s}"] = state[s] if state[s] is not None else 0.0
    t = g.until
    inputs_at(t)
    st.evaluate()
    if rescale is not None:
        _rescale(pl, rescale, st)
        st.evaluate()
    k, _ = _substeps(st.rates(state), step / 3600.0)
    if control is not None:
        k = control.begin(V, state, {m[0] for m in moving}, k, n, step)
    dt = step / 3600.0 / k
    for i in range(n):
        for _ in range(k):
            inputs_at(t)
            if control is not None:
                control.step(t, dt)
            st.evaluate(dt)
            st.step(state, dt)
            t += step / k
        inputs_at(t)
        st.evaluate()
        if control is not None:
            control.point(i, t)
        for s in pl.integrate:
            out[f"stock.{s}"][i] = state[s]
        for r in pl.eqs:
            out[r][i] = V[r]
    left = sorted(r for r in out if r in held)
    for r in left:
        out[r] = [None] * n
    notes = control.notes() if control is not None else \
        [f"open loop: inputs {'held where they were' if inputs == 'hold' else 'carried on along their trend'}, controllers held"]
    if left:
        notes.append(f"left out downstream of a controller's flow ({len(left)} part{'s' if len(left) > 1 else ''})")
    how = {f"stock.{s}": "integrated" for s in pl.integrate} | {r: "equation" for r in pl.eqs}
    counted = st.counted()
    for r, c in pl.eqs.items():
        c.faults.clear()
        c.faults.update(saved[r])
    return Run(times, out, how, notes + st.clamps(), {s: v for s, v in state.items() if v is not None}, st.S,
               steps=n * k, invalid=st.clamps(), faults=counted)


HORIZON = 0.25           # a projection looks ahead at most a quarter of the window ...
LEAST = 0.05             # ... at least a twentieth of it ...
DOMINANT = 3.0           # ... and, between, three of the slowest time constant the replay met


def horizon_of(run: Run, window: float) -> float:
    """How far a projection looks: a few of the model's slowest time constants, within a twentieth and
    a quarter of the window."""
    slow = max((v for r, v in run.time_constants.items() if r.startswith("stock.")), default=None)
    if not slow:
        return window * HORIZON
    return min(window * HORIZON, max(window * LEAST, DOMINANT * slow * 3600.0))
