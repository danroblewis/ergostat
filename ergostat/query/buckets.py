"""The time grid of an answer, and what one bucket's values add up to. Pure arithmetic: every case is worked by hand
in ``tests/test_query_buckets.py``."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Grid:
    """``n`` buckets of ``step`` seconds on multiples of it, so a refresh keeps its buckets; the first and the last are
    cut to the window (``spans``)."""
    since: float
    until: float
    step: float
    start: float
    n: int

    @property
    def times(self) -> list[float]:
        """Each bucket's start (the first: where the window starts)."""
        return [max(self.since, self.start + i * self.step) for i in range(self.n)]

    @property
    def spans(self) -> list[float]:
        """How many seconds of the window each bucket covers."""
        return [min(self.until, self.start + (i + 1) * self.step) - max(self.since, self.start + i * self.step)
                for i in range(self.n)]

    def at(self, t: float) -> int:
        return min(self.n - 1, max(0, int((t - self.start) // self.step)))


def step_of(window: float, points: int, asked: float | None = None) -> float:
    """The bucket width: as asked, else the window over ``points``; whole minutes from a minute up, whole seconds
    below; never so narrow that the window takes more than ``points`` buckets."""
    least = window / points
    width = max(asked or least, least)
    return float(math.ceil(width / 60) * 60) if width >= 60 else float(max(1, math.ceil(width)))


def grid(since: float, until: float, points: int, asked: float | None = None) -> Grid:
    step = step_of(until - since, points, asked)
    start = math.floor(since / step) * step
    n = max(1, math.ceil((until - start) / step))
    while n > points + 1:                         # (aligned to its step, a window can touch one bucket more)
        step = step_of(until - since, points, step + 1)
        start = math.floor(since / step) * step
        n = max(1, math.ceil((until - start) / step))
    return Grid(since, until, step, start, n)


def percentile(values: list[float], p: float) -> float:
    """The ``p`` percentile, interpolated between the two nearest ranks (as spreadsheets and NumPy do by default)."""
    xs = sorted(values)
    at = (len(xs) - 1) * p / 100
    lo = math.floor(at)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (at - lo)


def aggregate(agg: str, values: list[float]) -> float | None:
    """What ``values``, in the order they happened, come to; None for none (a count of none is 0)."""
    if agg == "count":
        return float(len(values))
    if not values:
        return None
    if agg == "sum":
        return float(sum(values))
    if agg == "avg":
        return sum(values) / len(values)
    if agg == "min":
        return min(values)
    if agg == "max":
        return max(values)
    if agg == "last":
        return values[-1]
    return percentile(values, float(agg[1:]))
