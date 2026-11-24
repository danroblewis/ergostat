"""Acceptance (chart-result-shapes), the server's half: every answer is one of five typed frames with the envelope
(ergostat/query/frames.py), a data source may answer with a typed frame (ergostat/datasources/_frames.py), and a PromQL
and a SQL answer of one shape are the same answer. The browser's half is tests/test_result_shapes_page.py.

``samples`` builds one answer of each shape the charts are judged against, from the real engine and the real frame
reader; the browser tests draw them."""

from __future__ import annotations

import json
import types

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.datasources import _frames
from ergostat.query import frames
from ergostat.query.buckets import grid
from ergostat.store import Project
from tests import test_data_sources as ds
from tests.test_data_sources import T as PT
from tests.test_data_sources import ask as ask_source
from tests.test_data_sources import project
from tests.test_query_axes import COST, T, _wave, ask
from tests.test_query_engine import _record

ITEMS = {"source": "items", "kind": "ticket"}
prom = ds.prom                     # (the stub Prometheus, a fixture)
BOX = {"q1": 2, "median": 3, "q3": 5, "lo": 1, "hi": 9, "outliers": [], "n": 9}


def _p(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    q = _record(tmp_path)
    for item, at, data in (("a", 20, {"net_lines": 10.0}), ("b", 30, {"net_lines": 40.0}), ("c", 260, {"ai_cost_usd": 7.0})):
        q.events.add("ticket.note", item=f"ticket/{item}", data=data, at=T + at)
    return q


def _model(tmp_path):
    from tests.test_control import TUNE
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(TUNE.replace(
        "    description: the level held\n", "    description: the level held\n    process:\n      gain: 2\n      time-constant: 100s\n"))
    return Project(mdl.load(tmp_path))


def from_source(frame: dict) -> dict:
    """A typed frame as a data source's answer comes to the page: read, checked and given its envelope."""
    g = grid(T, T + 480, 4)
    asked = types.SimpleNamespace(source="sql", text="SELECT")
    return {"id": "a", **frames.framed(_frames.answer(frame, g, datasources.MOST_SERIES), asked)}


def samples(tmp_path) -> dict[str, dict]:
    """One answer of each shape, by name: ergostat's own through ``GET /api/query``, a data source's through its reader."""
    p = _p(tmp_path / "p")
    one = lambda *q, **kw: {**ask(p, *q, **kw)[0], "id": "a"}  # noqa: E731
    out = {
        "series": one(COST),
        "two-signals": one({**COST, "x": {"type": "query", "query": "1"}}, {"source": "counts", "kind": "ticket", "state": ["doing"]}),
        "candles": one({**ITEMS, "field": "ai_cost_usd", "agg": "ohlc"}),
        "table": one({"source": "counts", "kind": "ticket", "x": {"type": "category", "by": "state"}}),
        "table-numeric": one({**ITEMS, "field": "ai_cost_usd", "agg": "sum", "x": {"type": "bins", "field": "net_lines", "bins": 2}}),
        "points": one({**ITEMS, "field": "ai_cost_usd", "x": {"type": "field", "field": "net_lines"}}),
        "bins": one({**ITEMS, "x": {"type": "bins", "field": "ai_cost_usd", "bins": 2}}),
        "samples": one({**ITEMS, "field": "ai_cost_usd", "agg": "none", "x": {"type": "category", "by": "state"}}),
        "table-one-row": from_source({"shape": "table", "dims": [{"name": "kind", "type": "string"}],
                                      "measures": [{"name": "open", "unit": "items"}], "rows": [["ticket", 3]]}),
        "table-two-measures": from_source({"shape": "table", "dims": [{"name": "kind", "type": "string"}],
                                           "measures": [{"name": "arrived", "unit": "items"}, {"name": "left", "unit": "items"}],
                                           "rows": [["ticket", 3, 2], ["note", 5, 5], ["page", 1, 0]]}),
        "table-two-dims": from_source({"shape": "table", "dims": [{"name": "kind", "type": "string"}, {"name": "state", "type": "string"}],
                                       "measures": [{"name": "n", "unit": "items"}],
                                       "rows": [["ticket", "open", 3], ["ticket", "done", 2], ["note", "open", 1]]}),
        "points-in-time": from_source({"shape": "points", "x": {"name": "arrivals", "unit": "/h", "values": [1, 2, 3, 2]},
                                       "y": {"name": "backlog", "unit": "items", "values": [4, 6, 5, 3]},
                                       "t": [T, T + 120, T + 240, T + 360], "order": "time"}),
        "quartiles": {"id": "a", "shape": "distribution", "form": "quartiles", "unit": "s",
                      "x": {"type": "category", "label": "state", "unit": "", "scale": "category", "distribution": True},
                      "series": [{"name": "open", "xs": ["open"], "values": [3], "box": BOX}]},
        "survival": {"id": "a", "shape": "distribution", "form": "survival", "unit": "s", "series": []},
        "over-time": {"id": "a", "shape": "distribution", "form": "over_time", "unit": "s", "series": []},
    }
    span = _wave(p)
    out["frequency"] = one({"source": "frequency", "input": {"source": "series", "series": "in"},
                            "output": {"source": "series", "series": "out"}}, since=span, until=T + span)
    out["model"] = {**ask(_model(tmp_path / "m"), {"source": "frequency", "model": {"goal": "level-held"}})[0], "id": "a"}
    return json.loads(json.dumps(out))


FRAMES = {
    "series": {"shape": "series"},
    "two-signals": {"shape": "series", "roles": ["input", "output"]},
    "candles": {"shape": "series", "roles": ["open", "high", "low", "close"]},
    "points": {"shape": "points"},
    "bins": {"shape": "distribution", "form": "bins"},
    "samples": {"shape": "distribution", "form": "samples"},
    "frequency": {"shape": "response", "has": ["frequency"]},
    "model": {"shape": "response", "has": ["frequency", "system"]},
}


def test_each_of_ergostats_own_answers_is_one_of_five_shapes(tmp_path):
    got = samples(tmp_path)
    for name, frame in FRAMES.items():
        assert {k: got[name].get(k) for k in frame} == frame, name
        assert {k for k in frames.FRAME_KEYS if k in got[name]} == set(frame), name
    t = got["table"]
    assert t["shape"] == "table" and t["dims"] == [{"name": "state", "type": "string"}] and t["measures"][0]["unit"] == "items"
    assert t["rows"] == [[x, v] for x, v in zip(t["series"][0]["xs"], t["series"][0]["values"], strict=True)]
    n = got["table-numeric"]
    assert n["dims"] == [{"name": "net_lines", "type": "number", "edges": [10.0, 25.0, 40.0]}] and n["rows"] == [[17.5, 3.5], [32.5, 4.0]]
    assert {r["shape"] for r in got.values()} == set(frames.SHAPES)


def test_every_answer_carries_its_envelope(tmp_path):
    got = samples(tmp_path)
    assert got["series"]["meta"] == {"source": "items", "query": None, "provenance": "observed", "verdict": {"level": "ok", "reasons": []}}
    assert got["model"]["meta"]["provenance"] == "declared" and got["frequency"]["meta"]["provenance"] == "derived"
    assert got["table-one-row"]["meta"]["query"] == "SELECT"
    p = _p(tmp_path / "e")
    [bad] = ask(p, {**COST, "x": {"type": "query", "query": "nope"}})
    assert bad["meta"]["verdict"] == {"level": "refuse", "reasons": [{"code": "unanswerable", "says": bad["error"]}]}
    assert "shape" not in bad                                    # a refused answer holds nothing to draw


@pytest.mark.parametrize("frame,word", [
    ({"shape": "graph"}, "not 'graph'"),
    ({"shape": "table", "dims": [{"name": "k", "type": "colour"}], "measures": [{"name": "n"}], "rows": []}, "typed"),
    ({"shape": "table", "dims": [{"name": "k", "type": "string"}], "measures": [{"name": "n"}], "rows": [["a"]]}, "a row holds"),
    ({"shape": "table", "dims": [{"name": "k", "type": "string"}], "measures": [{"name": "n"}], "rows": [["a", 1], ["a", 2]]}, "share"),
    ({"shape": "table", "dims": [{"name": "k", "type": "string"}], "measures": [{"name": "n"}], "rows": [["a", "x"]]}, "not a number"),
    ({"shape": "points", "x": {"values": [1, 2]}, "y": {"values": [1]}}, "one length"),
    ({"shape": "series", "time": [1, 2], "series": [{"key": "a", "values": [1]}]}, "1 values for 2 times"),
])
def test_a_frame_that_is_not_what_it_says_is_refused(frame, word):
    with pytest.raises(_frames.Bad, match=word):
        _frames.answer(frame, grid(T, T + 480, 4), 50)


def test_a_frame_over_its_bound_is_a_limit(monkeypatch):
    monkeypatch.setattr(_frames, "MOST_ROWS", 2)
    with pytest.raises(_frames.TooMany, match="3 entries, more than the 2"):
        _frames.answer({"shape": "table", "dims": [{"name": "k", "type": "number"}], "measures": [{"name": "n"}],
                        "rows": [[1, 1], [2, 2], [3, 3]]}, grid(T, T + 480, 4), 50)


def test_a_non_finite_value_is_no_value():
    frame = {"shape": "points", "x": {"values": [1, float("nan")]}, "y": {"values": [float("inf"), 2]}}
    got = _frames.answer(frame, grid(T, T + 480, 4), 50)
    assert got["series"][0]["xs"] == [1.0, None] and got["series"][0]["values"] == [None, 2.0]


def _values(times: list, j: int) -> list:
    return [10 * j + i for i in range(len(times))]


def fake_sql(src, text, w):
    """A SQL source over a table of (t, job, up): it answers in rows, made a series per job, as a SQL type would."""
    times = [w.start + i * w.step for i in range(w.points)]
    rows = [(t, job, v) for j, job in enumerate(("a", "b")) for t, v in zip(times, _values(times, j), strict=True)]
    keys = list(dict.fromkeys(f'up{{job="{job}"}}' for _, job, _ in rows))
    return {"shape": "series", "time": times,
            "series": [{"key": k, "values": [v for _, job, v in rows if f'up{{job="{job}"}}' == k]} for k in keys]}


FAKE_SQL = "fake-sql"   # a type name of the test's own: the real ergostat/datasources/sql.py is type ``sql``


@pytest.fixture
def sql():
    datasources.types()     # the package's own types found first, so none of them is registered over the fake later
    datasources.register(types.SimpleNamespace(TYPE=FAKE_SQL, KEYS={"database"}, LANGUAGE="SQL", query=fake_sql))
    yield
    datasources.unregister(FAKE_SQL)


def same_shape_answers(tmp_path, prom_url: str) -> tuple[dict, dict]:
    """``sum by (job) (up)`` asked of a (stub) Prometheus, and its SQL equal asked of a SQL source, over one window."""
    p = project(tmp_path, f"prom: {{type: prometheus, url: '{prom_url}'}}\nwarehouse: {{type: {FAKE_SQL}, database: metrics}}")
    a = ask_source(p, {"source": "prom", "text": "sum by (job) (up)"}, until=PT + 480)[0]
    b = ask_source(p, {"source": "warehouse", "text": "SELECT t, job, up FROM up_by_job"}, until=PT + 480)[0]
    return a, b


def test_a_promql_and_a_sql_answer_of_one_shape_are_the_same_answer(tmp_path, prom, sql):     # done 3, the server's half
    a, b = same_shape_answers(tmp_path, prom)
    assert "error" not in a and "error" not in b, (a, b)
    assert a["shape"] == b["shape"] == "series" and a["series"][0]["values"] == [0.0, 1.0, 2.0, 3.0]
    assert {k: v for k, v in a.items() if k != "meta"} == {k: v for k, v in b.items() if k != "meta"}
    assert (a["meta"]["source"], b["meta"]["source"]) == ("prom", "warehouse")


def test_two_signals_from_a_source_are_drawn_one_against_the_other():
    got = _frames.answer({"shape": "series", "time": [T, T + 120], "series": [
        {"key": "load", "role": "input", "unit": "/s", "values": [1, 2]},
        {"key": "latency", "role": "output", "unit": "s", "values": [5, 7]}]}, grid(T, T + 480, 4), 50)
    assert got["roles"] == ["input", "output"] and got["x"]["label"] == "load" and got["unit"] == "s"
    assert got["series"][0]["xs"][:2] == [1.0, 2.0] and got["series"][0]["values"][:2] == [5.0, 7.0]
    assert frames.describe(got)["roles"] == ["input", "output"]
