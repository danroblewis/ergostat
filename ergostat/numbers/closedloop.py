"""The model run ahead with its loops running: a closed-loop projection (SPEC §12b, §12c).

The open-loop projection (``simulate.project``) holds the blocks still, so it cannot say whether a backlog drains or a
loop holds. Here the control structure runs forward beside the stocks and flows, as system dynamics simulates a policy
(Sterman, *Business Dynamics*, ch. 1 and 21: a decision rule is part of the model, not an input to it):

- **goals and built-in blocks** are worked out by the engine's own code (``spec/engine.py``'s ``goals``,
  ``_builtins``, ``get`` and ``command_of``, on the engine's built-in blocks, ``spec/blocks.py``), on a shadow of the
  engine's state, so a closed-loop projection cannot decide otherwise than ergostat would: an ``onoff`` latches with
  its hysteresis, a cascade sets the inner setpoint, a goal turns off and back on with its tolerance;
- **machine blocks** (programs, AI agents, people, and external blocks) are not run: each is replaced by a **stand-in**,
  a model of what it does to the flow it moves, identified from the record (``identify``) and said in words:

  - a block that takes items (``takes:``, SPEC §9.5): *seats*, ``success × min(waiting, pool) / time a seat is held``,
    the time a seat is held being its runs' time, or its lease's TTL for an attempt that expired (Little's law for a
    multi-server queue);
  - a block whose flow has an equation: the equation, while the block is commanded, at most what its pool can do;
  - a block draining a stock: ``min(most it moved, waiting / time things wait)`` while commanded, the time things wait by
    Little's law over the record (the mean level over the mean outflow);
  - a block filling from outside: its rate while commanded, and while not;
  - a block whose law the model writes (``gain:``, integral action, SPEC §9.3): that law, ``gain × error`` a run;
  - anything else it sets (a setpoint, an auxiliary, a command to a machine) is held where it was, and says so.

  Where the record is too short, the stand-in is an **assumption**, flagged as such, and the projection says which.

**Risk** (``risk``): Monte Carlo over what the projection does not know, as SD Lab's and Vensim's sensitivity runs
are, but with the loops running: the model's own uncertain parameters (``sensitivity.uncertain``: a ``range:``, an
estimate's standard error), each stand-in's identified numbers by their standard errors (a rate, a time per item, a
success rate), and each input from outside the control by how much its mean over the horizon could differ from now
(its readings' spread over the square root of the horizon's buckets). It gives, for each goal, the probability that it
is off at the horizon and the expected time it spends off, and for each part the projection's spread. The runs are
bounded (``RUNS``, at most ``MOST_RUNS``), each run's steps are bounded (``MAX_STEPS``), and a watchdog stops the whole
at ``BUDGET`` seconds of wall time, saying how many runs it made; the draws come from a fixed seed, so the same model
and record give the same answer.

Time is in hours, as rates are; a block's own time (its ``every:``, an ``onoff``'s ``min-on``) in seconds, as the
engine keeps it."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from ..spec import engine as en
from ..spec.blocks import make as make_builtin
from ..spec.blocks import order as builtin_order
from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

MIN_RUNS = 5                # a block's runs on record, at least, before its time per item and success are identified
MIN_BUCKETS = 6             # buckets with the block commanded and its flow measured, at least, before a rate is
MAX_STEPS = 4000            # integration steps in one closed-loop run, at most
MIN_STEPS = 4               # ... and at least this many in each point drawn
RUNS = 100                  # Monte Carlo runs of the risk, by default ...
MOST_RUNS = 400             # ... and at most
BUDGET = 15.0               # seconds of wall time the risk may take; past it, it stops and says how many runs it made
MOST_HORIZON = 30 * 86400.0  # a closed-loop projection looks at most this far ahead (seconds)
SEED = 20261118
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)


# ---- the stand-ins: what each machine block does to its flow, identified from the record

@dataclass
class StandIn:
    """What a machine block does to one flow it moves, in the closed-loop projection. Rates per hour, times in hours."""

    block: str
    flow: str                          # flow.NAME
    form: str                          # seats, equation, drain, rate, law, held
    said: str = ""                     # in words, with where its numbers come from
    assumed: bool = False              # a declared assumption, not identified: the record is too short
    gate: str | None = None            # what commands it (a block), when anything does
    source: str | None = None          # the stock it drains
    rate_on: float | None = None       # per hour, while commanded (form rate)
    rate_off: float = 0.0              # per hour, while not
    tau: float | None = None           # hours a thing waits in its source before it moves it (drain)
    cap: float | None = None           # per hour, the most it moves
    seats: int | None = None           # its pool (seats)
    service: float | None = None       # hours a run takes (seats)
    success: float | None = None       # share of runs that end well
    expired: float = 0.0               # share of attempts whose lease expired (seats)
    ttl: float | None = None           # hours a silent run holds its seat before its lease expires (seats)
    gain: float | None = None          # its law's gain, per run (law)
    period: float | None = None        # hours between its runs (law)
    goal: str | None = None            # the goal whose error its law reads (law), or whose stock it fills (fill)
    target: str | None = None          # the stock it fills up to that goal's setpoint (fill)
    held: float | None = None          # per hour, the rate held (held)
    runs: int = 0                      # its runs on record
    span: float = 0.0                  # hours of record it was identified from
    se: dict[str, float] = field(default_factory=dict)   # the standard error of each identified number, for the risk

    def capacity(self, x: dict | None = None) -> float | None:
        """The most it can move an hour (seats: its pool over the time a seat is held)."""
        if self.form in ("seats", "equation") and self.seats and self.service:
            return _get(x, "seats", self.seats) / self.seat_time(x)
        return _get(x, "cap", self.cap)

    def seat_time(self, x: dict | None = None) -> float:
        e = _get(x, "expired", self.expired)
        return max(1e-9, (1.0 - e) * _get(x, "service", self.service or 0.0) + e * (self.ttl or 0.0))

    def rate(self, V: dict, on: bool, x: dict | None = None, eqv: float | None = None, dt: float = 0.0) -> float:
        """Its flow's rate now: ``V`` the moment's values, ``on`` whether it is commanded, ``x`` values drawn for a
        Monte Carlo run (else its identified ones), ``eqv`` its flow's equation worked out (form equation)."""
        if self.form == "held":
            return self.held or 0.0
        if self.form == "law":
            e = V.get(f"goal.{self.goal}.error") or 0.0
            return _get(x, "gain", self.gain) * e / max(self.period or 1.0, 1e-9) if on else 0.0
        if not on:
            return self.rate_off
        if self.form == "rate":
            return max(0.0, _get(x, "rate_on", self.rate_on or 0.0))
        if self.form == "equation":
            v = max(0.0, eqv or 0.0)
            cap = self.capacity(x)
            return min(v, cap) if cap is not None else v
        if self.form == "fill":
            room = max(0.0, (V.get(f"goal.{self.goal}") or 0.0) - (V.get(f"stock.{self.target}") or 0.0))
            v = room / max(_get(x, "tau", self.tau or 1e-9), dt, 1e-9)
            cap = _get(x, "cap", self.cap)
            return min(v, max(0.0, cap)) if cap is not None else v
        waiting = max(0.0, V.get(f"stock.{self.source}") or 0.0) if self.source else 0.0
        if self.form == "seats":
            busy = min(waiting, _get(x, "seats", self.seats or 1)) if self.source else _get(x, "seats", self.seats or 1)
            return _get(x, "success", self.success if self.success is not None else 1.0) * busy / self.seat_time(x)
        v = waiting / max(_get(x, "tau", self.tau or 1e-9), 1e-9)               # drain
        cap = _get(x, "cap", self.cap)
        return min(v, cap) if cap is not None else v

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {}, "")}


def _get(x: dict | None, k: str, default):
    v = (x or {}).get(k)
    return default if v is None else v


def _dur(hours: float | None) -> str:
    from ..durations import human
    return "?" if hours is None else human(hours * 3600.0)


def _rate(v: float | None) -> str:
    if v is None:
        return "?"
    return f"{v:.3g}/h" if v >= 0.1 or v == 0 else f"{v * 24:.3g}/day"


def _quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0]
    k = q * (len(xs) - 1)
    i = int(k)
    return xs[i] if i + 1 >= len(xs) else xs[i] + (xs[i + 1] - xs[i]) * (k - i)


def _mean_sd(xs: list[float]) -> tuple[float, float]:
    m = sum(xs) / len(xs)
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))


def actuated(spec: Spec) -> dict[str, str]:
    """Each flow a block moves → the block (the first, as ``Spec.actuator_of``)."""
    out = {}
    for f in spec.flows:
        b = spec.actuator_of(f)
        if b is not None:
            out[f"flow.{f}"] = b.name
    return out


def has_controllers(spec: Spec) -> bool:
    """Whether the model has loops a closed-loop projection would run: a block that moves a flow, or a built-in that
    decides (an ``onoff``, a cascade), other than the judge of changes to the model."""
    return any(b.type != "judge" and (any(t.kind in ("flow", "block", "goal") for t in b.targets()))
               for b in spec.blocks.values())


def _gate_series(p, spec: Spec, block: str, since: float, until: float) -> list[tuple[float, float]] | None:
    """When a built-in commander's output changed, over the span: what says when the block was commanded."""
    cs = [c for c in spec.commanders_of(block) if c.builtin]
    if not cs:
        return None
    pts: list[tuple[float, float]] = []
    for c in cs:
        before = p.measurements.latest(f"block/{c.name}", before=since)
        if before:
            pts.append((since, before[1]))
        pts += p.measurements.range(f"block/{c.name}", since, until)
    return sorted(pts) if pts else []


def _on_at(pts: list[tuple[float, float]] | None, times: list[float]) -> list[bool]:
    """Whether the block was commanded at each of these (sorted) moments: the commander's last output before each."""
    if pts is None:
        return [True] * len(times)
    out, j, last = [], 0, None
    for t in times:
        while j < len(pts) and pts[j][0] <= t:
            last = pts[j][1]
            j += 1
        out.append(bool(last))
    return out


def _runs(p, block: str, since: float, until: float) -> list[dict]:
    return p.events.query(n=None, type="agent.ran,agent.failed", item=block, since=since, until=until)


def identify(p, spec: Spec, data: ob.Data | None = None) -> dict[str, StandIn]:
    """Each flow a machine block moves → its stand-in, identified from the record on ``data``'s grid (the reference
    window when none is given)."""
    data = data or ob.measured(p, ob.reference(p))
    g = data.grid
    span_h = (g.until - g.since) / 3600.0
    times = g.times()
    out: dict[str, StandIn] = {}
    for ref, block in actuated(spec).items():
        b = spec.blocks[block]
        if b.builtin:
            continue                                        # a built-in moves its flow itself: run as the engine does
        f = spec.flows[ref[5:]]
        several = sum(1 for t in b.targets() if t.kind == "flow") > 1
        name = f"{block} (on {f.name})" if several else block   # how it is said: which of its flows, when it moves several
        cs = spec.commanders_of(block)
        gate = cs[0].name if cs else None
        runs = _runs(p, block, g.since, g.until)
        s = StandIn(block, ref, "rate", gate=gate, source=f.source, runs=len(runs), span=span_h)
        gated = f" while {gate} commands it" if gate else ""
        pts = _gate_series(p, spec, block, g.since, g.until)
        vals = data.values.get(ref) or []
        lvl = data.values.get(f"stock.{f.source}") if f.source else None
        gate_on = _on_at(pts, times)
        on_b = [i for i in range(len(times)) if gate_on[i] and i < len(vals) and vals[i] is not None]
        off_b = [i for i in range(len(times)) if not gate_on[i] and i < len(vals) and vals[i] is not None]
        moved_off = sum(vals[i] for i in off_b)
        if gate and len(on_b) < MIN_BUCKETS <= len(off_b) and moved_off > 0 and not b.takes:
            # it moved while nothing commanded it (a person answers before being asked): its flow is not its command's
            on_b, off_b, s.gate = sorted(on_b + off_b), [], None
            gated = f" whether or not {gate} commands it (it moved {moved_off * data.grid.width / 3600:.3g} while not commanded)"
        ok = [r for r in runs if r["type"] == "agent.ran"]
        took = [r for r in runs if (r.get("data") or {}).get("item")]
        if b.takes:
            from ..leases import EXPIRED
            from ..leases.terms import terms
            t = terms(spec, b)
            s.seats, s.ttl = b.pool, t["ttl"] / 3600.0
            if len(took) >= MIN_RUNS:
                secs = [float((r.get("data") or {}).get("seconds") or 0.0) for r in took]
                m, sd = _mean_sd(secs)
                med = _quantile(secs, 0.5)
                good = sum(1 for r in took if r["type"] == "agent.ran" and not (r.get("data") or {}).get("nack"))
                exp = sum(1 for e in p.events.query(n=None, type=EXPIRED, since=g.since, until=g.until)
                          if (e.get("data") or {}).get("block") == block)
                s.service, s.success = med / 3600.0, good / len(took)
                s.expired = min(1.0, exp / (len(took) + exp)) if exp else 0.0
                s.se = {"service": sd / math.sqrt(len(took)) / 3600.0,
                        "success": math.sqrt(max(s.success * (1 - s.success), 0.25 / len(took)) / len(took))}
                s.form = "seats"
            else:
                s.form, s.assumed = "seats", True
                s.service, s.success = (b.every or min(t["ttl"] / 4.0, 600.0)) / 3600.0, 1.0
        if f.equation is not None:
            s.form = "equation"
            cap = f" at most {_rate(s.capacity())} ({s.seats} at once, {_dur(s.service)} a run)" if s.seats and s.service else ""
            s.said = f"{name} modelled by {f.name}'s equation ({f.equation.text}){gated}{cap}"
            if s.assumed and cap:
                s.said += f"; the time a run takes is assumed (only {len(took)} runs on record, at least {MIN_RUNS})"
            out[ref] = s
            continue
        if s.form == "seats":
            words = (f"{name} modelled as {_rate(1.0 / s.seat_time() * (s.success or 1.0))} a seat "
                     f"({_dur(s.service)} a run), {s.seats} seat{'s' if s.seats != 1 else ''}, "
                     f"{round((s.success or 0) * 100)}% success")
            if s.expired:
                words += f", {round(s.expired * 100)}% of attempts expiring at its lease ({_dur(s.ttl)})"
            s.said = words + (f", taking from {f.source}" if f.source else "") + gated + \
                (f"; assumed: only {len(took)} runs on record (at least {MIN_RUNS}), a run taken as {_dur(s.service)}"
                 if s.assumed else f", from {_dur(span_h)} of record ({len(took)} runs)")
            out[ref] = s
            continue
        params = b.params or {}
        reads_goal = next((r.name for r in b.reads() if r.kind == "goal"), None) or b.goal
        if params.get("gain") is not None and reads_goal and b.every:
            s.form, s.gain, s.period, s.goal = "law", float(params["gain"]), b.every / 3600.0, reads_goal
            s.said = f"{name} modelled by its law as written: a step of {params['gain']:g} × {reads_goal}'s error every {_dur(s.period)}"
            out[ref] = s
            continue
        holds = next((gl for gl in spec.goals.values() if f.target and str(gl.of) == f"stock.{f.target}"
                      and gl.name in {r.name for r in b.reads() if r.kind == "goal"} and gl.name != b.goal), None)
        rates_on = [vals[i] for i in on_b]
        if holds is not None:                               # it reads the goal on what it fills: never past its setpoint
            s.form, s.goal, s.target = "fill", holds.name, f.target
            s.tau = (b.every or data.grid.width) / 3600.0
            if len(rates_on) >= MIN_BUCKETS and any(rates_on):
                m, sd = _mean_sd(rates_on)
                s.cap = _quantile(rates_on, 0.95) if f.source else m
                s.se = {"cap": sd / math.sqrt(len(rates_on))}
                how = (f"at most {_rate(s.cap)} ({'the most it moved' if f.source else 'its rate'}{gated}, from "
                       f"{_dur(span_h)} of record)")
            else:
                s.assumed = True
                how = f"as fast as its runs allow (assumed: the record has {len(rates_on)} buckets of it, at least {MIN_BUCKETS})"
            s.said = (f"{name} modelled as moving {how}{', taking from ' + f.source if f.source else ''}, and never past "
                      f"{holds.name}'s setpoint on {f.target} (it reads that goal), each of its runs every {_dur(s.tau)}")
            out[ref] = s
            continue
        if f.source and lvl:
            pairs = [(lvl[i], vals[i]) for i in on_b if i < len(lvl) and lvl[i] is not None]
            moved = sum(v for _, v in pairs)
            if len(pairs) >= MIN_BUCKETS and moved > 0:
                level = sum(x for x, _ in pairs)
                s.form, s.tau = "drain", max(level / moved, 1e-6)
                rs = [v for _, v in pairs]
                s.cap = _quantile(rs, 0.95) if max(rs) > 0 else None
                m, sd = _mean_sd(rs)
                s.se = {"tau": s.tau * (sd / m if m > 0 else 1.0) / math.sqrt(len(rs))}
                if s.cap:
                    s.se["cap"] = sd / math.sqrt(len(rs))
                s.rate_off = (sum(vals[i] for i in off_b) / len(off_b)) if len(off_b) >= MIN_BUCKETS else 0.0
                s.said = (f"{name} modelled as draining {f.source}: what waits there moves in {_dur(s.tau)} on average"
                          f"{(', at most ' + _rate(s.cap)) if s.cap else ''}{gated}, from {_dur(span_h)} of record "
                          f"({len(pairs)} buckets{', ' + str(len(runs)) + ' runs' if runs else ''}"
                          f"{', ' + str(round(100 * len(ok) / len(runs))) + '% ending well' if runs else ''})")
                out[ref] = s
                continue
        if len(rates_on) >= MIN_BUCKETS and not any(rates_on):   # measured long enough, and it moved nothing
            s.form, s.rate_on = "rate", 0.0
            s.said = f"{name} moved nothing along {f.name}{gated} in {_dur(span_h)} of record ({len(rates_on)} buckets): modelled as 0"
            out[ref] = s
            continue
        if not f.source and len(rates_on) >= MIN_BUCKETS:
            m, sd = _mean_sd(rates_on)
            s.form, s.rate_on, s.se = "rate", m, {"rate_on": sd / math.sqrt(len(rates_on))}
            s.rate_off = (sum(vals[i] for i in off_b) / len(off_b)) if len(off_b) >= MIN_BUCKETS else 0.0
            s.said = (f"{name} modelled as {_rate(m)}{gated}"
                      f"{', ' + _rate(s.rate_off) + ' otherwise' if gate and s.rate_off else ''}, from {_dur(span_h)} of record")
            out[ref] = s
            continue
        s.assumed = True                                    # too little record: a declared assumption
        if f.source:
            s.form, s.tau = "drain", (b.every or 60.0) / 3600.0
            s.said = (f"{name} assumed to move what waits in {f.source} within one of its runs ({_dur(s.tau)}){gated}: "
                      f"the record has {len(on_b)} buckets of it{' commanded' if gate else ''} (at least {MIN_BUCKETS})")
        else:
            s.form, s.rate_on = "rate", float(f.rate or 0.0)
            s.said = (f"{name} assumed to move {_rate(s.rate_on)}{gated} ({'its declared rate' if f.rate else 'nothing known'}): "
                      f"the record has {len(on_b)} buckets of it (at least {MIN_BUCKETS})")
        out[ref] = s
    return out


def held_by_blocks(spec: Spec) -> list[str]:
    """What machine blocks set that the closed-loop projection holds where it was: a setpoint, an auxiliary, a command
    to another machine block."""
    out = []
    for b in spec.blocks.values():
        if b.builtin or b.type == "judge":
            continue
        for t in b.targets():
            if t.kind == "goal":
                out.append(f"{b.name} sets goal {t.name}'s setpoint: held where it was")
            elif t.kind == "auxiliary":
                out.append(f"{b.name} sets {t.name}: held where it was")
            elif t.kind == "block" and t.name in spec.blocks and not spec.blocks[t.name].builtin:
                out.append(f"{b.name} commands {t.name}: its command held where it was")
    return out


# ---- the control structure's state now, from the record

@dataclass
class Start:
    """Where the control structure is now: each goal's status, each setpoint a block set, each built-in's last output
    and when it changed (epoch seconds)."""

    status: dict[str, str] = field(default_factory=dict)
    setpoint: dict[str, float] = field(default_factory=dict)
    outputs: dict[str, tuple[float, float]] = field(default_factory=dict)


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
    for name, b in spec.blocks.items():
        if b.builtin and b.type != "judge":
            got = p.measurements.latest(f"block/{name}", before=at)
            if got:
                st.outputs[name] = (got[0], got[1])
    return st


class _Spec:
    """The model as the shadow reads it: the spec itself, but who commands each block worked out once (the engine
    asks at every pass; in a projection that is thousands of times)."""

    def __init__(self, spec: Spec):
        self._spec, self._commanders = spec, {}
        self.goals, self.blocks = spec.goals, spec.blocks

    def __getattr__(self, name):
        return getattr(self._spec, name)

    def commanders_of(self, block: str):
        got = self._commanders.get(block)
        if got is None:
            got = self._commanders[block] = self._spec.commanders_of(block)
        return got


class Shadow:
    """The engine's control state without its machinery: the engine's own methods (``goals``, ``_builtins``, ``get``,
    ``command_of``) run on it, so what a built-in decides here is what it would decide there."""

    get = en.Engine.get
    goals = en.Engine.goals
    _builtins = en.Engine._builtins
    _downstream = en.Engine._downstream
    _builtin_wiring = en.Engine._builtin_wiring
    _event = en.Engine._event
    decided = en.Engine.decided
    command_of = en.Engine.command_of

    def __init__(self, spec: Spec, signals: dict, start: Start | None = None, setpoints: dict | None = None):
        self.spec, self.signals = _Spec(spec), signals
        self.builtins = {n: make_builtin(spec.blocks[n], spec) for n in builtin_order(spec)}
        self.status: dict[str, str] = dict(start.status if start else {})
        self.setpoint: dict[str, float] = dict(start.setpoint if start else {})
        self.fixed = dict(setpoints or {})                  # a what-if's setpoints: a cascade does not move them
        self.setpoint.update(self.fixed)
        self.outputs: dict[str, dict[str, float]] = {}
        self.commands: dict[str, dict] = {}
        self.cause: dict[str, str] = {}
        for n, (t, v) in ((start.outputs if start else {}) or {}).items():
            if n in self.builtins:
                self.builtins[n].out, self.builtins[n].changed_at = v, t
                signals[f"block.{n}"] = v

    def say(self, _text: str) -> None:
        pass

    def step(self, now: float) -> None:
        """One pass, as ``Engine.evaluate`` makes it with everything worked out: goals, then the built-ins in their
        order, then the goals whose setpoint a built-in moved."""
        events: list = []
        self.goals(now, out=events)
        _, set_goals, _ = self._builtins(now, None, {}, events, [])
        if self.fixed:
            self.setpoint.update(self.fixed)
        if set_goals:
            self.goals(now, out=events)

    def on(self, block: str) -> bool:
        """Whether a machine block is commanded now (one nothing commands runs on its own: always)."""
        cmd, _ = self.command_of(self.spec.blocks[block])
        return True if cmd is None else bool(cmd)


# ---- the closed-loop run

@dataclass
class ClosedRun(sim.Run):
    """A closed-loop projection: a ``simulate.Run`` with, besides, each goal's share of each point spent off, whether it
    was off at each point's end, its hours off in all, and the stand-ins it ran with."""

    off: dict[str, list[float]] = field(default_factory=dict)
    off_end: dict[str, list[int]] = field(default_factory=dict)
    off_hours: dict[str, float] = field(default_factory=dict)
    standins: dict[str, StandIn] = field(default_factory=dict)


@dataclass
class WhatIf:
    """What a what-if changes beyond a parameter: an input's rate (per hour, or ``×`` a multiple of its mean over the
    window: ``x2``, arrivals doubled), a goal's setpoint, a block's pool."""

    flows: dict[str, tuple[str, float]] = field(default_factory=dict)    # flow.NAME → ("=", rate) or ("x", factor)
    setpoints: dict[str, float] = field(default_factory=dict)            # goal → setpoint
    pools: dict[str, int] = field(default_factory=dict)                   # block → pool

    def __bool__(self) -> bool:
        return bool(self.flows or self.setpoints or self.pools)

    def key(self) -> tuple:
        return (tuple(sorted(self.flows.items())), tuple(sorted(self.setpoints.items())), tuple(sorted(self.pools.items())))

    def said(self) -> list[str]:
        out = [f"{r[5:]} {'×' + format(v, 'g') + ' its mean' if how == 'x' else 'at ' + _rate(v)}" for r, (how, v) in self.flows.items()]
        out += [f"goal {g} at {v:g}" for g, v in self.setpoints.items()]
        out += [f"{b}'s pool {n}" for b, n in self.pools.items()]
        return out


class WhatIfError(ValueError):
    pass


def parse_whatif(spec: Spec, raw: dict[str, str]) -> tuple[dict[str, str], WhatIf]:
    """Split a what-if's names: parameters (returned as they came, for ``proposals.what_if``) from ``flow.NAME`` (an
    input's rate per hour, or ``x2`` for twice it), ``goal.NAME`` (its setpoint) and ``block.NAME.pool``."""
    params, w = {}, WhatIf()
    for k, v in raw.items():
        v = str(v).strip()
        if k.startswith("flow."):
            if k[5:] not in spec.flows:
                raise WhatIfError(f"no flow {k[5:]}")
            try:
                w.flows[k] = ("x", float(v[1:])) if v[:1] in ("x", "×", "*") else ("=", float(v))
            except ValueError:
                raise WhatIfError(f"{k}: {v!r} is a rate per hour, or x2 for twice what it is") from None
            if w.flows[k][1] < 0:
                raise WhatIfError(f"{k}: a rate below 0")
        elif k.startswith("goal."):
            if k[5:] not in spec.goals:
                raise WhatIfError(f"no goal {k[5:]}")
            try:
                w.setpoints[k[5:]] = float(v)
            except ValueError:
                raise WhatIfError(f"{k}: {v!r} is not a number") from None
        elif k.startswith("block.") and k.endswith(".pool"):
            b = spec.blocks.get(k[6:-5])
            if b is None or not b.takes:
                raise WhatIfError(f"{k[6:-5]} is not a block that takes items: it has no pool")
            try:
                n = int(float(v))
            except ValueError:
                raise WhatIfError(f"{k}: {v!r} is not a number of runs at once") from None
            if n < 1:
                raise WhatIfError(f"{k}: a pool of at least 1")
            w.pools[k[6:-5]] = n
        else:
            params[k] = v
    return params, w


def closed(spec: Spec, data: ob.Data, run: sim.Run, horizon: float, pl: sim.Plan | None = None, points: int | None = None,
           standins: dict[str, StandIn] | None = None, start: Start | None = None, inputs: str = "hold",
           whatif: WhatIf | None = None, draw: dict | None = None, rescale: sim.Plan | None = None,
           max_steps: int = MAX_STEPS) -> ClosedRun:
    """From now (``data.grid.until``) for ``horizon`` seconds, with the loops running: the stocks from their last
    readings, delays as the replay left them, the goals and built-ins from ``start`` (where the record left them), each
    machine block's flow from its stand-in, every other input held where it was (or along its trend). ``draw`` is a
    Monte Carlo run's values: ``{"standins": {flow: {name: value}}, "inputs": {ref: rate}}``."""
    whatif = whatif or WhatIf()
    standins = {r: s for r, s in (standins or {}).items() if r not in whatif.flows}   # a rate tried replaces its stand-in
    draw = draw or {}
    horizon = min(horizon, MOST_HORIZON)
    base = pl or sim.plan(spec)
    act = actuated(spec)
    # a flow a machine block moves whose equation the stand-in runs itself (gated, capped) is taken out of the plan
    gated = {r for r, s in standins.items() if s.form == "equation" and r in base.eqs and not base.eqs[r].slots}
    pl = sim.plan(spec, base.params, given=gated) if gated else base
    own = {r: base.eqs[r] for r in gated}
    g = data.grid
    n = points or max(2, round(horizon / g.width))
    step = horizon / n
    times = [g.until + (i + 1) * step for i in range(n)]
    saved = {r: dict(c.faults) for r, c in pl.eqs.items()}
    for c in pl.eqs.values():
        c.faults.clear()
    st = sim._Stepper(pl, pl.integrate)
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
        tr = sim._trend(vals, ts)
        if tr is not None:
            ahead[r] = (tr[0], tr[1] if inputs == "trend" else 0.0)
    for r, (how, v) in whatif.flows.items():                # an input's rate tried: held there (x2: twice its mean)
        seen = [x for x in data.values.get(r) or [] if x is not None]
        ahead[r] = (v if how == "=" else v * (sum(seen) / len(seen) if seen else 0.0), 0.0)
    for r, v in (draw.get("inputs") or {}).items():
        if r in ahead and r not in whatif.flows:
            ahead[r] = (v, ahead[r][1])
    one_way = {f"flow.{f.name}" for f in spec.flows.values() if not f.two_way}
    for r in data.values:
        V[r] = 0.0
    machine_flows = {r: b for r, b in act.items() if r in standins}
    for r, (v0, _) in ahead.items():
        if r not in machine_flows:
            V[r] = max(0.0, v0) if r in one_way and v0 >= 0 else v0
    moving = [(r, v0, slope) for r, (v0, slope) in ahead.items() if r not in machine_flows and (slope or inputs != "hold")]
    # an outflow held where it was stops when its stock is empty: nothing leaves an empty stock (Sterman ch. 21's first
    # extreme condition); an equation's outflow is the model's own and is left as it writes it
    drains = {r: spec.flows[r[5:]].source for r in ahead if r.startswith("flow.") and r not in machine_flows
              and r not in pl.eqs and r in one_way and spec.flows.get(r[5:]) and spec.flows[r[5:]].source
              and spec.flows[r[5:]].source in state}
    want = {r: V.get(r, 0.0) for r in drains}
    moving_refs = {m[0] for m in moving}
    # the goals and built-ins read the levels as the engine's sensors would: a count of items is a whole number (a
    # queue drained to a fraction of an item is empty), so a goal "<= 0" on a queue holds once it is
    counted = {f"stock.{n}" for n, x in spec.stocks.items()
               if x.sensors and all(z.items and z.items.get("measure") in (None, "count") for z in x.sensors.values())}
    reads = {str(gl.of) for gl in spec.goals.values()} | \
        {str(r) for b in spec.blocks.values() if b.builtin for r in b.inputs.values() if r.kind in ("stock", "flow", "auxiliary")}
    G: dict = {}
    sh = Shadow(spec, G, start, whatif.setpoints)
    told = [f"goal.{s.goal}{k}" for s in standins.values() if s.goal for k in ("", ".error", ".off")]
    blocks_on = sorted({s.block for s in standins.values() if s.block in spec.blocks})

    def shadow_step(t: float) -> None:
        for r in reads:
            v = V.get(r)
            if v is None:
                G.pop(r, None)
            else:
                G[r] = math.floor(v + 0.5) if r in counted else v
        sh.step(t)
        for k in told:
            V[k] = G.get(k)
    drawn = draw.get("standins") or {}
    for r, s in standins.items():                           # a pool tried: the stand-in's seats
        if s.block in whatif.pools:
            drawn = {**drawn, r: {**(drawn.get(r) or {}), "seats": whatif.pools[s.block]}}

    def inputs_at(t: float) -> None:
        h = (t - g.until) / 3600.0
        for r, v0, slope in moving:
            v = v0 + slope * h
            V[r] = max(0.0, v) if r in one_way and v0 >= 0 else v
        for s in pl.integrate:
            V[f"stock.{s}"] = state[s] if state[s] is not None else 0.0
        for r in drains:
            if r in moving_refs:
                want[r] = V[r]

    def control(t: float, dt: float) -> None:
        """The goals and the built-ins, as the engine works them out; then each machine block's flow by its stand-in
        (a flow it drains never takes more than its stock holds in a step)."""
        shadow_step(t)
        for r, src in drains.items():
            x = state.get(src)
            V[r] = min(want[r], max(0.0, x) / dt) if x is not None and dt > 0 else want[r]
        ons = {b: sh.on(b) for b in blocks_on}
        for r, s in standins.items():
            on = ons.get(s.block, True) if s.gate else True
            eqv = None
            if r in own:
                try:
                    eqv = own[r].fn(V, pl.params, [], [], False)
                except (OverflowError, ValueError, ZeroDivisionError):
                    eqv = 0.0
            v = s.rate(V, on, drawn.get(r), eqv, dt)
            if r in one_way:
                v = max(0.0, v)
                src = spec.flows[r[5:]].source
                if src and state.get(src) is not None and dt > 0:
                    v = min(v, max(0.0, state[src]) / dt)
            V[r] = v

    t = g.until
    inputs_at(t)
    st.evaluate()
    if rescale is not None:
        sim._rescale(pl, rescale, st)
        st.evaluate()
    k, _ = sim._substeps(st.rates(state), step / 3600.0)
    fastest = min((s.tau for s in standins.values() if s.form == "drain" and s.tau), default=None)
    if fastest:
        k = max(k, math.ceil(step / 3600.0 / fastest))     # a drain is stepped at least once per its time
    k = max(MIN_STEPS, min(k, max(1, max_steps // n)))
    dt = step / 3600.0 / k
    out: dict[str, list[float | None]] = {f"stock.{s}": [None] * n for s in pl.integrate} | \
        {r: [None] * n for r in pl.eqs} | {r: [None] * n for r in standins}
    off = {name: [0.0] * n for name in spec.goals}
    off_end = {name: [0] * n for name in spec.goals}
    hours = dict.fromkeys(spec.goals, 0.0)
    for i in range(n):
        acc = dict.fromkeys(standins, 0.0)
        for _ in range(k):
            inputs_at(t)
            control(t, dt)
            st.evaluate(dt)
            for name in spec.goals:
                if G.get(f"goal.{name}.off"):
                    off[name][i] += 1.0 / k
                    hours[name] += dt
            for r in standins:
                acc[r] += V[r] / k
            st.step(state, dt)
            t += step / k
        inputs_at(t)
        st.evaluate()
        shadow_step(t)
        for s in pl.integrate:
            out[f"stock.{s}"][i] = state[s]
        for r in pl.eqs:
            out[r][i] = V[r]
        for r in standins:
            out[r][i] = acc[r]
        for name in spec.goals:
            off_end[name][i] = 1 if G.get(f"goal.{name}.off") else 0
    notes = [f"with the loops running: the goals and built-in blocks worked out as the engine does, each machine block "
             f"by its stand-in; inputs {'held where they were' if inputs == 'hold' else 'carried on along their trend'}"]
    assumed = [s.block for s in standins.values() if s.assumed]
    if assumed:
        notes.append(f"assumed, not identified (too little record): {', '.join(sorted(set(assumed)))}")
    if whatif:
        notes.append("what if " + ", ".join(whatif.said()))
    how = {f"stock.{s}": "integrated" for s in pl.integrate} | {r: "equation" for r in pl.eqs} | \
        {r: "stand-in" for r in standins}
    counted = st.counted()
    for r, c in pl.eqs.items():
        c.faults.clear()
        c.faults.update(saved[r])
    return ClosedRun(times, out, how, notes + st.clamps(), {s: v for s, v in state.items() if v is not None}, st.S,
                     steps=n * k, invalid=st.clamps(), faults=counted, off=off, off_end=off_end, off_hours=hours,
                     standins=standins)


# ---- risk: Monte Carlo over what is not known, with the loops running

def inputs_uncertain(spec: Spec, data: ob.Data, horizon: float) -> list[dict]:
    """Each input from outside the control (a flow no equation works out and no block moves: an arrival, a measured
    rate) and how its mean over the horizon could differ from now: its readings' spread over the square root of the
    buckets the horizon spans (the standard error of a mean over that many buckets)."""
    act = actuated(spec)
    out = []
    width = data.grid.width
    k = max(1.0, horizon / width)
    for name, f in spec.flows.items():
        r = f"flow.{name}"
        if f.equation is not None or r in act:
            continue
        vals = [v for v in (data.values.get(r) or []) if v is not None]
        if len(vals) < MIN_BUCKETS:
            continue
        tail = vals[-max(MIN_BUCKETS, len(vals) // 4):]
        _, sd = _mean_sd(tail)
        now = sim._trend(data.values[r], data.grid.times())
        if sd <= 0 or now is None:
            continue
        m, e = now[0], sd / math.sqrt(k)                    # about where the projection holds it
        out.append({"name": r, "how": "input", "value": m, "sd": e, "low": max(0.0, m - 2 * e), "high": m + 2 * e})
    return out


WIDEST = math.log(10.0)     # an estimate whose standard error is wider than a factor of ten bounds nothing: held


def informative(unc: list[dict]) -> tuple[list[dict], list[str]]:
    """The uncertain parameters the risk samples, and those it holds at their value because their estimate's error
    spans more than a factor of ten either way (sampled, they would make every run a different model)."""
    keep, held = [], []
    for u in unc:
        if u["how"] == "estimate" and ((u.get("logged") and u.get("sd", 0) > WIDEST) or
                                       (not u.get("logged") and u.get("sd", 0) > 10 * abs(u.get("value") or 0))):
            held.append(u["name"])
        else:
            keep.append(u)
    return keep, held


def risk(spec: Spec, data: ob.Data, run: sim.Run, horizon: float, points: int, standins: dict[str, StandIn],
         start: Start | None = None, estimates: dict | None = None, params: dict | None = None, inputs: str = "hold",
         whatif: WhatIf | None = None, runs: int = RUNS, seed: int = SEED, budget: float = BUDGET) -> dict:
    """The closed-loop projection run ``runs`` times over what it does not know (the module's docstring): for each goal
    the probability it is off at the horizon, at each point, and its expected hours off; for each part its spread."""
    from . import sensitivity as sens
    runs = max(1, min(int(runs), MOST_RUNS))
    began = time.monotonic()
    unc, too_wide = informative(sens.uncertain(spec, estimates))
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
        x: dict = {}
        for r, s in standins.items():
            got = {}
            for key, se in s.se.items():
                v0 = getattr(s, key, None)
                if v0 is None or not se:
                    continue
                v = rnd.gauss(v0, se)
                got[key] = min(1.0, max(0.0, v)) if key == "success" else max(v0 * 0.05, v)
            if got:
                x[r] = got
        drew = {u["name"]: max(0.0, rnd.gauss(u["value"], u["sd"])) for u in ins}
        pl = sim.plan(spec, {**(params or {}), **d})
        cr = closed(spec, data, run, horizon, pl, points, standins, start, inputs, whatif,
                    {"standins": x, "inputs": drew}, rescale=base)
        made += 1
        if not cr.valid:
            invalid += 1
            continue
        for ref, vals in cr.values.items():
            if all(v is not None for v in vals):
                rows.setdefault(ref, []).append(vals)
        for gname in spec.goals:
            off_end[gname].append(cr.off_end[gname])
            hours[gname].append(cr.off_hours[gname])
    ok = made - invalid
    bands = {}
    for ref, rs in rows.items():
        if len(rs) < 2:
            continue
        cols = [sorted(c) for c in zip(*rs, strict=True)]
        bands[ref] = {f"p{round(q * 100)}": [_quantile(c, q) for c in cols] for q in QUANTILES
                      if len(rs) >= sens.TAILS or 0.1 < q < 0.9}
    goals = {}
    for gname in spec.goals:
        ends = off_end[gname]
        if not ends:
            continue
        p_off = [sum(e[i] for e in ends) / len(ends) for i in range(len(ends[0]))]
        goals[gname] = {"p_off": p_off, "p_off_end": p_off[-1], "expected_off": sum(hours[gname]) / len(hours[gname])}
    sampled = [{k: v for k, v in u.items() if k != "corr"} for u in unc] + ins
    for s in standins.values():
        for key, se in s.se.items():
            if se and getattr(s, key, None) is not None:
                v0 = getattr(s, key)
                sampled.append({"name": f"{s.block}.{key}", "how": "stand-in", "value": v0, "sd": se,
                                "low": max(0.0, v0 - 2 * se), "high": v0 + 2 * se})
    return {"runs": ok, "asked": runs, "made": made, "invalid": invalid, "seed": seed, "horizon": horizon,
            "bands": bands, "goals": goals, "sampled": sampled, "not_sampled": too_wide, "stopped": stopped,
            "seconds": round(time.monotonic() - began, 3), "tails": ok >= sens.TAILS}


def risk_said(spec: Spec, got: dict, goal: str) -> str | None:
    """A goal's risk in one line: "queue-short: off at +8h with p≈0.3; 1.2h off expected"."""
    x = (got.get("goals") or {}).get(goal)
    if not x or not got.get("runs"):
        return None
    p = x["p_off_end"]
    words = f"{goal}: off at +{_dur(got['horizon'] / 3600.0)} with p≈{p:.2g}" if p >= 0.005 else \
        f"{goal}: holding at +{_dur(got['horizon'] / 3600.0)} in every run"
    if x["expected_off"] > 0:
        words += f"; {_dur(x['expected_off'])} off expected over the {_dur(got['horizon'] / 3600.0)}"
    return words + f" ({got['runs']} runs{', ' + got['stopped'] if got.get('stopped') else ''})"
