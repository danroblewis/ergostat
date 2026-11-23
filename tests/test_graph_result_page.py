"""Acceptance (graph-result-and-panel), the page's half, in a real browser with the real chart families: a graph answer
drawn by the graph family from a layout ELK works out in a Web Worker, one layout for one structure (a refresh moves no
node); the critical path heavy and its end beside the levelled end; an over-budget graph collapsed, saying so and
offering the matrix, which the heatmap draws; and what a graph cannot be trusted to say, said. The answers are the
server's own, from the hand-worked records of tests/test_graph_result_and_panel.py.

    uv run --with playwright==1.63.0 python -m pytest tests/test_graph_result_page.py
"""

from __future__ import annotations

import pytest

from ergostat.query import frames, graphs, parse
from tests import test_graph_result_and_panel as rec
from tests import test_plot_forms as forms
from tests.test_plot_forms import PAINTED, Site, config, playwright

browser = forms.browser                                    # (a fixture)
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")
PAGE = forms.PAGE.replace("</body>", '<script src="/static/plots-graph.js"></script></body>')
META = {"now": rec.T0 + 3000, "since": rec.T0 + 2100, "until": rec.T0 + 3000, "step": 225}
STATE = "(id) => document.querySelector(`[data-panel-id=\"${id}\"]`).dataset.state"
WARNED = "(id) => document.querySelector(`[data-panel-id=\"${id}\"] .panel-warning`)?.textContent || ''"
SAID = "(id) => document.querySelector(`[data-panel-id=\"${id}\"] .panel-message-text`)?.textContent || ''"
NODES = """(id) => [...document.querySelectorAll(`[data-panel-id="${id}"] .graph-node`)].map((g) =>
  [g.dataset.id, g.dataset.holds, g.getAttribute('class')])"""
EDGES = """(id) => [...document.querySelectorAll(`[data-panel-id="${id}"] .graph-edge`)].map((g) =>
  [g.dataset.id, g.getAttribute('class')])"""


class GraphSite(Site):
    """The chart families' page with the graph family; its routes are the context's, so the layout worker's own
    requests (its script, and the ELK bundle it loads) are served too."""

    def __init__(self, browser, width=1200, height=900):
        self.context = browser.new_context(viewport={"width": width, "height": height})
        self.page = self.context.new_page()
        self.errors, self.asked = [], []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.context.route(f"{forms.ORIGIN}/**", self.serve)
        self.page.goto(f"{forms.ORIGIN}/")

    def serve(self, route):
        if route.request.url.rstrip("/") == forms.ORIGIN:
            route.fulfill(content_type="text/html", body=PAGE)
        else:
            super().serve(route)


def graph_config(form="graph", pid="g"):
    return {**config(form, pid=pid), "queries": [{"id": "a", "source": "graph", "diagram": "dependency"}]}


def wired(out: dict, diagram="service") -> dict:
    return {**frames.framed(out, parse.Query(id="a", source="graph", agg="count", diagram=diagram)), "id": "a"}


@pytest.fixture
def dependency(tmp_path):
    graphs._KEPT.clear()
    [r] = rec.ask(rec.deps(tmp_path), {"source": "graph", "diagram": "dependency", "kind": "ticket"})
    return {**r, "id": "a"}


def many(n=50) -> dict:
    nodes = [{"id": f"agent:m{i}", "label": f"m{i}", "runs": i, "failing": i == 3} for i in range(n)]
    edges = [{"id": f"w{i}", "source": f"agent:m{i}", "target": f"agent:m{(i + 1) % n}", "seen": True, "declared": i % 2 == 0,
              "count": i + 1, "perHour": 1.0, "last": 1.0} for i in range(n)]
    return wired(graphs.drawn(*graphs.service({"nodes": nodes, "edges": edges, "since": 0, "until": 1})))


def test_a_dependency_graph_is_laid_out_in_a_worker_and_draws_its_critical_path(browser, dependency):   # charts 74, 75
    s = GraphSite(browser)
    try:
        s.mount(graph_config(), dependency, META)
        assert s.page.evaluate(STATE, "g") == "drawn"
        m = s.model()
        assert m["by"]["worker"] >= 1 and m["by"]["page"] == 0          # ELK in a Web Worker, never on the page's thread
        nodes = {i: c for i, _, c in s.page.evaluate(NODES, "g")}
        assert set(nodes) == {f"ticket/{x}" for x in "abcdefg"}
        assert {i for i, c in nodes.items() if "is-critical" in c} == {"ticket/a", "ticket/b"}
        edges = dict(s.page.evaluate(EDGES, "g"))
        assert "is-critical" in edges["ticket/a>ticket/b:blocked_by"] and "is-met" in edges["ticket/f>ticket/g:blocked_by"]
        warned = s.page.evaluate(WARNED, "g")
        assert "The critical path ends in 40m; levelled by each block's capacity, the work ends in 1h" in warned   # G42
        assert "heavy: the critical path" in m["notes"] and not any("not evidence" in x for x in m["notes"])
        before, laid = m["at"], m["by"]["worker"]
        changed = {**dependency, "nodes": {**dependency["nodes"], "label": [x.upper() for x in dependency["nodes"]["label"]]}}
        s.page.evaluate("([r, m]) => last.update([r], m)", [changed, META])
        s.page.wait_for_function("() => last.plotView.frame.paints > 1")
        after = s.model()
        assert after["at"] == before and after["by"]["worker"] == laid     # one layout for one structure: nothing moved
        assert not s.errors, s.errors
    finally:
        s.close()


def test_an_over_budget_graph_collapses_says_so_and_its_matrix_is_drawn_by_the_heatmap(browser):   # AG, chart 77
    r = many()
    s = GraphSite(browser)
    try:
        s.mount(graph_config(), r, META)
        nodes = s.page.evaluate(NODES, "g")
        assert len(nodes) == 40 and [h for i, h, _ in nodes if i == "other"] == ["11"]
        assert "is-unhealthy" in next(c for i, _, c in nodes if i == "other")     # m3 fails: its group is marked
        warned = s.page.evaluate(WARNED, "g")
        assert "50 nodes and 50 edges are more than the 40 and 100 a panel draws" in warned and "Draw it as a matrix" in warned
        assert "A route through two lines is not evidence that anything took it" in s.model()["notes"]       # G35
        s.mount(graph_config("heatmap", pid="m"), r, META)
        assert s.page.evaluate(STATE, "m") == "drawn" and s.page.evaluate(PAINTED, "m") > 2
        cells = s.model()["counts"]
        assert len(cells) == 50 and sum(map(sum, cells)) == sum(range(1, 51))      # every edge's weight, uncollapsed
        assert not s.errors, s.errors
    finally:
        s.close()


def test_what_the_graph_panel_cannot_draw_it_says(browser, dependency, tmp_path):  # done 3
    from tests.test_result_shapes import samples
    seq = {**dependency, "kind": "sequence"}
    (tmp_path / "shapes").mkdir()
    s = GraphSite(browser)
    try:
        misfit = {name: s.page.evaluate("([f, r]) => resultFrames.mismatch(plotForms()[f], [r])", ["graph", r])
                  for name, r in samples(tmp_path / "shapes").items()}
        assert misfit.pop("graph") is None                  # the graph family takes a graph, and nothing else
        assert all(w.startswith("Graph needs a graph; this result is ") and w.count(".") == 1 for w in misfit.values()), misfit
        s.mount(graph_config(pid="seq"), seq, META)
        assert s.page.evaluate(STATE, "seq") == "empty"
        assert s.page.evaluate(SAID, "seq").startswith("A sequence diagram is drawn on fixed axes")
        two = {**graph_config(pid="two"), "queries": [{"id": "a", "source": "graph", "diagram": "dependency"},
                                                      {"id": "b", "source": "graph", "diagram": "process"}]}
        s.page.evaluate("([c, rs, m]) => { const el = chartPanel(c); document.getElementById('page').append(el); el.update(rs, m); }",
                        [two, [dependency, {**dependency, "id": "b"}], META])
        s.page.wait_for_function("() => document.querySelector('[data-panel-id=\"two\"]').dataset.state !== 'loading'")
        assert s.page.evaluate(STATE, "two") == "empty" and "draws one graph" in s.page.evaluate(SAID, "two")
        assert s.page.evaluate("() => document.querySelectorAll('[data-panel-id=\"two\"] .graph-node').length") == 0
        assert not s.errors, s.errors
    finally:
        s.close()
