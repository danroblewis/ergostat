"""What an independent review of the query engine found, each against a worked answer."""

from __future__ import annotations

import threading
import time

import pytest

from ergostat.query import engine, sources
from ergostat.query import transforms as tf
from ergostat.query.buckets import grid
from ergostat.query.sources import series_grid
from ergostat.store import Measurements
from ergostat.web.server import Live, api
from tests.test_query_engine import T, _ask, _q, _record, _series

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


def test_a_counters_rate_in_a_cut_first_bucket_is_over_the_time_it_built_up():
    # 10 more since a reading 55 s before the window, whose first bucket is cut to 5 s: 10 over 60 s, not over 5 s
    assert tf.counter_rate([110.0, 130.0], [5.0, 60.0], 100.0, 55.0) == [10 / 60, 20 / 60]
    assert tf.counter_rate([110.0], [60.0], 100.0) == [10 / 60]


@pytest.fixture
def p(tmp_path):
    return _record(tmp_path)


def _counting(p, monkeypatch):
    calls = []
    real = p.events.query
    monkeypatch.setattr(p.events, "query", lambda **k: calls.append(k) or real(**k))
    return calls


def test_many_event_charts_of_one_window_share_one_read(p, monkeypatch):
    calls = _counting(p, monkeypatch)
    got = _ask(p, *[{"source": "events", "type": "ticket.*", "bucket": 120 + i} for i in range(40)])
    assert len(calls) == 1 and all("error" not in r for r in got)


def test_a_request_reads_the_log_a_few_times_and_says_busy_past_that(p, monkeypatch):
    calls = _counting(p, monkeypatch)
    got = _ask(p, *[{"source": "events", "type": f"ticket.{i}"} for i in range(engine.LOG_READS + 3)])
    assert len(calls) == engine.LOG_READS
    assert all("busy" in r["error"] for r in got[engine.LOG_READS:]) and all("error" not in r for r in got[:engine.LOG_READS])


def test_a_log_read_never_waits_behind_others(p):
    live = Live(p)
    gate = engine._kept(live).log_gate
    for _ in range(engine.LOG_AT_ONCE):
        assert gate.acquire(blocking=False)
    t = time.perf_counter()
    r = api(live, "query", {"q": [_q({"source": "events"}, {"source": "counts", "kind": "ticket"})]})["results"]
    assert time.perf_counter() - t < 2 and "busy" in r[0]["error"] and "error" not in r[1]


def test_a_request_past_its_deadline_starts_nothing_more(p, monkeypatch):
    monkeypatch.setattr(engine, "REQUEST_SECONDS", -1.0)
    r = _ask(p, {"source": "counts", "kind": "ticket"})[0]
    assert "busy" in r["error"]


def test_an_events_window_is_bounded_in_words(p):
    r = _ask(p, {"source": "events"}, since=sources.EVENTS_WINDOW + 86400, until=T + 480)[0]
    assert "31 days" in r["error"]


def test_the_gate_is_released_after_a_failed_read(p, monkeypatch):
    live = Live(p)
    monkeypatch.setattr(p.events, "query", lambda **k: (_ for _ in ()).throw(OSError("gone")))
    assert "could not be read" in api(live, "query", {"q": [_q({"source": "events"})]})["results"][0]["error"]
    gate = engine._kept(live).log_gate
    assert all(gate.acquire(blocking=False) for _ in range(engine.LOG_AT_ONCE))


def test_abandoned_requests_cannot_hold_more_than_the_gate(p, monkeypatch):
    live = Live(p)
    hold, inside = threading.Event(), []
    real = p.events.query

    def slow(**k):
        inside.append(1)
        hold.wait(5)
        return real(**k)
    monkeypatch.setattr(p.events, "query", slow)
    out: list = []
    ts = [threading.Thread(target=lambda i=i: out.append(api(live, "query", {"q": [_q({"source": "events", "bucket": 200 + i})]})))
          for i in range(10)]
    for x in ts:
        x.start()
    deadline = time.monotonic() + 3
    while len(out) < 8 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(inside) <= engine.LOG_AT_ONCE and len(out) >= 8      # the rest answered busy at once
    hold.set()
    for x in ts:
        x.join(5)


def test_two_queries_with_one_id_the_second_says_so(p):
    body = [{"id": "a", "source": "counts", "kind": "ticket"}, {"id": "a", "source": "nope"}, "not an object"]
    got = _ask_raw(p, body)
    assert "error" not in got[0] and "same id" in got[1]["error"] and "must be an object" in got[2]["error"]


def _ask_raw(p, queries):
    import base64
    import json
    raw = base64.urlsafe_b64encode(json.dumps({"since": 480, "until": T + 480, "points": 4, "queries": queries}).encode()).decode()
    return api(Live(p), "query", {"q": [raw]})["results"]


def _reentering(p):
    """x: arrives 10, doing 20, back to open 130, doing 250, done 370. y: arrives 15, doing 260."""
    for item, at, ty in (("x", 10, "ticket.note"), ("y", 15, "ticket.note"), ("x", 20, "ticket.started"), ("x", 130, "ticket.reopened"),
                         ("x", 250, "ticket.started"), ("y", 260, "ticket.started"), ("x", 370, "ticket.done")):
        p.events.add(ty, item=f"ticket/{item}", at=T + at)


@pytest.fixture
def q(tmp_path):
    import textwrap

    from ergostat import model as mdl
    from ergostat.store import Project
    from tests.test_query_engine import MODEL
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace(
        "on: {ticket.started: doing, ticket.done: done}", "on: {ticket.started: doing, ticket.reopened: open, ticket.done: done}"))
    got = Project(mdl.load(tmp_path))
    _reentering(got)
    return got


def test_first_entries_count_an_arrival_once(q):
    every = _ask(q, {"source": "moves", "kind": "ticket", "measure": "entries", "state": "doing", "agg": "count"})[0]
    first = _ask(q, {"source": "moves", "kind": "ticket", "measure": "entries", "first_only": True, "state": "doing", "agg": "count"})[0]
    assert _series(every)["entries"] == [1.0, 0.0, 2.0, 0.0]
    assert _series(first)["entries"] == [1.0, 0.0, 1.0, 0.0]         # x's return at 250 is not a new arrival


def test_time_in_state_can_include_what_is_still_there(q):
    ask = {"source": "moves", "kind": "ticket", "measure": "time_in_state", "state": "doing", "agg": "max"}
    assert _series(_ask(q, ask)[0])["time_in_state"] == [None, 110.0, None, 120.0]
    got = _series(_ask(q, {**ask, "include_open": True})[0])["time_in_state"]
    assert got == [None, 110.0, None, 220.0]             # y, in doing since 260, is 220 s old at the window's end (480)


def test_an_item_in_a_state_it_has_never_left_is_counted_when_open(tmp_path):
    p = _record(tmp_path)
    p.events.add("ticket.started", item="ticket/z", at=T + 400)
    ask = {"source": "moves", "kind": "ticket", "measure": "time_in_state", "state": "done", "agg": "max", "include_open": True}
    assert _series(_ask(p, ask)[0])["time_in_state"][-1] == 110.0     # a, done since 370; no item has ever left done


def test_include_open_reads_the_state_at_the_windows_end(q):
    ask = {"source": "moves", "kind": "ticket", "measure": "time_in_state", "state": "doing", "agg": "max", "include_open": True}
    got = _series(_ask(q, ask, since=240.0, until=T + 240, points=2)[0])["time_in_state"]
    assert got[-1] == 110.0                              # at 240: x had left at 130 (110 s) and nobody was in doing


def test_the_two_flags_are_each_for_their_measure(q):
    assert "include_open" in _ask(q, {"source": "moves", "kind": "ticket", "measure": "entries", "include_open": True})[0]["error"]
    assert "first_only" in _ask(q, {"source": "moves", "kind": "ticket", "measure": "exits", "first_only": True})[0]["error"]


def test_the_fields_name_each_kinds_finished_states(q):
    got = api(Live(q), "query/fields", {})["sources"]
    assert got["moves"]["kinds"]["ticket"]["finished"] == ["done"] and got["items"]["kinds"]["ticket"]["finished"] == ["done"]
