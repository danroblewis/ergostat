"""Acceptance (graph-result-and-panel, B6 of the chart catalog), the server's half: ergostat's own three graphs as
``graph`` answers of named kinds (``{"source": "graph", "diagram": ...}``: graphs.py), the panel's budget and honest
aggregation (graphfit.py), the matrix (chart 77), and the guardrails this item answers for, each tried. The page's half
(ELK in a worker, the graph and matrix drawn) is tests/test_graph_result_page.py.

The hand-worked dependency record (charts 74 and 75): one block, ``worker``, of pool 2, takes tickets from ``todo``; five
old tickets each spent 20 min in ``doing``, so a ticket's expected work is 20 min (1,200 s). Open: ``a``, ``b`` blocked by
``a``, ``c``, ``d``, ``e``, and ``g`` blocked by ``f``, which is done.

    critical path (no capacity)   a 0-20, then b 20-40; the rest 0-20       ends in 40 min, a and b critical
    slack                         a 0, b 0; c, d, e, g 20 min each
    levelled (2 at once)          lane 1: a 0-20, b 20-40, e 40-60; lane 2: c 0-20, d 20-40, g 40-60      ends in 1 h
    edges                         a > b blocks (a is open); f > g met (f is done: no wait is held, G40)

The hand-worked process record (by states): t1 and t2 go todo, doing, done; t3 goes todo, doing, back to todo, doing.

    lines        start>todo 3   todo>doing 4 (1 a return)   doing>done 2   doing>todo 1 (a return)   done>end 2
    steps        todo 4   doing 4   done 2   start 3   end 2
"""

from __future__ import annotations

import base64
import json
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.datasources import _frames
from ergostat.query import frames, graphfit, graphs, parse
from ergostat.store import Project
from ergostat.web.server import Live, api

T0 = 1_700_000_000.0
DEPS = """
items:
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.started: doing, ticket.done: done}
    relations:
      blocked_by: ticket
messages:
  done: {ticket: [done]}
blocks:
  worker:
    type: program
    run: "true"
    takes: {kind: ticket, at: todo}
    pool: 2
"""
STEPS = """
items:
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.started: doing, ticket.returned: todo, ticket.done: done}
messages:
  done: {ticket: [done]}
"""


def project(tmp_path, text) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def ask(p, *queries, since=900.0, until=T0 + 3000) -> list[dict]:
    body = {"since": since, "until": until, "points": 4, "queries": [{"id": str(i), **x} for i, x in enumerate(queries)]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return api(Live(p), "query", {"q": [q]})["results"]


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(graphs, "_KEPT", {})


def deps(tmp_path) -> Project:
    p = project(tmp_path, DEPS)
    ev = p.events.add
    for i in range(5):
        ev("ticket.planned", item=f"ticket/old{i}", at=T0 + i)
        ev("ticket.started", item=f"ticket/old{i}", at=T0 + 10 + i)
        ev("ticket.done", item=f"ticket/old{i}", at=T0 + 10 + i + 1200)
    ev("ticket.planned", item="ticket/f", at=T0 + 2000)
    ev("ticket.started", item="ticket/f", at=T0 + 2100)
    ev("ticket.done", item="ticket/f", at=T0 + 2500)
    for name, after in (("a", None), ("b", "a"), ("c", None), ("d", None), ("e", None), ("g", "f")):
        ev("ticket.planned", item=f"ticket/{name}", data={"blocked_by": f"ticket/{after}"} if after else {}, at=T0 + 2600)
    return p


def column(g, part, name):
    return dict(zip(g[part]["id"], next(f for f in g[part]["fields"] if f["name"] == name)["values"], strict=True))


def test_the_dependency_graph_and_its_critical_path_beside_the_levelled_end(tmp_path):     # charts 74, 75; G42, G40
    [r] = ask(deps(tmp_path), {"source": "graph", "diagram": "dependency", "kind": "ticket"})
    assert "error" not in r, r
    assert (r["shape"], r["kind"], r["semantics"]["paths_real"], r["semantics"]["acyclic"]) == ("graph", "dependency", True, True)
    ids = {f"ticket/{x}" for x in "abcdefg"}
    assert set(r["nodes"]["id"]) == ids
    assert dict(zip(r["edges"]["id"], r["edges"]["relation"], strict=True)) == {
        "ticket/a>ticket/b:blocked_by": "blocks", "ticket/f>ticket/g:blocked_by": "met"}
    slack = column(r, "nodes", "slack")
    assert {k: slack[f"ticket/{k}"] for k in "abcdeg"} == {"a": 0, "b": 0, "c": 1200, "d": 1200, "e": 1200, "g": 1200}
    assert {k for k, v in column(r, "nodes", "critical").items() if v} == {"ticket/a", "ticket/b"}
    assert r["semantics"]["focus"] == ["ticket/a", "ticket/b"]
    assert column(r, "edges", "critical") == {"ticket/a>ticket/b:blocked_by": 1.0, "ticket/f>ticket/g:blocked_by": 0.0}
    now = T0 + 3000
    assert (r["ends"]["critical_path"] - now, r["ends"]["levelled"] - now) == (2400, 3600)
    assert r["said"] == ["The critical path ends in 40m; levelled by each block's capacity, the work ends in 1h: "
                         "the critical path alone is not the finish date"]
    assert r["meta"]["verdict"] == {"level": "ok", "reasons": []} and r["meta"]["n"] == 7
    assert r["read_log"] is False                       # the item index, not the event log


def steps(tmp_path) -> Project:
    p = project(tmp_path, STEPS)
    ev = p.events.add
    for i, (name, path) in enumerate((("t1", "sd"), ("t2", "sd"), ("t3", "srs"))):
        ev("ticket.planned", item=f"ticket/{name}", at=T0 + i)
        for j, step in enumerate(path):
            ev({"s": "ticket.started", "d": "ticket.done", "r": "ticket.returned"}[step], item=f"ticket/{name}",
               at=T0 + 60 * (j + 1) + i)
        if name == "t3":
            ev("ticket.started", item="ticket/t3", at=T0 + 300)
    return p


def test_the_process_map_is_a_process_graph_whose_routes_are_not_evidence(tmp_path):    # chart 66's graph; G35
    [r] = ask(steps(tmp_path), {"source": "graph", "diagram": "process"}, until=T0 + 600)
    assert "error" not in r, r
    assert (r["kind"], r["semantics"]["paths_real"]) == ("process", False)
    label = dict(zip(r["nodes"]["id"], r["nodes"]["label"], strict=True))
    lines = {f"{label[s]}>{label[t]}": n for s, t, n in zip(r["edges"]["source"], r["edges"]["target"], r["edges"]["n"], strict=True)}
    assert lines == {"start>todo": 3, "todo>doing": 4, "doing>done": 2, "doing>todo": 1, "done>end": 2}
    returns = column(r, "edges", "returns")
    assert {f"{label[s]}>{label[t]}": returns[i] for i, s, t in zip(r["edges"]["id"], r["edges"]["source"], r["edges"]["target"], strict=True)
            if returns[i]} == {"todo>doing": 1, "doing>todo": 1}
    assert {label[k]: v for k, v in column(r, "nodes", "count").items()} == {"start": 3, "todo": 4, "doing": 4, "done": 2, "end": 2}
    assert r["semantics"]["acyclic"] is False and r["meta"]["verdict"]["level"] == "ok"     # a line back is no defect (G44)
    assert r["said"][0].startswith("a line back is a return or concurrency, not a defect")
    assert r["read_log"] is True


def test_the_wiring_is_a_service_graph_with_its_evidence(repo):
    from tests.test_graph_cli_web import wired
    p = wired(repo)
    [r] = ask(p, {"source": "graph", "diagram": "service"}, since=86400.0, until=None)
    assert "error" not in r, r
    assert (r["kind"], r["semantics"]["paths_real"]) == ("service", False)
    name = dict(zip(r["nodes"]["id"], r["nodes"]["label"], strict=True))
    ev = {(name[s], name[t]): (e, n) for s, t, e, n in zip(r["edges"]["source"], r["edges"]["target"], r["edges"]["evidence"],
                                                           r["edges"]["n"], strict=True)}
    assert ev == {("cleaner", "ergostat"): ("both", 1), ("ergostat", "decider"): ("both", 1), ("cleaner", "notifier"): ("observed", 1),
                  ("billing", "mailer"): ("observed", 1), ("cleaner", "auditor"): ("declared", 0)}
    seen = dict(zip(r["edges"]["evidence"], r["edges"]["last_seen"], strict=False))
    assert seen["declared"] is None                     # declared, never seen: no time it was seen (G40)


def graph(n: int, m: int = 0, **cols) -> dict:
    """``n`` nodes ``n0``..; ``m`` edges in a chain round them, edge ``i`` of count ``i + 1`` and latency ``i / 10``."""
    ids = [f"n{i}" for i in range(n)]
    edges = [(ids[i % n], ids[(i + 1) % n]) for i in range(m)]
    return _frames.answer({
        "shape": "graph", "kind": "service",
        "nodes": {"id": ids, "label": ids, "fields": [{"name": "calls", "role": "count", "values": list(range(n))}], **cols},
        "edges": {"id": [f"e{i}" for i in range(m)], "source": [a for a, _ in edges], "target": [b for _, b in edges],
                  "relation": ["calls"] * m, "evidence": ["observed"] * m, "n": [i + 1 for i in range(m)],
                  "fields": [{"name": "latency", "unit": "s", "role": "latency", "values": [i / 10 for i in range(m)]}]},
        "semantics": {"paths_real": False}, "time": {"mode": "snapshot"},
        "omitted": {"nodes": 0, "edges": 0, "weight_share": 0.0, "how": ""}}, None, 0)


def test_a_graph_within_the_budget_is_drawn_as_it_is():
    g = graph(40, 100)
    assert graphfit.fit(g, *graphfit.PANEL) == (g, [])


def test_over_the_budget_nodes_collapse_by_group_and_what_they_hold_is_said():      # G45
    group = ["g"] * 10 + [None] * 35
    health = ["ok"] * 9 + ["unhealthy"] + ["ok"] * 35
    g = graph(45, 44, group=group, health=health)
    got, how = graphfit.fit(g, *graphfit.PANEL)
    assert how == ["45 nodes collapsed by group into 36", "9 edges inside a collapsed node are held by it"]
    i = got["nodes"]["id"].index("group:g")
    assert (got["nodes"]["label"][i], got["nodes"]["holds"][i], got["nodes"]["health"][i]) == ("g", 10, "unhealthy")
    assert got["nodes"]["fields"][0]["values"][i] == sum(range(10))           # a count is summed
    out = [k for k, s in enumerate(got["edges"]["source"]) if s == "group:g"]
    assert [got["edges"]["id"][k] for k in out] == ["e9"]                      # n9 > n10 leaves the group
    assert got["semantics"]["paths_real"] is False and got["semantics"]["acyclic"] is g["semantics"]["acyclic"]
    assert got["omitted"]["how"] == "45 nodes collapsed by group into 36; 9 edges inside a collapsed node are held by it"


def test_latency_is_never_averaged_across_an_aggregated_edge():                     # G45, the misuse tried
    g = graph(42, 0, group=["a"] * 21 + ["b"] * 21)
    g = {**g, "edges": {"id": ["x", "y"], "source": ["n0", "n1"], "target": ["n21", "n22"], "relation": ["calls"] * 2,
                        "evidence": ["observed", "declared"], "n": [3, 5],
                        "fields": [{"name": "latency", "unit": "s", "role": "latency", "values": [0.2, 0.8]},
                                   {"name": "per s", "unit": "/s", "role": "rate", "values": [1.5, 2.5]}]}}
    got, _ = graphfit.fit(g, *graphfit.PANEL)
    e = got["edges"]
    assert (e["id"], e["source"], e["target"], e["holds"], e["n"], e["evidence"]) == (
        ["group:a>group:b:calls"], ["group:a"], ["group:b"], [2], [8], ["both"])
    assert [f["values"] for f in e["fields"]] == [[0.8], [4.0]]               # the worst latency, never 0.5; rates summed
    assert e["worst"] == [{"latency": "y"}]


def test_then_by_type_then_by_weight_into_other():
    typed = graphfit.fit(graph(50, type=["db"] * 20 + [None] * 30), *graphfit.PANEL)
    assert typed[1] == ["50 nodes collapsed by type into 31"] and "type:db" in typed[0]["nodes"]["id"]
    got, how = graphfit.fit(graph(60), *graphfit.PANEL)
    assert how == ["the lightest 21 into 'other'"]
    assert len(got["nodes"]["id"]) == 40 and got["nodes"]["id"][0] == "other" and got["nodes"]["holds"][0] == 21
    assert set(got["nodes"]["id"]) - {"other"} == {f"n{i}" for i in range(21, 60)}     # the heaviest 39 kept


def test_over_the_edge_budget_the_lightest_edges_are_left_out_and_their_share_said():
    g = graph(30, 120)
    g["edges"]["relation"] = [f"r{i}" for i in range(120)]       # (each its own edge: none merged)
    got, how = graphfit.fit(g, *graphfit.PANEL)
    assert len(got["edges"]["id"]) == 100 and set(got["edges"]["n"]) == set(range(21, 121))
    share = sum(range(1, 21)) / sum(range(1, 121))
    assert got["omitted"]["edges"] == 20 and got["omitted"]["weight_share"] == pytest.approx(share)
    assert how == [f"the lightest 20 edges left out ({share:.0%} of the weight)"]


def test_an_over_budget_graph_warns_and_offers_the_matrix():                       # chart 77
    out = graphs.drawn(*graphs.service({"nodes": [{"id": f"agent:{i}", "label": str(i), "runs": i} for i in range(50)],
                                        "edges": [], "since": 0, "until": 1}))
    framed = frames.framed(out, parse.Query(id="0", source="graph", agg="count", diagram="service"))
    [why] = framed["meta"]["verdict"]["reasons"]
    assert why["code"] == "graph-over-budget" and why["says"].startswith("50 nodes and 0 edges are more than the 40 and 100")
    assert "matrix" in why["fix"] and framed["meta"]["verdict"]["level"] == "warn"
    assert len(out["matrix"]["ids"]) == 50 and out["matrix"]["fitted"] == []     # the matrix holds them all


def test_the_matrix_orders_by_group_and_sums_the_cells():
    g = graph(3, 3, group=["z", "a", None])
    g["edges"]["source"], g["edges"]["target"] = ["n0", "n0", "n2"], ["n1", "n1", "n0"]
    g["edges"]["relation"] = ["calls", "owns", "calls"]
    m = graphfit.matrix(g)
    assert (m["ids"], m["group"]) == (["n1", "n0", "n2"], ["a", "z", None])
    assert m["cells"] == [[1, 0, 3], [2, 1, 3]]       # n0 > n1 twice (1 + 2), n2 > n0 once (3)


def test_a_graph_read_only_in_part_says_whether_it_has_a_cycle_is_not_known():     # G43
    ans = {"nodes": [{"id": "p:t:a", "label": "a", "kind": "activity", "itemKind": "t", "count": 1, "items": 1}],
           "edges": [], "since": 0, "until": 1, "capped": {"edges": True}, "total": {"nodes": 1, "edges": 200}}
    out = graphs.drawn(*graphs.process(ans))
    assert out["semantics"]["acyclic"] is None
    [(code, says)] = out["warnings"]
    assert code == "graph-truncated" and "whether it has a cycle, and what reaches what, is not known" in says
    assert out["omitted"]["edges"] == 200 and out["omitted"]["weight_share"] is None


def test_what_a_cycle_means_is_said_by_kind():                                     # G44
    item = lambda i, **kw: {"id": i, "status": "blocked", "cycle": True, **kw}      # noqa: E731
    ans = {"items": [item("x"), item("y")], "now": 0, "end": 0, "since": 0, "capped": {}, "critical": [], "cycles": [["x", "y"]],
           "edges": [{"from": "x", "to": "y", "rel": "after", "kind": "precedence"}, {"from": "y", "to": "x", "rel": "after", "kind": "precedence"}]}
    dep = graphs.drawn(*graphs.dependency(ans))
    assert dep["warnings"] == [("graph-cycle", "a cycle of precedence is a defect: none of its items can ever be ready (x, y)")]
    assert dep["nodes"]["health"] == ["unhealthy", "unhealthy"]
    wire = {"nodes": [{"id": "agent:a", "label": "a"}, {"id": "agent:b", "label": "b"}], "since": 0, "until": 1,
            "edges": [{"id": i, "source": s, "target": t, "seen": True, "declared": True, "count": 1, "perHour": 1, "last": 1}
                      for i, s, t in (("1", "agent:a", "agent:b"), ("2", "agent:b", "agent:a"))]}
    svc = graphs.drawn(*graphs.service(wire))
    assert svc["warnings"] == [] and svc["said"][0].startswith("calls that go round are normal")


@pytest.mark.parametrize("q,word", [
    ({"source": "graph"}, "diagram: dependency | process | service"),
    ({"source": "graph", "diagram": "callgraph"}, "diagram: dependency | process | service"),
    ({"source": "graph", "diagram": "process", "agg": "sum"}, "'agg' is not one of its keys"),
    ({"source": "items", "field": "x", "diagram": "process"}, "a graph is asked as"),
    ({"source": "items", "field": "x", "x": {"type": "query", "query": {"source": "graph", "diagram": "process"}}},
     "never an X"),
])
def test_a_graph_is_asked_only_in_its_own_form(q, word):
    [got] = parse.parse({"queries": [q]}).queries
    assert isinstance(got, parse.Refused) and word in got.error, got


def test_a_kind_not_in_the_model_and_a_kind_on_the_wiring_are_refused(tmp_path):
    p = deps(tmp_path)
    a, b = ask(p, {"source": "graph", "diagram": "dependency", "kind": "nope"}, {"source": "graph", "diagram": "service", "kind": "ticket"})
    assert "kind 'nope' is not in the model" in a["error"] and "takes no kind" in b["error"]
    assert a["meta"]["verdict"]["level"] == "refuse" and "nodes" not in a


def test_the_record_is_read_once_for_a_graph_however_many_ask(tmp_path, monkeypatch):   # done 5
    from ergostat import process as pm
    p, calls, real = steps(tmp_path), [], pm.process
    monkeypatch.setattr(pm, "process", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = ask(p, {"source": "graph", "diagram": "process"}, until=T0 + 600)[0]
    again = ask(p, {"source": "graph", "diagram": "process"}, until=T0 + 600)[0]
    assert len(calls) == 1 and first["read_log"] is True and again["read_log"] is False
    assert again["nodes"] == first["nodes"]
    clock = time.monotonic
    monkeypatch.setattr(graphs.time, "monotonic", lambda: clock() + graphs.KEPT + 1)
    ask(p, {"source": "graph", "diagram": "process"}, until=T0 + 600)
    assert len(calls) == 2                                # kept KEPT seconds, then read again


def test_fitting_a_graph_at_its_bound_is_quick():                                  # done 5: factory size
    g = graph(5000, 5000, group=[f"g{i % 400}" for i in range(5000)])
    t = time.perf_counter()
    shown, how = graphfit.fit(g, *graphfit.PANEL)
    m = graphfit.matrix(g)
    took = time.perf_counter() - t
    assert len(shown["nodes"]["id"]) <= 40 and len(shown["edges"]["id"]) <= 100 and len(m["ids"]) <= 300
    assert took < 5.0, took
