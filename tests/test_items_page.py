"""Acceptance: the Items page groups its kinds by system. Each system folds away: a folded system keeps its
charts, and its lists of items are neither drawn nor asked for; the folding is remembered across a reload. The kinds' charts sit
side by side, three across at 1500 px and two at 900, each following its card's width.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_items_page.py -v
"""

from __future__ import annotations

import os
import re
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
EXAMPLE = "image-squeeze"
HOME: dict = {}                       # the site's ERGOSTAT_HOME, for a test that adds to its record while it runs




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
for i, last in enumerate(("checked", "checked", "accepted"), 1):     # the model's changes: two waiting, one written
    c = f"ergostat.model-change/c{{i}}"
    p.events.add("ergostat.model-change.made", item=c, data={{"title": f"change {{i}}", "kind": "parameter"}}, at=t + 600 + i)
    p.events.add("ergostat.model-change.checked", item=c, at=t + 601 + i)
    if last == "accepted":
        p.events.add("ergostat.model-change.accepted", item=c, data={{"fit_gained": 0.02}}, at=t + 700)
from ergostat.spec.engine import read_sensor                          # the stocks' readings, as the engine would take them
for st in ("pending-changes", "accepted-changes"):
    s = p.model.spec.stocks[st].sensors["main"]
    p.measurements.add(s.series, read_sensor(p.model.spec, s, p.events)[0])
"""
    subprocess.run([sys.executable, "-c", code], env={**os.environ, "ERGOSTAT_HOME": str(home)}, check=True,
                   capture_output=True)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp(EXAMPLE) / EXAMPLE
    shutil.copytree(ROOT / "examples" / EXAMPLE, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    home = HOME["home"] = d.parent / "home"
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
    assert systems(pg) == ["lab", "benchmark", "modelling", "ergostat"]       # ergostat's own kinds where they are counted
    head = pg.locator('section.sys-group[data-system="lab"] .sys-head').inner_text()
    assert "lab" in head and "24 items, 6 kinds" in head                      # and the claims, messages and decisions it counts
    pg.wait_for_function("""() => document.querySelectorAll('section[data-system="lab"] .kind-flow .uplot').length >= 2""")
    lab = cards(pg, "lab")
    assert len(lab) == 6 and len({c["top"] for c in lab[:3]}) == 1 and lab[3]["top"] > lab[0]["top"], lab   # three a row
    assert all(c["width"] > 300 for c in lab), lab
    for c in lab:
        if c["chart"] is not None:                                                 # each chart as wide as its card
            assert abs(c["chart"] - c["width"]) < 4, lab
    pg.set_viewport_size({"width": 900, "height": 1000})
    pg.wait_for_timeout(400)
    lab = cards(pg, "lab")
    assert len({c["top"] for c in lab}) == 3 and lab[0]["top"] == lab[1]["top"] < lab[2]["top"], lab   # two across
    for c in lab:
        if c["chart"] is not None:                                                 # the charts followed their cards
            assert abs(c["chart"] - c["width"]) < 4, lab
    assert not errors, errors
    pg.close()


NAV = ["/diagram", "/loops", "/agents", "/items", "/record", "/model", "/check", "/guide"]


@pytest.fixture(scope="module")
def nav_site(tmp_path_factory):
    """A site of its own: opening every page records ergostat's first offered changes, which `site`'s tests count."""
    d = tmp_path_factory.mktemp("nav") / EXAMPLE
    shutil.copytree(ROOT / "examples" / EXAMPLE, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
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


@pytest.mark.parametrize("size", [(390, 844), (720, 450)], ids=["phone", "zoom-200"])
def test_the_navigation_shows_every_page_at_phone_width_and_at_200_percent_zoom(browser, nav_site, size):
    """Below 760 px the tabs wrap onto rows of their own: all eight inside the viewport on every page, nothing
    scrolled sideways, and the current page still underlined."""
    site = nav_site
    w, h = size
    pg = browser.new_page(viewport={"width": w, "height": h})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    for route in NAV:
        pg.goto(f"{site}{route}")
        pg.wait_for_selector(f'#nav a.on[href="{route}"]')
        pg.wait_for_timeout(300)
        seen = pg.evaluate("""() => ({
            links: [...document.querySelectorAll("#nav a")].map((a) => {
                const r = a.getBoundingClientRect();
                return { href: a.getAttribute("href"), left: r.left, right: r.right, top: r.top, bottom: r.bottom };
            }),
            scroll: document.scrollingElement.scrollWidth, client: document.scrollingElement.clientWidth,
            rows: new Set([...document.querySelectorAll("#nav a")].map((a) => Math.round(a.getBoundingClientRect().top))).size,
            under: getComputedStyle(document.querySelector("#nav a.on")).borderBottomColor,
            plain: getComputedStyle(document.querySelector("#nav a:not(.on)")).borderBottomColor,
        })""")
        assert [a["href"] for a in seen["links"]] == NAV, (route, seen)
        out = [a for a in seen["links"] if a["left"] < 0 or a["top"] < 0 or a["right"] > w or a["bottom"] > h]
        assert not out, (route, size, out)
        assert seen["scroll"] == seen["client"], (route, size, seen)
        assert seen["rows"] <= 2, (route, size, seen)                          # two rows at most
        assert seen["under"] != seen["plain"], (route, seen)                    # the current page underlined
    assert not errors, errors
    pg.close()


def test_items_list_sorts_by_a_column(browser, site):
    """A column's header sorts the list by its field (up, down, off), kept in the address (sort=FIELD, -FIELD)."""
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    rows = lambda: pg.locator('section[data-system="lab"] table tr td:first-child b').all_inner_texts()  # noqa: E731
    pg.goto(f"{site}/items?kind=hypothesis&sort=-title")
    pg.wait_for_selector('section[data-system="lab"] table button.sort')
    assert rows()[:3] == ["hypothesis/8", "hypothesis/7", "hypothesis/6"]
    head = pg.locator('section[data-system="lab"] table button.sort', has_text="title")
    assert head.get_attribute("aria-sort") == "descending"
    head.click()                                                                   # down, then off
    pg.wait_for_function("() => !location.search.includes('sort=')")
    pg.wait_for_function("""() => [...document.querySelectorAll('section[data-system="lab"] table button.sort')]
                            .every((b) => b.getAttribute('aria-sort') === 'none')""")      # drawn again, unsorted
    pg.locator('section[data-system="lab"] table button.sort', has_text="title").click()
    pg.wait_for_function("() => location.search.includes('sort=title')")
    pg.wait_for_function("""() => document.querySelector('section[data-system="lab"] table tr td:first-child b')
                            ?.textContent === 'hypothesis/1'""")
    assert rows()[:3] == ["hypothesis/1", "hypothesis/2", "hypothesis/3"]
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


def add_events(*events) -> None:
    """Events added to the running site's record from outside, as a block's run would."""
    code = f"""
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path({str(HOME["home"].parent / EXAMPLE)!r})))
for t, item, data in {events!r}:
    p.events.add(t, item=item, data=data)
"""
    subprocess.run([sys.executable, "-c", code], env={**os.environ, "ERGOSTAT_HOME": str(HOME["home"])}, check=True,
                   capture_output=True)


def open_part(pg, site, node: str, around: str) -> None:
    pg.goto(f"{site}/diagram?view=dynamics&around={around}")
    pg.wait_for_function("() => S.graph && document.querySelectorAll('.node').length > 0", timeout=60000)
    pg.evaluate(f"() => openNode(S.graph.nodes.find((n) => {node}))")


def test_the_model_changes_are_found_by_heading_search_and_panel(browser, site):
    """The owner reaches the model's changes from the Items page by their plain heading under modelling, by searching
    for "change", and from the accepted-changes stock's panel, whose first line names the kind it counts and links to
    exactly the items it counts (as many as its reading); a flow's panel says what it measures."""
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site}/items")
    card = pg.locator('section.sys-group[data-system="modelling"] .kind-flow .kname').first
    card.wait_for()
    assert card.inner_text().startswith("Model changes") and "ergostat.model-change" in card.inner_text()
    head = pg.locator('section.sys-group[data-system="modelling"] h3.kind-head')
    head.wait_for()
    assert head.inner_text().startswith("Model changes")
    pg.fill('input[aria-label="Search"]', "change")
    pg.wait_for_function("() => location.search.includes('q=change')")
    pg.wait_for_function("""() => [...document.querySelectorAll('section.sys-group table tr td:first-child')]
        .map((td) => td.textContent).filter((t) => t.startsWith('ergostat.model-change/')).length === 3""")
    for stock, state in (("accepted-changes", "accepted"), ("pending-changes", "checked")):
        open_part(pg, site, f"n.label === '{stock}' && n.kind === 'stock'", f"stock/{stock}")
        line = pg.locator("#detail .counts-line")
        line.wait_for()
        assert line.inner_text().startswith(f"Counts items of kind ergostat.model-change in state {state}"), line.inner_text()
        assert pg.locator("#detail > *").evaluate_all("els => els.findIndex((e) => e.classList.contains('counts-line'))") <= 2
        value = int(float(pg.evaluate(f"() => api('part/stock/{stock}').then((d) => d.now.value)")))
        line.locator("a").click()
        pg.wait_for_selector(".set-chip")
        assert f"kind=ergostat.model-change&state={state}" in pg.url
        pg.wait_for_selector('section.sys-group[data-system="modelling"] table tr td')
        rows = pg.locator('section.sys-group table tr td:first-child').all_inner_texts()
        assert len(rows) == value and all(r.startswith("ergostat.model-change/") for r in rows), (rows, value)
    for flow, says in (("changes-accepted", "Items of kind ergostat.model-change entering accepted"),
                       ("model-mended", "Items of kind ergostat.model-change entering accepted, summing their fit_gained"),
                       ("model-drift", "The change of model-error that its other flows do not account for")):
        open_part(pg, site, f"(n.flow || n.label) === '{flow}' && ['valve', 'disturbance'].includes(n.kind)", f"flow/{flow}")
        pg.wait_for_selector("#detail .counts-line")
        assert pg.locator("#detail .counts-line").inner_text().startswith(says)
    assert not errors, errors
    pg.close()


def test_a_valves_leased_items_are_listed_live(browser, site):
    """A valve moved by a block that takes items: its panel names the kind, how many are leased now and to whom, and
    links to exactly those items; the list follows leases taken and given back without a reload."""
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    open_part(pg, site, "(n.flow || n.label) === 'started' && ['valve', 'disturbance'].includes(n.kind)", "flow/started")
    line = pg.locator("#detail .leases-line")
    line.wait_for()
    assert "developer" in line.inner_text() and "hypothesis" in line.inner_text() and "1 leased now" in line.inner_text()
    line.locator("a").click()
    pg.wait_for_selector('td[data-lease="held"]')
    leased = lambda: pg.locator('section.sys-group table tr td:first-child').all_inner_texts()   # noqa: E731
    assert leased() == ["hypothesis/1"]
    assert "developer" in pg.locator('td[data-lease="held"]').inner_text()
    pg.evaluate("() => { window.__same = true; }")                     # no reload: the page's own state survives
    add_events(("ergostat.lease.taken", "hypothesis/3", {"run": "run3aaaaaaaa", "fence": 1, "block": "developer", "ttl": 2400,
                                                          "max": 2, "back": "proposed", "tier": "ai"}))
    pg.wait_for_function("""() => [...document.querySelectorAll('section.sys-group table tr td:first-child')]
        .some((td) => td.textContent === 'hypothesis/3')""", timeout=20000)
    add_events(("ergostat.lease.ended", "hypothesis/3", {"run": "run3aaaaaaaa", "fence": 1, "how": "nack", "count": False}))
    pg.wait_for_function("""() => ![...document.querySelectorAll('section.sys-group table tr td:first-child')]
        .some((td) => td.textContent === 'hypothesis/3')""", timeout=20000)
    assert leased() == ["hypothesis/1"] and pg.evaluate("() => window.__same")
    assert not errors, errors
    pg.close()


def add_record(*events) -> None:
    """Events with their source and time, (type, item, source, data, at), added to the running site's record."""
    code = f"""
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path({str(HOME["home"].parent / EXAMPLE)!r})))
for t, item, source, data, at in {events!r}:
    p.events.add(t, item=item, source=source, data=data, at=at)
"""
    subprocess.run([sys.executable, "-c", code], env={**os.environ, "ERGOSTAT_HOME": str(HOME["home"])}, check=True,
                   capture_output=True)


def record_rows(pg) -> list[dict]:
    pg.wait_for_selector("main .page table tr td")
    return pg.locator("main .page table tr:has(td)").evaluate_all("""trs => trs.map((tr) => {
        const td = [...tr.children].map((c) => c.textContent.trim());
        return { type: td[1], item: td[2], source: td[3], data: td[4] }; })""")


def test_a_crossing_opens_the_record_narrowed_to_its_goal_and_time_and_the_filter_stays_in_the_address(browser, site):
    """A crossing of a goal in its evidence panel links to the Record of that goal (it, its controller's and valves'
    agents, its valves) from the crossing to the next one, and nothing else; the filter box matches an event's item
    and source as well as its type; the filter and the window stay in the address, so a reload keeps them."""
    t0 = float(int(time.time()) - 900)
    add_record(("loop.off", "ideas-ready", None, {"value": 1, "error": 2, "mark": "mk-off"}, t0),
               ("controller.decided", "ideas-ready", None, {"decision": "propose", "mark": "mk-inside"}, t0 + 100),
               ("hypothesis.proposed", "hypothesis/99", None, {"title": "x", "mark": "mk-other-item"}, t0 + 150),
               ("loop.on", "ideas-ready", None, {"value": 4, "mark": "mk-on"}, t0 + 300),
               ("controller.decided", "ideas-ready", None, {"decision": "rest", "mark": "mk-after"}, t0 + 400),
               ("repair.fixed", "repair/1", "fixer", {"mark": "mk-fixer-source"}, t0 + 500))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site}/diagram")
    pg.wait_for_function("() => typeof openLoop === 'function' && S.status", timeout=60000)
    link = pg.locator(f'#detail table.crossings a[href*="from={int(t0)}&"]')
    for _ in range(40):                                  # the page's snapshot may be older than the events just added
        pg.evaluate("() => openLoop('ideas-ready')")
        try:
            link.wait_for(timeout=1000)
            break
        except playwright.Error:
            pass
    link.click()
    pg.wait_for_function("() => location.pathname === '/record' && location.search.includes('about=ideas-ready')")
    assert f"from={int(t0)}" in pg.url and f"to={int(t0) + 300}" in pg.url, pg.url
    lp = pg.evaluate("() => api('loops/ideas-ready')")
    mine = {"ideas-ready", *(pt["name"] for pt in lp["parts"] if pt["kind"] != "sensor"),
            *(pt["agent"]["name"] for pt in lp["parts"] if pt["kind"] != "sensor" and pt.get("agent"))}
    for _ in range(2):                                   # as clicked, then reloaded
        rows = record_rows(pg)
        marks = {m for r in rows for m in ("off", "inside", "on", "other-item", "after", "fixer-source") if f"mk-{m}" in r["data"]}
        assert marks == {"off", "inside", "on"}, rows
        assert all(r["item"] in mine or r["source"] in mine for r in rows), (rows, mine)
        pg.reload()
        pg.wait_for_function("() => location.search.includes('about=ideas-ready')")
    pg.goto(f"{site}/record")
    pg.fill('input[aria-label="Event type, item or source"]', "fixer")
    pg.press('input[aria-label="Event type, item or source"]', "Enter")
    pg.wait_for_function("() => location.search.includes('match=fixer')")
    for _ in range(2):
        # the unfiltered Record holds mk-fixer-source too: wait for the filtered rows, not only for the text
        pg.wait_for_function("""() => { const rs = [...document.querySelectorAll('main .page table tr:has(td)')]
            .map((tr) => [...tr.children].map((c) => c.textContent.trim()));
            return rs.length && rs.some((r) => r[4].includes('mk-fixer-source'))
                && rs.every((r) => r[2] === 'fixer' || r[3] === 'fixer'); }""")
        rows = record_rows(pg)
        assert rows and all(r["source"] == "fixer" or r["item"] == "fixer" for r in rows), rows
        pg.reload()
        pg.wait_for_function("() => location.search.includes('match=fixer')")
        assert pg.input_value('input[aria-label="Event type, item or source"]') == "fixer"
    assert not errors, errors
    pg.close()


STRIP = """() => {
  const t = document.querySelector('.track');
  if (!t) return null;
  const c = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const rgb = (css) => { c.clearRect(0, 0, 1, 1); c.fillStyle = css; c.fillRect(0, 0, 1, 1); return [...c.getImageData(0, 0, 1, 1).data]; };
  const lum = ([r, g, b]) => [r, g, b].map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
    .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
  const bg = (el) => { for (; el; el = el.parentElement) { const x = rgb(getComputedStyle(el).backgroundColor);
    if (x[3] === 255) return x; } return [255, 255, 255, 255]; };
  const ratio = (el) => { const a = lum(rgb(getComputedStyle(el).color)), b = lum(bg(el));
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); };
  const top = [...t.children];
  return { path: top.filter((e) => !e.classList.contains('alt')).map((e) => e.classList.contains('arrow') ? '→' : e.textContent),
           alt: [...t.querySelectorAll('.alt .stbox')].map((e) => e.textContent),
           final: [...t.querySelectorAll('.stbox.final')].map((e) => e.textContent.trim()).sort(),
           double: [...t.querySelectorAll('.stbox.final')].every((e) => getComputedStyle(e).borderTopStyle === 'double'),
           worst: Math.min(...[...t.querySelectorAll('.stbox'), t.querySelector('.alt')].filter(Boolean).map(ratio)) };
}"""


def test_the_lifecycle_strip_draws_the_path_taken_and_sets_the_other_endings_apart(browser, site):
    """A done session's strip is 'open → done', ending at its present state; its other endings (failed, lost) sit apart
    with no arrow element between 'done' and them, each ending double-bordered, and every state label is at least
    4.5:1 against its background in light and dark. An open session draws only 'open', its other states apart."""
    add_events(("session.started", "session/strip", {"role": "researcher"}), ("session.ran", "session/strip", {}))
    errors: list[str] = []
    for theme in ("light", "dark"):
        pg = browser.new_page(viewport={"width": 1400, "height": 900}, color_scheme=theme)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{site}/item/session/strip")
        pg.wait_for_function("() => document.querySelector('.track .stbox.on')?.textContent === 'done'", timeout=20000)
        got = pg.evaluate(STRIP)
        assert got["path"] == ["open", "→", "done"], got
        assert got["alt"] == ["failed", "lost"], got
        assert not pg.locator(".track .alt .arrow").count()                  # nothing points from 'done' to another ending
        assert got["final"] == ["done", "failed", "lost"] and got["double"], got
        assert got["worst"] >= 4.5, (theme, got)
        pg.goto(f"{site}/item/session/s1")
        pg.wait_for_function("() => document.querySelector('.track .stbox.on')?.textContent === 'open'", timeout=20000)
        got = pg.evaluate(STRIP)
        assert got["path"] == ["open"] and got["alt"] == ["done", "failed", "lost"] and got["worst"] >= 4.5, (theme, got)
        assert not errors, errors
        pg.close()


# ---- the Graph and the Timeline (relations: SPEC §5a; relations.js), on the roadmap example's record

ROADMAP = "roadmap"
OBSERVE = """() => {
  window.__mo?.disconnect();
  window.__muts = [];
  window.__mo = new MutationObserver((rs) => {
    for (const r of rs) window.__muts.push({ target: r.target.nodeName, attr: r.attributeName }); });
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
    after = {{"after": f"epic/e{{n-1}}"}} if n > 1 else {{}}
    ev.add("epic.planned", item=f"epic/e{{n}}", data={{"title": f"release {{n}}", **after}}, at=at)
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
            across = a["x"] + 1 < b["x"] + b["w"] and b["x"] + 1 < a["x"] + a["w"]
            if across and a["y"] + 1 < b["y"] + b["h"] and b["y"] + 1 < a["y"] + a["h"]:
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


def test_the_graphs_status_counts_filter_it(browser, roadmap):
    """Each status's count in the legend is a filter: a click shows only that status, again shows them all."""
    pg, errors = open_view(browser, roadmap, "items?view=graph&frontier=0&collapse=0", ".rg-graph[data-drawn] .rg-node")
    keys = pg.locator(".rg-legend button.rg-key")
    assert keys.count() >= 2 and "ready" not in pg.locator(".rg-legend").inner_text().split()   # unblocked, not ready
    key = keys.filter(has_text="blocked").first if keys.filter(has_text="unblocked").count() == 0 else \
        keys.filter(has_text="unblocked").first
    st = (key.get_attribute("class") or "").split("rg-")[-1].split()[0]
    n = int(key.inner_text().split()[0])
    key.click()
    pg.wait_for_function(f"() => location.search.includes('status={st}')")
    pg.wait_for_function(f"""() => document.querySelectorAll('.rg-graph .rg-node:not(.rg-hub)').length > 0 &&
        [...document.querySelectorAll('.rg-graph .rg-node:not(.rg-hub)')].every((e) => e.classList.contains('rg-{st}'))""")
    assert pg.locator(f".rg-graph .rg-node.rg-{st}:not(.rg-hub)").count() <= n
    pg.locator(".rg-legend button.rg-key.on").click()
    pg.wait_for_function("() => !location.search.includes('status=')")
    assert not errors, errors
    pg.close()


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
    assert "rg-blocked" in st["ticket/e2-integrate"] and "rg-unblocked" in st["ticket/e3-design"]
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


RG_MODEL = """([d, o]) => { const m = rgModel(d, o);
  return { nodes: m.nodes.map((n) => n.id), edges: m.edges.filter((e) => e.cls === 'dep' || e.cls === 'via').map((e) => [e.from, e.to]),
           capped: m.capped, lost: m.lost }; }"""


def test_the_graph_draws_every_dependency_of_the_unfinished_work(browser, roadmap):
    """The page's own rgModel on an answer of the factory's shape (tests/test_graph_parts.py): every unfinished gap
    and every line into one drawn, no review; past the bound (a chained record, one group bigger than the bound, an
    epic over more than the bound), exactly what the unit tests' rule draws, and every line left out counted."""
    from ergostat.web import graph_parts
    from tests.test_graph_parts import drawn as rule
    from tests.test_graph_parts import epic_answer, factory_answer, fan_answer, unreported
    pg, errors = open_view(browser, roadmap, "items?view=graph", ".rg-graph[data-drawn] .rg-node")
    ans = graph_parts.mark(factory_answer())
    by = {x["id"]: x for x in ans["items"]}
    into = {(e["from"], e["to"]) for e in ans["edges"] if e["kind"] == "precedence" and by[e["to"]]["status"] != "done"}
    unfinished = {a for a, x in by.items() if x["kind"] == "gap" and x["status"] != "done"}
    o = {"frontier": True, "collapse": False, "group": "parent", "q": "", "status": None}
    got = pg.evaluate(RG_MODEL, [ans, o])
    assert not got["capped"] and got["lost"] == 0, got["capped"]
    assert unfinished <= set(got["nodes"]) and not any(a.startswith("review/") for a in got["nodes"])
    assert {tuple(e) for e in got["edges"]} == into and len(into) == 340
    got = pg.evaluate(RG_MODEL, [ans, {**o, "collapse": True}])                  # the finished collapsed: theirs go
    assert set(got["nodes"]) == unfinished
    assert {tuple(e) for e in got["edges"]} == {(a, b) for a, b in into if a in unfinished}
    for big in (factory_answer(n_open=1200, seed=11), fan_answer(), epic_answer()):   # past the bound
        big = graph_parts.mark(big)
        got = pg.evaluate(RG_MODEL, [big, o])
        scope, keep, lost = rule(big)                                        # the rule, as the unit tests hold it
        assert got["capped"] == len(scope) > 600 and set(got["nodes"]) == keep and got["lost"] == lost
        assert unreported(big, scope, keep, got["lost"]) == 0                   # each line left out, counted
        assert not any(a.startswith("gap/p") for a in keep)                     # never paused work before active
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
    assert not pg.locator(".rg-timeline .rg-row.rg-done").count()                 # the finished collapsed, by default
    pg.locator(".rg-check", has_text="Collapse done").locator("input").uncheck()   # the finished rows come back
    pg.wait_for_function(f"() => document.querySelectorAll('.rg-timeline .rg-row').length > {len(rows)}")
    kept = pg.locator(".rg-timeline .rg-row").count()
    pg.locator(".rg-check", has_text="Frontier").locator("input").uncheck()        # every item in the window
    pg.wait_for_function(f"() => document.querySelectorAll('.rg-timeline .rg-row').length > {kept}")
    assert not errors, errors
    pg.close()


def test_the_timeline_levels_lanes_per_block(browser, roadmap):
    """The projected bars are levelled (numbers/eta.py): by lanes, each block that takes items a row a lane, no more
    lanes than its capacity, one run at a time in each; by item, each open item's p50 tick and p90 whisker."""
    pg, errors = open_view(browser, roadmap, "items?view=timeline&rows=lanes", ".rg-timeline[data-drawn] .rg-lane .rg-lanebar")
    lanes = pg.evaluate("""() => [...document.querySelectorAll('.rg-timeline .rg-lane')].map((r) => ({
      block: r.dataset.block, lane: +r.dataset.lane,
      bars: [...r.querySelectorAll('.rg-lanebar')].map((b) => [+b.getAttribute('x'),
                                                               +b.getAttribute('x') + +b.getAttribute('width')]) }))""")
    per = {}
    for x in lanes:
        per.setdefault(x["block"], set()).add(x["lane"])
        bars = sorted(x["bars"])
        assert all(a[1] <= b[0] + 0.5 for a, b in zip(bars, bars[1:], strict=False)), x       # one run at a time
    assert per.get("developer") and max(per["developer"]) < 2 and max(per.get("reviewer", {0})) < 1, per   # pool 2, pool 1
    assert pg.locator(".rg-key.rg-eta").count() >= 1                                   # when the last is done, p50 and p90
    pg.locator(".rg-viewbar button", has_text="By item").click()
    pg.wait_for_selector(".rg-timeline .rg-row .rg-whisker", timeout=20000)
    assert pg.locator(".rg-timeline .rg-p50").count() >= 5
    assert not errors, errors
    pg.close()


def shown_clock(said: str, now: float) -> float:
    """A clock time the legend says ("04:02", or "Nov 23 04:02" on another day) as seconds since the epoch."""
    import datetime as dt
    *day, hm = said.split()
    today = dt.datetime.fromtimestamp(now)
    d = dt.datetime.strptime(f"{' '.join(day)} {today.year}", "%b %d %Y").date() if day else today.date()
    t = dt.datetime.combine(d, dt.datetime.strptime(hm, "%H:%M").time())
    return t.timestamp()


def test_the_finish_is_a_clock_time_no_earlier_than_the_critical_paths_end(browser, roadmap):
    """The legend says when the last open item is done in one sentence, on first paint ("being worked out" until the
    estimates are): a clock time expected and one 'at worst', the expected no earlier than now plus the critical
    path's remaining duration (the answer's ``end``), the worst no earlier than the expected."""
    import re
    answers: list[dict] = []
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    pg.add_init_script("window.ERGOSTAT_POLL_SPEED = 4;")
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("response", lambda r: answers.append(r) if "/api/items-graph" in r.url else None)
    pg.goto(f"{roadmap}/items?view=graph")
    pg.wait_for_selector(".rg-graph[data-drawn] .rg-node", timeout=20000)
    first = pg.locator(".rg-legend .rg-eta").all_inner_texts()                   # on first paint, one sentence
    assert len(first) == 1 and ("being worked out" in first[0] or "at worst" in first[0]), first
    assert "done in about" not in pg.locator(".rg-legend").first.inner_text()       # no duration beside it
    pg.wait_for_function("() => document.querySelector('.rg-legend .rg-eta')?.textContent.includes('at worst')", timeout=30000)
    said = pg.locator(".rg-legend .rg-eta").first.inner_text()
    m = re.fullmatch(r"last (\w+) \((\S+)\) expected ((?:\w{3} \d+ )?\d\d:\d\d), by ((?:\w{3} \d+ )?\d\d:\d\d) at worst \(9 in 10\)", said)
    assert m, said
    d = next(a.json() for a in reversed(answers) if a.ok and (a.json().get("eta") or {}).get("kinds"))
    expected, worst = shown_clock(m[3], d["now"]), shown_clock(m[4], d["now"])
    assert d["critical"] and d["end"] > d["now"], d["end"] - d["now"]
    assert expected >= d["end"], (said, d["end"] - d["now"])                       # not before the critical path's end
    assert worst >= expected, said
    # a simulation that ends before the critical path does: the sentence still says no earlier than its end
    said, now, end = pg.evaluate("""() => { const now = Math.floor(Date.now() / 1000), end = now + 3600;
      const e = { p50: now + 60, p90: now + 120, visits: {} };
      const d = { now, end, critical: ['epic/e100'], eta_pending: false, eta: { runs: 50, kinds: { epic: e } },
                  items: [{ id: 'epic/e100', kind: 'epic', status: 'active', eta: e }] };
      return [rgFinish(d).textContent, now, end]; }""")
    m = re.fullmatch(r"last epic \(e100\) expected ((?:\w{3} \d+ )?\d\d:\d\d), by ((?:\w{3} \d+ )?\d\d:\d\d) at worst \(9 in 10\)", said)
    assert m and shown_clock(m[1], now) >= end and shown_clock(m[2], now) >= end, said
    # an estimate not yet worked out (a what-if never asked): the answer says so, and so does the sentence
    import json
    with urllib.request.urlopen(f"{roadmap}/api/items-graph?whatif=block.developer.pool:7", timeout=10) as r:
        fresh = json.load(r)
    assert fresh["eta"] is None and fresh["eta_pending"] is True, fresh.get("eta_pending")
    said = pg.evaluate("(d) => rgFinish(d).textContent", fresh)
    assert said == "the last item's finish: being worked out", said
    assert not errors, errors
    pg.close()


def test_the_timeline_opens_at_now(browser, roadmap):
    """A short window: the Timeline opens with its now line in view, at the first unfinished row."""
    pg = browser.new_page(viewport={"width": 1200, "height": 420})
    pg.add_init_script("window.ERGOSTAT_POLL_SPEED = 4;")
    pg.goto(f"{roadmap}/items?view=timeline")
    pg.wait_for_selector(".rg-timeline[data-drawn] .rg-now line", state="attached", timeout=20000)
    pg.wait_for_timeout(500)
    at = pg.evaluate("""() => { const box = (e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
      return { now: box(document.querySelector('.rg-timeline .rg-now line')),
               row: box(document.querySelector('.rg-timeline .rg-row:not(.rg-done)')), w: innerWidth, h: innerHeight,
               y: scrollY }; }""")
    (x, t, _, b), (_, rt, _, rb) = at["now"], at["row"]
    assert 0 <= x <= at["w"] and t < at["h"] and b > 0, at                     # the now line, inside the viewport
    assert 0 <= rt and rb <= at["h"], at                                          # and the first unfinished row
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


def test_a_snapshot_draws_the_graph_and_timeline(browser, tmp_path):
    """A snapshot (``ergostat snapshot``) of a model with relations in two systems, opened from its file: the Graph
    and the Timeline of each system drawn from the answers it holds, keyed as the page's ``snapKey`` asks."""
    from ergostat.web.snapshot import build
    from tests.test_graph_cli_web import related_project
    (tmp_path / "m").mkdir()
    f = tmp_path / "snapshot.html"
    f.write_text(build(related_project(tmp_path / "m")))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f.as_uri() + "#/items?view=graph")
    for system, ids in (("planning", {"epic/e1", "epic/e2", "goal/g"}), ("delivery", {"ticket/a", "ticket/b", "epic/e1"})):
        sel = f'section.sys-group[data-system="{system}"] .rg-graph[data-drawn] .rg-node'
        pg.wait_for_selector(sel, timeout=20000)
        assert ids <= {n["id"] for n in drawn(pg, sel)}, (system, drawn(pg, sel))
    assert "not in a snapshot" not in pg.locator(".page").inner_text()
    pg.locator(".rg-viewbar button", has_text="Timeline").first.click()
    for system in ("planning", "delivery"):
        pg.wait_for_selector(f'section.sys-group[data-system="{system}"] .rg-timeline[data-drawn] .rg-row', timeout=20000)
    rows = {r["id"] for r in drawn(pg, '.rg-timeline .rg-row')}
    assert {"ticket/a", "ticket/b", "goal/g"} <= rows, rows
    assert pg.locator(".rg-timeline .rg-seg").count() >= 4                         # what happened, state by state
    assert "not in a snapshot" not in pg.locator(".page").inner_text()
    assert not errors, errors
    pg.close()


SNAP_IDS = """() => [...document.querySelectorAll('.page table td:first-child')].map((t) => t.textContent.trim())
  .filter((t) => t.startsWith('ticket/'))"""


def snapshot_page(browser, tmp_path):
    from ergostat.web.snapshot import build
    from tests.test_snapshot_sets import sets_project
    (tmp_path / "m").mkdir(exist_ok=True)
    f = tmp_path / "snapshot.html"
    f.write_text(build(sets_project(tmp_path / "m")))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f.as_uri() + "#/diagram?view=dynamics")
    pg.wait_for_function("() => S.graph && document.querySelectorAll('.node').length > 0", timeout=60000)
    return pg, errors


def test_a_snapshot_lists_a_parts_items_and_opens_its_set(browser, tmp_path):
    """From the file (snapshot_sets.py): the stock's panel (where area is flags or billing: two values) and the flow's
    list their items, and each one's Items page link shows those very items; nothing says "not in this snapshot"."""
    pg, errors = snapshot_page(browser, tmp_path)
    for node, ids in (("n.label === 'awaiting' && n.kind === 'stock'", ["ticket/2", "ticket/4"]),
                      ("(n.flow || n.label) === 'completed' && n.kind !== 'stock'", ["ticket/1", "ticket/3"])):
        pg.goto(pg.url.split("#")[0] + "#/diagram?view=dynamics")
        pg.wait_for_function("() => S.graph && document.querySelectorAll('.node').length > 0", timeout=60000)
        pg.evaluate(f"() => openNode(S.graph.nodes.find((n) => {node}))")
        pg.wait_for_selector("#detail .item-set table.item-list")
        listed = pg.locator("#detail .item-set table.item-list a").all_inner_texts()
        assert sorted(listed) == ids, (node, listed)
        assert "not in this snapshot" not in pg.locator("#detail").inner_text()
        pg.locator("#detail .item-set a[href^='#/items?']").first.click()
        pg.wait_for_selector(".set-chip", timeout=20000)
        pg.wait_for_function(f"() => ({SNAP_IDS})().length >= {len(ids)}", timeout=20000)
        assert sorted(pg.evaluate(SNAP_IDS)) == ids
        assert "not in this snapshot" not in pg.locator(".page").inner_text()
    assert not errors, errors
    pg.close()


def test_a_set_left_out_of_a_snapshot_says_so(browser, tmp_path, monkeypatch):
    """A set past the maximum is not held: its panel says so, as before, and nothing breaks."""
    from ergostat.web import snapshot_sets
    monkeypatch.setattr(snapshot_sets, "MOST", 0)
    pg, errors = snapshot_page(browser, tmp_path)
    pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.label === 'awaiting' && n.kind === 'stock'))")
    pg.wait_for_function("() => /not in this snapshot/.test(document.querySelector('#detail .item-set')?.textContent || '')",
                         timeout=20000)
    assert not errors, errors
    pg.close()


def test_a_snapshot_lets_a_kind_and_its_state_be_chosen(browser, tmp_path):
    """The same snapshot, opened from its file with a kind chosen: its list, one of its states, and its Graph and
    Timeline (a kind without relations too), each from what the snapshot holds; a set chosen is not held, and says so."""
    from ergostat.web.snapshot import build
    from tests.test_graph_cli_web import related_project
    (tmp_path / "m").mkdir()
    f = tmp_path / "snapshot.html"
    f.write_text(build(related_project(tmp_path / "m")))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    listed = lambda: {t.strip() for t in pg.locator("table.items tr.click td:first-child").all_inner_texts()}   # noqa: E731
    said = lambda: pg.locator(".page").inner_text()                                                         # noqa: E731
    pg.goto(f.as_uri() + "#/items?kind=ticket")
    pg.wait_for_function("() => document.querySelectorAll('table.items tr.click').length >= 2", timeout=20000)
    assert listed() == {"ticket/a", "ticket/b"}, listed()
    assert "epic/e1" not in listed() and "not in this snapshot" not in said()
    pg.locator('.kind-flow:has(.kname.on) a.stbox', has_text="doing").first.click()      # the chart's state: its items
    pg.wait_for_function("() => document.querySelectorAll('table.items tr.click').length === 1", timeout=20000)
    assert listed() == {"ticket/a"}, listed()
    assert "not in this snapshot" not in said()
    for view, sel in (("graph", ".rg-graph[data-drawn] .rg-node"), ("timeline", ".rg-timeline[data-drawn] .rg-row")):
        pg.goto(f.as_uri() + f"#/items?kind=ticket&view={view}")
        pg.wait_for_selector(sel, timeout=20000)
        assert {"ticket/a", "ticket/b"} <= {n["id"] for n in drawn(pg, sel)}, (view, drawn(pg, sel))
        assert "not in this snapshot" not in said() and "not in a snapshot" not in said()
    pg.goto(f.as_uri() + "#/items?kind=note&view=graph")                          # a kind without relations
    pg.wait_for_selector(".rg-graph[data-drawn] .rg-node", timeout=20000)
    assert "note/n" in {n["id"] for n in drawn(pg, ".rg-graph[data-drawn] .rg-node")}
    assert "not in this snapshot" not in said() and "not in a snapshot" not in said()
    assert not errors, errors
    pg.goto(f.as_uri() + "#/items?kind=ticket&moved=doing")                       # a set: not held, and said so
    pg.wait_for_selector(".set-chip.bad", timeout=20000)
    assert "items: not in this snapshot" in pg.locator(".set-chip.bad").inner_text()
    assert not errors, errors
    pg.close()


# ---- a report upstream's page (SPEC §12m): the text to paste, a Copy button, the link to a new issue, the scrub log

def seed_report(d: Path, home: Path) -> str:
    code = f"""
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
from ergostat.reports import record
p = Project(mdl.load(Path({str(d)!r})))
got = record.draft(p, "worker crashed writing inbox for dana@corp.example.com", origin="agent", by="work-agent",
                   details="on build7.corp.internal, token=s3cr3tvalue", parts=["block.worker"])
print(got["id"])
"""
    out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "ERGOSTAT_HOME": str(home)}, check=True,
                         capture_output=True, text=True)
    return out.stdout.strip().splitlines()[-1]


@pytest.fixture(scope="module")
def reported(tmp_path_factory):
    d = tmp_path_factory.mktemp("first-loop") / "first-loop"
    shutil.copytree(ROOT / "examples" / "first-loop", d)
    home = d.parent / "home"
    rid = seed_report(d, home)
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
    yield url, rid
    proc.terminate()
    proc.wait(timeout=10)


def test_a_reports_page_shows_its_text_a_copy_button_the_issue_link_and_the_scrub_log(browser, reported):
    url, rid = reported
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000})
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{url}/")                                       # needs attention: one line
    pg.wait_for_function("() => document.body.innerText.includes('reports upstream')")
    pg.goto(f"{url}/item/{rid}")
    pg.wait_for_selector(".report-body")
    body = pg.locator(".report-body").inner_text()
    assert "What went wrong" in body and "email-1" in body
    for secret in ("dana@corp.example.com", "build7.corp.internal", "s3cr3tvalue", "worker", "inbox"):
        assert secret not in body, secret
    link = pg.locator("a.report-issue")
    href = link.get_attribute("href")
    assert href.startswith("https://github.com/danroblewis/ergostat/issues/new?title=") and link.get_attribute("target") == "_blank"
    log = pg.locator(".scrub-log").inner_text()
    assert "dana@corp.example.com" in log and "an email address" in log and "block-1" in log
    pg.locator("button.report-copy").click()
    pg.wait_for_function("() => document.querySelector('.report-acts .note').textContent.includes('Copied')")
    assert "What went wrong" in pg.evaluate("navigator.clipboard.readText()")
    pg.locator('button[data-mark="submitted"]').click()
    pg.wait_for_function("() => document.querySelector('.track .stbox.on')?.textContent === 'submitted'", timeout=15000)
    assert not errors, errors
    ctx.close()


REMOTE_LOCAL = """
name: home
remotes:
  r:
    url: {url}
    token-file: r.token
stocks:
  queue:
    sensor: {{run: echo 1}}
"""


def fake_remote():
    """An in-process stdlib remote: /remote/v1/counts, items, items/ID, status and events, one item and one event."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    now = time.time()
    from urllib.parse import unquote
    ev = {"seq": 1, "id": "e1", "type": "incident.opened", "item": "incident/3", "time": now - 30,
          "data": {"title": "disk full"}}
    answers = {"counts": {"kinds": {"incident": {"open": 1, "closed": 4}}, "total": 5},
               "items": {"items": [{"id": "incident/3", "kind": "incident", "state": "open"}], "total": 5, "kinds": []},
               "items/incident/3": {"id": "incident/3", "state": "open", "fields": {"title": "disk full", "notes": "file:notes.md",
                                                    "shots": [{"pic": "file:shot.png"}]}, "events": 1,
                             "moves": [{"time": now - 30, "from": None, "to": "open", "type": "incident.opened"}],
                             "record": [ev]},
               "status": {"last_seq": 1},
               "events": {"events": [ev], "next": 1, "more": False, "last_seq": 1}}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            # as remote_api.answer: split on /, then each segment unquoted (an id's encoded / is one segment)
            path = "/".join(unquote(x) for x in self.path.split("?")[0].removeprefix("/remote/v1/").split("/"))
            body = answers.get(path)
            self.send_response(200 if body is not None else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body if body is not None else {"error": "not here"}).encode())

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", free_port()), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_a_remotes_items_and_events_are_shown_marked_remote(browser, tmp_path, monkeypatch):
    import types

    from ergostat import model as mdl
    from ergostat.remote import events, items
    from ergostat.store import Project
    from ergostat.web import serve as web_serve
    clock = [time.time()]                              # the remote's clock (items.time, events.time), moved on by hand:
    now = types.SimpleNamespace(time=lambda: clock[0])  # the period (10 s at least) passes without a real wait
    monkeypatch.setattr(items, "time", now)
    monkeypatch.setattr(events, "time", now)
    items._state.clear()
    events._kept.clear()
    remote, rurl = fake_remote()
    d = tmp_path / "home"
    d.mkdir()
    (d / "ergostat.yaml").write_text(REMOTE_LOCAL.format(url=rurl))
    (d / "r.token").write_text("tok")
    server, url = web_serve(Project(mdl.load(d)), free_port())
    pg = browser.new_page(viewport={"width": 1400, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        pg.goto(f"{url}/items")
        sec = pg.locator('section.sys-group.remote[data-remote="r"]')
        sec.locator("a", has_text="incident/3").first.wait_for()
        text = sec.inner_text()
        assert "remote r" in text and rurl in text and "incident" in text and "closed" in text
        assert sec.locator(f'a[href="{rurl}/item/incident%2F3"]').count() == 1
        sec.locator('a[href="/item/incident%2F3?remote=r"]').click()
        pg.wait_for_function("() => document.body.innerText.includes('disk full')")
        assert pg.url.endswith("/item/incident%2F3?remote=r")
        assert "remote r" in pg.locator("h1").inner_text() and pg.locator("textarea").count() == 0
        pg.goto(f"{url}/record?remote=r")
        pg.wait_for_function("() => document.body.innerText.includes('incident.opened')")
        assert pg.locator(".remote-links a", has_text="remote r").count() == 1
        assert pg.locator('a[href="/item/incident%2F3?remote=r"]').count() >= 1   # its item, opened there
        remote.shutdown()
        remote.server_close()
        clock[0] += 60                                  # past the period: the next poll asks again, and fails
        pg.wait_for_function("() => document.body.innerText.includes('r does not answer')", timeout=20000)
        body = pg.locator("#main").inner_text()
        assert "these were read" in body and "ago" in body and "Nothing recorded yet." not in body
        assert "incident.opened" in body                   # what was read before, still shown
        assert not errors, errors
    finally:
        pg.close()
        server.shutdown()
        server.server_close()
        items._state.clear()
        events._kept.clear()


def test_a_remote_items_file_field_never_reads_a_local_file(browser, tmp_path):
    """A remote item's `file:` value names a file in the remote's project: shown as text, never fetched from ours."""
    from ergostat import model as mdl
    from ergostat.remote import events, items
    from ergostat.store import Project
    from ergostat.web import serve as web_serve
    items._state.clear()
    events._kept.clear()
    remote, rurl = fake_remote()
    d = tmp_path / "home"
    d.mkdir()
    (d / "ergostat.yaml").write_text(REMOTE_LOCAL.format(url=rurl))
    (d / "r.token").write_text("tok")
    (d / "notes.md").write_text("LOCAL-ONLY TEXT\n")          # a local file of the same name as the remote's
    server, url = web_serve(Project(mdl.load(d)), free_port())
    pg = browser.new_page(viewport={"width": 1400, "height": 1000})
    asked: list[str] = []
    pg.on("request", lambda r: asked.append(r.url))
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        pg.goto(f"{url}/item/incident%2F3?remote=r")
        pg.wait_for_function("() => document.body.innerText.includes('file:notes.md')")
        pg.wait_for_function("() => document.body.innerText.includes('file:shot.png')")   # inside a list of records
        body = pg.locator("#main").inner_text()
        assert "LOCAL-ONLY TEXT" not in body
        assert pg.locator("#main img").count() == 0 and pg.locator("#main .file-view").count() == 0
        pg.goto(f"{url}/record?remote=r")                     # a later page: any request the item page made is seen
        pg.wait_for_function("() => document.body.innerText.includes('incident.opened')")
        assert not [u for u in asked if "/file/" in u], asked
        assert not errors, errors
    finally:
        pg.close()
        server.shutdown()
        server.server_close()
        remote.shutdown()
        remote.server_close()
        items._state.clear()
        events._kept.clear()


UPKEEP_SEED = """
import sys, time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path(sys.argv[1])))
for stock, value in (("inbox", 10), ("model-error", 0.5), ("unanswered-requests", 3)):   # inbox-short holds; the two
    s = next(iter(p.model.spec.stocks[stock].sensors.values()))                         # modelling goals are off
    p.measurements.add(s.series, value, at=time.time())
"""


def test_the_header_counts_the_systems_goals_and_the_models_upkeep_apart(browser, tmp_path):
    """Q14: with only requests-handled and model-fits off (the modelling use's own goals), the header's first figure is
    0 and not red, 'model upkeep 2' is said apart, and the switcher's entry for a project, read from another one, has
    the same first figure as that project's own header."""
    home, urls, procs = tmp_path / "home", {}, []
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        for name in ("first-loop", "second-loop"):
            d = tmp_path / name
            shutil.copytree(ROOT / "examples" / "first-loop", d)
            y = d / "ergostat.yaml"
            y.write_text(y.read_text().replace("name: first-loop", f"name: {name}"))
            env = {**os.environ, "ERGOSTAT_HOME": str(home)}
            subprocess.run([sys.executable, "-c", UPKEEP_SEED, str(d)], env=env, check=True, capture_output=True)
            port = free_port()
            procs.append(subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                                          env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            urls[name] = f"http://127.0.0.1:{port}"
        for url in urls.values():
            for _ in range(150):
                try:
                    urllib.request.urlopen(url + "/api/status", timeout=1)
                    break
                except Exception:
                    time.sleep(0.2)
            else:
                pytest.fail("a page never came up")
        heads, entries = {}, {}
        for name, url in urls.items():
            pg.goto(f"{url}/items")
            st = pg.evaluate("() => fetch('/api/status').then((r) => r.json())")
            assert sorted(n for n, lp in st["loops"].items() if lp["status"] == "off") == ["model-fits", "requests-handled"]
            pg.wait_for_function("() => / off/.test(document.querySelector('#running').textContent)")
            run = pg.locator("#running")
            heads[name] = run.inner_text()
            assert re.match(r"^0 goals off\b", heads[name]), heads[name]
            red = pg.evaluate("""() => { const p = document.createElement('span'); p.className = 'runstate bad';
                document.body.append(p); const c = getComputedStyle(p).color; p.remove(); return c; }""")
            assert run.evaluate("(e) => getComputedStyle(e).color") != red, "the first figure is red"
            assert pg.locator("#upkeep").inner_text().strip() == "· model upkeep 2"
            assert pg.locator("#upkeep").evaluate("(e) => getComputedStyle(e).color") != red
            assert "model upkeep 2" in pg.locator("header").inner_text()
            other = next(n for n in urls if n != name)
            find = f"[...document.querySelectorAll('#project option')].find((o) => o.text.startsWith('{other} ('))"
            pg.wait_for_function(f"() => !!{find}")
            entries[other] = pg.evaluate(f"() => {find}.text")
        for name, head in heads.items():
            entry = entries[name]
            assert re.search(r"\((\d+) off", entry).group(1) == re.match(r"^(\d+)", head).group(1), (entry, head)
            assert "model upkeep 2" in entry, entry
    finally:
        pg.close()
        for proc in procs:
            proc.terminate()
            proc.wait(timeout=10)
