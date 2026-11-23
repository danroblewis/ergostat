"""The panel editor in a real browser, against a stub of panels.js and a fake query API. Nothing listens on a port:
every address is answered by Playwright's routing.

    uv run --with playwright==1.63.0 python -m pytest tests/test_panel_editor.py -q

Set PANEL_EDITOR_SHOTS to a directory to keep the screenshots.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

try:
    from playwright import sync_api as playwright
except ImportError:
    playwright = None
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

STATIC = Path(__file__).resolve().parent.parent / "ergostat" / "web" / "static"
ORIGIN = "http://editor.test"
FIELDS = {
    "sources": {
        "items": {"kinds": {
            "gap": {"fields": [{"name": "ai_cost_usd", "unit": "usd"}, {"name": "tokens", "unit": "tokens"}],
                    "states": ["ready", "building", "merged"], "group_by": ["state", "size"]},
            "note": {"fields": [{"name": "words", "unit": "words"}], "states": ["open", "closed"], "group_by": ["state"]},
        }},
        "moves": {"kinds": {"gap": {"states": ["ready", "building", "merged"]}}},
        "counts": {"kinds": ["gap", "note"]},
        "series": {"series": [{"name": "stock.backlog", "unit": "items"}]},
        "events": {"types": ["gap.merged", "gap.failed"]},
    },
    "aggregations": ["count", "sum", "avg", "min", "max", "last", "p50", "p90", "p95", "p99"],
    "transforms": ["none", "rate", "delta", "cumulative", "moving_avg"],
}
STUB = """
window.__log = {asked: [], charts: [], configs: [], states: [], updates: [], destroyed: 0};
window.__holds = [];
const COLOURS = ['var(--g0)', 'var(--g1)', 'var(--g2)', 'var(--g3)'];
function drawStub(el, cfg, results) {
  const series = results.flatMap(r => r.series || []);
  const n = Math.max(1, ...series.map(x => x.values.length));
  const tops = Array.from({length: n}, (_, i) => series.reduce((t, x) => t + (x.values[i] || 0), 0));
  const most = Math.max(1, ...tops);
  const bars = Array.from({length: n}, (_, i) => {
    let at = 100;
    const parts = series.map((x, k) => { const h = (x.values[i] || 0) / most * 96; at -= h;
      return `<rect x="${i / n * 100}" y="${at}" width="${90 / n}" height="${h}" fill="${COLOURS[k % 4]}"/>`; });
    return parts.join('');
  }).join('');
  el.innerHTML = `<div style="font-weight:600">${cfg.title || 'Untitled'}</div><div style="display:flex;flex:1;min-height:0;gap:8px">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style="flex:1;min-width:0;height:100%">${bars}</svg>
    <div>${series.map((x, k) => `<div><span style="color:${COLOURS[k % 4]}">&#9632;</span> ${x.name}</div>`).join('')}</div></div>`;
}
function chartPanel(config) {
  const el = document.createElement('div');
  el.className = 'stub-chart';
  el.style.cssText = 'display:flex;flex-direction:column;height:100%;background:var(--bg);padding:8px;box-sizing:border-box';
  let cfg = config;
  __log.charts.push(config);
  el.update = (results) => {
    __log.updates.push(JSON.parse(JSON.stringify(results)));
    el.dataset.state = 'drawn';
    drawStub(el, cfg, results);
  };
  el.setState = (state, reason) => { __log.states.push([state, reason]); el.dataset.state = state; el.textContent = reason || state; };
  el.setConfig = (c) => { cfg = c; __log.configs.push(JSON.parse(JSON.stringify(c))); };
  el.destroy = () => { __log.destroyed++; };
  return el;
}
async function queryFields() { return (await fetch('/api/query/fields')).json(); }
async function queryPanels(configs, {since} = {}) {
  const queries = configs.flatMap(c => c.queries);
  __log.asked.push(JSON.parse(JSON.stringify(queries)));
  const hold = __holds.shift();
  if (hold) await new Promise(r => { hold.release = r; __log.held = (__log.held || []).concat([hold]); });
  const q = btoa(JSON.stringify({since, queries})).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
  const answer = await (await fetch('/api/query?q=' + q)).json();
  return new Map(configs.map(c => [c.id, {results: answer.results, meta: {now: answer.now}}]));
}
"""
PAGE = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/style.css"><link rel="stylesheet" href="/static/panel-editor.css"></head>
<body><main id="main"><button id="opener">Edit</button></main>
<script src="/static/elk.bundled.js"></script>
<script src="/static/util.js"></script><script>{STUB}</script><script src="/static/panel-editor.js"></script></body></html>"""
OPEN = """(config) => {
  window.__result = {changes: []};
  window.__original = config;
  document.getElementById('opener').focus();
  window.__editor = openPanelEditor(config, {
    onChange: c => __result.changes.push(c),
    onSave: c => { __result.saved = c; },
    onCancel: c => { __result.cancelled = c; },
  });
}"""
HOUR_COST = {"source": "items", "kind": "gap", "field": "ai_cost_usd", "group_by": "state", "agg": "sum",
             "transform": "rate", "rate_per": "hour"}


def answer_for(queries):
    results = []
    for q in queries:
        if q.get("field") == "broken":
            results.append({"id": q["id"], "error": "broken: this field cannot be read"})
            continue
        names = ["ready", "building", "merged"] if q.get("group_by") == "state" else [q.get("field") or q["source"]]
        series = [{"name": n, "values": [round((k + 1) * (2 + (i * (k + 2)) % 7) * 0.4, 2) for i in range(24)]}
                  for k, n in enumerate(names)]
        results.append({"id": q["id"], "times": [1795313600.0 + 3600 * i for i in range(24)], "series": series,
                        "unit": "usd/h", "capped": 0, "read_log": False})
    return {"now": 1795400000.0, "since": 1795313600.0, "until": 1795400000.0, "step": 3600, "results": results}


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def ed(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 860})
    page = context.new_page()
    page.requests = []
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))

    def handle(route):
        request = route.request
        path = request.url[len(ORIGIN):].split("?")[0]
        page.requests.append((request.method, path))
        if path == "/":
            route.fulfill(content_type="text/html", body=PAGE)
        elif path.startswith("/static/"):
            kind = "text/css" if path.endswith(".css") else "text/javascript"
            route.fulfill(content_type=kind, body=(STATIC / path[len("/static/"):]).read_text())
        elif path == "/api/query/fields":
            route.fulfill(content_type="application/json", body=json.dumps(FIELDS))
        elif path == "/api/query":
            raw = request.url.split("?q=", 1)[1]
            body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
            route.fulfill(content_type="application/json", body=json.dumps(answer_for(body["queries"])))
        else:
            route.fulfill(status=404, body="")

    page.route(f"{ORIGIN}/**", handle)
    page.goto(ORIGIN + "/")
    yield page
    assert page.errors == []
    assert {m for m, _ in page.requests} == {"GET"}, "the editor writes nothing to the server"
    context.close()


def opened(page, config):
    page.evaluate(OPEN, config)
    page.wait_for_selector(".pe-q select[data-slot=source] option[value=items]", state="attached")


def card(page, letter="a"):
    return page.locator(f".pe-q[data-query={letter}]")


def choose(page, slot, value, letter="a"):
    card(page, letter).locator(f"select[data-slot={slot}]").select_option(value)


def options(page, slot, letter="a"):
    return card(page, letter).locator(f"select[data-slot={slot}] option").evaluate_all("els => els.map(e => e.value)")


def result(page):
    return page.evaluate("__result")


def wait_drawn(page):
    page.wait_for_function("document.querySelector('.stub-chart')?.dataset.state === 'drawn'")


def shot(page, name, tmp_path):
    where = Path(os.environ.get("PANEL_EDITOR_SHOTS") or tmp_path)
    where.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(where / f"{name}.png"))


def check_built(saved):
    assert saved["title"] == "AI cost per hour by state"
    assert saved["form"] == "stacked"
    assert len(saved["queries"]) == 1
    q = saved["queries"][0]
    assert {k: q.get(k) for k in HOUR_COST} == HOUR_COST


def test_builds_cost_per_hour_by_state_stacked_by_mouse(ed, tmp_path):
    opened(ed, {"id": "p1"})
    ed.get_by_label("Title").fill("AI cost per hour by state")
    choose(ed, "source", "items")
    choose(ed, "kind", "gap")
    choose(ed, "field", "ai_cost_usd")
    choose(ed, "group_by", "state")
    choose(ed, "agg", "sum")
    choose(ed, "transform", "rate")
    assert card(ed).locator("select[data-slot=rate_per]").input_value() == "hour"
    ed.locator(".pe-seg", has_text="Stacked").click()
    wait_drawn(ed)
    ed.wait_for_function("__log.configs.at(-1)?.form === 'stacked'")
    assert "Auto (usd/h)" in ed.locator(".pe-side select").first.inner_text()
    shot(ed, "desktop-built", tmp_path)
    ed.get_by_role("button", name="Save", exact=True).click()
    check_built(result(ed)["saved"])
    assert ed.locator(".pe-overlay").count() == 0


def tab_to(page, js_test, most=80):
    for _ in range(most):
        if page.evaluate(f"(() => {{ const e = document.activeElement; return !!({js_test}); }})()"):
            return
        page.keyboard.press("Tab")
    raise AssertionError(f"never reached by Tab: {js_test}")


def key_pick(page, slot, text):
    tab_to(page, f"e.dataset.slot === '{slot}'")
    page.keyboard.type(text, delay=20)
    page.wait_for_timeout(30)


def test_builds_cost_per_hour_by_state_stacked_by_keyboard_alone(ed):
    opened(ed, {"id": "p1"})
    ed.wait_for_function("document.activeElement.dataset.slot === 'source'")
    ed.keyboard.type("Item f", delay=20)
    key_pick(ed, "kind", "gap")
    key_pick(ed, "field", "ai_")
    key_pick(ed, "group_by", "state")
    key_pick(ed, "agg", "Sum")
    key_pick(ed, "transform", "Rate")
    assert card(ed).locator("select[data-slot=transform]").input_value() == "rate"
    tab_to(ed, "e.labels?.[0]?.textContent === 'Title'")
    ed.keyboard.type("AI cost per hour by state")
    tab_to(ed, "e.type === 'radio' && e.value === 'line'")
    ed.keyboard.press("ArrowRight")
    ed.keyboard.press("ArrowRight")
    assert ed.evaluate("document.activeElement.value") == "stacked"
    tab_to(ed, "e.textContent === 'Save'")
    ed.keyboard.press("Enter")
    check_built(result(ed)["saved"])
    assert ed.evaluate("document.activeElement.id") == "opener"


def test_several_queries_add_duplicate_hide_and_remove(ed):
    opened(ed, {"id": "p1", "queries": [{**HOUR_COST, "id": "a"}]})
    wait_drawn(ed)
    ed.get_by_role("button", name="Duplicate query A").click()
    assert card(ed, "b").locator("select[data-slot=field]").input_value() == "ai_cost_usd"
    ed.wait_for_function("__log.asked.at(-1).length === 2")
    ed.get_by_role("button", name="Hide query A").click()
    ed.wait_for_function("__log.asked.at(-1).map(q => q.id).join() === 'b'")
    assert "hidden" not in ed.evaluate("__log.asked.at(-1)[0]")
    ed.get_by_role("button", name="Add query").click()
    assert ed.evaluate("document.activeElement.dataset.slot") == "source"
    assert card(ed, "c").count() == 1
    ed.get_by_role("button", name="Remove query B").click()
    assert ed.evaluate("document.activeElement.getAttribute('aria-label')") == "Remove query C"
    ed.get_by_role("button", name="Save", exact=True).click()
    saved = result(ed)["saved"]
    assert [q["id"] for q in saved["queries"]] == ["a"], "the query nothing was chosen in is not saved"
    assert saved["queries"][0]["hidden"] is True


def test_only_valid_combinations_are_offered_and_a_new_source_resets(ed):
    opened(ed, {"id": "p1", "queries": [{**HOUR_COST, "id": "a", "where": {"state": ["merged"]}}]})
    assert set(options(ed, "field")) == {"ai_cost_usd", "tokens"}
    choose(ed, "kind", "note")
    assert options(ed, "field")[-1] == "words"
    q = ed.evaluate("__editor.config.queries[0]")
    assert q["field"] == "words", "the old field is gone, and the new kind's only field is taken"
    assert q["group_by"] == "state", "what the new kind also has stays"
    assert "where" not in q, "a state the new kind does not have is not kept"
    choose(ed, "field", "words")
    choose(ed, "agg", "p90")
    assert "rate" not in options(ed, "transform"), "a rate of a percentile is not offered"
    assert ed.evaluate("__editor.config.queries[0].transform") == "none"
    assert card(ed).locator("select[data-slot=rate_per]").count() == 0
    choose(ed, "source", "moves")
    q = ed.evaluate("__editor.config.queries[0]")
    assert "field" not in q and "group_by" not in q, "what moves do not have is gone"
    assert q.get("kind") == "gap", "note is not a kind moves have, and gap is the one they do"
    choose(ed, "measure", "entries")
    assert options(ed, "agg") == ["count"]
    choose(ed, "measure", "time_in_state")
    assert "count" not in options(ed, "agg")
    assert ed.evaluate("__editor.config.queries[0].agg") == "avg"
    choose(ed, "source", "events")
    assert options(ed, "type") == ["", "gap.merged", "gap.failed"]
    assert card(ed).locator("select[data-slot=state]").count() == 0
    choose(ed, "source", "series")
    assert ed.evaluate("__editor.config.queries[0].series") == "stock.backlog", "the one choice is taken"
    assert "count" not in options(ed, "agg")
    choose(ed, "transform", "moving_avg")
    assert ed.evaluate("__editor.config.queries[0].window") == 5


def test_preview_is_debounced_and_a_stale_answer_never_replaces_a_newer_one(ed):
    opened(ed, {"id": "p1", "queries": [{**HOUR_COST, "id": "a"}]})
    wait_drawn(ed)
    before = ed.evaluate("__log.asked.length")
    for agg in ("avg", "max", "sum", "min", "max"):
        choose(ed, "agg", agg)
    ed.wait_for_function(f"__log.asked.length === {before + 1}")
    ed.wait_for_timeout(350)
    assert ed.evaluate("__log.asked.length") == before + 1, "five quick changes are one question"
    assert ed.evaluate("__log.asked.at(-1)[0].agg") == "max"

    ed.evaluate("__holds.push({})")
    choose(ed, "field", "tokens")
    ed.wait_for_function("__log.held?.length === 1")
    choose(ed, "field", "ai_cost_usd")
    ed.wait_for_function("__log.asked.at(-1)[0].field === 'ai_cost_usd'")
    ed.wait_for_function("__log.updates.length > 0 && __log.configs.at(-1).queries[0].field === 'ai_cost_usd'")
    drawn = ed.evaluate("__log.configs.length")
    ed.evaluate("__log.held[0].release()")
    ed.wait_for_timeout(200)
    assert ed.evaluate("__log.configs.length") == drawn, "the older answer was dropped"
    assert ed.evaluate("__log.configs.at(-1).queries[0].field") == "ai_cost_usd"


def test_display_changes_redraw_without_asking_again(ed):
    opened(ed, {"id": "p1", "queries": [{**HOUR_COST, "id": "a"}]})
    wait_drawn(ed)
    asked = ed.evaluate("__log.asked.length")
    ed.get_by_label("Minimum").fill("0")
    ed.get_by_label("Maximum").fill("50")
    ed.get_by_label("Log scale").check()
    assert "above 0" in ed.locator(".pe-side [role=status]").inner_text()
    ed.get_by_label("Minimum").fill("1")
    ed.get_by_label("Position").select_option("bottom")
    ed.get_by_label("Decimals").select_option("3")
    ed.locator(".pe-checks .pe-seg", has_text="Max").click()
    ed.get_by_role("button", name="Add threshold").click()
    ed.get_by_label("Threshold 1 value").fill("100")
    ed.get_by_label("Threshold 1 label").fill("budget")
    ed.locator(".pe-seg", has_text="Two thirds").click()
    ed.get_by_label("Double height").check()
    ed.wait_for_function("__log.configs.at(-1).display.thresholds?.[0]?.label === 'budget'")
    assert ed.evaluate("__log.asked.length") == asked
    ed.get_by_role("button", name="Save", exact=True).click()
    saved = result(ed)["saved"]
    assert saved["display"] == {"y": {"min": 1, "max": 50, "log": True}, "legend": "bottom", "decimals": 3,
                                "legend_values": ["max"], "thresholds": [{"value": 100, "label": "budget"}]}
    assert saved["size"] == "l" and saved["tall"] is True


def test_a_query_error_shows_beside_that_query(ed):
    opened(ed, {"id": "p1", "queries": [{**HOUR_COST, "id": "a"}, {**HOUR_COST, "id": "b"}]})
    wait_drawn(ed)
    ed.evaluate("""() => { const real = queryPanels; window.queryPanels = async (c, o) => {
        const m = await real(c, o);
        for (const v of m.values()) v.results = v.results.map(r => r.id === 'b' ? {id: 'b', error: 'tokens: cannot be summed'} : r);
        return m; }; }""")
    choose(ed, "agg", "max", "b")
    ed.wait_for_selector(".pe-q[data-query=b] .pe-q-msg:has-text('cannot be summed')")
    assert card(ed, "a").locator(".pe-q-msg").inner_text() == ""
    assert [r["id"] for r in ed.evaluate("__log.updates.at(-1)")] == ["a"]


def test_cancel_and_escape_leave_nothing_and_return_focus(ed):
    config = {"id": "p1", "title": "Before", "custom": {"kept": 1}, "queries": [{**HOUR_COST, "id": "a"}]}
    for how in ("button", "escape"):
        opened(ed, config)
        assert ed.evaluate("document.getElementById('main').inert") is True
        ed.get_by_label("Title").fill("After")
        choose(ed, "field", "tokens")
        if how == "button":
            ed.get_by_role("button", name="Cancel").click()
        else:
            ed.get_by_label("Title").focus()
            ed.keyboard.press("Escape")
        assert ed.locator(".pe-overlay").count() == 0
        got = result(ed)
        assert got["cancelled"] == config and "saved" not in got
        assert ed.evaluate("__original") == config, "the object handed in is never changed"
        assert ed.evaluate("document.activeElement.id") == "opener"
        assert ed.evaluate("document.getElementById('main').inert") is False
        asked = ed.evaluate("__log.asked.length")
        ed.wait_for_timeout(320)
        assert ed.evaluate("__log.asked.length") == asked, "nothing is asked after closing"


def test_focus_stays_in_the_editor(ed):
    opened(ed, {"id": "p1", "queries": [{**HOUR_COST, "id": "a"}]})
    ed.get_by_role("button", name="Cancel").focus()
    ed.keyboard.press("Shift+Tab")
    assert ed.evaluate("!!document.activeElement.closest('.pe-overlay')")
    for _ in range(60):
        ed.keyboard.press("Tab")
        assert ed.evaluate("!!document.activeElement.closest('.pe-overlay')")


def test_a_field_gone_from_the_model_is_shown_and_keeps_the_panel(ed, tmp_path):
    gone = {**HOUR_COST, "id": "a", "field": "retired_cost", "where": {"state": ["archived"]}}
    config = {"id": "p7", "title": "Old panel", "size": "l", "queries": [gone, {**HOUR_COST, "id": "b"}]}
    opened(ed, config)
    wait_drawn(ed)
    field = card(ed).locator("select[data-slot=field]")
    assert field.input_value() == "retired_cost" and field.get_attribute("aria-invalid") == "true"
    assert "retired_cost (missing)" in field.inner_text()
    message = card(ed).locator(".pe-q-msg").inner_text()
    assert "retired_cost" in message and "no longer in the model" in message and "archived" in message
    assert [q["id"] for q in ed.evaluate("__log.asked.at(-1)")] == ["b"], "the missing query is not asked"
    shot(ed, "desktop-missing", tmp_path)
    ed.get_by_role("button", name="Save", exact=True).click()
    assert result(ed)["saved"]["queries"][0] == gone
    assert result(ed)["saved"]["size"] == "l"


def test_fields_that_cannot_be_read_lose_nothing_and_can_be_tried_again(ed):
    ed.evaluate("""() => { const real = queryFields; let first = true;
        window.queryFields = () => { if (first) { first = false; return Promise.reject(new Error('busy')); } return real(); }; }""")
    config = {"id": "p1", "title": "Kept", "queries": [{**HOUR_COST, "id": "a"}]}
    ed.evaluate(OPEN, config)
    ed.wait_for_selector(".pe-fields-msg:has-text('busy')")
    source = card(ed).locator("select[data-slot=source]")
    assert source.input_value() == "items" and source.is_disabled() and source.get_attribute("aria-invalid") is None
    ed.get_by_role("button", name="Try again").click()
    wait_drawn(ed)
    assert not source.is_disabled() and card(ed).locator("select[data-slot=field]").input_value() == "ai_cost_usd"
    assert ed.evaluate("!!document.activeElement.closest('.pe-overlay')"), "focus stays in the editor"
    ed.get_by_role("button", name="Save", exact=True).click()
    assert result(ed)["saved"]["queries"] == config["queries"]


def test_a_half_made_query_is_not_saved(ed):
    opened(ed, {"id": "p1"})
    choose(ed, "source", "items")
    choose(ed, "kind", "gap")
    ed.get_by_role("button", name="Save", exact=True).click()
    assert "saved" not in result(ed)
    assert "choose field" in ed.locator(".pe-save-msg").inner_text()
    assert ed.evaluate("document.activeElement.dataset.slot") == "field"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_at_phone_width_it_stacks_with_no_sideways_scroll(ed, scheme, tmp_path):
    ed.emulate_media(color_scheme=scheme)
    ed.set_viewport_size({"width": 390, "height": 844})
    many = {"id": "p1", "title": "A long title for a narrow screen", "form": "stacked",
            "display": {"thresholds": [{"value": 1, "label": "x"}]},
            "queries": [{**HOUR_COST, "id": "a", "where": {"state": ["ready", "merged"]}},
                        {**HOUR_COST, "id": "b", "field": "retired"}]}
    opened(ed, many)
    wait_drawn(ed)
    wide = ed.evaluate("""() => { const o = document.querySelector('.pe-body');
        const over = [...o.querySelectorAll('*')].filter(e => e.getClientRects().length
             && e.getBoundingClientRect().right > innerWidth + 0.5
             && !e.closest('.pe-live') && getComputedStyle(e).position !== 'absolute');
        return {scroll: o.scrollWidth, client: o.clientWidth, over: over.map(e => e.tagName + '.' + e.className)}; }""")
    assert wide["scroll"] <= wide["client"] and wide["over"] == []
    boxes = ed.evaluate("""['.pe-preview', '.pe-query-area', '.pe-side']
        .map(s => document.querySelector(s).getBoundingClientRect().top)""")
    assert boxes == sorted(boxes), "preview, then queries, then options"
    shot(ed, f"phone-{scheme}", tmp_path)
    ed.locator(".pe-body").evaluate("e => e.scrollTo(0, e.scrollHeight)")
    assert ed.evaluate("""Math.abs(document.querySelector('.pe-preview').getBoundingClientRect().top
        - document.querySelector('.pe-body').getBoundingClientRect().top) < 1"""), "the preview stays in sight"
    shot(ed, f"phone-{scheme}-options", tmp_path)
