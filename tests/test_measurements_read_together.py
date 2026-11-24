"""The status reads the window's readings of every sensor together (``Measurements.ranges``) and the store's first
reading by each series' index (``first_time``): each answer equals the store's own, one series at a time, with raw
readings kept for a while and tiers below them (dev/records/status-reads-the-projections.md)."""

from __future__ import annotations

import random

from ergostat.store import Measurements

DAY = 86400.0
NOW = 1_800_000_000.0


def _store(tmp_path, r: random.Random) -> Measurements:
    m = Measurements(tmp_path, raw=6 * 3600.0, tiers=[(60.0, 2 * DAY), (600.0, 30 * DAY)])
    rows = []
    for k in range(12):                                   # some read for days, some only lately, some long ago only
        since = r.choice([5 * DAY, 3 * 3600.0, 600.0, 4 * DAY])
        until = r.choice([0.0, 0.0, 2 * DAY]) if since > DAY else 0.0
        t = NOW - since
        while t < NOW - until:
            rows.append((f"sensor/s{k}", t, round(r.uniform(0, 9), 1)))
            if r.random() < 0.05:                         # two readings at one moment
                rows.append((f"sensor/s{k}", t, round(r.uniform(0, 9), 1)))
            t += r.choice([30.0, 60.0, 61.5, 600.0])
    r.shuffle(rows)                                       # (written in no order: a late reading among them)
    m.add_many(rows)
    m.roll(NOW)                                           # raw past its keep rolled into the tiers and forgotten
    return m


def test_the_readings_read_together_are_each_series_own_range(tmp_path):
    r = random.Random("together")
    m = _store(tmp_path, r)
    names = [f"sensor/s{k}" for k in range(12)] + ["sensor/none"]
    answered = left = 0
    for _ in range(40):
        a = NOW - r.choice([3600.0, 5 * 3600.0, 7 * 3600.0, 3 * DAY, 300.0])
        b = r.choice([NOW, NOW - 60.0, a + 1800.0])
        got = m.ranges(names, a, b)
        for s in names:
            if s in got:
                assert got[s] == m.range(s, a, b), (s, a, b)
                answered += 1
            else:
                left += 1
    assert answered and left                              # (both: raw alone answers some, the tiers the rest)


def test_the_first_reading_is_found_by_each_series_index(tmp_path):
    r = random.Random("first")
    m = _store(tmp_path, r)
    with m._c() as c:
        want = min(x for x in (c.execute("select min(time) from samples").fetchone()[0],
                               c.execute("select min(first_t) from tiers").fetchone()[0]) if x is not None)
    assert m.first_time() == want
    (tmp_path / "empty").mkdir()
    assert Measurements(tmp_path / "empty").first_time() is None
