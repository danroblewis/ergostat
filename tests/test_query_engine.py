"""The query engine over a small record worked out by hand (ergostat/query): each source, grouping, filters, the cap,
refusals, the cache, read-only access, and a factory-sized record answered without reading the event log."""

from __future__ import annotations

import base64
import json
import random
import textwrap
import time
import urllib.error
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat.query import BadQuery, engine, sources
from ergostat.query.parse import MOST_ENCODED, MOST_QUERIES
from ergostat.store import Measurements, Project
from ergostat.web import serve
from ergostat.web.server import Live, api
from tests.ports import free_port

T = 14_916_667 * 120.0      # on a multiple of the 120 s buckets below
MODEL = """
    name: q
    stocks:
      queue: {unit: tickets}
    items:
      ticket:
        id: ticket/*
        states: [open, doing, done]
        on: {ticket.started: doing, ticket.done: done}
        fold: {ai_cost_usd: sum}
    storage:
      events: segments
    """


def _record(tmp_path) -> Project:
    """a: arrives 10, doing 130, done 370. b: arrives 20, doing 140. c: arrives 250. Costs: a 1, 2, 0.5; b 4."""
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    p = Project(mdl.load(tmp_path))
    for item, at, ty, data in (("a", 10, "ticket.note", {"ai_cost_usd": 1.0, "size": "s"}),
                               ("b", 20, "ticket.note", {"ai_cost_usd": 4.0, "size": "s"}),
                               ("a", 130, "ticket.started", {"ai_cost_usd": 2.0}),
                               ("b", 140, "ticket.started", {}),
                               ("c", 250, "ticket.note", {"size": "l"}),
                               ("a", 370, "ticket.done", {"ai_cost_usd": 0.5})):
        p.events.add(ty, item=f"ticket/{item}", data=data, at=T + at)
    return p


def _q(*queries, since=480.0, until=T + 480, points=4) -> str:
    body = {"since": since, "until": until, "points": points, "queries": [{"id": str(i), **x} for i, x in enumerate(queries)]}
    return base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")


def _ask(p, *queries, **kw) -> list[dict]:
    return api(Live(p), "query", {"q": [_q(*queries, **kw)]})["results"]


def _series(r: dict) -> dict:
    assert "error" not in r, r
    return {s["name"]: s["values"] for s in r["series"]}


@pytest.fixture
def p(tmp_path):
    return _record(tmp_path)


def test_the_answers_shape(p):
    got = api(Live(p), "query", {"q": [_q({"source": "counts", "kind": "ticket"})]})
    assert (got["since"], got["until"], got["step"]) == (T, T + 480, 120)
    r = got["results"][0]
    assert r["times"] == [T, T + 120, T + 240, T + 360]
    assert (r["unit"], r["capped"], r["read_log"]) == ("items", 0, False)


def test_items_sum_adds_what_each_change_moved_the_field(p):
    r = _ask(p, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum"})[0]
    assert _series(r) == {"ai_cost_usd": [5.0, 2.0, 0.0, 0.5]} and r["unit"] == "usd"


def test_items_rate_per_hour(p):
    r = _ask(p, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum", "transform": "rate",
                 "rate_per": "hour"})[0]
    assert _series(r)["ai_cost_usd"] == pytest.approx([150.0, 60.0, 0.0, 15.0]) and r["unit"] == "usd/h"


@pytest.mark.parametrize("agg,want", [("count", [2.0, 1.0, 0.0, 1.0]), ("last", [5.0 - 1.0, 3.0, None, 3.5]),
                                      ("max", [4.0, 3.0, None, 3.5]), ("min", [1.0, 3.0, None, 3.5]),
                                      ("avg", [2.5, 3.0, None, 3.5]), ("p50", [2.5, 3.0, None, 3.5])])
def test_items_other_aggregations_read_the_values_the_items_took(p, agg, want):
    r = _ask(p, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": agg})[0]
    assert _series(r)["ai_cost_usd"] == want


def test_items_filtered_and_grouped(p):
    done = _ask(p, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum", "where": {"state": ["done"]}})[0]
    assert _series(done)["ai_cost_usd"] == [1.0, 2.0, 0.0, 0.5]
    by = _ask(p, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum", "group_by": "size"})[0]
    assert _series(by) == {"s": [5.0, 2.0, 0.0, 0.5]}
    by = _ask(p, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum", "group_by": "state"})[0]
    assert _series(by) == {"doing": [4.0, 0.0, 0.0, 0.0], "done": [1.0, 2.0, 0.0, 0.5]}
    assert [s["name"] for s in by["series"]] == ["doing", "done"]     # a kind's states in their order


def test_moves_entries_and_exits(p):
    into = _ask(p, {"source": "moves", "kind": "ticket", "measure": "entries", "state": "doing"})[0]
    assert _series(into) == {"entries": [0.0, 2.0, 0.0, 0.0]}
    out = _ask(p, {"source": "moves", "kind": "ticket", "measure": "exits", "state": "open"})[0]
    assert _series(out) == {"exits": [0.0, 2.0, 0.0, 0.0]}
    arrivals = _ask(p, {"source": "moves", "kind": "ticket", "measure": "entries", "state": "open"})[0]
    assert _series(arrivals) == {"entries": [2.0, 0.0, 1.0, 0.0]}


def test_moves_time_in_state(p):
    r = _ask(p, {"source": "moves", "kind": "ticket", "measure": "time_in_state", "state": "doing", "agg": "p50"})[0]
    assert _series(r) == {"time_in_state": [None, None, None, 240.0]} and r["unit"] == "seconds"
    by = _ask(p, {"source": "moves", "kind": "ticket", "measure": "time_in_state", "agg": "max", "group_by": "state"})[0]
    assert _series(by) == {"open": [None, 120.0, None, None], "doing": [None, None, None, 240.0]}


def test_counts_are_the_level_at_each_buckets_end(p):
    r = _ask(p, {"source": "counts", "kind": "ticket"})[0]
    assert _series(r) == {"open": [2.0, 0.0, 1.0, 1.0], "doing": [0.0, 2.0, 2.0, 1.0], "done": [0.0, 0.0, 0.0, 1.0]}
    assert [s["name"] for s in r["series"]] == ["open", "doing", "done"]


def test_counts_carry_what_came_before_the_window(p):
    r = _ask(p, {"source": "counts", "kind": "ticket", "state": ["doing"]}, since=240.0, until=T + 480, points=2)[0]
    assert _series(r) == {"doing": [2.0, 1.0]}


def test_counts_filtered_by_a_field(p):
    r = _ask(p, {"source": "counts", "kind": "ticket", "where": {"size": "l"}})[0]
    assert _series(r) == {"open": [0.0, 0.0, 1.0, 1.0]}


def test_buckets_before_the_record_began_hold_nothing_not_zero(p):
    r = _ask(p, {"source": "moves", "kind": "ticket", "measure": "entries", "state": "open"},
             since=720.0, until=T + 480, points=6)[0]
    assert _series(r)["entries"] == [None, None, 2.0, 0.0, 1.0, 0.0]


def _readings(p):
    for at, v in ((-10, 90.0), (10, 100.0), (130, 130.0), (250, 20.0), (370, 50.0), (375, 80.0)):
        p.measurements.add("sensor/queue.main", v, at=T + at)


@pytest.mark.parametrize("agg,want", [("avg", [100.0, 130.0, 20.0, 65.0]), ("last", [100.0, 130.0, 20.0, 80.0]),
                                      ("sum", [100.0, 130.0, 20.0, 130.0]), ("count", [1.0, 1.0, 1.0, 2.0]),
                                      ("min", [100.0, 130.0, 20.0, 50.0]), ("max", [100.0, 130.0, 20.0, 80.0]),
                                      ("p50", [100.0, 130.0, 20.0, 65.0])])
def test_a_series_aggregated(p, agg, want):
    _readings(p)
    r = _ask(p, {"source": "series", "series": "sensor/queue.main", "agg": agg})[0]
    assert _series(r)["sensor/queue.main"] == want and r["unit"] == "tickets"


def test_a_counters_rate_counts_a_reset_from_zero(p):
    _readings(p)
    r = _ask(p, {"source": "series", "series": "sensor/queue.main", "agg": "last", "transform": "rate", "rate_per": "minute"})[0]
    # increases 10 (from 90), 30, 20 (a reset, from zero), 60 over 120 s buckets
    assert _series(r)["sensor/queue.main"] == pytest.approx([5.0, 15.0, 10.0, 30.0]) and r["unit"] == "tickets/min"


def test_a_gap_in_a_series_stays_a_gap(p):
    p.measurements.add("sensor/queue.main", 1.0, at=T + 10)
    p.measurements.add("sensor/queue.main", 3.0, at=T + 370)
    r = _ask(p, {"source": "series", "series": "sensor/queue.main", "agg": "avg"})[0]
    assert _series(r)["sensor/queue.main"] == [1.0, None, None, 3.0]


def test_a_series_from_its_rolled_up_tiers_is_the_same_as_from_its_readings(tmp_path):
    raw, rolled = Measurements(tmp_path), None
    (tmp_path / "r").mkdir()
    rolled = Measurements(tmp_path / "r", raw=60.0, tiers=[(60.0, 1e9)])
    rows = [("s", T + i * 7.0, float(i % 11)) for i in range(120)]
    raw.add_many(rows)
    rolled.add_many(rows)
    rolled.roll(now=T + 5000)
    a = raw.rollups("s", T, T + 840, T, 120.0, 7)
    b = rolled.rollups("s", T, T + 840, T, 120.0, 7)
    assert [(x[1], x[2], x[3], x[4]) for x in a] == [(x[1], x[2], x[3], x[4]) for x in b]


def test_events_counted_by_type_and_said_to_be_from_the_log(p):
    r = _ask(p, {"source": "events", "type": "ticket.*", "group_by": "type"})[0]
    assert _series(r) == {"ticket.note": [2.0, 0.0, 1.0, 0.0], "ticket.started": [0.0, 2.0, 0.0, 0.0],
                          "ticket.done": [0.0, 0.0, 0.0, 1.0]}
    assert r["read_log"] is True and r["unit"] == "events"


def test_events_are_bounded_and_say_so(p, monkeypatch):
    monkeypatch.setattr(sources, "EVENTS_MOST", 2)
    r = _ask(p, {"source": "events", "type": "ticket.*"})[0]
    assert r["truncated"] is True and "latest 2" in r["note"]
    assert sum(_series(r)["ticket.*"]) == 2


@pytest.mark.parametrize("transform,want", [("delta", [None, -3.0, -2.0, 0.5]), ("cumulative", [5.0, 7.0, 7.0, 7.5]),
                                            ("moving_avg", [5.0, 3.5, 1.0, 0.25])])
def test_transforms_in_a_query(p, transform, want):
    r = _ask(p, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum", "transform": transform, "window": 2})[0]
    assert _series(r)["ai_cost_usd"] == want


def test_a_rate_chooses_a_readable_unit_of_time(p):
    r = _ask(p, {"source": "moves", "kind": "ticket", "measure": "entries", "state": "open", "transform": "rate"})[0]
    assert r["unit"] == "items/min" and _series(r)["entries"] == pytest.approx([1.0, 0.0, 0.5, 0.0])


def test_at_most_twelve_groups_and_the_rest_as_other(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    q = Project(mdl.load(tmp_path))
    for i in range(15):
        for j in range(15 - i):
            q.events.add("ticket.note", item=f"ticket/{i}-{j}", data={"team": f"t{i:02}", "ai_cost_usd": 1.0}, at=T + 10)
    r = _ask(q, {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum", "group_by": "team"})[0]
    got = _series(r)
    assert r["capped"] == 3 and len(got) == 13 and list(got)[-1] == "other"
    assert got["other"][0] == 3 + 2 + 1 and got["t00"][0] == 15


@pytest.mark.parametrize("query,word", [({"source": "nope"}, "source"), ({"source": "items", "kind": "ticket"}, "field"),
                                        ({"source": "counts", "agg": "median"}, "agg"), ({"source": "counts", "wat": 1}, "wat"),
                                        ({"source": "moves", "kind": "ticket"}, "measure"),
                                        ({"source": "counts", "transform": "log"}, "transform"),
                                        ({"source": "series"}, "series"), ({"source": "counts", "bucket": "soon"}, "bucket"),
                                        ({"source": "counts", "window": 0}, "window")])
def test_a_malformed_query_is_refused_naming_what_is_wrong(p, query, word):
    with pytest.raises(BadQuery) as e:
        _ask(p, query)
    assert word in str(e.value)


@pytest.mark.parametrize("raw", ["", "!!!", base64.urlsafe_b64encode(b"[1]").decode(), "A" * (MOST_ENCODED + 1)])
def test_a_request_that_is_not_one_is_refused(p, raw):
    with pytest.raises(BadQuery):
        api(Live(p), "query", {"q": [raw]})


def test_too_many_queries_too_long_a_window_or_too_many_points_are_refused(p):
    for kw in ({"since": 1e9}, {"points": 5000}):
        with pytest.raises(BadQuery, match="since|points"):
            _ask(p, {"source": "counts"}, **kw)
    with pytest.raises(BadQuery, match="queries"):
        _ask(p, *[{"source": "counts"}] * (MOST_QUERIES + 1))


def test_one_query_that_fails_leaves_the_others_answered(p):
    got = _ask(p, {"source": "items", "kind": "nope", "field": "x"}, {"source": "items", "kind": "ticket", "field": "nope"},
               {"source": "series", "series": "sensor/none"}, {"source": "moves", "kind": "ticket", "measure": "entries", "state": "nope"},
               {"source": "counts", "kind": "ticket"})
    assert "'nope'" in got[0]["error"] and "kind" in got[0]["error"]
    assert "'nope'" in got[1]["error"] and "field" in got[1]["error"]
    assert "sensor/none" in got[2]["error"] and "state" in got[3]["error"]
    assert all("series" not in r for r in got[:4]) and "error" not in got[4]


def test_an_answer_is_kept_until_its_data_changes(p, monkeypatch):
    live, calls = Live(p), []
    real = sources.READERS["items"]
    monkeypatch.setitem(engine.READERS, "items", lambda *a: (calls.append(1), real(*a))[1])
    ask = {"q": [_q({"source": "items", "kind": "ticket", "field": "ai_cost_usd"})]}
    first = api(live, "query", ask)["results"][0]
    assert api(live, "query", ask)["results"][0] == first and len(calls) == 1
    p.events.add("ticket.note", item="ticket/a", data={"ai_cost_usd": 1.0}, at=T + 400)
    assert api(live, "query", ask)["results"][0] != first and len(calls) == 2


def test_the_fields_say_what_can_be_charted(p):
    p.measurements.add("sensor/queue.main", 1.0, at=T)
    f = api(Live(p), "query/fields", {})
    k = f["sources"]["items"]["kinds"]["ticket"]
    assert k["fields"] == [{"name": "ai_cost_usd", "unit": "usd"}] and k["states"] == ["open", "doing", "done"]
    assert k["group_by"][:2] == ["state", "kind"]
    assert f["sources"]["moves"]["kinds"]["ticket"]["states"] == ["open", "doing", "done"]
    assert "ticket" in f["sources"]["counts"]["kinds"]
    assert {"name": "sensor/queue.main", "unit": "tickets"} in f["sources"]["series"]["series"]
    assert "ticket.done" in f["sources"]["events"]["types"]
    assert "p99" in f["aggregations"] and "moving_avg" in f["transforms"]


def test_a_public_read_only_name_reads_but_cannot_post(tmp_path):
    name = "open.example.org"
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL) + f"\nweb:\n  names: [{name}]\n  open: read\n")
    q = Project(mdl.load(tmp_path))
    q.events.add("ticket.note", item="ticket/a", data={"ai_cost_usd": 1.0}, at=T + 10)
    before = q.events.count()
    server, url = serve(q, free_port())

    def call(path, data=None):
        req = urllib.request.Request(url + path, data=data, method="POST" if data is not None else "GET", headers={"Host": name})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    try:
        code, body = call("/api/query?q=" + _q({"source": "counts", "kind": "ticket"}))
        assert code == 200 and json.loads(body)["results"][0]["series"]
        assert call("/api/query/fields")[0] == 200
        code, body = call("/api/query?q=!!!")
        assert code == 400 and b"base64url" in body
        assert call("/api/query?q=" + _q({"source": "counts"}), data=b"{}")[0] in (403, 404)
        assert q.events.count() == before
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.serial
def test_a_factory_sized_record_answers_each_source_within_100_ms_without_the_log(tmp_path, monkeypatch):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    q = Project(mdl.load(tmp_path))
    r, now = random.Random(2), T + 7 * 86400
    q.events.add_many([{"id": f"e{i}", "at": T + i * 6.0, "type": r.choice(("ticket.note", "ticket.started", "ticket.done")),
                        "item": f"ticket/{r.randrange(7000)}", "data": {"ai_cost_usd": 0.1}} for i in range(100_000)], new=True)
    q.measurements.add_many([("sensor/queue.main", T + i * 30.0, float(i % 50)) for i in range(20_000)])
    live = Live(q)
    asks = [{"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "sum", "transform": "rate", "group_by": "state"},
            {"source": "moves", "kind": "ticket", "measure": "entries", "state": "done", "transform": "rate"},
            {"source": "moves", "kind": "ticket", "measure": "time_in_state", "agg": "p90", "group_by": "state"},
            {"source": "counts", "kind": "ticket"},
            {"source": "series", "series": "sensor/queue.main", "agg": "avg"}]
    api(live, "query", {"q": [_q(asks[0], since=86400.0, until=now, points=120)]})      # the index caught up

    def no(*a, **k):
        raise AssertionError("a chart read the event log")
    monkeypatch.setattr(q.events, "_scan", no)
    monkeypatch.setattr(q.events, "of_items", no)
    for a in asks:
        best = 9.0
        for _ in range(3):
            engine._kept(live).got.clear()
            t = time.perf_counter()
            got = api(live, "query", {"q": [_q(a, since=86400.0, until=now, points=120)]})["results"][0]
            best = min(best, time.perf_counter() - t)
        assert "error" not in got and got["read_log"] is False
        assert best < 0.100, (a, best)
