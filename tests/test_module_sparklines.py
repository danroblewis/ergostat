"""The module boxes' sparklines, without a browser (dev/records/module-box-sparklines.md): the one batched answer
(``GET /api/series?measured=1``) reads the measurement store alone, never the event log or the page's state, and a
bucket with no reading is None (a gap), never a zero or the reading before it."""

from __future__ import annotations

import time

import pytest

SPARKED = """
name: sparked
stocks:
  backlog:
    unit: tickets
    sensor:
      manual: true
flows:
  arriving:
    to: backlog
    sensor:
      manual: true
  finishing:
    from: backlog
auxiliaries:
  pressure:
    unit: share
    driven-by: +stock.backlog
    sensor:
      manual: true
"""


class NoLog:
    """An event log that may not be read: any use of it fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"the event log was read: .{name}")


@pytest.fixture
def project(tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.store import Project
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "sparked"
    d.mkdir()
    (d / "ergostat.yaml").write_text(SPARKED)
    p = Project(mdl.load(d))
    now = time.time()
    for i in range(360):                       # the last hour, every 10s, but for minutes 20 to 30 ago (backlog's hole)
        t = now - 3600 + i * 10
        if not (now - 1810 <= t < now - 1190):
            p.measurements.add("sensor/backlog.main", 4 + i % 3, at=t)
        p.measurements.add("sensor/pressure.main", 0.5, at=t)
        p.measurements.add("sensor/arriving.main", 6, at=t)
    p.events.add("valve.opened", item="w", data={"amount": 1, "flow": "finishing"}, at=now - 60)
    return p, now


def ask(p, refs: str, points: int = 12, at: float | None = None):
    from ergostat import state
    from ergostat.web.server import Live, api
    live = Live(p)
    p.events = NoLog()                         # (after Live is made: from here on nothing may read it)
    q = {"refs": [refs], "measured": ["1"], "since": ["1h"], "points": [str(points)]}
    if at is not None:
        q["at"] = [str(at)]
    was = state.snapshot

    def no(*a, **kw):
        raise AssertionError("a snapshot was taken")
    state.snapshot = no
    try:
        return api(live, "series", q)
    finally:
        state.snapshot = was


def test_one_answer_for_every_box_from_the_store_alone_with_gaps_where_nothing_was_read(project):
    p, now = project
    d = ask(p, "stock.backlog,stock.pressure,flow.arriving,flow.finishing,stock.nothing", at=now + 1)
    got = {s["ref"]: s for s in d["series"]}
    assert set(got) == {"stock.backlog", "auxiliary.pressure", "flow.arriving", "flow.finishing"}, got
    assert d["until"] - d["since"] == pytest.approx(3600) and len(d["times"]) == 12
    back = got["stock.backlog"]["values"]
    hole = [i for i, v in enumerate(back) if v is None]
    assert hole == [6, 7], back                 # minutes 20-30 ago: buckets 6 and 7 of 12 (5 minutes each), nothing else
    assert all(v in (4, 5, 6) for i, v in enumerate(back) if i not in hole), back
    assert got["auxiliary.pressure"]["values"] == [0.5] * 12
    assert got["flow.arriving"]["values"] == [6] * 12 and got["flow.arriving"]["how"].startswith("measured by")
    # a flow no sensor reads: not measured, all gaps (its valve's openings are in the event log, never read here)
    assert got["flow.finishing"]["values"] == [None] * 12 and got["flow.finishing"]["how"] == "not measured"


def test_a_reading_that_stopped_is_a_gap_after_it_never_carried_on(project):
    p, now = project
    d = ask(p, "stock.backlog", points=12, at=now + 1800)      # half an hour on: nothing read since `now`
    vals = d["series"][0]["values"]
    assert vals[-6:] == [None] * 6, vals
    assert vals[:2] == [None, None] and all(v is not None for v in vals[2:6]), vals     # (the hole, then readings)


def test_the_answer_reads_at_most_its_ceiling_of_parts(project):
    from ergostat import series
    p, now = project
    d = ask(p, ",".join(["stock.backlog"] * 5 + [f"stock.x{i}" for i in range(200)]))
    assert [s["ref"] for s in d["series"]] == ["stock.backlog"]        # (asked again: answered once)
    assert series.MEASURED_REFS == 60
    assert d["cut"] == [f"stock.x{i}" for i in range(59, 200)], d["cut"]   # (the 59 after backlog are read, if unknown)


def test_parts_past_the_ceiling_are_named_as_cut_never_answered_as_unread(tmp_path, monkeypatch):
    """More than MEASURED_REFS parts asked, every one read in the store: the first 60 are answered with their readings,
    the rest named in ``cut`` and absent from ``series`` (so the page draws nothing for them, never 'no readings')."""
    from ergostat import model as mdl
    from ergostat.store import Project
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "wide"
    d.mkdir()
    (d / "ergostat.yaml").write_text("name: wide\nstocks:\n" + "".join(
        f"  s{i}:\n    unit: things\n    sensor:\n      manual: true\n" for i in range(70)))
    p = Project(mdl.load(d))
    now = time.time()
    for i in range(70):
        for k in range(12):
            p.measurements.add(f"sensor/s{i}.main", i, at=now - 3600 + k * 300)
    refs = [f"stock.s{i}" for i in range(70)]
    got = ask(p, ",".join(refs), at=now + 1)
    assert [s["ref"] for s in got["series"]] == refs[:60], got["series"]
    assert all(any(v == i for v in s["values"]) for i, s in enumerate(got["series"])), "a read part answered as unread"
    assert got["cut"] == refs[60:], got["cut"]
