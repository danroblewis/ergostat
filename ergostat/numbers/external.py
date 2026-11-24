"""An external block's law identified from its record (SPEC §12d, *Existing controllers*): ``identify: {input, output}``
read from their sensors' record on one grid, fitted by ``extlaw``; the law the closed-loop projection runs in place of
the generic stand-in (``ExternalModel``), a law declared (``law:``, control/laws.py) run in its place; a declared law
judged on the same record (``declared``); and its findings, ``external-unidentified``, ``external-not-run`` and
``external-law-disagrees``."""

from __future__ import annotations

import copy
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field, replace
from statistics import median

from ..spec.ir import KnownLaw, Ref, Spec
from . import extlaw as el
from .blockmodels import BlockModel

MAX_POINTS = 2000         # the record fitted: its last this many samples, at the output's own sensor period
_CACHE: dict = {}
log = logging.getLogger("ergostat")


def blocks(spec: Spec) -> dict[str, dict[str, Ref]]:
    """Each external block that says ``identify:`` → its input and output."""
    return {n: b.params["identify"] for n, b in spec.blocks.items() if b.type == "external" and b.params.get("identify")}


def readings(p, spec: Spec, r: Ref, since: float, until: float) -> list[tuple[float, float]]:
    """One sensor's readings of the part (the named one, else its first): two sensors' are never interleaved."""
    part = spec.measured(r.kind).get(r.name)
    s = (part.sensors.get(r.port) if r.port else next(iter(part.sensors.values()), None)) if part is not None else None
    if s is None:
        return []
    before = p.measurements.latest(s.series, before=since)
    return ([(since, before[1])] if before else []) + sorted(p.measurements.range(s.series, since, until))


def grid(xp: list, up: list, until: float) -> tuple[list[float], list[float], list[float], float, float]:
    """Both signals on one grid at the output's median sensor period, over at most its last ``MAX_POINTS`` samples (never
    widened: a law's durations are whole samples of its own period), each its last reading at or before each moment;
    and how long, at the median, the input's reading was older than the output's (part of any delay seen)."""
    if len(up) < 2 or not xp:
        return [], [], [], 1.0, 0.0
    dt = max(1.0, median(b[0] - a[0] for a, b in zip(up, up[1:], strict=False)))
    t0 = max(xp[0][0], up[0][0], until - (MAX_POINTS - 1) * dt)
    ts = [t0 + i * dt for i in range(int((until - t0) / dt) + 1)]

    def held(pts):
        out, j = [], 0
        for t in ts:
            while j + 1 < len(pts) and pts[j + 1][0] <= t:
                j += 1
            out.append(pts[j])
        return out
    xh, uh = held(xp), held(up)
    lag = median(max(0.0, u[0] - x[0]) for x, u in zip(xh, uh, strict=True))
    return ts, [x[1] for x in xh], [u[1] for u in uh], dt, lag


def identify(p, spec: Spec, name: str, since: float, until: float) -> dict:
    """``{"law", "laws", "why", "ts", "xs", "us"}``: the law chosen (None, with why) on ``[since, until]``."""
    key = (str(getattr(p, "dir", id(p))), name, str(spec.blocks[name].params["identify"]), int(since // 60), int(until // 60))
    if key in _CACHE:
        return _CACHE[key]
    io = spec.blocks[name].params["identify"]
    ts, xs, us, dt, lag = grid(readings(p, spec, io["input"], since, until), readings(p, spec, io["output"], since, until), until)
    law, laws, why = el.fit(xs, us, dt) if ts else (None, [], f"no readings of {io['input' if us else 'output']} yet")
    for w in laws:
        w.sampling = lag + dt
    got = {"law": law, "laws": laws, "why": why, "ts": ts, "xs": xs, "us": us}
    while len(_CACHE) >= 64:                               # the oldest first: each block keeps its latest
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = got
    return got


def declared(p, spec: Spec, name: str, since: float, until: float) -> dict | None:
    """The block's declared law (``law:``) judged on the record on identify's grid, as identify judges its own laws:
    ``{"kind", "law", "why", "beaten"}``, ``law`` None with why (too little record, as identify says); ``beaten`` the
    identified law when its parsimony score is lower than the declared law's error (its parameters given, not fitted,
    so only a delay counts against it). None: no law declared."""
    known = spec.blocks[name].law
    if known is None:
        return None
    got = identify(p, spec, name, since, until)
    memo = got.setdefault("declared", {})                  # kept with the identification, keyed by the law as declared
    if str(known) in memo:
        return memo[str(known)]
    xs, us = got["xs"], got["us"]
    out = {"kind": known.kind, "law": None, "why": got["why"], "beaten": None}
    if got["ts"] and len(xs) >= el.MIN_POINTS and max(us) > min(us):
        from ..control import laws as kl
        nf = int(len(xs) * (1 - el.HELD_OUT))
        dt = got["ts"][1] - got["ts"][0]

        def fitted_sse(w):                                 # its delay, as identify searches one, on the part fitted only
            one = el.run(w, xs[:nf], us[:nf])
            return sum((a - b) ** 2 for a, b in zip(one[1:], us[1:nf], strict=True))
        base = kl.law(known, dt)
        law = min((replace(base, delay=d * dt) for d in range(el.MAX_DELAY + 1)), key=lambda w: (fitted_sse(w), w.delay))
        el.judge(law, xs, us, nf)
        nh = len(xs) - nf
        law.score -= (law.k - (law.delay > 0)) * math.log(nh)   # the declared numbers are not fitted: no penalty for them
        best = got["law"]
        out.update(law=law, why="", beaten=best if best is not None and best.score < law.score else None)
    memo[str(known)] = out
    return out


def disagrees(d: dict | None) -> bool:
    """A declared law judged that fits its record worse: below 0 skill held out, or beaten by the law identified."""
    w = (d or {}).get("law")
    return w is not None and (w.skill is not None and w.skill < 0 or d["beaten"] is not None)


def cached(p, spec: Spec, now: float | None = None) -> dict[str, dict] | None:
    """``laws`` if every one is identified already (None: some would be fitted now)."""
    from . import observe as ob
    g = ob.reference(p, now)
    keys = [(str(getattr(p, "dir", id(p))), n, str(io), int(g.since // 60), int(g.until // 60)) for n, io in blocks(spec).items()]
    return {k[1]: _CACHE[k] for k in keys} if all(k in _CACHE for k in keys) else None


def laws(p, spec: Spec, now: float | None = None) -> dict[str, dict]:
    """Each identified block on the reference window → its identification."""
    from . import observe as ob
    if not blocks(spec):
        return {}
    g = ob.reference(p, now)
    return {n: identify(p, spec, n, g.since, g.until) for n in blocks(spec)}


def moved_by(spec: Spec, name: str) -> str | None:
    """The flow the projection moves for the block's output: the output itself when a flow, else the block's flow into
    or out of the output stock (None: an auxiliary, or a stock it moves no flow of)."""
    out = spec.blocks[name].params["identify"]["output"]
    if out.kind == "flow":
        return f"flow.{out.name}"
    if out.kind == "stock":
        return next((f"flow.{t.name}" for t in spec.blocks[name].targets() if t.kind == "flow" and t.name in spec.flows
                     and out.name in (spec.flows[t.name].target, spec.flows[t.name].source)), None)
    return None


@dataclass
class ExternalModel(BlockModel):
    """An external block run by its declared law, else its identified one: its input read from the projection's values
    at each step, its output the law's, sampled every ``law.dt`` past its delay (``at`` is told the time). A stock output
    is moved by the block's own flow by each change of the law's level, so the stock's other flows still move it."""

    law: el.Law | None = None
    input: str = ""
    stock: str | None = None            # the output stock its flow moves by the law's changes (else the flow is the output)
    sign: int = 1
    begin: dict = field(default_factory=dict)
    known: KnownLaw | None = None       # its declared law (form "declared")
    record: tuple = ()                  # the record's grid (ts, xs, us) a declared law is started from again (``tried``)
    _t: float | None = None

    def tried(self, values: dict) -> ExternalModel:
        """A copy whose declared law has these parameters (a what-if), started from the record again."""
        from ..control import laws
        m = copy.copy(self)
        m.known = KnownLaw(self.known.kind, {**self.known.params, **values})
        m.law = laws.law(m.known)
        m.begin = _begin(m.law, *_every(m.law.dt, *self.record))
        return m

    def fresh(self) -> ExternalModel:
        """A copy at where the record left it, for one projection run (runs may go on in threads side by side)."""
        m = copy.copy(self)
        m._t = None
        m.at(self.begin["next"] - self.law.dt)
        return m

    def at(self, t: float) -> None:
        if self._t is None or t < self._t - 1e-6:          # a projection run begins: from where the record left it
            self.st, self.hist, self.next = copy.deepcopy(self.begin["st"]), deque(self.begin["hist"]), self.begin["next"]
            self.level = self.st["u"]
        self._t = t

    def rate(self, V: dict, on: bool, x: dict | None = None, eqv: float | None = None, dt: float = 0.0) -> float:
        law, t = self.law, self._t or 0.0
        v = V.get(self.input)
        if v is not None:
            self.hist.append((t, v))
        while self.next <= t + 1e-9:
            when = self.next - law.delay
            while len(self.hist) > 1 and self.hist[1][0] <= when:
                self.hist.popleft()
            el.step(law, self.st, self.hist[0][1])
            self.next += law.dt
        u = self.st["u"]
        if self.stock is None:
            return u
        moved, self.level = u - self.level, u
        return self.sign * moved / max(dt, 1e-9)

    def said(self) -> str:
        how = f"declared {self.known.kind}" if self.form == "declared" else "identified"
        return f"{self.block} {how}, external: {self.law.said()}"

    def as_dict(self) -> dict:
        return {"block": self.block, "flow": self.flow, "form": self.form, "law": self.law.as_dict(), "said": self.said()}


def _every(dt: float, ts: list, xs: list, us: list) -> tuple[list, list, list]:
    """The record's grid at a declared law's own period, ending where it ends: each its last sample at or before."""
    n = min(MAX_POINTS - 1, int((ts[-1] - ts[0]) / dt + 1e-9))
    at = [ts[-1] - (n - i) * dt for i in range(n + 1)]
    j, ix = 0, []
    for t in at:
        while j + 1 < len(ts) and ts[j + 1] <= t + 1e-6:
            j += 1
        ix.append(j)
    return at, [xs[j] for j in ix], [us[j] for j in ix]


def _begin(law: el.Law, ts: list, xs: list, us: list) -> dict:
    """Where the record left the law: its state (``settle``), the input it will read past its delay, its next sample."""
    hist = [(t, x) for t, x in zip(ts, xs, strict=True) if t >= ts[-1] - law.delay - law.dt]
    return {"st": el.settle(law, xs, us), "hist": hist, "next": ts[-1] + law.dt}


def models(p, spec: Spec, since: float, until: float) -> dict[str, ExternalModel]:
    """Each external block whose output the projection can move → its declared law (the owner's statement), else its
    identified one, as the block's model, keyed by that flow; started from the record either way."""
    from ..control import laws
    out = {}
    for name, io in blocks(spec).items():
        ref, known = moved_by(spec, name), spec.blocks[name].law
        got = identify(p, spec, name, since, until)
        if ref is None or not got["ts"] or (known is None and got["law"] is None):
            continue
        law = laws.law(known) if known is not None else got["law"]
        grid_ = (got["ts"], got["xs"], got["us"])
        f = spec.flows[ref[5:]]
        stock = io["output"].name if io["output"].kind == "stock" else None
        out[ref] = ExternalModel(name, ref, form="declared" if known else "identified", label=name,
                                 basis="its declaration" if known else "its record", law=law, source=f.source,
                                 target=f.target, input=f"{io['input'].kind}.{io['input'].name}", stock=stock,
                                 sign=1 if stock is None or f.target == stock else -1, known=known, record=grid_,
                                 begin=_begin(law, *(_every(law.dt, *grid_) if known else grid_)))
    return out


def findings(p, spec: Spec, now: float, say) -> None:
    """``external-unidentified`` (too little record, or no law fits) and ``external-not-run`` (identified, but its output
    is not a flow or a stock its own flow moves, so the projection runs the generic stand-in), and
    ``external-law-disagrees`` (its declared law fits its record worse) (SPEC §12d)."""
    from . import observe as ob
    if not blocks(spec):
        return
    g = ob.reference(p, now)
    for name, io in blocks(spec).items():
        b = spec.blocks[name]
        got = identify(p, spec, name, g.since, g.until)
        if got["law"] is None:
            say("external-unidentified", f"block {name} (external): its law from {io['input']} to {io['output']} is not "
                f"identified: {got['why']}", b.where, f"block.{name}")
        if (got["law"] is not None or b.law is not None) and moved_by(spec, name) is None:
            how = f"declared ({b.law.kind})" if b.law is not None else f"identified ({got['law'].short()})"
            say("external-not-run", f"block {name} (external): its law is {how} but not run "
                f"ahead: {io['output']} is not a flow, nor a stock one of its out: flows moves", b.where, f"block.{name}")
        d = declared(p, spec, name, g.since, g.until)
        if not disagrees(d):
            continue                                       # holds (never a finding), or too little record to say
        w = d["law"]
        than = (f"the law identified from it, {d['beaten'].short()} (score {d['beaten'].score:.4g} against {w.score:.4g})"
                if d["beaten"] else "holding its last value")
        at = lambda t: time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t))   # noqa: E731
        say("external-law-disagrees", f"block {name}: declared {d['kind']} ({w.short()}) fits its record worse than {than}: "
            f"it does not behave as configured (skill {_f(w.skill)}, R² {_f(w.r2)} on the last quarter of {w.points} points "
            f"held out, the record from {at(got['ts'][0])} to {at(got['ts'][-1])})", b.where, f"block.{name}")


def _f(x: float | None) -> str:
    return "–" if x is None else f"{x:.2f}"
