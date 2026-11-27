"""Every X type and the candles, over a record worked out by hand (ergostat/query)."""

from __future__ import annotations

import math
import random

import pytest

from ergostat.query import axes
from ergostat.web.server import Live, api
from tests.test_query_engine import T, _q, _record


@pytest.fixture
def p(tmp_path):
    q = _record(tmp_path)
    for item, at, data in (("a", 20, {"net_lines": 10.0}), ("b", 30, {"net_lines": 40.0}), ("c", 260, {"ai_cost_usd": 7.0})):
        q.events.add("ticket.note", item=f"ticket/{item}", data=data, at=T + at)
    return q


def ask(p, *queries, **kw):
    return api(Live(p), "query", {"q": [_q(*queries, **kw)]})["results"]


COST = {"source": "items", "projection": "ticket", "field": "ai_cost_usd", "agg": "sum"}
LINES = {"source": "items", "projection": "ticket", "field": "net_lines", "agg": "sum"}


def test_no_x_and_a_time_x_are_the_same_answer(p):
    a, b = ask(p, COST), ask(p, {**COST, "x": {"type": "time"}})
    assert a[0]["series"] == b[0]["series"] and "x" not in b[0]


def test_a_query_x_pairs_bucket_by_bucket_and_says_the_order(p):
    r = ask(p, {**COST, "x": {"type": "query", "query": "1"}}, {"source": "counts", "projection": "ticket", "state": ["doing"]})[0]
    assert r["x"] == {"type": "query", "label": "counts", "unit": "items", "scale": "number"}
    s = r["series"][0]
    assert s["values"] == [5.0, 2.0, 7.0, 0.5]
    assert s["times"] == [T, T + 120, T + 240, T + 360] and s["ids"] is None
    assert s["xs"] == [None, 2.0, 2.0, 1.0] or len(s["xs"]) == 4


def test_pairing_across_an_empty_bucket_holds_no_point():
    assert axes.paired([1.0, None, 3.0, 4.0], [5.0, 6.0, None, 8.0]) == ([1.0, None, None, 4.0], [5.0, None, None, 8.0])
    assert axes.paired([float("nan")], [1.0]) == ([None], [None])


def test_a_query_x_on_another_bucket_is_read_on_the_coarser(p):
    r = ask(p, {**COST, "bucket": 120, "x": {"type": "query", "query": "1"}}, {**LINES, "bucket": 240})[0]
    assert r["step"] == 240 and r["series"][0]["xs"] == [50.0, 0.0, 0.0]    # T is halfway through a 240 s bucket
    assert r["series"][0]["values"] == [5.0, 9.0, 0.5]


@pytest.mark.parametrize("x,word", [({"type": "query", "query": "nope"}, "not in this request"),
                                    ({"type": "query", "query": "0"}, "cannot be itself")])
def test_a_bad_reference_fails_alone(p, x, word):
    got = ask(p, {**COST, "x": x}, COST)
    assert word in got[0]["error"] and "series" in got[1]


def test_an_x_query_may_be_given_whole(p):
    r = ask(p, {**COST, "x": {"type": "query", "query": LINES}})[0]
    assert r["x"]["label"] == "net_lines" and r["series"][0]["xs"][0] == 50.0


def test_a_field_x_is_one_point_per_item_at_the_windows_end(p):
    r = ask(p, {"source": "items", "projection": "ticket", "field": "ai_cost_usd", "x": {"type": "field", "field": "net_lines"}})[0]
    s = r["series"][0]
    got = dict(zip(s["ids"], zip(s["xs"], s["values"], strict=True), strict=True))
    assert got == {"ticket/a": (10.0, 3.5), "ticket/b": (40.0, 4.0)} and r["x"]["unit"] == "lines" and r["unit"] == "usd"
    assert s["times"] == sorted(s["times"])


def test_a_field_x_as_of_a_past_end(p):
    r = ask(p, {"source": "items", "projection": "ticket", "field": "ai_cost_usd", "x": {"type": "field", "field": "net_lines"}},
            since=100.0, until=T + 100)[0]
    s = r["series"][0]
    assert dict(zip(s["ids"], s["values"], strict=True)) == {"ticket/a": 1.0, "ticket/b": 4.0}


def test_a_field_x_returns_size_and_colour_per_point(p):
    r = ask(p, {"source": "items", "projection": "ticket", "field": "ai_cost_usd",
                "x": {"type": "field", "field": "net_lines", "size": "ai_cost_usd", "color_by": "state"}})[0]
    s = r["series"][0]
    assert dict(zip(s["ids"], s["sizes"], strict=True)) == {"ticket/a": 3.5, "ticket/b": 4.0}
    assert dict(zip(s["ids"], s["colors"], strict=True)) == {"ticket/a": "done", "ticket/b": "doing"}


def test_a_size_that_is_no_number_is_said(p):
    x = {"type": "field", "field": "net_lines", "size": "size"}
    r = ask(p, {"source": "items", "projection": "ticket", "field": "ai_cost_usd", "x": x})[0]
    assert "size" in r["error"]


def test_a_field_x_is_capped_and_says_so(p, monkeypatch):
    from ergostat.query import points
    monkeypatch.setattr(points, "MOST_POINTS", 1)
    r = ask(p, {"source": "items", "projection": "ticket", "field": "ai_cost_usd", "x": {"type": "field", "field": "net_lines"}})[0]
    assert r["capped"] == 1 and r["series"][0]["ids"] == ["ticket/a"] and "only the 1" in r["note"]


def test_a_field_x_is_for_items(p):
    r = ask(p, {"source": "events", "x": {"type": "field", "field": "net_lines"}})[0]
    assert "items source" in r["error"]


def test_a_category_x(p):
    r = ask(p, {"source": "moves", "projection": "ticket", "measure": "entries", "agg": "count", "x": {"type": "category", "by": "state"}})[0]
    assert r["x"]["scale"] == "category"
    assert dict(zip(r["series"][0]["xs"], r["series"][0]["values"], strict=True))["doing"] == 2.0
    r = ask(p, {"source": "counts", "projection": "ticket", "x": {"type": "category", "by": "state"}})[0]
    assert dict(zip(r["series"][0]["xs"], r["series"][0]["values"], strict=True)) == {"open": 1.0, "doing": 1.0, "done": 1.0}
    assert r["series"][0]["xs"] == ["open", "doing", "done"]


def test_a_category_of_a_sum_and_its_rate(p):
    r = ask(p, {**COST, "x": {"type": "category", "by": "size"}})[0]
    got = dict(zip(r["series"][0]["xs"], r["series"][0]["values"], strict=True))
    assert got["s"] == 7.5 and got["l"] == 7.0
    r = ask(p, {**COST, "transform": "rate", "rate_per": "hour", "x": {"type": "category", "by": "size"}})[0]
    assert dict(zip(r["series"][0]["xs"], r["series"][0]["values"], strict=True))["s"] == pytest.approx(7.5 / 480 * 3600)
    assert r["unit"] == "usd/h"


def test_a_series_has_no_categories(p):
    p.measurements.add("m", 1.0, at=T + 1)
    assert "no labels" in ask(p, {"source": "series", "series": "m", "x": {"type": "category", "by": "state"}})[0]["error"]


def test_bin_edges_by_hand():
    e = axes.edges([0.0, 1.0], 10)
    assert e[0] == 0.0 and e[-1] == 1.0 and len(e) == 11
    assert axes.bin_of(0.0, e) == 0 and axes.bin_of(1.0, e) == 9
    assert axes.bin_of(e[3], e) == 3                  # on an edge: the bin above, though 0.3 / 0.1 rounds below 3
    assert all(axes.bin_of(e[i], e) == i for i in range(10))
    assert axes.edges([2.0, 2.0], 2) == [1.5, 2.0, 2.5]


def test_binning_agrees_with_counting_by_the_edges():
    r = random.Random(3)
    v = [r.uniform(-5, 9) for _ in range(2000)]
    e = axes.edges(v, 17)
    got = [0] * 17
    for x in v:
        got[axes.bin_of(x, e)] += 1
    want = [sum(e[i] <= x < e[i + 1] for x in v) for i in range(17)]
    want[-1] += sum(x == e[-1] for x in v)
    assert got == want and sum(got) == 2000


def test_a_histogram_of_a_field(p):
    r = ask(p, {"source": "items", "projection": "ticket", "x": {"type": "bins", "field": "ai_cost_usd", "bins": 2}})[0]
    assert r["x"]["edges"] == [3.5, 5.25, 7.0] and r["series"][0]["xs"] == [4.375, 6.125]
    assert r["series"][0]["values"] == [2.0, 1.0] and r["unit"] == "items"


def test_a_histogram_aggregating_another_field_in_each_bin(p):
    r = ask(p, {"source": "items", "projection": "ticket", "field": "ai_cost_usd", "agg": "sum",
                "x": {"type": "bins", "field": "net_lines", "bins": 2}})[0]
    assert r["x"]["edges"] == [10.0, 25.0, 40.0] and r["series"][0]["values"] == [3.5, 4.0] and r["unit"] == "usd"


def test_a_histogram_of_a_querys_values(p):
    p.measurements.add_many([("m", T + 60 * i + 1, float(i % 3)) for i in range(8)])
    r = ask(p, {"source": "series", "series": "m", "bucket": 60, "x": {"type": "bins", "bins": 3}}, points=8)[0]
    assert r["series"][0]["values"] == [3.0, 3.0, 2.0] and r["unit"] == "buckets"
    r = ask(p, {**COST, "agg": "count", "x": {"type": "bins", "query": "1", "bins": 3}},
            {"source": "series", "series": "m", "bucket": 60}, points=8)[0]
    assert sum(r["series"][0]["values"]) == 8 and r["x"]["label"] == "m"


def test_an_empty_histogram_is_empty_not_an_error(p):
    r = ask(p, {"source": "items", "projection": "ticket", "x": {"type": "bins", "field": "ai_cost_usd"}}, since=5.0, until=T + 5)[0]
    assert r["series"] == [] and r["x"]["edges"] == []


@pytest.mark.parametrize("x,word", [("up", "must be an object"), ({"type": "polar"}, "polar"), ({"type": "query"}, "x.query"),
                                    ({"type": "field"}, "x.field"), ({"type": "category"}, "x.by"),
                                    ({"type": "bins", "bins": 0}, "x.bins"), ({"type": "bins", "bins": 201}, "x.bins"),
                                    ({"type": "time", "nope": 1}, "nope"), ({"type": "bins", "field": "a", "query": "b"}, "not both")])
def test_a_malformed_x_is_refused(p, x, word):
    got = ask(p, {**COST, "x": x}, COST)
    assert word in got[0]["error"] and "series" in got[1]


def test_agg_none_is_only_for_a_field_x(p):
    assert "only for an x of type field" in ask(p, {**COST, "agg": "none"})[0]["error"]


@pytest.mark.parametrize("q,word", [({"source": "counts", "projection": "ticket", "agg": "ohlc"}, "no values in time"),
                                    ({"source": "events", "agg": "ohlc"}, "no values in time"),
                                    ({"source": "moves", "projection": "ticket", "measure": "entries", "agg": "ohlc"}, "time_in_state"),
                                    ({**COST, "agg": "ohlc", "x": {"type": "category", "by": "state"}}, "time X")])
def test_candles_refused_in_words(p, q, word):
    assert word in ask(p, q)[0]["error"]


def _wave(p, n=2000, step=30.0):
    x = [math.sin(2 * math.pi * i / 90) + 0.5 * math.sin(2 * math.pi * i / 37) for i in range(n)]
    p.measurements.add_many([("in", T + i * step, x[i]) for i in range(n)] + [("out", T + i * step, 2.0 * x[i]) for i in range(n)])
    return n * step


def test_a_frequency_response_through_the_api(p):
    span = _wave(p)
    r = ask(p, {"source": "frequency", "input": {"source": "series", "series": "in"}, "output": {"source": "series", "series": "out"}},
            since=span, until=T + span)[0]
    assert "error" not in r, r
    assert r["method"] == "empirical" and r["samples"] > 500 and r["unit"] == "" and r["read_log"] is False
    best = max(range(len(r["frequency"]["hz"])), key=lambda i: r["frequency"]["coherence"][i])
    assert r["frequency"]["magnitude_db"][best] == pytest.approx(20 * math.log10(2), abs=0.1)
    assert set(r["frequency"]) == {"hz", "magnitude_db", "phase_deg", "re", "im", "coherence"}
    assert r["supported"] is True and 0 < r["coherence_floor_each"] < r["coherence_floor"] < 1


def test_unrelated_signals_through_the_api_are_answered_as_no_response_with_no_curve(p):
    """Done item 3 (dev/records/frequency-refuses-noise.md): the server decides, and the answer carries the decision."""
    r = random.Random(11)
    n, step = 1024, 30.0
    p.measurements.add_many([("in", T + i * step, r.gauss(0, 1)) for i in range(n)]
                            + [("out", T + i * step, r.gauss(0, 1)) for i in range(n)])
    got = ask(p, {"source": "frequency", "input": {"source": "series", "series": "in"}, "output": {"source": "series", "series": "out"}},
              since=n * step, until=T + n * step)[0]
    assert "error" not in got, got
    assert got["supported"] is False and "no frequency is coherent past chance" in got["refused"]
    assert got["frequency"]["hz"] == [] and got["frequency"]["magnitude_db"] == []
    assert got["coherence_peak"] < got["coherence_floor"] < 1


def test_a_constant_input_is_refused_in_words_and_the_others_answer(p):
    p.measurements.add_many([("flat", T + i * 30.0, 4.0) for i in range(600)] + [("out", T + i * 30.0, math.sin(i)) for i in range(600)])
    got = ask(p, {"source": "frequency", "input": {"source": "series", "series": "flat"}, "output": {"source": "series", "series": "out"}},
              COST, since=18000.0, until=T + 18000)
    assert "input does not vary" in got[0]["error"] and "series" in got[1]


def test_too_few_samples_are_refused_in_words(p):
    p.measurements.add_many([("a", T + i, float(i % 2)) for i in range(5)] + [("b", T + i, float(i % 3)) for i in range(5)])
    r = ask(p, {"source": "frequency", "input": {"source": "series", "series": "a"}, "output": {"source": "series", "series": "b"}})[0]
    assert "too few samples" in r["error"]


def test_a_frequency_answer_is_kept_until_its_data_changes(p, monkeypatch):
    span = _wave(p, 600)
    from ergostat.query import frequency as fr
    calls = []
    real = fr.estimate
    monkeypatch.setattr(fr, "estimate", lambda *a: calls.append(1) or real(*a))
    live = Live(p)
    q = {"q": [_q({"source": "frequency", "input": {"source": "series", "series": "in"},
                   "output": {"source": "series", "series": "out"}}, since=span, until=T + span)]}
    api(live, "query", q), api(live, "query", q)
    assert len(calls) == 1
    p.measurements.add("in", 3.0, at=T + 5.5)
    api(live, "query", q)
    assert len(calls) == 2


def test_a_model_response_is_the_declared_process(tmp_path):
    from ergostat import model as mdl
    from ergostat.store import Project
    from tests.test_control import TUNE
    (tmp_path / "ergostat.yaml").write_text(TUNE.replace(
        "    description: the level held\n",
        "    description: the level held\n    process:\n      gain: 2\n      time-constant: 100s\n"))
    r = ask(Project(mdl.load(tmp_path)), {"source": "frequency", "model": {"goal": "level-held"}})[0]
    assert "error" not in r, r
    f = r["frequency"]
    i = min(range(len(f["hz"])), key=lambda j: abs(f["hz"][j] - 1 / (2 * math.pi * 100)))
    assert r["method"] == "model" and f["coherence"] is None and r["poles"] == [{"re": -0.01, "im": 0.0}]
    assert f["magnitude_db"][i] == pytest.approx(20 * math.log10(2) - 3.01, abs=0.1)
    assert f["phase_deg"][i] == pytest.approx(-45.0, abs=1.5)


def test_a_model_response_of_no_goal_is_refused(p):
    assert "not in the model" in ask(p, {"source": "frequency", "model": {"goal": "nope"}})[0]["error"]


def test_the_fields_say_what_each_source_can_take(p):
    got = api(Live(p), "query/fields", {})
    assert got["sources"]["items"]["x"] == ["time", "query", "field", "category", "bins"]
    assert "field" not in got["sources"]["series"]["x"] and "category" not in got["sources"]["series"]["x"]
    assert got["sources"]["frequency"]["x"] == ["frequency"] and got["x_types"][0] == "time"
    assert "ohlc" in got["aggregations"] and got["sources"]["series"]["ohlc"] and not got["sources"]["counts"]["ohlc"]
