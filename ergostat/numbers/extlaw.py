"""A controller ergostat does not run, identified from its record (SPEC §12d, *Existing controllers*): what it reads
(``xs``) and what it sets (``us``), on one grid of ``dt`` seconds, fitted by each candidate law, each with a pure delay:

- **onoff**: two levels; on once its input is past ``on`` (above it, or below it: ``side``) for ``for`` seconds, off once
  it is back past ``off`` for ``for_off``; at least ``min_on`` on and ``min_off`` off (an alert rule; a relay with
  hysteresis);
- **proportional**: ``u = c + k x``, clamped to ``[lo, hi]`` where the record shows it saturating;
- **pi**: velocity form, ``u += kp Δx + ki dt (x − r)`` while ``|x − r|`` is past the deadband ``db``;
- **stepper**, three-position step (floating) control: up by ``step_up`` while above ``up`` for ``for_up`` and
  ``cool_up`` since its last move, down by ``step_down`` while below ``down`` (the HPA's shape), within ``[lo, hi]``;
- **ratio**, the HPA's own rule, declared (control/laws.py) or fitted (``_fit_ratio``): ``u = ⌈u x / target⌉`` when
  ``x / target`` is outside ``1 ± tolerance``, down to the largest of that over ``stabilize_down``, up to the least over
  ``stabilize_up``, within ``[lo, hi]``.

Each is fitted on the record's first three quarters and judged on the last (Ljung, *System Identification*, ch. 16):
its **skill** one step ahead against holding the last value, and its **R²** run free from the held-out record's start.
The law kept is the one with the least held-out error, n ln(SSE/n), plus k ln n for its k active parameters: a
Schwarz-like parsimony rule, not a likelihood (a switching law's errors are counts of moves mistold, not Gaussian noise),
so a law that only adds parameters never wins on a tie. Durations in seconds; thresholds in the input's units; steps in the output's."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import fmean, median, median_low, pstdev

from .estimate import _invert, solve_linear

FAMILIES = ("onoff", "proportional", "pi", "stepper", "ratio")
SPREAD = ("on", "off", "up", "down")   # thresholds: their uncertainty is the spread of those that mistell as few moves
MIN_POINTS = 40           # points of record, at least
MIN_MOVES = 3             # moves of a switching law's output in the part fitted, at least
MAX_DELAY = 6             # the longest pure delay searched, in samples
HELD_OUT = 0.25
GRID = 40                 # thresholds tried, at the quantiles of the input just before each move


@dataclass
class Law:
    family: str
    p: dict
    dt: float
    delay: float = 0.0
    se: dict = field(default_factory=dict)
    skill: float | None = None
    r2: float | None = None
    score: float = math.inf
    points: int = 0
    sampling: float = 0.0     # seconds of the delay that may be the sensors' (the input read before the output; a grid step)

    @property
    def d(self) -> int:
        return round(self.delay / self.dt)

    def n(self, key: str) -> int:
        return round((self.p.get(key) or 0.0) / self.dt)

    @property
    def k(self) -> int:
        """Its active parameters: each it sets that is not none or 0, and its delay when not 0."""
        return sum(1 for key, v in self.p.items() if key != "side" and v not in (None, 0)) + (self.delay > 0)

    def said(self) -> str:
        from ..durations import human
        p = self.p
        g = lambda k: f"{p[k]:.3g}" + ("" if not self.se.get(k) else f" (spread {self.se[k]:.2g})" if k in SPREAD   # noqa: E731
                                       else f" ± {self.se[k]:.2g}")
        t = lambda k: human(p[k]) if p.get(k) else "0s"   # noqa: E731
        if self.family == "onoff":
            past = "above" if p["side"] > 0 else "below"
            law = (f"on-off between {p['lo']:g} and {p['hi']:g}: on once {past} {g('on')} for {t('for')}, off once back past "
                   f"{g('off')} (hysteresis {p['side'] * (p['on'] - p['off']):.3g}) for {t('for_off')}; at least {t('min_on')} on, "
                   f"{t('min_off')} off")
        elif self.family == "stepper":
            law = "three-position step (floating) control:" + "; ".join(
                f" {w} {p['step_' + w]:g} once {past} {g(w)} for {t('for_' + w)}, {t('cool_' + w)} after its last move"
                for w, past in (("up", "above"), ("down", "below")) if p[w] is not None)
        elif self.family == "ratio":
            law = (f"ratio (the HPA's rule): u ← ⌈u·x / {g('target')}⌉ outside 1 ± {g('tolerance')}, down after "
                   f"{t('stabilize_down')}, up after {t('stabilize_up')}")
        elif self.family == "proportional":
            law = f"proportional: u = {g('c')} + {g('k')} x"
        else:
            law = f"PI (velocity form): kp {g('kp')}, ki {g('ki')}/s about {g('r')}, deadband {g('db')}"
        if self.family != "onoff" and (p.get("lo") is not None or p.get("hi") is not None):
            law += f", within [{_g(p.get('lo'))}, {_g(p.get('hi'))}]"
        fit = ", ".join(x for x in (f"skill {self.skill:.2f}" if self.skill is not None else "",
                                    f"R² {self.r2:.2f}" if self.r2 is not None else "") if x)
        delay = f"; delay {human(self.delay) if self.delay else '0s'}" + (
            f" (up to {human(self.sampling)} of it may be the sensors' sampling)" if self.delay and self.sampling else "")
        if not self.delay and self.family in ("proportional", "pi"):
            delay += (" (with no delay, a controller whose input answers its output within a sample is fitted with its "
                      "gain biased toward 0: Ljung ch. 13)")
        return law + delay + (f" ({fit} on the record held out)" if fit else "")

    def short(self) -> str:
        """The law in a few characters, as a block writes it."""
        p = self.p
        if self.family == "onoff":
            return f"on {'>' if p['side'] > 0 else '<'} {p['on']:.3g}, off {'<' if p['side'] > 0 else '>'} {p['off']:.3g}"
        if self.family == "stepper":
            return ", ".join(f"{s}{p['step_' + w]:g} {c} {p[w]:.3g}" for w, s, c in (("up", "+", ">"), ("down", "−", "<"))
                             if p[w] is not None)
        if self.family == "ratio":
            return f"⌈u x / {p['target']:.3g}⌉"
        if self.family == "proportional":
            return f"K_p = {p['k']:.3g}"
        return f"K_p = {p['kp']:.3g}, K_i = {p['ki']:.3g}"

    def as_dict(self) -> dict:
        return {"family": self.family, "params": self.p, "se": self.se, "delay": self.delay, "dt": self.dt,
                "skill": self.skill, "r2": self.r2, "points": self.points, "said": self.said(), "short": self.short()}


def _g(x) -> str:
    return "…" if x is None else f"{x:g}"


def _clamp(u: float, lo, hi) -> float:
    return max(lo, u) if lo is not None and u < lo else min(hi, u) if hi is not None and u > hi else u


def _rules(law: Law) -> list[tuple[int, float | None, int, int]]:
    """A switching law's two rules: (side, threshold, samples its condition holds, samples since the last move)."""
    p = law.p
    if law.family == "onoff":
        return [(p["side"], p["on"], law.n("for") + 1, law.n("min_off")), (-p["side"], p["off"], law.n("for_off") + 1, law.n("min_on"))]
    return [(1, p.get("up"), law.n("for_up") + 1, law.n("cool_up")), (-1, p.get("down"), law.n("for_down") + 1, law.n("cool_down"))]


def start(law: Law, u: float, x: float) -> dict:
    return {"u": u, "since": 10 ** 6, "runs": [0, 0], "x": x, "rules": _rules(law) if law.family in ("onoff", "stepper") else [],
            "wants": []}


def _ratio(law: Law, st: dict, x: float) -> float:
    """The HPA's rule: desired ⌈u x / target⌉ when x / target is outside 1 ± tolerance; the samples' desired kept over
    each window (those within it, now's included), a scale-up to the least over ``stabilize_up``, a scale-down to the
    largest over ``stabilize_down``; within [lo, hi]."""
    p, u = law.p, st["u"]
    r = x / p["target"]
    want = math.ceil(u * r - 1e-9) if abs(r - 1) > p["tolerance"] else u
    wants = st["wants"]
    wants.append(want)
    n_up, n_dn = max(1, law.n("stabilize_up")), max(1, law.n("stabilize_down"))
    del wants[:-max(n_up, n_dn)]
    up, down = min(wants[-n_up:]), max(wants[-n_dn:])
    new = up if u < up else u
    return _clamp(down if new > down else new, p.get("lo"), p.get("hi"))


def step(law: Law, st: dict, x: float) -> float:
    """One sample of the law: ``x`` its input, already delayed; ``st`` its state (``start``), changed in place."""
    p, f = law.p, law.family
    st["since"] += 1
    if f in ("onoff", "stepper"):
        for i, (side, thr, _, _) in enumerate(st["rules"]):
            st["runs"][i] = st["runs"][i] + 1 if thr is not None and side * (x - thr) > 0 else 0
        u = st["u"]
        if f == "onoff":
            i = 1 if u > (p["lo"] + p["hi"]) / 2 else 0
            _, _, nf, nc = st["rules"][i]
            if st["runs"][i] >= nf and st["since"] >= nc:
                st["u"], st["since"] = (p["lo"] if i else p["hi"]), 0
        else:
            for i, sign, key in ((0, 1, "hi"), (1, -1, "lo")):
                _, thr, nf, nc = st["rules"][i]
                room = p.get(key) is None or sign * (p[key] - u) > 1e-9
                if thr is not None and room and st["runs"][i] >= nf and st["since"] >= nc:
                    st["u"], st["since"] = _clamp(u + sign * p["step_up" if i == 0 else "step_down"], p.get("lo"), p.get("hi")), 0
                    break
    elif f == "ratio":
        st["u"] = _ratio(law, st, x)
    elif f == "proportional":
        st["u"] = _clamp(p["c"] + p["k"] * x, p.get("lo"), p.get("hi"))
    else:
        e = x - p["r"]
        if abs(e) > p["db"]:
            st["u"] = _clamp(st["u"] + p["kp"] * (x - st["x"]) + p["ki"] * law.dt * e, p.get("lo"), p.get("hi"))
    st["x"] = x
    return st["u"]


def since_moves(us: list[float], tol: float) -> list[int]:
    out = [10 ** 6]
    for k in range(1, len(us)):
        out.append(0 if abs(us[k] - us[k - 1]) > tol else out[-1] + 1)
    return out


def run(law: Law, xs: list[float], us: list[float], free_from: int | None = None) -> list[float]:
    """What the law puts out at each sample: one step ahead from the record's state before ``free_from``, free after."""
    ms, d = since_moves(us, tol(us)), law.d
    st, out = start(law, us[0], xs[0]), [us[0]]
    for k in range(1, len(xs)):
        if free_from is None or k < free_from:
            st["u"], st["since"] = us[k - 1], ms[k - 1]
        out.append(step(law, st, xs[max(0, k - d)]))
    return out


def tol(us: list[float]) -> float:
    return 1e-3 * ((max(us) - min(us)) or 1.0)


def _runs(xs: list[float], side: int, thr: float) -> list[int]:
    out, r = [], 0
    for x in xs:
        r = r + 1 if side * (x - thr) > 0 else 0
        out.append(r)
    return out


def _rule(xs, ev, ok, since, side) -> dict | None:
    """The threshold, the samples its condition must hold and the samples since the last move that best tell when the
    record moved (``ev``) where it could (``ok``): for each threshold and delay, the largest of each consistent with
    every move (or none at all, when that misses no more), by the fewest moves mistold."""
    idx = [k for k in range(1, len(xs)) if ok[k]]
    evk = [k for k in idx if ev[k]]
    if len(evk) < MIN_MOVES:
        return None
    qs = sorted(xs[k - j] for k in evk for j in range(MAX_DELAY + 16) if k >= j)   # where a move's threshold can be
    grid = sorted({(qs[int(i * (len(qs) - 1) / GRID)] + qs[int((i + 1) * (len(qs) - 1) / GRID)]) / 2 for i in range(GRID)})
    tried = []
    for thr in grid:
        r = _runs(xs, side, thr)
        for d in range(MAX_DELAY + 1):
            rd = [r[max(0, k - d)] for k in range(len(xs))]
            best = None
            for nf in {1, max(1, min(rd[k] for k in evk))}:
                for nc in {0, min(since[k] for k in evk)}:
                    miss = sum(1 for k in idx if (rd[k] >= nf and since[k] >= nc) != ev[k])
                    cost = miss + 2 * (nc > 0)              # a wait only where it tells more than two moves
                    if best is None or (cost, nf + nc) < best[:2]:
                        best = (cost, nf + nc, nf, nc, miss)
            tried.append((best[0], d, thr, best[2], best[3]))
    least = min(t[0] for t in tried)
    d = min(t[1] for t in tried if t[0] == least)
    ties = sorted((t for t in tried if t[0] == least and t[1] == d), key=lambda t: t[2])
    mid = ties[len(ties) // 2]
    step_ = (qs[-1] - qs[0]) / GRID
    se = max((ties[-1][2] - ties[0][2]) / math.sqrt(12), step_ / math.sqrt(12))
    return {"thr": mid[2], "se": se, "d": d, "nf": mid[3], "nc": mid[4], "miss": least, "moves": len(evk)}


def _fit_switching(family: str, xs, us, dt) -> Law | None:
    eps = tol(us)
    lo, hi = min(us), max(us)
    dus = [0.0] + [us[k] - us[k - 1] for k in range(1, len(us))]
    moves = [k for k, x in enumerate(dus) if abs(x) > eps]
    if len(moves) < MIN_MOVES or len(moves) > 0.25 * len(us):
        return None                                            # not a switching law's record: it hardly moves, or always
    since = [s + 1 for s in [10 ** 6] + since_moves(us, eps)[:-1]]
    if family == "onoff":
        if any(min(abs(u - lo), abs(u - hi)) > eps for u in us):
            return None
        on = [u > (lo + hi) / 2 for u in us]
        best = None
        was = on[:1] + on[:-1]
        for side in (1, -1):
            r_on = _rule(xs, [a and not w for a, w in zip(on, was, strict=True)], [not w for w in was], since, side)
            r_off = _rule(xs, [w and not a for a, w in zip(on, was, strict=True)], was, since, -side)
            ok = r_on and r_off and side * (r_on["thr"] - r_off["thr"]) >= 0      # never a negative hysteresis
            if ok and (best is None or r_on["miss"] + r_off["miss"] < best[0]):
                best = (r_on["miss"] + r_off["miss"], side, r_on, r_off)
        if best is None:
            return None
        _, side, a, b = best
        d = min(a["d"], b["d"])
        return Law("onoff", {"side": side, "on": a["thr"], "off": b["thr"], "for": (a["nf"] - 1 + a["d"] - d) * dt,
                             "for_off": (b["nf"] - 1 + b["d"] - d) * dt, "min_off": a["nc"] * dt, "min_on": b["nc"] * dt,
                             "lo": lo, "hi": hi}, dt, d * dt, {"on": a["se"], "off": b["se"]})
    bound = {k: v if sum(1 for u in us if abs(u - v) <= eps) >= max(3, 0.05 * len(us)) else None for k, v in (("lo", lo), ("hi", hi))}
    ups, downs = [dus[k] for k in moves if dus[k] > 0], [-dus[k] for k in moves if dus[k] < 0]
    rs = []
    for side, ev, room in ((1, [x > eps for x in dus], lambda u: bound["hi"] is None or u < hi - eps),
                           (-1, [x < -eps for x in dus], lambda u: bound["lo"] is None or u > lo + eps)):
        rs.append(_rule(xs, ev, [k > 0 and room(us[k - 1]) for k in range(len(us))], since, side))
    for key, side, r in (("hi", 1, rs[0]), ("lo", -1, rs[1])):   # a bound only where its rule held and it did not move
        rd = _runs(xs, side, r["thr"]) if r and bound[key] is not None else []
        held = sum(1 for k in range(1, len(us)) if rd and abs(us[k - 1] - bound[key]) <= eps and abs(dus[k]) <= eps
                   and rd[max(0, k - r["d"])] >= r["nf"] and since[k] >= r["nc"])
        bound[key] = bound[key] if held >= MIN_MOVES else None
    up, down = rs
    if up is None and down is None or up and down and up["thr"] < down["thr"]:
        return None                                            # nothing epsd, or up below down: no such controller
    d = min(r["d"] for r in rs if r)
    p, se = {"lo": bound["lo"], "hi": bound["hi"]}, {}
    for key, r, sizes in (("up", up, ups), ("down", down, downs)):
        p[key], p[f"step_{key}"] = (r["thr"] if r else None), (median(sizes) if sizes else 0.0)
        p[f"for_{key}"] = (r["nf"] - 1 + r["d"] - d) * dt if r else 0.0
        p[f"cool_{key}"] = r["nc"] * dt if r else 0.0
        if r:
            se[key] = r["se"]
            se[f"step_{key}"] = pstdev(sizes) / math.sqrt(len(sizes))
    return Law("stepper", p, dt, d * dt, se)


def _ceiling(t0: float, moves: list[tuple[float, float]]) -> float:
    """The target nearest the least-squares ``t0`` that the most moves up agree with: ⌈u x / t⌉ = u' holds for t in
    [u x / u', u x / (u' − 1)), so the middle of the span the most such intervals share."""
    ev = sorted([(ux / v, 1) for ux, v in moves] + [(ux / (v - 1), -1) for ux, v in moves if v > 1], key=lambda e: (e[0], e[1]))
    spans, n = [], 0
    for (t, s), nxt in zip(ev, ev[1:] + [(math.inf, 0)], strict=True):
        n += s
        spans.append((-n, abs((t + nxt[0]) / 2 - t0) if nxt[0] < math.inf else math.inf, t, nxt[0]))
    best = min(spans, default=None)
    return t0 if best is None or best[0] >= 0 or best[3] == math.inf else (best[2] + best[3]) / 2


def _fit_ratio(xs, us, dt) -> Law | None:
    """The HPA's rule, for each delay: the target by least squares on the moves up, log((u' − ½)/u) = log x − log target
    (the ½ for the ceiling, then moved to the nearest the most moves agree with: ``_ceiling``; a move up is the rule's
    own, a move down waits on its window); the tolerance the largest x/target − 1 that moved nothing, below the least
    that moved it up (the side a scale-down's window does not hide); stabilize-down the median run of a lower desired
    that ended in a move down (each is the window, but one sample misjudged at the tolerance's edge breaks a run, and the
    shortest follows that sample); a bound where the record sat on its extreme while its rule wanted past it, at least
    MIN_MOVES times; stabilize-up 0s. The delay is the one of least one-step error. None on a record not of whole
    numbers from 1 or with fewer than MIN_MOVES moves up."""
    eps, top, bottom = tol(us), max(us), min(us)
    if bottom < 1 or any(u != round(u) for u in us):
        return None
    best = None
    for d in range(MAX_DELAY + 1):
        xd = [xs[max(0, k - d)] for k in range(len(xs))]
        up = [k for k in range(1, len(us)) if us[k] > us[k - 1] + eps and xd[k] > 0]
        if len(up) < MIN_MOVES:
            continue
        inner = [k for k in up if us[k] < top - eps]
        on = inner if len(inner) >= MIN_MOVES else up
        logs = [math.log(xd[k]) - math.log((us[k] - 0.5) / us[k - 1]) for k in on]
        target = _ceiling(math.exp(fmean(logs)), [(us[k - 1] * xd[k], us[k]) for k in inner])
        r = [x / target for x in xd]
        least = min((r[k] for k in inner), default=math.inf)
        still = [k for k in range(1, len(us)) if abs(us[k] - us[k - 1]) <= eps]
        tolerance = max((r[k] - 1 for k in still if 1 < r[k] < least and us[k - 1] < top - eps), default=0.0)
        want = [us[0]] + [math.ceil(us[k - 1] * r[k] - 1e-9) if abs(r[k] - 1) > tolerance else us[k - 1] for k in range(1, len(us))]
        lower = []                                     # at each sample, how long the desired has been below the record's u
        for k in range(len(us)):                       # counted back afresh only where the record's u moved
            ref = us[k - 1 if k else 0]
            lower.append(lower[-1] + 1 if k > 1 and ref == us[k - 2] and want[k] < ref else
                         next((j for j in range(k + 1) if want[k - j] >= ref), k + 1))
        downs = [lower[k] for k in range(1, len(us)) if us[k] < us[k - 1] - eps]
        n_dn = median_low(downs) if downs else 0
        hi = top if sum(1 for k in still if us[k - 1] >= top - eps and want[k] > top) >= MIN_MOVES else None
        lo = bottom if sum(1 for k in still if us[k - 1] <= bottom + eps and lower[k] > n_dn) >= MIN_MOVES else None
        se = {"target": target * pstdev(logs) / math.sqrt(len(logs)),
              "tolerance": (min(least - 1, 1.0) - tolerance) / math.sqrt(12) if least < math.inf else 0.0}
        law = Law("ratio", {"target": target, "tolerance": tolerance, "stabilize_down": n_dn * dt, "stabilize_up": 0.0,
                            "lo": lo, "hi": hi}, dt, d * dt, se)
        sse = sum((a - b) ** 2 for a, b in zip(run(law, xs, us), us, strict=True))
        if best is None or sse < best[0] - 1e-12:
            best = (sse, law)
    return best[1] if best else None


def _ols(rows, ys, names) -> tuple[dict, dict, float] | None:
    b = solve_linear(rows, ys) if len(rows) > len(names) else None
    if b is None:
        return None
    sse = sum((y - sum(c * x for c, x in zip(b, r, strict=True))) ** 2 for r, y in zip(rows, ys, strict=True))
    inv = _invert([[sum(r[i] * r[j] for r in rows) for j in range(len(names))] for i in range(len(names))]) or []
    s2 = sse / (len(rows) - len(names))
    se = {n: math.sqrt(max(0.0, s2 * inv[i][i])) for i, n in enumerate(names)} if inv else {}
    return dict(zip(names, b, strict=True)), se, sse


def _bounds(us) -> tuple:
    eps = 5 * tol(us)
    return tuple(v if sum(1 for u in us if abs(u - v) <= eps) >= max(3, 0.05 * len(us)) else None for v in (min(us), max(us)))


def _pi(xd, us, free, db: float, r0: float | None, dt: float) -> tuple[dict, dict] | None:
    """PI in velocity form by least squares on the moves outside the deadband about ``r0``: Δu = kp Δx + a x + b."""
    rows = [k for k in free if r0 is None or abs(xd[k] - r0) > db]
    got = _ols([[xd[k] - xd[k - 1], xd[k], 1.0] for k in rows], [us[k] - us[k - 1] for k in rows], ["kp", "a", "b"])
    if got is None or abs(got[0]["a"]) < 1e-12:
        return None
    c, se, _ = got
    return ({"kp": c["kp"], "ki": c["a"] / dt, "r": -c["b"] / c["a"], "db": db},
            {"kp": se.get("kp", 0.0), "ki": se.get("a", 0.0) / dt,
             "r": math.hypot(se.get("b", 0.0) / c["a"], c["b"] * se.get("a", 0.0) / c["a"] ** 2)})


def _fit_linear(family: str, xs, us, dt) -> Law | None:
    lo, hi = _bounds(us)
    eps = 5 * tol(us)
    free = [k for k in range(1, len(us)) if not any(b is not None and abs(us[j] - b) <= eps for b in (lo, hi) for j in (k, k - 1))]
    best = None
    for d in range(MAX_DELAY + 1):
        xd = [xs[max(0, k - d)] for k in range(len(xs))]
        if family == "proportional":
            got = _ols([[1.0, xd[k]] for k in free], [us[k] for k in free], ["c", "k"])
            cands = [got[:2]] if got else []
        else:
            cands = [base] if (base := _pi(xd, us, free, 0.0, None, dt)) else []
            if base:                                         # the deadband: a share of the errors about the first fit's r
                es = sorted(abs(xd[k] - base[0]["r"]) for k in free)
                cands += [c for q in (0.05, 0.1, 0.2, 0.3) if (c := _pi(xd, us, free, es[int(q * len(es))], base[0]["r"], dt))]
                still = [k for k in free if abs(us[k] - us[k - 1]) <= 1e-9 * tol(us)]   # held exactly: inside the band
                c = base
                for _ in range(3) if len(still) >= 5 else ():        # the band and its centre, each from the other
                    c = _pi(xd, us, free, max(abs(xd[k] - c[0]["r"]) for k in still), c[0]["r"], dt) or c
                cands += [c]
        for p, s in cands:
            law = Law(family, {**p, "lo": lo, "hi": hi}, dt, d * dt, s)
            pred = run(law, xs, us)
            sse = sum((pred[k] - us[k]) ** 2 for k in range(1, len(us)))
            if best is None or sse < best[0] - 1e-12:
                best = (sse, law)
    return best[1] if best else None


def fit(xs: list[float], us: list[float], dt: float) -> tuple[Law | None, list[Law], str]:
    """The law chosen (None, with why), and every law fitted, best first."""
    n = len(xs)
    if n < MIN_POINTS:
        return None, [], f"{n} points of record on a {dt:g}s grid (at least {MIN_POINTS})"
    if max(us) - min(us) <= 0:
        return None, [], "its output never moved in the record"
    nf = int(n * (1 - HELD_OUT))
    laws = []
    for fam in FAMILIES:
        law = (_fit_ratio(xs[:nf], us[:nf], dt) if fam == "ratio" else
               (_fit_switching if fam in ("onoff", "stepper") else _fit_linear)(fam, xs[:nf], us[:nf], dt))
        if law is not None:
            judge(law, xs, us, nf)
            laws.append(law)
    laws.sort(key=lambda w: w.score)
    if not laws:
        return None, [], f"no law fits its record ({nf} points fitted, too few moves of its output to tell)"
    return laws[0], laws, ""


def judge(law: Law, xs, us, nf: int) -> None:
    """Its skill and R² on the record held out, and its score: the held-out error, penalised per parameter."""
    one, free = run(law, xs, us), run(law, xs, us, nf)
    h = range(nf, len(us))
    sse = sum((one[k] - us[k]) ** 2 for k in h)
    pers = sum((us[k] - us[k - 1]) ** 2 for k in h)
    law.skill = 1 - sse / pers if pers > 0 else None
    m = fmean(us[k] for k in h)
    sst = sum((us[k] - m) ** 2 for k in h)
    law.r2 = 1 - sum((free[k] - us[k]) ** 2 for k in h) / sst if sst > 0 else None
    nh = len(h)
    law.score = nh * math.log(max(sse / nh, tol(us) ** 2)) + law.k * math.log(nh)
    law.points = len(us)


def settle(law: Law, xs: list[float], us: list[float]) -> dict:
    """Its state where the record ends: run one step ahead over it, its output and its last move as measured."""
    st, ms = start(law, us[0], xs[0]), since_moves(us, tol(us))
    for k in range(1, len(xs)):
        st["u"], st["since"] = us[k - 1], ms[k - 1]
        step(law, st, xs[max(0, k - law.d)])
    st["u"], st["since"] = us[-1], ms[-1]
    return st
