"""What an independent review of the query engine found, each against a worked answer."""

from __future__ import annotations

from ergostat.query.buckets import grid
from ergostat.query.sources import series_grid
from ergostat.store import Measurements

DAY = 86400.0
BASE = 20_000 * DAY


def _rolled(tmp_path) -> tuple[Measurements, list]:
    """A reading every 37 s for a day, rolled into 600 s rows, the raw readings gone."""
    m = Measurements(tmp_path, raw=60.0, tiers=[(600.0, 1e9)])
    rows = [("s", BASE + i * 37.0, float(i % 50)) for i in range(int(DAY // 37))]
    m.add_many(rows)
    m.roll(now=BASE + DAY + 1200)
    m._marks = (0.0, {})
    return m, rows


def test_a_series_step_is_a_multiple_of_the_tier_that_answers_it(tmp_path):
    m, _ = _rolled(tmp_path)
    assert grid(BASE, BASE + DAY, 120).step == 720
    assert series_grid(m, "s", BASE, BASE + DAY, 120, None).step == 1200


def test_rolled_buckets_match_the_raw_readings_they_came_from(tmp_path):
    m, rows = _rolled(tmp_path)
    g = series_grid(m, "s", BASE, BASE + DAY, 120, None)
    got = {r[0]: r for r in m.rollups("s", g.since, g.until, g.start, g.step, g.n)}
    want: dict[int, list] = {}
    for _, t, v in rows:
        if g.since <= t <= g.until:
            a = want.setdefault(g.at(t), [0, 0.0])
            a[0] += 1
            a[1] += v
    whole = [b for b in want if g.spans[b] == g.step and b in got]
    assert len(whole) > 60
    assert all(got[b][1] == want[b][0] and got[b][2] == want[b][1] for b in whole)


def test_a_store_with_nothing_rolled_keeps_the_asked_step(tmp_path):
    m = Measurements(tmp_path, raw=DAY, tiers=[(600.0, 1e9)])
    m.add("s", 1.0, at=BASE)
    assert series_grid(m, "s", BASE, BASE + DAY, 120, None).step == 720
