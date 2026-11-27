"""The record group's panels in the browser (SPEC §4f): events, goal-crossings and goal-decisions each draw on a
declared dashboard with no page error, and the Record page, now an events panel, still draws and filters by its
address.

It needs Playwright and a Chromium, so the unit run skips it:

    uv run --with playwright==1.63.0 python -m pytest -q tests/test_react_panels_record.py
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from tests.test_react_pages import EXAMPLE, WAIT, browser, heading, opened, project_with_items, settled  # noqa: F401

playwright = pytest.importorskip("playwright.sync_api")

GOAL = "inbox-short"
DECLARED = f"""
dashboards:
  events-board:
    title: Record board
    panels:
      - {{panel: events, title: Tickets done, match: ticket.done, size: m}}
      - {{panel: events, title: The goal's, about: {GOAL}, size: m}}
      - {{panel: goal-crossings, title: Crossings, goal: {GOAL}, size: m}}
      - {{panel: goal-decisions, title: Decisions, goal: {GOAL}, size: m}}
"""


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    """The smoke suite's project, with a crossing and a decision of its goal on the record, and a record board."""
    p = project_with_items(tmp_path_factory.mktemp("record") / EXAMPLE)
    now = time.time()
    p.events.add("loop.off", item=GOAL, data={"value": 26, "setpoint": "<= 20", "error": 6}, at=now - 200)
    p.events.add("controller.decided", item=GOAL, data={"decision": "run worker for 6 over"}, at=now - 190)
    p.events.add("loop.on", item=GOAL, data={"value": 14, "setpoint": "<= 20", "error": 0}, at=now - 100)
    p.model.path.write_text(p.model.path.read_text() + DECLARED)
    p = Project(mdl.load(p.model.path.parent))
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def rows_text(pg, panel) -> str:
    return pg.locator(panel).inner_text()


def test_each_record_kind_draws_on_a_declared_dashboard(browser, recorded):  # noqa: F811
    _, url = recorded
    pg = opened(browser, url + "/events-board")
    heading(pg)
    pg.wait_for_function("() => document.querySelector('#main h1').textContent.startsWith('Record board')", timeout=WAIT)
    done = pg.locator(".panel.panel-kind-events[aria-label='Tickets done']")
    done.locator("table tbody tr").first.wait_for(timeout=WAIT)
    assert set(done.locator("tbody tr td:nth-child(2)").all_inner_texts()) == {"ticket.done"}   # its match, only
    goal = pg.locator(".panel.panel-kind-events[aria-label=\"The goal's\"]")
    goal.locator("tbody tr").first.wait_for(timeout=WAIT)
    assert {"loop.off", "loop.on", "controller.decided"} <= set(goal.locator("tbody tr td:nth-child(2)").all_inner_texts())
    crossings = pg.locator(".panel.panel-kind-goal-crossings table.crossings tbody tr")
    crossings.first.wait_for(timeout=WAIT)
    assert crossings.count() == 2
    link = crossings.last.locator("a")                                    # the oldest: off, to the next crossing
    assert re.fullmatch(rf"/record\?about={GOAL}&from=[\d.]+&to=[\d.]+", link.get_attribute("href"))
    decisions = pg.locator(".panel.panel-kind-goal-decisions")
    decisions.locator("tbody tr").first.wait_for(timeout=WAIT)
    assert "run worker for N over" in decisions.inner_text()
    assert decisions.get_by_role("link", name="Each one in the Record").get_attribute("href").startswith(
        f"/record?item={GOAL}&match=controller.decided")
    done.locator("tbody tr a.plain").first.click()                        # an event, whole, in the side panel
    pg.locator("#detail h2").wait_for(timeout=WAIT)
    assert pg.locator("#detail h2").inner_text() == "ticket.done"
    assert settled(pg, 2500) == []
    link.click()                                                          # a crossing's link: the Record, scoped
    pg.wait_for_url(re.compile(r".*/record\?about="), timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('#main')?.innerText.includes('loop.off')", timeout=WAIT)
    assert f"of goal {GOAL}" in pg.locator(".filters").inner_text()
    assert settled(pg) == []
    pg.close()


def test_the_record_page_is_an_events_panel_and_filters_by_its_address(browser, recorded):  # noqa: F811
    _, url = recorded
    pg = opened(browser, url + "/record")
    assert heading(pg) == "Record"
    panel = pg.locator(".panel.panel-kind-events.panel-fit")
    panel.locator("tbody tr").first.wait_for(timeout=WAIT)
    assert "ticket/1" in panel.inner_text()
    box = pg.get_by_label("Event type, item or source")
    box.fill("ticket.done")
    box.press("Enter")
    pg.wait_for_url(re.compile(r".*match=ticket\.done"), timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('.panel-kind-events tbody tr td:nth-child(2)')]"
                         ".every(td => td.innerText === 'ticket.done')", timeout=WAIT)
    pg.get_by_label(re.compile("Show runs")).check()
    pg.wait_for_url(re.compile(r".*runs=1"), timeout=WAIT)
    assert settled(pg) == []
    pg.close()

    pg = opened(browser, url + "/record?item=" + quote("ticket/2", safe=""))           # a scope: its words, its events
    pg.wait_for_function("() => document.querySelector('.filters')?.innerText.includes('about ticket/2')", timeout=WAIT)
    pg.locator(".panel-kind-events tbody tr").first.wait_for(timeout=WAIT)
    assert set(pg.locator(".panel-kind-events tbody tr td:nth-child(3)").all_inner_texts()) == {"ticket/2"}
    assert settled(pg) == []
    pg.close()

    pg = opened(browser, url + "/record?match=nothing.like.this&window=1")                # nothing matches: clear it
    pg.locator("a.clear-filter").wait_for(timeout=WAIT)
    assert "in the window" in pg.locator(".filters").inner_text()
    pg.locator("a.clear-filter").click()
    pg.wait_for_url(re.compile(r".*/record\?window=1$"), timeout=WAIT)
    pg.locator(".panel-kind-events tbody tr").first.wait_for(timeout=WAIT)
    assert settled(pg) == []
    pg.close()

    old = opened(browser, url + "/record?type=ticket.opened")                             # an old link's filter=/type=
    old.wait_for_function("() => [...document.querySelectorAll('.panel-kind-events tbody tr td:nth-child(2)')]"
                          ".map(td => td.innerText).join() === 'ticket.opened,ticket.opened,ticket.opened'", timeout=WAIT)
    assert old.get_by_label("Event type, item or source").input_value() == "ticket.opened"
    assert settled(old) == []
    old.close()
