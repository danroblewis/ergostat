"""Acceptance: the Dashboard page. Its panels are stood in for by a small stub of the contract's globals and a fake
/api/query, so this tests the page: the route, the default made from the fields, the draft in the address and in
localStorage, editing by keyboard and mouse, and the layout at desktop and phone widths.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_dashboard_page.py -v
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.ports import free_port

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
SHOTS = os.environ.get("DASHBOARD_SHOTS")

FIELDS = {
    "sources": {
        "items": {"kinds": {
            "quiet": {"fields": [], "states": ["new", "closed"], "group_by": ["state"]},
            "widget": {"fields": [{"name": "spend_usd", "unit": "usd"}, {"name": "lines", "unit": "lines"},
                                  {"name": "rank", "unit": ""}],
                       "states": ["ready", "building", "checking", "shipped", "dropped"], "group_by": ["state"]},
            "part": {"fields": [{"name": "weight", "unit": "g"}], "states": ["queued", "cut", "done"], "group_by": ["state"]},
            "ergostat.note": {"fields": [], "states": ["open", "shut"], "group_by": ["state"]},
        }},
        "moves": {"kinds": {}}, "counts": {"kinds": ["quiet", "widget", "part"]},
        "series": {"series": [{"name": "stock.x", "unit": "items"}]}, "events": {"types": []},
    },
    "aggregations": ["count", "sum"], "transforms": ["none", "rate"],
}
FLOWS = {
    "quiet": {"now": {"new": 0, "closed": 900}, "finished_states": ["closed"]},
    "widget": {"now": {"ready": 12, "building": 30, "checking": 4, "shipped": 200, "dropped": 9},
               "finished_states": ["shipped", "dropped"]},
    "part": {"now": {"queued": 3, "cut": 1, "done": 40}, "finished_states": ["done"]},
    "ergostat.note": {"now": {"open": 500, "shut": 0}, "finished_states": ["shut"]},
}

# chartPanel and friends as the contract gives them: the panel builder's real ones replace these
STUB = """
window.__queries = 0;
window.chartPanel = (config) => {
  const el = document.createElement("div");
  el.className = "stub-panel";
  el.dataset.form = config.form;
  const title = document.createElement("b"), plot = document.createElement("div");
  title.textContent = config.title; plot.className = "stub-plot"; plot.textContent = config.form;
  el.style.cssText = "display:flex;flex-direction:column;padding:6px;font-size:12px;gap:4px";
  plot.style.cssText = "flex:1;background:var(--fill);min-height:0;display:flex;align-items:center;" +
    "justify-content:center;color:var(--muted)";
  el.append(title, plot);
  el.update = (results) => { el.dataset.drawn = String(results.length); };
  el.setState = (s) => { el.dataset.state = s; };
  el.setConfig = (c) => { title.textContent = c.title; el.dataset.form = c.form; };
  el.destroy = () => {};
  return el;
};
window.queryFields = () => fetch("/api/query/fields").then((r) => r.json());
window.queryPanels = async (configs, opts) => {
  window.__queries++;
  window.__since = opts.since;
  const q = btoa(JSON.stringify({ since: opts.since, queries: configs.flatMap((c) => c.queries) }));
  await fetch("/api/query?q=" + encodeURIComponent(q));
  return new Map(configs.map((c) => [c.id, { results: c.queries.map((x) => ({ id: x.id, times: [], series: [] })), meta: {} }]));
};
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("image-squeeze") / "image-squeeze"
    shutil.copytree(ROOT / "examples" / "image-squeeze", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("the page never came up")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def context(browser, width=1440, height=1000, fields=FIELDS):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    ctx.add_init_script(STUB)
    ctx.route("**/api/query/fields", lambda r: r.fulfill(json=fields))
    ctx.route("**/api/query?*", lambda r: r.fulfill(json={"results": []}))

    def flow(r):
        kind = r.request.url.split("kind=")[1].split("&")[0]
        r.fulfill(json=FLOWS.get(kind, {"now": {}, "finished_states": []}))
    ctx.route("**/api/items-flow*", flow)
    return ctx


def opened(ctx, url):
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(url)
    pg.wait_for_selector(".dash-cell")
    pg.wait_for_function("() => window.__queries > 0")
    return pg


def titles(pg) -> list[str]:
    return pg.evaluate("() => dashboardDraft().panels.map((p) => p.title)")


def order(pg) -> list[str]:
    return pg.evaluate("() => dashboardDraft().panels.map((p) => p.id)")


def edit(pg):
    pg.get_by_role("button", name="Edit", exact=True).click()
    pg.wait_for_selector(".dash-grid.editing")


def no_sideways_scroll(pg):
    assert pg.evaluate("""() => [document.documentElement, document.querySelector('.page.dash')]
                                .every((e) => e.scrollWidth <= e.clientWidth + 1)""")


def test_the_route_and_the_nav_entry_after_diagram(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    names = pg.locator("#nav a").all_inner_texts()
    assert names[:2] == ["Diagram", "Dashboard"]
    assert pg.locator('#nav a[href="/dashboard"]').get_attribute("class") == "on"
    assert pg.errors == []
    ctx.close()


def test_the_default_is_made_from_the_fields_ranked_by_what_kinds_hold(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    d = pg.evaluate("() => dashboardDraft()")
    forms = [p["form"] for p in d["panels"]]
    assert forms[:6] == ["stat"] * 6 and "stat" not in forms[6:]                 # the opening row, cost included
    assert "Work in progress (widget)" == d["panels"][0]["title"]                # widget has the most work open
    assert any("spend_usd per hour" in p["title"] for p in d["panels"][:6])
    said = " ".join(p["title"] for p in d["panels"])
    assert "part:" in said and "ergostat.note" not in said and "quiet" not in said     # its own notes and idle kinds wait
    work = next(p for p in d["panels"] if p["title"] == "widget: open work by state")
    assert work["queries"][0]["where"] == {"state": ["ready", "building", "checking"]}   # the server's finished states are left out
    assert work["form"] == "stacked"
    stay = next(p for p in d["panels"] if "time in" in p["title"] and p["form"] == "line")
    assert "building" in stay["title"] and [q["agg"] for q in stay["queries"]] == ["p50", "p90"]    # the state holding the most
    assert not any(":" in p["title"] and "rank" in p["title"] for p in d["panels"])   # an ordinal is not worth a chart
    assert len(d["panels"]) <= 24
    ctx.close()


def test_a_default_with_no_cost_has_three_stats_and_with_no_kinds_charts_series(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    got = pg.evaluate("""([f, fl]) => {
      const bare = JSON.parse(JSON.stringify(f));
      bare.sources.items.kinds.widget.fields = [];
      const stats = dashDefault(bare, fl).panels.filter((p) => p.form === "stat").length;
      bare.sources.items.kinds = {};
      return { stats, series: dashDefault(bare, {}).panels.map((p) => p.queries[0].series) };
    }""", [FIELDS, FLOWS])
    assert got == {"stats": 3, "series": ["stock.x"]}
    ctx.close()


def test_a_draft_goes_through_the_address_and_localstorage(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    assert "draft=" not in pg.url                                                 # the default writes nothing
    edit(pg)
    first = pg.locator(".dash-cell").first
    first.focus()
    pg.keyboard.press("Alt+ArrowRight")
    pg.wait_for_function("() => location.search.includes('draft=')")
    link = pg.url
    wanted = order(pg)
    text = link.split("draft=")[1].split("&")[0]
    decoded = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
    assert [p["id"] for p in decoded["panels"]] == wanted

    again = opened(ctx, f"{site}/dashboard")                                       # the same browser, no address
    assert order(again) == wanted
    other = context(browser)                                                       # a fresh browser, the link
    there = opened(other, link)
    assert order(there) == wanted

    plain = pg.evaluate("""() => { const d = dashboardDraft(); d.title = 'Sent to me'; d.panels = d.panels.slice(0, 2);
                                   return dashEncode(d); }""")
    sent = opened(ctx, f"{site}/dashboard?draft={plain}")                          # the address wins over what is kept
    assert sent.locator(".dash-head h1").inner_text() == "Sent to me" and len(order(sent)) == 2
    kept = opened(ctx, f"{site}/dashboard")                                        # and opening a link leaves what is kept alone
    assert order(kept) == wanted
    other.close()
    ctx.close()


def test_an_unreadable_link_says_so_and_opens_what_is_kept(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard?draft=not-a-draft")
    assert "could not be read" in pg.locator(".page.dash > .note").inner_text()
    assert pg.errors == []
    ctx.close()


def test_edit_mode_moves_resizes_and_removes_by_keyboard(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    edit(pg)
    was = order(pg)
    pid = was[0]
    cell = pg.locator(f'[data-panel="{pid}"]')
    cell.focus()
    pg.keyboard.press("Alt+ArrowRight")
    assert order(pg)[:2] == [was[1], pid]
    assert pg.evaluate("() => document.activeElement.dataset.panel") == pid       # focus stays on the panel
    assert "moved to place 2 of" in pg.locator(".dash-live").inner_text()
    pg.keyboard.press("Alt+ArrowLeft")
    assert order(pg) == was

    pg.keyboard.press("Shift+Alt+ArrowRight")
    def size():
        return pg.evaluate("(id) => dashboardDraft().panels.find((p) => p.id === id).size", pid)
    assert size() == "m"
    pg.keyboard.press("Shift+Alt+ArrowLeft")
    assert size() == "s"
    pg.keyboard.press("Shift+Alt+ArrowDown")
    assert pg.evaluate("(id) => dashboardDraft().panels.find((p) => p.id === id).tall", pid) is True
    pg.keyboard.press("Shift+Alt+ArrowUp")

    pg.keyboard.press("Delete")
    assert pid not in order(pg)
    assert pg.evaluate("() => document.activeElement.dataset.panel") == was[1]    # focus goes to the next
    pg.get_by_role("button", name="Undo").click()
    assert pid in order(pg)
    assert pg.errors == []
    ctx.close()


def test_edit_mode_moves_and_resizes_by_mouse(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    edit(pg)
    was = order(pg)
    grip = pg.locator(f'[data-panel="{was[0]}"] .dash-grip').bounding_box()
    to = pg.locator(f'[data-panel="{was[1]}"]').bounding_box()
    pg.mouse.move(grip["x"] + 3, grip["y"] + 3)
    pg.mouse.down()
    pg.mouse.move(to["x"] + to["width"] / 2, to["y"] + to["height"] / 2, steps=4)
    pg.mouse.up()
    assert order(pg)[:2] == [was[1], was[0]]

    handle = pg.locator(f'[data-panel="{was[1]}"] .dash-handle').bounding_box()
    pg.mouse.move(handle["x"] + 3, handle["y"] + 3)
    pg.mouse.down()
    grid = pg.locator(".dash-grid").bounding_box()
    pg.mouse.move(grid["x"] + grid["width"] * 0.48, handle["y"] + 3, steps=4)
    pg.mouse.up()
    assert pg.evaluate("(id) => dashboardDraft().panels.find((p) => p.id === id).size", was[1]) == "m"
    assert "draft=" in pg.url
    ctx.close()


def test_the_tools_never_sit_over_the_plot(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    edit(pg)
    assert pg.evaluate("""() => [...document.querySelectorAll('.dash-cell')].every((c) => {
      const b = c.querySelector('.dash-body').getBoundingClientRect(), t = c.querySelector('.dash-tools').getBoundingClientRect(),
            f = c.querySelector('.dash-foot').getBoundingClientRect();
      return t.bottom <= b.top + 1 && f.top >= b.bottom - 1;
    })""")
    ctx.close()


def test_the_header_window_is_used_and_kept(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    assert pg.evaluate("() => window.__since") == 86400
    pg.locator("#when .menu-btn").click()
    pg.get_by_role("menuitemcheckbox", name="Last 6 hours").click()
    pg.wait_for_function("() => window.__since === 21600")
    assert "since=6h" in pg.url
    pg.reload()
    pg.wait_for_function("() => window.__since === 21600")
    ctx.close()


@pytest.mark.parametrize("width,height", [(1440, 1000), (390, 844)])
def test_no_sideways_scroll_and_one_column_on_a_phone(browser, site, width, height):
    ctx = context(browser, width, height)
    posts: list[str] = []
    pg = ctx.new_page()
    pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    pg.goto(f"{site}/dashboard")
    pg.wait_for_selector(".dash-cell")
    pg.wait_for_function("() => window.__queries > 0")
    no_sideways_scroll(pg)
    lefts = pg.evaluate("""() => [...new Set([...document.querySelectorAll('.dash-cell')]
                                             .map((c) => Math.round(c.getBoundingClientRect().left)))]""")
    assert (len(lefts) == 1) == (width < 700), lefts
    if SHOTS:
        pg.screenshot(path=f"{SHOTS}/dashboard-{width}.png")
    edit(pg)
    no_sideways_scroll(pg)
    if SHOTS:
        pg.screenshot(path=f"{SHOTS}/dashboard-{width}-edit.png")
    assert [u for u in posts if "/api/query" in u or "dashboard" in u] == []
    ctx.close()


def test_a_project_with_nothing_recorded_says_so(browser, site):
    ctx = context(browser, fields={"sources": {}})
    pg = ctx.new_page()
    pg.goto(f"{site}/dashboard")
    pg.wait_for_selector(".dash-empty")
    assert "Nothing is recorded" in pg.locator(".dash-empty").inner_text()
    ctx.close()
