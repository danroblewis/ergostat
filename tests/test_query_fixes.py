"""What an independent review of the query engine found, each against a worked answer."""

from __future__ import annotations

import uuid

import pytest

from ergostat.query import engine, sources
from ergostat.query import transforms as tf
from ergostat.query.buckets import grid
from ergostat.query.sources import series_grid
from ergostat.victoria import Victoria
from ergostat.web.server import Live, api
from tests.test_query_engine import T, _ask, _q, _record, _series

DAY = 86400.0
BASE = 20_000 * DAY


def _store(tmp_path, vm) -> tuple[Victoria, list]:
    """A reading every 37 s for a day."""
    m = Victoria(vm, tmp_path, project=f"test-{uuid.uuid4().hex[:10]}")
    rows = [("s", BASE + i * 37.0, float(i % 50)) for i in range(int(DAY // 37))]
    m.add_many(rows)
    return m, rows


def test_a_series_keeps_the_asked_step(tmp_path, vm):
    m, _ = _store(tmp_path, vm)
    assert grid(BASE, BASE + DAY, 120).step == 720
    assert series_grid(m, "s", BASE, BASE + DAY, 120, None).step == 720


def test_buckets_match_the_raw_readings_they_came_from(tmp_path, vm):
    m, rows = _store(tmp_path, vm)
    g = series_grid(m, "s", BASE, BASE + DAY, 120, None)
    got = {r[0]: r for r in m.rollups("s", g.since, g.until, g.start, g.step, g.n)}
    want: dict[int, list] = {}
    for _, t, v in rows:
        if g.since <= t <= g.until:
            a = want.setdefault(g.at(t), [0, 0.0])
            a[0] += 1
            a[1] += v
    assert len(got) == len(want) > 100
    assert all(got[b][1] == want[b][0] and got[b][2] == want[b][1] for b in want)
    q = engine.Query(id="a", source="series", agg="sum", series="s")
    read = sources.series(type("P", (), {"measurements": m, "model": type("M", (), {"stocks": {}, "flows": {}})()})(), None, q, g)
    assert read.levels["s"][0] == want[0][1] and read.note is None


def test_a_counters_rate_in_a_cut_first_bucket_is_over_the_time_it_built_up():
    # 10 more since a reading 55 s before the window, whose first bucket is cut to 5 s: 10 over 60 s, not over 5 s
    assert tf.counter_rate([110.0, 130.0], [5.0, 60.0], 100.0, 55.0) == [10 / 60, 20 / 60]
    assert tf.counter_rate([110.0], [60.0], 100.0) == [10 / 60]


@pytest.fixture
def p(tmp_path):
    return _record(tmp_path)


def test_an_events_chart_is_sql_over_the_item_index_and_never_reads_the_log(p, monkeypatch):
    """Events are counted from the item index's per-minute counts (the ``events`` view), never by reading the log."""
    monkeypatch.setattr(p.events, "moments", lambda **k: (_ for _ in ()).throw(AssertionError("read the log")))
    got = _ask(p, *[{"source": "events", "type": "ticket.*", "bucket": 120 + i} for i in range(8)])
    assert all("error" not in r and r["read_log"] is False for r in got)
    assert all(r["compiled"][0]["source"] == "sql" for r in got)


def test_a_request_past_its_deadline_starts_nothing_more(p, monkeypatch):
    monkeypatch.setattr(engine, "REQUEST_SECONDS", -1.0)
    r = _ask(p, {"source": "counts", "kind": "ticket"})[0]
    assert "busy" in r["error"]


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
