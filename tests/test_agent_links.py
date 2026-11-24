"""Acceptance: every agent name links to its page (/agent/NAME): the Agents table's first cells (reached by Tab), an
item's lease attempts' block column, the Blocks panel's 'block' row, the goal panel's actor line, the valve panel's
taken items and the Actions' 'asked by', each an a (details.js agentA). Structure only.

    uv run --with playwright==1.63.0 python scripts/named_tests.py tests/test_agent_links.py"""

from __future__ import annotations

import pytest

from tests.test_agent_page import agents, serve


@pytest.fixture(scope="module")
def tf(tmp_path_factory):
    proc, url = serve(tmp_path_factory.mktemp("tf"), "ticket-factory")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


# each text node of a container that is exactly an agent's name, and whether it is inside an a to its page
UNLINKED = """([sel, names]) => [...document.querySelectorAll(sel)].flatMap((box) => {
  const out = [], walk = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  for (let t = walk.nextNode(); t; t = walk.nextNode()) {
    const n = t.nodeValue.trim();
    if (!names.includes(n)) continue;
    const a = t.parentElement.closest('a');
    if (!a || a.getAttribute('href') !== `/agent/${encodeURIComponent(n)}`) out.push(n);
  }
  return out;
})"""


def page(browser, url):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(url)
    return pg


def test_each_agents_row_names_it_with_a_link_reached_by_tab(browser, tf):
    names = list(agents(tf))
    pg = page(browser, f"{tf}/agents")
    pg.wait_for_selector("tr.click[data-row]")
    cells = pg.eval_on_selector_all("tr.click[data-row]", """rs => rs.map((r) =>
        [r.dataset.row, r.cells[0].querySelector('a')?.getAttribute('href') ?? null])""")
    assert sorted(n for n, _ in cells) == sorted(names)
    assert all(href == f"/agent/{n}" for n, href in cells if "/" not in n), cells
    assert pg.evaluate(UNLINKED, ["tr.click[data-row] td:first-child", names]) == []
    reached = set()
    for _ in range(400):                                       # Tab through the page: each row's link takes the focus
        pg.keyboard.press("Tab")
        reached.add(pg.evaluate("() => document.activeElement.closest('tr.click')?.dataset.row ?? null"))
        if reached >= set(names):
            break
    assert reached >= set(names), set(names) - reached
    assert not pg.errors, pg.errors
    pg.close()


def test_the_item_pages_lease_block_column_links_each_agent(browser, tf):
    pg = page(browser, f"{tf}/item/ticket%2FSCRUM-7")
    pg.wait_for_function("() => typeof leaseView === 'function'")
    hrefs = pg.evaluate("""() => {
      const l = { attempts: 2, max: 3, history: [{ fence: 1, block: 'close', run: 'aaaaaaaa1', taken: 1, ended: 2, how: 'ack' },
        { fence: 2, block: 'merge', run: 'bbbbbbbb2', taken: 3 }, { fence: 3, run: 'cccccccc3', taken: 4 }] };
      const t = leaseView(l, 'open').querySelector('table');
      const col = [...t.querySelectorAll('th')].findIndex((th) => th.textContent === 'block');
      return [...t.querySelectorAll('tr')].slice(1).map((r) => r.cells[col])
        .filter((c) => c.textContent).map((c) => c.querySelector('a')?.getAttribute('href') ?? null);
    }""")
    assert hrefs == ["/agent/merge", "/agent/close"], hrefs
    pg.close()


def test_the_blocks_panel_of_a_machine_block_links_its_agent(browser, tf):
    pg = page(browser, f"{tf}/diagram?view=blocks&open=*")
    pg.wait_for_function("() => S.graph?.nodes?.some((n) => n.id === 'blk:work')", timeout=60000)
    pg.evaluate("() => { openBlock(S.graph.nodes.find((n) => n.id === 'blk:work')); }")
    pg.wait_for_selector("#detail dl dt:text-is('block')")
    dd = pg.eval_on_selector("#detail dl dt:text-is('block') + dd", "d => [d.textContent, d.querySelector('a')?.getAttribute('href')]")
    assert dd[0].startswith("work (") and dd[1] == "/agent/work", dd
    assert not pg.errors, pg.errors
    pg.close()


def test_every_agent_name_in_those_containers_is_inside_a_link(browser, tf):
    """Each agent's name, wherever it stands in the Agents table, the lease attempts, the valve panel's leases line and
    an action's 'asked by' (waiting and answered), is inside an a to its page."""
    names = list(agents(tf))
    pg = page(browser, f"{tf}/agents")
    pg.wait_for_selector("tr.click[data-row]")
    assert pg.evaluate(UNLINKED, ["tr.click[data-row] td:first-child", names]) == []
    got = pg.evaluate("""(names) => {
      const box = document.createElement('div'); box.id = 'probe'; document.body.append(box);
      box.append(leaseView({ history: names.map((n, i) => ({ fence: i + 1, block: n, run: 'r' + i, taken: 1 })) }, 'open'));
      box.append(...countsLines({ leases: names.map((n) =>
        ({ block: n, kind: 'ticket', taken: 0, waiting: 0, at: [], set: { kind: 'ticket' } })) }));
      box.append(actionsAbout(names.flatMap((n) => ['ran', 'requested'].map((state) =>
        ({ id: `action/${state}-${n}`, state, block: n, by: n, gate: 'approve', time: 1, 'approved by': 'gate (auto)' })))));
      return box.querySelectorAll('table.leases tr, .leases-line, .claim').length;
    }""", names)
    assert got == 1 + 4 * len(names), got
    assert pg.evaluate(UNLINKED, ["#probe", names]) == []
    shown = pg.evaluate("([sel, names]) => names.filter((n) => document.querySelector(sel).textContent.includes(n))", ["#probe", names])
    assert shown == names                                       # each name is there, so each was checked
    assert not pg.errors, pg.errors
    pg.close()


def test_the_records_machine_scope_links_back_to_the_agent(browser, tf):
    pg = page(browser, f"{tf}/record?machine=work")
    pg.wait_for_selector("a:text-is('Show all')")
    assert pg.eval_on_selector_all("a[href='/agent/work']", "as => as.map((a) => a.parentElement.textContent)")[0].startswith("from work")
    assert not pg.errors, pg.errors
    pg.close()
