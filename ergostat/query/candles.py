"""Open, high, low and close of each bucket, from the readings in it: its open the reading with the earliest time, its
close the latest."""

from __future__ import annotations

from .buckets import Grid

READINGS_MOST = 200_000     # readings the store may hand over for one query


class TooMany(Exception):
    """More readings than one query may read."""


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


def of_series(m, series: str, g: Grid) -> dict[int, list]:
    if m.count(series, g.since, g.until) > READINGS_MOST:
        raise TooMany(f"{series} holds more than {READINGS_MOST} readings in this window: ask for a shorter one")
    return from_readings(m.ranges([series], g.since, g.until)[series], g)


def columns(got: dict[int, list], n: int) -> dict[str, list]:
    """One entry per bucket, null for an empty one (its count too)."""
    out: dict[str, list] = {"open": [None] * n, "high": [None] * n, "low": [None] * n, "close": [None] * n, "count": [None] * n}
    for b, (k, _s, lo, hi, _ft, fv, _lt, lv) in got.items():
        out["open"][b], out["high"][b], out["low"][b], out["close"][b], out["count"][b] = fv, hi, lo, lv, k
    return out
