"""Acceptance: the Dashboard page, on the real panels.js with a fake /api/query, so this tests the page: the route,
the default made from the fields, the draft in the address and in
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
            "log": {"fields": [{"name": "cost", "unit": "count"}], "states": ["started", "ended", "failed"], "group_by": ["state"]},
            "widget": {"fields": [{"name": "spend_usd", "unit": "usd"}, {"name": "net_lines", "unit": "lines"},
                                  {"name": "tries_attempts", "unit": "count"}, {"name": "loop_hours", "unit": "hours"},
                                  {"name": "rank", "unit": "count"}],
                       "states": ["new", "ready", "redo", "building", "checked", "shipped", "dropped", "held", "dead"],
                       "group_by": ["state"]},
            "part": {"fields": [{"name": "weight", "unit": "g"}], "states": ["queued", "cut", "ground", "done"], "group_by": ["state"]},
            "ergostat.note": {"fields": [], "states": ["open", "doing", "more", "shut"], "group_by": ["state"]},
        }},
        "moves": {"kinds": {}}, "counts": {"kinds": ["log", "widget", "part"]},
        "series": {"series": [{"name": "stock.x", "unit": "items"}]}, "events": {"types": []},
    },
    "aggregations": ["count", "sum"], "transforms": ["none", "rate"],
}
ITEMS = {"kinds": [
    {"name": "log", "counts": {"started": 40, "ended": 3000, "failed": 50}, "finished": ["ended", "failed"], "paused": [],
     "dead": False, "finished_from": "inferred", "relations": {"about": ["widget"]}},
    {"name": "widget", "counts": {"new": 4, "ready": 90, "redo": 60, "building": 9, "checked": 20, "shipped": 200, "dropped": 30,
                                  "held": 11},
     "finished": ["shipped", "dropped"], "paused": ["held"], "dead": True, "finished_from": "declared",
     "relations": {"depends_on": ["widget"]}},
    {"name": "part", "counts": {"queued": 3, "cut": 1, "ground": 2, "done": 40}, "finished": ["done"], "paused": [], "dead": False,
     "finished_from": "declared", "relations": {}},
    {"name": "ergostat.note", "counts": {"open": 500}, "finished": ["shut"], "paused": [], "dead": False,
     "finished_from": "inferred", "relations": {}},
], "items": []}
GRAPH = {"kinds": [{"name": "widget", "queue": ["new", "ready", "redo", "checked"]}, {"name": "part", "queue": ["queued"]},
                   {"name": "log", "queue": ["started"]}]}

# the page runs on the real panels.js: only the server is faked, and each query it is sent is noted here
WATCH = """
window.__queries = 0;
window.__asked = [];
const realFetch = window.fetch.bind(window);
window.fetch = (url, opts) => {
  const text = String(url);
  if (text.includes("/api/query?")) {
    const q = new URL(text, location.href).searchParams.get("q").replace(/-/g, "+").replace(/_/g, "/");
    const asked = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(q), (c) => c.charCodeAt(0))));
    window.__queries++;
    window.__since = asked.since;
    window.__asked = asked.queries;
  }
  return realFetch(url, opts);
};
"""


def answer(route):
    """A fake /api/query: three points for every query asked."""
    text = route.request.url.split("q=")[1].split("&")[0]
    asked = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
    now = 1795400000.0
    route.fulfill(json={"now": now, "since": now - asked["since"], "until": now, "step": 60, "results": [
        {"id": q["id"], "times": [now - 120, now - 60, now], "series": [{"name": "x", "values": [1.0, 2.0, 3.0]}],
         "unit": "", "capped": 0, "read_log": False} for q in asked["queries"]]})


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
    ctx.add_init_script(WATCH)
    ctx.route("**/api/query/fields", lambda r: r.fulfill(json=fields))
    ctx.route("**/api/query?*", answer)

    ctx.route("**/api/items?*", lambda r: r.fulfill(json=ITEMS))
    ctx.route("**/api/items-graph*", lambda r: r.fulfill(json=GRAPH))
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


def default(pg):
    return {p["title"]: p for p in pg.evaluate("() => dashboardDraft().panels")}


def test_the_default_leads_with_the_kind_that_is_work_moving_to_a_finish(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    d = pg.evaluate("() => dashboardDraft()")
    forms = [p["form"] for p in d["panels"]]
    assert forms[:6] == ["stat"] * 6 and "stat" not in forms[6:]                 # the opening row, cost included
    assert d["panels"][0]["title"] == "widget: work in progress"                 # not the log, which holds the most
    said = " ".join(p["title"] for p in d["panels"])
    assert "part:" in said and "ergostat.note" not in said and "log:" not in said
    assert len(d["panels"]) <= 32
    ctx.close()


def test_arrivals_enter_the_first_state_and_completions_the_finished_ones(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    a, b = default(pg)["widget: arrivals and completions per hour"]["queries"]
    assert (a["label"], a["state"], a["first_only"]) == ("arrivals", ["new"], True)     # a re-entry is not an arrival
    assert "first_only" not in b
    assert (b["label"], b["state"]) == ("completions", ["shipped", "dropped"])
    named = pg.evaluate("""() => dashNamed({ queries: [{ id: "a", label: "arrivals" }, { id: "b" }] },
      [{ id: "a", series: [{ name: "entries", values: [1] }] }, { id: "b", series: [{ name: "x", values: [1] }] }])
      .map((r) => r.series[0].name)""")
    assert named == ["", "x"]                                                     # so the legend reads "arrivals" alone
    ctx.close()


def test_time_in_state_is_for_the_main_states_and_work_is_grouped(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    got = default(pg)
    stay = got["widget: median time in ready, building, checked"]                 # the rework state is passed over
    assert [q["state"] for q in stay["queries"]] == [["ready"], ["building"], ["checked"]]
    work = got["widget: work by state"]
    assert work["form"] == "stacked"
    assert {q["label"]: q["state"] for q in work["queries"]} == {
        "waiting": ["new", "ready", "redo", "checked"], "working": ["building"], "stopped": ["held", "dead"]}   # none finished
    ctx.close()


def test_money_is_read_from_the_field_and_the_asked_numbers_are_charted(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    got = default(pg)
    assert got["widget: cost per hour"]["display"]["unit"] == "usd/h"
    assert pg.evaluate("() => dashCostUnit({ name: 'cost', unit: 'count' })") == "usd"
    assert {"widget: attempts, average", "widget: net lines per hour", "widget: loop hours, average"} <= set(got)
    assert not any("rank" in t for t in got)
    ctx.close()


def test_a_change_from_near_zero_is_not_said(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    assert pg.evaluate("() => dashStartsNearZero([{ series: [{ values: [0.1, 5, 55] }] }])") is True
    assert pg.evaluate("() => dashStartsNearZero([{ series: [{ values: [40, 45, 50] }] }])") is False
    ctx.close()


def test_a_rate_stat_reads_a_recent_average_not_its_last_bucket(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    assert default(pg)["widget: completions per hour"]["display"]["recent"] == 10
    got = pg.evaluate("""() => dashAnswer({ form: "stat", display: { recent: 2 }, queries: [{ id: "a" }] },
      [{ id: "a", series: [{ name: "x", values: [4, null, 2, 0] }] }])[0].series[0].values""")
    assert got == [4, 4, 2, 1]
    ctx.close()


def test_a_default_with_no_cost_has_three_stats_and_with_no_kinds_charts_series(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    got = pg.evaluate("""([f, items]) => {
      const bare = JSON.parse(JSON.stringify(f));
      bare.sources.items.kinds.widget.fields = [];
      bare.sources.items.kinds.log.fields = [];
      bare.sources.items.kinds.part.fields = [];
      const stats = dashDefault(bare, items.kinds).panels.filter((p) => p.form === "stat").length;
      bare.sources.items.kinds = {};
      return { stats, series: dashDefault(bare, []).panels.map((p) => p.queries[0].series) };
    }""", [FIELDS, ITEMS])
    assert got == {"stats": 3, "series": ["stock.x"]}
    ctx.close()


def test_the_default_has_a_panel_of_every_chart_family(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    got = pg.evaluate("""([f, items]) => {
      const rich = JSON.parse(JSON.stringify(f));
      rich.sources.items.kinds.widget.fields = [{ name: "cost_usd", unit: "usd" }, { name: "net_lines", unit: "lines" }];
      rich.sources.frequency = { goals: ["widgets-held"] };
      const made = dashDefault(rich, items.kinds).panels;
      return { made: made.map((p) => normalizeForm(p).form), all: Object.keys(plotForms()), n: made.length, most: DASH_MOST };
    }""", [FIELDS, ITEMS])
    assert set(got["all"]) <= set(got["made"])
    assert got["n"] <= got["most"]
    ctx.close()


def test_the_default_draws_no_response_from_arrivals_against_completions(browser, site):
    """dev/records/frequency-refuses-noise.md: arrivals and completions are not shown as a working Bode or Nyquist
    example; a goal's declared process is, when there is one."""
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    got = pg.evaluate("""([f, items]) => {
      const freq = (made) => made.filter((p) => ["bode", "nyquist", "pole-zero"].includes(normalizeForm(p).form))
        .map((p) => ({ form: normalizeForm(p).form, q: p.queries[0] }));
      const withGoal = JSON.parse(JSON.stringify(f));
      withGoal.sources.frequency = { goals: ["widgets-held"] };
      return { bare: freq(dashDefault(f, items.kinds).panels), goal: freq(dashDefault(withGoal, items.kinds).panels) };
    }""", [FIELDS, ITEMS])
    assert got["bare"] == []
    assert sorted(p["form"] for p in got["goal"]) == ["bode", "nyquist", "pole-zero"]
    assert all(p["q"] == {"id": "a", "source": "frequency", "model": {"goal": "widgets-held"}} for p in got["goal"])
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
    pg.wait_for_function("() => !document.getAnimations().some((a) => a.effect?.target?.classList?.contains('dash-cell'))")   # settled

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


def test_a_duration_stat_is_over_the_whole_window_and_says_who_is_still_waiting(browser, site):
    ctx = context(browser)
    now = 1795400000.0
    waiting = [{"id": f"widget/{i}", "kind": "widget", "state": "ready", "entered": now - 3600 * (i + 1)} for i in range(3)]
    ctx.route("**/api/items?*", lambda r: r.fulfill(json={**ITEMS, "items": waiting, "matched": {"widget": 3}})
              if "state=ready" in r.request.url else r.fallback())
    pg = opened(ctx, f"{site}/dashboard")
    stat = default(pg)["widget: median wait of items that left ready"]
    assert stat["display"]["whole"] is True and stat["display"]["still"] == {"kind": "widget", "state": "ready"}
    asked = [q for q in pg.evaluate("() => window.__asked") if q.get("measure") == "time_in_state" and "bucket" in q]
    assert asked and all(q["bucket"] >= 86400 for q in asked)
    assert "whole" not in asked[0] and "still" not in asked[0]                    # the server is sent only query keys
    assert pg.evaluate("""() => [[1795390000, 1795400000], [86400 * 20000 - 50, 86400 * 20000 + 50], [1000, 87400]]
      .every(([a, b]) => { const s = dashWholeBucket(a, b); return s >= b - a && Math.floor(a / s) === Math.floor((b + 120) / s); })""")
    assert pg.evaluate("(x) => dashStillWords(x, 3, 1795400000)", waiting) == "still waiting: 3, median age 2.0h"
    assert pg.evaluate("(x) => dashStillWords(x, 9, 1795400000)", waiting) == "still waiting: 9"   # a cut list gives no median
    pg.wait_for_function("() => [...document.querySelectorAll('.panel-note')].some((e) => e.textContent.includes('still waiting: 3'))")
    ctx.close()


@pytest.mark.parametrize("bad", ["constructor", "toString", "__proto__", 7, None])
def test_a_crafted_draft_cannot_freeze_the_tab(browser, site, bad):
    ctx = context(browser)
    panels = [{"id": "a", "title": "x", "form": "line", "size": bad, "queries": []},
              {"id": "__proto__", "title": "y" * 5000, "form": {"no": 1}, "size": "m", "queries": "no", "display": 3}]
    panels += [{"id": f"n{i}", "title": "n", "form": "line", "size": "s", "queries": []} for i in range(200)]
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded({'title': 't', 'since': 'constructor', 'panels': panels})}")
    d = pg.evaluate("() => dashboardDraft()")
    assert d["panels"][0]["size"] == "m" and d["since"] == "1d" and len(d["panels"]) == 32
    assert len(d["panels"][1]["title"]) == 200 and d["panels"][1]["form"] == "line" and d["panels"][1]["queries"] == []
    assert pg.errors == []
    ctx.close()


def encoded(d) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")


def opened_plain(ctx, url):
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(url)
    pg.wait_for_selector(".dash-cell")
    return pg


PLAIN = {"title": "t", "panels": [{"id": "g", "title": "good", "form": "line", "size": "m",
                                   "queries": [{"id": "a", "source": "counts", "agg": "last"}], "display": {}}]}


def test_a_hung_answer_is_late_keeps_its_data_and_is_asked_again(browser, site):
    ctx = context(browser)
    ctx.clock.install()
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(PLAIN)}")
    pg.wait_for_selector(".panel[data-state=drawn]")
    held = []
    pg.route("**/api/query?*", lambda r: held.append(r))
    pg.evaluate("() => { localStorage.setItem(dashEveryKey(), 'Off'); dashPoll(); void dashRefresh(); }")
    pg.wait_for_function("() => window.__queries > 1")
    state = lambda: pg.eval_on_selector(".panel", "e => e.dataset.state")     # noqa: E731
    pg.clock.run_for(4000)
    assert state() == "drawn"
    pg.clock.run_for(5000)
    assert state() == "late" and pg.locator(".panel-flag").inner_text() == "Late"
    pg.clock.run_for(17000)
    assert "asking again" in pg.locator(".dash-said").inner_text()
    assert state() == "late" and pg.locator(".panel canvas").count() > 0        # what it showed stays
    pg.unroute("**/api/query?*")
    pg.clock.run_for(11000)
    pg.wait_for_selector(".panel[data-state=drawn]")
    assert len(held) == 1
    ctx.close()


def test_a_snapshot_says_the_dashboard_needs_the_live_server(browser, site):
    status = urllib.request.urlopen(site + "/api/status", timeout=10).read().decode()
    ctx = context(browser)
    ctx.add_init_script(f"window.SNAPSHOT = {{ at: 1795400000, data: {{ status: {status} }} }};")
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(f"{site}/#/dashboard")
    pg.wait_for_selector(".dash-snapshot")
    assert "needs the live server" in pg.locator(".dash-snapshot").inner_text()
    assert pg.locator(".dash-cell").count() == 0 and pg.errors == []
    ctx.close()


def test_a_recent_average_is_weighted_by_each_buckets_span(browser, site):
    ctx = context(browser)
    pg = opened(ctx, f"{site}/dashboard")
    assert pg.evaluate("() => dashRecent([10, 20], 2, [1, 3])") == [10, 17.5]
    assert pg.evaluate("() => dashSpans([100, 160, 220], 250)") == [60, 60, 30]
    got = pg.evaluate("""() => dashAnswer({ form: "stat", display: { recent: 2 }, queries: [{ id: "a" }] },
      [{ id: "a", times: [0, 30], series: [{ name: "x", values: [10, 20] }] }], { until: 120 })[0].series[0].values""")
    assert got == [10, 17.5]
    ctx.close()


def test_a_draft_too_large_for_an_address_stays_in_this_browser(browser, site):
    ctx = context(browser)
    pg = opened_plain(ctx, f"{site}/dashboard?draft={encoded(PLAIN)}")
    got = pg.evaluate("""() => {
      const d = dashboardDraft();
      d.panels = Array.from({ length: 20 }, (_, i) => ({ ...d.panels[0], id: `p${i}`, display: { pad: "n".repeat(4000) } }));
      saveDashboardDraft(d);
      return { search: location.search, said: document.querySelector(".dash-said").textContent,
               kept: JSON.parse(localStorage.getItem(dashKey())).panels.length };
    }""")
    assert "draft=" not in got["search"] and got["kept"] == 20 and "Too large" in got["said"]
    pg.get_by_role("button", name="Copy link").click()
    assert "Too large" in pg.locator(".dash-said").inner_text()
    ctx.close()
