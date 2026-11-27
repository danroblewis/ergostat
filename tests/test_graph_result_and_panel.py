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
from ergostat.web import relations_api
from ergostat.web.server import Live, api

T0 = 1_700_000_000.0
DEPS = """
projections:
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
    takes: {projection: ticket, at: todo}
    pool: 2
"""
STEPS = """
projections:
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
    """Each test starts with no kept answers: graphs.py's, and relations_api's, whose key holds id(spec), an id CPython
    reuses once a test's spec is freed, and not precedence.py's caps; so a capped answer is never served to another."""
    monkeypatch.setattr(graphs, "_KEPT", {})
    monkeypatch.setattr(relations_api, "_CACHE", {})


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
    [r] = ask(deps(tmp_path), {"source": "graph", "diagram": "dependency", "projection": "ticket"})
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
    e = r["edges"]
    assert {f"{label[s]}>{label[t]}": returns[i] for i, s, t in zip(e["id"], e["source"], e["target"], strict=True)
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


def test_edges_of_unknown_weight_left_out_leave_their_share_unknown():           # lesson 3
    """120 edges, the lightest 20 of which (n 1 to 20) have their n null: nobody knows what they weigh, so leaving them
    out is never said to be 0% of the weight. Through ``graphs.panel``, as a data source's graph is fitted, too."""
    g = graph(30, 120)
    g["edges"]["relation"] = [f"r{i}" for i in range(120)]
    g["edges"]["n"] = [None] * 20 + list(range(21, 121))
    g = _frames.answer(g, None, 0)
    assert g["edges"]["n"][:20] == [None] * 20
    got, how = graphfit.fit(g, *graphfit.PANEL)
    assert len(got["edges"]["id"]) == 100 and got["omitted"]["edges"] == 20 and got["omitted"]["weight_share"] is None
    assert how == ["20 edges left out (their share of the weight is not known)"]
    out = graphs.panel(g, {})
    assert out["omitted"]["edges"] == 20 and out["omitted"]["weight_share"] is None
    g["edges"]["n"] = list(range(1, 100)) + [None] + list(range(101, 121))    # one kept edge unknown: the total is too
    assert graphfit.fit(g, *graphfit.PANEL)[0]["omitted"]["weight_share"] is None


def test_a_matrix_cell_of_unknown_weight_is_null_never_one():                     # lesson 3; done 3
    """n0 > n1 has n 3; n1 > n2 has n null; n2 > n0 twice, once null: the two unknown cells are null, not 1 or 3."""
    g = graph(3, 4)
    g["edges"]["source"], g["edges"]["target"] = ["n0", "n1", "n2", "n2"], ["n1", "n2", "n0", "n0"]
    g["edges"]["n"] = [3, None, 4, None]
    assert graphfit.matrix(_frames.answer(g, None, 0))["cells"] == [[0, 1, 3.0], [1, 2, None], [2, 0, None]]
    del g["edges"]["n"]                                  # no n: the first summed field weighs it, null when it is
    g["edges"]["fields"] = [{"name": "calls", "role": "count", "values": [3, None, 4, None]}]
    assert graphfit.matrix(_frames.answer(g, None, 0))["cells"] == [[0, 1, 3.0], [1, 2, None], [2, 0, None]]


def test_a_merged_field_with_an_unknown_member_is_unknown_not_a_partial_total():   # lesson 3; G45
    """Group a (n0..n20) to group b (n21..n41) by three edges of n 5, null and 7, count 5, null, 7, latency 0.2, null,
    0.1: the merged edge holds 3, and its n, count and latency are null, never 12, 12 and 0.2. A node group with a
    count null in one member, or a health not known in one, is not known either; with every member known, it is."""
    g = graph(42, 0, group=["a"] * 21 + ["b"] * 21, health=["ok"] * 20 + [None] + ["ok"] * 21)
    g["nodes"]["fields"][0]["values"][3] = None
    g = {**g, "edges": {"id": ["x", "y", "z"], "source": ["n0", "n1", "n2"], "target": ["n21", "n22", "n23"],
                        "relation": ["calls"] * 3, "evidence": ["observed"] * 3, "n": [5, None, 7], "confidence": [0.9, None, 0.8],
                        "fields": [{"name": "count", "role": "count", "values": [5, None, 7]},
                                   {"name": "latency", "unit": "s", "role": "latency", "values": [0.2, None, 0.1]}]}}
    e = graphfit.fit(_frames.answer(g, None, 0), *graphfit.PANEL)[0]["edges"]
    assert (e["holds"], e["n"], e["confidence"], [f["values"] for f in e["fields"]]) == ([3], [None], [None], [[None], [None]])
    assert e["worst"] == [{}]                            # no member named the worst when one is not known
    nodes = graphfit.fit(_frames.answer(g, None, 0), *graphfit.PANEL)[0]["nodes"]
    assert nodes["fields"][0]["values"] == [None, sum(range(21, 42))] and nodes["health"] == [None, "ok"]


def test_an_over_budget_graph_warns_and_offers_the_matrix():                     # chart 77
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
    ans = {"nodes": [{"id": "p:t:a", "label": "a", "kind": "activity", "projection": "t", "count": 1, "items": 1}],
           "edges": [], "since": 0, "until": 1, "capped": {"edges": True}, "total": {"nodes": 1, "edges": 200}}
    out = graphs.drawn(*graphs.process(ans))
    assert out["semantics"]["acyclic"] is None
    [(code, says)] = out["warnings"]
    assert code == "graph-truncated" and "whether it has a cycle, and what reaches what, is not known" in says
    assert out["omitted"]["edges"] == 200 and out["omitted"]["weight_share"] is None


def test_a_capped_graph_over_the_panel_budget_keeps_its_share_unknown():        # G43; lesson 3
    """ergostat's own graphs past their makers' caps say ``weight_share`` None with no edges counted as left out. Fitted
    to the panel (50 nodes into 40), the unknown stays unknown, not 0 (nor only the share the fit dropped)."""
    wiring = {"nodes": [{"id": f"agent:{i}", "label": str(i), "runs": i} for i in range(50)],
              "edges": [{"id": f"e{i}", "source": f"agent:{i}", "target": f"agent:{i + 1}", "count": i + 1, "last": 1,
                         "perHour": 1.0, "seen": True, "declared": False} for i in range(49)], "since": 0, "until": 1}
    known = graphs.drawn(*graphs.service(wiring))
    assert len(known["nodes"]["id"]) == 40 and known["omitted"]["weight_share"] == 0.0    # a known share stays known
    out = graphs.drawn(*graphs.service({**wiring, "capped": True}))
    assert len(out["nodes"]["id"]) == 40 and out["omitted"]["edges"] == 0 and out["omitted"]["weight_share"] is None
    items = [{"id": f"x{i}", "status": "ready", "duration": 10.0} for i in range(50)]
    ans = {"items": items, "edges": [], "now": 0, "end": 0, "since": 0, "critical": [], "cycles": [], "capped": {"open": 7}}
    dep = graphs.drawn(*graphs.dependency(ans))
    assert len(dep["nodes"]["id"]) == 40 and dep["omitted"]["weight_share"] is None


def test_a_dependency_graph_read_only_in_part_states_no_schedule(tmp_path, monkeypatch):   # G43, done 3; lesson 3, 8
    """With precedence.py's open items capped at 3 of the 6 (a, b, c, d, e, g), the others are not scheduled, so no end,
    slack or critical path is stated as fact: each is null, nothing is heavy, and the warning says they are not known.
    The same when only the items pulled in by relations were cut."""
    from ergostat import precedence
    monkeypatch.setattr(precedence, "MOST_OPEN", 3)
    [r] = ask(deps(tmp_path), {"source": "graph", "diagram": "dependency", "projection": "ticket"})
    assert "error" not in r, r
    assert r["omitted"]["nodes"] == 3 and r["semantics"]["acyclic"] is None
    assert "ends" not in r and "said" not in r and r["semantics"]["focus"] == []
    assert set(column(r, "nodes", "slack").values()) == {None} and set(column(r, "nodes", "critical").values()) == {None}
    assert set(column(r, "edges", "critical").values()) <= {None}
    [says] = [w["says"] for w in r["meta"]["verdict"]["reasons"] if w["code"] == "graph-truncated"]
    assert "its slack, its critical path and when the work ends, is not known" in says and r["meta"]["verdict"]["level"] == "warn"
    item = {"id": "x", "status": "ready", "slack": 0.0, "critical": True, "lf": 100.0, "duration": 10.0}
    ans = {"items": [item], "edges": [], "now": 0, "end": 200, "since": 0, "critical": ["x"], "cycles": [],
           "capped": {"pulled": True}}
    out = graphs.drawn(*graphs.dependency(ans))
    assert "ends" not in out and "said" not in out and out["semantics"]["focus"] == []
    assert column(out, "nodes", "slack") == {"x": None} and column(out, "nodes", "critical") == {"x": None}
    ans["capped"] = {"done": True}                      # finished items past their cap are not scheduled: it stands
    out = graphs.drawn(*graphs.dependency(ans))
    assert out["ends"] == {"now": 0, "critical_path": 100.0, "levelled": 200} and out["semantics"]["focus"] == ["x"]


def test_what_a_cycle_means_is_said_by_kind():                                     # G44
    item = lambda i, **kw: {"id": i, "status": "blocked", "cycle": True, **kw}      # noqa: E731
    ans = {"items": [item("x"), item("y")], "now": 0, "end": 0, "since": 0, "capped": {}, "critical": [], "cycles": [["x", "y"]],
           "edges": [{"from": a, "to": b, "rel": "after", "kind": "precedence"} for a, b in (("x", "y"), ("y", "x"))]}
    dep = graphs.drawn(*graphs.dependency(ans))
    assert dep["warnings"] == [("graph-cycle", "a cycle of precedence is a defect: none of its items can ever be ready (x, y)")]
    assert dep["nodes"]["health"] == ["unhealthy", "unhealthy"]
    wire = {"nodes": [{"id": "agent:a", "label": "a"}, {"id": "agent:b", "label": "b"}], "since": 0, "until": 1,
            "edges": [{"id": i, "source": s, "target": t, "seen": True, "declared": True, "count": 1, "perHour": 1, "last": 1}
                      for i, s, t in (("1", "agent:a", "agent:b"), ("2", "agent:b", "agent:a"))]}
    svc = graphs.drawn(*graphs.service(wire))
    assert svc["warnings"] == [] and svc["said"][0].startswith("calls that go round are normal")


def test_a_cycle_in_a_kind_with_no_words_of_its_own_is_said_and_never_fails(monkeypatch):   # G44; lesson 3
    """A sequence diagram's reply (a > b > a) is a cycle; its graph still answers, a reply said to be no defect. A kind
    with no wording at all is warned of in the generic sentence, never a KeyError."""
    def seq():
        return _frames.answer({"shape": "graph", "kind": "sequence", "nodes": {"id": ["a", "b"], "label": ["a", "b"]},
                               "edges": {"id": ["1", "2"], "source": ["a", "b"], "target": ["b", "a"], "relation": ["calls", "replies"],
                                         "evidence": ["observed"] * 2},
                               "semantics": {"paths_real": True}, "time": {"mode": "snapshot"},
                               "omitted": {"nodes": 0, "edges": 0, "weight_share": 0.0, "how": ""}}, None, 0)
    out = graphs.panel(seq(), {})
    assert out["semantics"]["acyclic"] is False and out["warnings"] == []
    assert out["said"] == ["a message back is a reply, not a defect"]
    monkeypatch.delitem(graphs.CYCLE, "sequence")
    out = graphs.panel(seq(), {})
    assert out["warnings"] == [("graph-cycle", graphs.UNSAID[1])] and "said" not in out


def test_a_start_to_start_wait_whose_state_is_reached_is_met(tmp_path):               # G40, done 1
    """h is started (``doing``). k waits on h through ``after`` (``starts_at: [doing]``), m through ``blocked_by``
    (finish to start). Hand-worked: h > k is met (k is ready, h being in doing), h > m blocks (h is not done)."""
    p = project(tmp_path, DEPS.replace("blocked_by: ticket", "blocked_by: ticket\n      after: {projection: ticket, starts_at: [doing]}"))
    ev = p.events.add
    ev("ticket.planned", item="ticket/h", at=T0)
    ev("ticket.started", item="ticket/h", at=T0 + 10)
    ev("ticket.planned", item="ticket/k", data={"after": "ticket/h"}, at=T0 + 20)
    ev("ticket.planned", item="ticket/m", data={"blocked_by": "ticket/h"}, at=T0 + 20)
    [r] = ask(p, {"source": "graph", "diagram": "dependency", "projection": "ticket"})
    assert "error" not in r, r
    assert dict(zip(r["edges"]["id"], r["edges"]["relation"], strict=True)) == {
        "ticket/h>ticket/k:after": "met", "ticket/h>ticket/m:blocked_by": "blocks"}


def test_graph_reads_are_charged_to_the_request_and_none_starts_late(tmp_path, monkeypatch):   # done 5; lesson 4
    """With one read of the event log a request: the process map reads it, the process map of one kind is refused, and the
    dependency graph (the item index) still answers. Past the request's deadline no graph is read at all."""
    from ergostat import process as pm
    from ergostat.query import engine
    p, calls, real = steps(tmp_path), [], pm.process
    monkeypatch.setattr(pm, "process", lambda *a, **k: calls.append(1) or real(*a, **k))
    monkeypatch.setattr(engine, "LOG_READS", 1)
    a, b, c = ask(p, {"source": "graph", "diagram": "process"}, {"source": "graph", "diagram": "process", "projection": "ticket"},
                  {"source": "graph", "diagram": "dependency"}, until=T0 + 600)
    assert "error" not in a and "error" not in c, (a, c)
    assert "already read the event log 1 times" in b["error"] and len(calls) == 1
    monkeypatch.setattr(graphs, "_KEPT", {})
    monkeypatch.setattr(engine, "REQUEST_SECONDS", -1.0)
    late = ask(p, {"source": "graph", "diagram": "process"}, {"source": "graph", "diagram": "dependency"}, until=T0 + 600)
    assert all("ran past" in r["error"] for r in late) and len(calls) == 1, late


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
    a, b = ask(p, {"source": "graph", "diagram": "dependency", "projection": "nope"}, {"source": "graph", "diagram": "service", "projection": "ticket"})
    assert "projection 'nope' is not in the model" in a["error"] and "takes no projection" in b["error"]
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
