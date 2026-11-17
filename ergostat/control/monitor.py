"""Controller performance monitoring, from the loop's record (Jelali, *Control Performance
Management in Industrial Automation*, 2013; Desborough & Harris 1992; Hägglund 1995; Thornhill,
Huang & Zhang 2003): how well the loop is doing what it is for, read off its scope.

- **Harris index** η = σ²_mv / σ²_e: the variance a minimum-variance controller would leave, given
  the dead time, over the variance the loop has. The error is fitted as an autoregression; the first
  b terms of its impulse response (b the dead time in controller samples, plus one for the hold) are
  what no controller could have removed. 1 is the best any linear controller could do with this dead
  time; near 0, the loop leaves most of what it could remove. Derivable only with a dead time
  (identified, or written in the goal's ``process:``) and enough record.
  It is for a goal held at a level (==): a ceiling or a floor (<=, >=) is not regulated to zero
  error, so it is judged by how often and how far it went past its bound instead (``constraint``).
  The error's mean counts against it (Desborough & Harris's index on the mean squared error).
- **Oscillation**: the zero crossings of the error's autocorrelation, not of the error itself, which
  noise breaks up (Thornhill, Huang & Zhang 2003); a loop oscillates when the intervals between them
  are regular (mean / (3 × spread) past 1) over two periods of the autocorrelation or more, the record
  four periods or more, with an amplitude past the goal's tolerance. Its period and amplitude are said.
- **Saturation**: the share of the time u was at a limit (a setting at its range's end), or of a
  valve's openings at its most.

Left out of all of it (Jelali ch. 2-3): the step tests, deliberate excursions with the loop held, and
the start, the first controller periods after ergostat starts (``loop.windows_left_out``).
- **Settling and overshoot**: for each time the loop went off and came back (a disturbance it
  rejected, or a setpoint it was given), how long until it held again for good (back within the
  tolerance and staying), and for a goal held at a level (==), how far it went past the setpoint
  on the other side, as a share of how far off it had been."""

from __future__ import annotations

import math
import statistics

from ..numbers.estimate import _invert

AR_ORDER = 8
MIN_SAMPLES = 60


def ar_fit(x: list[float], p: int, starts: list[int] | None = None) -> tuple[list[float], float] | None:
    """x_t = Σ a_i x_(t−i) + w_t, by least squares; the coefficients and the variance of w. With
    ``starts`` (where each stretch of the record begins), no row reaches back across a gap."""
    n = len(x)
    if n < 4 * p + 10:
        return None
    cut = sorted(set(starts or [0]))
    first = [0] * n                                   # the start of the stretch each sample is in
    j = 0
    for t in range(n):
        while j + 1 < len(cut) and cut[j + 1] <= t:
            j += 1
        first[t] = cut[j]
    ts = [t for t in range(p, n) if t - p >= first[t]]
    if len(ts) < 3 * p + 10:
        return None
    rows = [[x[t - i] for i in range(1, p + 1)] for t in ts]
    ys = [x[t] for t in ts]
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(p)] for i in range(p)]
    inv = _invert(ata)
    if inv is None:
        return None
    aty = [sum(r[i] * y for r, y in zip(rows, ys, strict=True)) for i in range(p)]
    a = [sum(inv[i][j] * aty[j] for j in range(p)) for i in range(p)]
    res = [y - sum(ai * ri for ai, ri in zip(a, r, strict=True)) for r, y in zip(rows, ys, strict=True)]
    return a, sum(w * w for w in res) / max(1, len(res) - p)


def harris(e: list[float], b: int, p: int = AR_ORDER, starts: list[int] | None = None) -> dict | None:
    """The Harris index of an error series sampled at the controller's period, with dead time b
    samples (b ≥ 1)."""
    if len(e) < MIN_SAMPLES:
        return None
    mean = sum(e) / len(e)
    total = sum(x * x for x in e) / len(e)          # the mean squared error: an offset counts against it
    if total <= 0:
        return None
    got = ar_fit([x - mean for x in e], p, starts)
    if got is None:
        return None
    a, s2 = got
    psi = [1.0]
    for k in range(1, b):
        psi.append(sum(a[i - 1] * psi[k - i] for i in range(1, min(k, len(a)) + 1)))
    mv = s2 * sum(v * v for v in psi)
    return {"index": max(0.0, min(1.0, mv / total)), "mv": mv, "total": total, "b": b, "order": p, "n": len(e),
            "mean_share": mean * mean / total}


def _acf_gappy(e: list, m: int) -> list[float]:
    """The autocorrelation up to m lags of a series with gaps (None), over the pairs both there."""
    got = [x for x in e if x is not None]
    mean = sum(got) / len(got)
    d = [None if x is None else x - mean for x in e]
    var = sum(x * x for x in got) / len(got) - mean * mean
    if var <= 0:
        return [0.0] * m
    out = []
    n = len(d)
    for j in range(1, m + 1):
        s, c = 0.0, 0
        for k in range(n - j):
            a, b = d[k], d[k + j]
            if a is not None and b is not None:
                s += a * b
                c += 1
        out.append(s / c / var if c else 0.0)
    return out


def oscillation(t: list[float], e: list, tolerance: float) -> dict | None:
    """Regular swings of the error: from the zero crossings of its autocorrelation (Thornhill, Huang &
    Zhang 2003), their period, amplitude and how regular. ``t`` is an even grid; gaps are None."""
    got = [x for x in e if x is not None]
    if len(got) < 20 or len(t) < 2:
        return None
    h = t[1] - t[0]
    m = min(len(e) // 2, 600)
    r = _acf_gappy(e, m)
    cross = []
    prev = 1.0                                        # lag 0
    for j, v in enumerate(r, start=1):
        if (prev > 0) != (v > 0) and v != prev:
            cross.append((j - 1) + prev / (prev - v))   # between lag j − 1 and j
        prev = v
    if len(cross) < 5:
        return {"oscillating": False, "crossings": len(cross)}
    gaps = [b - a for a, b in zip(cross, cross[1:], strict=False)]
    mg = statistics.mean(gaps)
    sd = statistics.pstdev(gaps)
    reg = mg / (3 * sd) if sd > 0 else math.inf
    period = 2 * mg * h
    lag = int(round(2 * mg))                          # one period: the autocorrelation's first peak past 0
    near = [r[i - 1] for i in range(max(1, int(lag * 0.75)), min(m, int(lag * 1.25) + 1) + 1)]
    power = max(near, default=0.0)
    mean = sum(got) / len(got)
    var = sum((x - mean) ** 2 for x in got) / len(got)
    amp = math.sqrt(2 * var * max(power, 0.0))
    span = len(e) * h
    osc = reg > 1 and span >= 4 * period and amp > max(tolerance, 1e-12)
    return {"oscillating": osc, "period": period, "regularity": reg, "amplitude": amp, "crossings": len(cross)}


def saturation(u: list, limits: list) -> float | None:
    lo, hi = (limits or [None, None])[:2]
    if lo is None and hi is None:
        return None
    got = [x for x in u if x is not None]
    if not got:
        return None
    at = [x for x in got if (hi is not None and x >= hi - 1e-9) or (lo is not None and x <= lo + 1e-9)]
    return len(at) / len(got)


def at_most(openings: list[float], limits: list) -> float | None:
    """The share of a valve's openings at its most (each run's amount capped there)."""
    hi = (limits or [None, None])[1]
    if hi is None or not openings or min(abs(a) for a in openings) >= hi - 1e-9:
        return None                                   # it always opens by the same amount: its unit, not a limit
    return sum(1 for a in openings if abs(a) >= hi - 1e-9) / len(openings)


def constraint(e: list, op: str, tolerance: float, h: float) -> dict | None:
    """For a ceiling or a floor: how often y was past its bound (and past its tolerance too), and by
    how much, typically and at worst (Jelali ch. 3: a constraint is judged by its violations)."""
    got = [x for x in e if x is not None]
    if not got:
        return None
    past = [(-x if op in ("<=", "<") else x) for x in got]          # e = r − y: past a ceiling is e < 0
    over = [x for x in past if x > 0]
    return {"share": len(over) / len(got), "share_off": sum(1 for x in past if x > tolerance) / len(got),
            "mean": statistics.mean(over) if over else 0.0, "worst": max(over) if over else 0.0,
            "time": len(over) * h}


def excursions(t: list[float], e: list, op: str, tolerance: float, hold_for: float) -> dict:
    """Each time the error left the band and came back to stay (``hold_for`` seconds at least):
    how long it took, its peak, and for a level held (==) how far past the setpoint it went after."""
    band = tolerance if tolerance > 0 else 0.0

    def off(x):
        if op in ("<=", "<"):
            return x < -band              # e = r − y: below 0 means y above a ceiling
        if op in (">=", ">"):
            return x > band
        return abs(x) > band
    out = []
    i, n = 0, len(t)
    while i < n:
        if e[i] is None or not off(e[i]):
            i += 1
            continue
        start, peak = t[i], e[i]
        j = i
        while j < n:                                   # until it is back in, and stays in for hold_for
            if e[j] is not None and off(e[j]):
                if abs(e[j]) > abs(peak):
                    peak = e[j]
                j += 1
                continue
            k = j
            while k < n and (e[k] is None or not off(e[k])) and t[k] - t[j] < hold_for:
                k += 1
            if k >= n or t[k] - t[j] >= hold_for:
                break
            j = k
        if j >= n:
            break
        back = t[j]
        over = None
        if op == "==" and peak:
            after = [x for tk, x in zip(t[j:], e[j:], strict=True) if x is not None and tk - back <= max(hold_for, back - start)]
            opp = [x for x in after if x * peak < 0]
            over = max((abs(x) for x in opp), default=0.0) / abs(peak)
        out.append({"start": start, "settled": back - start, "peak": peak, "overshoot": over})
        i = j + 1
    sett = [x["settled"] for x in out]
    ov = [x["overshoot"] for x in out if x["overshoot"] is not None]
    return {"count": len(out), "settling": statistics.median(sett) if sett else None,
            "slowest": max(sett) if sett else None, "overshoot": statistics.median(ov) if ov else None,
            "list": out[-20:]}


def masked(d: dict, left_out: list[tuple[float, float]] | None) -> list:
    """The error, with what monitoring leaves out set to None."""
    e = list(d["e"])
    for a, b in left_out or []:
        for i, t in enumerate(d["t"]):
            if a <= t <= b:
                e[i] = None
    return e


def performance(d: dict, op: str, tolerance: float, period: float | None, theta: float | None,
                limits: list, how: str, left_out: list[tuple[float, float]] | None = None, delay: float = 0.0) -> dict:
    """What the scope's numbers say of a loop, from its record (``record.read``), less the step tests
    and the starts (``left_out``)."""
    t, h = d["t"], d["h"]
    e = masked(d, left_out)
    every = period or h
    out: dict = {"left_out": sum(1 for x, y in zip(d["e"], e, strict=True) if x is not None and y is None) * h}
    if op not in ("==",):
        out["harris"] = {"why": "a ceiling or a floor is not held at zero error: judged by its violations instead"}
        out["constraint"] = constraint(e, op, tolerance, h)
    elif theta is not None:
        k = max(1, int(round(every / h))) if every else 1
        es, starts, gap = [], [], True
        for x in e[::k]:
            if x is None:
                gap = True
                continue
            if gap:
                starts.append(len(es))
                gap = False
            es.append(x)
        b = int((theta + delay) // every) + 1
        hr = harris(es, b, starts=starts)
        out["harris"] = hr if hr else {"why": f"too little record: {len(es)} samples at the controller's period "
                                              f"(at least {MIN_SAMPLES})", "short": True}
    else:
        out["harris"] = {"why": "needs the loop's dead time: identify its process (or write it in the goal's process:)",
                         "needs_theta": True}
    out["oscillation"] = oscillation(t, e, tolerance)
    out["saturation"] = saturation(d["u"], limits) if how == "setting" else at_most(d.get("openings") or [], limits)
    out["excursions"] = excursions(t, e, op, tolerance, hold_for=max(3 * every, 3 * h))
    got = [x for x in e if x is not None]
    if got:
        out["error"] = {"mean": statistics.mean(got), "rms": math.sqrt(sum(x * x for x in got) / len(got)), "n": len(got)}
    return out
