"""``ergostat sensor PART.SENSOR --backfill FILE``: readings at past times, written whole or not at all, and a ledger
of what was backfilled that outlives every roll, prune and event (SPEC §6)."""

import json
import time

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.store import Project

MODEL = """
items:
  pr:
    id: pr/*
    states: [open, done]
    on: {pr.opened: open, pr.merged: done}
stocks:
  points:
    sensor:
      manual: true
  open-prs:
    sensor:
      items: pr
      state: open
flows:
  gained:
    to: points
    sensor:
      changes: rises
      over: 1h
"""
DAY = 86400.0
SERIES = "sensor/points.main"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "repo"
    d.mkdir()
    (d / "ergostat.yaml").write_text(MODEL)
    return d


def project(repo):
    return Project(mdl.load(repo))


def lines(tmp_path, rows, name="h.jsonl"):
    f = tmp_path / name
    f.write_text("".join((r if isinstance(r, str) else json.dumps({"at": r[0], "value": r[1]})) + "\n" for r in rows))
    return f


def cli(repo, *args, capsys):
    rc = main(["-C", str(repo), *args])
    got = capsys.readouterr()
    return rc, got.out, got.err


def test_past_readings_are_in_range(repo, tmp_path, capsys):
    now = time.time()
    rows = [(now - 3 * DAY, 1.0), (now - 2 * DAY, 4.0), (now - DAY, 9.0)]
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfill", str(lines(tmp_path, rows)), "--from", "git log",
                     capsys=capsys)
    assert rc == 0 and "3 written, 0 skipped" in out
    assert project(repo).measurements.range(SERIES, now - 4 * DAY, now) == rows


def test_twice_writes_nothing_new(repo, tmp_path, capsys):
    now = time.time()
    f = lines(tmp_path, [(now - 100, 1.0), (now - 50, 2.0)])
    assert cli(repo, "sensor", "points.main", "--backfill", str(f), capsys=capsys)[0] == 0
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfill", str(f), "--json", capsys=capsys)
    got = json.loads(out)
    assert rc == 0 and (got["count"], got["skipped"]) == (0, 2)
    lines(tmp_path, [(now - 100, 1.0), (now - 50, 2.0), (now - 10, 3.0)])        # one more: only it is written
    got = json.loads(cli(repo, "sensor", "points.main", "--backfill", str(f), "--json", capsys=capsys)[1])
    assert (got["count"], got["skipped"], got["first"]) == (1, 2, now - 10)
    assert project(repo).measurements.range(SERIES, now - 200, now) == [(now - 100, 1.0), (now - 50, 2.0), (now - 10, 3.0)]


def test_twice_after_the_roll_writes_nothing_new(repo, tmp_path, capsys):
    now = time.time()
    rows = [(now - 10 * DAY - i * 3600, float(i)) for i in (2, 1, 0)]
    f = lines(tmp_path, rows)
    assert cli(repo, "sensor", "points.main", "--backfill", str(f), capsys=capsys)[0] == 0
    p = project(repo)
    assert p.measurements.roll(now)["forgot"] >= 3                                # the raw readings are gone: buckets
    with p.measurements._c() as c:
        assert c.execute("select count(*) from samples where series = ?", (SERIES,)).fetchone()[0] == 0
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfill", str(f), capsys=capsys)
    assert rc == 0 and "0 written, 3 skipped" in out
    p.measurements.roll(now)
    assert p.measurements.range(SERIES, now - 11 * DAY, now) == rows


def test_two_readings_in_one_old_bucket_are_one_point(repo, tmp_path, capsys):
    """SPEC §6: a bucket keeps the last of the readings in it, so two closer than an old tier's bucket are one point."""
    now = time.time()
    t = (now - 10 * DAY) // 60 * 60
    f = lines(tmp_path, [(t + 10, 1.0), (t + 40, 2.0)])
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfill", str(f), capsys=capsys)
    assert rc == 0 and "2 written" in out
    p = project(repo)
    p.measurements.roll(now)
    assert p.measurements.range(SERIES, t - 60, t + 120) == [(t + 40, 2.0)]
    assert [b["count"] for b in p.measurements.backfills(SERIES)] == [2]


@pytest.mark.parametrize("bad", ["not json", '{"at": 1}', '{"at": "1", "value": 2}', '{"at": 1, "value": NaN}',
                                 '{"at": 1, "value": Infinity}', '{"at": 1e999, "value": 1}', '{"at": true, "value": 1}',
                                 "[1, 2]", "null", "FUTURE"])
def test_future_or_malformed_refuses_all(repo, tmp_path, capsys, bad):
    now = time.time()
    bad = bad.replace("FUTURE", json.dumps({"at": now + 3600, "value": 1}))
    f = lines(tmp_path, [(now - 100, 1.0), bad, (now - 50, 2.0)])
    rc, _, err = cli(repo, "sensor", "points.main", "--backfill", str(f), capsys=capsys)
    assert rc == 2 and "nothing written: line 2" in err
    p = project(repo)
    assert p.measurements.range(SERIES, 0, now + 7200) == [] and p.measurements.backfills(SERIES) == []
    assert not p.events.query(n=None, type="sensor.backfilled")


def test_same_at_in_one_file_keeps_the_last(repo, tmp_path, capsys):
    now = time.time()
    f = lines(tmp_path, [(now - 100, 1.0), (now - 50, 2.0), (now - 100, 7.0)])
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfill", str(f), capsys=capsys)
    assert rc == 0 and "2 written" in out and "1 at a time another line had (the last kept)" in out
    assert project(repo).measurements.range(SERIES, now - 200, now) == [(now - 100, 7.0), (now - 50, 2.0)]
    (e,) = project(repo).events.query(n=None, type="sensor.backfilled")
    assert (e["data"]["written"], e["data"]["repeated"]) == (2, 1)


def test_derived_sensors_refused(repo, tmp_path, capsys):
    f = lines(tmp_path, [(time.time() - 100, 1.0)])
    for name, how in (("open-prs.main", "items"), ("gained.main", "changes")):
        rc, _, err = cli(repo, "sensor", name, "--backfill", str(f), capsys=capsys)
        assert rc == 2 and f"derived by ergostat ({how})" in err
    p = project(repo)
    assert p.measurements.count() == 0 and not p.events.query(n=None, type="sensor.backfilled")


def test_backfilled_lists_the_span_after_events_are_pruned(repo, tmp_path, capsys):
    now = time.time()
    f = lines(tmp_path, [(now - 5 * DAY, 1.0), (now - 4 * DAY, 2.0)])
    assert cli(repo, "sensor", "points.main", "--backfill", str(f), "--from", "git history", capsys=capsys)[0] == 0
    p = project(repo)
    p.events.add("noise", at=now + 10)
    p.events.prune(now + 5)
    p.measurements.prune(now - 3 * DAY)                    # the readings themselves gone too: the ledger stays
    assert not p.events.query(n=None, type="sensor.backfilled")
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfilled", "--json", capsys=capsys)
    (b,) = json.loads(out)
    assert rc == 0 and (b["from"], b["first"], b["last"], b["count"]) == ("git history", now - 5 * DAY, now - 4 * DAY, 2)
    rc, out, _ = cli(repo, "sensor", "points.main", "--backfilled", capsys=capsys)
    assert rc == 0 and "2 readings" in out and "from git history" in out and "1 backfill of points.main" in out


def test_changes_flow_reads_backfilled_history(repo, tmp_path, capsys):
    now = time.time()
    f = lines(tmp_path, [(now - 7200, 0.0), (now - 1800, 10.0), (now - 1200, 16.0), (now - 600, 12.0)])
    assert cli(repo, "sensor", "points.main", "--backfill", str(f), capsys=capsys)[0] == 0
    from ergostat.spec.engine import changed
    p = project(repo)
    spec = p.model.spec
    assert changed(spec, spec.flows["gained"].sensors["main"], p.measurements, now)[0] == 16.0
