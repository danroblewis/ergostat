"""A frequency response estimated from two measured signals, by Welch's method (Welch 1967; Bendat & Piersol, *Random
Data*, ch. 9): the record resampled to a uniform grid, cut into half-overlapping stretches that cross no gap, each
detrended and Hann-windowed; H = Pxy / Pxx (the H1 estimate, for noise on the output) and the coherence
|Pxy|^2 / (Pxx Pyy). Pure arithmetic in the standard library. Frequencies the input holds no power at are left out:
nothing can be said about them.

Whether the record supports a response at all is decided here, not on the page. Unrelated signals pass a per-frequency
floor at one frequency in twenty, so among hundreds of frequencies they nearly always pass it somewhere. The floor is
therefore corrected for the number of frequencies looked at (Bonferroni). A record where no frequency reaches the
corrected floor is answered with ``supported: false``, the reason in words, and no curve."""

from __future__ import annotations

import cmath
import math
import statistics

MIN_SAMPLES = 32            # paired samples, at least, for an estimate
MIN_LENGTH = 16             # samples in one stretch
MOST_SAMPLES = 2048         # the uniform grid is coarsened to at most this many
MOST_LENGTH = 1024          # samples in one stretch: at most 511 frequencies
MOST_SEGMENTS = 64
SEGMENTS = 4
GAP_SAMPLES = 3             # readings further apart than this many typical spacings are a gap, never interpolated
NO_POWER = 1e-9             # of the input's strongest frequency: below this it was not excited there
FLAT = 1e-9                 # a spread below this share of the signal's size is no variation
ALPHA = 0.05                # the coherence floor: what unrelated signals stay below 95% of the time


class Refused(Exception):
    """The record cannot support an estimate: the words say why."""


def _smooth(n: int) -> bool:
    for f in (2, 3, 5):
        while n % f == 0:
            n //= f
    return n == 1


def fft(a: list[complex]) -> list[complex]:
    """The discrete Fourier transform of a length with no prime factor past 5 (decimation in time)."""
    n = len(a)
    if n == 1:
        return list(a)
    f = next(x for x in (2, 3, 5) if n % x == 0)
    parts = [fft(a[i::f]) for i in range(f)]
    m = n // f
    base = -2j * math.pi / n
    out = [0j] * n
    for k in range(n):
        out[k] = sum(parts[r][k % m] * cmath.exp(base * r * k) for r in range(1, f)) + parts[0][k % m]
    return out


def _median_gap(present: list[int]) -> float:
    return statistics.median(b - a for a, b in zip(present, present[1:], strict=False))


def _filled(values: list, reach: float) -> list:
    """Straight lines between readings no further apart than ``reach`` buckets; a longer gap stays empty."""
    out = list(values)
    at = [i for i, v in enumerate(values) if v is not None]
    for a, b in zip(at, at[1:], strict=False):
        if 1 < b - a <= reach:
            for i in range(a + 1, b):
                out[i] = values[a] + (values[b] - values[a]) * (i - a) / (b - a)
    return out


def _cells(values: list, k: int) -> list:
    """Each ``k`` buckets' mean; empty unless all of them hold a value (the same averaging for both signals)."""
    out = []
    for i in range(0, len(values) - k + 1, k):
        cell = values[i:i + k]
        out.append(None if any(v is None for v in cell) else sum(cell) / k)
    return out


def resample(xs: list, ys: list, step: float) -> tuple[list, list, float]:
    """Two signals on one bucket grid (``None`` where empty), on a uniform grid as coarse as the slower one's readings."""
    px, py = [[i for i, v in enumerate(s) if v is not None] for s in (xs, ys)]
    if len(px) < MIN_SAMPLES or len(py) < MIN_SAMPLES:
        raise Refused(f"too few samples: the input has {len(px)} and the output {len(py)} in this window, "
                      f"and an estimate needs at least {MIN_SAMPLES} of each")
    gx, gy = _median_gap(px), _median_gap(py)
    k = max(1, math.ceil(max(gx, gy)), math.ceil(len(xs) / MOST_SAMPLES))
    return _cells(_filled(xs, GAP_SAMPLES * gx), k), _cells(_filled(ys, GAP_SAMPLES * gy), k), step * k


def _runs(xs: list, ys: list) -> list[tuple[int, int]]:
    """The stretches ``[a, b)`` where both signals hold a value."""
    out, start = [], None
    for i, (x, y) in enumerate(zip(xs, ys, strict=True)):
        if x is None or y is None:
            if start is not None:
                out.append((start, i))
            start = None
        elif start is None:
            start = i
    if start is not None:
        out.append((start, len(xs)))
    return out


def _windows(runs: list[tuple[int, int]], length: int) -> list[int]:
    hop = max(1, length // 2)
    return [s for a, b in runs if b - a >= length for s in range(a, b - length + 1, hop)]


def _length(runs: list[tuple[int, int]], segments: int) -> int | None:
    """The longest stretch length of few prime factors that still gives ``segments`` windows."""
    top = min(MOST_LENGTH, max(b - a for a, b in runs))
    for n in range(top, MIN_LENGTH - 1, -1):
        if _smooth(n) and len(_windows(runs, n)) >= segments:
            return n
    return None


def _detrended(v: list[float]) -> list[float]:
    """Less its least-squares straight line."""
    n = len(v)
    mid = (n - 1) / 2
    bar = sum(v) / n
    slope = sum((i - mid) * (x - bar) for i, x in enumerate(v)) / (n * (n * n - 1) / 12)
    return [x - bar - slope * (i - mid) for i, x in enumerate(v)]


def _varies(v: list[float]) -> bool:
    size = max(abs(x) for x in v)
    return size > 0 and statistics.pstdev(v) > FLAT * size


# what the analysis calls reuse (query/spectra.py), unchanged, under public names
runs, windows, stretch, cells, detrended, varies, smooth = _runs, _windows, _length, _cells, _detrended, _varies, _smooth


def floor(windows: int) -> float:
    """The coherence unrelated signals stay under 95% of the time, for Hann windows overlapping by half: each window
    is worth 9/11 of an independent one (Welch 1967)."""
    effective = max(1.0 + 1e-9, windows * 9 / 11)
    return 1 - ALPHA ** (1 / (effective - 1)) if effective > 1.5 else 1.0


def family_floor(windows: int, frequencies: int) -> float:
    """The coherence unrelated signals stay under at all ``frequencies`` frequencies at once, 95% of the time: the
    per-frequency floor at ALPHA / frequencies (Bonferroni; neighbouring frequencies are not independent, so it errs
    toward refusing)."""
    effective = max(1.0 + 1e-9, windows * 9 / 11)
    share = ALPHA / max(1, frequencies)
    return 1 - share ** (1 / (effective - 1)) if effective > 1.5 else 1.0


def _unsupported(out: dict, coherence: list[float]) -> dict:
    """The record answered with why it supports no response, and no curve to draw as if it were one."""
    best = max(range(len(coherence)), key=coherence.__getitem__)
    why = (f"no frequency is coherent past chance: the highest coherence is {coherence[best]:.2f}, at "
           f"{out['frequency']['hz'][best]:.3g} Hz, and unrelated signals reach {out['coherence_floor']:.2f} somewhere "
           f"among these {len(coherence)} frequencies one record in twenty ({out['segments']} averages of "
           f"{out['segment_samples']} samples); the input may not move the output, or was not varied enough to show how")
    return {**out, "supported": False, "refused": why, "coherence_peak": coherence[best],
            "frequency": {k: [] for k in out["frequency"]}}


def _unwrapped(phases: list[float], coherent: list[bool]) -> list[float]:
    """Degrees, continuous; only a frequency that is coherent moves the reference, so noise cannot add a false turn."""
    out, ref = [], None
    for ph, good in zip(phases, coherent, strict=True):
        if ref is not None:
            ph -= 360 * round((ph - ref) / 360)
        if good or ref is None:
            ref = ph
        out.append(ph)
    return out


def estimate(xs: list, ys: list, dt: float, segments: int = SEGMENTS) -> dict:
    """The response of output ``ys`` to input ``xs`` sampled every ``dt`` seconds (``None`` for a gap)."""
    runs = _runs(xs, ys)
    samples = sum(b - a for a, b in runs)
    if samples < MIN_SAMPLES:
        raise Refused(f"too few samples: the input and output overlap at {samples} points, and an estimate needs {MIN_SAMPLES}")
    paired_x = [xs[i] for a, b in runs for i in range(a, b)]
    paired_y = [ys[i] for a, b in runs for i in range(a, b)]
    if not _varies(paired_x):
        raise Refused("the input does not vary in this window, so it says nothing about how the output responds")
    if not _varies(paired_y):
        raise Refused("the output does not vary in this window, so there is no response to estimate")
    length = _length(runs, segments)
    if length is None:
        raise Refused(f"too few samples: the gaps leave no {segments} stretches of at least {MIN_LENGTH} unbroken samples")
    starts = _windows(runs, length)
    hann = [0.5 - 0.5 * math.cos(2 * math.pi * i / length) for i in range(length)]
    top = (length + 1) // 2                       # below Nyquist: a real signal's phase is not defined there
    pxx, pyy = [0.0] * top, [0.0] * top
    pxy = [0j] * top
    for s in starts:
        a = _detrended([float(v) for v in xs[s:s + length]])
        b = _detrended([float(v) for v in ys[s:s + length]])
        z = fft([complex(p * w, q * w) for p, q, w in zip(a, b, hann, strict=True)])  # two real signals in one transform
        for k in range(1, top):
            zk, zr = z[k], z[length - k].conjugate()
            fx, fy = (zk + zr) / 2, (zk - zr) / 2j
            pxx[k] += abs(fx) ** 2
            pyy[k] += abs(fy) ** 2
            pxy[k] += fx.conjugate() * fy
    least = NO_POWER * max(pxx)
    keep = [k for k in range(1, top) if pxx[k] > least and pxy[k] != 0]
    if not keep:
        raise Refused("the input and output share no frequency with any power")
    gain = [pxy[k] / pxx[k] for k in keep]
    coherence = [min(1.0, abs(pxy[k]) ** 2 / (pxx[k] * pyy[k])) if pyy[k] > 0 else 0.0 for k in keep]
    each = floor(len(starts))
    bar = family_floor(len(starts), len(keep))
    left = top - 1 - len(keep)
    out = {"frequency": {"hz": [k / (length * dt) for k in keep],
                         "magnitude_db": [20 * math.log10(abs(h)) for h in gain],
                         "phase_deg": _unwrapped([math.degrees(cmath.phase(h)) for h in gain], [c >= bar for c in coherence]),
                         "re": [h.real for h in gain], "im": [h.imag for h in gain], "coherence": coherence},
           "samples": samples, "segments": len(starts), "segment_samples": length, "sample_seconds": dt,
           "coherence_floor": bar, "coherence_floor_each": each, "supported": True}
    if left:
        out["note"] = f"{left} of {top - 1} frequencies are left out: the input holds no power at them"
    if not max(coherence) >= bar:                  # a NaN coherence is no evidence either
        return _unsupported(out, coherence)
    return out
