"""How much the projection depends on what is not known: Monte Carlo sensitivity analysis, as system
dynamics does it (Sterman, *Business Dynamics*, ch. 21, sensitivity analysis in Table 21-4: multivariate
sensitivity over joint distributions; Vensim's sensitivity runs, drawn as confidence bounds on the
behaviour over time).

The parameters that are uncertain are those the model says are: a ``range: [low, high]`` written on
the parameter (sampled uniformly in it), or, where none is written, an estimate's standard error
(estimate.py: sampled normally about the value written, on its logarithm when it was searched there,
widened to cover the distance between the value written and the estimate, so the fan is about the
projection drawn and still reaches what the record says). Parameters estimated together are drawn
**jointly**, from the multivariate normal of their covariance: the Cholesky factor of their correlation
applied to the Latin hypercube's normal scores (Iman and Conover, 1982), so no sample combines values the
data rules out. Every other number is held at its value. The samples are a Latin hypercube (each
parameter's range cut into as many equal-probability strata as there are samples, each stratum used
once: McKay, Beckman and Conover, 1979), ``SAMPLES`` of them as Vensim's sensitivity runs default to,
from a fixed seed, so the same model and record draw the same fan.

Each sample is the projection run again from the state now, with the sample's values: the stocks from
their last readings, and each material delay's contents as the replay left them **rescaled to the
sample's delay time** at the same outflow (``simulate.project``'s ``rescale``: what is in a pipeline at a
given throughput is that throughput times its time, so a sample starts in its own steady state and the
fan does not jump at now); a smoothed value (SMOOTH) is kept. What is drawn is the spread of the
projections: for each part and each moment ahead, the 25th and 75th percentiles across the samples, and
the 5th and 95th from ``TAILS`` runs or more (from fewer, the tails move from one seed to another and are
not drawn). Nothing here changes the model: it says how far the projection could be off for what the
model admits it does not know, and nothing about what it leaves out."""

from __future__ import annotations

import math
import random
from statistics import NormalDist

from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

SAMPLES = 200
TAILS = 100              # runs needed, at least, before the 5th and 95th percentiles are drawn
SEED = 20261116
QUANTILES = (0.05, 0.25, 0.75, 0.95)


def uncertain(spec: Spec, estimates: dict | None = None) -> list[dict]:
    """Each parameter an equation uses that the model says is uncertain, and how it is sampled."""
    used = {n for t in (spec.flows, spec.auxiliaries) for x in t.values() if x.equation for n in x.equation.parameters}
    out = []
    for name in sorted(used):
        p = spec.parameters.get(name)
        if p is None or p.table:
            continue
        if p.range:
            out.append({"name": name, "how": "range", "low": p.range[0], "high": p.range[1], "value": p.value,
                        "unit": p.unit, "duration": p.duration})
            continue
        e = (estimates or {}).get(name) or {}
        if p.value is not None and e.get("se") and e.get("value") is not None:
            logged = bool(e.get("logged")) and p.value > 0 and e["value"] > 0
            se = float(e["se"])
            gap = (math.log(e["value"] / p.value) if logged else e["value"] - p.value)
            sd = math.sqrt(se * se + gap * gap)          # about the value written, wide enough to reach the estimate
            lo, hi = ((p.value * math.exp(-2 * sd), p.value * math.exp(2 * sd)) if logged else (p.value - 2 * sd, p.value + 2 * sd))
            out.append({"name": name, "how": "estimate", "value": p.value, "se": se, "sd": sd, "estimate": e["value"],
                        "logged": logged, "low": lo, "high": hi, "unit": p.unit, "duration": p.duration,
                        "corr": {k: c for k, c in (e.get("corr") or {}).items() if c is not None}})
    return out


def cholesky(a: list[list[float]]) -> list[list[float]] | None:
    """The lower factor L of a symmetric positive definite matrix (L·Lᵀ = a); None when it is not."""
    n = len(a)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = a[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s <= 1e-12:
                    return None
                L[i][i] = math.sqrt(s)
            else:
                L[i][j] = s / L[j][j]
    return L


def joint(unc: list[dict]) -> list[list[float]] | None:
    """The Cholesky factor of the estimated parameters' correlations (in the order they come in ``unc``), shrunk
    toward independence until it is positive definite; None when none are correlated."""
    est = [u for u in unc if u["how"] == "estimate"]
    c = [[1.0 if i == j else float((a.get("corr") or {}).get(b["name"], 0.0) or 0.0) for j, b in enumerate(est)]
         for i, a in enumerate(est)]
    if not any(c[i][j] for i in range(len(est)) for j in range(len(est)) if i != j):
        return None
    for shrink in (1.0, 0.99, 0.95, 0.9, 0.75, 0.5, 0.0):
        L = cholesky([[x if i == j else x * shrink for j, x in enumerate(row)] for i, row in enumerate(c)])
        if L is not None:
            return L
    return None


def draws(unc: list[dict], k: int = SAMPLES, seed: int = SEED) -> list[dict[str, float]]:
    """k sets of values, a Latin hypercube over the uncertain parameters; those estimated together drawn
    jointly (their normal scores correlated by the Cholesky factor of their correlations)."""
    if not unc or k < 1:
        return []
    rnd = random.Random(seed)
    cols = []
    for _ in unc:
        strata = [(i + rnd.random()) / k for i in range(k)]
        rnd.shuffle(strata)
        cols.append(strata)
    norm = NormalDist()
    est = [j for j, u in enumerate(unc) if u["how"] == "estimate"]
    L = joint(unc)
    out = []
    for i in range(k):
        got = {}
        z = [norm.inv_cdf(min(max(cols[j][i], 1e-9), 1 - 1e-9)) for j in est]
        if L is not None:
            z = [sum(L[a][b] * z[b] for b in range(a + 1)) for a in range(len(z))]
        score = dict(zip(est, z, strict=True))
        for j, (u, col) in enumerate(zip(unc, cols, strict=True)):
            if u["how"] == "range":
                q = min(max(col[i], 1e-9), 1 - 1e-9)
                got[u["name"]] = u["low"] + q * (u["high"] - u["low"])
            elif u["logged"]:
                got[u["name"]] = u["value"] * math.exp(score[j] * u.get("sd", u["se"]))
            else:
                got[u["name"]] = u["value"] + score[j] * u.get("sd", u["se"])
        out.append(got)
    return out


def quantile(xs: list[float], q: float) -> float:
    """The q-quantile of sorted values, linear between them."""
    if len(xs) == 1:
        return xs[0]
    x = q * (len(xs) - 1)
    i = int(x)
    return xs[i] if i + 1 >= len(xs) else xs[i] + (xs[i + 1] - xs[i]) * (x - i)


def fan(spec: Spec, data: ob.Data, horizon: float, points: int, inputs: str = "hold", estimates: dict | None = None,
        k: int = SAMPLES, base: dict[str, float] | None = None, run: sim.Run | None = None) -> dict:
    """The projection's spread over the uncertain parameters: for each part the projection works out,
    its percentiles at each moment ahead; which parameters were sampled and how; how many runs were
    not valid (left out of the fan). ``run`` is the model's replay the projections start from (else
    the model is replayed with its values as written)."""
    unc = uncertain(spec, estimates)
    sets = draws(unc, k)
    runs: dict[str, list[list[float]]] = {}
    invalid = 0
    was = sim.plan(spec, base or None)
    run = run if run is not None or not sets else sim.replay(spec, data, was)
    held = sim.controlled(spec)
    from .estimate import touched
    # a stock no equation reads, nor the sampled values move, is the same in every sample: it is not run again
    _, moved = touched(spec, {u["name"] for u in unc})
    moved |= {r[6:] for t in (spec.flows, spec.auxiliaries) for x in t.values() if x.equation
              for r in x.equation.refs if r.startswith("stock.")}
    for d in sets:
        pl = sim.plan(spec, {**(base or {}), **d}, integrate=moved)
        proj = sim.project(spec, data, run, horizon, pl, points=points, inputs=inputs, rescale=was, held=held)
        if not proj.valid:
            invalid += 1
            continue
        for ref, vals in proj.values.items():
            if any(v is None for v in vals):
                continue
            runs.setdefault(ref, []).append(vals)
    bands = {}
    for ref, rows in runs.items():
        if len(rows) < 2:
            continue
        cols = [sorted(col) for col in zip(*rows, strict=True)]
        bands[ref] = {f"p{round(q * 100)}": [quantile(c, q) for c in cols] for q in QUANTILES
                      if len(rows) >= TAILS or 0.1 < q < 0.9}
    return {"bands": bands, "samples": len(sets) - invalid, "invalid": invalid, "parameters": unc}


REPLAYS = 100            # runs of the replay for the spread over the record (each a replay: dearer than a projection)


def replay_fan(spec: Spec, data: ob.Data, estimates: dict | None = None, k: int = REPLAYS) -> dict:
    """The replay's spread over the uncertain parameters, over the record itself (Vensim's sensitivity graphs:
    confidence bounds over the whole run): each sample the model replayed with its values, and for each part
    the replay works out its percentiles at each bucket."""
    unc = uncertain(spec, estimates)
    sets = draws(unc, k)
    runs: dict[str, list[list[float]]] = {}
    invalid = 0
    for d in sets:
        r = sim.replay(spec, data, sim.plan(spec, d))
        if not r.valid:
            invalid += 1
            continue
        for ref, vals in r.values.items():
            runs.setdefault(ref, []).append(vals)
    bands = {}
    for ref, rows in runs.items():
        if len(rows) < 2:
            continue
        cols = [sorted(v for v in col if v is not None) for col in zip(*rows, strict=True)]
        bands[ref] = {f"p{round(q * 100)}": [quantile(c, q) if c else None for c in cols] for q in QUANTILES
                      if len(rows) >= TAILS or 0.1 < q < 0.9}
    return {"bands": bands, "samples": len(sets) - invalid, "invalid": invalid, "parameters": unc}


def upstream(spec: Spec, refs: list[str]) -> set[str]:
    """The parameters the model's values of these parts depend on: their equations', and those of every
    part their equations read, back through stocks to the flows that fill and drain them."""
    seen, todo, out = set(), list(refs), set()
    while todo:
        r = todo.pop()
        if r in seen:
            continue
        seen.add(r)
        kind, _, name = r.partition(".")
        if kind == "stock":
            todo += [f"flow.{f.name}" for f in spec.flows_of(name)]
            continue
        x = (spec.flows if kind == "flow" else spec.auxiliaries if kind == "auxiliary" else {}).get(name)
        if x is not None and x.equation:
            out |= set(x.equation.parameters)
            todo += list(x.equation.refs)
    return out


def said(unc: list[dict], dur=None) -> str:
    """The parameters sampled, in words: each with its range and where the range comes from."""
    def v(u, x):
        return dur(x * 3600) if dur and u.get("duration") else f"{x:.3g}"
    return "; ".join(f"{u['name']} {v(u, u['low'])} to {v(u, u['high'])}"
                     f"{' (its range)' if u['how'] == 'range' else ' (its estimate, ±2 standard errors)'}" for u in unc)


def joint_said(unc: list[dict]) -> str:
    """Which sampled parameters were drawn together, and how correlated."""
    est = [u for u in unc if u["how"] == "estimate"]
    pairs = [(a["name"], b, c) for a in est for b, c in (a.get("corr") or {}).items()
             if a["name"] < b and any(x["name"] == b for x in est) and abs(c) > 0.1]
    return "; ".join(f"{a} and {b} drawn together (correlated {c:+.2f})" for a, b, c in pairs)
