"""The status reads the window's readings of every sensor together (``Victoria.ranges``) and the store's first reading
(``first_time``): each answer equals the store's own, one series at a time (dev/records/status-reads-the-projections.md)."""

from __future__ import annotations

import random
import uuid

from ergostat.victoria import Victoria

DAY = 86400.0
NOW = 1_790_000_000.0                                    # (in the past: a query asks up to a day ahead)


def _store(tmp_path, vm, r: random.Random) -> tuple[Victoria, list]:
    m = Victoria(vm, tmp_path, project=f"test-{uuid.uuid4().hex[:10]}")
    rows = []
    for k in range(12):                                   # some read for days, some only lately, some long ago only
        since = r.choice([5 * DAY, 3 * 3600.0, 600.0, 4 * DAY])
        until = r.choice([0.0, 0.0, 2 * DAY]) if since > DAY else 0.0
        t = NOW - since
        while t < NOW - until:
            rows.append((f"sensor/s{k}", t, round(r.uniform(0, 9), 1)))
            t += r.choice([30.0, 60.0, 61.5, 600.0])
    r.shuffle(rows)                                       # (written in no order: a late reading among them)
    m.add_many(rows)
    return m, rows


def test_the_readings_read_together_are_each_series_own_range(tmp_path, vm):
    r = random.Random("together")
    m, _ = _store(tmp_path, vm, r)
    names = [f"sensor/s{k}" for k in range(12)] + ["sensor/none"]
    for _ in range(10):
        a = NOW - r.choice([3600.0, 5 * 3600.0, 7 * 3600.0, 3 * DAY, 300.0])
        b = r.choice([NOW, NOW - 60.0, a + 1800.0])
        got = m.ranges(names, a, b)
        assert sorted(got) == sorted(names)
        for s in names:
            assert got[s] == m.range(s, a, b), (s, a, b)
    assert got["sensor/none"] == []


def test_the_first_reading_is_the_oldest_of_any_series(tmp_path, vm):
    m, rows = _store(tmp_path, vm, random.Random("first"))
    assert m.first_time() == min(t for _, t, _ in rows)
    assert Victoria(vm, tmp_path / "empty", project=f"test-{uuid.uuid4().hex[:10]}").first_time() is None
