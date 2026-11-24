"""The dashboard's chart panel (static/panels.js) in a real browser, against a fake of the query API: every form in
both themes and at both widths, the four states, a refresh in place, one request for many panels, and the owner's
rule that nothing but the cursor is drawn over a plot.

    uv run --with playwright==1.63.0 python -m pytest tests/test_panels.py -n 4

PANEL_SHOTS=<directory> also saves the gallery of every form, in each theme and width.
"""

from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

try:
    from playwright import sync_api as playwright
except ImportError:
    playwright = None
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"
ORIGIN = "http://panels.test"
NOW = 1795400000.0
STEP = 720
POINTS = 120
SCRIPTS = ["elk.bundled.js", "uplot/uPlot.iife.min.js", "util.js", "charts.js", "frames.js", "panels.js"]
PAGE = (
    '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    '<link rel="stylesheet" href="/static/style.css"><link rel="stylesheet" href="/static/panels.css">'
    "<style>body{display:block;height:auto;padding:16px}</style></head><body><div id=page></div>"
    + "".join(f'<script src="/static/{n}"></script>' for n in SCRIPTS)
    + "</body></html>"
)
TYPES = {".js": "text/javascript", ".css": "text/css"}


def wave(i: int, seed: int, base: float, swing: float) -> float:
    return max(0.0, base + swing * math.sin(i / 9 + seed) + swing * 0.35 * math.sin(i / 2.3 + seed * 2))


FAKE: dict[str, tuple[str, list[tuple[str, float, float]]]] = {
    "cost": ("usd/h", [("merged", 42, 16), ("review", 26, 9), ("ready", 15, 6), ("failed", 5, 3)]),
    "latency": ("s", [("p50", 48, 12), ("p90", 190, 40), ("p99", 620, 130)]),
    "throughput": ("items/h", [("gap", 18, 6), ("note", 7, 3), ("research", 3, 1.5)]),
    "slow_rate": ("items/h", [("rare", 0.08, 0.03)]),
    "queue": ("items", [("waiting", 128, 38)]),
    "memory": ("bytes", [("daemon", 2.6e9, 4e8), ("web", 8.2e8, 1e8)]),
    "share": ("%", [("busy", 64, 18)]),
    "wide": ("items", [(f"group {n}", 20 + n * 3, 4 + n / 2) for n in range(12)] + [("other", 12, 3)]),
}


def fake_answer(payload: dict) -> dict:
    times = [NOW - STEP * (POINTS - 1 - i) for i in range(POINTS)]
    results = []
    for q in payload["queries"]:
        field = q.get("field") or q.get("series")
        if field == "broken":
            results.append({"id": q["id"], "error": "no field named broken on this kind"})
        elif field == "nothing":
            results.append({"id": q["id"], "times": times, "series": [{"name": "x", "values": [None] * POINTS}],
                            "unit": "items", "capped": 0, "read_log": False})
        else:
            unit, shapes = FAKE[field]
            series = [{"name": name, "values": [None if field == "queue" and 40 <= i < 46 else round(wave(i, n, b, s), 4)
                                                for i in range(POINTS)]}
                      for n, (name, b, s) in enumerate(shapes)]
            results.append({"id": q["id"], "times": times, "series": series, "unit": unit, "capped": 0, "read_log": False})
    return {"now": NOW, "since": times[0], "until": NOW, "step": STEP, "results": results}


def decode(url: str) -> dict:
    q = parse_qs(urlparse(url).query)["q"][0]
    return json.loads(base64.urlsafe_b64decode(q + "=" * (-len(q) % 4)))


def query(field: str, **more) -> dict:
    return {"id": "a", "source": "items", "kind": "gap", "field": field, "agg": "sum", **more}


def panel(pid: str, form: str, field: str, title: str, size: str = "m", **display) -> dict:
    return {"id": pid, "title": title, "note": "", "form": form, "queries": [query(field)], "display": display, "size": size, "tall": False}


GALLERY = [
    panel("stat1", "stat", "queue", "Items waiting", "s", unit="items"),
    panel("stat2", "stat", "cost", "AI cost per hour", "s", decimals=2),
    panel("stat3", "stat", "share", "Time busy", "s"),
    panel("line", "line", "latency", "Time in review", "l", legend="right", legend_values=["last", "avg", "max"],
          thresholds=[{"value": 600, "label": "limit"}]),
    panel("table", "table", "throughput", "Throughput by kind", "s", legend_values=["last", "avg", "max"]),
    panel("stacked", "stacked", "cost", "AI cost by state", "m", legend="right", legend_values=["last", "max"], decimals=2,
          y={"min": 0}, thresholds=[{"value": 120, "label": "budget"}]),
    panel("bars", "bars", "throughput", "Items finished", "m", legend="bottom", legend_values=["last", "max"]),
    panel("area", "area", "memory", "Memory", "m", legend="right", legend_values=["last", "max"]),
    panel("log", "line", "latency", "Time in review, log scale", "m", legend="bottom", legend_values=["last"], y={"log": True}),
    panel("rate", "line", "slow_rate", "A slow rate reads per day", "m", legend="hidden"),
    panel("gaps", "area", "queue", "Queue, with a gap in the record", "m", legend="hidden", y={"min": 0}),
    panel("wide", "stacked", "wide", "Twelve groups and other", "full", legend="right", legend_values=["last", "avg", "max"]),
]
FORMS = ["line", "area", "stacked", "bars", "stat", "table"]

# what lies over a plot: everything in a panel but the plot's own canvas, axes and cursor, or an ancestor of them
OVERLAPS = """() => {
  const hit = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5
    && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5;
  const out = [];
  for (const panel of document.querySelectorAll('.panel')) {
    const over = panel.querySelector('.u-over');
    if (!over || !over.getClientRects().length) continue;
    const plot = over.getBoundingClientRect();
    for (const el of panel.querySelectorAll('*')) {
      if (el === over || el.contains(over) || !el.getClientRects().length) continue;
      if (el.closest('.u-over') && /u-cursor/.test(el.className)) continue;
      if (el.closest('.u-wrap') && (el.tagName === 'CANVAS' || el.classList.contains('u-under'))) continue;
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      if (hit(el.getBoundingClientRect(), plot)) out.push(`${panel.dataset.panelId}: ${el.tagName}.${el.className}`);
    }
  }
  return out;
}"""
NO_SCROLL = "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
PAINTED = """(id) => {
  const c = document.querySelector(`[data-panel-id="${id}"] canvas`);
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  const seen = new Set();
  for (let i = 0; i < d.length; i += 40) if (d[i + 3]) seen.add(`${d[i]},${d[i + 1]},${d[i + 2]}`);
  return seen.size;
}"""


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


class Site:
    """A page served entirely through routes (no port), with the query API faked and its requests counted."""

    def __init__(self, browser, width=1440, height=1000, scheme="light"):
        self.context = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme)
        self.page = self.context.new_page()
        self.queries: list[dict] = []
        self.fields = 0
        self.hold = None
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.route(f"{ORIGIN}/**", self.serve)
        self.page.goto(f"{ORIGIN}/")

    def serve(self, route):
        url = route.request.url
        path = urlparse(url).path
        if path == "/":
            route.fulfill(content_type="text/html", body=PAGE)
        elif path.startswith("/static/"):
            f = STATIC / path.removeprefix("/static/")
            route.fulfill(content_type=TYPES.get(f.suffix, "text/plain"), body=f.read_bytes())
        elif path == "/api/query/fields":
            self.fields += 1
            route.fulfill(json={"sources": {}, "aggregations": ["sum"], "transforms": ["none"]})
        elif path == "/api/query":
            payload = decode(url)
            self.queries.append(payload)
            if self.hold and self.hold(payload, route):
                return
            route.fulfill(json=fake_answer(payload))
        else:
            route.fulfill(status=404, body="")

    def draw(self, configs, every=60000):
        self.page.evaluate("([c, every]) => { window.P = pagePanels(document.getElementById('page'), c, { since: 86400, every }); }",
                           [configs, every])
        self.settled(len(configs))

    def settled(self, n):
        """Every panel drawn: a panel off the screen draws when it comes on, so each is brought on in turn."""
        self.page.wait_for_function("(n) => document.querySelectorAll('.panel').length === n", arg=n)
        for i in range(n):
            one = self.page.locator(".panel").nth(i)
            one.scroll_into_view_if_needed()
            self.page.wait_for_function(
                "(el) => el.dataset.state !== 'loading' && (el.querySelector('.panel-chart').hidden || el.querySelector('.u-over'))",
                arg=one.element_handle())
        self.page.evaluate("window.scrollTo(0, 0)")

    def close(self):
        self.context.close()


@pytest.fixture
def site(browser):
    s = Site(browser)
    yield s
    assert not s.errors, s.errors
    s.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 390])
def test_every_form_draws_with_no_page_scroll_and_nothing_over_a_plot(browser, scheme, width):
    s = Site(browser, width=width, height=1000 if width > 500 else 844, scheme=scheme)
    try:
        s.draw(GALLERY)
        assert {p["form"] for p in GALLERY} == set(FORMS)
        assert s.page.evaluate(NO_SCROLL), "the page scrolls sideways"
        assert s.page.evaluate(OVERLAPS) == []
        for p in GALLERY:
            if p["form"] in ("stat", "table"):
                assert s.page.locator(f'[data-panel-id="{p["id"]}"] .panel-spark path').first.get_attribute("d")
            else:
                s.page.locator(f'[data-panel-id="{p["id"]}"]').scroll_into_view_if_needed()
                assert s.page.evaluate(PAINTED, p["id"]) > 3, f'{p["id"]} is blank'
        out = os.environ.get("PANEL_SHOTS")
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            s.page.evaluate("window.scrollTo(0, 0)")
            s.page.screenshot(path=f"{out}/gallery-{scheme}-{width}.png", full_page=True)
        assert not s.errors, s.errors
    finally:
        s.close()


def test_the_cursor_is_read_in_the_legend_and_nothing_appears_over_the_plot(site):
    site.draw([GALLERY[3], GALLERY[5]])
    box = site.page.locator('[data-panel-id="line"] .u-over').bounding_box()
    before = site.page.locator('[data-panel-id="line"] tbody tr').first.locator("td").nth(1).inner_text()
    site.page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] / 2)
    site.page.wait_for_function("document.querySelector('[data-panel-id=line]').hasAttribute('data-hover')")
    assert site.page.locator('[data-panel-id="line"] tbody tr').first.locator("td").nth(1).inner_text() != before
    assert site.page.evaluate(OVERLAPS) == []
    # the cursor is shared: the other panel reads the same moment
    head = "document.querySelector('[data-panel-id=%s] th.panel-now').textContent"
    site.page.wait_for_function(f"{head % 'stacked'} === {head % 'line'} && {head % 'line'} !== 'Last'")


KEPT = ".panel, .panel canvas, .uplot, .panel-legend tr, .panel-stat, .panel-data-table tr"


def test_a_refresh_draws_in_place(site):
    site.draw(GALLERY[:9])
    site.page.evaluate("(q) => { window.kept = [...document.querySelectorAll(q)]; }", KEPT)
    assert site.page.evaluate("window.kept.length") > 30
    configs = GALLERY[:9]
    n = len(site.queries)
    site.page.locator('[data-panel-id="line"]').scroll_into_view_if_needed()
    site.page.wait_for_timeout(100)
    drawn = site.page.evaluate("document.querySelector('[data-panel-id=line]').draws")
    site.page.evaluate("(c) => P.setConfigs(c)", configs)
    site.page.wait_for_function("(d) => document.querySelector('[data-panel-id=line]').draws > d", arg=drawn)
    assert len(site.queries) == n + 1
    assert site.page.evaluate("""(q) => window.kept.every((el) => el.isConnected)
        && window.kept.length === document.querySelectorAll(q).length""", KEPT)


def test_twelve_panels_make_one_request_and_same_queries_are_asked_once(site):
    configs = [panel(f"p{i}", "line", "cost" if i % 2 else "latency", f"Panel {i}") for i in range(12)]
    site.draw(configs)
    assert len(site.queries) == 1
    assert len(site.queries[0]["queries"]) == 2, "an identical query is asked once"
    answers = site.page.evaluate("""async (c) => { const m = await queryPanels(c, { since: 3600 });
        return [...m].map(([id, a]) => [id, a.results.map((r) => r.id), a.results[0].unit]); }""", configs)
    assert len(site.queries) == 2
    assert [a[0] for a in answers] == [c["id"] for c in configs]
    assert all(a[1] == ["a"] for a in answers), "each panel gets its own query id back"
    assert answers[1][2] == "usd/h" and answers[0][2] == "s"


def test_empty_failing_and_partly_failing_queries(site):
    partial = panel("partial", "line", "cost", "Partly failing")
    partial["queries"] = [query("cost"), {**query("broken"), "id": "b"}]
    site.draw([panel("empty", "line", "nothing", "Empty"), panel("bad", "stacked", "broken", "Failing"), partial,
               {"id": "none", "title": "No query", "form": "line", "queries": [], "display": {}, "size": "m"}])
    empty = site.page.locator('[data-panel-id="empty"]')
    assert empty.get_attribute("data-state") == "empty" and "nothing" in empty.inner_text().lower()
    bad = site.page.locator('[data-panel-id="bad"]')
    assert bad.get_attribute("data-state") == "error" and "no field named broken" in bad.inner_text()
    flag = site.page.locator('[data-panel-id="partial"] .panel-flag')
    assert flag.inner_text() == "Partial" and "broken" in flag.get_attribute("title")
    assert site.page.evaluate(OVERLAPS) == []


def test_loading_late_and_error_keep_the_numbers_and_stay_off_the_plot(site):
    site.draw([GALLERY[3]])
    p = site.page.locator('[data-panel-id="line"]')
    for state, word in (("late", "Late"), ("error", "Error")):
        site.page.evaluate("(s) => document.querySelector('.panel').setState(s, 'the reason')", state)
        assert p.locator(".panel-flag").inner_text() == word and p.locator(".u-over").is_visible()
        assert site.page.evaluate(OVERLAPS) == []
    fresh = site.page.evaluate("""() => { const el = chartPanel({ id: 'x', title: 'x', form: 'line', queries: [], display: {} });
        el.id = 'fresh'; document.getElementById('page').append(el);
        const said = {}; for (const s of ['loading', 'late', 'error', 'empty']) {
          el.setState(s, 'why ' + s); said[s] = el.querySelector('.panel-message').innerText; }
        el.destroy(); return said; }""")
    assert all(f"why {k}" in v for k, v in fresh.items())


def test_a_hidden_tab_does_not_ask_and_asks_when_shown(site):
    site.draw([GALLERY[3]], every=80)
    site.page.evaluate("""() => { window.tabHidden = true;
        Object.defineProperty(document, 'hidden', { configurable: true, get: () => window.tabHidden });
        document.dispatchEvent(new Event('visibilitychange')); }""")
    site.page.wait_for_timeout(120)
    n = len(site.queries)
    site.page.wait_for_timeout(500)
    assert len(site.queries) == n
    site.page.evaluate("() => { window.tabHidden = false; document.dispatchEvent(new Event('visibilitychange')); }")
    site.page.wait_for_timeout(300)
    assert len(site.queries) > n
    site.page.evaluate("P.stop()")


def test_a_panel_off_screen_does_not_redraw_until_it_returns(browser):
    s = Site(browser, height=500)
    try:
        s.draw([panel(f"p{i}", "line", "cost", f"P{i}", "full") for i in range(6)])
        last = '[data-panel-id="p5"]'
        s.page.wait_for_function("(q) => document.querySelector(q).getBoundingClientRect().top > innerHeight + 200", arg=last)
        s.page.wait_for_timeout(150)                 # its observer has said it is off the screen
        before = s.page.evaluate("(q) => document.querySelector(q).draws", last)
        s.page.evaluate("""(q) => document.querySelector(q).update(
            [{ id: 'a', times: [1, 2], series: [{ name: 'merged', values: [1, 2] }], unit: 'usd/h' }],
            { since: 1, until: 2, step: 1 })""", last)
        s.page.wait_for_timeout(100)
        assert s.page.evaluate("(q) => document.querySelector(q).draws", last) == before
        s.page.locator(last).scroll_into_view_if_needed()
        s.page.wait_for_function("([q, n]) => document.querySelector(q).draws > n", arg=[last, before])
    finally:
        s.close()


def test_a_stale_answer_never_overwrites_a_newer_one(site):
    held = []
    site.hold = lambda payload, route: not held and (held.append((payload, route)) or True)
    first = panel("p", "line", "cost", "Stale")
    site.page.evaluate("(c) => { window.P = pagePanels(document.getElementById('page'), [c], { since: 86400, every: 60000 }); }", first)
    site.page.wait_for_timeout(200)
    assert held, "the first request is being held"
    site.hold = None
    newer = {**first, "queries": [query("queue")]}
    site.page.evaluate("(c) => P.setConfigs([c])", newer)
    site.page.wait_for_function("document.querySelector('.panel').innerText.includes('waiting')")
    shown = site.page.evaluate("document.querySelector('.panel').innerText")
    assert "merged" not in shown
    try:
        held[0][1].fulfill(json=fake_answer(held[0][0]))     # the old answer lands late (or was already cancelled)
    except Exception:
        pass
    site.page.wait_for_timeout(150)
    assert site.page.evaluate("document.querySelector('.panel').innerText") == shown


def test_series_that_come_and_go_keep_their_colours_and_the_chart(site):
    site.draw([panel("p", "stacked", "cost", "Groups", legend="right", legend_values=["last"])])
    answer = """(names) => { const el = document.querySelector('.panel'); const times = [1795399000, 1795399500, 1795400000];
        el.update([{ id: 'a', times, unit: 'usd/h', series: names.map((name) => ({ name, values: [1, 2, 3] })) }],
                  { since: 1795399000, until: 1795400000, step: 500 });
        return Object.fromEntries([...el.querySelectorAll('.panel-legend tbody tr')].map((r) =>
          [r.innerText.split('\\t')[0].trim(), r.querySelector('i').style.getPropertyValue('--swatch')])); }"""
    site.page.evaluate("window.u0 = document.querySelector('.uplot')")
    one = site.page.evaluate(answer, ["merged", "review", "ready", "failed"])
    two = site.page.evaluate(answer, ["ready", "failed"])
    assert two["ready"] == one["ready"] and two["failed"] == one["failed"], "a colour follows its series, not its rank"
    three = site.page.evaluate(answer, ["merged", "review", "ready", "failed", "fresh"])
    assert three["merged"] == one["merged"] and len(set(three.values())) == 5
    assert site.page.evaluate("window.u0 === document.querySelector('.uplot') && window.u0.isConnected")


def test_units_read_well(site):
    site.draw(GALLERY)
    def text(pid: str) -> str:
        return site.page.locator(f'[data-panel-id="{pid}"]').inner_text()

    assert "$" in text("stacked") and "/h" in text("stacked")
    assert "GB" in text("area")
    assert " min" in text("line") or " s" in text("line")
    assert "/day" in text("rate"), "0.08 an hour reads per day"
    assert "%" in text("stat3")


def test_legend_places_and_values(site):
    site.draw([panel("r", "line", "cost", "Right", legend="right", legend_values=["last", "avg", "max"]),
               panel("b", "line", "cost", "Bottom", legend="bottom", legend_values=["max"]),
               panel("h", "line", "cost", "Hidden", legend="hidden")])
    geo = site.page.evaluate("""() => Object.fromEntries(['r', 'b'].map((id) => { const p = document.querySelector(`[data-panel-id=${id}]`);
        const a = p.querySelector('.u-over').getBoundingClientRect(), l = p.querySelector('.panel-legend').getBoundingClientRect();
        return [id, { beside: l.left >= a.right, below: l.top >= a.bottom,
          heads: [...p.querySelectorAll('thead th')].map((t) => t.textContent) }]; }))""")
    assert geo["r"]["beside"] and geo["r"]["heads"][-3:] == ["Last", "Avg", "Max"]
    assert geo["b"]["below"] and geo["b"]["heads"][-1] == "Max"
    assert not site.page.locator('[data-panel-id="h"] .panel-legend').is_visible()


def test_fields_are_asked_for_once(site):
    assert site.page.evaluate("""async () => { const [a, b] = await Promise.all([queryFields(), queryFields()]);
        await queryFields(); return a === b; }""")
    assert site.fields == 1


def test_a_change_of_theme_repaints(browser):
    s = Site(browser, scheme="light")
    try:
        s.draw([GALLERY[3]])
        swatch = "getComputedStyle(document.querySelector('.panel-legend i')).backgroundColor"
        light = s.page.evaluate(swatch)
        s.page.emulate_media(color_scheme="dark")
        s.page.wait_for_function("(c) => getComputedStyle(document.querySelector('.panel-legend i')).backgroundColor !== c", arg=light)
        assert not s.errors
    finally:
        s.close()


def test_axis_labels_say_their_ticks(site):
    site.draw(GALLERY)
    labels = "(id) => document.querySelector(`[data-panel-id=${id}] .panel-mount`).plot.axes[1]._values"
    for pid in ("line", "stacked", "bars", "area", "log", "rate"):
        said = [v for v in site.page.evaluate(labels, pid) if v]
        assert len(said) >= 2 and len(set(said)) == len(said), f"{pid}: {said}"
        assert not any(v.startswith("0.0") and float(v[:3]) == 0 for v in said), f"{pid}: {said}"
    assert "0" in site.page.evaluate(labels, "area"), "zero is a plain 0"


@pytest.mark.parametrize("width", [1440, 390])
def test_stat_numbers_are_whole_and_inside_their_panel(browser, width):
    s = Site(browser, width=width)
    try:
        s.draw(GALLERY[:3])
        assert s.page.evaluate("""() => [...document.querySelectorAll('.panel-stat-num')].every((n) => {
            const box = n.closest('.panel-stats').getBoundingClientRect(), r = n.getBoundingClientRect();
            return n.scrollWidth <= n.clientWidth && r.bottom <= box.bottom + 1; })""")
    finally:
        s.close()


def test_a_changed_query_never_shows_the_old_numbers(site):
    site.draw([panel("p", "line", "cost", "Changing")])
    held = []
    site.hold = lambda payload, route: held.append(route) or True
    site.page.evaluate("(c) => P.setConfigs([c])", panel("p", "line", "queue", "Changing"))
    site.page.wait_for_function("document.querySelector('.panel').dataset.state === 'loading'")
    assert "$" not in site.page.locator(".panel").inner_text()
    site.page.evaluate("P.stop()")


def test_a_hidden_query_is_not_asked_for_or_drawn(site):
    two = panel("two", "line", "cost", "One hidden", legend="right", legend_values=["last"])
    two["queries"] = [query("queue"), {**query("cost"), "id": "b", "hidden": True}]
    gone = panel("gone", "line", "cost", "All hidden")
    gone["queries"] = [{**query("cost"), "hidden": True}]
    site.draw([two, gone])
    assert [q["field"] for q in site.queries[0]["queries"]] == ["queue"]
    assert not any("hidden" in q for q in site.queries[0]["queries"])
    assert site.page.locator('[data-panel-id="two"] .panel-legend tbody tr').count() == 1
    shut = site.page.locator('[data-panel-id="gone"]')
    assert shut.get_attribute("data-state") == "empty"
    assert "All of this panel's queries are hidden" in shut.inner_text()
    # handed an answer for a hidden query anyway, the panel still does not draw it
    site.page.evaluate("""() => document.querySelector('[data-panel-id=gone]').update(
        [{ id: 'a', times: [1, 2], series: [{ name: 'x', values: [1, 2] }], unit: 'items' }], { since: 1, until: 2, step: 1 })""")
    assert shut.get_attribute("data-state") == "empty"


def test_only_hidden_queries_make_no_request(site):
    gone = panel("gone", "line", "cost", "All hidden")
    gone["queries"] = [{**query("cost"), "hidden": True}]
    site.draw([gone])
    assert site.queries == []
    assert "are hidden" in site.page.locator(".panel").inner_text()


@pytest.mark.parametrize("width,where", [(1440, "beside"), (390, "below")])
def test_an_unset_legend_is_beside_a_wide_panel_and_under_a_narrow_one(browser, width, where):
    s = Site(browser, width=width)
    try:
        s.draw([panel("auto", "line", "cost", "Automatic", "full")])
        geo = s.page.evaluate("""() => { const p = document.querySelector('.panel');
            const a = p.querySelector('.u-over').getBoundingClientRect(), l = p.querySelector('.panel-legend').getBoundingClientRect();
            return { beside: l.left >= a.right, below: l.top >= a.bottom, shown: l.width > 0 }; }""")
        assert geo["shown"] and geo[where], geo
        assert s.page.evaluate(OVERLAPS) == [] and s.page.evaluate(NO_SCROLL)
    finally:
        s.close()
