"""The arithmetic of the analysis calls ``pair``, ``psd``, ``spectrogram`` and ``ccf`` (SPEC §4e, *Analysis*), on
signals already on one uniform grid, ``None`` where a gap is. It reuses query/frequency.py's FFT, coarsening, detrending
and gap-aware stretches: there is no second FFT here. Each call refuses (``Refused``, the words naming the cause) a
record that is too short, holds a NaN or ±inf, has no stretch long enough between its gaps, or is flat, so a refusal
is never read as zero power, zero correlation or an empty curve. Every count it takes has a hard maximum."""

from __future__ import annotations

import math
import statistics

from . import frequency as fq
from .frequency import Refused

MOST_LAG = 256              # lags each side of zero, in samples: each costs a pass over the record
MOST_CELLS = 5000           # a spectrogram's stretches × frequencies
DETRENDS = ("linear", "mean", "none")
Z = statistics.NormalDist().inv_cdf(0.975)


def checked(signals: dict[str, list]) -> list[tuple[int, int]]:
    """The stretches where every signal holds a value; Refused, naming the cause, when they cannot be analysed."""
    for name, v in signals.items():
        if any(x is not None and not math.isfinite(x) for x in v):
            raise Refused(f"{name} holds a NaN or ±inf, and a value that is not a number is never read as one")
    vs = list(signals.values())
    runs = fq.runs(vs[0], vs[-1])
    if (n := sum(b - a for a, b in runs)) < fq.MIN_SAMPLES:
        raise Refused(f"the record is too short: {' and '.join(signals)} hold a value together at {n} samples, "
                      f"and at least {fq.MIN_SAMPLES} are needed")
    for name, v in signals.items():
        if not fq.varies([v[i] for a, b in runs for i in range(a, b)]):
            raise Refused(f"{name} is flat in this window: it does not vary, so there is nothing to show")
    if (most := max(b - a for a, b in runs)) < fq.MIN_LENGTH:
        raise Refused(f"no stretch is long enough between the gaps: the longest unbroken one is {most} samples, and "
                      f"at least {fq.MIN_LENGTH} are needed")
    return runs


def coarse(v: list, dt: float) -> tuple[list, float]:
    """At most ``frequency.MOST_SAMPLES``: each k samples' mean, empty unless all hold a value (frequency.cells)."""
    k = max(1, math.ceil(len(v) / fq.MOST_SAMPLES))
    return (fq.cells(v, k), dt * k) if k > 1 else (list(v), dt)


def _less(v: list[float], how: str) -> list[float]:
    if how == "linear":
        return fq.detrended(v)
    bar = sum(v) / len(v) if how == "mean" else 0.0
    return [x - bar for x in v]


def _power(v: list, starts: list[int], length: int, how: str, dt: float) -> list[list[float]]:
    """One-sided power density of each stretch (Hann-windowed, so the units are the signal's squared per Hz)."""
    hann = [0.5 - 0.5 * math.cos(2 * math.pi * i / length) for i in range(length)]
    scale, top = 2 * dt / sum(w * w for w in hann), (length + 1) // 2
    size = max(abs(x) for s in starts for x in v[s:s + length])
    rows = []
    for s in starts:
        seg = _less(v[s:s + length], how)
        if not statistics.pstdev(seg) > fq.FLAT * size:
            raise Refused(f"after taking out its {how} trend a stretch is flat (a straight line), so it holds no power")
        z = fq.fft([complex(x * w) for x, w in zip(seg, hann, strict=True)])
        rows.append([abs(z[k]) ** 2 * scale for k in range(top)])
    return rows


def _chi2(p: float, nu: int) -> float:
    """The ``p`` quantile of chi-square with an even ``nu`` (its distribution function in closed form, bisected)."""
    def below(x: float) -> float:
        term = total = 1.0
        for j in range(1, nu // 2):
            term *= x / 2 / j
            total += term
        return 1 - math.exp(-x / 2) * total
    lo, hi = 0.0, nu + 20 * math.sqrt(nu) + 20
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if below(mid) < p else (lo, mid)
    return (lo + hi) / 2


def _points(label: str, unit: str, name: str, xs: list, ys: list, order: str, **more) -> dict:
    return {"shape": "points", "order": order, "x": {"type": "field", "label": label, "unit": unit, "scale": "number"},
            "series": [{"name": name, "xs": xs, "values": ys, "times": more.pop("times", None), "ids": None,
                        **{k: more.pop(k) for k in ("lower", "upper") if k in more}}],
            "unit": "", "capped": 0, "read_log": False, **more}


def _shortest(scrape: float | None, dt: float) -> float:
    return 2 * max(scrape or dt, dt)                # G2: a period under two samples is aliased


def psd(name: str, v: list, dt: float, scrape: float | None, detrend: str = "linear", segments: int = fq.SEGMENTS) -> dict:
    """Welch power against period, with a 95% band for the stretches averaged; no value under 2 × max(scrape, step)."""
    v, dt = coarse(v, dt)
    runs = checked({name: v})
    length = fq.stretch(runs, segments)
    if length is None:
        raise Refused(f"no {segments} stretches of at least {fq.MIN_LENGTH} unbroken samples lie between the gaps")
    starts = fq.windows(runs, length)
    rows = _power(v, starts, length, detrend, dt)
    p = [sum(r[k] for r in rows) / len(rows) for k in range(len(rows[0]))]
    nu = max(2, 2 * round(len(starts) * 9 / 11))   # Hann, half-overlapping: each worth 9/11 of one (frequency.floor)
    lo, hi = nu / _chi2(0.975, nu), nu / _chi2(0.025, nu)
    shortest = _shortest(scrape, dt)
    keep = [k for k in range(len(p) - 1, 0, -1) if length * dt / k >= shortest]
    if not keep:
        raise Refused(f"every period this record holds is under {shortest:g} s, twice its sampling: none is observable")
    return _points("period", "s", "power", [length * dt / k for k in keep], [p[k] for k in keep], "x",
                   lower=[lo * p[k] for k in keep], upper=[hi * p[k] for k in keep], segments=len(starts),
                   segment_samples=length, sample_seconds=dt, dof=nu, not_observable_s=[0, shortest])


def spectrogram(name: str, v: list, dt: float, t0: float, scrape: float | None, length_s: float | None = None,
                detrend: str = "linear", cells: int = MOST_CELLS) -> dict:
    """Power by stretch start × frequency, a table of at most ``cells`` cells (stretches thinned evenly to fit)."""
    v, dt = coarse(v, dt)
    runs = checked({name: v})
    want = max(fq.MIN_LENGTH, min(fq.MOST_LENGTH, len(v) // 8)) if length_s is None else length_s / dt
    if not fq.MIN_LENGTH <= want <= fq.MOST_LENGTH:
        raise Refused(f"length is {want:g} samples of {dt:g} s; a stretch is {fq.MIN_LENGTH} to {fq.MOST_LENGTH} samples "
                      f"({fq.MIN_LENGTH * dt:g} to {fq.MOST_LENGTH * dt:g} s)")
    length = next(n for n in range(int(want), fq.MIN_LENGTH - 1, -1) if fq.smooth(n))
    if not (starts := fq.windows(runs, length)):
        raise Refused(f"no stretch of {length} unbroken samples ({length * dt:g} s) lies between the gaps")
    shortest = _shortest(scrape, dt)
    ks = [k for k in range(1, (length + 1) // 2) if length * dt / k >= shortest]
    if not ks:
        raise Refused(f"every period a stretch of {length * dt:g} s holds is under {shortest:g} s: none is observable")
    if len(ks) > cells:
        raise Refused(f"one stretch holds {len(ks)} frequencies, more than the {cells} cells asked: shorten length")
    every = math.ceil(len(starts) / (cells // len(ks)))     # so ceil(stretches / every) × frequencies <= cells
    starts = starts[::every]
    rows = _power(v, starts, length, detrend, dt)
    out = {"shape": "table", "dims": [{"name": "start", "type": "time"}, {"name": "frequency", "type": "number"}],
           "measures": [{"name": "power", "unit": ""}], "unit": "", "capped": 0, "read_log": False,
           "rows": [[t0 + s * dt, k / (length * dt), r[k]] for s, r in zip(starts, rows, strict=True) for k in ks],
           "segment_samples": length, "sample_seconds": dt, "not_observable_s": [0, shortest]}
    return {**out, "note": f"one stretch in {every} is shown, to stay within {cells} cells"} if every > 1 else out


def ccf(names: list[str], a: list, b: list, dt: float, most_lag_s: float | None = None) -> dict:
    """corr(A at t, B at t + lag) against lag in seconds (a positive lag: B moves after A), with ±1.96/√n, the band
    95% of lags of two independent white signals stay inside; it says nothing for signals that are not white."""
    (a, _), (b, dt) = coarse(a, dt), coarse(b, dt)
    checked(dict(zip(names, (a, b), strict=True)))
    n = len(a)
    m = min(MOST_LAG, n // 4) if most_lag_s is None else most_lag_s / dt
    if not 1 <= m <= MOST_LAG:
        raise Refused(f"most_lag is {m:g} samples of {dt:g} s; it is 1 to {MOST_LAG} samples (up to {MOST_LAG * dt:g} s)")
    (ma, sa), (mb, sb) = [(statistics.fmean(p), statistics.pstdev(p)) for p in ([x for x in s if x is not None]
                                                                               for s in (a, b))]
    lags, rs, band = [], [], []
    for lag in range(-int(m), int(m) + 1):
        got = [(a[i] - ma) * (b[i + lag] - mb) for i in range(max(0, -lag), min(n, n - lag))
               if a[i] is not None and b[i + lag] is not None]
        if len(got) < fq.MIN_SAMPLES:
            raise Refused(f"most_lag is too long for the record: at a lag of {lag * dt:g} s only {len(got)} pairs are "
                          f"left, and at least {fq.MIN_SAMPLES} are needed")
        lags.append(lag * dt)
        rs.append(sum(got) / (len(got) * sa * sb))
        band.append(Z / math.sqrt(len(got)))
    return _points("lag", "s", "correlation", lags, rs, "x", lower=[-x for x in band], upper=band, sample_seconds=dt)


def pair(names: list[str], a: list, b: list, times: list) -> dict:
    """One point per grid time where both hold a value: x from A, y from B, in time order."""
    checked(dict(zip(names, (a, b), strict=True)))
    at = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x is not None and y is not None]
    return _points(names[0], "", names[1], [a[i] for i in at], [b[i] for i in at], "time", times=[times[i] for i in at])
