"""An object's name on the page (SPEC §5a, *An object's name*): a projection's list shows each item's name with its key
small, and the item's page is titled by its name, the key under it."""

from __future__ import annotations

import pytest

from ergostat import web
from ergostat.web import server as ws

from tests.test_projection_name import project, recorded
from tests.test_react_pages import WAIT, browser, heading, opened, settled  # noqa: F401  (browser: the module's fixture)

pytestmark = pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    p = project(tmp_path_factory.mktemp("names"))
    recorded(p)
    server, url = web.serve(p, 0)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def test_the_list_shows_the_name_and_the_key(site, browser):
    pg = opened(browser, site + "/instance")
    row = pg.locator("table.projection-items tbody tr", has_text="web-1")
    row.first.wait_for(timeout=WAIT)
    assert "eu/i-1" in row.first.inner_text()                          # the key, small, beside it
    assert pg.locator("table.projection-items tbody tr", has_text="i-2").count() == 1
    assert settled(pg) == []
    pg.close()


def test_the_item_page_is_titled_by_its_name(site, browser):
    pg = opened(browser, site + "/instance/eu/i-1")
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent === 'web-1'", timeout=WAIT)
    assert pg.get_by_test_id("item-key").inner_text() == "eu/i-1"
    assert settled(pg) == []
    pg.close()
