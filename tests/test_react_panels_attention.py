"""The attention group's panels in the page (SPEC §4f): each kind draws on a declared dashboard with no page error, and
the pages drawn from them (the Diagram page's side list, the Goals page, a goal's detail) still draw.

    uv run --with playwright==1.63.0 python -m pytest -q tests/test_react_panels_attention.py
"""

from __future__ import annotations

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from ergostat.web import server as ws
from tests.test_react_pages import EXAMPLE, WAIT, browser, heading, opened, project_with_items, settled, site  # noqa: F401

pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")

DECLARED = """
dashboards:
  watch:
    title: Watch board
    panels:
      - {panel: attention, title: Asks for me, size: m}
      - {panel: legend, title: Reading blocks, view: blocks, size: s}
      - {panel: feedback-loops, title: Feedback, size: s}
      - {panel: control-loops, title: Control, size: s}
      - {panel: quiet-systems, title: Quiet, size: s}
      - {panel: goal-runbook, title: Runbook, goal: inbox-short, size: m}
      - {panel: goal-parts, title: Parts, goal: inbox-short, size: m}
      - {panel: goal-control, title: Its control, goal: inbox-short, size: full, fit: true}
"""
KINDS = ("attention", "legend", "feedback-loops", "control-loops", "quiet-systems", "goal-runbook", "goal-parts",
         "goal-control")


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


def test_each_attention_kind_draws_on_a_declared_dashboard(browser, declared):  # noqa: F811
    _, url = declared
    pg = opened(browser, url + "/watch")
    heading(pg)
    pg.wait_for_function("() => document.querySelector('#main h1').textContent.startsWith('Watch board')", timeout=WAIT)
    for kind in KINDS:
        pg.locator(f".panel.panel-kind-{kind}").wait_for(timeout=WAIT)
        assert "Not a kind of panel" not in pg.locator(f".panel-kind-{kind}").inner_text()
    att = pg.locator(".panel-kind-attention")
    att.get_by_text("Goals off").wait_for(timeout=WAIT)
    assert att.locator("#may-do, #waiting").count() == 1
    assert pg.locator(".panel-kind-legend .legend svg").count() >= 2                     # the block diagram's marks
    pg.locator(".panel-kind-control-loops button.looprow[data-loop='inbox-short']").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-feedback-loops .looprow, .panel-kind-feedback-loops .muted").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-quiet-systems .quiet-systems").wait_for(timeout=WAIT)
    pg.locator(".panel-kind-goal-runbook .runbook-line").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-goal-parts table.parts tbody tr").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-goal-control .control-box, .panel-kind-goal-control p.muted").first.wait_for(timeout=WAIT)
    pg.locator(".panel-kind-control-loops button.looprow[data-loop='inbox-short']").click()   # a goal opens beside it
    pg.locator("h2", has_text="inbox-short").first.wait_for(timeout=WAIT)
    assert settled(pg, 2500) == []
    pg.close()


@pytest.mark.parametrize("view, own", [("dynamics", "Feedback loops"), ("blocks", "Control loops"),
                                       ("process", "Projections")])
def test_the_diagram_side_list_reads_the_diagram_only(browser, site, view, own):  # noqa: F811
    pg = opened(browser, f"{site}/diagram?view={view}")
    heading(pg, "#diagram-caption")
    pg.get_by_text("How to read it").first.wait_for(timeout=WAIT)
    pg.get_by_text(own).first.wait_for(timeout=WAIT)
    side = pg.locator(".diagram")
    for gone in ("Goals off", "Model housekeeping", "Suggestions", "Waiting for you", "Nothing waits for you"):
        assert side.get_by_text(gone).count() == 0, gone                    # nothing of the attention list stays here
    assert pg.locator("#may-do, #waiting, .wait-card, .goals-off, .housekeeping").count() == 0
    assert settled(pg) == []
    pg.close()


def test_goals_off_housekeeping_and_suggestions_are_on_the_goals_page(browser, site):  # noqa: F811
    pg = opened(browser, f"{site}/goals")
    att = pg.locator(".panel-kind-attention")
    att.get_by_text("Goals off").first.wait_for(timeout=WAIT)
    att.get_by_text("Model housekeeping").first.wait_for(timeout=WAIT)
    assert att.locator("details.housekeeping").count() == 1                  # folded, as its own section
    assert att.locator("#may-do, #waiting, .wait-card").count() == 0         # decisions are the Inbox's
    assert settled(pg) == []
    pg.close()


def test_a_goal_off_says_where_its_loop_stops_on_its_row_and_each_step_in_its_detail(browser, tmp_path):  # noqa: F811
    import time
    p = project_with_items(tmp_path / EXAMPLE)
    (s,) = p.model.spec.stocks["inbox"].sensors.values()
    for i in range(3):                                   # the inbox far past its setpoint: inbox-short off
        p.measurements.add(s.series, 40.0, time.time() - 20 + 5 * i)
    server, url = web.serve(p, 0)
    try:
        pg = opened(browser, url + "/goals")
        row = pg.locator(".goals-off [data-row='goal inbox-short']")
        row.locator("[data-stuck]").wait_for(timeout=WAIT)
        assert row.locator("[data-stuck]").inner_text() == "where it stops: the worker has never run (it runs while inbox-short is off)"
        assert row.locator("[data-stuck] a").get_attribute("href").endswith("/worker")
        row.locator("button.name").click()               # its detail: each step along its loop
        pg.locator("[data-goal-stuck] li.stuck", has_text="the worker has never run").first.wait_for(timeout=WAIT)
        assert settled(pg) == []
        pg.close()
    finally:
        server.shutdown()
        server.server_close()


def test_the_goals_page_is_the_goals_panel_with_every_column_and_select_opens_the_goal(browser, site):  # noqa: F811
    pg = opened(browser, site + "/goals?select=inbox-short")
    assert heading(pg).startswith("Goals")
    table = pg.locator(".panel.panel-kind-goals.panel-full table.loops")
    table.locator("tbody tr").first.wait_for(timeout=WAIT)
    heads = table.locator("thead th").all_inner_texts()
    assert {"time off", "back in", "behaviour", "acted"} <= {h.strip() for h in heads}, heads   # every column
    pg.locator(".runbook .runbook-line").first.wait_for(timeout=WAIT)          # the goal's detail, opened by ?select=
    pg.locator("table.parts tbody tr").first.wait_for(timeout=WAIT)
    pg.locator(".control-box, p.muted.small", has_text="control loop of goal").first.wait_for(timeout=WAIT)
    assert settled(pg) == []
    pg.close()
