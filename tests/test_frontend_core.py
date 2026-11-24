"""Acceptance (preact-foundation): the app shell draws the header with Preact and routes every page, its old function
until the page's module (app/pages/<page>/index.js) exports ``page``; a page's API calls go through useApi, timed,
aborted when it is left; the timing overlay lists every call, slowest first; and the budget helper (tests/budget.py)
holds the Agents page to 1 s to usable and 300 ms a call on the demo fixture (image-squeeze, seeded as
test_page_polling seeds it). docs/frontend.md says the rules.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_frontend_core.py -v
"""

from __future__ import annotations

import shutil

import pytest

from tests.budget import budget
from tests.test_page_polling import ROOT, seed, serve

try:                           # collected without it too, each test skipped, so a run of this file alone is rc 0, not 5
    from playwright import sync_api as playwright
except ImportError:
    playwright = None
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

EXAMPLE = "image-squeeze"
AGENTS_DRAWN = "() => document.querySelector('#main .ladder-line .step')"
# a page moved: what a page gap's app/pages/agents/index.js would be, served in place of the stub
MOVED = """import { html, useApi } from "/static/app/core.js";
export function page({ path }) {
  const a = useApi("agents"), held = useApi("held");
  return html`<div class="page moved"><h1>Agents</h1><p class="n">${a.data ? Object.keys(a.data).length : ""}</p>
    <p class="where">${path}</p><p class="held">${held.loading ? "asking" : "answered"}</p></div>`;
}
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp(EXAMPLE) / EXAMPLE
    shutil.copytree(ROOT / "examples" / EXAMPLE, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    home = d.parent / "home"
    seed(d, home)
    yield from serve(d, home)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                        # no Chromium here
            pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


def opened(browser, url):
    pg = browser.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(url)
    return pg


def test_the_shell_draws_the_header_and_routes_old_pages(browser, site):
    """The header is the shell's (one nav, nine links, the page shown marked, the two counts, the project list and the
    window's menu filled by main.js into it), and pages with no module are drawn by their old functions."""
    pg = opened(browser, f"{site}/agents")
    pg.wait_for_function(AGENTS_DRAWN, timeout=30000)
    pg.wait_for_function("() => document.querySelector('#running').textContent", timeout=10000)
    assert pg.evaluate("() => typeof window.ergostatApp?.mount") == "function"
    assert pg.evaluate("() => document.querySelectorAll('#nav, #running, #waits, #project, #when').length") == 5
    assert pg.locator("#nav a").all_inner_texts() == ["Diagram", "Dashboard", "Goals", "Agents", "Items", "Record",
                                                       "Model", "Check", "Guide"]
    assert pg.get_attribute("#nav a[aria-current=page]", "href") == "/agents"
    assert pg.locator("#when .menu-btn").count() == 1 and pg.locator("#project option").count() >= 1
    assert pg.get_attribute("#waits", "href") == "/diagram#waiting"
    pg.locator("#nav a", has_text="Goals").click()
    pg.wait_for_function("() => location.pathname === '/goals' && document.querySelector('#nav a.on')?.textContent === 'Goals'"
                         " && document.querySelector('#main h1')?.textContent.startsWith('Goals')", timeout=30000)
    assert pg.locator("#nav a.on").count() == 1
    assert pg.errors == []
    pg.close()


def test_a_page_module_that_exports_page_is_mounted_and_its_calls_end_when_it_is_left(browser, site):
    """A module exporting ``page`` is mounted in place of the old page; its useApi calls are timed into the call log,
    and one still on its way when the page is left is aborted; back again, it is mounted anew."""
    pg = browser.new_page()
    held = []
    pg.route("**/static/app/pages/agents/index.js*", lambda r: r.fulfill(status=200, content_type="text/javascript", body=MOVED))
    pg.route("**/api/held*", lambda r: held.append(r))           # never answered: still on its way when the page is left
    pg.goto(f"{site}/agents")
    pg.wait_for_function("() => document.querySelector('#main .moved .n')?.textContent", timeout=30000)
    assert pg.locator("#main .ladder-line").count() == 0                     # the old page is not drawn
    n = pg.evaluate("async () => Object.keys(await (await fetch('/api/agents')).json()).length")
    assert pg.locator("#main .moved .n").inner_text() == str(n)
    assert pg.locator("#main .moved .where").inner_text() == "/agents"
    assert pg.locator("#main .moved .held").inner_text() == "asking" and held
    calls = pg.evaluate("() => window.ERGOSTAT_CALLS.map((c) => [c.path, c.status, typeof c.ms])")
    assert ["agents", 200, "number"] in calls, calls
    pg.locator("#nav a", has_text="Goals").click()
    pg.wait_for_function("() => document.querySelector('#main h1')?.textContent.startsWith('Goals')", timeout=30000)
    pg.wait_for_function("() => window.ERGOSTAT_CALLS.some((c) => c.path === 'held' && c.status === 'aborted')", timeout=10000)
    assert pg.locator("#main .moved").count() == 0
    pg.go_back()
    pg.wait_for_function("() => document.querySelector('#main .moved .n')?.textContent", timeout=30000)
    pg.unroute_all(behavior="ignoreErrors")       # (the held calls let go)
    pg.close()


POLLED = """import { html, useApi } from "/static/app/core.js";
let drawn = 0;
export function page() {
  const a = useApi("steady", {}, { every: 100 });
  window.__drawn = ++drawn;
  return html`<div class="page polled"><p class="n">${a.data ? a.data.n : ""}</p></div>`;
}
"""
HIDE = """(on) => { Object.defineProperty(document, "hidden", { configurable: true, get: () => on });
                    document.dispatchEvent(new Event("visibilitychange")); }"""
POLLS_MADE = "() => window.ERGOSTAT_CALLS.filter((c) => c.path === 'steady').length"


def test_use_api_polls_at_most_twice_a_second_not_while_hidden_and_draws_nothing_for_the_same_answer(browser, site):
    """``every`` asks again after each answer, never faster than every 500 ms (100 asked); a hidden tab asks nothing
    and asks again once shown; an unchanged answer draws the component no more."""
    pg = browser.new_page()
    pg.route("**/static/app/pages/agents/index.js*", lambda r: r.fulfill(status=200, content_type="text/javascript", body=POLLED))
    pg.route("**/api/steady*", lambda r: r.fulfill(status=200, content_type="application/json", body='{"n": 3}'))   # never changes
    pg.goto(f"{site}/agents")
    pg.wait_for_function("() => document.querySelector('#main .polled .n')?.textContent", timeout=30000)
    drawn, first = pg.evaluate("window.__drawn"), pg.evaluate(POLLS_MADE)
    pg.wait_for_timeout(2000)
    made = pg.evaluate(POLLS_MADE) - first
    assert 2 <= made <= 5, f"{made} polls in 2 s at every: 100 (at least 500 ms apart: at most 5)"
    assert pg.evaluate("window.__drawn") == drawn, "an unchanged answer drew the page again"
    pg.evaluate(HIDE, True)
    pg.wait_for_timeout(1000)                     # (one on its way arrives)
    hidden = pg.evaluate(POLLS_MADE)
    pg.wait_for_timeout(1500)
    assert pg.evaluate(POLLS_MADE) == hidden, "asked while hidden"
    pg.evaluate(HIDE, False)
    pg.wait_for_function(f"() => ({POLLS_MADE})() > {hidden}", timeout=5000)
    pg.close()


def test_the_timing_overlay_lists_each_call_slowest_first(browser, site):
    """Off by default; ?timing=1 opens it (and is no part of the route); Shift+T closes and opens it, but not while
    typing in a field; each row a call's path and milliseconds, slowest first, new calls added as they end."""
    rows = "() => [...document.querySelectorAll('.timing tbody tr')].map((r) => [r.cells[0].textContent, +r.cells[1].textContent])"
    pg = opened(browser, f"{site}/agents")
    pg.wait_for_function(AGENTS_DRAWN, timeout=30000)
    assert pg.locator(".timing").count() == 0
    pg.goto(f"{site}/items?timing=1")
    pg.wait_for_function("() => document.querySelectorAll('.timing tbody tr').length >= 2", timeout=30000)
    assert pg.evaluate("() => parseRoute().q.has('timing')") is False      # the Items overview, not a search
    got = pg.evaluate(rows)
    assert {"status"} <= {p for p, _ in got}, got
    assert [ms for _, ms in got] == sorted((ms for _, ms in got), reverse=True), got
    assert len(got) == pg.evaluate("() => window.ERGOSTAT_CALLS.length")
    pg.locator("#nav a", has_text="Agents").click()
    pg.wait_for_function("() => [...document.querySelectorAll('.timing tbody td:first-child')].some((td) => td.textContent === 'agents')",
                         timeout=30000)
    pg.locator("body").press("Shift+T")
    pg.wait_for_function("() => !document.querySelector('.timing')", timeout=5000)
    pg.locator("body").press("Shift+T")
    pg.wait_for_function("() => document.querySelector('.timing tbody tr')", timeout=5000)
    pg.goto(f"{site}/record")                     # (closed again: a load without ?timing=1)
    field = pg.locator("#main input[type=search]")
    field.wait_for(timeout=30000)
    field.press("Shift+T")
    pg.wait_for_timeout(300)                      # (a render it caused would be drawn by now)
    assert pg.locator(".timing").count() == 0 and field.input_value() == "T"
    assert pg.errors == []
    pg.close()


@pytest.mark.serial
def test_the_agents_page_is_usable_within_its_budget(browser, site):
    """The budget helper on the Agents page (old, through the router): usable within 1 s of navigation on the demo
    fixture, and no API call it makes over 300 ms. The first load warms the server's caches; the second is measured."""
    pg = opened(browser, f"{site}/agents")
    pg.wait_for_function(AGENTS_DRAWN, timeout=60000)
    b = budget(pg, f"{site}/agents", AGENTS_DRAWN)
    assert {"status", "agents"} <= {c["path"] for c in b.calls}, b.calls
    b.check(usable_ms=1000, call_ms=300)
    assert pg.errors == []
    pg.close()
