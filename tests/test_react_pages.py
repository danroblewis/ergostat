"""The page's smoke suite: the React app (ergostat/web/ui, built into static/app), served by ``web.serve`` for a small
project with items on its record, opened in Chromium at each page's path. Each page draws its heading and its content,
and none raises an error in the page or gets a server error from the API.

It needs Playwright and a Chromium, so the unit run skips it:

    uv run --with playwright==1.63.0 python -m pytest -q tests/test_react_pages.py
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from urllib.parse import quote

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from ergostat.web import server as ws

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "first-loop"
ITEM = "ticket/1"
KIND = """
items:
  ticket:
    id: ticket/*
    states: [opened, working, done]
    on: {ticket.opened: opened, ticket.working: working, ticket.done: done}
"""
WAIT = 20_000                      # ms: a page's first answers on a busy machine

pytestmark = pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")


def project_with_items(d: Path) -> Project:
    """The first loop, with a few readings and three tickets on its record (one finished)."""
    shutil.copytree(ROOT / "examples" / EXAMPLE, d, ignore=shutil.ignore_patterns("run", "__pycache__", "inbox"))
    f = d / "ergostat.yaml"
    f.write_text(f.read_text() + KIND)
    p = Project(mdl.load(d))
    now = time.time()
    for i in range(6):
        p.measurements.add("sensor/inbox", 10.0 + i, now - 300 + 50 * i)
    for n, states in ((1, ("opened", "working")), (2, ("opened",)), (3, ("opened", "working", "done"))):
        for j, s in enumerate(states):
            p.events.add(f"ticket.{s}", item=f"ticket/{n}", data={"state": s, "title": f"ticket {n}"},
                         at=now - 600 + 60 * n + 10 * j)
    return p


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    p = project_with_items(tmp_path_factory.mktemp("react") / EXAMPLE)
    server, url = web.serve(p, 0)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as e:                        # no Chromium here
            pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


def opened(browser, url: str):
    """A new page at ``url``, with its page errors and the API's server errors kept in ``pg.errs``."""
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(f"page error: {e}"))
    pg.on("response", lambda r: errs.append(f"{r.status} {r.url}") if r.status >= 500 else None)
    pg.errs = errs
    pg.goto(url, wait_until="load")
    return pg


def heading(pg, selector: str = "#main h1") -> str:
    pg.wait_for_selector(selector, timeout=WAIT)
    return pg.locator(selector).first.inner_text()


def settled(pg, ms: int = 1500) -> list[str]:
    """The page's errors, after it has had a moment to draw what its first answers said."""
    pg.wait_for_timeout(ms)
    return pg.errs


def test_the_header_names_the_pages_dashboard_first_and_no_project_list(browser, site):
    pg = opened(browser, site + "/goals")
    pg.wait_for_selector("#nav a", timeout=WAIT)
    assert pg.locator("#nav a").all_inner_texts() == ["Dashboard", "Diagram", "Goals", "Agents", "Items", "Record"]
    assert pg.locator("select#project").count() == 0
    pg.wait_for_selector("#running", timeout=WAIT)          # the run state, from /api/status
    assert settled(pg) == []
    pg.close()


def test_the_dashboard_draws_its_panels(browser, site):
    pg = opened(browser, site + "/dashboard")
    assert heading(pg)
    pg.wait_for_selector("#main .page.dash", timeout=WAIT)
    assert settled(pg, 2500) == []
    pg.close()


@pytest.mark.parametrize("view, caption, nodes", [
    ("dynamics", "Stock-and-flow diagram", True),
    ("blocks", "Block diagram", True),
    ("process", "Process map", False),
])
def test_each_view_of_the_diagram_draws(browser, site, view, caption, nodes):
    pg = opened(browser, f"{site}/diagram?view={view}")
    assert caption in heading(pg, "#diagram-caption")
    if nodes:                                               # the model's parts, laid out and drawn
        pg.wait_for_selector("svg.canvas g.node", timeout=WAIT)
        assert pg.locator("svg.canvas g.node").count() > 1
    assert settled(pg) == []
    pg.close()


@pytest.mark.parametrize("path, title, content", [
    ("/goals", "Goals", "inbox-short"),
    ("/agents", "Agents", "worker"),
    ("/items", "Items", "ticket"),
    ("/record", "Record", "ticket"),
])
def test_each_list_page_draws_its_heading_and_its_rows(browser, site, path, title, content):
    pg = opened(browser, site + path)
    assert heading(pg).startswith(title)
    pg.wait_for_function(f"() => document.querySelector('#main').innerText.includes({content!r})", timeout=WAIT)
    assert settled(pg) == []
    pg.close()


def test_an_item_page_draws_the_item(browser, site):
    pg = opened(browser, f"{site}/item/{quote(ITEM, safe='')}")
    assert heading(pg) == ITEM
    pg.wait_for_function("() => document.querySelector('#main').innerText.includes('working')", timeout=WAIT)
    assert settled(pg) == []
    pg.close()


def test_a_removed_page_goes_to_the_diagram(browser, site):
    pg = opened(browser, site + "/diagram")
    heading(pg, "#diagram-caption")
    pg.evaluate("() => { history.pushState(null, '', '/check'); dispatchEvent(new PopStateEvent('popstate')); }")
    pg.wait_for_url("**/diagram", timeout=WAIT)              # (the server has no /check: the app routes it away)
    assert settled(pg) == []
    pg.close()


def test_model_errors_are_said_in_a_note_under_the_run_state(browser, tmp_path):
    p = project_with_items(tmp_path / EXAMPLE)
    server, url = web.serve(p, 0)
    try:
        f = p.model.path
        f.write_text(f.read_text() + "\ngoals:\n  broken: {stock: nowhere, hold: '<= 1'}\n")
        pg = opened(browser, url + "/goals")
        pg.wait_for_selector("button.model-errors", timeout=WAIT)
        assert "Model errors" in pg.locator("button.model-errors").inner_text()
        pg.locator("button.model-errors").click()
        note = pg.locator("#model-errors")
        note.wait_for(timeout=WAIT)
        assert note.inner_text().strip()
        assert settled(pg, 500) == []
        pg.close()
    finally:
        server.shutdown()
        server.server_close()
