"""How much the projection depends on what is not known: Monte Carlo sensitivity analysis, as system
dynamics does it (Sterman, *Business Dynamics*, ch. 21.4.9: multivariate sensitivity; Vensim's
sensitivity runs, drawn as confidence bounds on the behaviour over time).

The parameters that are uncertain are those the model says are: a ``range: [low, high]`` written on
the parameter (sampled uniformly in it), or, where none is written, an estimate's standard error
(estimate.py: sampled normally about the value written, on its logarithm when it was searched there).
Every other number is held at its value. The samples are a Latin hypercube (each parameter's range cut
into as many equal-probability strata as there are samples, each stratum used once: McKay, Beckman and
Conover, 1979), from a fixed seed, so the same model and record draw the same fan.

Each sample is the model run again, its replay over the record and its projection past now, so the
delays' hidden stocks are each sample's own. What is drawn is the spread of the projections: for each
part and each moment ahead, the 5th, 25th, 75th and 95th percentiles across the samples. Nothing here
changes the model: it says how far the projection could be off for what the model admits it does not
know, and nothing about what it leaves out."""

from __future__ import annotations

import math
import random
from statistics import NormalDist

from ..spec.ir import Spec
from . import observe as ob
from . import simulate as sim

SAMPLES = 40
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
            logged = bool(e.get("logged")) and p.value > 0
            se = float(e["se"])
            lo, hi = ((p.value * math.exp(-2 * se), p.value * math.exp(2 * se)) if logged else (p.value - 2 * se, p.value + 2 * se))
            out.append({"name": name, "how": "estimate", "value": p.value, "se": se, "logged": logged, "low": lo, "high": hi,
                        "unit": p.unit, "duration": p.duration})
    return out


def draws(unc: list[dict], k: int = SAMPLES, seed: int = SEED) -> list[dict[str, float]]:
    """k sets of values, a Latin hypercube over the uncertain parameters."""
    if not unc or k < 1:
        return []
    rnd = random.Random(seed)
    cols = []
    for _ in unc:
        strata = [(i + rnd.random()) / k for i in range(k)]
        rnd.shuffle(strata)
        cols.append(strata)
    norm = NormalDist()
    out = []
    for i in range(k):
        got = {}
        for u, col in zip(unc, cols, strict=True):
            q = min(max(col[i], 1e-9), 1 - 1e-9)
            if u["how"] == "range":
                got[u["name"]] = u["low"] + q * (u["high"] - u["low"])
            elif u["logged"]:
                got[u["name"]] = u["value"] * math.exp(norm.inv_cdf(q) * u["se"])
            else:
                got[u["name"]] = u["value"] + norm.inv_cdf(q) * u["se"]
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
        k: int = SAMPLES, base: dict[str, float] | None = None) -> dict:
    """The projection's spread over the uncertain parameters: for each part the projection works out,
    its percentiles at each moment ahead; which parameters were sampled and how; how many runs were
    not valid (left out of the fan)."""
    unc = uncertain(spec, estimates)
    sets = draws(unc, k)
    runs: dict[str, list[list[float]]] = {}
    invalid = 0
    for d in sets:
        pl = sim.plan(spec, {**(base or {}), **d})
        run = sim.replay(spec, data, pl)
        proj = sim.project(spec, data, run, horizon, pl, points=points, inputs=inputs)
        if not run.valid or not proj.valid:
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
        bands[ref] = {f"p{round(q * 100)}": [quantile(c, q) for c in cols] for q in QUANTILES}
    return {"bands": bands, "samples": len(sets) - invalid, "invalid": invalid, "parameters": unc}


def said(unc: list[dict], dur=None) -> str:
    """The parameters sampled, in words: each with its range and where the range comes from."""
    def v(u, x):
        return dur(x * 3600) if dur and u.get("duration") else f"{x:.3g}"
    return "; ".join(f"{u['name']} {v(u, u['low'])} to {v(u, u['high'])}"
                     f"{' (its range)' if u['how'] == 'range' else ' (its estimate, ±2 standard errors)'}" for u in unc)
