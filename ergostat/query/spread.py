"""The spread of one category's values, for a box plot: exact quartiles and whiskers over every value, and a bounded
sample of them, so the answer stays small however many items there are."""

from __future__ import annotations

MOST_SAMPLE = 200           # order statistics sent for a density or a percentile whisker's outliers
MOST_OUTLIERS = 30          # outliers sent on each side, the furthest first


def quantile(ordered: list[float], p: float) -> float:
    """Linear interpolation between order statistics (Hyndman and Fan's type 7, numpy's default)."""
    at = (len(ordered) - 1) * p
    lo = int(at)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (at - lo)


def sample(ordered: list[float], most: int = MOST_SAMPLE) -> list[float]:
    """Evenly spaced order statistics, the least and the greatest among them."""
    n = len(ordered)
    if n <= most:
        return list(ordered)
    return [ordered[round(i * (n - 1) / (most - 1))] for i in range(most)]


def box(values: list[float]) -> dict:
    """Quartiles, the percentiles, the extremes, and Tukey's whiskers: the furthest values within 1.5 IQR of the box."""
    xs = sorted(values)
    q1, q3 = quantile(xs, 0.25), quantile(xs, 0.75)
    low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    inside = [v for v in xs if low <= v <= high]
    below = [v for v in xs if v < low]
    above = [v for v in xs if v > high]
    kept = below[:MOST_OUTLIERS] + above[-MOST_OUTLIERS:]
    return {"n": len(xs), "min": xs[0], "max": xs[-1], "p5": quantile(xs, 0.05), "q1": q1, "median": quantile(xs, 0.5), "q3": q3,
            "p95": quantile(xs, 0.95), "lo": inside[0], "hi": inside[-1], "outliers": kept,
            "outliers_more": len(below) + len(above) - len(kept)}
