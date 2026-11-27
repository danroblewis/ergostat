"""Pages that are dashboards (SPEC §4f): a dashboard at its name, /NAME, in the header with ``nav:``; one named as
ergostat's page drawn there instead; one named as a projection that projection's page; ``page: agent`` drawn on every agent's page,
bound to the address's agent; ?builtin=1 for ergostat's own page; the Goals page a list of panels. And every dashboard
edited where it is drawn (SPEC §4f, *Editing in place*): a projection's list and show saved under the projection, the
Goals page as the dashboard goals, a new one from the nav bar's + saved with nav: true; Reset to ergostat's takes a
saved one out again."""

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
  goals:
    title: My goals
    panels:
      - {panel: goals, title: Just some, columns: [goal, status], size: full, fit: true}
  one-agent:
    title: One agent
    page: agent
    panels:
      - {panel: agent-what, agent: $agent, size: full, fit: true}
  ticket:
    title: Tickets, my way
    panels:
      - {panel: projection-now, projection: $projection, size: full, fit: true}
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
    pg = opened(browser, url + "/diagrams")
    pg.wait_for_function("() => [...document.querySelectorAll('#nav a')].some((a) => a.textContent === 'Crew')", timeout=WAIT)
    assert pg.locator("#nav a").all_inner_texts() == ["Overview", "Diagrams", "Goals", "Agents", "Events", "Crew",
                                                      "Ticket"]                 # the defaults, the model's, the projections
    pg.locator("#nav a", has_text="Crew").click()
    pg.wait_for_url("**/crew", timeout=WAIT)
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
    pg = opened(browser, url + "/agent/worker")                     # the old address: the agent's own
    pg.wait_for_url("**/agents/worker", timeout=WAIT)
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


def test_a_dashboard_named_as_a_projection_is_its_page_and_its_items_stay_under_it(browser, boards):
    _, url = boards
    pg = opened(browser, url + "/ticket")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('Tickets, my way')", timeout=WAIT)
    pg.locator(".panel.panel-kind-projection-now").wait_for(timeout=WAIT)
    pg.close()
    pg = opened(browser, url + "/ticket/1")                          # its items: the item page, under the projection's address
    assert heading(pg) == "ticket/1"
    pg.close()
    pg = opened(browser, url + "/big-board")                         # nothing of the model's there
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent === 'Nothing here'", timeout=WAIT)
    assert settled(pg) == []
    pg.close()


@pytest.fixture
def plain(tmp_path):
    p = project_with_items(tmp_path / EXAMPLE)
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def _edit(pg):
    pg.get_by_role("button", name="Edit", exact=True).first.click()
    pg.get_by_role("toolbar", name="Editing this dashboard").wait_for(timeout=WAIT)


def _add_note(pg, title: str, text: str):
    pg.get_by_role("button", name="Add panel").click()
    editor = pg.locator("[aria-label='Edit panel']")
    editor.wait_for(timeout=WAIT)
    editor.locator("select[aria-label='Panel']").select_option("note")
    editor.get_by_label("Title").fill(title)
    editor.locator("input[aria-label='text']").fill(text)
    editor.get_by_role("button", name="Save panel").click()
    pg.locator(f".panel[aria-label='{title}'], .panel:has-text('{text}')").first.wait_for(timeout=WAIT)


def _saved(pg):
    pg.get_by_role("button", name="Save", exact=True).click()
    pg.get_by_role("toolbar", name="Editing this dashboard").wait_for(state="detached", timeout=WAIT)


def test_a_projection_s_list_is_edited_in_place_saved_under_the_projection_and_reset(browser, plain):
    p, url = plain
    pg = opened(browser, url + "/ticket")
    pg.locator(".panel.panel-kind-item-list").wait_for(timeout=WAIT)
    _edit(pg)
    _add_note(pg, "About tickets", "Each ticket is a request.")
    _saved(pg)
    text = p.model.path.read_text()
    block = text.split("  ticket:\n")[1]
    assert "    dashboards:\n      list:\n        panels:\n" in block and "Each ticket is a request." in block
    assert '"projection": "$projection"' in block                       # ergostat's panels, as written for any projection
    pg.reload()
    pg.wait_for_function("() => document.querySelector('#main').innerText.includes('Each ticket is a request.')", timeout=WAIT)
    pg.locator(".panel.panel-kind-item-list table tbody tr").first.wait_for(timeout=WAIT)   # bound to ticket
    _edit(pg)
    pg.get_by_role("button", name="Reset to ergostat's").click()
    pg.get_by_role("toolbar", name="Editing this dashboard").wait_for(state="detached", timeout=WAIT)
    assert "dashboards:" not in p.model.path.read_text()
    pg.reload()
    pg.locator(".panel.panel-kind-item-list").wait_for(timeout=WAIT)
    assert "Each ticket is a request." not in pg.locator("#main").inner_text()
    assert settled(pg) == []
    pg.close()


def test_an_item_s_page_is_saved_as_its_projection_s_show_dashboard(browser, plain):
    p, url = plain
    pg = opened(browser, url + "/ticket/1")
    assert heading(pg) == "ticket/1"
    pg.locator(".panel.panel-kind-item-fields").wait_for(timeout=WAIT)
    _edit(pg)
    for t in ("item-why", "item-path", "item-relations", "item-refused", "item-moves", "item-events", "item-changes"):
        pg.locator(f".panel.panel-kind-{t}").first.wait_for(timeout=WAIT)
        n = pg.locator(f".panel.panel-kind-{t}").count()
        pg.locator(f".panel.panel-kind-{t} button[aria-label^='Remove']").first.click()
        pg.wait_for_function(f"() => document.querySelectorAll('.panel.panel-kind-{t}').length < {n}", timeout=WAIT)
    _saved(pg)
    show = p.model.path.read_text().split("  ticket:\n")[1]
    assert "      show:\n" in show and '"item": "$item"' in show and "item-events" not in show
    pg.close()
    pg = opened(browser, url + "/ticket/2")                              # every ticket's page: drawn so
    assert heading(pg).startswith("ticket/2")                           # (then its buttons)
    pg.locator(".panel.panel-kind-item-fields").wait_for(timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('.panel-kind-item-fields')?.innerText.includes('ticket 2')", timeout=WAIT)
    assert pg.locator(".panel.panel-kind-item-events").count() == 0
    assert settled(pg) == []
    pg.close()


def test_the_goals_page_is_saved_as_the_dashboard_goals_and_reset(browser, plain):
    p, url = plain
    pg = opened(browser, url + "/goals")
    pg.locator(".panel-kind-goals table.loops tbody tr").first.wait_for(timeout=WAIT)
    _edit(pg)
    pg.locator(".panel.panel-kind-goals button[aria-label^='Edit']").first.click()
    editor = pg.locator("[aria-label='Edit panel']")
    editor.get_by_label("Title").fill("My goals")
    editor.locator("input[aria-label='columns']").fill("goal, status")
    editor.get_by_role("button", name="Save panel").click()
    _saved(pg)
    text = p.model.path.read_text()
    assert "  goals:\n" in text.split("dashboards:")[1] and '"title": "My goals"' in text
    pg.wait_for_function("() => document.querySelectorAll('.panel-kind-goals table.loops thead th').length === 2", timeout=WAIT)
    assert pg.get_by_role("link", name="ergostat's own page").count() == 1       # drawn in the Goals page's place
    _edit(pg)
    pg.get_by_role("button", name="Reset to ergostat's").click()
    pg.wait_for_function("() => document.querySelectorAll('.panel-kind-goals table.loops thead th').length > 2", timeout=WAIT)
    assert "dashboards:" not in p.model.path.read_text()
    assert settled(pg) == []
    pg.close()


def test_the_nav_bar_s_plus_makes_a_new_dashboard_in_the_nav(browser, plain):
    p, url = plain
    pg = opened(browser, url + "/diagrams")
    pg.wait_for_selector("#nav a", timeout=WAIT)
    plus = pg.get_by_role("button", name="New dashboard")
    pg.locator("#nav").hover()
    plus.click()
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('New dashboard')", timeout=WAIT)
    _add_note(pg, "Hello", "A board of my own.")
    save = pg.get_by_role("button", name="Save", exact=True)
    assert save.is_disabled()                                           # it needs its name first
    pg.locator("input[aria-label='Its name']").fill("my-board")
    save.click()
    pg.wait_for_url("**/my-board", timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('#nav a')].some((a) => a.textContent === 'My board')", timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('#main').innerText.includes('A board of my own.')", timeout=WAIT)
    text = p.model.path.read_text()
    assert "  my-board:\n" in text and "    nav: true\n" in text
    assert settled(pg) == []
    pg.close()
