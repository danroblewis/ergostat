"""An external block's law identified from its record (SPEC §12d, *Existing controllers*): ``identify: {input, output}``
read from their sensors' record on one grid, fitted by ``extlaw``; the law the closed-loop projection runs in place of
the generic stand-in (``ExternalModel``); and its findings, ``external-unidentified`` and ``external-law-changed``."""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from statistics import median

from ..spec.ir import Ref, Spec
from . import extlaw as el
from .blockmodels import BlockModel

MAX_POINTS = 2000         # the grid is widened past this many points
_CACHE: dict = {}


def blocks(spec: Spec) -> dict[str, dict[str, Ref]]:
    """Each external block that says ``identify:`` → its input and output."""
    return {n: b.params["identify"] for n, b in spec.blocks.items() if b.type == "external" and b.params.get("identify")}


def readings(p, spec: Spec, r: Ref, since: float, until: float) -> list[tuple[float, float]]:
    part = spec.measured(r.kind).get(r.name)
    pts = []
    for s in (part.sensors.values() if part is not None else ()):
        before = p.measurements.latest(s.series, before=since)
        pts += ([(since, before[1])] if before else []) + p.measurements.range(s.series, since, until)
    return sorted(pts)


def grid(xp: list, up: list, until: float) -> tuple[list[float], list[float], list[float], float]:
    """Both signals on one grid at the output's median sensor period (widened to at most ``MAX_POINTS``), each its last
    reading at or before each moment."""
    if len(up) < 2 or not xp:
        return [], [], [], 1.0
    t0 = max(xp[0][0], up[0][0])
    dt = max(1.0, median(b[0] - a[0] for a, b in zip(up, up[1:], strict=False)), (until - t0) / MAX_POINTS)
    ts = [t0 + i * dt for i in range(int((until - t0) / dt) + 1)]

    def held(pts):
        out, j = [], 0
        for t in ts:
            while j + 1 < len(pts) and pts[j + 1][0] <= t:
                j += 1
            out.append(pts[j][1])
        return out
    return ts, held(xp), held(up), dt


def identify(p, spec: Spec, name: str, since: float, until: float) -> dict:
    """``{"law", "laws", "why", "ts", "xs", "us"}``: the law chosen (None, with why) on ``[since, until]``."""
    key = (str(getattr(p, "dir", id(p))), name, str(spec.blocks[name].params["identify"]), int(since // 60), int(until // 60))
    if key in _CACHE:
        return _CACHE[key]
    io = spec.blocks[name].params["identify"]
    ts, xs, us, dt = grid(readings(p, spec, io["input"], since, until), readings(p, spec, io["output"], since, until), until)
    law, laws, why = el.fit(xs, us, dt) if ts else (None, [], f"no readings of {io['input' if us else 'output']} yet")
    got = {"law": law, "laws": laws, "why": why, "ts": ts, "xs": xs, "us": us}
    if len(_CACHE) > 64:
        _CACHE.clear()
    _CACHE[key] = got
    return got


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
    """An external block run by its identified law: its input read from the projection's values at each step, its
    output the law's, sampled every ``law.dt`` past its delay (``at`` is told the time)."""

    law: el.Law | None = None
    input: str = ""
    stock: str | None = None            # the output stock its flow moves to the law's level (else the flow is the output)
    sign: int = 1
    begin: dict = field(default_factory=dict)
    _t: float | None = None

    def fresh(self) -> ExternalModel:
        """A copy at where the record left it, for one projection run (runs may go on in threads side by side)."""
        m = copy.copy(self)
        m.st, m.hist, m.next, m._t = copy.deepcopy(self.begin["st"]), deque(self.begin["hist"]), self.begin["next"], None
        return m

    def at(self, t: float) -> None:
        if self._t is None or t < self._t - 1e-6:          # a projection run begins: from where the record left it
            self.st, self.hist, self.next = copy.deepcopy(self.begin["st"]), deque(self.begin["hist"]), self.begin["next"]
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
        return self.sign * (u - (V.get(f"stock.{self.stock}") or 0.0)) / max(dt, 1e-9)

    def said(self) -> str:
        return f"{self.block} identified, external: {self.law.said()}"

    def as_dict(self) -> dict:
        return {"block": self.block, "flow": self.flow, "form": self.form, "law": self.law.as_dict(), "said": self.said()}


def models(p, spec: Spec, since: float, until: float) -> dict[str, ExternalModel]:
    """Each identified block whose output the projection can move → its law as the block's model, keyed by that flow."""
    out = {}
    for name, io in blocks(spec).items():
        ref = moved_by(spec, name)
        got = identify(p, spec, name, since, until)
        law = got["law"]
        if ref is None or law is None:
            continue
        xs, us = got["xs"], got["us"]
        st = el.start(law, us[0], xs[0])
        ms = el._since(us, el._tol(us))
        for k in range(1, len(xs)):
            st["u"], st["since"] = us[k - 1], ms[k - 1]
            el.step(law, st, xs[max(0, k - law.d)])
        st["u"], st["since"] = us[-1], ms[-1]
        hist = [(t, x) for t, x in zip(got["ts"], xs, strict=True) if t >= got["ts"][-1] - law.delay - law.dt]
        f = spec.flows[ref[5:]]
        stock = io["output"].name if io["output"].kind == "stock" else None
        out[ref] = ExternalModel(name, ref, form="identified", label=name, basis="its record", law=law, source=f.source, target=f.target,
                                 input=f"{io['input'].kind}.{io['input'].name}", stock=stock,
                                 sign=1 if stock is None or f.target == stock else -1,
                                 begin={"st": st, "hist": hist, "next": got["ts"][-1] + law.dt})
    return out


def findings(p, spec: Spec, now: float, say) -> None:
    """``external-unidentified`` and ``external-law-changed`` (SPEC §12d), on the reference window."""
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
            continue
        mid = (g.since + g.until) / 2
        a, z = identify(p, spec, name, g.since, mid)["law"], identify(p, spec, name, mid, g.until)["law"]
        moved = el.drifted(a, z) if a is not None and z is not None else []
        if moved:
            say("external-law-changed", f"block {name} (external): its identified law changed between the first and the "
                f"second half of the record ({'; '.join(moved)}): someone retuned it, or it is not the law it was",
                b.where, f"block.{name}")
