"""Acceptance (promql-editor): the panel editor's query box for a PromQL source, in a real browser, through the real
ergostat server, against stub Prometheus sources (tests/test_promql_suggest.py): a metric name, a label and a label value
completed; the text highlighted; a syntax error marked where the source said it is; Ctrl+Enter runs; the owner's
exploration pattern is the starting hint and runs; and the suggestions stay bounded on a source of 100,000 series.

    uv run --with playwright==1.63.0 python -m pytest tests/test_promql_editor.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from tests.ports import free_port
from tests.test_promql_suggest import Meta

playwright = pytest.importorskip("playwright.sync_api")

HINT = 'count by(__name__)({__name__=~".+"})'


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    kinds = {"prom": type("Small", (Meta,), {"seen": []}), "big": type("Big", (Meta,), {"big": True, "seen": []}),
             "rude": type("Rude", (Meta,), {"big": True, "obeys": False, "seen": []})}
    stubs = {n: ThreadingHTTPServer(("127.0.0.1", 0), k) for n, k in kinds.items()}
    for s in stubs.values():
        threading.Thread(target=s.serve_forever, daemon=True).start()
    d = tmp_path_factory.mktemp("pq") / "pq"
    d.mkdir()
    (d / "ergostat.yaml").write_text("name: pq\nstocks:\n  queue: {unit: tickets}\nsources:\n" + "".join(
        f"  {n}: {{type: prometheus, url: 'http://127.0.0.1:{s.server_address[1]}'}}\n" for n, s in stubs.items()))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            pytest.fail("the page never came up")
        yield url, kinds
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        for s in stubs.values():
            s.shutdown()
            s.server_close()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def editor(browser, site):
    """The panel editor open on a new panel, its query's source ``which``; yields (page, textarea)."""
    url, _ = site
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(url + "/dashboard")

    def open_on(which: str):
        pg.wait_for_function("() => typeof openPanelEditor === 'function'")
        pg.evaluate("""() => openPanelEditor({ id: 'n', title: 'New', note: '', form: 'line', queries: [{ id: 'a' }],
                                               display: {}, size: 'm', tall: false }, {})""")
        pg.wait_for_function(f"() => [...document.querySelectorAll('.pe-q select[data-slot=source] option')]"
                             f".some((o) => o.value === '{which}')")
        pg.locator('.pe-q select[data-slot="source"]').first.select_option(which)
        area = pg.locator('.pe-q textarea[data-slot="text"]')
        area.click()
        return area
    yield pg, open_on
    assert pg.errors == []
    ctx.close()


def picks(pg) -> list[tuple[str, str]]:
    pg.wait_for_selector(".pq-list:not([hidden]) .pq-pick", timeout=10000)
    return [(li.get_attribute("data-kind"), li.locator(".pq-pick-name").inner_text())
            for li in pg.locator(".pq-list .pq-pick").all()]


def shows(pg, name: str, kind: str) -> None:
    pg.wait_for_function("""([n, k]) => [...document.querySelectorAll('.pq-list:not([hidden]) .pq-pick')]
        .some((li) => li.dataset.kind === k && li.querySelector('.pq-pick-name').textContent === n)""",
                         arg=[name, kind], timeout=10000)


def test_a_metric_name_a_label_and_a_label_value_are_completed_against_the_source(editor, site):
    pg, open_on = editor
    area = open_on("prom")
    pg.keyboard.type("http_r")
    shows(pg, "http_requests_total", "metric")
    pg.keyboard.press("Tab")
    assert area.input_value() == "http_requests_total"
    pg.keyboard.type("{")
    shows(pg, "job", "label")
    assert ("label", "code") in picks(pg) and ("label", "instance") not in picks(pg)     # this metric's labels only
    pg.keyboard.type("j")
    shows(pg, "job", "label")
    assert [n for _, n in picks(pg)] == ["job"]
    pg.keyboard.press("Enter")
    assert area.input_value() == "http_requests_total{job"
    pg.keyboard.type('="')
    shows(pg, "worker", "value")
    assert [n for _, n in picks(pg)] == ["api", "worker"]
    pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Enter")
    assert area.input_value() == 'http_requests_total{job="worker"'      # the value, and its closing quote
    pg.keyboard.type("}")
    hl = {k: pg.locator(f".pq-hl .pq-{k}").all_inner_texts() for k in ("metric", "label", "string", "punct")}
    assert hl["metric"] == ["http_requests_total"] and hl["label"] == ["job"] and hl["string"] == ['"worker"']
    pg.keyboard.press("Home")
    pg.keyboard.type("rat")
    shows(pg, "rate", "function")                                   # PromQL's own words too
    pg.keyboard.press("Enter")
    assert area.input_value().startswith('rate(http_requests_total{job="worker"}')
    assert pg.locator(".pq-hl .pq-function").all_inner_texts() == ["rate"]


def pick(pg, name: str) -> None:
    """Choose ``name`` in the open list with the arrow keys and Enter, as one would by hand."""
    n = [x for _, x in picks(pg)].index(name)
    for _ in range(n):
        pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Enter")


def test_code_editor_lists_open_before_anything_is_typed_and_the_panel_answers(editor, site):
    """promql-code-editor done 1: a metric, a label name and a label value each picked from a list (the label's and the
    value's opening at an empty prefix: after "{" and after a bare "="), and the panel draws the query's answer."""
    pg, open_on = editor
    _, kinds = site
    area = open_on("prom")
    pg.keyboard.type("http_r")
    shows(pg, "http_requests_total", "metric")
    pick(pg, "http_requests_total")
    pg.keyboard.type("{")
    shows(pg, "job", "label")                                     # (nothing typed after the brace)
    pick(pg, "job")
    pg.keyboard.type("=")
    shows(pg, "worker", "value")                                  # (no quote typed: it is put in)
    assert [n for _, n in picks(pg)] == ["api", "worker"]
    pick(pg, "worker")
    assert area.input_value() == 'http_requests_total{job="worker"'
    pg.keyboard.type("}")
    want = 'http_requests_total{job="worker"}'
    assert pg.locator(".pq-hl .pq-match").all_inner_texts() == ["{", "}"]   # the brace at the caret and its match
    assert pg.locator(".pq-lines").inner_text().split() == ["1"]
    asked = lambda: any(a.get("query") == want for _, path, a in kinds["prom"].seen if path == "/api/v1/query_range")  # noqa: E731
    deadline = time.monotonic() + 10
    while not asked() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert asked()                                                # the panel's preview asked the source the query typed
    pg.wait_for_function("() => document.querySelector('.pe-preview [data-state]')?.dataset.state === 'drawn'", timeout=10000)
    assert pg.locator(".pe-q-msg").inner_text().strip() == ""
    pg.keyboard.press("Control+Home")
    pg.keyboard.type("rate(")
    pg.keyboard.press("Control+Space")                            # asked for: the metrics at an empty prefix
    shows(pg, "up", "metric")
    pg.keyboard.press("Escape")
    assert pg.locator(".pq-list:not([hidden])").count() == 0
    assert area.input_value() == "rate(" + want


def test_code_editor_numbers_lines_matches_brackets_and_marks_the_refusal(editor, site):
    """promql-code-editor done 2: a refused query of two lines marked at the place the source names, with its lines
    numbered and the bracket at the caret drawn with its own match (or as unmatched)."""
    pg, open_on = editor
    area = open_on("prom")
    text = "sum(rate(up[5m]))\n  $ 2"
    area.fill(text)
    err = pg.locator(".pq-hl .pq-err")
    err.wait_for(timeout=10000)
    assert err.inner_text() == "$" and err.get_attribute("data-at") == str(text.index("$"))
    assert "2:3: parse error" in err.get_attribute("title")
    assert pg.locator(".pq-lines").inner_text().split() == ["1", "2"]
    pg.keyboard.press("Control+Home")
    pg.keyboard.press("End")                                      # after the last ")" of line 1: it closes sum's "("
    match = pg.locator(".pq-hl .pq-match")
    assert match.all_inner_texts() == ["(", ")"]
    assert match.first.evaluate("(s) => s.previousSibling.textContent") == "sum"
    pg.keyboard.press("ArrowLeft")                                # after the one before it: it closes rate's
    assert match.first.evaluate("(s) => s.previousSibling.textContent") == "rate"
    assert err.count() == 1                                       # (moving the caret keeps the mark)
    area.fill("sum(up(")
    pg.keyboard.press("End")
    assert pg.locator(".pq-hl .pq-nomatch").all_inner_texts() == ["("] and match.count() == 0


def test_code_editor_page_loads_with_nothing_asked_beyond_ergostat(browser, site):
    """promql-code-editor done 3: every request not to ergostat's own server is refused, and the page still loads and
    the query box mounts, highlights and completes."""
    url, _ = site
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    outside, errors = [], []
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(url + "/") else (outside.append(r.request.url), r.abort()))
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        pg.goto(url + "/dashboard")
        pg.wait_for_function("() => typeof openPanelEditor === 'function' && !!window.codeBox && !!window.queryEditors?.PromQL")
        pg.evaluate("""() => openPanelEditor({ id: 'n', title: 'New', note: '', form: 'line', queries: [{ id: 'a' }],
                                               display: {}, size: 'm', tall: false }, {})""")
        pg.wait_for_function("() => [...document.querySelectorAll('.pe-q select[data-slot=source] option')]"
                             ".some((o) => o.value === 'prom')")
        pg.locator('.pe-q select[data-slot="source"]').first.select_option("prom")
        pg.locator('.pe-q textarea[data-slot="text"]').click()
        pg.keyboard.type("up{")
        shows(pg, "job", "label")
        assert pg.locator(".pq-hl .pq-metric").all_inner_texts() == ["up"]
        assert pg.locator(".pq-lines").is_visible()
        assert outside == [] and errors == []
    finally:
        ctx.close()


def test_a_syntax_error_is_marked_where_the_source_says_it_is_and_ctrl_enter_runs(editor, site):
    pg, open_on = editor
    _, kinds = site
    area = open_on("prom")
    text = "sum(rate(up[5m]))\n  $ 2"
    area.fill(text)
    err = pg.locator(".pq-hl .pq-err")
    err.wait_for(timeout=10000)
    assert err.inner_text() == "$" and err.get_attribute("data-at") == str(text.index("$"))
    assert "2:3: parse error: unexpected character" in err.get_attribute("title")
    assert area.get_attribute("aria-invalid") == "true"
    assert "unexpected character" in pg.locator(".pe-q-msg").inner_text()
    assert pg.locator(".pq-hl .pq-number").all_inner_texts() == ["5m", "2"]
    assert pg.locator(".pq-hl .pq-function").all_inner_texts() == ["sum", "rate"]
    pg.keyboard.press("End")
    pg.keyboard.type(" ")                                          # edited: the old place no longer holds
    assert err.count() == 0
    area.fill("sum(up)")
    asked = lambda: sum(1 for _, path, a in kinds["prom"].seen if path == "/api/v1/query_range" and a["query"] == "sum(up)")  # noqa: E731
    pg.wait_for_function("() => document.querySelector('.pe-preview [data-state]')?.dataset.state === 'drawn'", timeout=10000)
    before = asked()
    assert before >= 1
    area.press("Control+Enter")                                    # asked again, though nothing changed
    deadline = time.monotonic() + 5
    while asked() == before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert asked() > before                                        # (nothing else asks: the preview was drawn, unchanged)


def test_a_syntax_error_after_non_ascii_text_is_marked_where_it_is(editor, site):
    """Prometheus's column counts bytes: "é" is two and "🙂" four (and two UTF-16 units), so the mark must not drift."""
    pg, open_on = editor
    area = open_on("prom")
    text = '# naïve\nsum(up{job="café 🙂"}) $ 2'
    area.fill(text)
    err = pg.locator(".pq-hl .pq-err")
    err.wait_for(timeout=10000)
    assert "2:27: parse error" in err.get_attribute("title")      # 26 bytes before "$" on its line
    assert err.inner_text() == "$" and err.get_attribute("data-at") == str(len(text[:text.index("$")].encode("utf-16-le")) // 2)


def test_the_owners_exploration_pattern_is_the_starting_hint_and_runs(editor, site):
    pg, open_on = editor
    _, kinds = site
    area = open_on("prom")
    assert area.get_attribute("placeholder") == HINT
    assert HINT in pg.locator(".pq-hint").inner_text()
    area.fill(HINT)
    area.press("Control+Enter")
    pg.wait_for_function("() => document.querySelector('.pe-preview [data-state]')?.dataset.state === 'drawn'", timeout=10000)
    assert pg.locator(".pe-q-msg").inner_text().strip() == ""
    assert any(a.get("query") == HINT for _, path, a in kinds["prom"].seen if path == "/api/v1/query_range")
    assert pg.locator(".pq-hl .pq-function").all_inner_texts() == ["count"]
    assert pg.locator(".pq-hl .pq-label").all_inner_texts() == ["__name__", "__name__"]
    area.fill('count by(__name__)({__name__=~"h')                 # inside its braces: the label's values are offered
    shows(pg, "http_requests_total", "value")
    area.fill("count by(")                                         # a grouping's labels
    shows(pg, "job", "label")
    area.fill("count by(job, in")
    shows(pg, "instance", "label")
    assert [n for _, n in picks(pg)] == ["instance"]


def test_a_query_moved_to_another_source_completes_from_that_source(editor):
    pg, open_on = editor
    area = open_on("prom")
    pg.keyboard.type("u")
    shows(pg, "up", "metric")                                      # (prom's names: none starts m_)
    pg.locator('.pe-q select[data-slot="source"]').first.select_option("big")
    area = pg.locator('.pe-q textarea[data-slot="text"]')
    area.fill("")
    area.click()
    pg.keyboard.type("m_0000")
    shows(pg, "m_00000", "metric")                                 # asked of big, the query's source now


@pytest.mark.parametrize("source", ["big", "rude"])
def test_autocomplete_stays_bounded_on_a_source_of_100000_series(editor, site, source):
    pg, open_on = editor
    open_on(source)
    t0 = time.monotonic()
    pg.keyboard.type("m_")
    shows(pg, "m_00000", "metric")
    took = time.monotonic() - t0
    got = picks(pg)
    assert len(got) == 100 and all(k == "metric" for k, _ in got)
    assert pg.locator(".pq-list .pq-more").count() == 1
    pg.keyboard.type("1234")
    shows(pg, "m_12340", "metric")
    assert [n for _, n in picks(pg)] == [f"m_1234{i}" for i in range(10)]
    pg.keyboard.type('{id="')
    shows(pg, "00000", "value")
    assert len(picks(pg)) == 100
    assert took < 5, took
