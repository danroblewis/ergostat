"""A category's spread for a box plot (ergostat/query/spread.py), over values worked out by hand."""

from __future__ import annotations

import pytest

from ergostat.query import spread
from tests.test_query_engine import T, _ask, _record

COST = {"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "none", "x": {"type": "category", "by": "state"}}


@pytest.fixture
def p(tmp_path):
    q = _record(tmp_path)
    for item, at, cost in (("d", 150, 1.0), ("e", 160, 2.0), ("f", 170, 3.0), ("g", 180, 100.0)):
        q.events.add("ticket.started", item=f"ticket/{item}", data={"ai_cost_usd": cost}, at=T + at)
    return q


def test_quartiles_whiskers_and_outliers_by_hand():
    b = spread.box([100.0, 1.0, 3.0, 2.0, 4.0])
    assert (b["q1"], b["median"], b["q3"]) == (2.0, 3.0, 4.0)  # fences at 2 - 3 = -1 and 4 + 3 = 7
    assert (b["lo"], b["hi"], b["outliers"], b["outliers_more"]) == (1.0, 4.0, [100.0], 0)
    assert (b["min"], b["max"], b["n"]) == (1.0, 100.0, 5)
    assert b["p5"] == pytest.approx(1.2) and b["p95"] == pytest.approx(80.8)


def test_the_answer_is_bounded_and_keeps_the_extremes():
    values = [float(i) for i in range(10_001)] + [1e6] * 100
    b = spread.box(values)
    assert b["median"] == pytest.approx(sorted(values)[len(values) // 2])
    assert len(b["outliers"]) == spread.MOST_OUTLIERS and b["outliers_more"] == 100 - spread.MOST_OUTLIERS
    s = spread.sample(sorted(values))
    assert len(s) == spread.MOST_SAMPLE and s[0] == 0.0 and s[-1] == 1e6


def test_each_category_answers_with_its_items_spread_in_state_order(p):
    r = _ask(p, COST)[0]
    assert "error" not in r and r["read_log"] is False
    assert r["x"]["type"] == "category" and r["x"]["distribution"] is True and r["unit"] == "usd"
    by = {s["name"]: s for s in r["series"]}
    assert [s["name"] for s in r["series"]] == ["doing", "done"]
    b = by["doing"]["box"]  # b 4, d 1, e 2, f 3, g 100
    assert (b["n"], b["q1"], b["median"], b["q3"], b["lo"], b["hi"], b["outliers"]) == (5, 2.0, 3.0, 4.0, 1.0, 4.0, [100.0])
    assert by["doing"]["values"] == [1.0, 2.0, 3.0, 4.0, 100.0]
    assert by["done"]["box"]["median"] == 3.5                      # a: its costs 1, 2 and 0.5 add up


def test_it_reads_no_event_log(p, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the event log was read")

    monkeypatch.setattr(p.events, "read", refuse, raising=False)
    assert "error" not in _ask(p, COST)[0]


@pytest.mark.parametrize(
    "query,word",
    [
        ({"source": "counts", "kind": "ticket", "agg": "none", "x": {"type": "category", "by": "state"}}, "numeric field of items"),
        ({"source": "items", "kind": "ticket", "field": "ai_cost_usd", "agg": "none"}, "only for an x of type field"),
    ],
)
def test_what_has_no_spread_is_refused_in_words(p, query, word):
    assert word in _ask(p, query)[0]["error"]
