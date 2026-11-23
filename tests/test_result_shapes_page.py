"""Acceptance (chart-result-shapes), the page's half, in a real browser with the real chart families: the table of every
family against every shape, each cell drawn or refused in one sentence (done 1); switching among the charts that apply,
in the editor and its dialog, never asks the server again (done 2); a PromQL and a SQL answer of one shape draw the same
chart (done 3); and the reshaping steps (pivot, join, group).

    uv run --with playwright==1.63.0 python -m pytest tests/test_result_shapes_page.py
"""

from __future__ import annotations

import base64
import json

import pytest

from tests import test_plot_forms as forms
from tests import test_result_shapes as shapes
from tests.test_data_sources import T as PT
from tests.test_panel_editor import FIELDS
from tests.test_plot_forms import ORIGIN, PAINTED, STATIC, TYPES, Site, config, playwright
from tests.test_query_axes import T
from tests.test_result_shapes import from_source, same_shape_answers, samples

browser, prom, sql = forms.browser, shapes.prom, shapes.sql     # (fixtures)
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

META = {"now": T + 480, "since": T, "until": T + 480, "step": 120}
FAMILIES = ["line", "bar", "stat", "table", "scatter", "phase", "histogram", "box", "heatmap", "candlestick", "bode", "nyquist",
            "pole-zero"]
# The table of docs/research/2026-11-23-charts/catalog.md §2.5, as built (its differences are in dev/records/chart-result-shapes.md)
TAKES = {
    "series": {"line", "bar", "stat", "table", "histogram"},
    "two-signals": {"line", "bar", "scatter", "phase"},
    "candles": {"candlestick"},
    "table": {"bar", "table"},
    "table-one-row": {"bar", "stat", "table"},
    "table-numeric": {"line", "bar", "table"},
    "table-two-measures": {"bar", "table", "scatter"},
    "table-two-dims": set(),
    "points": {"line", "scatter", "heatmap"},
    "points-in-time": {"line", "scatter", "phase", "heatmap"},
    "bins": {"bar", "histogram"},
    "samples": {"histogram", "box"},
    "quartiles": {"box"},
    "survival": set(),
    "over-time": {"bar", "histogram", "heatmap"},       # (result-frames-and-verdicts: a Prometheus histogram's buckets)
    "graph": {"table", "heatmap"},                      # (its edges a row each; its matrix. The graph family: test_graph_result_page)
    "frequency": {"bode", "nyquist"},
    "model": {"bode", "nyquist", "pole-zero"},
}
STATE = "(id) => document.querySelector(`[data-panel-id=\"${id}\"]`).dataset.state"
SAID = "(id) => document.querySelector(`[data-panel-id=\"${id}\"] .panel-message-text`)?.textContent || ''"
MISFIT = "([f, r]) => resultFrames.mismatch(plotForms()[f], [r])"


@pytest.mark.slow
def test_every_chart_family_against_every_shape(browser, tmp_path):            # done 1
    got = samples(tmp_path)
    assert set(got) == set(TAKES)
    s = Site(browser)
    try:
        assert sorted(s.page.evaluate("() => Object.keys(plotForms())")) == sorted(FAMILIES)
        labels = s.page.evaluate("() => Object.fromEntries(Object.entries(plotForms()).map(([k, f]) => [k, f.label]))")
        wrong = []
        for name, result in got.items():
            for family in FAMILIES:
                pid = f"{name}-{family}"
                why = s.page.evaluate(MISFIT, [family, result])
                if (why is None) != (family in TAKES[name]):
                    wrong.append((name, family, why))
                s.mount(config(family, pid=pid), result, META)
                s.page.wait_for_timeout(30)
                state, said = s.page.evaluate(STATE, pid), s.page.evaluate(SAID, pid)
                if family in TAKES[name]:
                    if state != "drawn" or s.page.evaluate(PAINTED, pid) <= 2:
                        wrong.append((name, family, f"not drawn: {state} {said}"))
                    if family == "table" and result["shape"] == "table":      # a row a dimension's value and measure
                        rows = s.page.evaluate("(id) => document.querySelectorAll(`[data-panel-id=\"${id}\"] tbody tr`).length", pid)
                        if rows != len(result["rows"]) * len(result["measures"]):
                            wrong.append((name, family, f"{rows} rows drawn of {len(result['rows'])}"))
                elif not (state == "empty" and said == why and why.startswith(f"{labels[family]} needs ")
                          and "; this result is " in why and why.endswith(".") and why.count(".") == 1):
                    wrong.append((name, family, f"refused as {state}: {said!r}, not in one sentence {why!r}"))
                s.clear()
        assert wrong == [], "\n".join(map(str, wrong))
        s.mount(config("stat", pid="one"), got["table-one-row"], META)                # the one row's value, as given
        assert s.page.locator('[data-panel-id="one"] .panel-stat-num').all_inner_texts() == ["3.00 items"]
        assert not s.errors, s.errors
    finally:
        s.close()


def test_a_mismatch_names_its_fix(browser, tmp_path):
    got = samples(tmp_path)
    s = Site(browser)
    try:
        said = lambda f, n: s.page.evaluate(MISFIT, [f, got[n]])  # noqa: E731
        assert said("phase", "series") == ("Phase portrait needs two signals, an input and an output or points in time order; this "
                                           "result is values over time: add a second query and use it as this one's X, so the two "
                                           "are paired in time.")
        assert said("bar", "table-two-dims").endswith("this result is a table of 2 dimensions, 1 measure and 3 rows: pivot it by "
                                                      "state (Reshape: pivot state).")
        assert "set the query's aggregation to ohlc" in said("candlestick", "series")
    finally:
        s.close()


def test_a_promql_and_a_sql_result_of_one_shape_draw_the_same_chart(browser, tmp_path, prom, sql):   # done 3
    a, b = same_shape_answers(tmp_path, prom)
    meta = {"now": PT + 480, "since": PT, "until": PT + 480, "step": 120}
    s = Site(browser)
    try:
        applies = "(r) => Object.keys(plotForms()).filter((f) => !resultFrames.mismatch(plotForms()[f], [r]))"
        drawn = s.page.evaluate(applies, a)
        assert drawn == s.page.evaluate(applies, b) and set(drawn) == TAKES["series"]
        picture = """(id) => { const p = document.querySelector(`[data-panel-id="${id}"]`);
          return [p.dataset.state, [...p.querySelectorAll('canvas')].map((c) => c.toDataURL()).join(), p.textContent]; }"""
        for family in drawn:
            pics = []
            for r in (a, b):
                s.mount(config(family, pid="same"), {**r, "id": "a"}, meta)
                s.page.wait_for_timeout(30)
                pics.append(s.page.evaluate(picture, "same"))
                s.clear()
            assert pics[0][0] == "drawn" and pics[0] == pics[1], family
        assert not s.errors, s.errors
    finally:
        s.close()


EDITOR = ('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/style.css">'
          '<link rel="stylesheet" href="/static/panels.css"><link rel="stylesheet" href="/static/plots.css">'
          '<link rel="stylesheet" href="/static/panel-editor.css"></head><body><main id="main"></main>'
          + "".join(f'<script src="/static/{n}"></script>' for n in [
              "elk.bundled.js", "uplot/uPlot.iife.min.js", "util.js", "charts.js", "frames.js", "panels.js",
              *[f"plots-{n}.js" for n in ["math", "frame", "xy", "bar", "dist", "heat", "candle", "freq"]], "panel-editor.js"])
          + "</body></html>")


class Editor:
    """The real editor and charts, with the server's answers given: ``asked`` is every query request the page made."""

    def __init__(self, browser, answers: dict):
        self.context = browser.new_context(viewport={"width": 1400, "height": 900})
        self.page = self.context.new_page()
        self.asked: list[dict] = []
        self.errors: list[str] = []
        self.answers = answers
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.route(f"{ORIGIN}/**", self.serve)
        self.page.goto(f"{ORIGIN}/")

    def serve(self, route):
        path = route.request.url[len(ORIGIN):].split("?")[0]
        if path == "/":
            route.fulfill(content_type="text/html", body=EDITOR)
        elif path.startswith("/static/"):
            f = STATIC / path.removeprefix("/static/")
            route.fulfill(content_type=TYPES.get(f.suffix, "text/plain"), body=f.read_bytes())
        elif path == "/api/query/fields":
            route.fulfill(json={**FIELDS, "datasources": [{"name": "warehouse", "type": "sql", "language": "SQL"}]})
        elif path == "/api/query":
            raw = route.request.url.split("?q=", 1)[1]
            body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
            self.asked.append(body)
            got = [{**self.answers[q.get("text") or q.get("field")], "id": q["id"]} for q in body["queries"]]
            route.fulfill(json={**META, "results": got})
        else:
            route.fulfill(status=404, body="")

    def preview(self) -> tuple:
        return self.page.evaluate("() => { const p = document.querySelector('.pe-preview .panel');"
                                  " return [p?.dataset.state, p?.className]; }")


@pytest.mark.parametrize("query,answer", [
    ({"source": "warehouse", "text": "SELECT t, up FROM up"}, "series"),
    ({"source": "items", "kind": "gap", "field": "tokens", "x": {"type": "field", "field": "ai_cost_usd"}}, "points"),
])
def test_switching_among_applicable_charts_never_asks_again(browser, tmp_path, query, answer):      # done 2
    got = samples(tmp_path)
    e = Editor(browser, {query.get("text") or query.get("field"): got[answer]})
    try:
        e.page.evaluate("(q) => openPanelEditor({ id: 'p', title: 'Shapes', form: 'line', queries: [{ id: 'a', ...q }],"
                        " display: {} }, {})", query)
        e.page.wait_for_function("() => document.querySelector('.pe-preview .panel')?.dataset.state === 'drawn'", timeout=15000)
        assert len(e.asked) == 1
        open_ = e.page.evaluate("() => [...document.querySelectorAll('.pe-form')].filter((t) => !t.querySelector('input').disabled)"
                                ".map((t) => t.dataset.form)")
        assert set(open_) == TAKES[answer]
        blocked = e.page.locator('.pe-form[data-form="bode"]')
        assert blocked.locator("input").is_disabled() and blocked.get_attribute("title").startswith("Bode plot needs a frequency response;")
        for form in [*open_, open_[0]]:
            e.page.locator(f'.pe-form[data-form="{form}"]').click()
            e.page.wait_for_timeout(400)                      # past the preview's debounce
            state, cls = e.preview()
            assert state == "drawn" and f"panel-form-{form}" in cls, (form, state)
        e.page.locator(".pe-pick-open").click()
        e.page.wait_for_selector(".pe-pick-card")
        picked = e.page.evaluate("() => [...document.querySelectorAll('.pe-pick-card')].map((c) => c.dataset.form)")
        assert set(picked) <= set(open_) and len(picked) >= 2
        e.page.locator(f'.pe-pick-card[data-form="{picked[-1]}"] button').click()
        e.page.wait_for_timeout(400)
        assert f"panel-form-{picked[-1]}" in e.preview()[1]
        assert len(e.asked) == 1, e.asked                      # one question, for every chart drawn from it
        assert e.errors == []
    finally:
        e.context.close()


def test_the_editors_reshaping_opens_the_charts_it_makes_fit_without_asking_again(browser, tmp_path):
    got = samples(tmp_path)
    e = Editor(browser, {"SELECT kind, state, n": got["table-two-dims"]})
    try:
        e.page.evaluate("() => openPanelEditor({ id: 'p', title: 'Kinds', form: 'bar', queries: [{ id: 'a', source: 'warehouse',"
                        " text: 'SELECT kind, state, n' }], display: {} }, { onChange: (c) => { window.__last = c; } })")
        e.page.wait_for_function("() => document.querySelector('.pe-form[data-form=bar] input')?.disabled", timeout=15000)
        assert "Reshape: pivot state" in e.page.locator(".pe-form-guide").inner_text()
        e.page.locator('textarea[data-slot="reshape"]').fill("pivot state")
        e.page.wait_for_function("() => document.querySelector('.pe-preview .panel')?.dataset.state === 'drawn'", timeout=5000)
        assert not e.page.locator('.pe-form[data-form="bar"] input').is_disabled()
        assert e.page.evaluate("() => window.__last.reshape") == "pivot state" and len(e.asked) == 1
        assert e.errors == []
    finally:
        e.context.close()


def test_pivot_join_and_group_reshape_a_table_on_the_page(browser, tmp_path):
    got = samples(tmp_path)
    two = got["table-two-dims"]
    other = from_source({"shape": "table", "dims": [{"name": "kind", "type": "string"}], "measures": [{"name": "age", "unit": "h"}],
                         "rows": [["ticket", 30], ["note", 2], ["page", 9]]})
    s = Site(browser)
    try:
        run = lambda text, rs: s.page.evaluate("([t, rs]) => resultFrames.reshaped(t, rs)", [text, rs])  # noqa: E731
        [p] = run("pivot state", [two])
        assert [d["name"] for d in p["dims"]] == ["kind"] and [m["name"] for m in p["measures"]] == ["open", "done"]
        assert p["rows"] == [["ticket", 3, 2], ["note", 1, None]]
        [g] = run("group kind", [two])
        assert g["rows"] == [["ticket", 5], ["note", 1]]
        [j] = run("join kind", [{**p, "id": "a"}, {**other, "id": "b"}])
        assert [m["name"] for m in j["measures"]] == ["open", "done", "age"] and j["rows"] == [["ticket", 3, 2, 30], ["note", 1, None, 2]]
        assert "is not a step" in run("melt kind", [two])[0]["error"]
        assert "needs a table with state" in run("pivot state", [got["series"]])[0]["error"]
        s.mount({**config("bar", pid="pv"), "reshape": "pivot state"}, two, META)     # the panel draws it reshaped
        assert s.page.evaluate(STATE, "pv") == "drawn" and s.page.evaluate(PAINTED, "pv") > 2
        s.mount(config("bar", pid="raw"), two, META)
        assert s.page.evaluate(STATE, "raw") == "empty" and "Reshape: pivot state" in s.page.evaluate(SAID, "raw")
        assert not s.errors, s.errors
    finally:
        s.close()
