"""Golden-file page tests (tests/golden.py): a page's rendered structure is compared with its saved reference in
tests/golden/, and an intended change regenerates the reference by a command instead of rewriting assertions:

    uv run python scripts/suite_watch.py -- uv run --with playwright==1.63.0 python -m tests.golden

The Dashboard's panels first: the default Dashboard made from test_dashboard_page's fake fields, every query answered
with the same three points, the clock, time zone, locale and pixel ratio fixed, so what is drawn depends on the page's
code alone.
"""

from __future__ import annotations

import base64
import json

import pytest

from ergostat.query import graphs
from tests import golden
from tests.test_dashboard_page import FIELDS, GRAPH, ITEMS, SETTLED, WATCH, served

NOW = 1795400000.0                                       # test_dashboard_page's answer() is at this moment


def process_map(kind: str) -> dict:
    """What process.process answers for ``kind``: its items started, went new > ready > building > checked > shipped,
    some sent back from checked to ready (a return), and ended."""
    steps = ["^", "new", "ready", "building", "checked", "shipped", "$"]
    role = {"^": "start", "$": "end"}
    nodes = [{"id": f"p:{kind}:{a}", "kind": role.get(a, "activity"), "itemKind": kind, "activity": a,
              "label": {"^": "start", "$": "end"}.get(a, a), "count": 10 + 2 * (a in ("ready", "building", "checked")),
              "items": 10} for a in steps]
    pairs = [*zip(steps, steps[1:], strict=False), ("checked", "ready")]
    edges = [{"id": f"f:{kind}:{a}>{b}", "kind": "follows", "source": f"p:{kind}:{a}", "target": f"p:{kind}:{b}",
              "itemKind": kind, "from": a, "to": b, "count": 2 if (a, b) == ("checked", "ready") else 10,
              "returns": 2 if (a, b) == ("checked", "ready") else 0, "median": 600.0} for a, b in pairs]
    return {"kind": "process", "nodes": nodes, "edges": edges, "since": NOW - 86400, "until": NOW}


def answer(route):
    """A fake /api/query: three points for every query asked, and a process map for a process graph, made into the
    panel's answer as the engine makes it (graphs.answer), so the process-map panel is drawn, not its error."""
    text = route.request.url.split("q=")[1].split("&")[0]
    asked = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))

    def one(q):
        if q.get("source") == "graph":                   # (the default asks for no other graph than the process map)
            return {"id": q["id"], **graphs.drawn(*graphs.process(process_map(q["kind"]))), "read_log": False}
        return {"id": q["id"], "times": [NOW - 120, NOW - 60, NOW], "series": [{"name": "x", "values": [1.0, 2.0, 3.0]}],
                "unit": "", "capped": 0, "read_log": False}
    route.fulfill(json={"now": NOW, "since": NOW - asked["since"], "until": NOW, "step": 60,
                        "results": [one(q) for q in asked["queries"]]})


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
    # the process map is laid out by ELK after its answer: wait until it has drawn, or said why not
    pg.wait_for_function("() => [...document.querySelectorAll('.graph-panel')].every((g) => g.firstElementChild)")
    pg.wait_for_timeout(300)                             # (dashPlotsMoved tells the plots where they are after 240 ms)
    text = pg.evaluate(golden.STRUCTURE, ".dash-grid > .dash-cell")
    drawn = pg.evaluate("() => [...document.querySelectorAll('.graph-panel')].map((g) => g.querySelectorAll('g.graph-node').length)")
    assert errors == []
    assert drawn == [7], drawn                           # the process map's 7 nodes drawn, not its error message
    ctx.close()
    golden.compare("dashboard-default-panels", text)
