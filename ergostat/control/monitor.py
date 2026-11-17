"""Controller performance monitoring, from the loop's record (Jelali, *Control Performance
Management in Industrial Automation*, 2013; Desborough & Harris 1992; Hägglund 1995; Thornhill,
Huang & Zhang 2003): how well the loop is doing what it is for, read off its scope.

- **Harris index** η = σ²_mv / σ²_e: the variance a minimum-variance controller would leave, given
  the dead time, over the variance the loop has. The error is fitted as an autoregression; the first
  b terms of its impulse response (b the dead time in controller samples, plus one for the hold) are
  what no controller could have removed. 1 is the best any linear controller could do with this dead
  time; near 0, the loop leaves most of what it could remove. Derivable only with a dead time
  (identified, or written in the goal's ``process:``) and enough record.
- **Oscillation**: the error's zero crossings; a loop oscillates when the periods between them are
  regular (Thornhill's regularity, mean period / (3 × its spread), past 1) over four periods or more,
  with an amplitude past the goal's tolerance. Its period and amplitude are said.
- **Saturation**: the share of the time (or of the valve's openings) u was at a limit.
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


def _resample(t: list[float], xs: list, every: float, h: float) -> list[float]:
    """Every k-th value, k the controller's period in buckets (the loop acts no faster than it)."""
    k = max(1, int(round(every / h))) if every else 1
    held, last = [], None
    for x in xs:                                     # the last reading carried over a bucket with none
        last = x if x is not None else last
        held.append(last)
    return [x for x in held[::k] if x is not None]


def ar_fit(x: list[float], p: int) -> tuple[list[float], float] | None:
    """x_t = Σ a_i x_(t−i) + w_t, by least squares; the coefficients and the variance of w."""
    n = len(x)
    if n < 4 * p + 10:
        return None
    rows = [[x[t - i] for i in range(1, p + 1)] for t in range(p, n)]
    ys = x[p:]
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(p)] for i in range(p)]
    inv = _invert(ata)
    if inv is None:
        return None
    aty = [sum(r[i] * y for r, y in zip(rows, ys, strict=True)) for i in range(p)]
    a = [sum(inv[i][j] * aty[j] for j in range(p)) for i in range(p)]
    res = [y - sum(ai * ri for ai, ri in zip(a, r, strict=True)) for r, y in zip(rows, ys, strict=True)]
    return a, sum(w * w for w in res) / max(1, len(res) - p)


def harris(e: list[float], b: int, p: int = AR_ORDER) -> dict | None:
    """The Harris index of an error series sampled at the controller's period, with dead time b
    samples (b ≥ 1)."""
    if len(e) < MIN_SAMPLES:
        return None
    mean = sum(e) / len(e)
    total = sum(x * x for x in e) / len(e)          # the mean squared error: an offset counts against it
    if total <= 0:
        return None
    got = ar_fit([x - mean for x in e], p)
    if got is None:
        return None
    a, s2 = got
    psi = [1.0]
    for k in range(1, b):
        psi.append(sum(a[i - 1] * psi[k - i] for i in range(1, min(k, len(a)) + 1)))
    mv = s2 * sum(v * v for v in psi)
    return {"index": max(0.0, min(1.0, mv / total)), "mv": mv, "total": total, "b": b, "order": p, "n": len(e)}


def oscillation(t: list[float], e: list, tolerance: float) -> dict | None:
    """Regular swings of the error about its mean: their period and amplitude, and how regular."""
    pts = [(ti, x) for ti, x in zip(t, e, strict=True) if x is not None]
    if len(pts) < 20:
        return None
    mean = sum(x for _, x in pts) / len(pts)
    cross, peaks, last, peak = [], [], None, 0.0
    for ti, x in pts:
        d = x - mean
        s = d > 0
        if last is not None and s != last:
            cross.append(ti)
            peaks.append(peak)
            peak = 0.0
        peak = max(peak, abs(d))
        last = s
    if len(cross) < 9:
        return {"oscillating": False, "crossings": len(cross)}
    periods = [cross[i + 2] - cross[i] for i in range(len(cross) - 2)]
    mp = statistics.mean(periods)
    sd = statistics.pstdev(periods)
    reg = mp / (3 * sd) if sd > 0 else math.inf
    amp = statistics.median(peaks[1:]) if len(peaks) > 1 else 0.0
    osc = reg > 1 and amp > max(tolerance, 1e-12)
    return {"oscillating": osc, "period": mp, "regularity": reg, "amplitude": amp, "crossings": len(cross)}


def saturation(u: list, limits: list) -> float | None:
    lo, hi = (limits or [None, None])[:2]
    if lo is None and hi is None:
        return None
    got = [x for x in u if x is not None]
    if not got:
        return None
    at = [x for x in got if (hi is not None and x >= hi - 1e-9) or (lo is not None and x <= lo + 1e-9)]
    return len(at) / len(got)


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


def performance(d: dict, op: str, tolerance: float, period: float | None, theta: float | None,
                limits: list, how: str) -> dict:
    """What the scope's numbers say of a loop, from its record (``record.read``)."""
    t, e, h = d["t"], d["e"], d["h"]
    every = period or h
    out: dict = {}
    if theta is not None:
        es = _resample(t, e, every, h)
        b = int(theta // every) + 1
        hr = harris(es, b)
        out["harris"] = hr if hr else {"why": f"too little record: {len(es)} samples at the controller's period "
                                              f"(at least {MIN_SAMPLES})"}
    else:
        out["harris"] = {"why": "needs the loop's dead time: identify its process (or write it in the goal's process:)"}
    out["oscillation"] = oscillation(t, e, tolerance)
    out["saturation"] = saturation(d["u"], limits) if how == "setting" else None
    out["excursions"] = excursions(t, e, op, tolerance, hold_for=max(3 * every, 3 * h))
    got = [x for x in e if x is not None]
    if got:
        out["error"] = {"mean": statistics.mean(got), "rms": math.sqrt(sum(x * x for x in got) / len(got)), "n": len(got)}
    return out
