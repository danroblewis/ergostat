"""A drafted projection waiting for the owner, on the page: its row in "Waiting for you" links to the change, opens the
draft in the workbench, and is approved by its button (written into the model)."""

from __future__ import annotations

import pytest

from ergostat import web
from ergostat.numbers import drafter as dr
from ergostat.numbers import judge as jd
from ergostat.numbers import unexplained as ux
from ergostat.web import server as ws

from tests.test_react_pages import WAIT, browser, opened  # noqa: F401  (browser: the module's fixture)
from tests.test_unexplained_events import DEPLOY, MODEL, emit, project, stand_in

pytestmark = pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")


def test_a_draft_waiting_is_linked_opened_and_approved_from_the_page(tmp_path, monkeypatch, browser):
    p = project(tmp_path, MODEL.replace("      ai: true\n", "      ai: true\n      review: {when: off}\n"))
    emit(p)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", stand_in(tmp_path, DEPLOY))
    (pid,) = dr.run(p, daily=1.0)["proposed"]
    jd.run(p, "judge")
    server, url = web.serve(p, 0)
    try:
        pg = opened(browser, url + "/diagram")
        row = pg.locator(f'[data-row="change/{pid}"]')
        row.wait_for(timeout=WAIT)
        assert row.locator(f'a[href$="ergostat.model-change/{pid}"]').count() == 1      # the change's own page
        assert row.locator('a[data-workbench="deploy"]').get_attribute("href").endswith(f"workbench=deploy&proposal={pid}")
        row.locator('button[data-answer="approve"]').click()
        row.locator("[data-answered]").wait_for(timeout=WAIT)
        assert "approved" in row.locator("[data-answered]").inner_text()
        assert "  deploy:" in p.model.path.read_text()
        pg.close()
    finally:
        server.shutdown()
        server.server_close()
