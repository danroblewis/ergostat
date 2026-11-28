"""An item's page as panels with one history (SPEC §5a, *The item's page*): a modelling request raised for a group of
unexplained events (ergostat's built-in bookkeeping) leads to its group, says no "Why isn't this done?", folds its
bookkeeping fields apart and draws a nested map as rows, not JSON; and its history is one list, each event with the move
it made."""

from __future__ import annotations

from urllib.parse import quote

import pytest

from ergostat import web
from tests.test_react_pages import EXAMPLE, WAIT, browser, opened, project_with_items, settled  # noqa: F401
from tests.test_react_pages import pytestmark  # noqa: F401  (skipped when the page is not built)

pytest.importorskip("playwright.sync_api")


@pytest.fixture
def request_page(tmp_path):
    from ergostat.numbers import requests as rq
    from ergostat.numbers import unexplained as ux
    p = project_with_items(tmp_path / EXAMPLE)                 # (under use: modelling: the built-in projections)
    p.events.add("deploy.finished", source="deployer", data={"service": "s1"})
    ux.sync(p)
    (g,) = [g for g in ux.groups(p) if g["type"] == "deploy.finished"]
    (r,) = [r for r in rq.stored(p).values() if r.get("about") == f"events:{g['id']}"]
    server, url = web.serve(p, 0)
    try:
        yield url, rq.item_of(r["id"]), g
    finally:
        server.shutdown()
        server.server_close()


def test_a_modelling_requests_page_leads_to_its_group_with_one_history(browser, request_page):
    url, rid, g = request_page
    pg = opened(browser, url + f"/item/{quote(rid, safe='')}")
    to = pg.locator("[data-testid=belongs-to] a")
    to.wait_for(timeout=WAIT)
    assert to.inner_text() == f"ergostat.unexplained/{g['id']}"
    assert "This is the group deploy.finished from deployer" in pg.locator("[data-testid=belongs-to]").inner_text()
    assert f"ergostat.unexplained/{quote(g['id'], safe='')}" in (to.get_attribute("href") or "") or \
        g["id"] in (to.get_attribute("href") or "")

    hist = pg.locator(".panel-kind-item-history .history-entry")
    hist.first.wait_for(timeout=WAIT)
    assert pg.locator(".panel-kind-item-history .history-move[data-to=open]").count() >= 1
    assert pg.locator(".panel-kind-item-history .history-kind").first.inner_text() == "raised"   # (less its projection's name)

    # its bookkeeping folded apart; a nested map as rows, never JSON
    book = pg.locator("[data-testid=bookkeeping]")
    book.wait_for(timeout=WAIT)
    book.locator("summary").click()
    group = book.locator(".field-block[data-field=group]")
    group.wait_for(timeout=WAIT)
    assert group.locator(".field-map-row[data-key=source] dd").inner_text() == "deployer"
    assert "{" not in group.inner_text() and group.locator("pre").count() == 0

    assert settled(pg, 2500) == []
    assert pg.locator(".panel-kind-item-why").count() == 0                   # ergostat's own: no "Why isn't this done?"
    for kind in ("item-summary", "item-fields", "item-history", "item-state-timeline", "item-events-histogram"):
        assert pg.locator(f".panel-kind-{kind}").count() <= 1, kind          # no part twice
    for gone in ("item-path", "item-moves", "item-events", "item-changes"):
        assert pg.locator(f".panel-kind-{gone}").count() == 0, gone
    pg.close()
