"""Golden-file page tests (tests/golden.py): a page's rendered structure is compared with its saved reference in
tests/golden/, and an intended change regenerates the reference by a command instead of rewriting assertions:

    uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m tests.golden

The Dashboard's panels first: the default Dashboard made from test_dashboard_page's fake fields, every query answered
with the same three points, the clock, time zone, locale and pixel ratio fixed, so what is drawn depends on the page's
code alone.
"""

from __future__ import annotations

import pytest

from tests import golden
from tests.test_dashboard_page import FIELDS, GRAPH, ITEMS, SETTLED, WATCH, answer, served

NOW = 1795400000.0                                       # test_dashboard_page's answer() is at this moment


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    yield from served(tmp_path_factory, "image-squeeze")


@pytest.fixture(scope="module")
def browser():
    if golden.updating():                                # regenerating: no browser is a failure, never a skip
        import playwright.sync_api as playwright
    else:
        playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def test_the_default_dashboards_panels_match_their_reference(browser, site):
    # tall enough that every panel is on screen, so each is drawn rather than left waiting to be scrolled to
    ctx = browser.new_context(viewport={"width": 1440, "height": 9000}, device_scale_factor=1,
                              timezone_id="UTC", locale="en-US")
    ctx.clock.set_fixed_time(NOW)
    ctx.add_init_script(WATCH)
    ctx.route("**/api/query/fields", lambda r: r.fulfill(json=FIELDS))
    ctx.route("**/api/query?*", answer)
    ctx.route("**/api/items?*", lambda r: r.fulfill(json=ITEMS))
    ctx.route("**/api/items-graph*", lambda r: r.fulfill(json=GRAPH))
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site}/dashboard")
    pg.wait_for_selector(".dash-cell .panel")
    pg.wait_for_function("""() => [...document.querySelectorAll('.dash-cell .panel')]
                                    .every((p) => p.dataset.state && p.dataset.state !== 'loading')""")
    pg.wait_for_function(SETTLED)
    pg.wait_for_timeout(300)                             # (dashPlotsMoved tells the plots where they are after 240 ms)
    text = pg.evaluate(golden.STRUCTURE, ".dash-grid > .dash-cell")
    assert errors == []
    ctx.close()
    golden.compare("dashboard-default-panels", text)
