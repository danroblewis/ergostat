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


def test_the_default_dashboard_draws_the_diagram_and_each_query_panel_its_own_answer(browser, site):
    pg = opened(browser, site + "/dashboard")
    pg.wait_for_selector("#main .page.dash", timeout=WAIT)
    diagram = pg.locator(".panel.panel-form-diagram").first
    diagram.wait_for(timeout=WAIT)
    assert diagram.locator(".panel-title").inner_text() == "The system"
    diagram.locator("svg.canvas g.node").first.wait_for(timeout=WAIT)           # the model's parts, laid out and drawn
    assert diagram.locator("svg.canvas g.node").count() > 1
    assert diagram.get_by_role("link", name="Open on the Diagram page").get_attribute("href") == "/diagram"
    assert pg.locator(".panel:not(.panel-form-diagram)").count() >= 1            # the query panels beside it
    assert settled(pg, 2500) == []
    pg.close()


def test_a_diagram_panel_is_added_in_the_editor_and_kept(browser, site):
    pg = opened(browser, site + "/dashboard")
    pg.wait_for_selector("#main .page.dash", timeout=WAIT)
    pg.get_by_role("button", name="Edit", exact=True).first.click()
    pg.get_by_role("button", name="Add panel").click()
    editor = pg.locator("[aria-label='Edit panel']")
    editor.wait_for(timeout=WAIT)
    editor.get_by_label("Title").fill("Control")
    editor.get_by_label("Chart").select_option("diagram")
    editor.get_by_label("View").select_option("blocks")
    assert editor.get_by_role("button", name="Add query").count() == 0           # a diagram asks no query
    editor.get_by_role("button", name="Save panel").click()
    added = pg.locator(".panel.panel-form-diagram[aria-label='Control']")
    added.locator("svg.canvas.bd g.node").first.wait_for(timeout=WAIT)          # drawn as a block diagram
    assert settled(pg) == []
    pg.reload()                                                                 # kept in this browser
    pg.locator(".panel.panel-form-diagram[aria-label='Control']").wait_for(timeout=WAIT)
    pg.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('ergostat.dashboard.')).forEach(k => localStorage.removeItem(k))")
    pg.close()


def test_the_panel_editor_offers_exactly_the_two_sources_and_shows_what_a_shortcut_asked(browser, site):
    """The Source select lists promql and sql and nothing else (NOTES.md, 2026-11-25); a shortcut's preview shows the
    SQL it wrote."""
    pg = opened(browser, site + "/dashboard")
    pg.wait_for_selector("#main .page.dash", timeout=WAIT)
    pg.get_by_role("button", name="Edit", exact=True).first.click()
    pg.get_by_role("button", name="Add panel").click()
    pg.wait_for_selector("[aria-label='Edit panel']", timeout=WAIT)
    pg.get_by_role("button", name="Add query").click()
    source = pg.locator("select[aria-label='Source']").first
    source.wait_for(timeout=WAIT)
    pg.wait_for_function("() => document.querySelectorAll(\"select[aria-label='Source'] option\").length >= 2",
                         timeout=WAIT)
    assert source.locator("option").evaluate_all("os => os.map(o => o.value)") == ["promql", "sql"]
    source.select_option("sql")
    pg.locator("select[aria-label='Query']").first.select_option("counts")
    pg.get_by_role("button", name="Preview").click()
    pg.wait_for_selector(".pe-compiled code", timeout=WAIT)
    assert "from transitions" in pg.locator(".pe-compiled code").first.inner_text()
    assert settled(pg) == []
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


DECLARED = """
dashboards:
  ops:
    title: Ops board
    panels:
      - {panel: note, title: Read me, text: "What this board is **for**", size: s}
      - {panel: goals, title: Goals, size: m}
      - {panel: chart, title: Inbox, refs: [stock.inbox], size: m}
      - {panel: states, title: Ticket states, kind: ticket, size: m}
      - {panel: cycle-time, title: Ticket cycle time, kind: ticket, size: m}
      - {panel: items, title: Open tickets, kind: ticket, size: full}
      - {panel: diagram, title: Blocks, address: "/diagram?view=blocks", size: full}
"""


@pytest.fixture
def declared(tmp_path):
    p = project_with_items(tmp_path / EXAMPLE)
    p.model.path.write_text(p.model.path.read_text() + DECLARED)
    p = Project(mdl.load(p.model.path.parent))
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def test_a_declared_dashboard_draws_a_panel_of_every_kind(browser, declared):
    _, url = declared
    pg = opened(browser, url + "/dashboard?name=ops")
    assert heading(pg).startswith("Ops board")
    for kind in ("note", "goals", "chart", "states", "cycle-time", "items"):
        pg.locator(f".panel.panel-kind-{kind}").wait_for(timeout=WAIT)
    assert "for" in pg.locator(".panel-kind-note strong").inner_text()
    pg.locator(".panel-kind-goals table.loops tbody tr").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-chart canvas, .panel-kind-chart p.muted").first.wait_for(timeout=WAIT)   # drawn, or said empty
    pg.locator(".panel-kind-items table tbody tr").first.wait_for(timeout=WAIT)
    pg.locator(".panel.panel-form-diagram svg.canvas.bd g.node").first.wait_for(timeout=WAIT)
    assert pg.locator("select[aria-label='Dashboard'] option").all_inner_texts()[:1] == ["This browser's draft"]
    assert "Ops board" in pg.locator("select[aria-label='Dashboard'] option").all_inner_texts()
    assert settled(pg, 2500) == []
    pg.close()


def test_keep_sends_the_draft_and_accept_writes_it_to_the_model(browser, declared):
    p, url = declared
    pg = opened(browser, url + "/dashboard")
    pg.wait_for_selector("#main .page.dash .panel", timeout=WAIT)
    pg.get_by_role("button", name="Keep").click()
    box = pg.locator("[aria-label='Keep this dashboard']")
    box.locator(".diff").wait_for(timeout=WAIT)                                  # the dashboards: entry, shown first
    assert "dashboards" in p.model.path.read_text() and "overview:" not in p.model.path.read_text()   # nothing yet
    box.get_by_role("button", name="Accept").click()
    pg.wait_for_url("**/dashboard?name=overview", timeout=WAIT)
    assert "overview:" in p.model.path.read_text()
    pg.locator(".panel").first.wait_for(timeout=WAIT)
    assert settled(pg) == []
    pg.close()
