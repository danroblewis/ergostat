"""How sure an estimate is, and whether the record says enough to make one (SPEC §12b; Ljung, *System Identification*,
ch. 9 on the estimates' covariance, ch. 13 on informative experiments, ch. 16 on validation). An estimate is proposed
only when the record covers enough of the part's dynamics: several of the slowest time constant it acts through, enough
points, enough of them independent, and enough movement in the inputs it acts through; else it is **held,
inconclusive**, with how much more record it needs.

**Its standard error, honest about errors that run together.** The Gauss–Newton covariance s²(JᵀJ)⁻¹ takes every
bucket as an independent point. A replay of a stock integrates the model's errors, so a mismatch at one moment (a
candidate counted a bucket late, a regime the model does not have) stays in the buckets after it: the errors drift
together, and a record of a few cycles holds a few independent points however often it was read. So it is widened by
(1 + ρ)/(1 − ρ), ρ the errors' lag-one autocorrelation (up to 0.99: it was held at 0.95, which said a record of 50
readings drifting as one held 1.3 independent points when it held fewer); and the **effective record**, n_eff =
n(1 − ρ)/(1 + ρ), the independent points it holds, must reach ``INDEPENDENT`` wherever the fit leaves a material error
(it was asked only where the error left was past a tenth of the readings' spread, so an 11- to 17-minute image-squeeze
record whose replay ran close to its readings, but drifting away from them as one, was taken as 80 independent points
and its estimate said ±12 images an hour, about a tenth of the scatter between such records).

**Enough movement in what it acts through** (persistence of excitation): what the parameter multiplies in the
equations it acts through, bucket by bucket (from the Jacobian: the change it makes to an equation's own rate, or to
a stock's rise), must have moved, each move a tenth of its range from where the last left it, ``MOVES`` times. A
switching input (an experiment started and decided) moves twice a cycle; one that held a single value the whole
record (one long experiment, a queue that never moved) says nothing about the parameter that a constant would not:
the record would be fitted as if it went on as it was."""

from __future__ import annotations

import math

from ..durations import human as dur

INDEPENDENT = 10        # independent points, at least, about a parameter before its value is proposed
MOVES = 6               # ... and moves of what it acts through (three cycles of a switching input)
STEP = 0.1              # a move: what it multiplies changed by this share of its range since the last move
RHO_MAX = 0.99          # errors that run together count as at least this many hundredths of independent points
MATERIAL = 0.001        # a weighted error left past this (its RMS past 3% of the readings' spread) is the model and the
                        # record disagreeing; below it, errors that drift together are the replay's own rounding


def _invert(a: list[list[float]]) -> list[list[float]] | None:
    from .estimate import _invert as inv
    return inv(a)


def _rho(segs: list[list[float]]) -> float:
    """The lag-one autocorrelation of errors in segments (each series in time), about 0, within 0 and ``RHO_MAX``."""
    num = sum(a * b for g in segs for a, b in zip(g, g[1:], strict=False))
    den = sum(a * a for g in segs for a in g[:-1])
    return max(0.0, min(num / den if den > 0 else 0.0, RHO_MAX))


def _gauss_newton(rows: list[list[float]], errs: list[float], segs: list[list[float]], p: int) -> dict | None:
    """s²(JᵀJ)⁻¹ widened by (1 + ρ)/(1 − ρ), and n(1 − ρ)/(1 + ρ) independent points."""
    n = len(rows)
    if n <= p:
        return None
    jtj = [[sum(r[i] * r[j] for r in rows) for j in range(p)] for i in range(p)]
    inv = _invert(jtj)
    if inv is None:
        return None
    rho = _rho(segs)
    s2 = sum(e * e for e in errs) / (n - p) * (1 + rho) / (1 - rho)
    return {"cov": [[s2 * v for v in row] for row in inv], "rho": rho, "n": n, "n_eff": n * (1 - rho) / (1 + rho)}


def sure(prob, names: list[str], cols: list[list[float]], keys: list[tuple[str, int]], e0: dict) -> dict | None:
    """How sure the estimates are: each one's standard error, widened for errors that run together, and as it would be
    with every point taken as independent (``se_naive``), their correlations, the errors' lag-one autocorrelation
    (``rho``), the effective record (``n_eff``, of each parameter in ``n_eff_of``) and how far the record moved what
    each acts through (``moves``)."""
    p = len(names)
    replayed = {f"stock.{s}" for s in prob.stocks}
    by: dict[str, list[tuple[int, int]]] = {}
    for k, (r, i) in enumerate(keys):
        by.setdefault(r, []).append((i, k))
    rows, errs, segs = [], [], []
    for _, ks in by.items():
        ks.sort()
        rows += [[cols[j][k] for j in range(p)] for _, k in ks]
        mine = [e0[keys[k]] for _, k in ks]
        errs += mine
        segs.append(mine)
    got = _gauss_newton(rows, errs, segs, p)
    if got is None:
        return None
    cov, rho = got["cov"], got["rho"]
    widen = (1 + rho) / (1 - rho)
    se = [math.sqrt(max(cov[i][i], 0.0)) for i in range(p)]
    corr = {names[i]: {names[j]: (cov[i][j] / (se[i] * se[j]) if se[i] and se[j] else None) for j in range(p) if j != i}
            for i in range(p)}
    moves = {nm: moved(prob, cols[j], keys, nm, replayed) for j, nm in enumerate(names)}
    return {"se": dict(zip(names, se, strict=True)), "corr": corr, "rho": rho, "n": got["n"], "n_eff": got["n_eff"],
            "n_eff_of": {nm: got["n_eff"] for nm in names},
            "se_naive": {nm: x / math.sqrt(widen) for nm, x in zip(names, se, strict=True)}, "moves": moves}


def moved(prob, col: list[float], keys: list[tuple[str, int]], name: str, replayed: set[str]) -> int | None:
    """How often what a parameter multiplies moved over the fitted record: in each series it is fitted to, bucket by
    bucket (an equation's own sensitivity, or a replayed stock's rise in the bucket), a move each time it has gone a
    tenth of its range from where the last move left it; the series that moved most. None for a parameter whose
    equations name nothing the record reads (a constant rate): nothing it acts through can move."""
    spec = prob.spec
    if not any(x.equation and name in x.equation.parameters and x.equation.refs
               for x in (*spec.flows.values(), *spec.auxiliaries.values())):
        return None
    by: dict[str, list[tuple[int, float]]] = {}
    for k, (r, i) in enumerate(keys):
        by.setdefault(r, []).append((i, col[k]))
    best = 0
    for r, v in by.items():
        v.sort()
        at = prob.data.at.get(r) or []
        if r in replayed:                                # a stock's rise in each span between readings, per hour
            xs = []
            for (i0, a), (i1, b) in zip(v, v[1:], strict=False):
                t0, t1 = (at[i0] if i0 < len(at) else None), (at[i1] if i1 < len(at) else None)
                dt = (t1 - t0) / 3600.0 if t0 is not None and t1 is not None and t1 > t0 else None
                if dt:
                    xs.append((b - a) / dt)
        else:
            xs = [x for _, x in v]
        if len(xs) < 2:
            continue
        span = max(xs) - min(xs)
        if span <= 1e-9 * max(1.0, max(abs(x) for x in xs)):
            continue
        n, last = 0, xs[0]
        for x in xs[1:]:
            if abs(x - last) >= STEP * span:
                n, last = n + 1, x
        best = max(best, n)
    return best


def too_short(e: dict) -> dict | None:
    """Whether the record an estimate was made on is too short to identify it: it must span ``fit.COVER`` of the
    slowest time constant the parameter acts through, hold ``estimate.PROPOSE`` points, ``INDEPENDENT`` of them
    independent where the fit leaves a material error (errors that drift together over the record count as the
    information they are), and have moved what it acts through ``MOVES`` times. Then ``{"says", "needs", "why"}``:
    held, inconclusive, and about how much more record it needs (seconds, the record assumed to go on as it has; None
    when what it acts through has not moved at all, so no length of the same record would do); else None."""
    from . import estimate as es
    from . import fit as ft
    if e.get("value") is None:
        return None
    window, why, needs = float(e.get("window") or 0.0), [], 0.0
    slowest = e.get("slowest")
    if slowest and window < ft.COVER * slowest * 3600:
        why.append(f"it spans {dur(window)}, under {ft.COVER:g} of the slowest time constant it acts through "
                   f"({dur(slowest * 3600)})")
        needs = max(needs, ft.COVER * slowest * 3600 - window)
    n = int(e.get("n") or 0)
    if n < es.PROPOSE:
        why.append(f"{n} points fitted, under {es.PROPOSE}")
        needs = max(needs, window * (es.PROPOSE / max(n, 1) - 1))
    eff = e.get("n_eff")
    if eff is not None and eff < INDEPENDENT and (e.get("after") is None or e["after"] > MATERIAL):
        why.append(f"the model's errors on it drift together over the record (lag-one autocorrelation {e.get('rho') or 0:.2f}), "
                   f"so its {n} points hold about {max(eff, 0):.1f} independent ones, under {INDEPENDENT}")
        needs = max(needs, window * (INDEPENDENT / max(eff, 0.5) - 1))
    mv = e.get("moves")
    moves_more = None
    if mv is not None and mv < MOVES:
        moves_more = MOVES - mv
        if mv == 0:
            why.append("what it acts through held one value over the record, so it cannot be told from a constant there")
            needs = None
        else:
            why.append(f"what it acts through moved {mv} time{'s' if mv != 1 else ''} in {dur(window)}, under {MOVES}")
            if needs is not None:
                needs = max(needs, window * (MOVES / mv - 1))
    if not why:
        return None
    if needs is not None:
        needs = max(needs, 60.0)
    if moves_more and needs is not None:
        more = (f"it needs what it acts through to move {moves_more} more time{'s' if moves_more != 1 else ''}: about "
                f"{dur(needs)} more record at the rate it has moved (a step test, or the next experiments, would do it)")
    elif needs is not None:
        more = f"it needs about {dur(needs)} more record (as the record has gone so far)"
    else:
        more = "it needs record in which what it acts through moves (a step test, or the next experiment, would do it)"
    return {"why": why, "needs": needs,
            "says": f"held, inconclusive: too little record to identify it ({'; '.join(why)}). Nothing says the value "
                    f"written is wrong: {more}"}


def record_says(spec, data, values: dict[str, float]) -> dict[str, dict]:
    """For values a change would write (a block's proposal), whether the record could identify each parameter at all:
    the record's own estimate of each group of parameters fitted together, worked out as the calibration works it out
    (each part alone), judged by ``too_short``; only those it holds. Judged at the record's best values, not at the ones
    proposed: errors a wrong value leaves say the value is wrong, not that the record is short."""
    from . import estimate as es
    from . import simulate as sim
    names = sorted(n for n in values if n in spec.parameters and not spec.parameters[n].table)
    if not names or data is None:
        return {}
    out = {}
    base = sim.replay(spec, data)
    cut = max(1, int(round(data.grid.n * (1 - es.HOLD_OUT))))
    marked = sorted(n for n, x in spec.parameters.items() if x.estimate and not x.table)
    groups = [g for g in es._groups(spec, sorted(set(marked) | set(names))) if set(g) & set(names)]   # as calibrated
    for group in groups:
        prob = es.Problem(spec, data, group, cut=cut)
        if prob.n() < 2:
            continue
        start = {n: (spec.parameters[n].value if spec.parameters[n].value is not None else values.get(n, 1.0)) for n in group}
        best, _, after, sure = es.solve(prob, start)
        at_best = sim.replay(spec, data, sim.plan(spec, best))      # its time constants as the record has them
        tc = es.slowest(spec, at_best if at_best.valid else base, prob.owners, prob.stocks, data)
        for n in group:
            if n not in values:
                continue
            e = {"value": best[n], "window": data.grid.until - data.grid.since, "n": prob.n(), "after": after,
                 "slowest": tc, "n_eff": (sure.get("n_eff_of") or {}).get(n),
                 "rho": sure.get("rho"), "moves": (sure.get("moves") or {}).get(n)}
            short = too_short(e)
            if short is not None:
                out[n] = short
    return out


def to_tell(e: dict, moved_by: float) -> float | None:
    """About how much more record (seconds) would tell an estimate this far from the value written (``moved_by``, in
    the coordinate it was searched in) from it, at two standard errors, the standard error falling as one over the root
    of the record's length; None when it cannot be said."""
    se, window = e.get("se"), float(e.get("window") or 0.0)
    if not se or not moved_by or not window:
        return None
    return max(60.0, window * ((2 * se / abs(moved_by)) ** 2 - 1))
