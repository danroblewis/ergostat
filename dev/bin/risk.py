"""The pools' risk, in expected interventions a day (docs/roadmap/overnight/pool-control.md): what the pool tuner
(pools.py) weighs against the owner's risk tolerance. Pure: the record's items in, numbers out.

Two harms, each ending in someone stepping in:
  factory damage     factory-caused interventions (an allowlist of classes, or `factory: true`) per gap processed (a
                     verdict: approved or parked); review findings and a reviewer's park are not harm
  low quality        escapes per merged gap: reverted (gap.reverted, or its upgrade reverted), `broke_main` said of
                     it, or named by a later gap or intervention as its `caused_by`

Each is a Poisson rate with a Gamma posterior, per implementor pool size n (the size in run/pools.json's history when
the evidence happened). Its prior is weak (shape 0.5) with the mean of the other sizes' evidence; a size above the
largest tried has that mean times (1 + steps above it), so its bound is high until it is run. risk(n) = (rates) x gaps
a day at n (n x 24 / the cycle hours, Little's law); its bound adds the two rates' 90% bounds (conservative: as if
both were at their bound at once)."""

from __future__ import annotations

import math
import re
from pathlib import Path

FACTORY = ("environment-defect", "self-reference", "factory-missing-capability", "queue-interleaving")
PRIOR = 0.5                           # the Gamma prior's shape, and its mean per gap with no evidence at all
Q = 0.9                               # the bound: this quantile of the posterior
MIN_CYCLE = 0.5                       # hours: a cycle time below this is taken as this (gaps a day stay finite)
MODEL = Path(__file__).resolve().parent.parent / "model" / "pools.yaml"
TOLERANCE = re.compile(r"^  risk-tolerance:\s*\n(?:    .*\n)*?    value:\s*([0-9.]+)", re.M)


def tolerance(model: Path = MODEL) -> float:
    """The parameter risk-tolerance in dev/model/pools.yaml. One that cannot be read is 0: the pools go down to 1."""
    try:
        m = TOLERANCE.search(model.read_text())
    except OSError:
        return 0.0
    return float(m.group(1)) if m else 0.0


def ids(v) -> list[str]:
    return [v] if isinstance(v, str) else list(v or [])


def size_at(history: list, t: float) -> int:
    """The implementor pool at time t: the last change at or before it (1 before any)."""
    n = 1
    for at, size in sorted(history):
        if at > t:
            break
        n = int(size)
    return n


def when(v) -> float:
    """A time from the record; one missing is now (the evidence counts against the current pool, the worst case)."""
    return float(v) if v else math.inf


def factory_caused(iv: dict) -> bool:
    f = iv["fields"]
    return f.get("factory") in (True, "true") or str(f.get("class") or "") in FACTORY


def evidence(gaps: list[dict], interventions: list[dict], upgrades: list[dict], history: list) -> dict:
    """{pool size: [factory interventions, gaps processed, escapes, gaps merged]}."""
    ev: dict[int, list[int]] = {}

    def add(t: float, i: int) -> None:
        ev.setdefault(size_at(history, t), [0, 0, 0, 0])[i] += 1

    blamed = {u["fields"].get("gap") for u in upgrades if u["state"] == "reverted"}
    blamed |= {c for x in [*gaps, *interventions] for c in ids(x["fields"].get("caused_by"))}
    for g in gaps:
        f = g["fields"]
        if f.get("approved_at") or f.get("parked_at"):
            add(float(f.get("approved_at") or f["parked_at"]), 1)
        if g["state"] == "merged" and f.get("merged_at"):     # (a split's join has no merge of its own)
            add(float(f["merged_at"]), 3)
            if f.get("reverted") or f.get("broke_main") or g["id"] in blamed:
                add(float(f["merged_at"]), 2)
    for iv in interventions:
        if factory_caused(iv):
            add(when(iv["fields"].get("recorded_at") or iv.get("first")), 0)
    return ev


def gamma_cdf(a: float, x: float) -> float:
    """The regularized lower incomplete gamma P(a, x), by its series."""
    if x <= 0:
        return 0.0
    term = total = 1.0 / a
    for k in range(1, 100000):
        term *= x / (a + k)
        total += term
        if term < total * 1e-13:
            break
    return min(1.0, total * math.exp(-x + a * math.log(x) - math.lgamma(a)))


def upper(a: float, b: float, q: float = Q) -> float:
    """The q quantile of Gamma(shape a, rate b), by bisection."""
    lo, hi = 0.0, a + 12 * math.sqrt(a) + 12
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gamma_cdf(a, mid) < q else (lo, mid)
    return hi / b


def table(ev: dict, most: int, cycle_hours: float) -> dict:
    """{n: its rates (mean and bound, per gap), gaps a day, risk and risk bound (interventions a day)}, n = 1..most."""
    tried = max([n for n, x in ev.items() if x[1] or x[3]] or [1])
    totals = [sum(x[i] for x in ev.values()) for i in range(4)]
    per_day_1 = 24 / max(MIN_CYCLE, cycle_hours)
    out = {}
    for n in range(1, most + 1):
        mine = ev.get(n, [0, 0, 0, 0])
        rates = {}
        for name, hit, expo in (("factory", 0, 1), ("escape", 2, 3)):
            others = (totals[hit] - mine[hit], totals[expo] - mine[expo])
            mean0 = (PRIOR + others[0]) / (1 + others[1]) * (1 + max(0, n - tried))
            a, b = PRIOR + mine[hit], PRIOR / mean0 + mine[expo]
            rates[name] = [round(a / b, 4), round(upper(a, b), 4)]
        per_day = n * per_day_1
        out[n] = {"rates": rates, "per_day": round(per_day, 2), "evidence": mine,
                  "risk": round(sum(r[0] for r in rates.values()) * per_day, 3),
                  "bound": round(sum(r[1] for r in rates.values()) * per_day, 3)}
    return out


def target(tab: dict, tol: float, demand: int) -> int:
    """The largest pool whose risk bound, and every smaller one's, is within the tolerance (so each step up on the way
    is too), and not above the ready demand; at least 1."""
    n = 0
    while n + 1 in tab and tab[n + 1]["bound"] <= tol and n + 1 <= demand:
        n += 1
    return max(1, n)


def step(n: int, tab: dict, tol: float, demand: int, since_raise: int, probation: int) -> tuple[str | None, int, str]:
    """(raise, lower or None; to; why). Down by one at once when the pool's own bound crosses the tolerance; toward
    the target one step at a time, a raise only once `probation` gaps were processed since the last one."""
    to = target(tab, tol, demand)
    if n > 1 and n in tab and tab[n]["bound"] > tol:
        return "lower", n - 1, f"risk bound {tab[n]['bound']}/day at {n} is over the tolerance {tol:g}"
    if to < n:
        return "lower", n - 1, f"the target is {to} (demand {demand}, tolerance {tol:g})"
    if to > n and since_raise < probation:
        return None, n, f"on probation: {since_raise} of {probation} gaps since the last raise"
    if to > n:
        return "raise", n + 1, f"risk bound {tab[n + 1]['bound']}/day at {n + 1} within the tolerance {tol:g}"
    return None, n, f"at the target {to}"


def processed_since(gaps: list[dict], at: float) -> int:
    """Gaps given a verdict (approved or parked) at or after ``at``."""
    return sum(float(g["fields"].get("approved_at") or g["fields"].get("parked_at") or -1) >= at for g in gaps)
