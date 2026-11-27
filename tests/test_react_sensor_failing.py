"""The page says a failing sensor: the header's "1 sensor failing", the stock drawn unmeasured on the diagram, and
its side panel saying why; the attention list carries it."""

from __future__ import annotations

import pytest

from ergostat import web
from ergostat.web import server as ws

from tests.test_react_pages import WAIT, browser, opened, settled  # noqa: F401  (browser: the module's fixture)
from tests.test_sensor_failing import fail, project

pytestmark = pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    p = project(tmp_path_factory.mktemp("failing"))
    for _ in range(3):
        fail(p)
    server, url = web.serve(p, 0)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


def test_the_header_and_the_diagram_say_the_sensor_is_failing(site, browser):
    pg = opened(browser, site + "/diagram")
    pg.wait_for_selector("#sensors-failing", timeout=WAIT)
    assert pg.locator("#sensors-failing").inner_text() == "1 sensor failing"
    assert "mission.main: it printed nothing" in pg.locator("#sensors-failing").get_attribute("title")
    node = pg.locator('.node.unmeasured[data-id="stock:mission"]')
    node.wait_for(timeout=WAIT)
    node.click()
    pg.wait_for_selector(".unmeasured-note", timeout=WAIT)
    note = pg.locator(".unmeasured-note").inner_text()
    assert "Unmeasured." in note and "its last 3 reads failed" in note and "Never read." in note
    pg.wait_for_selector('[data-row="sensor mission.main"]', state="attached", timeout=WAIT)   # (under the side panel)
    assert settled(pg) == []
    pg.close()
