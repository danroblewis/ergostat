"""What each machine block does to the flow it moves, identified from the record: the **identified model** the
closed-loop projection runs in its place (closedloop.py; SPEC §12b). A program, an AI agent or a person is not run
ahead; what the record says it did is (Ljung, *System Identification*: a model of the input-output behaviour, with
its uncertainty). The forms, by what the model and the record say of the block:

- **servers** (a block that takes items, SPEC §9.5): a multi-server queue, ``success × min(waiting, servers) / the
  time a server is held``, the time a server is held being a run's median time, or its lease's TTL for an attempt
  that expired;
- **equation**: its flow's own equation, while the block is commanded, at most its servers over their time;
- **fill**: a block reading the goal on the stock it fills (a dispatcher reading its work-in-progress limit) moves at
  most the 95th percentile of its rate, and never past that goal's setpoint;
- **drain**: ``min(95th percentile of its rate, waiting / residence time)`` while commanded, the residence time (the
  time in system) by Little's law over the buckets it was commanded: mean level over mean outflow;
- **rate**: its mean rate while commanded, and while not;
- **law**: a law the model writes (``gain:``, integral action, SPEC §9.3), with its deadband, resolution and limits;
- anything else it sets (a setpoint, an auxiliary, a command to a machine) is held where it was (``held_by_blocks``).

Each number carries its standard error, for the risk. Where the record is too short the model is a declared
**assumption**, flagged as one. A block that moved its flow while nothing commanded it (a person answering before
being asked) is modelled ungated. Rates per hour, times in hours."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import fmean, median, stdev

from ..spec.ir import Spec
from . import observe as ob
from .sensitivity import quantile

MIN_RUNS = 5                # a block's runs on record, at least, before its run time and success are identified
MIN_BUCKETS = 6             # buckets with the block commanded and its flow measured, at least, before a rate is


@dataclass
class BlockModel:
    """A machine block's identified model of one flow it moves."""

    block: str
    flow: str                          # flow.NAME
    form: str = "rate"                 # servers, equation, fill, drain, rate, law
    label: str = ""                    # how it is named in words (the block, and its flow when it moves several)
    assumed: str = ""                  # why it is an assumption, when it is one (the record too short)
    gate: str | None = None            # what commands it (a block), when anything does
    gating: str = ""                   # in words: " while keep-x commands it", or why it is ungated
    basis: str = ""                    # in words: what it was identified from
    source: str | None = None          # the stock it drains
    target: str | None = None          # the stock it fills (fill, law)
    rate_on: float | None = None       # per hour, while commanded (rate)
    rate_off: float = 0.0              # per hour, while not
    residence: float | None = None     # hours: time in system in its source (drain), or a run's period (fill)
    cap: float | None = None           # per hour: the 95th percentile of its rate (drain, fill), or its mean (fill from outside)
    servers: int | None = None         # its pool (servers)
    service: float | None = None       # hours a run takes (servers)
    success: float | None = None       # share of runs that end well
    expired: float = 0.0               # share of attempts whose lease expired (servers)
    ttl: float | None = None           # hours a silent run holds its server before its lease expires (servers)
    gain: float | None = None          # its law's gain, per run (law)
    period: float | None = None        # hours between its runs (law)
    deadband: float = 0.0              # its law's deadband, in its goal's error (law)
    resolution: float = 0.0            # its law's step, rounded to this (law)
    limits: tuple | None = None        # its law's setting kept within (law)
    goal: str | None = None            # the goal it reads (law, fill)
    equation: str = ""                 # its flow's equation, as written (equation)
    runs: int = 0
    se: dict[str, float] = field(default_factory=dict)   # the standard error of each identified number, for the risk

    def capacity(self, x: dict | None = None) -> float | None:
        if self.servers and self.service:
            return _get(x, "servers", self.servers) / self.server_time(x)
        return _get(x, "cap", self.cap)

    def server_time(self, x: dict | None = None) -> float:
        e = _get(x, "expired", self.expired)
        return max(1e-9, (1.0 - e) * _get(x, "service", self.service or 0.0) + e * (self.ttl or 0.0))

    def rate(self, V: dict, on: bool, x: dict | None = None, eqv: float | None = None, dt: float = 0.0) -> float:
        """Its flow's rate now: ``V`` the moment's values, ``on`` whether it is commanded, ``x`` a Monte Carlo run's
        values (else the identified ones), ``eqv`` its flow's equation worked out (equation)."""
        if self.form == "law":
            return self._law(V, x) if on else 0.0
        if not on:
            return self.rate_off
        if self.form == "rate":
            return max(0.0, _get(x, "rate_on", self.rate_on or 0.0))
        cap = self.capacity(x)
        if self.form == "equation":
            v = max(0.0, eqv or 0.0)
        elif self.form == "fill":
            room = max(0.0, (V.get(f"goal.{self.goal}") or 0.0) - (V.get(f"stock.{self.target}") or 0.0))
            v = room / max(_get(x, "residence", self.residence or 1e-9), dt, 1e-9)
        else:
            waiting = max(0.0, V.get(f"stock.{self.source}") or 0.0) if self.source else None
            if self.form == "servers":
                busy = _get(x, "servers", self.servers or 1)
                busy = min(waiting, busy) if waiting is not None else busy
                return _get(x, "success", self.success if self.success is not None else 1.0) * busy / self.server_time(x)
            v = (waiting or 0.0) / max(_get(x, "residence", self.residence or 1e-9), 1e-9)
        return min(v, max(0.0, cap)) if cap is not None else v

    def _law(self, V: dict, x: dict | None) -> float:
        e = V.get(f"goal.{self.goal}.error") or 0.0
        if abs(e) <= self.deadband:
            return 0.0
        step = _get(x, "gain", self.gain) * e
        if self.resolution:
            step = round(step / self.resolution) * self.resolution
        u = V.get(f"stock.{self.target}") if self.target else None
        if self.limits and u is not None:
            lo, hi = self.limits
            step = min(step, hi - u) if hi is not None and step > 0 else step
            step = max(step, lo - u) if lo is not None and step < 0 else step
        return step / max(self.period or 1.0, 1e-9)

    def said(self) -> str:
        """In words: what it is modelled as, how it is commanded, and what it was identified from (or why assumed)."""
        f = self.flow[5:]
        if self.form == "servers":
            what = (f"modelled as {_rate(self.success_or_1() / self.server_time())} a server ({_dur(self.service)} a run), "
                    f"{self.servers} server{'s' if self.servers != 1 else ''}, {round(self.success_or_1() * 100)}% success"
                    + (f", {round(self.expired * 100)}% of attempts expiring at its lease ({_dur(self.ttl)})" if self.expired else "")
                    + (f", taking from {self.source}" if self.source else ""))
        elif self.form == "equation":
            what = f"modelled by {f}'s equation ({self.equation})"
            if self.servers and self.service:
                what += f", at most {_rate(self.capacity())} ({self.servers} at once, {_dur(self.service)} a run)"
        elif self.form == "fill":
            most = f"at most {_rate(self.cap)} (its 95th percentile)" if self.cap is not None else "as fast as its runs allow"
            what = (f"modelled as moving {most}"
                    f"{', taking from ' + self.source if self.source else ''}, never past {self.goal}'s setpoint on {self.target} "
                    f"(it reads that goal), a run every {_dur(self.residence)}")
        elif self.form == "drain":
            what = (f"modelled as draining {self.source}: a residence time of {_dur(self.residence)}"
                    + (f", at most {_rate(self.cap)} (its 95th percentile)" if self.cap else ""))
        elif self.form == "law":
            what = (f"modelled by its law as written: a step of {self.gain:g} × {self.goal}'s error every {_dur(self.period)}"
                    + (f", deadband {self.deadband:g}" if self.deadband else "")
                    + (f", steps of {self.resolution:g}" if self.resolution else "")
                    + (f", within {list(self.limits)}" if self.limits else ""))
        elif self.rate_on == 0 and not self.assumed:
            what = f"moved nothing along {f}: modelled as 0"
        else:
            what = f"modelled as {_rate(self.rate_on)}" + (f", {_rate(self.rate_off)} otherwise" if self.gate and self.rate_off else "")
        return f"{self.label} {what}{self.gating}" + (f"; assumed: {self.assumed}" if self.assumed else
                                                      (f", from {self.basis}" if self.basis else ""))

    def success_or_1(self) -> float:
        return self.success if self.success is not None else 1.0

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {}, "")} | {"said": self.said()}


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


def _sd(xs: list[float]) -> float:
    return stdev(xs) if len(xs) > 1 else 0.0


def actuated(spec: Spec) -> dict[str, str]:
    """Each flow a block moves → the block (the first, as ``Spec.actuator_of``)."""
    return {f"flow.{f}": b.name for f in spec.flows if (b := spec.actuator_of(f)) is not None}


def has_controllers(spec: Spec) -> bool:
    """Whether a closed-loop projection has anything to run: a block, other than the judge, that moves a flow, commands
    a block or sets a setpoint."""
    return any(b.type != "judge" and any(t.kind in ("flow", "block", "goal") for t in b.targets()) for b in spec.blocks.values())


def _gate(p, spec: Spec, block: str, since: float, times: list[float]) -> list[bool] | None:
    """Whether the block was commanded at each moment: its built-in commanders' recorded output (None: none)."""
    cs = [c for c in spec.commanders_of(block) if c.builtin]
    if not cs:
        return None
    pts: list[tuple[float, float]] = []
    for c in cs:
        before = p.measurements.latest(f"block/{c.name}", before=since)
        pts += [(since, before[1])] if before else []
        pts += p.measurements.range(f"block/{c.name}", since, times[-1] if times else since)
    pts.sort()
    out, j, last = [], 0, None
    for t in times:
        while j < len(pts) and pts[j][0] <= t:
            last = pts[j][1]
            j += 1
        out.append(bool(last))
    return out


def identify(p, spec: Spec, data: ob.Data | None = None) -> dict[str, BlockModel]:
    """Each flow a machine block moves → its identified model, from the record on ``data``'s grid (the reference window
    when none is given)."""
    from ..leases import EXPIRED
    from ..leases.terms import terms
    data = data or ob.measured(p, ob.reference(p))
    g = data.grid
    span = _dur((g.until - g.since) / 3600.0)
    times = g.times()
    out: dict[str, BlockModel] = {}
    for ref, block in actuated(spec).items():
        b = spec.blocks[block]
        if b.builtin:
            continue                                        # a built-in moves its flow itself, as the engine runs it
        f = spec.flows[ref[5:]]
        several = sum(1 for t in b.targets() if t.kind == "flow") > 1
        cs = spec.commanders_of(block)
        m = BlockModel(block, ref, label=f"{block} (on {f.name})" if several else block, gate=cs[0].name if cs else None,
                       source=f.source, target=f.target)
        m.gating = f" while {m.gate} commands it" if m.gate else ""
        runs = p.events.query(n=None, type="agent.ran,agent.failed", item=block, since=g.since, until=g.until)
        m.runs = len(runs)
        vals = data.values.get(ref) or []
        lvl = data.values.get(f"stock.{f.source}") if f.source else None
        gate = _gate(p, spec, block, g.since, times) or [True] * len(times)
        on_b = [i for i in range(len(times)) if gate[i] and i < len(vals) and vals[i] is not None]
        off_b = [i for i in range(len(times)) if not gate[i] and i < len(vals) and vals[i] is not None]
        moved_off = sum(vals[i] for i in off_b)
        if m.gate and len(on_b) < MIN_BUCKETS <= len(off_b) and moved_off > 0 and not b.takes:
            # it moved while nothing commanded it (a person answers before being asked): its flow is not its command's
            m.gating = f" whether or not {m.gate} commands it (it moved {moved_off * g.width / 3600:.3g} while not commanded)"
            on_b, off_b, m.gate = sorted(on_b + off_b), [], None
        rates = [vals[i] for i in on_b]
        m.basis = f"{span} of record ({len(rates)} buckets{', ' + str(len(runs)) + ' runs' if runs else ''})"
        if b.takes:
            t = terms(spec, b)
            m.form, m.servers, m.ttl = "servers", b.pool, t["ttl"] / 3600.0
            took = [r for r in runs if (r.get("data") or {}).get("item")]
            if len(took) >= MIN_RUNS:
                secs = [float((r.get("data") or {}).get("seconds") or 0.0) for r in took]
                good = sum(1 for r in took if r["type"] == "agent.ran" and not (r.get("data") or {}).get("nack"))
                exp = sum(1 for e in p.events.query(n=None, type=EXPIRED, since=g.since, until=g.until)
                          if (e.get("data") or {}).get("block") == block)
                m.service, m.success = median(secs) / 3600.0, good / len(took)
                m.expired = exp / (len(took) + exp)
                m.se = {"service": _sd(secs) / math.sqrt(len(took)) / 3600.0,
                        "success": math.sqrt(max(m.success * (1 - m.success), 0.25 / len(took)) / len(took))}
                m.basis = f"{span} of record ({len(took)} runs)"
            else:
                m.service, m.success = (b.every or min(t["ttl"] / 4.0, 600.0)) / 3600.0, 1.0
                m.assumed = f"only {len(took)} runs on record (at least {MIN_RUNS}), a run taken as {_dur(m.service)}"
        if f.equation is not None:
            m.form, m.equation = "equation", f.equation.text
        elif b.takes:
            pass
        elif (law := b.params or {}).get("gain") is not None and (goal := next((r.name for r in b.reads() if r.kind == "goal"),
                                                                               None) or b.goal) and b.every:
            lim = law.get("limits")
            m.form, m.gain, m.period, m.goal = "law", float(law["gain"]), b.every / 3600.0, goal
            m.deadband, m.resolution = float(law.get("deadband") or 0.0), float(law.get("resolution") or 0.0)
            m.limits = tuple(lim) if isinstance(lim, list | tuple) and len(lim) == 2 else None
            m.basis = "the model"
        elif (holds := next((gl for gl in spec.goals.values() if f.target and str(gl.of) == f"stock.{f.target}" and gl.name != b.goal
                             and gl.name in {r.name for r in b.reads() if r.kind == "goal"}), None)) is not None:
            m.form, m.goal, m.residence = "fill", holds.name, (b.every or g.width) / 3600.0
            if len(rates) >= MIN_BUCKETS and any(rates):
                m.cap = quantile(sorted(rates), 0.95) if f.source else fmean(rates)
                m.se = {"cap": _sd(rates) / math.sqrt(len(rates))}
            else:
                m.assumed = f"the record has {len(rates)} buckets of it (at least {MIN_BUCKETS})"
        elif len(rates) >= MIN_BUCKETS and not any(rates):
            m.rate_on = 0.0                                 # measured long enough, and it moved nothing
        elif f.source and lvl and len(pairs := [(lvl[i], vals[i]) for i in on_b if i < len(lvl) and lvl[i] is not None]) >= MIN_BUCKETS \
                and sum(v for _, v in pairs) > 0:
            rs = [v for _, v in pairs]
            m.form, m.residence = "drain", max(sum(x for x, _ in pairs) / sum(rs), 1e-6)   # Little's law: L / λ
            m.cap = quantile(sorted(rs), 0.95) or None
            cv = _sd(rs) / fmean(rs)
            m.se = {"residence": m.residence * cv / math.sqrt(len(rs))} | ({"cap": _sd(rs) / math.sqrt(len(rs))} if m.cap else {})
            m.rate_off = fmean([vals[i] for i in off_b]) if len(off_b) >= MIN_BUCKETS else 0.0
        elif not f.source and len(rates) >= MIN_BUCKETS:
            m.rate_on, m.se = fmean(rates), {"rate_on": _sd(rates) / math.sqrt(len(rates))}
            m.rate_off = fmean([vals[i] for i in off_b]) if len(off_b) >= MIN_BUCKETS else 0.0
        elif f.source:                                      # too little record: a declared assumption
            m.form, m.residence = "drain", (b.every or 60.0) / 3600.0
            m.assumed = (f"it moves what waits within one of its runs ({_dur(m.residence)}): the record has {len(on_b)} buckets "
                         f"of it{' commanded' if m.gate else ''} (at least {MIN_BUCKETS})")
        else:
            m.rate_on = float(f.rate or 0.0)
            m.assumed = (f"{'its declared rate' if f.rate else 'nothing known'}: the record has {len(on_b)} buckets of it "
                         f"(at least {MIN_BUCKETS})")
        out[ref] = m
    from .external import models as external  # an external block's identified law, where it has one
    return out | external(p, spec, g.since, g.until)


def held_by_blocks(spec: Spec) -> list[str]:
    """What machine blocks set that a closed-loop projection holds where it was."""
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
