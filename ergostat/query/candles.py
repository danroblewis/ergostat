"""Open, high, low and close of each bucket, from the values in it: its open the value with the earliest time, its
close the latest. An item field's are worked out here from the rows its SQL read; a series' by VictoriaMetrics
(sources.series_candles)."""

from __future__ import annotations

from .buckets import Grid


def from_readings(readings: list[tuple[float, float]], g: Grid) -> dict[int, list]:
    """From readings (time, value) in any order; of equal times, the later in the list is the later."""
    got: dict[int, list] = {}
    for t, v in sorted(readings, key=lambda r: r[0]):
        b = g.at(t)
        a = got.get(b)
        if a is None:
            got[b] = [1, v, v, v, t, v, t, v]
        else:
            a[0], a[1], a[2], a[3], a[6], a[7] = a[0] + 1, a[1] + v, min(a[2], v), max(a[3], v), t, v
    return got


def columns(got: dict[int, list], n: int) -> dict[str, list]:
    """One entry per bucket, null for an empty one (its count too)."""
    out: dict[str, list] = {"open": [None] * n, "high": [None] * n, "low": [None] * n, "close": [None] * n, "count": [None] * n}
    for b, (k, _s, lo, hi, _ft, fv, _lt, lv) in got.items():
        out["open"][b], out["high"][b], out["low"][b], out["close"][b], out["count"][b] = fv, hi, lo, lv, k
    return out
