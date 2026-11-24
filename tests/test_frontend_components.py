"""Acceptance (preact-components): the shared components every moved page is built from (app/components/,
docs/frontend.md "Components", the design in docs/frontend-components.md), each drawn in a real browser by a small page
module served in place of the Agents stub, as a page gap's would be: Page, Section, Note and Facts; Table (groups,
total, clickable rows, hold); Async (loading, slow, error and Retry, empty); Chip and StateChip; Ref; Dom; openPanel;
and the hooks (useQueryState, useKeys, useWindow, usePoll).

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_frontend_components.py -v
"""

from __future__ import annotations

import shutil

import pytest

from tests.test_page_polling import ROOT, serve

try:                           # collected without it too, each test skipped, so a run of this file alone is rc 0, not 5
    from playwright import sync_api as playwright
except ImportError:
    playwright = None
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

EXAMPLE = "image-squeeze"
C = "/static/app/components"
IMPORTS = f"""import {{ html, useState, useApi, usePoll }} from "/static/app/core.js";
import {{ Page }} from "{C}/page.js"; import {{ Section }} from "{C}/section.js"; import {{ Note }} from "{C}/note.js";
import {{ Facts }} from "{C}/facts.js"; import {{ Table }} from "{C}/table.js"; import {{ Async }} from "{C}/async.js";
import {{ Chip, StateChip }} from "{C}/chip.js"; import {{ Ref }} from "{C}/ref.js"; import {{ Dom }} from "{C}/dom.js";
import {{ openPanel, closePanel }} from "{C}/side-panel.js";
import {{ useQueryState, useKeys, useWindow }} from "{C}/hooks.js";
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp(EXAMPLE) / EXAMPLE
    shutil.copytree(ROOT / "examples" / EXAMPLE, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    yield from serve(d, d.parent / "home")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                        # no Chromium here
            pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


def moved(browser, site, body, routes=(), at="/agents"):
    """The page module ``body`` (after the imports) served as the Agents page, its ``.g`` drawn."""
    pg = browser.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.route("**/static/app/pages/agents/index.js*",
             lambda r: r.fulfill(status=200, content_type="text/javascript", body=IMPORTS + body))
    for pattern, handler in routes:
        pg.route(pattern, handler)
    pg.goto(site + at)
    pg.wait_for_function("() => document.querySelector('#main .g')", timeout=30000)
    return pg


def answer(body, status=200):
    return lambda r: r.fulfill(status=status, content_type="application/json", body=body)


TEXT = """export function page() {
  return html`<${Page} title="Gallery" aside=" · 2 off" toolbar=${html`<input type="search" aria-label="find" />`}>
    <div class="g"><${Section} title="Daemons" level=${3} aside="2" actions=${html`<button>act</button>`}>
      <${Note}>a note<//><${Note} tone="bad" action=${{ label: "clear", onClick: () => { window.__cleared = 1; } }}>bad<//>
      <${Note} tone="warn" action=${{ label: "see", href: "/record" }}>warn<//><${Note} tone="muted">quiet<//>
      <${Facts} pairs=${[["kind", "ticket"], ["owner", null], ["empty", ""], ["zero", 0]]} />
    <//></div><//>`;
}"""


def test_page_section_note_and_facts_say_what_they_are_given(browser, site):
    """Page: the h1, its muted aside and the filters row; Section: the heading at its level, aside and actions;
    Note: each tone's class and its action (a button or a link); Facts: null and "" left out, 0 kept."""
    pg = moved(browser, site, TEXT)
    assert pg.inner_text("#main .page > h1") == "Gallery · 2 off"
    assert pg.locator("#main .page > .filters input[type=search]").count() == 1
    assert pg.inner_text("#main section.sec > h3.sec-head .sec-aside") == "2"
    assert pg.locator("#main section.sec > h3 .sec-actions button").count() == 1
    notes = pg.evaluate("() => [...document.querySelectorAll('#main .g p')].map((p) => [p.className, p.dataset.tone || ''])")
    assert notes == [["note", ""], ["note", "bad"], ["note", "warn"], ["muted", ""]]
    pg.click("#main p[data-tone=bad] button")
    assert pg.evaluate("window.__cleared") == 1
    assert pg.get_attribute("#main p[data-tone=warn] a", "href") == "/record"
    assert pg.locator("#main dl.facts dt").all_inner_texts() == ["kind", "zero"]
    assert pg.locator("#main dl.facts dd").all_inner_texts() == ["ticket", "0"]
    assert pg.errors == []
    pg.close()


TABLE = """const cols = [{ key: "name", head: "agent" }, { key: "runs", head: "runs", num: true, title: "how many" },
                  { key: "x", head: "twice", cell: (r) => r.runs * 2 }];
export function page() {
  const [rows, setRows] = useState([{ name: "a", runs: 1 }, { name: "b", runs: 2 }]);
  window.__setRows = setRows;
  const [picked, setPicked] = useState("");
  return html`<div class="page g">
    <div id="grouped"><${Table} caption="Agents, by rung" columns=${cols} rowHref=${(r) => `/items?q=${r.name}`}
      groups=${[{ key: "ai", head: "ai · 1", rows: rows.slice(0, 1) }, { key: "rule", head: "rule · 1", rows: rows.slice(1) }]}
      total=${{ name: "total", runs: rows.reduce((s, r) => s + r.runs, 0) }} /></div>
    <div id="held"><${Table} caption="Held" hold columns=${cols} rows=${rows} onRow=${(r) => setPicked(r.name)} /></div>
    <p class="picked">${picked}</p>
    <div id="none"><${Table} caption="None" columns=${cols} rows=${[]} empty="Nothing yet." /></div>
    <p id="away">away</p></div>`;
}"""


def test_table_draws_groups_a_total_and_rows_that_open_and_holds_still_while_the_reader_is_in_it(browser, site):
    """The caption for screen readers, th scope=col with num and title; a tbody per group under its colgroup heading;
    the total row; keyed rows (data-row). onRow's row picked by a click; with hold, a change waits while the pointer is
    in the table ("1 update waiting", the old rows kept) and is drawn once it leaves; empty said in place of a table;
    a rowHref row's click goes to its page."""
    pg = moved(browser, site, TABLE)
    g = "#grouped table"
    assert pg.inner_text(f"{g} caption.sr-only") == "Agents, by rung"
    assert pg.evaluate(f"() => [...document.querySelectorAll('{g} thead th')].map((t) => [t.scope, t.className, t.title])") == \
        [["col", "", ""], ["col", "num", "how many"], ["col", "", ""]]
    assert pg.locator(f"{g} tbody.group").count() == 2
    assert pg.inner_text(f"{g} tbody.group >> nth=1 >> th[scope=colgroup]") == "rule · 1"
    assert pg.locator(f"{g} tbody.group tr[data-row]").evaluate_all("(rs) => rs.map((r) => r.dataset.row)") == ["a", "b"]
    assert pg.locator(f"{g} tr[data-row=b] td").all_inner_texts() == ["b", "2", "4"]
    assert pg.locator(f"{g} tbody.total tr[data-total] td").all_inner_texts() == ["total", "3", ""]
    assert pg.inner_text("#none") == "Nothing yet." and pg.locator("#none table").count() == 0
    pg.click("#held tr[data-row=b] td >> nth=0")
    assert pg.inner_text(".picked") == "b"
    pg.hover("#held tr[data-row=a]")                       # the reader in the held table: a change waits
    pg.evaluate("window.__setRows([{ name: 'a', runs: 5 }, { name: 'b', runs: 2 }])")
    pg.wait_for_function("() => document.querySelector('#held .waiting').textContent === '1 update waiting'", timeout=5000)
    assert pg.locator("#held tr[data-row=a] td").all_inner_texts()[1] == "1"
    assert pg.locator("#grouped tr[data-row=a] td").all_inner_texts()[1] == "5"    # (a table not held: drawn at once)
    pg.hover("#away")
    pg.wait_for_function("() => document.querySelector('#held tr[data-row=a] td.num').textContent === '5'", timeout=5000)
    assert pg.inner_text("#held .waiting") == ""
    pg.click(f"{g} tr[data-row=b] td >> nth=1")
    pg.wait_for_function("() => location.pathname === '/items' && location.search.includes('q=b')", timeout=10000)
    assert pg.errors == []
    pg.close()


ASYNC = """export function page() {
  const slow = useApi("slowthing"), bad = useApi("broken"), none = useApi("nothing"), some = useApi("something");
  window.__reloadBad = bad.reload;
  const each = (d) => html`<span class="got">${d.join(",")}</span>`;
  return html`<div class="page g">
    <div id="slow"><${Async} of=${slow} what="the goals">${each}<//></div>
    <div id="bad"><${Async} of=${bad} what="the things">${each}<//></div>
    <div id="none"><${Async} of=${none} empty=${{ text: "Nothing matches", action: { label: "clear", href: "/record" } }}>${each}<//></div>
    <div id="some"><${Async} of=${some} empty="Nothing yet.">${each}<//></div></div>`;
}"""


def test_async_says_loading_then_still_waiting_could_not_be_read_with_retry_and_empty(browser, site):
    """Before the first answer "Loading…"; past 1.5 s with nothing back "Still waiting for the goals (N s)", its
    seconds counted up; a failed call "The things could not be read: …" with a Retry that asks again and draws the
    answer; an empty answer its empty words and action; data drawn by the children."""
    held, broken = [], {"status": 500}
    pg = moved(browser, site, ASYNC, routes=[
        ("**/api/slowthing*", lambda r: held.append(r)),
        ("**/api/broken*", lambda r: answer("[7]", broken["status"])(r)),
        ("**/api/nothing*", answer("[]")), ("**/api/something*", answer("[1,2]"))])
    assert pg.inner_text("#slow") == "Loading…"
    pg.wait_for_function("() => /^Still waiting for the goals \\(\\d+ s\\)$/.test(document.querySelector('#slow').textContent)",
                         timeout=5000)
    first = pg.inner_text("#slow")
    pg.wait_for_function(f"() => document.querySelector('#slow').textContent !== {first!r}", timeout=5000)   # counted up
    pg.wait_for_function("() => document.querySelector('#bad [data-tone=bad]')", timeout=5000)
    assert pg.inner_text("#bad p").startswith("The things could not be read: broken: 500")
    broken["status"] = 200
    pg.click("#bad button:text('Retry')")
    pg.wait_for_function("() => document.querySelector('#bad .got')?.textContent === '7'", timeout=5000)
    assert pg.locator("#bad [data-tone=bad]").count() == 0
    broken["status"] = 500                                # failing again: said over the last answer, which stays
    pg.evaluate("window.__reloadBad()")
    pg.wait_for_function("() => document.querySelector('#bad [data-tone=bad]')", timeout=5000)
    assert pg.inner_text("#bad .got") == "7"
    assert pg.inner_text("#none p") == "Nothing matches clear" and pg.get_attribute("#none p a", "href") == "/record"
    assert pg.inner_text("#some .got") == "1,2"
    pg.unroute_all(behavior="ignoreErrors")
    pg.close()


CHIPS = """export function page() {
  const [on, setOn] = useState(false);
  return html`<div class="page g">
    <${Chip} label="open" n=${3} href="/items/ticket?state=open" title="the open ones" />
    <${Chip} label="mine" on=${on} onClick=${() => setOn(!on)} />
    <${Chip} label="set" n=${2} onRemove=${() => { window.__removed = 1; }} />
    ${["off", "stale", "open", "holding", "unknown", "done"].map((w) => html`<${StateChip} word=${w} />`)}
    <${StateChip} word="" /></div>`;
}"""


def test_chips_count_link_toggle_and_remove_and_a_state_word_takes_its_tone(browser, site):
    """A chip: its count, a link with its title, a pressed button that toggles, an × that removes (named for a screen
    reader); a state word's tone from the one table (off bad, stale and open warn, holding and unknown quiet), another
    word none, and no word "–"."""
    pg = moved(browser, site, CHIPS)
    link = pg.locator("#main .chip a")
    assert link.get_attribute("href") == "/items/ticket?state=open" and link.get_attribute("title") == "the open ones"
    assert pg.inner_text("#main .chip a .chip-n") == "3"
    btn = pg.locator("#main .chip button[aria-pressed]")
    assert btn.get_attribute("aria-pressed") == "false"
    btn.click()
    pg.wait_for_function("() => document.querySelector('#main .chip.on button[aria-pressed=true]')", timeout=5000)
    pg.click("#main .chip-x[aria-label='Remove set']")
    assert pg.evaluate("window.__removed") == 1
    tones = pg.evaluate("() => [...document.querySelectorAll('#main .chip')].slice(3).map((c) => [c.textContent, c.dataset.tone || ''])")
    assert tones == [["off", "bad"], ["stale", "warn"], ["open", "warn"], ["holding", "quiet"], ["unknown", "quiet"], ["done", ""]]
    assert pg.locator("#main .g > span.muted").inner_text() == "–"
    assert pg.errors == []
    pg.close()


REFS = """export function page() {
  return html`<div class="page g">
    <${Ref} to="item" id="ticket/1" /> <${Ref} to="item" id="ticket/2" remote="peer" /> <${Ref} to="item" id="../x" remote="peer" />
    <${Ref} to="kind" id="ticket">tickets<//> <${Ref} to="agent" id="triager" panel=${(n) => { window.__opened = n; }} />
    <${Ref} to="goal" id="queue" /> <${Ref} to="part" id="sys.queue" /></div>`;
}"""


def test_a_ref_links_each_kind_of_thing_and_a_plain_click_with_panel_opens_it_there(browser, site):
    """Each ``to`` its address (a remote item's on its remote, an id that cannot be opened there its text alone); a
    plain click with ``panel`` calls the opener and stays, a link without it is an ordinary link."""
    pg = moved(browser, site, REFS)
    hrefs = pg.evaluate("() => [...document.querySelectorAll('#main .g a')].map((a) => [a.textContent, a.getAttribute('href')])")
    assert hrefs == [["ticket/1", "/item/ticket%2F1"], ["ticket/2", "/item/ticket%2F2?remote=peer"], ["tickets", "/items/ticket"],
                     ["triager", "/agent/triager"], ["queue", "/goals?select=queue"],
                     ["sys.queue", "/diagram?view=dynamics&around=sys%2Fqueue"]]
    assert pg.locator("#main .g > span").inner_text() == "../x"
    assert pg.get_attribute("#main a.agent-link", "href") == "/agent/triager"
    pg.click("#main a.agent-link")
    assert pg.evaluate("window.__opened") == "triager" and pg.evaluate("location.pathname") == "/agents"
    pg.click("#main a:text('tickets')")
    pg.wait_for_function("() => location.pathname === '/items/ticket'", timeout=10000)
    assert pg.errors == []
    pg.close()


DOM = """const made = document.createElement("b"); made.className = "made"; made.textContent = "old node";
export function page() {
  return html`<div class="page g"><${Dom} node=${made} class="bridge" />
    <${Dom} tag="span" class="drawn" deps=${[]} make=${(el) => { el.textContent = "drawn"; window.__made = (window.__made || 0) + 1;
      return () => { window.__cleaned = true; }; }} /></div>`;
}"""


def test_dom_shows_an_old_node_and_a_drawing_and_cleans_up_when_the_page_is_left(browser, site):
    """``node`` an element made the old way, shown in the component's box; ``make`` draws into its own box once and
    its cleanup is called when the page is left."""
    pg = moved(browser, site, DOM)
    assert pg.inner_text("#main div.bridge > b.made") == "old node"
    assert pg.inner_text("#main span.drawn") == "drawn" and pg.evaluate("window.__made") == 1
    assert pg.evaluate("window.__cleaned") is None
    pg.locator("#nav a", has_text="Goals").click()
    pg.wait_for_function("() => window.__cleaned === true", timeout=10000)
    assert pg.errors == []
    pg.close()


PANEL = """function Body({ name }) {
  const a = useApi("held");
  return html`<p class="body">${name}: ${a.loading ? "asking" : "answered"}</p>`;
}
export function page() {
  const old = () => { const p = document.createElement("p"); p.className = "legacy"; p.textContent = "old body"; return p; };
  return html`<div class="page g">
    <button id="new" onClick=${() => openPanel({ kind: "goal", title: "queue", body: html`<${Body} name="queue" />` })}>new</button>
    <button id="old" onClick=${() => openPanel({ kind: "agent", title: "triager", body: old() })}>old</button></div>`;
}"""


def test_open_panel_shows_a_live_body_in_the_one_panel_and_unmounts_it_when_closed(browser, site):
    """openPanel: the kind and title in the old frame's head (its ×), the body a live component whose call is on its
    way; Escape closes the panel and its call is aborted; an old element is shown through Dom; another panel opened
    in its place unmounts the one before."""
    held = []
    pg = moved(browser, site, PANEL, routes=[("**/api/held*", lambda r: held.append(r))])
    pg.click("#new")
    pg.wait_for_function("() => document.querySelector('#detail:not([hidden]) .panel-body .body')", timeout=5000)
    assert pg.text_content("#detail .head .kind") == "goal" and pg.text_content("#detail h2") == "queue"
    assert pg.locator("#detail .head button.close").count() == 1
    assert pg.inner_text("#detail .body") == "queue: asking"     # (its call held: the abort below shows it was made)
    pg.keyboard.press("Escape")
    pg.wait_for_function("() => document.querySelector('#detail').hidden", timeout=5000)
    pg.wait_for_function("() => window.ERGOSTAT_CALLS.some((c) => c.path === 'held' && c.status === 'aborted')", timeout=5000)
    pg.click("#new")
    pg.wait_for_function("() => document.querySelector('#detail .body')", timeout=5000)
    pg.click("#old")
    pg.wait_for_function("() => document.querySelector('#detail .panel-body p.legacy')?.textContent === 'old body'", timeout=5000)
    pg.wait_for_function("() => window.ERGOSTAT_CALLS.filter((c) => c.path === 'held' && c.status === 'aborted').length === 2",
                         timeout=5000)
    assert pg.text_content("#detail .kind") == "agent"
    pg.unroute_all(behavior="ignoreErrors")
    pg.close()


HOOKS = """function Inner() {
  useKeys({ k: () => { window.__keys.push("inner"); } });
  return html`<p class="inner">inner</p>`;
}
export function page() {
  window.__keys = window.__keys || [];
  const [match, setMatch] = useQueryState("match", "");
  const [runs, setRuns] = useQueryState("runs", false, { parse: (v) => v === "1" });
  const [inner, setInner] = useState(true);
  const w = useWindow();
  useKeys({ k: () => { window.__keys.push("outer"); }, "mod+Enter": () => { window.__keys.push("run"); } });
  usePoll(() => { window.__polls = (window.__polls || 0) + 1; return { wait: 50 }; }, 60000);
  return html`<div class="page g">
    <p class="match">${match}</p><p class="runs">${String(runs)}</p><p class="win">${w.since} ${w.words} ${String(w.live)}</p>
    <button id="set" onClick=${() => { setMatch("ticket.opened"); setRuns(true); }}>set</button>
    <button id="clear" onClick=${() => { setMatch(""); setRuns(false); }}>clear</button>
    <button id="drop" onClick=${() => setInner(false)}>drop</button>
    <input id="field" aria-label="field" />${inner ? html`<${Inner} />` : null}</div>`;
}"""


def test_the_hooks_keep_a_query_key_take_keys_innermost_first_say_the_window_and_poll_at_the_answers_wait(browser, site):
    """useQueryState: read from the address, written in place (true as "1", the default dropped); useKeys: the handler
    mounted last wins, a plain key typed in a field is the field's, a mod+ key is not, and an unmounted handler lets the
    next take it; useWindow: the store's window in words, live; usePoll: the answer's {wait} sets the next wait."""
    pg = moved(browser, site, HOOKS, at="/agents?match=goal.off&window=6h")
    assert pg.inner_text("#main .match") == "goal.off" and pg.inner_text("#main .runs") == "false"
    pg.wait_for_function("() => document.querySelector('#main .win').textContent === '6h Last 6 hours true'", timeout=10000)
    pg.click("#set")
    pg.wait_for_function("() => document.querySelector('#main .match').textContent === 'ticket.opened'", timeout=5000)
    q = pg.evaluate("() => Object.fromEntries(new URLSearchParams(location.search))")
    assert q == {"match": "ticket.opened", "runs": "1", "window": "6h"}, q
    assert pg.inner_text("#main .runs") == "true"
    pg.click("#clear")
    pg.wait_for_function("() => !location.search.includes('match=') && !location.search.includes('runs=')", timeout=5000)
    pg.locator("body").press("k")
    pg.locator("#field").press("k")
    pg.locator("#field").press("Control+Enter")
    assert pg.evaluate("window.__keys") == ["inner", "run"]
    pg.click("#drop")
    pg.wait_for_function("() => !document.querySelector('#main .inner')", timeout=5000)
    pg.locator("body").press("k")
    assert pg.evaluate("window.__keys") == ["inner", "run", "outer"]
    pg.wait_for_function("() => window.__polls >= 5", timeout=5000)   # (60 s apart but for its {wait})
    assert pg.errors == []
    pg.close()
