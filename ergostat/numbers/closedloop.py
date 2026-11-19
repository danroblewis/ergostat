"""The model run ahead with its loops running: a closed-loop projection, and its risk (SPEC §12b, §12c).

The open-loop projection (``simulate.project``) holds the blocks still, so it cannot say whether a backlog drains or a
loop holds. Here the control structure runs forward beside the stocks and flows, as system dynamics simulates a policy
(Sterman, *Business Dynamics*, ch. 1 and 21: a decision rule is part of the model, not an input to it), through
``simulate.project``'s control hook:

- **goals and built-in blocks** are worked out by the engine's own code (``spec/engine.py``'s ``goals``,
  ``_builtins``, ``get`` and ``command_of``, on the engine's built-in blocks) on a shadow of the engine's state, started
  from where the record left it (``start_of``: each goal's status and set setpoint, each built-in's output and the
  internal state the record lets us rebuild: a delay's line, a timer's or an alarm's start, a counter's count). Given the
  same readings at the same moments, a built-in decides what the engine would; the projection's readings are the
  model's, taken at its own steps, and a state the record cannot rebuild is said in the notes;
- **machine blocks** run as their identified models (``blockmodels.py``);
- the goals and built-ins read a count of items as a whole number, as its sensor does.

**Risk** (``risk``): Monte Carlo over what the projection does not know: the model's uncertain parameters
(``sensitivity.uncertain``, less those whose error spans everything, ``sensitivity.informative``), each identified
model's numbers by their standard errors, and each input from outside by how far its mean over the horizon could be
from now (``inputs_uncertain``). For each goal, the probability it is off at the horizon (a run that is not valid counts
as off, and is said) and its expected time off; for each part, the spread. Bounded in runs (``MOST_RUNS``), steps
(``MAX_STEPS``) and wall time (``budget``); the draws come from a fixed seed, so the same model and record give the same
answer when every run is made within the time allowed.

Time is in hours, as rates are; a block's own time (``every:``, ``min-on``) in seconds, as the engine keeps it."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from statistics import fmean, stdev

from ..spec import engine as en
from ..spec.blocks import make as make_builtin
from ..spec.blocks import order as builtin_order
from ..spec.ir import Ref, Spec
from . import observe as ob
from . import sensitivity as sens
from . import simulate as sim
from .blockmodels import BlockModel, _dur, _rate, actuated, has_controllers, held_by_blocks, identify  # noqa: F401

MAX_STEPS = 4000            # integration steps in one closed-loop run, at most
MIN_STEPS = 4               # ... and at least this many in each point drawn
DRAIN_STEPS = 8             # ... and at most this many to follow a fast drain (one faster empties within a step)
RUNS = 100                  # Monte Carlo runs of the risk, by default ...
MOST_RUNS = 400             # ... and at most
BUDGET = 15.0               # seconds of wall time the risk may take; past it, it stops and says how many runs it made
MOST_HORIZON = 30 * 86400.0  # a closed-loop projection looks at most this far ahead (seconds)
SEED = 20261118


# ---- where the control structure is now, from the record

@dataclass
class Start:
    """Each goal's status and a setpoint a block set; each built-in's output and when it changed (epoch seconds), and
    the internal state rebuilt from the record (attribute → value); what could not be rebuilt, in words."""

    status: dict[str, str] = field(default_factory=dict)
    setpoint: dict[str, float] = field(default_factory=dict)
    outputs: dict[str, tuple[float, float]] = field(default_factory=dict)
    state: dict[str, dict] = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)


def _history(p, spec: Spec, r: Ref, since: float, until: float) -> list[tuple[float, float]] | None:
    """A signal's recorded values over a span, the one before it first: a part's readings, a built-in's output (None: a
    signal the record does not keep, a goal's error or a machine's command)."""
    if r.kind == "block":
        series = [f"block/{r.name}"] if r.name in spec.blocks and spec.blocks[r.name].builtin else []
    else:
        part = spec.measured(r.kind).get(r.name)
        series = [s.series for s in part.sensors.values()] if part is not None else []
    if not series:
        return None
    pts = []
    for sr in series:
        before = p.measurements.latest(sr, before=since)
        pts += ([(since, before[1])] if before else []) + p.measurements.range(sr, since, until)
    return sorted(pts)


def _since(pts: list[tuple[float, float]], test) -> float | None:
    """When the last unbroken run of values passing ``test`` began (None: the last value does not pass)."""
    began = None
    for t, v in pts:
        began = (began if began is not None else t) if test(v) else None
    return began


def start_of(p, spec: Spec, at: float) -> Start:
    st = Start()
    for name, g in spec.goals.items():
        evs = p.events.query(n=1, type="loop.off,loop.holding", item=name, until=at)
        if evs:
            st.status[name] = evs[-1]["type"].split(".", 1)[1]
            sp = str((evs[-1].get("data") or {}).get("setpoint") or "").split()
            try:
                v = float(sp[-1]) if sp else None
            except ValueError:
                v = None
            if v is not None and v != g.hold.value:
                st.setpoint[name] = v
    order = builtin_order(spec)
    for name, b in spec.blocks.items():
        if not b.builtin or b.type == "judge":
            continue
        got = p.measurements.latest(f"block/{name}", before=at)
        if got:
            st.outputs[name] = (got[0], got[1])
        x = next(iter(b.inputs.values()), None)
        pr = b.params
        if b.type == "limit":
            st.state[name] = {"last_t": at}
        elif b.type in ("delay", "timer", "alarm", "counter"):
            span = float(pr.get("delay") or 0.0) if b.type == "delay" else 7 * 86400.0
            pts = _history(p, spec, x, at - span, at) if x is not None else None
            if pts is None:
                st.unknown.append(f"{name} ({b.type}): what it read is not kept in the record, so it starts afresh")
                continue
            if b.type == "delay":
                st.state[name] = {"line": [(t, v) for t, v in pts if t >= at - span], "held": got[1] if got else None}
                if x.kind == "block" and x.name in order and order.index(x.name) > order.index(name):
                    st.unknown.append(f"{name} (delay): {x.name} is worked out after it in each pass, so its line is "
                                      f"rebuilt from {x.name}'s changes, a pass early")
            elif b.type == "timer":
                st.state[name] = {"since": _since(pts, bool)}
            elif b.type == "alarm":
                hi, lo = pr.get("above"), pr.get("below")
                st.state[name] = {"since": _since(pts, lambda v, hi=hi, lo=lo: (hi is not None and v > float(hi)) or
                                                  (lo is not None and v < float(lo)))}
            else:
                outs = _history(p, spec, Ref("block", name), at - span, at) or []
                zero = next((t for t, v in reversed(outs) if v == 0), None)
                st.state[name] = {"n": got[1] if got else 0.0, "was": bool(pts[-1][1]) if pts else False,
                                  "reset_at": zero if zero is not None else at}
                if pr.get("reset") and zero is None:
                    st.unknown.append(f"{name} (counter): when it last reset is not in the record; its reset clock starts now")
    return st


class Shadow:
    """The engine's control state without its machinery: the engine's own methods run on it."""

    get = en.Engine.get
    goals = en.Engine.goals
    _builtins = en.Engine._builtins
    _downstream = en.Engine._downstream
    _builtin_wiring = en.Engine._builtin_wiring
    _event = en.Engine._event
    decided = en.Engine.decided
    command_of = en.Engine.command_of
    stale_mode = en.Engine.stale_mode

    def __init__(self, spec: Spec, signals: dict, start: Start | None = None, setpoints: dict | None = None):
        from collections import deque
        self.spec, self.signals = spec, signals
        self.stale, self.stale_parts = {}, {}               # a simulated reading is never stale (SPEC §9.6)
        self.builtins = {n: make_builtin(spec.blocks[n], spec) for n in builtin_order(spec)}
        start = start or Start()
        self.status, self.setpoint = dict(start.status), dict(start.setpoint)
        self.fixed = dict(setpoints or {})                  # a what-if's setpoints: a cascade does not move them
        self.setpoint.update(self.fixed)
        self.outputs: dict = {}
        self.commands: dict = {}
        self.cause: dict = {}
        for n, (t, v) in start.outputs.items():
            if n in self.builtins:
                self.builtins[n].out, self.builtins[n].changed_at = v, t
                signals[f"block.{n}"] = v
        for n, attrs in start.state.items():
            for k, v in attrs.items():
                if n in self.builtins and v is not None:
                    setattr(self.builtins[n], k, deque(v) if k == "line" else v)

    def say(self, _text: str) -> None:
        pass

    def step(self, now: float) -> None:
        """One pass, as ``Engine.evaluate`` makes it with everything worked out: the goals, the built-ins in their order,
        then the goals whose setpoint a built-in moved."""
        events: list = []
        self.goals(now, out=events)
        _, set_goals, _ = self._builtins(now, None, {}, events, [])
        if self.fixed:
            self.setpoint.update(self.fixed)
        if set_goals:
            self.goals(now, out=events)

    def on(self, block: str) -> bool:
        cmd, _ = self.command_of(self.spec.blocks[block])
        return True if cmd is None else bool(cmd)


# ---- what-ifs only a closed loop tries

@dataclass
class WhatIf:
    """An input's rate (per hour, or ``x`` a multiple of its mean over the window), a goal's setpoint, a block's pool."""

    flows: dict[str, tuple[str, float]] = field(default_factory=dict)
    setpoints: dict[str, float] = field(default_factory=dict)
    pools: dict[str, int] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.flows or self.setpoints or self.pools)

    def key(self) -> tuple:
        return tuple(tuple(sorted(d.items())) for d in (self.flows, self.setpoints, self.pools))

    def said(self) -> list[str]:
        return [f"{r[5:]} {'×' + format(v, 'g') + ' its mean' if how == 'x' else 'at ' + _rate(v)}"
                for r, (how, v) in self.flows.items()] + \
            [f"goal {g} at {v:g}" for g, v in self.setpoints.items()] + [f"{b}'s pool {n}" for b, n in self.pools.items()]


class WhatIfError(ValueError):
    pass


def _number(k: str, v: str, words: str) -> float:
    try:
        return float(v[1:] if v[:1] in ("x", "×", "*") else v)
    except ValueError:
        raise WhatIfError(f"{k}: {v!r} is not {words}") from None


def parse_whatif(spec: Spec, raw: dict[str, str]) -> tuple[dict[str, str], WhatIf]:
    """The parameters (as they came, for ``proposals.what_if``) apart from ``flow.NAME`` (a rate an hour, or ``x2``),
    ``goal.NAME`` (a setpoint) and ``block.NAME.pool``."""
    params, w = {}, WhatIf()
    for k, v in raw.items():
        v = str(v).strip()
        if k.startswith("flow."):
            if k[5:] not in spec.flows:
                raise WhatIfError(f"no flow {k[5:]}")
            w.flows[k] = ("x" if v[:1] in ("x", "×", "*") else "=", _number(k, v, "a rate an hour, or x2 for twice its mean"))
            if w.flows[k][1] < 0:
                raise WhatIfError(f"{k}: a rate below 0")
        elif k.startswith("goal."):
            if k[5:] not in spec.goals:
                raise WhatIfError(f"no goal {k[5:]}")
            w.setpoints[k[5:]] = _number(k, v, "a number")
        elif k.startswith("block.") and k.endswith(".pool"):
            b = spec.blocks.get(k[6:-5])
            if b is None or not b.takes:
                raise WhatIfError(f"{k[6:-5]} is not a block that takes items: it has no pool")
            n = int(_number(k, v, "a number of runs at once"))
            if n < 1:
                raise WhatIfError(f"{k}: a pool of at least 1")
            w.pools[k[6:-5]] = n
        else:
            params[k] = v
    return params, w


# ---- the closed-loop run

@dataclass
class ClosedRun(sim.Run):
    """A ``simulate.Run`` with each goal's share of each point off, whether off at each point's end, its hours off, and
    the identified models it ran with."""

    off: dict[str, list[float]] = field(default_factory=dict)
    off_end: dict[str, list[int]] = field(default_factory=dict)
    off_hours: dict[str, float] = field(default_factory=dict)
    models: dict[str, BlockModel] = field(default_factory=dict)


class _Control:
    """``simulate.project``'s control hook: the shadow's pass and each identified model's flow at every step."""

    def __init__(self, spec: Spec, models: dict[str, BlockModel], start: Start | None, whatif: WhatIf, drawn: dict,
                 own: dict, params: dict, inputs: str, fine: int = 0):
        self.fine = fine
        self.spec, self.models, self.own, self.params, self.inputs, self.whatif = spec, models, own, params, inputs, whatif
        self.flows = set(models)
        self.drawn = {r: {**(drawn.get(r) or {}), **({"servers": whatif.pools[m.block]} if m.block in whatif.pools else {})}
                      for r, m in models.items()}
        self.G: dict = {}
        self.sh = Shadow(spec, self.G, start, whatif.setpoints)
        self.start = start
        self.counted = {f"stock.{n}" for n, x in spec.stocks.items()
                        if x.sensors and all(z.items and z.items.get("measure") in (None, "count") for z in x.sensors.values())}
        self.reads = {str(gl.of) for gl in spec.goals.values()} | {str(r) for b in spec.blocks.values() if b.builtin
                                                                    for r in b.inputs.values() if r.kind in ("stock", "flow", "auxiliary")}
        self.told = [f"goal.{m.goal}{k}" for m in models.values() if m.goal for k in ("", ".error", ".off")]
        self.blocks = sorted({m.block for m in models.values() if m.gate})
        self.one_way = {f"flow.{f.name}" for f in spec.flows.values() if not f.two_way}
        self.faults: dict[str, int] = {}
        self.timed = [m for m in models.values() if hasattr(m, "at")]   # a model that changes at a time (impact.py)

    def begin(self, V, state, moving, k, n, step):
        self.V, self.state, self.n = V, state, n
        # an outflow held where it was stops when its stock is empty (Sterman ch. 21's first extreme condition); an
        # equation's outflow is the model's own and is left as it writes it
        self.drains = {r: f.source for r in V if r.startswith("flow.") and r not in self.flows and r in self.one_way
                       and (f := self.spec.flows.get(r[5:])) is not None and f.source in state and f.equation is None}
        self.want = {r: V.get(r, 0.0) for r in self.drains}
        self.moving = moving
        self.out = {r: [None] * n for r in self.models}
        self.off = {g: [0.0] * n for g in self.spec.goals}
        self.off_end = {g: [0] * n for g in self.spec.goals}
        self.hours = dict.fromkeys(self.spec.goals, 0.0)
        self.acc = dict.fromkeys(self.models, 0.0)
        self.k = k
        fastest = min((m.residence for m in self.models.values() if m.form == "drain" and m.residence), default=None)
        if fastest:                                          # a drain followed about once per its residence time, up to
            k = max(k, min(DRAIN_STEPS, math.ceil(step / 3600.0 / fastest)))   # DRAIN_STEPS: faster, it empties in a step
        self.k = max(MIN_STEPS, self.fine, min(k, max(1, MAX_STEPS // n)))   # fine: at least so many (extremes.py)
        self.i = 0
        return self.k

    def _shadow(self, t: float) -> None:
        V, G = self.V, self.G
        for r in self.reads:
            v = V.get(r)
            if v is None:
                G.pop(r, None)
            else:
                G[r] = math.floor(v + 0.5) if r in self.counted else v
        self.sh.step(t)
        for key in self.told:
            V[key] = G.get(key)

    def step(self, t: float, dt: float) -> None:
        V, state = self.V, self.state
        self._shadow(t)
        for r, src in self.drains.items():
            if r in self.moving:
                self.want[r] = V[r]
            x = state.get(src)
            V[r] = min(self.want[r], max(0.0, x) / dt) if x is not None else self.want[r]
        ons = {b: self.sh.on(b) for b in self.blocks}
        for m in self.timed:
            m.at(t)
        for r, m in self.models.items():
            eqv = None
            if r in self.own:
                try:
                    eqv = self.own[r].fn(V, self.params, [], [], False)
                except (OverflowError, ValueError, ZeroDivisionError):
                    self.faults[r] = self.faults.get(r, 0) + 1
                    eqv = 0.0
            v = m.rate(V, ons.get(m.block, True) if m.gate else True, self.drawn.get(r), eqv, dt)
            V[r] = max(0.0, v) if r in self.one_way else v
        took: dict[str, list[str]] = {}                      # what the models take from each stock, together at most what it holds
        for r in self.models:
            src = self.spec.flows[r[5:]].source
            if r in self.one_way and src and state.get(src) is not None:
                took.setdefault(src, []).append(r)
        for src, rs in took.items():
            k = max(0.0, state[src]) / dt / (sum(V[r] for r in rs) or 1.0)
            for r in rs:
                V[r] *= min(1.0, k)
        for r in self.models:
            self.acc[r] += V[r] / self.k
        for g in self.spec.goals:
            if self.G.get(f"goal.{g}.off"):
                self.off[g][self.i] += 1.0 / self.k
                self.hours[g] += dt

    def point(self, i: int, t: float) -> None:
        self._shadow(t)
        for r in self.models:
            self.out[r][i], self.acc[r] = self.acc[r], 0.0
        for g in self.spec.goals:
            self.off_end[g][i] = 1 if self.G.get(f"goal.{g}.off") else 0
        self.i = i + 1

    def notes(self) -> list[str]:
        out = [f"with the loops running: the goals and built-in blocks worked out as the engine does, each machine block "
               f"by its identified model; inputs {'held where they were' if self.inputs == 'hold' else 'carried on along their trend'}"]
        assumed = sorted({m.block for m in self.models.values() if m.assumed})
        if assumed:
            out.append(f"assumed, not identified (too little record): {', '.join(assumed)}")
        out += [f"not rebuilt from the record: {x}" for x in (self.start.unknown if self.start else [])]
        out += [f"{r}: its equation failed {k} time{'s' if k > 1 else ''}, each taken as 0" for r, k in self.faults.items()]
        if self.whatif:
            out.append("what if " + ", ".join(self.whatif.said()))
        return out


def closed(spec: Spec, data: ob.Data, run: sim.Run, horizon: float, pl: sim.Plan | None = None, points: int | None = None,
           models: dict[str, BlockModel] | None = None, start: Start | None = None, inputs: str = "hold",
           whatif: WhatIf | None = None, draw: dict | None = None, rescale: sim.Plan | None = None, fine: int = 0) -> ClosedRun:
    """From now (``data.grid.until``) for ``horizon`` seconds, with the loops running (the module's docstring). ``draw``
    is a Monte Carlo run's values: ``{"models": {flow: {name: value}}, "inputs": {ref: rate}}``."""
    whatif, draw = whatif or WhatIf(), draw or {}
    models = {r: m for r, m in (models or {}).items() if r not in whatif.flows}   # a rate tried replaces its model
    base = pl or sim.plan(spec)
    # a flow whose equation its model runs itself (gated, capped) is taken out of the plan
    gated = {r for r, m in models.items() if m.form == "equation" and r in base.eqs and not base.eqs[r].slots}
    pl = sim.plan(spec, base.params, given=gated) if gated else base
    own = {r: base.eqs[r] for r in gated}
    saved = {r: dict(c.faults) for r, c in own.items()}
    override = dict(draw.get("inputs") or {})
    for r, (how, v) in whatif.flows.items():
        seen = [x for x in data.values.get(r) or [] if x is not None]
        override[r] = v if how == "=" else v * (fmean(seen) if seen else 0.0)
    ctl = _Control(spec, models, start, whatif, draw.get("models") or {}, own, pl.params, inputs, fine)
    for c in own.values():
        c.faults.clear()
    try:
        got = sim.project(spec, data, run, min(horizon, MOST_HORIZON), pl, points, inputs, rescale, set(), override, ctl)
        for r, c in own.items():                             # its own equation's faults, each taken as 0: said
            if c.faults:
                got.faults[r] = dict(c.faults)
                got.notes.append(f"{r}: {'; '.join(f'{w} {k} times' for w, k in sorted(c.faults.items()))}, each taken as 0")
    finally:
        for r, c in own.items():
            c.faults.clear()
            c.faults.update(saved[r])
    got.values.update(ctl.out)
    got.how.update({r: "identified model" for r in models})
    for r, k in ctl.faults.items():
        got.faults.setdefault(r, {})["failed to compute"] = k
    return ClosedRun(**got.__dict__, off=ctl.off, off_end=ctl.off_end, off_hours=ctl.hours, models=models)


def projection(p, spec: Spec, data: ob.Data, run: sim.Run, horizon: float, pl: sim.Plan | None = None,
               points: int | None = None, loops: str = "closed", inputs: str = "hold", whatif: WhatIf | None = None,
               models: dict[str, BlockModel] | None = None, held: set[str] | None = None) -> dict:
    """The projection the page and ``ergostat project`` draw: with the loops running (each machine block's model
    identified on the reference window), or held. ``{"projection", "models", "start"}``."""
    if loops != "closed":
        return {"projection": sim.project(spec, data, run, horizon, pl, points, inputs, held=held), "models": {}, "start": None}
    models = models if models is not None else identify(p, spec, ob.measured(p, ob.reference(p, data.grid.until)))
    start = start_of(p, spec, data.grid.until)
    return {"projection": closed(spec, data, run, horizon, pl, points, models, start, inputs, whatif),
            "models": models, "start": start}


# ---- risk: Monte Carlo over what is not known, with the loops running

def inputs_uncertain(spec: Spec, data: ob.Data, horizon: float) -> list[dict]:
    """Each input from outside the control and how far its mean over the horizon could be from where the projection
    holds it: the spread of its recent readings over the square root of the horizon's effective number of buckets, the
    buckets the horizon spans times (1 − ρ)/(1 + ρ), ρ the readings' lag-one autocorrelation (readings that drift
    together are fewer independent ones: Ljung ch. 9, as ``identify.py`` widens an estimate's error)."""
    from .identify import _rho
    act = actuated(spec)
    out = []
    for name, f in spec.flows.items():
        r = f"flow.{name}"
        vals = [v for v in (data.values.get(r) or []) if v is not None]
        if f.equation is not None or r in act or len(vals) < 6:
            continue
        tail = vals[-max(6, len(vals) // 4):]
        sd, now = stdev(tail), sim._trend(data.values[r], data.grid.times())
        if sd <= 0 or now is None:
            continue
        rho = _rho([[v - fmean(tail) for v in tail]])
        k = max(1.0, horizon / data.grid.width * (1 - rho) / (1 + rho))
        e = sd / math.sqrt(k)
        out.append({"name": r, "how": "input", "value": now[0], "sd": e, "low": max(0.0, now[0] - 2 * e), "high": now[0] + 2 * e})
    return out


def risk(spec: Spec, data: ob.Data, run: sim.Run, horizon: float, points: int, models: dict[str, BlockModel],
         start: Start | None = None, estimates: dict | None = None, params: dict | None = None, inputs: str = "hold",
         whatif: WhatIf | None = None, runs: int = RUNS, seed: int = SEED, budget: float = BUDGET) -> dict:
    """The closed-loop projection run ``runs`` times over what it does not know (the module's docstring)."""
    runs = max(1, min(int(runs), MOST_RUNS))
    began = time.monotonic()
    unc, too_wide = sens.informative(sens.uncertain(spec, estimates))
    sets = sens.draws(unc, runs, seed) or [{} for _ in range(runs)]
    ins = inputs_uncertain(spec, data, horizon)
    rnd = random.Random(seed + 1)
    base = sim.plan(spec, params or None)
    rows: dict[str, list[list[float]]] = {}
    off_end: dict[str, list[list[int]]] = {g: [] for g in spec.goals}
    hours: dict[str, list[float]] = {g: [] for g in spec.goals}
    invalid, made, stopped = 0, 0, None
    for d in sets:
        if time.monotonic() - began > budget:
            stopped = f"stopped at {budget:g} s of wall time, after {made} of {runs} runs"
            break
        x = {r: {k: (min(1.0, max(0.0, v)) if k == "success" else max(getattr(m, k) * 0.05, v))
                 for k, se in m.se.items() if se and getattr(m, k, None) is not None
                 for v in [rnd.gauss(getattr(m, k), se)]} for r, m in models.items()}
        drew = {u["name"]: max(0.0, rnd.gauss(u["value"], u["sd"])) for u in ins}
        cr = closed(spec, data, run, horizon, sim.plan(spec, {**(params or {}), **d}), points, models, start, inputs,
                    whatif, {"models": x, "inputs": drew}, rescale=base)
        made += 1
        if not cr.valid:                                     # a run that blew up says nothing held: counted as off
            invalid += 1
            for g in spec.goals:
                off_end[g].append([1] * points)
                hours[g].append(horizon / 3600.0)
            continue
        for ref, vals in cr.values.items():
            if all(v is not None for v in vals):
                rows.setdefault(ref, []).append(vals)
        for g in spec.goals:
            off_end[g].append(cr.off_end[g])
            hours[g].append(cr.off_hours[g])
    goals = {}
    for g, ends in off_end.items():
        if ends:
            p_off = [sum(e[i] for e in ends) / len(ends) for i in range(len(ends[0]))]
            goals[g] = {"p_off": p_off, "p_off_end": p_off[-1], "expected_off": fmean(hours[g])}
    sampled = [{k: v for k, v in u.items() if k != "corr"} for u in unc] + ins
    sampled += [{"name": f"{m.block}.{k}", "how": "identified model", "value": getattr(m, k), "sd": se,
                 "low": max(0.0, getattr(m, k) - 2 * se), "high": getattr(m, k) + 2 * se}
                for m in models.values() for k, se in m.se.items() if se and getattr(m, k, None) is not None]
    return {"runs": made - invalid, "asked": runs, "made": made, "invalid": invalid, "seed": seed, "horizon": horizon,
            "bands": sens.bands(rows, (0.05, 0.25, 0.5, 0.75, 0.95)), "goals": goals, "sampled": sampled,
            "not_sampled": too_wide, "stopped": stopped, "seconds": round(time.monotonic() - began, 3),
            "tails": made - invalid >= sens.TAILS}


def risk_said(got: dict, goal: str) -> str | None:
    """A goal's risk in one line: "queue-short: off at +8h with p≈0.3; 1h12m off expected over the 8h (100 runs)"."""
    x = (got.get("goals") or {}).get(goal)
    if not x or not got.get("made"):
        return None
    h = _dur(got["horizon"] / 3600.0)
    words = f"{goal}: off at +{h} with p≈{x['p_off_end']:.2g}" if x["p_off_end"] >= 0.005 else f"{goal}: holding at +{h} in every run"
    if x["expected_off"] > 0:
        words += f"; {_dur(x['expected_off'])} off expected over the {h}"
    extra = [f"{got['invalid']} of {got['made']} runs not valid, counted as off"] if got.get("invalid") else []
    extra += [got["stopped"]] if got.get("stopped") else []
    return words + f" ({got['made']} runs{'; ' + '; '.join(extra) if extra else ''})"
