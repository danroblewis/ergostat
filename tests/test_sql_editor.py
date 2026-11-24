"""Acceptance (sql-source-over-item-views): a SQL data source in a real browser, through the real ergostat server, on
a small record: a panel draws a SELECT over ``item_spans`` and says in its panel why a read of the index's own tables is
refused; the panel editor's query box highlights SQL and completes the source's views and their columns.

    uv run --with playwright==1.63.0 python -m pytest tests/test_sql_editor.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import textwrap
import time
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat.store import Project
from tests.ports import free_port

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("sq") / "sq"
    d.mkdir()
    home = d.parent / "home"
    (d / "ergostat.yaml").write_text(textwrap.dedent("""
        name: sq
        stocks:
          queue: {unit: tickets}
        items:
          ticket:
            id: ticket/*
            states: [open, doing, done]
            on: {ticket.started: doing, ticket.done: done}
            show: [owner]
        sources:
          record: {type: sql}
        """))
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ERGOSTAT_HOME", str(home))
        p = Project(mdl.load(d))
        now = time.time() - 600
        for i, steps in enumerate([("ticket.started", "ticket.done"), ("ticket.started",), ()]):
            p.events.add("ticket.opened", item=f"ticket/{i}", data={"owner": "ana"}, at=now + i)
            for j, t in enumerate(steps):
                p.events.add(t, item=f"ticket/{i}", at=now + 10 * (j + 1) + i)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)},
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
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    assert pg.errors == []
    ctx.close()


def panel(pid: str, text: str) -> dict:
    return {"id": pid, "title": pid, "note": "", "form": "table", "size": "m", "tall": False, "display": {},
            "queries": [{"id": "a", "source": "record", "text": text}]}


def test_a_sql_panel_draws_its_answer_and_a_read_of_the_index_says_why_it_is_refused(page, site):
    raw = json.dumps({"title": "SQL", "panels": [
        panel("open", "select state, count(*) as n from item_spans where \"left\" is null group by state"),
        panel("inside", "select count(*) as n from main.items")]}).encode()
    page.goto(f"{site}/dashboard?draft=" + base64.urlsafe_b64encode(raw).decode().rstrip("="))
    page.wait_for_function("""() => ['open', 'inside'].every((id) => {
        const s = document.querySelector(`[data-panel-id="${id}"]`)?.dataset.state; return s && s !== 'loading'; })""",
                           timeout=20000)
    shown = page.locator('[data-panel-id="open"]')
    assert shown.get_attribute("data-state") == "drawn", shown.inner_text()
    assert all(w in shown.inner_text() for w in ("doing", "done", "open")), shown.inner_text()
    refused = page.locator('[data-panel-id="inside"]')
    assert refused.get_attribute("data-state") == "error"
    assert "only a SELECT of the views is allowed, and this reads main.items" in refused.inner_text()


def picks(pg) -> list[tuple[str, str]]:
    pg.wait_for_selector(".pq-list:not([hidden]) .pq-pick", timeout=10000)
    return [(li.get_attribute("data-kind"), li.locator(".pq-pick-name").inner_text())
            for li in pg.locator(".pq-list .pq-pick").all()]


def test_the_query_box_highlights_sql_and_completes_views_and_their_columns(page, site):
    page.goto(site + "/dashboard")
    page.wait_for_function("() => typeof openPanelEditor === 'function'")
    page.evaluate("""() => openPanelEditor({ id: 'n', title: 'New', note: '', form: 'table', queries: [{ id: 'a' }],
                                             display: {}, size: 'm', tall: false }, {})""")
    page.wait_for_function("() => [...document.querySelectorAll('.pe-q select[data-slot=source] option')]"
                           ".some((o) => o.value === 'record')")
    page.locator('.pe-q select[data-slot="source"]').first.select_option("record")
    assert "Query (SQL)" in page.locator(".pe-q").first.inner_text()
    area = page.locator('.pe-q textarea[data-slot="text"]')
    area.click()
    page.keyboard.type("select count(*) as n from item_s")
    assert picks(page) == [("view", "item_spans"), ("view", "item_stages")]    # (and the stages' view)
    page.keyboard.type("p")
    assert picks(page) == [("view", "item_spans")]
    page.keyboard.press("Tab")
    assert area.input_value() == "select count(*) as n from item_spans"
    page.keyboard.type(" where sta")
    assert ("column", "state") in picks(page)
    page.keyboard.press("Enter")
    page.keyboard.type(" = 'doing' and ow")                   # not a column of item_spans: only the views named
    page.wait_for_timeout(500)
    assert page.locator(".pq-list:not([hidden]) .pq-pick").count() == 0
    page.keyboard.press("Backspace")
    page.keyboard.press("Backspace")
    page.keyboard.type("from ticket t where t.ow")
    assert picks(page) == [("column", "owner")]
    page.keyboard.press("Tab")
    hl = {k: page.locator(f".pq-hl .pq-{k}").all_inner_texts() for k in ("view", "function", "string", "number")}
    assert hl == {"view": ["item_spans", "ticket"], "function": ["count"], "string": ["'doing'"], "number": []}, hl
    assert "select" in page.locator(".pq-hl .pq-keyword").all_inner_texts()
    assert "owner" in page.locator(".pq-hl .pq-column").all_inner_texts()
