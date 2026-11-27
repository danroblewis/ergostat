"""The page scoped by systems (SPEC §4f; docs/roadmap/systems-and-projections.md, steps 5 to 7): the System tree top
left, the nav bar the chosen system's (its default dashboards, a bar, the projections it contains, an ancillary one
greyer), every address read one segment at a time (a nested system's overview, a subsystem's projection and item), a
deeper address redirected to the top-most, a system's Events only those behind what it contains, and a system's
Overview edited in place saved into that system's file.

It needs Playwright and a Chromium, as the smoke suite (tests/test_react_pages.py) does."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from tests.test_react_pages import WAIT, browser, heading, opened, settled  # noqa: F401

pytestmark = pytest.mark.slow

MAIN = """\
name: plant
include: [intake.yaml]
systems:
  factory: {description: makes things}
  intake: {within: factory, description: takes work in}
  qa: {within: factory, description: checks the work}
  delivery: {within: factory, description: ships it}
projections:
  ticket: {states: [new, shipped], system: intake}
  note: {states: [open], system: qa}
  run: {match: {key: run/*}, states: [going]}
stocks:
  arrived: {system: intake, unit: tickets, sensor: {projection: ticket, state: new}}
  shipped: {system: delivery, unit: tickets, sensor: {projection: ticket, state: shipped}}
  notes-open: {system: qa, unit: notes, sensor: {projection: note, state: open}}
  runs: {unit: runs, sensor: {projection: run, state: going}}
goals:
  few-notes: {system: qa, stock: notes-open, hold: "<= 5"}
  some-runs: {stock: runs, hold: "<= 9"}
"""
INTAKE = """\
defaults:
  system: intake
goals:
  full: {stock: arrived, hold: "<= 50"}
"""


@pytest.fixture(scope="module")
def plant(tmp_path_factory):
    d: Path = tmp_path_factory.mktemp("plant")
    (d / "ergostat.yaml").write_text(MAIN)
    (d / "intake.yaml").write_text(INTAKE)
    p = Project(mdl.load(d))
    now = time.time()
    p.events.add("ticket.new", item="factory/intake/ticket/1", data={"state": "new", "title": "first"}, at=now - 300)
    p.events.add("note.open", item="factory/qa/note/7", data={"state": "open", "title": "a note"}, at=now - 200)
    p.events.add("run.going", item="run/3", data={"state": "going"}, at=now - 100)
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def nav(pg) -> list[str]:
    return [x.strip() for x in pg.locator("#nav a, #nav .menu-btn").all_inner_texts()]


def test_the_system_tree_navigates_and_the_nav_bar_is_the_chosen_systems(browser, plant):
    _, url = plant
    pg = opened(browser, url + "/overview")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('plant')", timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('#nav a')].some((a) => a.textContent === 'Run')", timeout=WAIT)
    assert nav(pg) == ["Overview", "Diagrams", "Goals", "Agents", "Events", "Run"]     # the top level's own: run
    tree = pg.locator(".system-menu .menu-btn")
    tree.click()
    items = pg.locator(".system-menu .menu-item").all_inner_texts()
    assert [x.strip("✓ ").strip() for x in items] == ["plant", "factory", "intake", "qa", "delivery"]
    pg.locator(".system-menu .menu-item", has_text="qa").click()
    pg.wait_for_url("**/factory/qa/overview", timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('qa')", timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('#nav a')].some((a) => a.textContent === 'Note')", timeout=WAIT)
    assert nav(pg) == ["Overview", "Diagrams", "Goals", "Agents", "Events", "Note"]
    assert "qa" in tree.inner_text()                                       # the tree says where the address is
    pg.locator(".panel-kind-goals table.loops tbody tr", has_text="few-notes").wait_for(timeout=WAIT)
    assert "some-runs" not in pg.locator(".panel-kind-goals").inner_text()  # qa's goals, not the top level's
    assert settled(pg) == []
    pg.close()


def test_a_nested_systems_overview_and_its_ancillary_projection(browser, plant):
    _, url = plant
    pg = opened(browser, url + "/factory/intake/overview")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('intake')", timeout=WAIT)
    pg.locator(".panel-kind-goals table.loops tbody tr", has_text="full").wait_for(timeout=WAIT)
    ticket = pg.locator("#nav a", has_text="Ticket")
    ticket.wait_for(timeout=WAIT)
    assert "ancillary" not in (ticket.get_attribute("class") or "")        # intake's own
    pg.close()
    pg = opened(browser, url + "/factory/overview")                         # ticket crosses into factory: ancillary there
    ticket = pg.locator("#nav a", has_text="Ticket")
    ticket.wait_for(timeout=WAIT)
    assert "ancillary" in ticket.get_attribute("class") and ticket.get_attribute("title") == "defined in intake"
    assert pg.locator("#nav a", has_text="Note").count() == 0               # qa's own stays in qa
    card = pg.locator(".panel-kind-projections .projection-card[data-projection=ticket]")
    card.wait_for(timeout=WAIT)
    assert "ancillary" in card.get_attribute("class")
    assert settled(pg) == []
    pg.close()


def test_a_projection_and_its_item_in_a_subsystem_and_a_deeper_address_redirects(browser, plant):
    _, url = plant
    pg = opened(browser, url + "/factory/qa/note")
    pg.locator(".panel-kind-item-list table tbody tr", has_text="factory/qa/note/7").wait_for(timeout=WAIT)
    pg.close()
    pg = opened(browser, url + "/factory/qa/note/7")
    assert heading(pg) == "factory/qa/note/7"
    pg.close()
    pg = opened(browser, url + "/factory/intake/ticket/1")                  # in factory too: its top-most address
    pg.wait_for_url(lambda u: u.endswith("/factory/ticket/1"), timeout=WAIT)
    assert heading(pg) == "factory/intake/ticket/1"
    pg.close()
    pg = opened(browser, url + "/note")                                     # an old top-level address: where it is
    pg.wait_for_url("**/factory/qa/note", timeout=WAIT)
    assert settled(pg) == []
    pg.close()
    pg = opened(browser, url + "/diagram?system=qa&view=blocks")             # the old Diagram of a system: its Diagrams
    pg.wait_for_url("**/factory/qa/diagrams?view=blocks", timeout=WAIT)
    assert "qa" in heading(pg, "#diagram-caption")
    assert settled(pg) == []
    pg.close()


def test_a_systems_events_are_only_those_behind_what_it_contains(browser, plant):
    _, url = plant
    pg = opened(browser, url + "/factory/qa/events")
    panel = pg.locator(".panel.panel-kind-events")
    panel.locator("tbody tr").first.wait_for(timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('.panel-kind-events').innerText.includes('note.open')", timeout=WAIT)
    text = panel.inner_text()
    assert "ticket.new" not in text and "run.going" not in text
    pg.close()
    pg = opened(browser, url + "/events")                                    # the top level's: every event
    pg.wait_for_function("() => ['note.open', 'ticket.new', 'run.going'].every((t) => "
                         "document.querySelector('.panel-kind-events')?.innerText.includes(t))", timeout=WAIT)
    assert settled(pg) == []
    pg.close()


def test_a_systems_overview_edited_in_place_is_saved_into_its_file(browser, tmp_path):
    (tmp_path / "ergostat.yaml").write_text(MAIN)
    (tmp_path / "intake.yaml").write_text(INTAKE)
    p = Project(mdl.load(tmp_path))
    server, url = web.serve(p, 0)
    try:
        pg = opened(browser, url + "/factory/intake/overview")
        pg.locator(".panel.panel-kind-goals").wait_for(timeout=WAIT)
        pg.get_by_role("button", name="Edit", exact=True).first.click()
        pg.get_by_role("button", name="Remove What needs attention").click()
        pg.get_by_role("button", name="Save", exact=True).click()
        pg.get_by_role("toolbar", name="Editing this dashboard").wait_for(state="detached", timeout=WAIT)
        sub = (tmp_path / "intake.yaml").read_text()
        assert "dashboards:\n  overview:\n" in sub and '"system": "$system"' in sub and "attention" not in sub
        assert (tmp_path / "ergostat.yaml").read_text() == MAIN
        pg.get_by_role("link", name="ergostat's own page").wait_for(timeout=WAIT)   # the model's, in the default's place
        assert pg.locator(".panel.panel-kind-attention").count() == 0
        pg.goto(url + "/factory/qa/overview")                                # qa's own default: still ergostat's
        pg.locator(".panel.panel-kind-attention").wait_for(timeout=WAIT)
        assert settled(pg) == []
        pg.close()
    finally:
        server.shutdown()
        server.server_close()
