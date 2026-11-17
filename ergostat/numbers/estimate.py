"""Parameters estimated from the record (system identification, as system dynamics calibrates:
Oliva 2003; Sterman ch. 21.4.7; Ljung ch. 7 and 9): each parameter marked ``estimate: true`` is given
the value that makes what it touches fit the record best, with how sure that value is.

What is fitted is the part of the model a parameter touches: each equation using it, against its
part's own readings with every input as measured (the partial-model test), and every stock its flows
fill or drain, replayed; each through the record's own measurement (``fit.pairs``). Weighted least
squares: each series' errors over its own spread (its readings' standard deviation, with a floor
of 1% of their mean), so a stock that barely moves is not drowned by one that swings. Nelder–Mead
over the parameters together, in their logarithm when they start positive (a rate never turns
negative), within a factor of a thousand of the value written; deterministic.

How sure: the covariance of the estimates from the Jacobian of the weighted errors at the optimum
(Gauss–Newton, Ljung ch. 9), widened for errors that run together in time (each series' lag-one
autocorrelation ρ), so each estimate has a standard error and parameters fitted together their
correlation; and, where the fit leaves a material error, the record's effective size, n(1 − ρ)/(1 + ρ)
independent points, which must reach ``fit.MIN_POINTS``. A value is proposed only from ``PROPOSE``
points or more, over three of the slowest time constant it touches (for a stock that only
integrates, the time things stay in it: Little's law). The last fifth of the record is held out: fitted on the rest, the estimate must fit
it better too.

An estimate is data: kept in the state directory under the model's structure (version.py), never
written into the YAML. It becomes part of the model only when the owner accepts the proposal it
makes (proposals.py), and a proposal is made only when the record supports it."""

from __future__ import annotations

import json
import math
import time

from ..durations import human as dur
from ..spec.ir import Spec
from . import fit as ft
from . import observe as ob
from . import simulate as sim
from . import version as ver

ITERATIONS = 160
SPAN = math.log(1000.0)      # how far an estimate may move from the value written, as a factor either way
HOLD_OUT = 0.2               # the last share of the record kept out of the fit, to test the estimate on
FLOOR = 0.01                 # a series' spread is at least this share of its mean, for its weight
CHANGED = 0.02               # an estimate moving a value by less than this share is not worth a change to the model
PROPOSE = 40                 # points fitted, at least, before a value is proposed
MATERIAL = 0.01              # a weighted error left past this (a tenth of the spread) is systematic enough to count ρ


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


_from_its_stock = ob.from_its_stock


class Scope:
    """What one calibration fits (Homer 2012; Oliva 2003): **each part alone** (``parts``: each
    equation with its inputs as measured, and the stocks its flows move, the rest as measured), **a
    system alone** (``system:NAME``: its stocks integrated from its flows, every input from outside it
    as measured: a partial model driven by its measured inputs), or **the whole model** (``whole``:
    every stock integrated, only the inputs from outside the model as measured)."""

    def __init__(self, key: str, label: str, names: list[str], integrate: set[str] | None = None,
                 equations: list[str] | None = None):
        self.key, self.label, self.names = key, label, names
        self.integrate, self.equations = integrate, equations or []


SCOPES = ("parts", "systems", "whole")
SCOPE_WORDS = {"parts": "each part alone", "systems": "each system alone, driven by its measured inputs",
               "whole": "the whole model"}


def _equations_in(spec: Spec, system: str | None) -> list[str]:
    from ..spec.ir import Ref
    out = []
    for kind, table in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)):
        for x in table.values():
            if x.equation and (system is None or spec.inside(Ref(kind, x.name), system)):
                out.append(f"{kind}.{x.name}")
    return sorted(out)


def scopes(spec: Spec, names: list[str], which: str = "parts") -> list[Scope]:
    """The calibrations ``which`` asks for, each with the parameters it fits and the stocks it integrates."""
    from ..spec.ir import Ref
    if which == "parts":
        return [Scope("parts", SCOPE_WORDS["parts"], g) for g in _groups(spec, names)]
    if which == "whole":
        eqs = _equations_in(spec, None)
        used = {n for r in eqs for n in _params_of(spec, r)}
        mine = [n for n in names if n in used]
        return [Scope("whole", "the whole model", mine, {s for s in spec.stocks if spec.flows_of(s)}, eqs)] if mine else []
    if which != "systems":
        raise ValueError(f"no calibration {which!r}: {', '.join(SCOPES)}")
    out, seen = [], set()
    for system in sorted(spec.systems):
        eqs = _equations_in(spec, system)
        used = {n for r in eqs for n in _params_of(spec, r)}
        mine = [n for n in names if n in used]
        stocks = {s for s in spec.stocks if spec.flows_of(s) and spec.inside(Ref("stock", s), system)}
        sig = (tuple(mine), tuple(sorted(stocks)), tuple(eqs))
        if not mine or sig in seen:
            continue
        seen.add(sig)
        out.append(Scope(f"system:{system}", f"system {system} alone, driven by its measured inputs", mine, stocks, eqs))
    return out


def _params_of(spec: Spec, ref: str) -> list[str]:
    kind, _, name = ref.partition(".")
    x = (spec.flows if kind == "flow" else spec.auxiliaries).get(name)
    return list(x.equation.parameters) if x is not None and x.equation else []


class Problem:
    """The fit of some parameters: run the touched part of the model with trial values, and read it
    through the record's measurement. Buckets before ``cut`` are fitted; from ``cut`` on, held out."""

    def __init__(self, spec: Spec, data: ob.Data, names: list[str], extra: dict | None = None,
                 extra_params: dict | None = None, cut: int | None = None, scope: Scope | None = None):
        self.spec, self.data, self.names = spec, data, names
        self.extra, self.extra_params = extra or {}, extra_params or {}
        self.scope = scope
        self.owners, self.stocks = touched(spec, set(names), self.extra)
        self.given: set[str] = set()
        if scope is not None and scope.integrate is not None:     # a system, or the whole model: one replay of it
            self.owners = set(scope.equations)
            self.stocks = {s for s in scope.integrate if any(f.equation for f in spec.flows_of(s))}
            self.given = {f"{k}.{x.name}" for k, t in (("flow", spec.flows), ("auxiliary", spec.auxiliaries)) for x in t.values()
                          if x.equation and f"{k}.{x.name}" not in self.owners
                          and any(v is not None for v in data.values.get(f"{k}.{x.name}") or [])}   # what comes in, as measured
        self.measured_owners = {r for r in self.owners if any(v is not None for v in data.values.get(r) or [])
                                and not ob.from_its_stock(spec, r)}
        self.cut = data.grid.n if cut is None else cut
        self.evaluations = 0
        self.spread = self._spread()

    def targets(self) -> list[tuple[str, str]]:
        """(series, which run it is read from): each measured equation in the partial test, each
        touched stock in the replay."""
        own = "replay" if self.scoped else "partial"
        return [(r, own) for r in sorted(self.measured_owners)] + [(f"stock.{s}", "replay") for s in sorted(self.stocks)]

    @property
    def scoped(self) -> bool:
        """Calibrated as one replay of a system (or of the whole model), not part by part."""
        return self.scope is not None and self.scope.integrate is not None

    def _spread(self) -> dict[str, float]:
        """Each series' weight: the standard deviation of its readings in the fitted part, at least
        FLOOR of their mean (and never 0)."""
        out = {}
        for r, _ in self.targets():
            vals = [v for i, v in enumerate(self.data.values.get(r) or []) if v is not None and i < self.cut]
            if not vals:
                continue
            m = sum(vals) / len(vals)
            sd = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))
            out[r] = max(sd, FLOOR * abs(m), 1e-9)
        return out

    def runs(self, values: dict[str, float]) -> dict[str, sim.Run]:
        out = {}
        if self.scoped:
            out["replay"] = sim.replay(self.spec, self.data, sim.plan(self.spec, values, self.extra, self.extra_params,
                                                                      set(self.scope.integrate), self.given))
            self.evaluations += 1
            return out
        if self.measured_owners:
            out["partial"] = sim.replay(self.spec, self.data, sim.plan(self.spec, values, self.extra, self.extra_params, set()))
        if self.stocks:
            out["replay"] = sim.replay(self.spec, self.data, sim.plan(self.spec, values, self.extra, self.extra_params, self.stocks))
        self.evaluations += 1
        return out

    def errors(self, values: dict[str, float], runs: dict | None = None) -> dict[str, list[tuple[int, float]]] | None:
        """Each series' weighted errors, (bucket, (model − measured) / spread); None when a run blew up."""
        runs = runs or self.runs(values)
        if any(not r.valid for r in runs.values()):
            return None
        out = {}
        for ref, which in self.targets():
            got = ft.pairs(self.spec, self.data, runs[which], ref) if which in runs else None
            if got and ref in self.spread:
                out[ref] = [(i, (m - a) / self.spread[ref]) for i, m, a in got]
        return out

    @staticmethod
    def _cost(errs: dict | None, part: str, cut: int) -> float:
        if errs is None:
            return math.inf
        e = [x for v in errs.values() for i, x in v if (i < cut) == (part == "fit")]
        return sum(x * x for x in e) / len(e) if e else 0.0

    def cost(self, values: dict[str, float]) -> float:
        """The weighted mean squared error over the fitted part of the record."""
        return self._cost(self.errors(values), "fit", self.cut)

    def both(self, values: dict[str, float]) -> tuple[float, float | None]:
        """The cost over the fitted part, and over the part held out (None when none is)."""
        errs = self.errors(values)
        held = self._cost(errs, "held", self.cut) if self.cut < self.data.grid.n else None
        return self._cost(errs, "fit", self.cut), held

    def n(self) -> int:
        refs = self.measured_owners | {f"stock.{s}" for s in self.stocks}
        return sum(1 for r in refs for i, v in enumerate(self.data.values.get(r) or []) if v is not None and i < self.cut)


def _invert(a: list[list[float]]) -> list[list[float]] | None:
    """A small matrix's inverse, Gauss–Jordan with partial pivoting; None when it is singular."""
    m = len(a)
    x = [row[:] + [1.0 if i == j else 0.0 for j in range(m)] for i, row in enumerate(a)]
    big = max((abs(v) for row in a for v in row), default=0.0) or 1.0
    for c in range(m):
        piv = max(range(c, m), key=lambda r: abs(x[r][c]))
        if abs(x[piv][c]) < 1e-12 * big:
            return None
        x[c], x[piv] = x[piv], x[c]
        p = x[c][c]
        x[c] = [v / p for v in x[c]]
        for r in range(m):
            if r != c and x[r][c]:
                k = x[r][c]
                x[r] = [u - k * v for u, v in zip(x[r], x[c], strict=True)]
    return [row[m:] for row in x]


def covariance(prob: Problem, best: dict[str, float], logged: list[bool]) -> dict | None:
    """The estimates' covariance, in the coordinates they were searched in (the logarithm of a
    positive one): Gauss–Newton, s²·(JᵀJ)⁻¹ over the fitted part, widened by (1 + ρ)/(1 − ρ) for
    errors that run together (ρ, their lag-one autocorrelation)."""
    names = prob.names
    base = prob.errors(best)
    if base is None:
        return None
    keys = [(r, i) for r, v in base.items() for i, _ in v if i < prob.cut]
    e0 = {(r, i): x for r, v in base.items() for i, x in v}
    cols = []
    for j, nm in enumerate(names):
        h = 1e-3 if logged[j] else 1e-3 * max(abs(best[nm]), 1e-6)
        trial = dict(best)
        trial[nm] = best[nm] * math.exp(h) if logged[j] else best[nm] + h
        got = prob.errors(trial)
        if got is None:
            return None
        e1 = {(r, i): x for r, v in got.items() for i, x in v}
        cols.append([(e1.get(k, e0[k]) - e0[k]) / h for k in keys])
    n = len(keys)
    felt = [j for j, col in enumerate(cols) if sum(x * x for x in col) > 1e-18]       # a parameter that moves nothing measured
    unseen = [names[j] for j in range(len(names)) if j not in felt]
    names, cols = [names[j] for j in felt], [cols[j] for j in felt]
    p = len(names)
    if n <= p or not p:
        return {"identifiable": False, "unseen": unseen} if not p else None
    jtj = [[sum(a * b for a, b in zip(cols[i], cols[j], strict=True)) for j in range(p)] for i in range(p)]
    inv = _invert(jtj)
    sse = sum(e0[k] ** 2 for k in keys)
    lagged = [(x, y) for r, v in base.items() for (i, x), (i2, y) in zip(v, v[1:], strict=False) if i2 < prob.cut]
    rho = sum(x * y for x, y in lagged) / max(sum(x * x for x, _ in lagged), 1e-300) if lagged else 0.0
    rho = max(0.0, min(rho, 0.95))
    s2 = sse / (n - p) * (1 + rho) / (1 - rho)
    if inv is None:
        return {"identifiable": False, "rho": rho, "unseen": unseen}
    cov = [[s2 * v for v in row] for row in inv]
    se = [math.sqrt(max(cov[i][i], 0.0)) for i in range(p)]
    corr = {names[i]: {names[j]: (cov[i][j] / (se[i] * se[j]) if se[i] and se[j] else None) for j in range(p) if j != i}
            for i in range(p)}
    return {"identifiable": True, "se": dict(zip(names, se, strict=True)), "corr": corr, "rho": rho, "n": n, "unseen": unseen,
            "n_eff": n * (1 - rho) / (1 + rho)}


def solve(prob: Problem, start: dict[str, float]) -> tuple[dict[str, float], float, float, dict]:
    """The best values, the cost before and after, and how sure they are: each one's standard error
    (in the coordinate it was searched in), their correlations, and which ended at their bound."""
    names = prob.names
    logged = [start[n] > 0 for n in names]
    x0 = [math.log(start[n]) if lg else start[n] for n, lg in zip(names, logged, strict=True)]
    scale = [0.5 if lg else (abs(start[n]) * 0.5 or 1.0) for n, lg in zip(names, logged, strict=True)]

    def values(x):                       # within a factor of a thousand of where it started: further is a question of structure
        return {n: (math.exp(max(x0[i] - SPAN, min(x0[i] + SPAN, v))) if lg else v)
                for i, (n, v, lg) in enumerate(zip(names, x, logged, strict=True))}
    before = prob.cost(start)
    best, after = nelder_mead(lambda x: prob.cost(values(x)), x0, scale)
    got = values(best)
    at_bound = [n for i, (n, lg) in enumerate(zip(names, logged, strict=True)) if lg and abs(best[i] - x0[i]) >= SPAN * 0.98]
    sure = covariance(prob, got, logged) or {"identifiable": False}
    for n in sure.get("unseen") or []:                   # it moves nothing measured: the search wandered on a flat cost
        got[n] = start[n]
        at_bound = [x for x in at_bound if x != n]
    sure["at_bound"] = at_bound
    sure["logged"] = dict(zip(names, logged, strict=True))
    return got, before, after, sure


def path(p, structure: str, which: str = "parts"):
    return p.dir / "estimates" / (f"{structure}.json" if which == "parts" else f"{structure}.{which}.json")


def load(p, spec: Spec, which: str = "parts") -> dict:
    """The estimates kept for this structure and calibration: key → {parameter, scope, value, se, before,
    after, n, when, window, ...}; the key is the parameter's name (``name@system`` for a system's)."""
    try:
        return json.loads(path(p, ver.structure(spec), which).read_text())
    except (OSError, ValueError):
        return {}


def load_all(p, spec: Spec) -> dict[str, dict]:
    """Every calibration's estimates kept for this structure, by calibration."""
    return {w: got for w in SCOPES if (got := load(p, spec, w))}


def residence(spec: Spec, data: ob.Data, stock: str) -> float | None:
    """How long things stay in a stock (hours), by Little's law: its mean level over its mean outflow,
    as measured. The time scale of a stock that only integrates, and has no time constant of its own."""
    level = [v for v in data.values.get(f"stock.{stock}") or [] if v is not None]
    outs = [f"flow.{f.name}" for f in spec.flows_of(stock) if f.source == stock]
    rates = [sum(x for x in vals if x is not None) / max(1, sum(1 for x in vals if x is not None))
             for vals in (data.values.get(r) or [] for r in outs) if any(x is not None for x in vals)]
    out = sum(rates)
    if not level or out <= 0:
        return None
    return (sum(level) / len(level)) / out


def slowest(spec: Spec, run: sim.Run, owners: set[str], stocks: set[str], data: ob.Data | None = None) -> float | None:
    """The slowest time constant (hours) the replay met in what a parameter touches, or, for a stock
    with none, how long things stay in it."""
    got = [run.time_constants[r] for r in (*owners, *(f"stock.{s}" for s in stocks)) if r in run.time_constants]
    if data is not None:
        got += [t for s in stocks if f"stock.{s}" not in run.time_constants and (t := residence(spec, data, s))]
    return max(got) if got else None


def key_of(scope: Scope, name: str) -> str:
    return f"{name}@{scope.key[7:]}" if scope.key.startswith("system:") else name


def estimate(p, snap: dict | None = None, n: int | None = None, which: str = "parts") -> dict:
    """Estimate every ``estimate: true`` parameter from the record on the reference window, by the
    calibration ``which`` asks for (each part alone, each system alone, or the whole model), keep the
    estimates under the model's structure, and return them."""
    spec: Spec = p.model.spec
    data = ob.measured(p, ob.reference(p, (snap or {}).get("at"), n))
    names = sorted(n for n, x in spec.parameters.items() if x.estimate and not x.table)
    out = load(p, spec, which)
    if not names:
        return out
    base = sim.replay(spec, data)
    span = data.grid.until - data.grid.since
    now = time.time()
    cut = max(1, int(round(data.grid.n * (1 - HOLD_OUT))))
    for sc in scopes(spec, names, which):
        group = sc.names
        prob = Problem(spec, data, group, cut=cut, scope=sc)
        tc = slowest(spec, base, prob.owners, prob.stocks, data)
        common = {"when": now, "window": span, "n": prob.n(), "slowest": tc, "with": [], "fitted_to": [r for r, _ in prob.targets()],
                  "scope": sc.key, "scope_words": sc.label}
        if prob.n() < ft.MIN_POINTS:
            for nm in group:
                out[key_of(sc, nm)] = {**common, "parameter": nm, "value": None, "why": f"too little measured of what it moves "
                                       f"({prob.n()} points; at least {ft.MIN_POINTS} are needed)"}
            continue
        start = {nm: (spec.parameters[nm].value if spec.parameters[nm].value is not None else 1.0) for nm in group}
        best, before, after, sure = solve(prob, start)
        held_before, held_after = prob.both(start)[1], prob.both(best)[1]
        for nm in group:
            se = (sure.get("se") or {}).get(nm)
            out[key_of(sc, nm)] = {**common, "parameter": nm, "value": best[nm], "declared": spec.parameters[nm].value,
                       "before": before, "after": after,
                       "held_before": held_before, "held_after": held_after, "with": [x for x in group if x != nm],
                       "se": se, "logged": sure["logged"][nm], "corr": (sure.get("corr") or {}).get(nm, {}),
                       "identifiable": sure.get("identifiable", False) and nm not in (sure.get("unseen") or []),
                       "unseen": nm in (sure.get("unseen") or []), "at_bound": nm in sure["at_bound"],
                       "n_eff": sure.get("n_eff"), "rho": sure.get("rho"),
                       "weights": prob.spread, "evaluations": prob.evaluations}
    f = path(p, ver.structure(spec), which)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1))
    return out


def judged(e: dict, declared: float | None) -> str | None:
    """Why an estimate is not to be proposed, or None when the record supports it: enough record
    for the slowest time constant it touches, not at its bound, identifiable, more than two
    standard errors from the value written, and better on the record held out."""
    if e.get("value") is None:
        return e.get("why") or "not estimated"
    if e.get("slowest") and e["window"] < ft.COVER * e["slowest"] * 3600:
        return (f"the record spans {dur(e['window'])}, under {ft.COVER:g} of the slowest time constant it touches "
                f"({dur(e['slowest'] * 3600)}): too little to say")
    if e["n"] < PROPOSE:
        return f"{e['n']} points fitted, under the {PROPOSE} a proposal needs: too little record to say"
    if e.get("n_eff") is not None and e["n_eff"] < ft.MIN_POINTS and e.get("after", 0) > MATERIAL:
        return (f"its errors run together (lag-one autocorrelation {e.get('rho', 0):.2f}), so its {e['n']} points hold about "
                f"{e['n_eff']:.0f} independent ones, under {ft.MIN_POINTS}: too little record to say")
    if e.get("at_bound"):
        return ("it ran to its bound (a thousand times from the value written): no value of it fits, a question of "
                "structure, not of size")
    if e.get("unseen"):
        return "nothing it moves is measured in the record: there is nothing to estimate it from"
    if not e.get("identifiable") or e.get("se") is None:
        return "the record does not tell it apart (it moves what it fits too little, or as another parameter does)"
    if declared is not None:
        moved = (math.log(e["value"] / declared) if e.get("logged") and declared > 0 and e["value"] > 0
                 else e["value"] - declared)
        if abs(moved) <= 2 * e["se"]:
            return "within two standard errors of the value written: the record does not say it is wrong"
        if abs(e["value"] - declared) <= CHANGED * max(abs(declared), 1e-12):
            return f"it moves the value written by less than {CHANGED:.0%}"
    if e.get("held_before") is not None and e.get("held_after") is not None and not e["held_after"] < e["held_before"]:
        return "it fits the record held out (its last fifth) no better than the value written"
    return None


def said_se(e: dict, value: float) -> float | None:
    """A standard error in the value's own units (from the logarithm's, when it was searched there)."""
    se = e.get("se")
    if se is None:
        return None
    return value * se if e.get("logged") else se


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


def r_squared(fitted: list[float], ys: list[float]) -> float | None:
    """1 − SSE/SST: the share of the readings' variation about their mean the fit explains (with or
    without a constant term: never the squared correlation, which a fit through 0 overstates)."""
    my = sum(ys) / len(ys)
    sst = sum((y - my) ** 2 for y in ys)
    if sst <= 0:
        return None
    return 1.0 - sum((f - y) ** 2 for f, y in zip(fitted, ys, strict=True)) / sst


def linear(data: ob.Data, target: str, causes: list[str], intercept: bool, times: str | None = None) -> dict | None:
    """``target`` as a + Σ bᵢ·causeᵢ (or, with ``times``, ``times`` · (Σ bᵢ·causeᵢ), the first cause
    then 1: a first-order outflow, its stock times a fraction) over the buckets where all are
    measured: the coefficients, R² (1 − SSE/SST) and n."""
    cols = [*(c for c in causes if c != times)]
    pts = []
    for i, y in enumerate(data.values.get(target) or []):
        row = [data.values[c][i] if data.values.get(c) else None for c in cols]
        s = data.values[times][i] if times and data.values.get(times) else (1.0 if not times else None)
        if y is None or s is None or None in row:
            continue
        pts.append(([s] + [s * x for x in row] if times else ([1.0] if intercept else []) + row, y))
    if len(pts) < max(ft.MIN_POINTS, len(cols) + 3):
        return None
    rows, ys = [r for r, _ in pts], [y for _, y in pts]
    coef = solve_linear(rows, ys)
    if coef is None:
        return None
    fitted = [sum(c * x for c, x in zip(coef, r, strict=True)) for r in rows]
    return {"coef": coef, "r2": r_squared(fitted, ys), "n": len(pts), "intercept": intercept and not times, "columns": cols}
