"""Open, high, low and close of each bucket. A bucket may be built from raw readings and from several roll-up rows of
several tiers: its open is the reading with the earliest time among them, its close the latest."""

from __future__ import annotations

from .buckets import Grid

READINGS_MOST = 200_000     # raw readings a store without roll-ups may hand over for one query


class TooMany(Exception):
    """More readings than one query may read."""


RAW = """select b, n, s, lo, hi, ft, fv, lt, lv from (
  select b, count(*) over w n, sum(value) over w s, min(value) over w lo, max(value) over w hi,
         first_value(time) over w ft, first_value(value) over w fv, last_value(time) over w lt, last_value(value) over w lv,
         row_number() over (partition by b order by time, id) r
  from (select max(min(cast((time - ?) / ? as integer), ?), 0) b, time, value, rowid id
        from samples where series = ? and time >= ? and time <= ?)
  window w as (partition by b order by time, id rows between unbounded preceding and unbounded following)) where r = 1"""
TIERS = """select b, n, s, lo, hi, ft, fv, lt, lv from (
  select b, sum(n) over a n, sum(sum) over a s, min(min) over a lo, max(max) over a hi,
         first_value(first_t) over o ft, first_value(first_v) over o fv,
         last_value(last_t) over c lt, last_value(last_v) over c lv,
         row_number() over (partition by b order by t) r
  from (select max(min(cast((last_t - ?) / ? as integer), ?), 0) b, t, n, sum, min, max, first_t, first_v, last_t, last_v
        from tiers where series = ? and every = ? and t >= ? and t < ?)
  window a as (partition by b),
         o as (partition by b order by first_t, t rows between unbounded preceding and unbounded following),
         c as (partition by b order by last_t, t rows between unbounded preceding and unbounded following)) where r = 1"""


def _merged(rows) -> dict[int, list]:
    """bucket: [n, sum, low, high, first time, open, last time, close]; a later row's close wins only if it is later."""
    got: dict[int, list] = {}
    for b, n, s, lo, hi, ft, fv, lt, lv in rows:
        a = got.get(b)
        if a is None:
            got[b] = [n, s, lo, hi, ft, fv, lt, lv]
            continue
        a[0], a[1], a[2], a[3] = a[0] + n, a[1] + s, min(a[2], lo), max(a[3], hi)
        if ft < a[4]:
            a[4], a[5] = ft, fv
        if lt >= a[6]:
            a[6], a[7] = lt, lv
    return got


def from_store(m, series: str, g: Grid) -> dict[int, list]:
    """From the store's raw readings and roll-ups, without bringing the readings into Python."""
    rows: list = []
    with m._c() as c:
        for e, lo, hi in m._sources(c, series, g.since, g.until, fine=g.step):
            if e == 0:
                rows += c.execute(RAW, (g.start, g.step, g.n - 1, series, lo, hi)).fetchall()
            else:
                rows += c.execute(TIERS, (g.start, g.step, g.n - 1, series, e, lo, hi)).fetchall()
    return _merged(tuple(r) for r in rows)


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
    if hasattr(m, "_sources"):
        return from_store(m, series, g)
    if m.count(series, g.since, g.until) > READINGS_MOST:
        raise TooMany(f"{series} holds more than {READINGS_MOST} readings in this window: ask for a shorter one")
    return from_readings(m.range(series, g.since, g.until), g)


def columns(got: dict[int, list], n: int) -> dict[str, list]:
    """One entry per bucket, null for an empty one (its count too)."""
    out: dict[str, list] = {"open": [None] * n, "high": [None] * n, "low": [None] * n, "close": [None] * n, "count": [None] * n}
    for b, (k, _s, lo, hi, _ft, fv, _lt, lv) in got.items():
        out["open"][b], out["high"][b], out["low"][b], out["close"][b], out["count"][b] = fv, hi, lo, lv, k
    return out
