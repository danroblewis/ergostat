"""Parameters estimated from the record (system identification, as system dynamics calibrates:
Oliva 2003; Sterman ch. 21): each parameter marked ``estimate: true`` is given the value that makes
the replay fit the record best, and a flow with declared causes and no equation may be given one
(a coefficient for each cause, fitted by least squares on what was measured).

What is fitted is the part of the model a parameter touches: each equation using it, against its
part's own readings where it has them (a partial-model test, every input as measured), and every
stock its flow fills or drains, replayed. Nelder–Mead over the parameters together (in their
logarithm when they start positive, so a rate never turns negative), deterministic.

An estimate is data: kept in the state directory under the model's structure (version.py), never
written into the YAML. It becomes part of the model only when the owner accepts the proposal it
makes (proposals.py)."""

from __future__ import annotations

import json
import math
import time

from ..spec.ir import Spec
from . import fit as ft
from . import simulate as sim
from . import version as ver

ITERATIONS = 160
SPAN = math.log(1000.0)      # how far an estimate may move from the value written, as a factor either way


def nelder_mead(f, x0: list[float], scale: list[float], iterations: int = ITERATIONS, tol: float = 1e-9) -> tuple[list[float], float]:
    """The minimum of ``f`` near ``x0``: the simplex method (Nelder and Mead, 1965), its usual
    coefficients."""
    n = len(x0)
    pts = [list(x0)] + [[x0[j] + (scale[j] if j == i else 0.0) for j in range(n)] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iterations):
        order = sorted(range(n + 1), key=lambda i: vals[i])
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol):
            break
        c = [sum(p[j] for p in pts[:-1]) / n for j in range(n)]
        refl = [c[j] + (c[j] - pts[-1][j]) for j in range(n)]
        fr = f(refl)
        if fr < vals[0]:
            exp = [c[j] + 2 * (c[j] - pts[-1][j]) for j in range(n)]
            fe = f(exp)
            pts[-1], vals[-1] = (exp, fe) if fe < fr else (refl, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = refl, fr
        else:
            con = [c[j] + 0.5 * (pts[-1][j] - c[j]) for j in range(n)]
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:
                for i in range(1, n + 1):
                    pts[i] = [pts[0][j] + 0.5 * (pts[i][j] - pts[0][j]) for j in range(n)]
                    vals[i] = f(pts[i])
    best = min(range(n + 1), key=lambda i: vals[i])
    return pts[best], vals[best]


def touched(spec: Spec, names: set[str], extra: dict | None = None) -> tuple[set[str], set[str]]:
    """The equations using these parameters, and the stocks their flows fill or drain."""
    owners = {f"flow.{f.name}" for f in spec.flows.values() if f.equation and names & set(f.equation.parameters)}
    owners |= {f"auxiliary.{a.name}" for a in spec.auxiliaries.values() if a.equation and names & set(a.equation.parameters)}
    owners |= {r for r, e in (extra or {}).items() if names & set(e.parameters)}
    stocks: set[str] = set()
    todo = list(owners)
    seen = set(todo)
    while todo:                                     # what follows from them at once: auxiliaries, flows, their stocks
        r = todo.pop()
        kind, _, name = r.partition(".")
        if kind == "flow" and name in spec.flows:
            f = spec.flows[name]
            stocks |= {s for s in (f.source, f.target) if s}
        for table, k in ((spec.flows, "flow"), (spec.auxiliaries, "auxiliary")):
            for x in table.values():
                e = (extra or {}).get(f"{k}.{x.name}") or x.equation
                if e and r in e.refs and f"{k}.{x.name}" not in seen:
                    seen.add(f"{k}.{x.name}")
                    todo.append(f"{k}.{x.name}")
    return seen, stocks


def _from_its_stock(spec: Spec, ref: str) -> bool:
    """A flow measured only by its stock's own changes (``changes:``): its readings are the stock's,
    differenced and smoothed, so the stock's replay tests its equation, and better."""
    kind, _, name = ref.partition(".")
    f = spec.flows.get(name) if kind == "flow" else None
    return bool(f and f.sensors and all(x.changes for x in f.sensors.values()))


class Problem:
    """The fit of some parameters: run the touched part of the model with trial values."""

    def __init__(self, spec: Spec, data: sim.Data, names: list[str], extra: dict | None = None,
                 extra_params: dict | None = None):
        self.spec, self.data, self.names = spec, data, names
        self.extra, self.extra_params = extra or {}, extra_params or {}
        self.owners, self.stocks = touched(spec, set(names), self.extra)
        self.measured_owners = {r for r in self.owners if any(v is not None for v in data.values.get(r) or [])
                                and not _from_its_stock(spec, r)}
        self.evaluations = 0

    def fit(self, values: dict[str, float], integrate: bool = True) -> dict:
        pl = sim.plan(self.spec, values, self.extra, self.extra_params, self.stocks if integrate else set())
        run = sim.replay(self.spec, self.data, pl)
        self.evaluations += 1
        return ft.compare(self.spec, self.data, run)

    def cost(self, values: dict[str, float]) -> float:
        """The partial test (every input as measured) of each measured equation, plus the replay of
        each stock it moves."""
        total = 0.0
        if self.measured_owners:
            got = ft.objective(self.fit(values, integrate=False), self.measured_owners)
            total += got if got is not None else 0.0
        if self.stocks:
            got = ft.objective(self.fit(values), {f"stock.{s}" for s in self.stocks})
            total += got if got is not None else 0.0
        return total

    def n(self) -> int:
        refs = self.measured_owners | {f"stock.{s}" for s in self.stocks}
        return sum(1 for r in refs for v in self.data.values.get(r) or [] if v is not None)


def solve(prob: Problem, start: dict[str, float]) -> tuple[dict[str, float], float, float]:
    """The best values, with the cost before and after."""
    names = prob.names
    logged = [start[n] > 0 for n in names]
    x0 = [math.log(start[n]) if lg else start[n] for n, lg in zip(names, logged, strict=True)]
    scale = [0.5 if lg else (abs(start[n]) * 0.5 or 1.0) for n, lg in zip(names, logged, strict=True)]

    def values(x):                       # within a factor of a thousand of where it started: further is a question of structure
        return {n: (math.exp(max(x0[i] - SPAN, min(x0[i] + SPAN, v))) if lg else v)
                for i, (n, v, lg) in enumerate(zip(names, x, logged, strict=True))}
    before = prob.cost(start)
    best, after = nelder_mead(lambda x: prob.cost(values(x)), x0, scale)
    return values(best), before, after


def path(p, structure: str):
    return p.dir / "estimates" / f"{structure}.json"


def load(p, spec: Spec) -> dict:
    """The estimates kept for this structure: name → {value, before, after, n, when, window}."""
    try:
        return json.loads(path(p, ver.structure(spec)).read_text())
    except (OSError, ValueError):
        return {}


def estimate(p, snap: dict, n: int | None = None) -> dict:
    """Estimate every ``estimate: true`` parameter from the record in the window, keep the estimates
    under the model's structure, and return them."""
    spec: Spec = p.model.spec
    since, until = ft.series.span(p, snap)
    data = sim.measured(p, sim.Grid(since, until, n or ft.series.POINTS))
    names = sorted(n for n, x in spec.parameters.items() if x.estimate and not x.table)
    out = load(p, spec)
    if not names:
        return out
    groups = _groups(spec, names)
    now = time.time()
    for group in groups:
        prob = Problem(spec, data, group)
        if prob.n() < 3:
            for nm in group:
                out[nm] = {"value": None, "why": "too little measured of what it moves to estimate it", "when": now,
                           "window": until - since, "n": prob.n()}
            continue
        start = {nm: (spec.parameters[nm].value if spec.parameters[nm].value is not None else 1.0) for nm in group}
        best, before, after = solve(prob, start)
        r2 = _r2(prob, best)
        for nm in group:
            out[nm] = {"value": best[nm], "declared": spec.parameters[nm].value, "before": before, "after": after,
                       "r2": r2, "n": prob.n(), "when": now, "window": until - since, "with": [x for x in group if x != nm],
                       "fitted_to": sorted(prob.measured_owners | {f"stock.{s}" for s in prob.stocks})}
    f = path(p, ver.structure(spec))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1))
    return out


def _r2(prob: Problem, values: dict) -> float | None:
    """How well what it was fitted to follows, with the estimates: the mean R² over those series."""
    got = prob.fit(values, integrate=bool(prob.stocks))
    if prob.measured_owners:
        part = prob.fit(values, integrate=False)
        got["equations"] = part["equations"]
    r2 = [s["r2"] for refs, part in ((prob.measured_owners, "equations"), ({f"stock.{s}" for s in prob.stocks}, "stocks"))
          for r, s in got[part].items() if r in refs and s and s["r2"] is not None]
    return sum(r2) / len(r2) if r2 else None


def _groups(spec: Spec, names: list[str]) -> list[list[str]]:
    """Parameters that share an equation (or a stock) are fitted together; the others apart."""
    groups: list[set[str]] = []
    for nm in names:
        owners, stocks = touched(spec, {nm})
        mine = {nm}
        for g in list(groups):
            o2, s2 = touched(spec, g)
            if owners & o2 or stocks & s2:
                mine |= g
                groups.remove(g)
        groups.append(mine)
    return [sorted(g) for g in groups]


# ---- an equation for a flow that has none: a coefficient for each declared cause, by least squares

def solve_linear(rows: list[list[float]], ys: list[float]) -> list[float] | None:
    """Least squares by the normal equations, Gaussian elimination with partial pivoting."""
    m = len(rows[0])
    a = [[sum(r[i] * r[j] for r in rows) for j in range(m)] + [sum(r[i] * y for r, y in zip(rows, ys, strict=True))]
         for i in range(m)]
    for c in range(m):
        piv = max(range(c, m), key=lambda r: abs(a[r][c]))
        if abs(a[piv][c]) < 1e-12:
            return None
        a[c], a[piv] = a[piv], a[c]
        for r in range(m):
            if r != c:
                k = a[r][c] / a[c][c]
                a[r] = [x - k * y for x, y in zip(a[r], a[c], strict=True)]
    return [a[i][m] / a[i][i] for i in range(m)]


def linear(data: sim.Data, target: str, causes: list[str], intercept: bool) -> dict | None:
    """``target`` as a + Σ bᵢ·causeᵢ over the buckets where all are measured: the coefficients, R²
    and n."""
    pts = [(row, y) for i, y in enumerate(data.values.get(target) or [])
           if y is not None and None not in (row := [data.values[c][i] if data.values.get(c) else None for c in causes])]
    if len(pts) < max(6, len(causes) + 3):
        return None
    rows = [([1.0] if intercept else []) + list(r) for r, _ in pts]
    ys = [y for _, y in pts]
    coef = solve_linear(rows, ys)
    if coef is None:
        return None
    fitted = [sum(c * x for c, x in zip(coef, r, strict=True)) for r in rows]
    st = ft.stats(fitted, ys)
    return {"coef": coef, "r2": st["r2"] if st else None, "n": len(pts), "intercept": intercept}
