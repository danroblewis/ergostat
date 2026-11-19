"""Acceptance: the Items page groups its kinds by system. Each system folds away: a folded system keeps its
charts, and its lists of items are neither drawn nor asked for; the folding is remembered across a reload. The kinds' charts sit
side by side, three across at 1500 px and two at 900, each following its card's width.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_items_page.py -v
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "image-squeeze"
PORTS = range(8791, 8800)      # kept clear of a page the owner has open on 8790


def free_port() -> int:
    for port in PORTS:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    pytest.skip("no free port in 8791-8799")


def seed(d: Path, home: Path) -> None:
    """Items of three kinds in the lab and one in the benchmark, each moving."""
    code = f"""
import time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path({str(d)!r})))
t = time.time() - 3000
for i in range(1, 9):
    p.events.add("hypothesis.proposed", item=f"hypothesis/{{i}}", data={{"title": f"idea {{i}}"}}, at=t + i * 60)
    p.events.add("session.started", item=f"session/s{{i}}", data={{"role": "researcher"}}, at=t + i * 60 + 5)
    p.events.add("release.made", item=f"release/r{{i}}", data={{"commit": "abc"}}, at=t + i * 60 + 7)
    p.events.add("case.run", item=f"case/c{{i}}", data={{"name": f"case {{i}}"}}, at=t + i * 60 + 9)
taken = {{"block": "developer", "ttl": 2400, "max": 2, "back": "proposed", "tier": "ai"}}   # leases (SPEC §9.5)
p.events.add("ergostat.lease.taken", item="hypothesis/1", data={{**taken, "run": "run1aaaaaaaa", "fence": 1}})
for n in (1, 2):
    p.events.add("ergostat.lease.taken", item="hypothesis/2", data={{**taken, "run": f"run2{{n}}aaaaaaa", "fence": n}})
    p.events.add("ergostat.lease.expired", item="hypothesis/2", data={{"run": f"run2{{n}}aaaaaaa", "fence": n, "silent": 2500}})
"""
    subprocess.run([sys.executable, "-c", code], env={**os.environ, "ERGOSTAT_HOME": str(home)}, check=True,
                   capture_output=True)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp(EXAMPLE) / EXAMPLE
    shutil.copytree(ROOT / "examples" / EXAMPLE, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    home = d.parent / "home"
    seed(d, home)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def systems(pg) -> list[str]:
    return pg.locator("section.sys-group").evaluate_all("els => els.map((e) => e.dataset.system)")


def cards(pg, system: str) -> list[dict]:
    """Each kind's card in a system: where it sits, and how wide its chart is drawn (none: no chart)."""
    return pg.locator(f'section.sys-group[data-system="{system}"] .kind-flow').evaluate_all("""els => els.map((e) => {
        const r = e.getBoundingClientRect(), plot = e.querySelector(".uplot");
        return { top: Math.round(r.top), left: Math.round(r.left), width: r.width,
                 chart: plot ? plot.getBoundingClientRect().width : null };
    })""")


def test_kinds_are_grouped_by_system_and_charts_sit_three_across(browser, site):
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site}/items")
    pg.wait_for_selector('section.sys-group[data-system="lab"] .kind-flow .uplot')
    assert systems(pg) == ["lab", "benchmark", "ergostat"]
    head = pg.locator('section.sys-group[data-system="lab"] .sys-head').inner_text()
    assert "lab" in head and "24 items, 3 kinds" in head
    pg.wait_for_function("""() => document.querySelectorAll('section[data-system="lab"] .kind-flow .uplot').length >= 2""")
    lab = cards(pg, "lab")
    assert len(lab) == 3 and len({c["top"] for c in lab}) == 1, lab               # hypothesis, release, session: one row
    assert all(c["width"] > 300 for c in lab), lab
    for c in lab:
        if c["chart"] is not None:                                                 # each chart as wide as its card
            assert abs(c["chart"] - c["width"]) < 4, lab
    pg.set_viewport_size({"width": 900, "height": 1000})
    pg.wait_for_timeout(400)
    lab = cards(pg, "lab")
    assert len({c["top"] for c in lab}) == 2 and lab[0]["top"] == lab[1]["top"], lab   # two across, the third below
    for c in lab:
        if c["chart"] is not None:                                                 # the charts followed their cards
            assert abs(c["chart"] - c["width"]) < 4, lab
    assert not errors, errors
    pg.close()


def test_a_folded_system_keeps_its_charts_not_its_lists_and_stays_folded(browser, site):
    ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
    pg = ctx.new_page()
    asked: list[str] = []
    pg.on("request", lambda r: asked.append(r.url) if "/api/items" in r.url else None)
    pg.add_init_script("window.ERGOSTAT_POLL_SPEED = 10;")
    pg.goto(f"{site}/items")
    lab = 'section.sys-group[data-system="lab"]'
    pg.wait_for_selector(f"{lab} .kind-flow .uplot")
    assert pg.locator(f"{lab} table").count() >= 1
    button = pg.locator(f"{lab} .sys-head button")
    assert button.get_attribute("aria-expanded") == "true"
    button.click()
    pg.wait_for_selector(f'{lab} .sys-head button[aria-expanded="false"]')
    assert pg.locator(f"{lab} table").count() == 0                                # its lists go
    pg.wait_for_selector(f"{lab} .kind-flow .uplot")                               # its charts stay
    assert pg.locator('section.sys-group[data-system="benchmark"] .kind-flow').count() == 1    # the others stay
    asked.clear()
    pg.wait_for_timeout(1500)                                                      # a few refreshes, sped up
    lists = [u for u in asked if "/api/items?" in u]
    assert lists and all("hide=lab" in u for u in lists), lists                     # the lab's items not sent
    stored = pg.evaluate("Object.entries(localStorage).filter(([k]) => k.startsWith('ergostat.items.folded.'))")
    assert stored == [["ergostat.items.folded.image-squeeze", '["lab"]']], stored

    pg.reload()                                                                    # remembered
    pg.wait_for_selector('section.sys-group[data-system="benchmark"] .kind-flow')
    assert pg.locator(f"{lab} .sys-head button").get_attribute("aria-expanded") == "false"
    assert pg.locator(f"{lab} table").count() == 0 and pg.locator(f"{lab} .kind-flow").count() >= 1

    pg.locator(f"{lab} .sys-head button").click()                                  # and shown again
    pg.wait_for_selector(f"{lab} table")                                           # its lists come back
    assert pg.locator(f"{lab} .kind-flow .uplot").count() >= 1
    assert pg.evaluate("localStorage.getItem('ergostat.items.folded.image-squeeze')") is None
    ctx.close()


def test_a_chosen_kinds_folded_system_is_shown(browser, site):
    ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
    pg = ctx.new_page()
    pg.goto(f"{site}/items")
    pg.evaluate("localStorage.setItem('ergostat.items.folded.image-squeeze', JSON.stringify(['lab']))")
    pg.goto(f"{site}/items?kind=hypothesis")
    pg.reload()
    lab = 'section.sys-group[data-system="lab"]'
    pg.wait_for_selector(f"{lab} table")
    assert pg.locator(f"{lab} .sys-head button").get_attribute("aria-expanded") == "true"
    ctx.close()


def test_leases_are_shown_on_the_items_page_and_the_items(browser, site):
    """Leased by and expires in on the Items page, a dead letter said as one; an item's page shows its lease and each
    attempt (SPEC §9.5)."""
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site}/items?kind=hypothesis")
    pg.wait_for_selector('td[data-lease="held"]')
    heads = pg.locator('section.sys-group[data-system="lab"] table th').all_inner_texts()
    assert "leased by" in heads and "expires in" in heads, heads
    assert "developer" in pg.locator('td[data-lease="held"]').first.inner_text()
    assert "dead letter" in pg.locator('td[data-lease="dead"]').first.inner_text()
    pg.goto(f"{site}/item/hypothesis/2")
    pg.wait_for_selector(".lease")
    text = pg.locator(".lease").inner_text()
    assert "A dead letter" in text and "--redrive" in text and text.count("expired") >= 2, text
    pg.goto(f"{site}/item/hypothesis/1")
    pg.wait_for_selector(".lease")
    assert "held by developer" in pg.locator(".lease").inner_text()
    assert not errors, errors
    pg.close()


def test_a_stocks_and_a_flows_side_panel_list_their_items_and_link_to_exactly_that_set(browser, site):
    """What is going through the wires (item_sets.py): the stock ideas lists the hypotheses proposed now, the flow
    proposed those that arrived in the window; each links to the Items page filtered to that set, shown as a chip
    with the same count, and only that kind's items listed."""
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    for node, words in (("n.label === 'ideas' && n.kind === 'stock'", "items now"),
                        ("(n.flow || n.label) === 'proposed' && ['valve', 'disturbance'].includes(n.kind)", "went through")):
        pg.goto(f"{site}/diagram?view=dynamics&around=stock/ideas")
        pg.wait_for_function("() => S.graph && document.querySelectorAll('.node').length > 0", timeout=60000)
        pg.evaluate(f"() => openNode(S.graph.nodes.find((n) => {node}))")
        pg.wait_for_selector("#detail .item-set table.item-list")
        head = pg.locator("#detail .item-set p b").first.inner_text()
        assert words in head, head
        n = int(head.split("(")[1].split()[0]) if "(" in head else int(head.split()[0])   # items (a flow's moves first)
        assert n >= 5 and pg.locator("#detail .item-set table.item-list tr").count() - 1 == min(n, 10)
        assert all(h.startswith("/item/hypothesis%2F") for h in
                   pg.locator("#detail .item-set table.item-list a").evaluate_all("els => els.map((a) => a.getAttribute('href'))"))
        link = pg.locator("#detail .item-set a[href^='/items?']")
        href = link.get_attribute("href")
        assert "kind=hypothesis" in href and ("state=proposed" in href if "stock" in node else "moved=%3Eproposed" in href), href
        link.click()
        pg.wait_for_selector(".set-chip")
        chip = pg.locator(".set-chip").inner_text()
        assert chip.startswith("hypothesis") and str(n) in chip.split(), chip
        pg.wait_for_selector('section.sys-group[data-system="lab"] table tr td')   # the groups draw after the chip
        assert systems(pg) == ["lab"]
        rows = pg.locator('section.sys-group[data-system="lab"] table tr td:first-child').all_inner_texts()
        assert len(rows) == n and all(r.startswith("hypothesis/") for r in rows), rows
        pg.locator(".set-chip button").click()                                     # the chip goes: the whole list again
        pg.wait_for_function("() => !document.querySelector('.set-chip') && location.search === ''")
    assert not errors, errors
    pg.close()


# ---- the Graph and the Timeline (relations: SPEC §5a; relations.js), on the roadmap example's record

ROADMAP = "roadmap"
OBSERVE = """() => {
  window.__mo?.disconnect();
  window.__muts = [];
  window.__mo = new MutationObserver((rs) => { for (const r of rs) window.__muts.push({ target: r.target.nodeName, attr: r.attributeName }); });
  window.__mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
}"""


def seed_roadmap(d: Path, home: Path) -> None:
    """Three epics, each a fan-out of tickets: the first shipped, the second under way (a ticket leased, one in
    review, one ready, two waiting), the third planned; and a chain through a finished ticket (v1, unfinished, then v2
    finished, then v3), so collapsing the finished leaves one line, via 1 done."""
    code = f"""
import time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path({str(d)!r})))
ev = p.events
t = time.time() - 3000
fan = [("design", []), ("build-api", ["design"]), ("build-ui", ["design"]), ("docs", ["design"]),
       ("integrate", ["build-api", "build-ui"]), ("release", ["integrate", "docs"])]
def plan(n, at):
    ev.add("epic.planned", item=f"epic/e{{n}}", data={{"title": f"release {{n}}", **({{"after": f"epic/e{{n-1}}"}} if n > 1 else {{}})}}, at=at)
    for name, after in fan:
        ev.add("ticket.planned", item=f"ticket/e{{n}}-{{name}}", data={{"title": name, "parent": f"epic/e{{n}}",
               "blocked_by": [f"ticket/e{{n}}-{{a}}" for a in after]}}, at=at + 1)
def work(item, at, took=60, review=20, finish=True):
    ev.add("ticket.started", item=item, at=at)
    ev.add("ticket.submitted", item=item, at=at + took)
    if finish:
        ev.add("ticket.approved", item=item, at=at + took + review)
for n in (1, 2, 3):
    plan(n, t + (n - 1) * 400)
for i, (name, _) in enumerate(fan):
    work(f"ticket/e1-{{name}}", t + 100 + i * 100, took=60 + i * 5)
ev.add("epic.started", item="epic/e1", at=t + 100)
ev.add("epic.shipped", item="epic/e1", at=t + 800)
work("ticket/e2-design", t + 1000)
ev.add("epic.started", item="epic/e2", at=t + 1000)
ev.add("ticket.started", item="ticket/e2-build-api", at=time.time() - 30)
work("ticket/e2-build-ui", time.time() - 200, finish=False)
ev.add("ergostat.lease.taken", item="ticket/e2-docs", data={{"run": "r1aaaaaaaaaa", "block": "developer", "fence": 1, "ttl": 600,
       "max": 3, "back": "todo", "tier": "program", "attempt": 1}}, at=time.time() - 10)
ev.add("ticket.planned", item="ticket/v1", data={{"title": "first", "parent": "epic/e3"}}, at=t + 1500)
ev.add("ticket.planned", item="ticket/v2", data={{"title": "second", "parent": "epic/e3", "blocked_by": ["ticket/v1"]}}, at=t + 1500)
ev.add("ticket.planned", item="ticket/v3", data={{"title": "third", "parent": "epic/e3", "blocked_by": ["ticket/v2"]}}, at=t + 1500)
ev.add("ticket.started", item="ticket/v1", at=t + 1600)
work("ticket/v2", t + 1600)                                    # finished, though what it waits on is not: never enforced
"""
    subprocess.run([sys.executable, "-c", code], env={**os.environ, "ERGOSTAT_HOME": str(home)}, check=True,
                   capture_output=True)


@pytest.fixture(scope="module")
def roadmap(tmp_path_factory):
    d = tmp_path_factory.mktemp(ROADMAP) / ROADMAP
    shutil.copytree(ROOT / "examples" / ROADMAP, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    home = d.parent / "home"
    seed_roadmap(d, home)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def overlaps(boxes: list[dict]) -> list[tuple]:
    out = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a["x"] + 1 < b["x"] + b["w"] and b["x"] + 1 < a["x"] + a["w"] and a["y"] + 1 < b["y"] + b["h"] and b["y"] + 1 < a["y"] + a["h"]:
                out.append((a["id"], b["id"]))
    return out


def drawn(pg, sel: str) -> list[dict]:
    return pg.locator(sel).evaluate_all("""els => els.map((e) => { const r = e.getBoundingClientRect();
        return { id: e.dataset.id || e.textContent, x: r.x, y: r.y, w: r.width, h: r.height,
                 cls: e.getAttribute('class'), text: e.textContent }; })""")


def open_view(browser, roadmap, route: str, ready: str):
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    pg.add_init_script("window.ERGOSTAT_POLL_SPEED = 4;")
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{roadmap}/{route}")
    pg.wait_for_selector(ready, timeout=20000)
    pg.wait_for_timeout(800)
    return pg, errors


def test_the_graph_draws_the_frontier_with_the_finished_collapsed(browser, roadmap):
    pg, errors = open_view(browser, roadmap, "items?view=graph", ".rg-graph[data-drawn] .rg-node")
    nodes = drawn(pg, ".rg-graph .rg-node")
    ids = {n["id"] for n in nodes}
    assert not overlaps(nodes), overlaps(nodes)
    assert "ticket/e2-integrate" in ids and "ticket/e3-design" in ids and "epic/e2" in ids
    assert not any("ticket/e1-" in i for i in ids), ids                             # finished, and nothing waits on them
    assert not any("rg-done" in n["cls"] and "rg-hub" not in n["cls"] for n in nodes), nodes   # collapsed
    st = {n["id"]: n["cls"] for n in nodes}
    assert "rg-active" in st["ticket/e2-docs"] and "rg-queued" in st["ticket/e2-build-ui"]     # leased; waiting for review
    assert "rg-blocked" in st["ticket/e2-integrate"] and "rg-ready" in st["ticket/e3-design"]
    assert "rg-hub" in st["epic/e2"]                                                  # a parent, its children hang off it
    labels = pg.locator(".rg-graph .rg-elabel").evaluate_all("els => els.map((e) => e.textContent)")
    assert "via 1 done" in labels, labels                                             # v1 -> (v2, done) -> v3
    assert pg.locator(".rg-graph .rg-edge.rg-crit").count() >= 2                       # the critical path, drawn
    legend = pg.locator(".rg-legend").first.inner_text()
    assert "active" in legend and "waiting" in legend and "critical path" in legend, legend
    # everything: the finished drawn too, nothing collapsed
    pg.locator(".rg-check", has_text="Frontier").locator("input").uncheck()
    pg.locator(".rg-check", has_text="Collapse done").locator("input").uncheck()
    pg.wait_for_function("() => document.querySelectorAll('.rg-graph .rg-node.rg-done').length >= 6")
    pg.wait_for_timeout(500)
    every = drawn(pg, ".rg-graph .rg-node")
    assert len(every) > len(nodes) and any(n["id"] == "ticket/e1-design" for n in every)
    assert not overlaps(every), overlaps(every)
    assert "via 1 done" not in pg.locator(".rg-graph .rg-elabel").evaluate_all("els => els.map((e) => e.textContent)")
    assert "frontier=0" in pg.url and "collapse=0" in pg.url
    # by kind: each kind a frame; and the search narrows it
    pg.locator(".rg-viewbar button", has_text="By kind").click()
    pg.wait_for_function("() => document.querySelectorAll('.rg-graph .rg-frame').length === 2")
    pg.fill("input[type=search]", "e2-")
    pg.wait_for_function("() => [...document.querySelectorAll('.rg-graph .rg-node')].every((n) => n.dataset.id.includes('e2-'))")
    pg.locator(".rg-graph .rg-node[data-id='ticket/e2-integrate']").click()           # a click opens the item
    pg.wait_for_url("**/item/ticket%2Fe2-integrate")
    pg.wait_for_selector("table.relations")
    rel = pg.locator("table.relations").inner_text()
    assert "blocked by" in rel and "ticket/e2-build-api" in rel and "blocks" in rel and "ticket/e2-release" in rel, rel
    assert "Waiting on" in pg.locator(".page").inner_text()
    assert not errors, errors
    pg.close()


def test_the_timeline_draws_what_happened_and_what_is_projected(browser, roadmap):
    pg, errors = open_view(browser, roadmap, "items?view=timeline", ".rg-timeline[data-drawn] .rg-row")
    rows = drawn(pg, ".rg-timeline .rg-row .rg-label")
    assert len(rows) >= 12                                                            # the unfinished, and what they wait on
    assert not overlaps(rows), overlaps(rows)
    assert len({round(r["y"]) for r in rows}) == len(rows)                            # one row each
    assert pg.locator(".rg-timeline .rg-seg").count() > 20                             # what happened, state by state
    proj = pg.locator(".rg-timeline .rg-proj").count()
    assert proj >= 5, proj                                                            # and what is projected
    assert pg.locator(".rg-timeline .rg-now line").count() == 1
    assert pg.locator(".rg-timeline .rg-edge").count() >= 5                            # what waits on what
    # each projected bar starts after what it waits on is projected to end
    order = pg.evaluate("""() => { const at = {};
      for (const r of document.querySelectorAll('.rg-timeline .rg-row')) {
        const ps = [...r.querySelectorAll('.rg-proj')].map((p) => [+p.getAttribute('x'), +p.getAttribute('x') + +p.getAttribute('width')]);
        if (ps.length) at[r.dataset.id] = [Math.min(...ps.map((p) => p[0])), Math.max(...ps.map((p) => p[1]))]; }
      return at; }""")
    assert order["ticket/e2-release"][0] >= order["ticket/e2-integrate"][1] - 1, order
    assert order["ticket/e2-integrate"][0] >= order["ticket/e2-build-api"][1] - 1, order
    # zoomed in, then fitted again
    ticks = lambda: pg.locator(".rg-timeline .rg-tick").evaluate_all("els => els.map((e) => e.textContent)")   # noqa: E731
    before = ticks()
    pg.locator(".rg-timeline .rg-tools button", has_text="+").click()
    pg.locator(".rg-timeline .rg-tools button", has_text="+").click()
    assert ticks() != before
    pg.locator(".rg-check", has_text="Collapse done").locator("input").check()     # the finished rows go
    pg.wait_for_function(f"() => document.querySelectorAll('.rg-timeline .rg-row').length < {len(rows)}")
    assert not pg.locator(".rg-timeline .rg-row.rg-done").count()
    pg.locator(".rg-check", has_text="Frontier").locator("input").uncheck()        # every item in the window
    pg.locator(".rg-check", has_text="Collapse done").locator("input").uncheck()
    pg.wait_for_function(f"() => document.querySelectorAll('.rg-timeline .rg-row').length > {len(rows)}")
    assert not errors, errors
    pg.close()


@pytest.mark.parametrize("view", ["graph", "timeline"])
def test_the_graph_and_the_timeline_left_open_change_nothing(browser, roadmap, view):
    pg, errors = open_view(browser, roadmap, f"items?view={view}", f".rg-{view} [data-drawn], .rg-{view}[data-drawn]")
    asked: list[str] = []
    pg.on("requestfinished", lambda r: asked.append(r.url) if "/api/items-graph" in r.url else None)
    pg.wait_for_timeout(1500)
    pg.evaluate("() => { for (const s of document.querySelectorAll('.rg-svg')) s.__was = true; }")
    pg.evaluate(OBSERVE)
    start = len(asked)
    for _ in range(100):
        if len(asked) - start >= 3:
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)
    ms = pg.evaluate("window.__muts")
    kept = pg.evaluate("() => [...document.querySelectorAll('.rg-svg')].every((s) => s.__was)")
    print(f"\n{view}, {len(asked) - start} refreshes with nothing new: {len(ms)} mutations")
    pg.close()
    assert len(asked) - start >= 3
    assert ms == [], ms[:10]
    assert kept and not errors, errors
