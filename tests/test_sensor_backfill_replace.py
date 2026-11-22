"""``ergostat sensor PART.SENSOR --backfill FILE --replace --from TEXT``: a redefined measure's history written again,
what was in the file's span set aside first (SPEC §6)."""

import json
import time

import pytest

from ergostat.spec.engine import changed
from ergostat.store import Project
from tests.test_sensor_backfill import DAY, MODEL, SERIES, cli, lines, project


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "repo"
    d.mkdir()
    (d / "ergostat.yaml").write_text(MODEL)
    return d


def replace(repo, tmp_path, rows, capsys, *more):
    return cli(repo, "sensor", "points.main", "--backfill", str(lines(tmp_path, rows, "new.jsonl")), "--replace",
               *more, capsys=capsys)


def test_replace_swaps_the_values_in_the_span(repo, tmp_path, capsys):
    now = time.time()
    old = [(now - 1000 + i * 60, float(i)) for i in range(10)]
    assert cli(repo, "sensor", "points.main", "--backfill", str(lines(tmp_path, old)), "--from", "v1", capsys=capsys)[0] == 0
    new = [(t, v * 10 + 5) for t, v in old]
    rc, out, _ = replace(repo, tmp_path, new, capsys, "--from", "v2", "--json")
    got = json.loads(out)
    assert rc == 0 and (got["count"], got["skipped"], got["replaced"]) == (10, 0, 10)
    p = project(repo)
    assert p.measurements.range(SERIES, now - 2000, now) == new
    (e,) = [e for e in p.events.query(n=None, type="sensor.backfilled") if e["data"]["from"] == "v2"]
    assert e["data"]["replaced"] == 10 and e["data"]["written"] == 10
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfilled", capsys=capsys)
    first, second = out.splitlines()[:2]
    assert "from v1  (replaced " in first and "replaced" not in second
    assert [b["replaced"] is not None for b in json.loads(cli(repo, "sensor", "points.main", "--backfilled", "--json",
                                                                capsys=capsys)[1])] == [True, False]


def test_replace_removes_live_readings_in_the_span(repo, tmp_path, capsys):
    now = time.time()
    p = project(repo)
    for i in range(5):
        p.measurements.add(SERIES, 100.0 + i, at=now - 500 + i * 100 + 30)      # live, between the file's times
    new = [(now - 500 + i * 100, 1.0) for i in range(5)]
    rc, out, _ = replace(repo, tmp_path, new, capsys, "--from", "redefined")
    assert rc == 0 and "4 set aside, 5 written" in out                         # (the fifth is past the file's last)
    assert project(repo).measurements.range(SERIES, now - 1000, now) == [*new, (now - 70, 104.0)]


def test_replace_leaves_readings_outside_the_span(repo, tmp_path, capsys):
    now = time.time()
    before = [(now - 900, 1.0), (now - 800, 2.0)]
    inside = [(now - 600, 3.0), (now - 500, 4.0)]
    after = [(now - 300, 5.0), (now - 200, 6.0)]
    f = lines(tmp_path, before + inside + after)
    assert cli(repo, "sensor", "points.main", "--backfill", str(f), "--from", "v1", capsys=capsys)[0] == 0
    project(repo).measurements.add(SERIES, 7.0, at=now - 100)
    rc, _, _ = replace(repo, tmp_path, [(now - 650, 30.0), (now - 450, 40.0)], capsys, "--from", "v2")
    assert rc == 0
    assert project(repo).measurements.range(SERIES, now - 1000, now) == [
        *before, (now - 650, 30.0), (now - 450, 40.0), *after, (now - 100, 7.0)]


def test_replace_after_the_roll(repo, tmp_path, capsys):
    now = time.time()
    t0 = (now - 10 * DAY) // 3600 * 3600
    old = [(t0 + i * 600, float(i)) for i in range(10)]
    assert cli(repo, "sensor", "points.main", "--backfill", str(lines(tmp_path, old)), "--from", "v1", capsys=capsys)[0] == 0
    p = project(repo)
    p.measurements.roll(now)
    with p.measurements._c() as c:                                              # the span is only in buckets now
        assert c.execute("select count(*) from samples where series = ?", (SERIES,)).fetchone()[0] == 0
        assert c.execute("select count(*) from tiers where series = ?", (SERIES,)).fetchone()[0] > 0
    new = [(t, 100.0 + v) for t, v in old]
    rc, out, _ = replace(repo, tmp_path, new, capsys, "--from", "v2")
    assert rc == 0 and "10 set aside, 10 written" in out
    p.measurements.roll(now)
    assert p.measurements.range(SERIES, t0 - 3600, t0 + 7200) == new
    with p.measurements._c() as c:
        assert c.execute("select min(min) from tiers where series = ?", (SERIES,)).fetchone()[0] >= 100.0
        assert c.execute("select count(*) from samples where series = ?", (SERIES,)).fetchone()[0] == 0
    means = [m for _, m, _, _ in p.measurements.bucketed(SERIES, t0, t0 + 6000, 1)]
    assert means == [sum(v for _, v in new) / 10]


@pytest.mark.parametrize("days, lost", [(30, 15), (120, 30)])
def test_replace_older_than_the_finest_keep(repo, tmp_path, capsys, days, lost):
    """Past the 1m tier's keep (14 days) only 10m buckets hold the span, past the 10m's (90) only 1h ones: those it
    overlaps are dropped, with their readings outside the span, and all of them are counted as set aside."""
    now = time.time()
    t0 = (now - days * DAY) // 3600 * 3600
    old = [(t0 + i * 120, 1.0) for i in range(60)]
    assert cli(repo, "sensor", "points.main", "--backfill", str(lines(tmp_path, old)), "--from", "v1", capsys=capsys)[0] == 0
    p = project(repo)
    p.measurements.roll(now)
    new = [(t0 + 1500 + i * 120, 9.0) for i in range(11)]
    rc, out, _ = replace(repo, tmp_path, new, capsys, "--from", "v2")
    assert rc == 0 and f"{lost} set aside, 11 written" in out
    p.measurements.roll(now)
    m = p.measurements
    assert m.count(SERIES, t0 - 3600, t0 + 10800) == 60 - lost + 11
    assert m.count(SERIES, t0 + 3600, t0 + 7200) == 30                         # the next hour: untouched
    if days == 30:                                                             # the 10m buckets beside the dropped ones
        assert m.count(SERIES, t0 + 600, t0 + 1199) == 5 and m.count(SERIES, t0 + 3000, t0 + 3599) == 5


def test_changes_flow_sees_no_false_step(repo, tmp_path, capsys):
    now = time.time()
    old = [(now - 3000 + i * 600, 100.0 - i * 10) for i in range(4)]            # the old definition: falling
    assert cli(repo, "sensor", "points.main", "--backfill", str(lines(tmp_path, old)), "--from", "v1", capsys=capsys)[0] == 0
    new = [(now - 3000 + i * 300, 1.0 + i) for i in range(9)]                   # the new: one up each reading
    assert replace(repo, tmp_path, new, capsys, "--from", "v2")[0] == 0
    p = project(repo)
    spec = p.model.spec
    assert changed(spec, spec.flows["gained"].sensors["main"], p.measurements, now)[0] == 8.0


def test_a_store_from_before_the_columns_takes_a_replace(tmp_path):
    """``forgotten.why`` and ``backfills.replaced`` are added to a file made before them."""
    import sqlite3

    from ergostat.store import Measurements
    old = sqlite3.connect(tmp_path / "measurements.db")
    old.executescript("create table forgotten (series text not null, time real not null, value real not null, "
                      "forgotten_at real not null); create table backfills (id text primary key, series text not null, "
                      "src text, written_at, first real, last real, count int);")
    old.close()
    m = Measurements(tmp_path)
    m.backfill("s", [(100.0, 1.0)], "v1")
    assert m.backfill("s", [(100.0, 2.0)], "v2", replace=True)["replaced"] == 1
    assert m.range("s", 0, 200) == [(100.0, 2.0)] and m.backfills("s")[0]["replaced"] is not None


def test_replaced_readings_are_kept_aside(repo, tmp_path, capsys):
    now = time.time()
    old = [(now - 300, 1.0), (now - 200, 2.0)]
    assert cli(repo, "sensor", "points.main", "--backfill", str(lines(tmp_path, old)), "--from", "v1", capsys=capsys)[0] == 0
    rc, _, err = replace(repo, tmp_path, [(now - 300, 5.0), (now - 200, 6.0)], capsys)
    assert rc == 2 and "--from" in err                                          # refused without --from: nothing done
    p = project(repo)
    assert p.measurements.range(SERIES, now - 400, now) == old
    assert replace(repo, tmp_path, [(now - 300, 5.0), (now - 200, 6.0)], capsys, "--from", "v2 of the measure")[0] == 0
    with Project(p.model).measurements._c() as c:
        kept = c.execute("select time, value, why, forgotten_at from forgotten where series = ? order by time",
                         (SERIES,)).fetchall()
    assert [(r[0], r[1], r[2]) for r in kept] == [(*o, "v2 of the measure") for o in old]
    assert all(now <= r[3] <= time.time() for r in kept)
