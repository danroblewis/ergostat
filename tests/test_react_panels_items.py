"""The items group's panels in the page (SPEC §4f): each draws on a declared dashboard with no page error, and the
Items, Projection and Item pages, now drawn from them, still draw what they did, their filters in the address still work,
and their links lead where the page reads them.

    uv run --with playwright==1.63.0 python -m pytest -q tests/test_react_panels_items.py
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.spec import read
from ergostat.store import Project
from tests.test_react_pages import EXAMPLE, ITEM, WAIT, browser, heading, opened, project_with_items, settled, site  # noqa: F401

pytestmark = pytest.mark.skipif(not __import__("ergostat.web.server", fromlist=["STATIC"]).STATIC.joinpath(
    "app", "index.html").is_file(), reason="the React page is not built")

KINDS = ("projections", "items-by-projection", "projection-now", "projection-model", "projection-definition", "item-list", "item-summary", "item-why",
         "item-path", "item-relations", "item-fields", "item-refused", "item-moves", "item-events", "item-changes")
BOARD = """
dashboards:
  tickets:
    title: Tickets board
    panels:
      - {panel: projections, size: full}
      - {panel: items-by-projection, q: ticket, size: full}
      - {panel: projection-now, projection: ticket, states: all}
      - {panel: projection-model, projection: ticket}
      - {panel: projection-definition, projection: ticket}
      - {panel: item-list, projection: ticket, n: 25, size: full}
      - {panel: item-summary, item: ticket/1}
      - {panel: item-why, item: ticket/1}
      - {panel: item-path, item: ticket/1}
      - {panel: item-relations, item: ticket/1}
      - {panel: item-fields, item: ticket/1}
      - {panel: item-refused, item: ticket/1}
      - {panel: item-moves, item: ticket/1}
      - {panel: item-events, item: ticket/1}
      - {panel: item-changes, item: ticket/1, history: all}
"""
COUNTED = {"stocks:\n": "stocks:\n  open-tickets:\n    sensor: {projection: ticket, state: [opened, working]}\n",
           "goals:\n": "goals:\n  few-tickets: {stock: open-tickets, hold: \"< 10\"}\n",   # a stock that counts tickets
           "    states: [opened, working, done]\n": "    states: [opened, working, done]\n    show: [title]\n"}


def counted(text: str) -> str:
    for old, new in COUNTED.items():
        text = text.replace(old, new, 1)
    return text


@pytest.fixture(scope="module")
def board(tmp_path_factory):
    p = project_with_items(tmp_path_factory.mktemp("panels-items") / EXAMPLE)
    p.model.path.write_text(counted(p.model.path.read_text()) + BOARD)
    assert [x for x in read(p.model.path)[1] if x.level == "error"] == []
    p = Project(mdl.load(p.model.path.parent))
    server, url = web.serve(p, 0)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def test_every_items_kind_draws_on_a_declared_dashboard(browser, board):
    pg = opened(browser, board + "/dashboard?name=tickets")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('Tickets board')", timeout=WAIT)
    for kind in KINDS:
        pg.locator(f".panel.panel-kind-{kind}").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-projections .projection-card[data-projection=ticket]").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-item-list table tbody tr").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-item-events table tbody tr").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-item-path .track .stbox.on").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-projection-definition pre, .panel-kind-projection-definition code").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-item-changes table.history tbody tr").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-item-why .why").wait_for(timeout=WAIT)                     # ticket/1 is working
    assert "Nothing is recorded" not in pg.locator("#main").inner_text()
    assert settled(pg, 2500) == []
    pg.close()


def test_the_old_items_addresses_lead_to_each_projections_own(browser, board):
    for old, new in (("/items/ticket?state=opened", "**/ticket?state=opened"), ("/items?projection=ticket", "**/ticket?projection=ticket"),
                     ("/items", "**/diagram")):
        pg = opened(browser, board + old)
        pg.wait_for_url(new, timeout=WAIT)
        assert settled(pg, 500) == []
        pg.close()
    pg = opened(browser, board + "/tickets")                         # the board's projections panel: a card links to /PROJECTION
    pg.locator(".panel-kind-projections .projection-card[data-projection=ticket]").wait_for(timeout=WAIT)
    assert pg.locator(".projection-card[data-projection=ticket] a.pm-link").get_attribute("href") == "/diagram?view=process&projections=ticket"
    pg.close()


def test_the_projection_page_draws_its_panels_and_keeps_its_filters_in_the_address(browser, board):
    pg = opened(browser, board + "/ticket")
    pg.locator(".projection-bar h1").wait_for(timeout=WAIT)
    for kind in ("projection-now", "projection-model", "projection-definition", "item-list"):
        pg.locator(f".panel-kind-{kind}").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-item-list table tbody tr").first.wait_for(timeout=WAIT)
    assert pg.locator(".panel-kind-item-list table tbody tr").count() == 2          # ticket/3 is done: hidden
    # the links: the goal as the Goals page reads it, the part as the Diagram page reads it, the process map
    goal = pg.locator(".projection-goals a").first
    goal.wait_for(timeout=WAIT)
    assert goal.get_attribute("href") == "/goals?select=few-tickets"
    assert pg.locator(".projection-model a[href^='/diagram']").first.get_attribute("href") == "/diagram?around=stock%2Fopen-tickets"
    assert pg.locator(".panel-kind-projection-now a.pm-link").get_attribute("href") == "/diagram?view=process&projections=ticket"
    # the finished shown, from the panel's own note: into the address
    pg.locator(".finished-flip").click()
    pg.wait_for_url("**finished=show**", timeout=WAIT)
    pg.wait_for_function("() => document.querySelectorAll('.panel-kind-item-list table tbody tr').length === 3", timeout=WAIT)
    # a sort, by the header: into the address as PROJECTION:field
    pg.get_by_role("button", name="Sort by title").click()
    pg.wait_for_url("**sort=ticket%3Atitle**", timeout=WAIT)
    assert settled(pg) == []
    pg.close()
    # from the address: a state, a search, a page size, each state
    pg = opened(browser, board + "/ticket?state=opened")
    pg.locator(".panel-kind-item-list table tbody tr").first.wait_for(timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('.panel-kind-item-list tbody tr')].map((r) => r.innerText)"
                         ".join('|').includes('ticket/2')", timeout=WAIT)
    assert pg.locator(".panel-kind-item-list tbody tr").count() == 1
    assert "state opened" in pg.locator(".set-chip").inner_text()
    pg.close()
    pg = opened(browser, board + "/ticket?q=ticket%201&states=all&size=100")
    pg.wait_for_function("() => document.querySelector('.search-said')?.textContent.startsWith('1 match')", timeout=WAIT)
    assert pg.locator("[aria-label=States] button[aria-pressed=true]").inner_text() == "Every state"
    assert pg.locator("select[aria-label='Rows a page']").first.input_value() == "100"
    assert settled(pg) == []
    pg.close()


def test_the_item_page_draws_its_parts_and_opens_its_changes(browser, board):
    pg = opened(browser, f"{board}/ticket/1")
    assert heading(pg) == ITEM
    for kind in ("item-summary", "item-path", "item-fields", "item-moves", "item-events", "item-changes"):
        pg.locator(f".panel-kind-{kind}").wait_for(timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('#main')?.innerText.includes('working')", timeout=WAIT)
    assert pg.locator(".panel-kind-item-refused").count() == 0                     # nothing refused: not drawn
    assert pg.locator(".panel-kind-item-relations").count() == 0                   # no relations: not drawn
    assert pg.locator(".panel-kind-item-path a", has_text="what every ticket touches").get_attribute("href") == \
        "/diagram?projection=ticket"
    assert pg.locator(".panel-kind-item-changes table.history").count() == 0       # folded: not asked for
    pg.locator("#changes > summary").click()
    pg.locator(".panel-kind-item-changes table.history tbody tr").first.wait_for(timeout=WAIT)
    assert settled(pg) == []
    pg.close()
    pg = opened(browser, f"{board}/ticket/nope")
    pg.wait_for_function("() => document.querySelector('#main')?.innerText.includes('Nothing is recorded about this id')",
                         timeout=WAIT)
    pg.close()
