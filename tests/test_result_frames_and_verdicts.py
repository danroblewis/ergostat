"""Acceptance (result-frames-and-verdicts), the server's half: the sixth shape (graph), the envelope with its verdict
(each reason from a closed list, with its fix), roles on fields from closed lists, a Prometheus histogram (``_bucket``
by ``le``) as a distribution of bins over time (chart 16), and the guardrails this item answers for, each tried. The
page's half (the verdict in the panel, the latency heatmap) is tests/test_result_frames_page.py.

The hand-worked record, four buckets at the four times of the grid (T, T + 120, T + 240, T + 360), cumulative:

    le       0.1  0.5  1   +Inf      in each bucket        above 1
    T        2    5    6   6         2  3  1               0
    T + 120  0    4    9   10        0  4  5               1
    T + 240  3    -    7   8         (le=0.5 missing: a gap, not a zero)
    T + 360  1    1    1   3         1  0  0               2
                                     ------- over the window
                                     3  7  6               3, of 19
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ergostat.datasources import _frames, _lint
from ergostat.query import frames, verdicts
from ergostat.query.buckets import grid
from tests.test_data_sources import T, ask, project

G = grid(T, T + 480, 4)
TIMES = [T, T + 120, T + 240, T + 360]
CUMULATIVE = {"0.1": [2, 0, 3, 1], "0.5": [5, 4, None, 1], "1": [6, 9, 7, 1], "+Inf": [6, 10, 8, 3]}


def buckets(cum=CUMULATIVE, times=TIMES, **labels) -> dict:
    return {"shape": "distribution", "name": "wait_seconds", "buckets": [
        {"labels": {"__name__": "wait_seconds_bucket", "le": le, **labels}, "time": times, "values": v} for le, v in cum.items()]}


def test_a_histograms_buckets_are_bins_over_time_on_the_hand_worked_record():
    got = _frames.answer(buckets(), G, 50)
    assert (got["shape"], got["form"]) == ("distribution", "bins")
    assert got["x"]["edges"] == [0.0, 0.1, 0.5, 1.0] and got["x"]["type"] == "bins"
    assert got["over_time"] == {"times": TIMES, "counts": [[2, 3, 1], [0, 4, 5], None, [1, 0, 0]]}
    assert got["series"] == [{"name": "wait_seconds", "xs": [0.05, 0.3, 0.75], "values": [3, 7, 6]}]
    assert got["warnings"] == [("open-top-bucket", "3 of 19 are above the highest bound (le=1), and are not drawn")]
    framed = frames.framed(got, None)
    assert framed["meta"]["verdict"] == {"level": "warn", "reasons": [{
        "code": "open-top-bucket", "says": "3 of 19 are above the highest bound (le=1), and are not drawn",
        "fix": "add a bucket above the highest bound, so those values are placed"}]}
    assert framed["meta"]["n"] == 3 and "warnings" not in framed


def test_buckets_with_no_inf_say_what_is_not_known_and_none_above_say_nothing():
    no_inf = {k: v for k, v in CUMULATIVE.items() if k != "+Inf"}
    assert _frames.answer(buckets(no_inf), G, 50)["warnings"] == [
        ("open-top-bucket", "the buckets have no +Inf, so what lies above le=1 is not known")]
    closed = {**CUMULATIVE, "+Inf": CUMULATIVE["1"]}
    assert _frames.answer(buckets(closed), G, 50)["warnings"] == []


@pytest.mark.parametrize("cum,code,words", [
    ({**CUMULATIVE, "1": [6, 3, 7, 1]}, "not-cumulative", "the count up to le=1 (3) is below the count up to le=0.5 (4)"),
    ({**CUMULATIVE, "0.1": [-1, 0, 3, 1]}, "not-cumulative", "the count up to le=0.1 (-1) is below zero"),
])
def test_counts_that_fall_toward_a_higher_bound_are_refused(cum, code, words):     # not one histogram at one time
    with pytest.raises(_frames.Bad, match=words.replace("(", r"\(").replace(")", r"\)")) as e:
        _frames.answer(buckets(cum), G, 50)
    assert e.value.code == code


def test_buckets_of_more_than_one_histogram_are_refused():
    two = buckets()
    two["buckets"][0]["labels"]["job"] = "a"            # (one bucket of another job's histogram)
    with pytest.raises(_frames.Bad, match="of 2 histograms") as e:
        _frames.answer(two, G, 50)
    assert e.value.code == "many-histograms"
    dup = buckets()
    dup["buckets"].append(dup["buckets"][0])
    with pytest.raises(_frames.Bad, match="histograms, not one"):
        _frames.answer(dup, G, 50)


@pytest.mark.parametrize("cum,word", [({"0": [1, 1, 1, 1]}, "above 0"), ({"-Inf": [0] * 4, "1": [1] * 4}, "above 0"),
                                      ({"+Inf": [1] * 4}, "a finite one"), ({"soon": [1] * 4}, "not a number")])
def test_buckets_with_no_bound_to_draw_from_are_refused(cum, word):
    with pytest.raises(_frames.Bad, match=word):
        _frames.answer(buckets(cum), G, 50)


def test_averaged_percentiles_and_a_quantile_inside_its_bucket_are_warned():   # G22
    q = "histogram_quantile(0.99, sum by (le) (rate(wait_seconds_bucket[5m])))"
    assert [c for c, _ in _lint.warnings("PromQL", q)] == ["quantile-in-bucket"]
    for averaged in (f"avg({q})", f"avg by (job) ({q})", f"avg_over_time(({q})[1h:5m])"):
        assert [c for c, _ in _lint.warnings("PromQL", averaged)] == ["averaged-percentiles", "quantile-in-bucket"], averaged
    assert _lint.warnings("PromQL", "avg(rate(x[5m])) + histogram_quantile(0.5, y)")[0][0] == "quantile-in-bucket"
    assert len(_lint.warnings("PromQL", "avg(rate(x[5m])) + histogram_quantile(0.5, y)")) == 1    # (not inside the avg)
    assert _lint.warnings("PromQL", "sum(rate(x[5m]))") == [] and _lint.warnings("SQL", f"SELECT '{q}'") == []


def test_every_reason_is_from_the_closed_list_and_has_its_fix():
    assert all(level in verdicts.LEVELS and fix for level, fix in verdicts.REASONS.values())
    with pytest.raises(KeyError, match="not a verdict's reason"):
        verdicts.reason("looks-odd", "something")
    v = verdicts.verdict([verdicts.reason("partial", "a"), verdicts.reason("limit", "b"), verdicts.reason("partial", "a")])
    assert v["level"] == "refuse" and [r["code"] for r in v["reasons"]] == ["partial", "limit"]
    assert verdicts.verdict([]) == {"level": "ok", "reasons": []}


def test_a_refused_answer_holds_nothing_to_draw():
    got = frames.framed({"id": "a", "error": "prom: no", "error_kind": "refused", "error_code": "not-cumulative",
                         "series": [{"name": "x", "values": [1]}], "times": [T], "read_log": False}, None)
    assert set(got) == {"id", "error", "error_kind", "read_log", "meta"}
    assert got["meta"]["verdict"]["level"] == "refuse" and got["meta"]["verdict"]["reasons"][0]["code"] == "not-cumulative"


def test_a_role_on_a_series_or_a_graphs_field_is_from_a_closed_list():
    with pytest.raises(_frames.Bad, match="role 'setpoint'"):
        _frames.answer({"shape": "series", "time": [T], "series": [{"key": "a", "role": "setpoint", "values": [1]}]}, G, 50)
    for role in ("sp", "pv", "op", "mv", "limit_hi", "mode"):
        _frames.answer({"shape": "series", "time": [T], "series": [{"key": "a", "role": role, "values": [1]}]}, G, 50)
    bad = graph()
    bad["nodes"]["fields"] = [{"name": "load", "role": "centrality", "values": [1, 2, 3]}]
    with pytest.raises(_frames.Bad, match="role 'centrality'"):
        _frames.answer(bad, G, 50)


def graph(**over) -> dict:
    g = {"shape": "graph", "kind": "dependency",
         "nodes": {"id": ["a", "b", "c"], "label": ["A", "B", "C"],
                   "fields": [{"name": "age", "unit": "s", "role": "age", "values": [1, 2, 3]}]},
         "edges": {"id": ["e1", "e2"], "source": ["a", "b"], "target": ["b", "c"], "relation": ["blocks", "blocks"],
                   "evidence": ["declared", "declared"], "fields": [{"name": "wait", "unit": "s", "role": "wait", "values": [5, None]}]},
         "semantics": {"paths_real": True}, "time": {"mode": "snapshot"},
         "omitted": {"nodes": 0, "edges": 0, "weight_share": 0, "how": ""}}
    for k, v in over.items():
        part, _, key = k.partition("__")
        if key:
            g[part] = {**g[part], key: v}
        else:
            g[part] = v
    return g


def test_a_graph_is_checked_and_its_cycles_worked_out_by_the_server():
    got = _frames.answer(graph(), G, 50)
    assert got["shape"] == "graph" and got["kind"] == "dependency" and got["semantics"]["acyclic"] is True
    assert got["edges"]["fields"][0]["values"] == [5.0, None] and got["nodes"]["label"] == ["A", "B", "C"]
    cyc = _frames.answer(graph(edges__source=["a", "c"], edges__target=["b", "a"]), G, 50)
    assert cyc["semantics"]["acyclic"] is True                  # a → b, c → a: no cycle
    loop = _frames.answer(graph(edges__source=["a", "b"], edges__target=["b", "a"]), G, 50)
    assert loop["semantics"]["acyclic"] is False
    assert _frames.answer(graph(edges__source=["a", "b"], edges__target=["a", "c"]), G, 50)["semantics"]["acyclic"] is False
    framed = frames.framed(got, None)
    assert framed["shape"] == "graph" and framed["kind"] == "dependency" and framed["meta"]["n"] == 3


@pytest.mark.parametrize("over,word", [
    ({"kind": "network"}, "not 'network'"),
    ({"edges__target": ["b", "z"]}, "names 'z', which is not one of the nodes"),
    ({"nodes__parent": ["b", None, "q"]}, "names 'q'"),
    ({"semantics": {}}, "paths_real, true or false"),
    ({"semantics": {"paths_real": "yes"}}, "paths_real, true or false"),
    ({"semantics": {"paths_real": True, "acyclic": False}}, "says acyclic is False, but it has no cycle"),
    ({"edges__evidence": ["declared", "guessed"]}, "not 'guessed'"),
    ({"edges__evidence": ["declared", "inferred"], "edges__confidence": [1, 0.4]}, "not built from inferred edges"),
    ({"time": {"mode": "events"}}, "needs each edge's time"),
    ({"time": {"mode": "intervals"}}, "time.mode is one of"),
    ({"omitted": {"nodes": 0}}, "what it left out"),
    ({"nodes__id": ["a", "a", "c"]}, "two nodes share an id"),
    ({"edges__relation": ["blocks"]}, "edges.relation has 1 entries for 2 edges"),
])
def test_a_graph_that_is_not_what_it_says_is_refused(over, word):
    with pytest.raises(_frames.Bad, match=word):
        _frames.answer(graph(**over), G, 50)


def test_an_inferred_edge_needs_its_confidence_and_a_service_map_may_hold_one():
    with pytest.raises(_frames.Bad, match="edges.confidence"):
        _frames.answer(graph(kind="service", semantics={"paths_real": False}, edges__evidence=["observed", "inferred"]), G, 50)
    got = _frames.answer(graph(kind="service", semantics={"paths_real": False}, edges__evidence=["observed", "inferred"],
                               edges__confidence=[1, 0.4]), G, 50)
    assert got["edges"]["confidence"] == [1.0, 0.4] and got["semantics"]["paths_real"] is False


def test_a_histogram_of_more_buckets_than_series_allowed_is_a_limit():
    with pytest.raises(_frames.TooMany, match="buckets has 4 entries, more than the 3 allowed"):
        _frames.answer(buckets(), G, 3)


def test_a_graph_over_its_bound_is_a_limit(monkeypatch):
    monkeypatch.setattr(_frames, "MOST_ROWS", 2)
    with pytest.raises(_frames.TooMany, match="nodes.id has 3 entries"):
        _frames.answer(graph(), G, 50)


def test_the_envelope_says_n_and_step_and_leaves_what_it_does_not_know_unknown():
    got = frames.framed({"times": TIMES, "step": 120.0, "series": [{"name": "a", "values": [1, None, 3, 4]}]}, None)
    assert got["meta"]["n"] == 3 and got["meta"]["n_effective"] is None
    assert got["meta"]["sampling"] == {"step_s": 120.0, "scrape_s": None, "range_windows_s": [],
                                       "observable_period_s": [240.0, None], "nulls_s": []}     # (no window: no high end)


class Histogram(BaseHTTPRequestHandler):
    """A Prometheus whose every range query answers the hand-worked buckets; ``two`` answers them for two jobs."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        a = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        text = a["query"]
        jobs = ["a", "b"] if text.startswith(("two", "slo")) else [None]
        cum = {**CUMULATIVE, "1": [6, 3, 7, 1]} if text.startswith("bad") else CUMULATIVE
        if text.startswith(("slo", "top")):          # one bound by job; or one finite bound and +Inf
            cum = {le: CUMULATIVE[le] for le in (["0.5"] if text.startswith("slo") else ["0.5", "+Inf"])}
        result = [{"metric": {"__name__": "wait_seconds_bucket", "le": le, **({"job": j} if j else {})},
                   "values": [[t, str(v)] for t, v in zip(TIMES, vs, strict=True) if v is not None]}
                  for j in jobs for le, vs in cum.items()]
        body = json.dumps({"status": "success", "data": {"resultType": "matrix", "result": result}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def histogram():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Histogram)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def asked(tmp_path, url, *texts) -> list[dict]:
    p = project(tmp_path, f"prom: {{type: prometheus, url: '{url}'}}")
    return ask(p, *({"source": "prom", "text": t} for t in texts))


def test_a_latency_heatmaps_query_through_prometheus_is_the_hand_worked_distribution(tmp_path, histogram):   # chart 16
    [got] = asked(tmp_path, histogram, "sum by (le) (increase(wait_seconds_bucket[2m]))")
    assert (got["shape"], got["form"]) == ("distribution", "bins") and got["x"]["label"] == "wait_seconds"
    assert got["over_time"]["counts"] == [[2, 3, 1], [0, 4, 5], None, [1, 0, 0]] and got["series"][0]["values"] == [3, 7, 6]
    assert got["meta"]["verdict"]["level"] == "warn" and got["meta"]["source"] == "prom"
    assert [r["code"] for r in got["meta"]["verdict"]["reasons"]] == ["open-top-bucket", "scrape-unknown"]


def test_through_prometheus_a_misused_histogram_is_refused_with_its_fix_and_nothing_to_draw(tmp_path, histogram):
    bad, two = asked(tmp_path, histogram, "bad", "two")
    for got, code in ((bad, "not-cumulative"), (two, "many-histograms")):
        assert "shape" not in got and "series" not in got and got["error_kind"] == "refused", got
        [r] = got["meta"]["verdict"]["reasons"]
        assert got["meta"]["verdict"]["level"] == "refuse" and r["code"] == code and r["fix"] == verdicts.REASONS[code][1]
        assert r["says"] == got["error"] and "answered badly" not in got["error"]
    [q] = asked(tmp_path, histogram, "avg(histogram_quantile(0.9, sum by (le) (rate(wait_seconds_bucket[5m]))))")
    assert [r["code"] for r in q["meta"]["verdict"]["reasons"]] == ["open-top-bucket", "averaged-percentiles", "quantile-in-bucket",
                                                                    "scrape-unknown"]


def test_a_bucket_query_at_one_bound_stays_plain_series_and_two_bounds_are_buckets(tmp_path, histogram):
    """``rate(x_bucket{le="0.5"}[5m])`` by job (an SLO's numerator) is plain series, as before buckets were read; one
    finite bound and +Inf are one histogram's buckets."""
    slo, top = asked(tmp_path, histogram, 'slo:rate(wait_seconds_bucket{le="0.5"}[2m])', "top")
    assert slo.get("shape") == "series" and "error" not in slo, slo
    assert len(slo["series"]) == 2 and slo["series"][0]["values"] == [5, 4, None, 1]
    assert [r["code"] for r in slo["meta"]["verdict"]["reasons"]] == ["scrape-unknown", "mixed-windows"]   # no misuse
    assert (top["shape"], top["form"]) == ("distribution", "bins") and top["x"]["edges"] == [0.0, 0.5]
    assert top["over_time"]["counts"] == [[5], [4], None, [1]]


def test_the_bucket_reading_is_quick_at_its_bound():
    """The largest histogram a query may answer, 50 buckets at 1,001 times: its time is measured and said (the
    record's *Where it stopped*), and bounded here only loosely, a hundred times what it takes."""
    g = grid(T, T + 1000 * 60, 1000)
    times = [g.start + i * g.step for i in range(g.n)]
    many = {"shape": "distribution", "buckets": [{"labels": {"le": str(0.01 * (k + 1))}, "time": times,
                                                  "values": [float(k + i) for i in range(g.n)]} for k in range(50)]}
    took = time.perf_counter()
    got = _frames.answer(many, g, 50)
    took = time.perf_counter() - took
    assert len(got["over_time"]["counts"]) == g.n and len(got["series"][0]["values"]) == 50
    assert took < 5.0, took
