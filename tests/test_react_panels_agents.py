"""The agents group's kinds of panel in the page (SPEC §4f): each draws on a declared dashboard with no page errors, and
the Agents page and an agent's own page, built-in dashboards of these panels, still draw what they drew.

    uv run --with playwright==1.63.0 python -m pytest -q tests/test_react_panels_agents.py
"""

from __future__ import annotations

import time

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from tests.test_react_pages import EXAMPLE, WAIT, browser, heading, opened, project_with_items, settled  # noqa: F401

pytest.importorskip("playwright.sync_api")

BOARD = """
dashboards:
  crew:
    title: The crew
    panels:
      - {panel: ladder, title: Ladder, size: full, fit: true}
      - {panel: agents, title: Every agent, size: full, fit: true}
      - {panel: daemons, title: Daemons, size: m}
      - {panel: agent-what, agent: worker, size: m}
      - {panel: agent-definition, agent: worker, size: m}
      - {panel: agent-place, agent: worker, size: m}
      - {panel: agent-runs, agent: worker, size: full, fit: true}
      - {panel: agent-log, agent: worker, size: m}
"""
KINDS = ("ladder", "agents", "daemons", "agent-what", "agent-definition", "agent-place", "agent-runs", "agent-log")


@pytest.fixture(scope="module")
def crew(tmp_path_factory):
    p = project_with_items(tmp_path_factory.mktemp("crew") / EXAMPLE)
    p.model.path.write_text(p.model.path.read_text() + BOARD)
    p = Project(mdl.load(p.model.path.parent))
    p.events.add("agent.ran", item="worker", data={"seconds": 1, "note": "5 handled"}, at=time.time() - 60)
    server, url = web.serve(p, 0)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def test_each_agents_kind_draws_on_a_declared_dashboard(browser, crew):  # noqa: F811
    pg = opened(browser, crew + "/crew")
    heading(pg)
    pg.wait_for_function("() => document.querySelector('#main h1').textContent.startsWith('The crew')", timeout=WAIT)
    for kind in KINDS:
        pg.locator(f".panel.panel-kind-{kind}").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-ladder .ladder-line .step").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-agents table a.agent-link", has_text="worker").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-agent-definition pre, .panel-kind-agent-definition code").first.wait_for(timeout=WAIT)
    assert pg.locator(".panel-kind-agent-what .panel-title").inner_text() == "Its program"     # its title, by its rung
    pg.locator(".panel-kind-agent-place a", has_text="Show on Blocks").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-agent-runs .runs-table tbody tr", has_text="5 handled").wait_for(timeout=WAIT)
    assert settled(pg, 2000) == []
    pg.close()


def test_the_agents_page_draws_the_ladder_and_the_table(browser, crew):  # noqa: F811
    pg = opened(browser, crew + "/agents")
    assert heading(pg).startswith("Agents")
    pg.locator(".panel-kind-ladder .ladder-line").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-agents table a.agent-link", has_text="worker").wait_for(timeout=WAIT)
    assert "What the runs cost" in pg.locator(".panel-kind-agents").inner_text()
    assert settled(pg) == []
    pg.close()


def test_an_agent_page_draws_each_section_under_its_anchor(browser, crew):  # noqa: F811
    pg = opened(browser, crew + "/agent/worker#its-place")
    assert heading(pg) == "worker"
    for anchor, kind in (("what-it-is", "agent-what"), ("its-definition", "agent-definition"), ("its-place", "agent-place"),
                         ("what-it-did", "agent-runs")):
        pg.locator(f"section#{anchor} .panel-kind-{kind}").wait_for(timeout=WAIT)
    pg.locator("#what-it-did .runs-table tbody tr", has_text="5 handled").wait_for(timeout=WAIT)
    assert "Kind" in pg.locator("#main").inner_text()                     # the page's own Meta row
    assert settled(pg) == []
    pg.close()


def test_an_agent_the_model_does_not_have_is_said(browser, crew):  # noqa: F811
    pg = opened(browser, crew + "/agent/nobody")
    pg.locator("p.no-agent").wait_for(timeout=WAIT)
    pg.close()
