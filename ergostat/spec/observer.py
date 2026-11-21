"""The observer (SPEC §9.6): what the engine knows of a part between its readings, and how well. Opt-in: none of it
runs for a model that asks for none of it (``Opted``).

**Staleness.** A reading has an age. A part is stale once the third reading its quickest periodic sensor should have
taken since is past (``every`` three times over, or the third time its ``cron`` comes round), as ``sensor-stale``
(``watch.py``) counts; one counted from the record, measured from its stock's changes, read by hand, or not read yet is
never stale. Only the goals that say ``on-stale:`` (or are on a stock with ``observe: true``) and the blocks that say it
are watched; what each then does is its policy (``POLICIES``), applied by the engine.

**Estimated stocks.** A state estimator kept scalar per stock (no covariance between stocks), for the stocks with
``observe: true`` and those whose estimate a block reads. Between readings each estimate moves by the stock's modelled
net flow (its flows' equations, worked out by simulate's ``Stepper``; their measured rates otherwise; the stock's last
measured rate of change when a flow is neither); at each reading the reading is blended in with a Kalman gain
(Kalman 1960; Anderson and Moore, *Optimal Filtering*, ch. 4) that is **adaptive**: re-estimated at each reading over the
last ``KEEP`` open-loop errors e (a reading less the one before it moved by the model). Those are w + v' - v, so their
lag-1 autocovariance is -r (the sensor's noise) and their variance q·T + 2r (q: the model's error per hour). The gain is
the steady state's for those r and q at the median interval T: P⁻ = (qT + sqrt(q²T² + 4qTr)) / 2, K = P⁻ / (P⁻ + r);
after a reading the variance is K·r, and it grows by q between. A model that is right drives K down (the model carries
the estimate); one that is structurally wrong makes its errors large and drives K towards 1 (the readings carry it).

The innovation (a reading less its prediction) is kept; ``RUN`` in a row more than ``LARGE`` expected standard
deviations off (never less than the sensor's resolution: 0.5 for a count) say the model disagrees with the stock."""

from __future__ import annotations

import math
from collections import deque
from statistics import median

from .ir import Ref, Spec

STALE_AFTER = 3            # readings missed before a part is stale
POLICIES = ("act", "hold", "off")
PORTS = ("estimate", "uncertainty")
KEEP = 50                  # the open-loop errors the gain is estimated over
FLOOR = 0.01               # the model's error is taken as at least this share of the noise: it keeps listening to the sensor
MIN_ERRORS = 4             # until this many, each reading is taken whole (gain 1)
LARGE, RUN = 3.0, 5        # innovations this many standard deviations off, this many in a row: the model disagrees
_CRONS: dict = {}


def stale_by(s, last: float) -> float | None:
    """When a reading taken at ``last`` is stale for this sensor (None: it reads on no clock)."""
    if s.items or s.changes or s.manual or not (s.commands or s.query or s.builtin):
        return None
    if s.cron:
        from ..cron import Cron
        c = _CRONS.get(s.cron) or _CRONS.setdefault(s.cron, Cron(s.cron))
        t = last
        for _ in range(STALE_AFTER):
            t = c.next_after(t)
        return t
    return last + STALE_AFTER * s.every


def stale_age(spec: Spec, ref: Ref, last: float | None, now: float, since: float | None = None) -> float | None:
    """A part's reading's age when it is stale; None while it is fresh, never read, or never stale (an estimate).
    ``since``: what is not yet due since then (the engine's start) is not stale."""
    t = spec.measured(ref.kind).get(ref.name)
    if last is None or t is None or not t.sensors or ref.port in PORTS:
        return None
    due = [stale_by(s, max(last, since or last)) for s in t.sensors.values()]
    return None if None in due or now <= min(due) else now - last


def estimated(spec: Spec, ref: Ref) -> bool:
    """Whether a reference names a stock's estimate or uncertainty (not a sensor of that name)."""
    st = spec.stocks.get(ref.name) if ref.kind == "stock" else None
    return st is not None and ref.port in PORTS and ref.port not in st.sensors


class Opted:
    """What a model asked the observer for: the stocks it estimates, the goals it watches (with their policy) and the
    parts those goals and the blocks that say ``on-stale:`` read. Worked out once per model."""

    def __init__(self, spec: Spec):
        read = {r.name for b in spec.blocks.values() for r in b.inputs.values() if estimated(spec, r)}
        self.stocks = sorted(n for n, st in spec.stocks.items() if st.sensors and (st.observe or n in read))
        self.blocks = {n for n, b in spec.blocks.items() if b.on_stale}
        theirs = {r.name for n in self.blocks for r in spec.blocks[n].reads() if r.kind == "goal"}
        self.goals = {n: g.on_stale or "act" for n, g in spec.goals.items()
                      if g.on_stale or n in theirs or (g.of.kind == "stock" and g.of.name in self.stocks)}
        parts = {Ref(spec.goals[n].of.kind, spec.goals[n].of.name) for n in self.goals}
        parts |= {Ref(r.kind, r.name) for n in self.blocks for r in spec.blocks[n].inputs.values()
                  if r.kind in ("stock", "flow", "auxiliary") and not estimated(spec, r)}
        self.parts = sorted(parts, key=str)

    def __bool__(self) -> bool:
        return bool(self.stocks or self.goals or self.blocks)


def opted(spec: Spec) -> Opted:
    kept = spec.lookups().kept
    got = kept.get("observer.opted")
    if got is None:
        got = kept["observer.opted"] = Opted(spec)
    return got


def gain(errors, dts) -> tuple[float, float, float]:
    """(r, q, K): the sensor's noise (a variance), the model's error (a variance per hour) and the gain, from the
    open-loop errors and their intervals (hours)."""
    n = len(errors)
    if n < MIN_ERRORS:
        return 0.0, 0.0, 1.0
    m = sum(errors) / n
    d = [e - m for e in errors]
    var = sum(x * x for x in d) / n
    r = min(max(-sum(a * b for a, b in zip(d, d[1:], strict=False)) / (n - 1), 0.0), var / 2)
    q = (var - 2 * r) / max(sum(dts) / n, 1e-9)
    if r <= 0:
        return r, q, 1.0
    a = max(q * median(dts), r * FLOOR)
    p = (a + math.sqrt(a * a + 4 * a * r)) / 2
    return r, q, p / (p + r)


class Track:
    """One stock's estimate: its value (as of the observer's time), the open-loop prediction from its last reading, and
    what its gain is made from."""

    def __init__(self, counts: bool = False):
        self.x = self.open = self.last = self.y = None
        self.slope = 0.0                                  # its last measured rate of change, per hour
        self.counts = counts                              # read as whole numbers (an items sensor, or so far)
        self.errors: deque = deque(maxlen=KEEP)
        self.dts: deque = deque(maxlen=KEEP)
        self.r, self.q, self.k, self.post, self.run = 0.0, 0.0, 1.0, 0.0, 0

    def read(self, t: float, y: float, back: float = 0.0) -> tuple[float, float] | None:
        """A reading taken at ``t``: (innovation, its expected standard deviation), or None for the first. ``back``: how
        far the estimate moved since ``t`` (it was moved on to the pass's time first), so the reading is weighed against
        the estimate at its own time."""
        if self.x is None:
            self.x = self.open = y + back
            self.y = y
            self.last, self.counts = t, self.counts or float(y).is_integer()
            return None
        self.counts = self.counts and float(y).is_integer()
        dt = (t - self.last) / 3600.0
        sd = max(math.sqrt(max(self.post + self.q * max(dt, 0.0), 0.0) + self.r), 0.5 if self.counts else 0.0)
        nu = y - (self.x - back)                          # (judged before it is learnt from)
        large = len(self.errors) >= MIN_ERRORS and abs(nu) > LARGE * sd + 1e-9 * max(1.0, abs(y))
        self.run = self.run + 1 if large else 0
        if dt > 0:
            self.errors.append(y - (self.open - back))
            self.dts.append(dt)
            self.r, self.q, self.k = gain(self.errors, self.dts)
            self.slope = (y - self.y) / dt
        self.x += self.k * nu
        self.post = self.k * self.r
        self.open, self.y, self.last = y + back, y, t
        return nu, sd

    def uncertainty(self, now: float) -> float | None:
        if self.x is None:
            return None
        return math.sqrt(max(self.post + self.q * max(now - self.last, 0.0) / 3600.0, 0.0))


class Observer:
    """Every estimated stock's ``Track``, moved together by the model between readings."""

    def __init__(self, spec: Spec, history=None, carry: Observer | None = None, mine=None):
        """``mine``: whether a stock (``stock.NAME``) is this engine's shard's to estimate (None: every one)."""
        self.spec, self.t = spec, carry.t if carry else None
        self.rate: dict[str, float] = {}                   # each stock's net flow over the last step, per hour
        self.tracks: dict[str, Track] = {}
        for n in (n for n in opted(spec).stocks if mine is None or mine(f"stock.{n}")):
            tr = carry.tracks.get(n) if carry else None
            if tr is None:
                tr = Track(any(s.items for s in spec.stocks[n].sensors.values()))
                pts = history(n) if history else []
                slope = (pts[-1][1] - pts[0][1]) / max((pts[-1][0] - pts[0][0]) / 3600.0, 1e-9) if len(pts) > 1 else 0.0
                for (t0, y0), (t1, y1) in zip(pts, pts[1:], strict=False):   # the record's errors about its drift
                    if t1 > t0:
                        tr.errors.append(y1 - y0 - slope * (t1 - t0) / 3600.0)
                        tr.dts.append((t1 - t0) / 3600.0)
                tr.r, tr.q, tr.k = gain(tr.errors, tr.dts)
            self.tracks[n] = tr
        self.pl = self.st = None
        if self.tracks:
            try:
                from ..numbers import simulate
                from . import equation as eq
                self.pl = simulate.plan(spec)
                self.st = simulate.Stepper(self.pl, [])
                self.reads = {r for c in self.pl.eqs.values() for r in eq.refs(c.tree)} - set(self.pl.eqs)
            except Exception:                            # its equations cannot run: the measured rates move it
                self.pl = self.st = None

    def rates(self, sig: dict, dt: float) -> dict[str, float]:
        """Each stock's net flow per hour, now: its flows' equations, else their measured rates, else its own slope."""
        V = {}
        if self.st is not None:
            V = self.st.V
            for r in self.reads:
                tr = self.tracks.get(r[6:]) if r.startswith("stock.") else None
                v = tr.x if tr is not None and tr.x is not None else sig.get(r)
                V[r] = float(v) if isinstance(v, int | float) else 0.0
            try:
                self.st.evaluate(dt)
                self.st.step({}, dt)                       # (its delays' stages move on)
            except Exception:
                V = {}
        out = {}
        for n, tr in self.tracks.items():
            net = 0.0
            for f in self.spec.flows_of(n):
                k = f"flow.{f.name}"
                v = V.get(k) if self.pl is not None and k in self.pl.eqs else sig.get(k)
                if not isinstance(v, int | float):
                    net = None
                    break
                net += v if f.target == n else -v
            out[n] = tr.slope if net is None else net
        return out

    def advance(self, to: float, sig: dict) -> None:
        if self.t is not None and to > self.t:
            dt = (to - self.t) / 3600.0
            self.rate = self.rates(sig, dt)
            for n, rate in self.rate.items():
                tr = self.tracks[n]
                if tr.x is not None:
                    tr.x += rate * dt
                    tr.open += rate * dt
        self.t = to if self.t is None else max(self.t, to)


def shown_stale(project, spec: Spec, name: str, status: str, now: float) -> float | None:
    """The age a goal's status shows as ``stale`` on the page, ``ergostat status`` and the MCP status: only a watched
    goal, only while it holds (off outranks stale), only while ergostat runs, and not before its sensors were due since
    ergostat started."""
    g = spec.goals.get(name)
    if g is None or name not in opted(spec).goals or status != "holding":
        return None
    from ..runner import running_pid
    if not running_pid(project, wait=False):
        return None
    t = spec.measured(g.of.kind).get(g.of.name)
    reads = [project.measurements.latest(s.series, now) for s in t.sensors.values()] if t else []
    began = [e["time"] for t in ("ergostat.started", "ergostat.engine.woke")      # started, or woke from a sleep
             for e in project.events.query(n=1, type=t, until=now)]
    return stale_age(spec, Ref(g.of.kind, g.of.name), max((r[0] for r in reads if r), default=None), now,
                     max(began, default=None))
