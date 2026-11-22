"""A measured stock's one-step residuals, worked out from the record (the observer's open-loop one-step errors,
``spec/observer.py``, for every measured stock and for any model, not only while the engine runs): what the stock
changed by from one bucket to the next, less what the model's flows moved in it. Under a right model they are what
nobody measured (the disturbance) and the readings' own noise, and so close to white; coloured, they carry structure
the model lacks. Whether they are white is a portmanteau test over lags 2 to 10, with Bartlett's covariance of the
sample autocorrelations under an MA(1) null (Box & Jenkins; Brockwell & Davis §7.2): reading noise makes
e(i) = w(i) + v(i) − v(i−1), so lag 1 is excused, and the autocorrelations past it are correlated with each other,
which the quadratic form allows for. Which inflow, and by how much it is late, is the lag whose regressor
u(i−k) − u(i) (what a k-bucket delay on inflow u leaves in the residual) the residual follows most."""

from __future__ import annotations

import math

from ..spec import equation as eq
from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

MIN_POINTS = 40           # residuals a stock needs, after the warm-up, to be examined
COVERED = 0.8             # ... and the share of buckets it must have a reading in
LAGS = 10                 # the autocorrelations tested: 2 to LAGS
CHI2_9_99 = 21.666        # χ²(9) at 0.99: coloured past it (α = 0.01)
MOST_LAG = 12             # the longest lag tried, in buckets
Z_99 = 2.576              # a lag's correlation must pass Z_99 / √n
CLIP = 0.45               # r1 at least −CLIP in Bartlett's matrix (at −0.5 it is singular)
DELAYS = ("DELAY1", "DELAY3", "SMOOTH", "SMOOTH3")


def unread(spec: Spec) -> set[str]:
    """The stocks the residual run integrates: those with flows and no sensor (every other is taken as read, and a
    remote's always is: SPEC §4c)."""
    from ..remote import remote_parts
    theirs = remote_parts(spec)
    return {s for s, st in spec.stocks.items() if spec.flows_of(s) and not st.sensors and f"stock.{s}" not in theirs}


def residual_run(spec: Spec, data: ob.Data) -> sim.Run:
    """The residual run: every measured stock taken as read, each never read integrated from its ``initial:``."""
    return sim.replay(spec, data, sim.plan(spec, integrate=unread(spec)))


def _sign(spec: Spec, x: str, f) -> int:
    return 1 if f.target == x else -1


def moved(spec: Spec, data: ob.Data, run: sim.Run, name: str) -> list[float | None]:
    """What flow ``name`` moved in each bucket: its equation's (the run's), what was counted, or its held rate × the
    bucket's width; None where it is not known (never 0)."""
    ref, g = f"flow.{name}", data.grid
    n, w, edges = g.n, g.width / 3600.0, g.edges()
    if ref in run.moved:
        f = spec.flows[name]
        out = list(run.moved[ref])
        given = [r for r in (f.equation.refs if f.equation else []) if r not in run.how]
        for i in range(n):                       # an equation fed a reading not yet made worked on a 0: not known
            t = edges[i]
            for r in given:
                v = data.level_at(r, t) if not r.startswith("flow.") else data.held(r)[i]
                if v is None:
                    out[i] = None
                    break
        return out
    if ref in data.counted:
        c = data.counted[ref]
        return [c.between(edges[i], edges[i + 1]) for i in range(n)]
    return [None if v is None else v * w for v in data.held(ref)] if ref in data.values else [None] * n


def examinable(spec: Spec, data: ob.Data, x: str) -> str | None:
    """Why stock ``x``'s residual cannot be worked out (None when it can)."""
    from ..remote import remote_of
    if (remote := remote_of(spec, f"stock.{x}")) is not None:
        return f"remote {remote}'s: its residual is examined there, never here"
    no_start =sorted(s for s in unread(spec) if spec.stocks[s].initial is None)
    for f in spec.flows_of(x):
        near = {f.source, f.target} | {r.split(".", 1)[1] for r in (f.equation.refs if f.equation else []) if r.startswith("stock.")}
        bad = next((s for s in no_start if s in near), None)
        if bad:
            return f"fed from {bad}, never read and with no initial: its residual cannot be worked out"
    vals = data.values.get(f"stock.{x}") or []
    have = sum(v is not None for v in vals)
    if not vals or have < COVERED * len(vals):
        return f"read in {have} of {len(vals)} buckets, under {COVERED:.0%}: its residual cannot be worked out"
    return None


def residuals(spec: Spec, data: ob.Data, run: sim.Run, x: str) -> list[float | None]:
    """e(i) = y(i) − y(i−1) − Σ± m_f(i) over x's flows, for each bucket with a reading in it and the one before;
    None in every other bucket, and in any where a flow's move is not known."""
    y = data.values.get(f"stock.{x}") or [None] * data.grid.n
    flows = [(_sign(spec, x, f), moved(spec, data, run, f.name)) for f in spec.flows_of(x)]
    out: list[float | None] = [None] * len(y)
    for i in range(1, len(y)):
        if y[i] is None or y[i - 1] is None:
            continue
        ms = [(s, m[i]) for s, m in flows]
        if all(m is not None for _, m in ms):
            out[i] = y[i] - y[i - 1] - sum(s * m for s, m in ms)
    return out


def _acf(e: list[float | None], most: int) -> tuple[int, list[float]]:
    got = [v for v in e if v is not None]
    n = len(got)
    if n < 3:
        return n, [0.0] * (most + 1)
    m = sum(got) / n
    d = sum((v - m) ** 2 for v in got)
    if d <= 0:
        return n, [1.0] + [0.0] * most
    r = [1.0]
    for k in range(1, most + 1):
        r.append(sum((e[i] - m) * (e[i - k] - m) for i in range(k, len(e)) if e[i] is not None and e[i - k] is not None) / d)
    return n, r


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    m = len(b)
    x = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(m):
        p = max(range(c, m), key=lambda i: abs(x[i][c]))
        x[c], x[p] = x[p], x[c]
        for i in range(m):
            if i != c:
                f = x[i][c] / x[c][c]
                for j in range(c, m + 1):
                    x[i][j] -= f * x[c][j]
    return [x[i][m] / x[i][i] for i in range(m)]


def bartlett(r1: float, size: int = LAGS - 1) -> list[list[float]]:
    """Bartlett's covariance of r_2 … r_10 (times n) under an MA(1) whose lag-1 correlation is ``r1``, taken in
    [−0.45, 0]: reading noise makes it negative, at most −0.5; a positive r_1 is not excused (it is a misfit's
    persistence, which an MA(1) with a positive ρ1 would wrongly expect r_2 … r_10 to share)."""
    p = max(-CLIP, min(0.0, r1))
    band = {0: 1 + 2 * p * p, 1: 2 * p, 2: p * p}
    return [[band.get(abs(a - b), 0.0) for b in range(size)] for a in range(size)]


def whiteness(e: list[float | None]) -> tuple[float, bool]:
    """q = n · r' Σ⁻¹ r over r_2 … r_10 (Σ: Bartlett's MA(1) covariance from the sample r_1), χ²(9) under a right
    model with reading noise; coloured past ``CHI2_9_99``. Over the residuals present, each lag's pairs both present."""
    n, r = _acf(e, LAGS)
    rest = r[2:LAGS + 1]
    q = n * sum(a * b for a, b in zip(rest, _solve(bartlett(r[1]), rest), strict=True))
    return q, q > CHI2_9_99


def _corr(pts: list[tuple[float, float]]) -> float | None:
    n = len(pts)
    if n < 3:
        return None
    ma, mb = sum(a for a, _ in pts) / n, sum(b for _, b in pts) / n
    sab = sum((a - ma) * (b - mb) for a, b in pts)
    saa, sbb = sum((a - ma) ** 2 for a, _ in pts), sum((b - mb) ** 2 for _, b in pts)
    return sab / math.sqrt(saa * sbb) if saa > 0 and sbb > 0 else None


def lag_of(e: list[float | None], u: list[float | None], kmax: int) -> tuple[int, float] | None:
    """The k in 1..kmax (at most ``MOST_LAG``) whose d_k(i) = u(i−k) − u(i) the residual correlates with most, and
    positively; None when that correlation is at or below 2.576/√n_k."""
    best = None
    for k in range(1, min(kmax, MOST_LAG) + 1):
        pts = [(e[i], u[i - k] - u[i]) for i in range(k, len(e)) if e[i] is not None and u[i] is not None and u[i - k] is not None]
        c = _corr(pts)
        if c is not None and c > 0 and (best is None or c > best[1]):
            best = (k, c, len(pts))
    if best is None or best[1] <= Z_99 / math.sqrt(best[2]):
        return None
    return best[0], best[1]


def delayed(f) -> bool:
    return bool(f.equation) and any(n[0] == "fn" and n[1] in DELAYS for n in eq.walk(f.equation.tree))


def inflows(spec: Spec, x: str) -> list:
    """x's inflows a missing delay may be on: not already delayed, not drawn from a stock with no sensor, not measured
    by x's own changes."""
    return [f for f in spec.flows_of(x) if f.target == x and not delayed(f)
            and not (f.source and not spec.stocks[f.source].sensors) and not ob.from_its_stock(spec, f"flow.{f.name}")]
