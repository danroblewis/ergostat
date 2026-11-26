"""Pages that are dashboards (SPEC §4f): a dashboard with ``nav:`` in the header at /d/NAME; one with ``page:`` drawn in
that page's place, an agent's page bound to the address's agent; ?builtin=1 for ergostat's own page; the Goals page a
list of panels; and a draft started from a copy of a page."""

from __future__ import annotations

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from tests.test_react_pages import EXAMPLE, WAIT, browser, heading, opened, project_with_items, settled  # noqa: F401

pytestmark = pytest.mark.slow

BOARD = """
dashboards:
  crew:
    title: The crew
    nav: Crew
    panels:
      - {panel: ladder, size: full, fit: true}
  my-goals:
    title: My goals
    page: goals
    panels:
      - {panel: goals, title: Just some, columns: [goal, status], size: full, fit: true}
  one-agent:
    title: One agent
    page: agent
    panels:
      - {panel: agent-what, agent: $agent, size: full, fit: true}
"""


@pytest.fixture
def boards(tmp_path):
    p = project_with_items(tmp_path / EXAMPLE)
    p.model.path.write_text(p.model.path.read_text() + BOARD)
    p = Project(mdl.load(p.model.path.parent))
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def test_a_nav_dashboard_is_in_the_header_at_its_own_address(browser, boards):
    _, url = boards
    pg = opened(browser, url + "/diagram")
    pg.wait_for_function("() => [...document.querySelectorAll('#nav a')].some((a) => a.textContent === 'Crew')", timeout=WAIT)
    assert pg.locator("#nav a").all_inner_texts() == ["Dashboard", "Diagram", "Goals", "Agents", "Items", "Record", "Crew"]
    pg.locator("#nav a", has_text="Crew").click()
    pg.wait_for_url("**/d/crew", timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('The crew')", timeout=WAIT)
    pg.locator(".panel.panel-kind-ladder").wait_for(timeout=WAIT)
    assert pg.locator("#nav a.on").inner_text() == "Crew"
    assert settled(pg) == []
    pg.close()


def test_a_page_declared_in_place_is_drawn_and_builtin_shows_ergostats_own(browser, boards):
    _, url = boards
    pg = opened(browser, url + "/goals")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('My goals')", timeout=WAIT)
    pg.locator(".panel-kind-goals table.loops tbody tr").first.wait_for(timeout=WAIT)
    assert pg.locator(".panel-kind-goals table.loops thead th").count() == 2      # columns: [goal, status]
    pg.get_by_role("link", name="ergostat's own page").click()
    pg.wait_for_url("**/goals?builtin=1", timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('Goals')", timeout=WAIT)
    pg.locator(".panel-kind-goals table.loops tbody tr").first.wait_for(timeout=WAIT)
    assert pg.locator(".panel-kind-goals table.loops thead th").count() > 2       # every column
    assert settled(pg) == []
    pg.close()


def test_an_agent_page_in_place_takes_its_agent_from_the_address(browser, boards):
    _, url = boards
    pg = opened(browser, url + "/agent/worker")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('One agent')", timeout=WAIT)
    pg.locator(".panel.panel-kind-agent-what").wait_for(timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('.panel-kind-agent-what')?.innerText.includes('Runs ls inbox')", timeout=WAIT)
    assert settled(pg) == []
    pg.close()


def test_the_goals_page_is_its_panels_and_a_click_keeps_the_goal_in_the_address(browser, boards):
    _, url = boards
    pg = opened(browser, url + "/goals?builtin=1")
    row = pg.locator(".panel-kind-goals table.loops tbody tr").first
    row.wait_for(timeout=WAIT)
    row.locator("td").first.click()
    pg.wait_for_url("**select=*", timeout=WAIT)
    assert pg.locator(".panel-kind-goals tr.on, .panel-kind-goals tr[aria-selected='true']").count() <= 1
    assert settled(pg) == []
    pg.close()


def test_a_draft_starts_from_a_copy_of_a_page(browser, boards):
    _, url = boards
    pg = opened(browser, url + "/dashboard")
    pg.wait_for_selector("#main .page.dash .panel", timeout=WAIT)              # the draft drawn: the project is known
    pg.locator("select[aria-label='Dashboard']").select_option("copy:agents")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('Agents')", timeout=WAIT)
    pg.locator(".panel.panel-kind-ladder").wait_for(timeout=WAIT)
    pg.locator(".panel.panel-kind-agents").wait_for(timeout=WAIT)
    pg.get_by_role("button", name="Keep").click()
    box = pg.locator("[aria-label='Keep this dashboard']")
    assert box.locator("select[aria-label='In place of a page']").input_value() == "agents"
    assert settled(pg) == []
    pg.close()
