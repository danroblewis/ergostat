"""System identification of a loop's process from the record (Ljung, *System Identification*, ch.
4, 7, 16; Seborg et al., *Process Dynamics and Control*, ch. 7): from what the loop's controller
moves (u) to what its goal holds (y), as a first-order process with dead time,

    P(s) = K e^(−θs) / (τs + 1)        or, when the lag is longer than the record tells apart,
    P(s) = k e^(−θs) / s               (an integrator with dead time),

fitted as an output-error model: the model is driven by the measured u alone, from the state the
record starts in, and compared with every reading of y (the model's own simulation, never a
one-step-ahead prediction, which a slow process fits trivially). Measured inputs that also move y
(an input from outside the model, a stock beside the path) are fitted with it, each its own gain
through the same lag, so what they did is not blamed on u.

For each (τ, θ) the gains are linear, so they are solved by least squares; τ and θ are searched (a
grid, then Nelder–Mead), θ between buckets by interpolation. The record is split: the first part
fitted, the last fifth held out (or, for a step test, the step up fitted and the step back held
out). What is said of the result:

- **fit**, on each part: 100 (1 − ‖y − ŷ‖ / ‖y − ȳ‖), the share of the readings' variation the model
  follows (MATLAB's ``compare``);
- **standard errors** of K, τ and θ from the Jacobian of the errors at the optimum (Gauss–Newton),
  widened for errors that run together in time ((1 + ρ)/(1 − ρ), ρ their lag-one autocorrelation);
- **whiteness** of the errors held out (Ljung–Box: their autocorrelation up to m lags against
  χ²(m) at 95%), and their **independence** from u (the cross-correlation within ±1.96/√n): an
  output-error model needs only the second, and a first-order model of a real process rarely has
  the first; both are said;
- **in closed loop**: identified from the loop working (not from a step test), u follows the
  disturbances, and the estimate may be biased toward the controller's inverse (Ljung ch. 13).

A process is proposed only when the record tells it apart (``judge``)."""

from __future__ import annotations

import math

from ..numbers.estimate import _invert, nelder_mead

HOLD_OUT = 0.2
FIT_MIN = 50.0           # % of the variation held out the model must follow
MOVES_MIN = 3            # steps of u in the part fitted, at least (a step test: one each way)
POINTS_MIN = 40
SPAN_MIN = 5.0           # the part fitted spans at least this many of τ + θ
SE_MAX = 0.5             # a standard error past this share of its value: not told apart
LAGS = 20


def _ffill(xs: list) -> list[float] | None:
    out, last = [], next((x for x in xs if x is not None), None)
    if last is None:
        return None
    for x in xs:
        last = x if x is not None else last
        out.append(float(last))
    return out


def filtered(x: list[float], h: float, tau: float | None, theta: float) -> list[float]:
    """x through e^(−θs)/(τs + 1) (or e^(−θs)/s when τ is None), sampled every h: the state at each
    sample, from equilibrium with x's first value (from 0, for an integrator). Between samples x is
    held; θ between samples is interpolated."""
    n = len(x)
    d = int(theta // h)
    f = theta / h - d
    a = math.exp(-h / tau) if tau else None
    s = x[0] if tau else 0.0
    out = [0.0] * n
    x0 = x[0]
    for k in range(n):
        out[k] = s
        i = k - d
        xi = x[i] if i >= 0 else x0
        xj = x[i - 1] if i - 1 >= 0 else x0
        ud = (1 - f) * xi + f * xj
        s = a * s + (1 - a) * ud if a is not None else s + h * ud
    return out


def _lstsq(cols: list[list[float]], ys: list[float], idx: list[int]) -> list[float] | None:
    """Least squares on the rows ``idx``, columns scaled first so their sizes do not matter."""
    m = len(cols)
    scale = [max((abs(c[i]) for i in idx), default=0.0) or 1.0 for c in cols]
    a = [[sum(cols[r][i] * cols[c][i] for i in idx) / (scale[r] * scale[c]) for c in range(m)] for r in range(m)]
    inv = _invert(a)
    if inv is None:
        return None
    b = [sum(cols[r][i] * ys[i] for i in idx) / scale[r] for r in range(m)]
    return [sum(inv[r][c] * b[c] for c in range(m)) / scale[r] for r in range(m)]


class Problem:
    def __init__(self, h: float, u: list[float], y: list[float | None], others: dict[str, list[float]],
                 est: list[int], val: list[int]):
        self.h, self.u, self.y, self.others = h, u, y, others
        self.est, self.val = est, val
        self.ys = [v if v is not None else 0.0 for v in y]

    def columns(self, tau: float | None, theta: float) -> list[list[float]]:
        cols = [filtered(self.u, self.h, tau, theta)]
        cols += [filtered(x, self.h, tau, theta) for x in self.others.values()]
        cols.append([1.0] * len(self.u))
        return cols

    def solve(self, tau: float | None, theta: float, idx: list[int] | None = None):
        cols = self.columns(tau, theta)
        coef = _lstsq(cols, self.ys, idx or self.est)
        if coef is None:
            return None, None, math.inf
        pred = [sum(c * col[k] for c, col in zip(coef, cols, strict=True)) for k in range(len(self.u))]
        sse = sum((self.ys[k] - pred[k]) ** 2 for k in (idx or self.est))
        return coef, pred, sse


def fit_share(y: list[float | None], pred: list[float], idx: list[int], level: bool = False) -> float | None:
    """100 (1 − ‖y − ŷ‖/‖y − ȳ‖) over ``idx``; with ``level``, each side's own mean taken out first,
    as each data set is detrended before it is compared (Ljung ch. 14): whether the model moves as the
    record does, whatever level the inputs not measured left it at."""
    got = [(y[k], pred[k]) for k in idx if y[k] is not None]
    if len(got) < 3:
        return None
    if level:
        ma, mb = sum(a for a, _ in got) / len(got), sum(b for _, b in got) / len(got)
        got = [(a - ma, b - mb) for a, b in got]
    my = sum(a for a, _ in got) / len(got)
    den = math.sqrt(sum((a - my) ** 2 for a, _ in got))
    if den <= 0:
        return None
    return 100.0 * (1 - math.sqrt(sum((a - b) ** 2 for a, b in got)) / den)


def acf(e: list[float], m: int) -> list[float]:
    n = len(e)
    me = sum(e) / n
    d = [x - me for x in e]
    den = sum(x * x for x in d) or 1.0
    return [sum(d[k] * d[k + j] for k in range(n - j)) / den for j in range(1, m + 1)]


def chi2_95(m: int) -> float:
    """χ²(m) at 95%, by Wilson and Hilferty's approximation."""
    z = 1.6449
    return m * (1 - 2 / (9 * m) + z * math.sqrt(2 / (9 * m))) ** 3


def whiteness(e: list[float], lags: int = LAGS) -> dict | None:
    n = len(e)
    m = min(lags, n // 4)
    if m < 3:
        return None
    r = acf(e, m)
    q = n * (n + 2) * sum(rj * rj / (n - j) for j, rj in enumerate(r, start=1))
    lim = chi2_95(m)
    return {"q": q, "limit": lim, "lags": m, "white": q <= lim, "rho1": r[0], "acf": r}


def independence(e: list[float], u: list[float], lags: int = LAGS) -> dict | None:
    """The cross-correlation of the errors with u, u leading by 0 to m samples, against ±1.96/√n."""
    n = len(e)
    m = min(lags, n // 4)
    if m < 3:
        return None
    me, mu = sum(e) / n, sum(u) / n
    de, du = [x - me for x in e], [x - mu for x in u]
    den = math.sqrt(sum(x * x for x in de) * sum(x * x for x in du))
    if den <= 0:
        return {"max": 0.0, "bound": 1.96 / math.sqrt(n), "ok": True, "lags": m, "flat": True}
    r = [sum(de[k] * du[k - j] for k in range(j, n)) / den for j in range(m + 1)]
    big = max(abs(x) for x in r)
    return {"max": big, "bound": 1.96 / math.sqrt(n), "ok": big <= 1.96 / math.sqrt(n), "lags": m}


def moves(u: list[float], idx: list[int]) -> list[tuple[int, float]]:
    """The steps of u: changes from one bucket to the next of more than a twentieth of its range."""
    vals = [u[k] for k in idx]
    rng = (max(vals) - min(vals)) if vals else 0.0
    if rng <= 0:
        return []
    out = []
    for a, b in zip(idx, idx[1:], strict=False):
        if abs(u[b] - u[a]) > 0.05 * rng:
            out.append((b, u[b] - u[a]))
    return out


def _search(prob: Problem, integrating: bool, tau_max: float, theta_max: float) -> tuple[float | None, float, float]:
    h = prob.h
    thetas = [theta_max * i / 11 for i in range(12)]
    if integrating:
        best = min((prob.solve(None, th)[2], th) for th in thetas)
        x, v = nelder_mead(lambda z: prob.solve(None, min(max(z[0], 0.0), theta_max))[2], [best[1]], [h], 40)
        return None, min(max(x[0], 0.0), theta_max), v
    lo = math.log(h / 4)
    hi = math.log(tau_max)
    taus = [math.exp(lo + (hi - lo) * i / 13) for i in range(14)]
    best = min((prob.solve(t, th)[2], t, th) for t in taus for th in thetas)

    def f(z):
        t = math.exp(min(max(z[0], lo), hi))
        th = min(max(z[1], 0.0), theta_max)
        return prob.solve(t, th)[2]
    x, v = nelder_mead(f, [math.log(best[1]), best[2]], [0.3, h], 80)
    return math.exp(min(max(x[0], lo), hi)), min(max(x[1], 0.0), theta_max), v


def _covariance(prob: Problem, tau: float | None, theta: float, coef: list[float], pred: list[float]) -> dict | None:
    """Standard errors of (ln τ, θ, the gains, the constant), by Gauss–Newton at the optimum."""
    idx = [k for k in prob.est if prob.y[k] is not None]
    n = len(idx)
    cols = prob.columns(tau, theta)
    jac = []
    if tau is not None:
        dt = 0.01
        up = prob.columns(tau * math.exp(dt), theta)
        jac.append([sum(c * (a[k] - b[k]) for c, a, b in zip(coef, up, cols, strict=True)) / dt for k in idx])
    dth = max(prob.h * 0.05, 1e-6)
    up = prob.columns(tau, theta + dth)
    jac.append([sum(c * (a[k] - b[k]) for c, a, b in zip(coef, up, cols, strict=True)) / dth for k in idx])
    for col in cols:
        jac.append([col[k] for k in idx])
    p = len(jac)
    if n <= p + 2:
        return None
    res = [prob.ys[k] - pred[k] for k in idx]
    s2 = sum(r * r for r in res) / (n - p)
    rho = acf(res, 1)[0] if n > 4 else 0.0
    rho = min(max(rho, 0.0), 0.95)
    infl = (1 + rho) / (1 - rho)
    scale = [math.sqrt(sum(v * v for v in row)) or 1.0 for row in jac]
    jtj = [[sum(a * b for a, b in zip(jac[i], jac[j], strict=True)) / (scale[i] * scale[j]) for j in range(p)] for i in range(p)]
    inv = _invert(jtj)
    if inv is None:
        return None
    var = [inv[i][i] * s2 * infl / (scale[i] ** 2) for i in range(p)]
    out = {"rho": rho, "effective": n * (1 - rho) / (1 + rho)}
    i = 0
    if tau is not None:
        out["tau"] = tau * math.sqrt(max(var[0], 0.0))
        i = 1
    out["theta"] = math.sqrt(max(var[i], 0.0))
    out["K"] = math.sqrt(max(var[i + 1], 0.0))
    return out


def identify(h: float, t: list[float], u: list, y: list, others: dict[str, list] | None = None,
             est: list[int] | None = None, val: list[int] | None = None, closed_loop: bool = True) -> dict:
    """The process from u to y, on samples every ``h`` seconds at times ``t``. Returns what was
    found and how far it can be trusted (``judge`` says whether it is worth proposing)."""
    n = len(t)
    uu = _ffill(u)
    if uu is None or n < 8:
        return {"found": False, "proposable": False,
                "why": ["the record has no readings of u" if uu is None else "too little record"]}
    oth = {k: f for k, v in (others or {}).items() if (f := _ffill(v)) is not None and max(f) > min(f)}
    if est is None:
        cut = int(n * (1 - HOLD_OUT))
        est, val = list(range(cut)), list(range(cut, n))
    est = [k for k in est if y[k] is not None]
    val = [k for k in (val or []) if y[k] is not None]
    oth = {k: f for k, f in oth.items() if est and max(f[i] for i in est) > min(f[i] for i in est)}   # held still: nothing to fit
    mv = moves(uu, est)
    span = (est[-1] - est[0]) * h if est else 0.0
    out: dict = {"found": False, "h": h, "n_est": len(est), "n_val": len(val), "span": span, "moves": len(mv),
                 "closed_loop": closed_loop, "inputs": sorted(oth), "why": [], "proposable": False}
    if not mv:
        out["why"].append("u did not move in the part of the record fitted: nothing to tell its dynamics from")
        return out
    if len(est) < 8:
        out["why"].append("too little record")
        return out
    prob = Problem(h, uu, y, oth, est, val)
    tau_max = max(span, 4 * h)
    theta_max = max(min(span / 4, 60 * h), h)
    tau, theta, _ = _search(prob, False, tau_max, theta_max)
    _, theta_i, _ = _search(prob, True, tau_max, theta_max)
    fits = {}
    for form, (tt, th) in (("fopdt", (tau, theta)), ("integrating", (None, theta_i))):
        coef, pred, _ = prob.solve(tt, th)
        if coef is None:
            continue
        fits[form] = {"tau": tt, "theta": th, "coef": coef, "pred": pred,
                      "fit_est": fit_share(y, pred, est), "fit_val": fit_share(y, pred, val, level=True) if val else None}
    if not fits:
        out["why"].append("the record does not tell the gains apart (u and the other inputs move together)")
        return out
    form = "fopdt"                       # unless the integrator follows the record held out better (by a point)
    if "fopdt" not in fits or ("integrating" in fits and (fits["integrating"]["fit_val"] or -1e9) > (fits["fopdt"]["fit_val"] or -1e9) + 1):
        form = "integrating"
    f = fits[form]
    coef, pred = f["coef"], f["pred"]
    se = _covariance(prob, f["tau"], f["theta"], coef, pred) or {}
    res_val = [y[k] - pred[k] for k in val] if val else []
    res_all = [y[k] - pred[k] for k in est]
    resid = res_val if len(res_val) >= 16 else res_all
    out.update(found=True, form=form, K=coef[0], tau=f["tau"], theta=f["theta"], offset=coef[-1],
               gains={k: c for k, c in zip(oth, coef[1:-1], strict=True)},
               fit_est=f["fit_est"], fit_val=f["fit_val"], se=se,
               whiteness=whiteness(resid), independence=independence(resid, [uu[k] for k in (val if resid is res_val else est)]),
               steps=[[round(t[k], 3), d] for k, d in mv[:40]], tau_max=tau_max,
               other_form={x: {"fit_val": v["fit_val"], "tau": v["tau"], "theta": v["theta"]} for x, v in fits.items() if x != form},
               pred=pred)
    return judge(out)


def judge(r: dict) -> dict:
    """Whether the record supports proposing the process found, and if not, why."""
    why = r["why"]
    if not r.get("found"):
        r["proposable"] = r["told_apart"] = False
        return r
    K, tau, th = r["K"], r.get("tau"), r["theta"]
    se = r.get("se") or {}
    if r["moves"] < MOVES_MIN and r["closed_loop"]:
        why.append(f"u stepped only {r['moves']} time{'s' if r['moves'] != 1 else ''} in the part fitted (at least {MOVES_MIN})")
    if r["n_est"] < POINTS_MIN:
        why.append(f"{r['n_est']} readings fitted (at least {POINTS_MIN})")
    if tau is not None and r["span"] < SPAN_MIN * (tau + th):
        why.append(f"the part fitted spans less than {SPAN_MIN:g} of τ + θ")
    if r["fit_val"] is None:
        why.append("no record held out to test it on")
    elif r["fit_val"] < FIT_MIN:
        why.append(f"it follows only {max(r['fit_val'], 0):.0f}% of the record held out (at least {FIT_MIN:g}%)")
    if not se:
        why.append("how sure it is cannot be worked out (the record does not tell its numbers apart)")
    else:
        if not K or se.get("K", math.inf) > SE_MAX * abs(K):
            why.append("its gain K is not told apart from 0 by the record")
        if tau is not None and se.get("tau", math.inf) > SE_MAX * tau:
            why.append("its time constant τ is not told apart by the record")
        if se.get("theta", math.inf) > max(SE_MAX * th, r["h"]):
            why.append("its dead time θ is not told apart by the record")
    r["told_apart"] = not any("told apart" in w or "cannot be worked out" in w for w in why)
    if tau is not None and tau >= 0.9 * r["tau_max"]:
        why.append("its time constant is at the longest the record can tell: it acts as an integrator over this record")
    r["proposable"] = not why
    return r


def words(r: dict) -> str:
    """The process as one line: P(s) = 0.0031 e^(−9s)/(21s + 1)."""
    from .. import durations
    if not r.get("found"):
        return "not identified"
    k = f"{r['K']:.3g}"
    th = durations.human(r["theta"]) if r["theta"] >= 1 else f"{r['theta']:.2g}s"
    if r["form"] == "integrating":
        return f"{k} e^(−{th}·s)/s"
    return f"{k} e^(−{th}·s)/({durations.human(r['tau'])}·s + 1)"
