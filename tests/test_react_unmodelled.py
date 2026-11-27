"""An item no projection matches is still drawn (its events folded as they are), labelled as not in the model, with
the projection to add; its address keeps the id's slash (/item/missioner/1235)."""

from __future__ import annotations

import pytest

from ergostat import web
from ergostat.web import server as ws

from tests.test_react_pages import WAIT, browser, opened, settled  # noqa: F401  (browser: the module's fixture)
from tests.test_sensor_failing import project

pytestmark = pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    p = project(tmp_path_factory.mktemp("unmodelled"))
    p.events.add("mission.started", item="missioner/1235", data={"name": "mission dolores"})
    server, url = web.serve(p, 0)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def test_an_unmodelled_item_says_so_and_what_to_add(site, browser):
    pg = opened(browser, site + "/item/missioner/1235")
    pg.wait_for_selector(".unmodelled-note", timeout=WAIT)
    note = pg.locator(".unmodelled-note").inner_text()
    assert "Not in the model." in note and "No projection matches missioner/1235" in note
    assert "projections:\n  missioner:\n    match: {key: missioner/*}" in note
    assert settled(pg) == []
    pg.close()
