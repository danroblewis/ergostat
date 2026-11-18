"""Acceptance: the control diagram of every example, drawn in a real browser, in every view (the
whole, everything open, each system opened, each drawn alone), draws no line through a part that
is not one of its ends, no line on top of another (lines merging into or out of one end are a net),
no line far longer than the way it covers, no two lines of one net crossing, no part on another or
under an outline it is not in, no drawing bigger than recorded or far longer one way than the other
when it does not fit the screen, and no page error;
draws within its time (ELK's layout, with ELK's lines), and has libavoid's lines within a
generous bound (routed in a worker, after the first draw).

And a generated model, 16 systems of 6 loops each (STRESS=systems,loops to change it), each
feeding the next and driving a flow two along: about 400 parts and 500 lines, drawn in about
0.3s and routed in about 1s.

It needs Playwright and the Chrome installed on this machine, so the usual run skips it:

    uv run --with playwright python -m pytest tests/test_diagram_rendering.py -v -s
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
AUDIT = (ROOT / "scripts" / "diagram_audit.js").read_text()
EXAMPLES = sorted(p.name for p in (ROOT / "examples").iterdir() if (p / "ergostat.yaml").exists())
# drawn, and its lines routed (libavoid's, in place of ELK's first ones)
READY = ("() => typeof S !== 'undefined' && S.layout && S.graphSig && !S.layout.routing && "
         "document.querySelectorAll('svg.canvas g.node').length > 0")
# [until it is first drawn, until its lines are routed], in ms
TIMED = ("async () => { const t = performance.now(); const lay = await layoutGraph(S.graph, 1.6, false); "
         "const first = performance.now() - t; await lay.whenRouted; return [first, performance.now() - t]; }")
LAYOUT_BUDGET_MS = 2500       # until the biggest view is first drawn, on a laptop; generous, to catch the layout going quadratic
ROUTED_BOUND_MS = 20000       # until libavoid's lines replace ELK's (in a worker: the page is never held up meanwhile);
                              # the 24x8 model (STRESS=24,8: 1,030 lines) takes about 15s, nearly all of it libavoid's
MAX_PIPE_BENDS = 6             # a flow that runs back (rework into a backlog) must turn; more is a pipe pushed about
# compactness: each view's drawing as much on the screen as it was recorded (tests/fixtures/diagram_sizes.json, written
# again with RECORD_SIZES=1 when a layout change is meant to make it so) and no longer one way than the other
SIZES = ROOT / "tests" / "fixtures" / "diagram_sizes.json"
SIZE_SLACK = 1.15              # the fit zoom may fall, the area grow, this much (labels' widths move a little with the data)
MAX_ASPECT = 4.0               # wider than tall (or taller than wide) by more, and too big to read whole (MIN_FIT):
MIN_FIT = 0.7                  # it runs off the screen one way, with the screen empty the other


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception as e:                        # no Chrome here
            pytest.skip(f"no Chrome to drive: {e}")
        yield b
        b.close()


@pytest.fixture(scope="module", params=EXAMPLES)
def page_of(request, tmp_path_factory):
    """The example's page, served (the model is not run: what is drawn is its structure)."""
    name = request.param
    d = tmp_path_factory.mktemp(name) / name
    shutil.copytree(ROOT / "examples" / name, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    port = free_port()
    env = {**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")}
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail(f"{name}: the page never answered")
    yield name, url
    proc.terminate()
    proc.wait(10)


def drawn(pg, url: str, view: str, n: int) -> None:
    pg.goto(f"{url}/diagram?v={n}&{view}")            # a new query: the page loads afresh, no layout carried over
    pg.wait_for_function(READY, timeout=60000)


def test_every_view_draws_cleanly_and_in_time(browser, page_of):
    name, url = page_of
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    drawn(pg, url, "", 0)
    tree = pg.evaluate("() => S.graph.tree || {}")
    views = ["", "open=*", *(f"open={s}" for s in tree), *(f"system={s}" for s in tree)]
    problems, slowest, routed = [], (0.0, ""), (0.0, "")
    everything = json.loads(SIZES.read_text()) if SIZES.exists() else {}
    recorded, sizes = everything.get(name, {}), {}
    for i, v in enumerate(views):
        drawn(pg, url, v, i + 1)
        r = pg.evaluate(AUDIT)
        problems += [f"[{v or 'whole'}] {k}: {x}" for k in ("through", "overlap", "detour", "netCrossings", "partOverlap")
                     for x in r[k]]
        if r["mostPipeBends"][0] > MAX_PIPE_BENDS:                   # a flow reads best straight: the links bend instead
            problems.append(f"[{v or 'whole'}] pipe {r['mostPipeBends'][1]} bends {r['mostPipeBends'][0]} times")
        size = r["size"]
        sizes[v] = [size["width"], size["height"], size["fit"]]
        was = recorded.get(v)
        # no less of it on the screen at once (a drawing shown whole at full size may change its shape), and
        # one too big to show whole no bigger
        if was and (min(size["fit"], 1) < min(was[2], 1) / SIZE_SLACK or
                    (size["fit"] < 1 and size["width"] * size["height"] > SIZE_SLACK * was[0] * was[1])):
            problems.append(f"[{v or 'whole'}] drawn {size['width']}x{size['height']} (fit {size['fit']}), "
                            f"recorded {was[0]}x{was[1]} (fit {was[2]})")
        if max(size["aspect"], 1 / size["aspect"]) > MAX_ASPECT and size["fit"] < MIN_FIT:    # (a short chain that fits is fine)
            problems.append(f"[{v or 'whole'}] {size['width']}x{size['height']}: aspect {size['aspect']}")
        first, final = pg.evaluate(TIMED)
        slowest = max(slowest, (first, v or "whole"))
        routed = max(routed, (final, v or "whole"))
    pg.close()
    if os.environ.get("RECORD_SIZES"):
        everything = json.loads(SIZES.read_text()) if SIZES.exists() else {}
        SIZES.write_text(json.dumps({**everything, name: sizes}, indent=1, sort_keys=True) + "\n")
    print(f"{name}: {len(views)} views, slowest first draw {slowest[0]:.0f}ms ({slowest[1]}), "
          f"slowest routing {routed[0]:.0f}ms ({routed[1]})")
    assert not errors, errors
    assert not problems, f"{name}: " + "\n".join(problems)
    assert slowest[0] < LAYOUT_BUDGET_MS, f"{name}: drawing {slowest[1]} took {slowest[0]:.0f}ms"
    assert routed[0] < ROUTED_BOUND_MS, f"{name}: routing {routed[1]} took {routed[0]:.0f}ms"


def big_model(systems: int = 8, loops: int = 4) -> str:
    """Systems of loops in series, each system feeding the next and driving a flow in the one after it:
    many lines crossing system edges, the case the router works hardest on."""
    out = ["name: stress", "systems:"] + [f"  s{i}:\n    description: system {i}" for i in range(systems)]
    stocks, flows, goals, blocks = ["stocks:"], ["flows:"], ["goals:"], ["blocks:"]
    for i in range(systems):
        for j in range(loops):
            q = f"q{i}-{j}"
            stocks += [f"  {q}:", f"    system: s{i}", "    unit: jobs", "    sensor:", "      manual: true"]
            nxt = f"q{i}-{j + 1}" if j + 1 < loops else (f"q{i + 1}-0" if i + 1 < systems else None)
            flows += [f"  {q}-out:", f"    system: s{i}", f"    from: {q}"] + ([f"    to: {nxt}"] if nxt else [])
            if j == 0:
                flows += [f"  {q}-in:", f"    system: s{i}", f"    to: {q}"]
                if i >= 2:
                    flows += [f"    driven-by: flow.q{i - 2}-{loops - 1}-out"]
            goals += [f"  {q}-low:", f"    system: s{i}", f"    stock: {q}", '    hold: "<= 5"']
            blocks += [f"  w{i}-{j}:", f"    system: s{i}", "    type: program", "    run: echo 1", f"    goal: {q}-low",
                       f"    out: flow.{q}-out"]
    return "\n".join(out + stocks + flows + goals + blocks) + "\n"


def test_a_big_tangled_model_lays_out_in_time_and_cleanly(browser, tmp_path):
    d = tmp_path / "stress"
    d.mkdir()
    (d / "ergostat.yaml").write_text(big_model(*map(int, os.environ.get("STRESS", "16,6").split(","))))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, v in enumerate(("", "open=*", "open=s3", "system=s3")):
            drawn(pg, url, v, i)
            r = pg.evaluate(AUDIT)
            first, final = pg.evaluate(TIMED)
            n = pg.evaluate("() => [S.graph.nodes.length, S.graph.edges.length]")
            print(f"stress [{v or 'whole'}]: {n[0]} parts, {n[1]} lines, drawn {first:.0f}ms, routed {final:.0f}ms; "
                  f"through {len(r['through'])}, overlap {len(r['overlap'])}, detour {len(r['detour'])}, "
                  f"net crossings {len(r['netCrossings'])}")
            assert first < LAYOUT_BUDGET_MS, f"[{v}] took {first:.0f}ms to draw"
            assert final < ROUTED_BOUND_MS, f"[{v}] took {final:.0f}ms to route"
            assert not r["through"] and not r["detour"] and not r["netCrossings"], (v, r["through"][:5], r["detour"][:5])
        assert not errors, errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)


def test_every_part_opens_its_panel_when_clicked_even_mid_redraw(browser, tmp_path):
    """Clicking any part says what it is; and a redraw landing between the press and the release
    (the page redraws every few seconds) does not swallow the click."""
    d = tmp_path / "software-factory"
    shutil.copytree(ROOT / "examples" / "software-factory", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="fit").click()
        silent = []
        ids = pg.evaluate("() => S.graph.nodes.filter((n) => n.kind !== 'cloud').map((n) => n.id)")
        for i, nid in enumerate(ids):
            pg.evaluate("() => { const d = document.querySelector('#detail'); d.hidden = true; d.replaceChildren(); }")
            hit = pg.locator(f'g.node[data-id="{nid}"] .hit').first
            box = hit.bounding_box()
            if not box:
                continue
            pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            pg.mouse.down()
            if i % 2:                                      # every other click, the page redraws in the middle of it
                pg.evaluate("() => drawGraph(document.querySelector('svg.canvas'), S.graph, S.layout)")
            pg.mouse.up()
            try:
                pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail .what')",
                                     timeout=3000)
            except Exception:
                silent.append(nid)
        pg.close()
        assert not errors, errors
        assert not silent, f"clicked, and no panel said what it is: {silent}"
    finally:
        proc.terminate()
        proc.wait(10)


@contextlib.contextmanager
def served(example: str, tmp_path: Path, edit=None):
    """An example's page, served from a fresh copy (the model is not run; ``edit`` may change the copy first)."""
    d = tmp_path / example
    shutil.copytree(ROOT / "examples" / example, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    if edit:
        edit(d)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        proc.wait(10)


VALVE_SIDES = """() => {
  // each valve's information lines attach at its stem, on the side most of what they join lies: up or down
  // for a level valve, left or right for one turned upright (valves.js)
  const box = Object.fromEntries(S.layout.children.map((c) => [c.id, c])), bad = [];
  for (const n of S.graph.nodes.filter((n) => n.kind === "valve" || n.kind === "disturbance")) {
    const c = box[n.id]; if (!c) continue;
    const ends = S.layout.edges.map((le) => [le, S.graph.edges.find((e) => e.id === le.id)])
      .filter(([, e]) => e && e.kind !== "pipe" && (e.source === n.id || e.target === n.id));
    if (!ends.length) continue;
    const upright = ["up", "down"].includes(c.turn?.flow);
    const far = (o) => (upright ? o.x + o.width / 2 > c.x + c.width / 2 + 10 : o.y + o.height / 2 > c.y + c.height / 2 + 10);
    const beyond = ends.filter(([, e]) => { const o = box[e.source === n.id ? e.target : e.source]; return o && far(o); }).length;
    const want = upright ? (beyond > ends.length / 2 ? "right" : "left") : (beyond > ends.length / 2 ? "down" : "up");
    if (c.turn?.stem !== want) bad.push(`${n.id}: stem ${c.turn?.stem}, its links lie ${want}`);
    for (const [le, e] of ends) {
      const sec = le.sections[0], p = e.source === n.id ? sec.startPoint : sec.endPoint;
      const on = { up: Math.abs(p.y - c.y) < 3, down: Math.abs(p.y - (c.y + c.height)) < 3,
                   left: Math.abs(p.x - c.x) < 3, right: Math.abs(p.x - (c.x + c.width)) < 3 }[want];
      if (!on) bad.push(`${n.id}: ${le.id} at ${Math.round(p.x)},${Math.round(p.y)} (stem ${want})`);
    }
  }
  return bad;
}"""


def test_valves_face_their_links_and_pipes_show_their_arrowheads(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        for i, v in enumerate(("system=product", "open=*", "open=product")):
            drawn(pg, url, v, i)
            assert pg.evaluate(VALVE_SIDES) == [], v
            heads = pg.evaluate("() => [...document.querySelectorAll('g.edge.pipe path.pipe-head')]"
                                ".map((h) => getComputedStyle(h).fill)")
            arrows = pg.evaluate("() => S.graph.edges.filter((e) => e.kind === 'pipe' && e.arrow).length")
            assert len(heads) == arrows and all(f not in ("none", "") for f in heads), (v, len(heads), arrows, heads[:3])
        pg.close()


UPRIGHT = """async () => {
  // the stock building pinned where it is, its valve abandoned above it and the valve's cloud above that:
  // the valve turns upright, its pipes in at the bottom and out at the top, the cloud's on its bottom
  const at = (id) => S.layout.children.find((c) => c.id === id);
  const st = at("stock:building"), v = at("flow:abandoned"), cl = at("cloud:abandoned:out");
  const cx = st.x + st.width / 2;
  S.pins = { "stock:building": { x: st.x, y: st.y }, "flow:abandoned": { x: Math.round(cx - v.width / 2), y: st.y - 150 },
             "cloud:abandoned:out": { x: Math.round(cx - cl.width / 2), y: st.y - 280 } };
  await S.relayout();
  await S.layout.whenRouted;
  const gEdge = (le) => S.graph.edges.find((x) => x.id === le.id);
  const edge = (s, t) => S.layout.edges.find((le) => { const e = gEdge(le); return e && e.source === s && e.target === t; });
  const ends = (le) => { const sec = le.sections[0]; return [sec.startPoint, sec.endPoint]; };
  const c = at("flow:abandoned"), k = at("cloud:abandoned:out");
  const [, inEnd] = ends(edge("stock:building", "flow:abandoned"));
  const [outStart, outEnd] = ends(edge("flow:abandoned", "cloud:abandoned:out"));
  const el = document.querySelector('g.node[data-id="flow:abandoned"]');
  const mine = (e) => e && e.kind !== "pipe" && (e.source === "flow:abandoned" || e.target === "flow:abandoned");
  const info = S.layout.edges.filter((le) => mine(gEdge(le)))
    .map((le) => (gEdge(le).source === "flow:abandoned" ? le.sections[0].startPoint : le.sections[0].endPoint));
  return { turn: c.turn, drawn: el.dataset.turn, glyph: el.querySelector("g")?.getAttribute("transform") || "",
           inAtBottom: Math.abs(inEnd.y - (c.y + c.height)) < 3 && inEnd.x > c.x && inEnd.x < c.x + c.width,
           outAtTop: Math.abs(outStart.y - c.y) < 3 && outStart.x > c.x && outStart.x < c.x + c.width,
           cloudBottom: Math.abs(outEnd.y - (k.y + k.height)) < 3,
           infoOnSide: info.every((p) => Math.abs(p.x - c.x) < 3 || Math.abs(p.x - (c.x + c.width)) < 3), info: info.length };
}"""


def test_a_valve_turns_upright_when_its_pipe_runs_up(browser, tmp_path):
    """What flows into a valve below it and out of it above it: the valve is drawn turned a quarter, its
    pipes attach at its bottom and top (and at the cloud's bottom), its information lines at its side."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=lab", 0)
        r = pg.evaluate(UPRIGHT)
        assert r["turn"]["flow"] == "up" and r["turn"]["stem"] in ("left", "right"), r
        assert r["drawn"].startswith("up ") and r["glyph"].startswith("matrix(0,-1"), r
        assert r["inAtBottom"] and r["outAtTop"] and r["cloudBottom"] and r["infoOnSide"], r
        audit = pg.evaluate(AUDIT)
        assert not audit["through"], audit["through"]
        assert not errors, errors
        pg.close()


def test_the_background_hides_the_side_panel_and_a_part_dragged_stays_pinned(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=product", 0)
        pg.get_by_role("button", name="fit").click()
        side = "() => document.querySelector('.diagram').classList.contains('side-hidden')"
        empty = pg.evaluate("""() => { const r = document.querySelector('svg.canvas').getBoundingClientRect();
            for (let y = r.top + 80; y < r.bottom - 80; y += 17) for (let x = r.left + 40; x < r.right - 40; x += 23) {
              const e = document.elementFromPoint(x, y); if (e && e.tagName === 'svg') return {x, y}; } return null; }""")
        assert empty, "no empty background to click"
        pg.mouse.click(empty["x"], empty["y"])
        pg.wait_for_timeout(200)
        assert pg.evaluate(side) is True
        pg.mouse.click(empty["x"], empty["y"])
        pg.wait_for_timeout(200)
        assert pg.evaluate(side) is False
        pg.mouse.move(empty["x"], empty["y"])
        pg.mouse.down()
        pg.mouse.move(empty["x"] + 80, empty["y"] + 40)
        pg.mouse.up()
        pg.wait_for_timeout(200)
        assert pg.evaluate(side) is False, "a pan is not a click"

        # drag a stock 150px right and 120px down: it stays there, pinned, and its lines are routed to it
        nid = "stock:users"
        before = pg.evaluate(f"() => {{ const c = S.layout.children.find((c) => c.id === '{nid}'); return [c.x, c.y]; }}")
        hit = pg.locator(f'g.node[data-id="{nid}"] .hit').first.bounding_box()
        k = pg.evaluate("() => S.view.k")
        x, y = hit["x"] + hit["width"] / 2, hit["y"] + hit["height"] / 2
        pg.mouse.move(x, y)
        pg.mouse.down()
        for step in range(1, 11):
            pg.mouse.move(x + 15 * step * k, y + 12 * step * k)
        pg.mouse.up()
        pg.wait_for_function(f"() => S.layout.children.find((c) => c.id === '{nid}') && S.pins['{nid}']", timeout=10000)
        pg.wait_for_timeout(1500)
        after = pg.evaluate(f"() => {{ const c = S.layout.children.find((c) => c.id === '{nid}'); return [c.x, c.y]; }}")
        assert abs(after[0] - before[0] - 150) < 6 and abs(after[1] - before[1] - 120) < 6, (before, after)
        r = pg.evaluate(AUDIT)
        assert not r["through"], r["through"]
        ends = pg.evaluate(f"""() => S.layout.edges.filter((le) => {{
            const e = S.graph.edges.find((x) => x.id === le.id);
            return e && (e.source === '{nid}' || e.target === '{nid}'); }}).map((le) => {{
            const c = S.layout.children.find((c) => c.id === '{nid}');
            const s = le.sections[0], e = S.graph.edges.find((x) => x.id === le.id);
            const p = e.source === '{nid}' ? s.startPoint : s.endPoint;
            return p.x >= c.x - 2 && p.x <= c.x + c.width + 2 && p.y >= c.y - 2 && p.y <= c.y + c.height + 2; }})""")
        assert ends and all(ends), "every line of the moved part ends on it"
        stored = pg.evaluate("() => Object.keys(localStorage).filter((k) => k.startsWith('ergostat.pins.'))")
        assert stored, "the pin is kept in this browser"
        drawn(pg, url, "open=product", 9)                          # a new visit: still where it was put
        again = pg.evaluate(f"() => {{ const c = S.layout.children.find((c) => c.id === '{nid}'); return [c.x, c.y]; }}")
        assert abs(again[0] - after[0]) < 2 and abs(again[1] - after[1]) < 2
        pg.locator(f'g.pins .pin[data-id="{nid}"]').click(force=True)   # (the page redraws: it never stands still)
        pg.wait_for_function(f"() => !S.pins['{nid}']", timeout=10000)
        pg.close()


def test_an_open_system_dragged_by_its_outline_takes_its_parts_and_stays(browser, tmp_path):
    """An open system's outline, dragged by its top, moves with everything in it by the same amount;
    its lines are routed again, cleanly; nothing lands under it; and it stays there after a new visit."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="fit").click()
        places = """() => Object.fromEntries(S.layout.children.filter((c) => (S.graph.nodes.find((n) => n.id === c.id)?.systems || [])
                       .includes('product')).map((c) => [c.id, [c.x, c.y]]))"""
        before = pg.evaluate(places)
        frame = "() => { const c = S.layout.containers.find((c) => c.name === 'product'); return [c.bx ?? c.x, c.by ?? c.y]; }"
        hull = pg.evaluate(frame)
        grip = pg.locator('g.hull[data-hull="product"] rect.hull-grip').bounding_box()
        k = pg.evaluate("() => S.view.k")
        x, y = grip["x"] + grip["width"] * 0.6, grip["y"] + 8
        pg.mouse.move(x, y)
        pg.mouse.down()
        for step in range(1, 11):
            pg.mouse.move(x + 18 * step * k, y + 9 * step * k)
        pg.mouse.up()
        pg.wait_for_function(f"() => S.pins['hull:product'] && S.layout && !S.layout.routing && "
                             f"Math.abs(S.layout.containers.find((c) => c.name === 'product').x - {hull[0]}) > 100", timeout=20000)
        after = pg.evaluate(places)
        moved = pg.evaluate(frame)
        assert before and set(before) == set(after)
        offs = {(round(after[i][0] - before[i][0]), round(after[i][1] - before[i][1])) for i in before}
        assert len(offs) == 1, offs                                   # all by the same amount
        (dx, dy), = offs
        assert abs(dx - 180) < 8 and abs(dy - 90) < 8, (dx, dy)
        assert abs(moved[0] - hull[0] - dx) < 2 and abs(moved[1] - hull[1] - dy) < 2   # its frame with them
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["partOverlap"] and not r["netCrossings"], (r["through"], r["partOverlap"])
        drawn(pg, url, "open=*", 9)                                   # a new visit: still where it was put
        again = pg.evaluate(places)
        assert all(abs(again[i][0] - after[i][0]) < 2 and abs(again[i][1] - after[i][1]) < 2 for i in after)
        pg.locator('g.pins .pin[data-id="hull:product"]').dispatch_event("click")
        pg.wait_for_function("() => !S.pins['hull:product']", timeout=10000)
        assert not errors, errors
        pg.close()


SLANTED = """() => {
  // straight pieces of the lines as drawn that run neither across nor up and down (corners are curves)
  let n = 0;
  for (const p of document.querySelectorAll("svg.canvas g.edge path.info, svg.canvas g.edge path.pipe-out")) {
    let at = null;
    for (const m of (p.getAttribute("d") || "").matchAll(/([MLQ])\\s*([-\\d.e]+),([-\\d.e]+)(?:\\s+([-\\d.e]+),([-\\d.e]+))?/g)) {
      const pt = m[1] === "Q" ? { x: +m[4], y: +m[5] } : { x: +m[2], y: +m[3] };
      if (m[1] === "L" && at && Math.abs(pt.x - at.x) > 1 && Math.abs(pt.y - at.y) > 1) n++;
      at = pt;
    }
  }
  return n;
}"""


def test_parts_chosen_with_a_box_move_together_pinned_and_with_no_new_layout(browser, tmp_path):
    """Shift and a drag on the background draws a box: the parts it touches are chosen (marked); one of them
    dragged moves them all, its lines never drawn across meanwhile; let go, they are all pinned there, with
    no new layout, and their lines routed cleanly."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=product", 0)
        pg.get_by_role("button", name="fit").click()
        ids = ["stock:users", "flow:signups"]
        boxes = [pg.locator(f'g.node[data-id="{i}"]').bounding_box() for i in ids]
        x0, y0 = min(b["x"] for b in boxes) - 6, min(b["y"] for b in boxes) - 6
        x1, y1 = max(b["x"] + b["width"] for b in boxes) + 6, max(b["y"] + b["height"] for b in boxes) + 6
        pg.keyboard.down("Shift")
        pg.mouse.move(x0, y0)
        pg.mouse.down()
        pg.mouse.move((x0 + x1) / 2, (y0 + y1) / 2)
        pg.mouse.move(x1, y1)
        pg.mouse.up()
        pg.keyboard.up("Shift")
        assert {"stock.users", "flow.signups"} <= set(pg.evaluate("() => [...S.sel]"))      # model parts (interact.js)
        chosen = pg.evaluate("() => [...document.querySelectorAll('g.node.selected')].map((e) => e.dataset.id)")
        assert set(ids) <= set(chosen), chosen
        before = pg.evaluate("() => Object.fromEntries(S.layout.children.map((c) => [c.id, [c.x, c.y]]))")
        layouts = pg.evaluate("() => S.layouts")
        k = pg.evaluate("() => S.view.k")
        hit = pg.locator('g.node[data-id="stock:users"] .hit').first.bounding_box()
        x, y = hit["x"] + hit["width"] / 2, hit["y"] + hit["height"] / 2
        pg.mouse.move(x, y)
        pg.mouse.down()
        slanted = 0
        for step in range(1, 13):
            pg.mouse.move(x + 10 * step * k, y + 8 * step * k)
            pg.wait_for_timeout(40)
            slanted += pg.evaluate(SLANTED)
        pg.mouse.up()
        assert slanted == 0, f"{slanted} slanted pieces drawn while dragging"
        pg.wait_for_function("() => S.layout && !S.layout.routing", timeout=20000)
        pg.wait_for_timeout(300)
        assert pg.evaluate(SLANTED) == 0
        assert pg.evaluate("() => S.layouts") == layouts, "letting go laid the diagram out again"
        after = pg.evaluate("() => Object.fromEntries(S.layout.children.map((c) => [c.id, [c.x, c.y]]))")
        for i in chosen:
            assert abs(after[i][0] - before[i][0] - 120) < 6 and abs(after[i][1] - before[i][1] - 96) < 6, (i, before[i], after[i])
        pins = pg.evaluate("() => S.pins")
        assert all(i in pins for i in chosen), pins
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["partOverlap"] and not r["netCrossings"], (r["through"], r["partOverlap"])
        pg.keyboard.press("Escape")
        assert pg.evaluate("() => S.sel.size") == 0
        assert not errors, errors
        pg.close()


SCREEN_AT = """(name) => {
  // where a system is on the screen: its open outline, else its box (the box itself: not its ports, which stand out)
  const id = S.graph.nodes.find((n) => n.label === name && n.kind === "system")?.id;
  const el = document.querySelector(`g.hull[data-hull="${name}"] rect:not(.hull-grip)`) ||
             document.querySelector(`g.node[data-id="${id}"] .hit`);
  const r = el.getBoundingClientRect();
  return [r.left, r.top];
}"""


def test_opening_and_closing_a_system_keeps_it_on_the_screen_and_keeps_the_pins(browser, tmp_path):
    """A system opened stays where its box was on the screen, and closed again where its outline was; another
    system's box, put by hand, keeps its pin and its place through both."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=-", 0)
        pg.get_by_role("button", name="fit").click()
        # the product box put somewhere by hand
        box = pg.locator('g.node.k-system:has(text:text-is("product")) .hit').first.bounding_box()
        k = pg.evaluate("() => S.view.k")
        x, y = box["x"] + 30, box["y"] + 30
        pg.mouse.move(x, y)
        pg.mouse.down()
        for step in range(1, 11):                     # well below, clear of factory opened
            pg.mouse.move(x, y + 40 * step * k)
        pg.mouse.up()
        pg.wait_for_function("() => S.pins['hull:product'] && !S.layout.routing", timeout=20000)
        pinned = pg.evaluate(SCREEN_AT, "product")
        for name, opened in (("factory", True), ("factory", False)):
            at = pg.evaluate(SCREEN_AT, name)
            pg.evaluate("(n) => S.toggleSystem(n)", name)
            pg.wait_for_function(f"() => S.graph && (S.graph.open || []).includes('{name}') === {str(opened).lower()} && S.layout && "
                                 "!S.layout.routing && document.querySelectorAll('svg.canvas g.node').length", timeout=30000)
            pg.wait_for_timeout(300)
            now = pg.evaluate(SCREEN_AT, name)
            assert abs(now[0] - at[0]) < 4 and abs(now[1] - at[1]) < 4, (name, opened, at, now)
            assert pg.evaluate("() => !!S.pins['hull:product']"), "the pin was lost"
            if not opened:                              # back as it was: product's box where it was put
                d = pg.evaluate(SCREEN_AT, "product")
                assert abs(d[0] - pinned[0]) < 4 and abs(d[1] - pinned[1]) < 4, (pinned, d)
            r = pg.evaluate(AUDIT)
            assert not r["through"] and not r["partOverlap"], (name, opened, r["through"], r["partOverlap"])
        assert not errors, errors
        pg.close()


TRANSCRIPT = [
    {"type": "user", "timestamp": "2026-11-15T10:00:00Z",
     "message": {"role": "user", "content": "Do the thing. <script>window.pwned=1</script>"}},
    {"type": "assistant", "timestamp": "2026-11-15T10:00:01Z", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "I'll **run** it:\n\n```python\nprint('hi')\n```\n<img src=x onerror=\"window.pwned=2\">"},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "bin/py test.py"}}]}},
    {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok: 0 failed"}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}},
]


# item ids as the Items page links them: a / (as %2F), and the characters a path or a query would take for its own
ADDRESSED = ["ticket/7", "ticket/a b?c#d%e&f+g", "ticket/ünï(1)!'*~"]


def test_pages_are_ordinary_links_opened_in_new_tabs_reloaded_and_walked_back(browser, tmp_path):
    """Each page is a path: a link to an item is an ordinary link (opened by itself in a new tab it is the item's
    page, and a ctrl- or cmd-click opens one), a plain click goes there without reloading, a reload on a deep path
    draws it again, back and forward walk the pages, and an old #/ address lands on its path."""
    d = tmp_path / "addresses"
    d.mkdir()
    (d / "ergostat.yaml").write_text("items:\n  ticket:\n    id: ticket/*\n")
    home = tmp_path / "home"
    env = {**os.environ, "ERGOSTAT_HOME": str(home)}
    for i, iid in enumerate(ADDRESSED):
        subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "event", "--add", "ticket.opened", "--item", iid,
                        "--data", json.dumps({"title": f"number {i}"})], env=env, check=True, capture_output=True)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    item_page = "(id) => document.querySelector('#main h1')?.textContent === id && !!document.querySelector('#main .meta')"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        ctx.on("weberror", lambda e: errors.append(str(e.error)))
        pg = ctx.new_page()
        pg.goto(url + "/items")
        pg.wait_for_selector("#main tr.click a[href^='/item/']", timeout=20000)
        hrefs = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('#main tr.click a[href^=\"/item/\"]')]"
                            ".map((a) => [a.textContent, a.getAttribute('href')]))")
        assert set(hrefs) == set(ADDRESSED), hrefs
        assert hrefs["ticket/7"] == "/item/ticket%2F7"
        # each link, opened by itself in a new tab: that item's page
        for iid in ADDRESSED:
            tab = ctx.new_page()
            tab.goto(url + hrefs[iid])
            tab.wait_for_function(item_page, arg=iid, timeout=20000)
            assert tab.evaluate("location.pathname + location.search") == hrefs[iid]
            tab.close()
        # a ctrl- or cmd-click is left to the browser: a new tab, on the item; this page stays where it is
        link = pg.locator("#main tr.click a[href='/item/ticket%2F7']")
        with ctx.expect_page() as opened:
            link.click(modifiers=["ControlOrMeta"])
        tab = opened.value
        tab.wait_for_function(item_page, arg="ticket/7", timeout=20000)
        tab.close()
        assert pg.evaluate("location.pathname") == "/items"
        # a plain click: the item here, with no reload (what the page holds stays)
        pg.evaluate("window.__stayed = 1")
        link.click()
        pg.wait_for_function(item_page, arg="ticket/7", timeout=20000)
        assert pg.evaluate("[location.pathname, window.__stayed]") == ["/item/ticket%2F7", 1]
        # the header's links too, and the item's link back to its kind
        pg.locator("#nav a", has_text="Record").click()
        pg.wait_for_function("() => location.pathname === '/record' && document.querySelector('#nav a.on')?.textContent === 'Record'")
        assert pg.evaluate("window.__stayed") == 1
        # back and forward
        pg.go_back()
        pg.wait_for_function(item_page, arg="ticket/7", timeout=20000)
        pg.go_back()
        pg.wait_for_function("() => location.pathname === '/items' && document.querySelector('#main tr.click')", timeout=20000)
        pg.go_forward()
        pg.wait_for_function(item_page, arg="ticket/7", timeout=20000)
        assert pg.evaluate("window.__stayed") == 1
        # a reload on a deep path draws the same page
        pg.reload()
        pg.wait_for_function(item_page, arg="ticket/7", timeout=20000)
        assert pg.evaluate("window.__stayed") is None
        odd = hrefs[ADDRESSED[1]]
        pg.goto(url + odd)
        pg.reload()
        pg.wait_for_function(item_page, arg=ADDRESSED[1], timeout=20000)
        # a query kept on the path: the diagram's view, and reloaded as it was
        pg.goto(url + "/diagram?view=blocks")
        pg.wait_for_function("() => document.querySelector('.toolbar .seg button.on')?.textContent === 'Blocks'", timeout=30000)
        # old #/ addresses (bookmarks, briefs, messages): shown at their paths
        for old, new in (("/#/item/ticket%2F7", "/item/ticket%2F7"), ("/#/items?kind=ticket", "/items?kind=ticket"),
                         ("/#/diagram?view=blocks", "/diagram?view=blocks"), ("/#/fit", "/model")):
            pg.goto(url + old)
            pg.wait_for_function("(p) => location.pathname + location.search === p && !location.hash", arg=new, timeout=20000)
        pg.wait_for_function("() => document.querySelector('#main h1')?.textContent === 'Model'", timeout=20000)
        pg.goto(url + "/#/item/ticket%2F7")
        pg.wait_for_function(item_page, arg="ticket/7", timeout=20000)
        pg.go_back()                                   # the old address replaced, not added: back is the page before it
        pg.wait_for_function("() => location.pathname === '/model'", timeout=20000)
        ctx.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def test_an_items_files_show_as_what_they_are_and_nothing_in_them_runs(browser, tmp_path):
    """A transcript as a conversation (each tool call one line, with what came back), Markdown rendered
    with its code highlighted, an image as an image; HTML in any of it shown as text, never run."""
    d = tmp_path / "files"
    (d / "run").mkdir(parents=True)
    (d / "run" / "s.jsonl").write_text("\n".join(json.dumps(x) for x in TRANSCRIPT))
    (d / "run" / "notes.md").write_text("# Notes\n\nSome *text* and `code`.\n\n<script>window.pwned=3</script>\n")
    (d / "ergostat.yaml").write_text("items:\n  session:\n    id: session/*\n    formats:\n      transcript: claude-session\n")
    port = free_port()
    home = tmp_path / "home"
    env = {**os.environ, "ERGOSTAT_HOME": str(home)}
    subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "event", "--add", "session.ran", "--item", "session/x",
                    "--data", json.dumps({"transcript": "file:run/s.jsonl", "notes": "file:run/notes.md"})], env=env, check=True,
                   capture_output=True)
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/item/session%2Fx")
        pg.wait_for_selector(".convo .turn.tool", timeout=10000)
        assert pg.locator(".convo .turn.user").count() == 1 and pg.locator(".convo .turn.assistant").count() == 2
        tool = pg.locator(".convo .turn.tool")
        assert "Bash" in tool.inner_text() and "bin/py test.py" in tool.inner_text()
        tool.locator("summary").click()
        assert "ok: 0 failed" in tool.inner_text()
        assert pg.locator(".convo .hljs-built_in, .convo .hljs-string").count() > 0          # the python block, highlighted
        pg.wait_for_selector(".f-markdown h1", timeout=10000)
        assert pg.locator(".f-markdown h1").inner_text() == "Notes"
        pg.wait_for_timeout(500)
        assert pg.evaluate("() => window.pwned") is None, "HTML in a file ran in the page"
        assert not errors, errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)


def test_an_items_page_shows_each_fields_history_and_a_session_folded_from_its_transcript(browser, tmp_path, monkeypatch):
    """Each field with its current value and a history disclosure: each change, oldest last, with
    the event that made it (a click opens it); a refused patch said; and a session item whose
    transcript's lines became events, folded into its conversation. ERGOSTAT_SHOTS=DIR keeps
    screenshots of both."""
    from ergostat import model as mdl
    from ergostat import transcripts as tr
    from ergostat.store import Project
    d = tmp_path / "hist"
    (d / "run").mkdir(parents=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent("""
        items:
          ticket:
            id: ticket/*
            states: [open, review, done]
            on:
              ticket.submitted: review
              ticket.merged: done
            show: [title, owner]
            fold:
              notes: append
              hours: sum
              labels: union
          session:
            id: session/*
            states: [open, done]
            on:
              session.ran: done
            show: [role, cost_usd, transcript]
            formats:
              transcript: claude-session
            fold:
              messages: append
              tool_calls: append
              tool_results: append
              thinking: append
              tokens_in: sum
              tokens_out: sum
        """))
    home = tmp_path / "home"
    monkeypatch.setenv("ERGOSTAT_HOME", str(home))
    p = Project(mdl.load(d))
    t = time.time() - 3 * 3600
    p.events.add("ticket.opened", item="ticket/7", source="support", at=t,
                 data={"title": "Thumbnails are blurry", "owner": "ann", "notes": "reported by a customer", "hours": 0.5,
                       "labels": ["images"]})
    p.events.add("ticket.started", item="ticket/7", source="developer", at=t + 1800,
                 data={"owner": "bob", "notes": "the encoder's quality is 60", "hours": 2, "labels": ["encoder"]})
    p.events.add("ticket.retitled", item="ticket/7", source="developer", at=t + 2400,
                 patch=[{"op": "test", "path": "/title", "value": "Thumbnails are blurry"},
                        {"op": "replace", "path": "/title", "value": "Thumbnails are blurry at quality 60"}])
    p.events.add("ticket.retitled", item="ticket/7", source="pm", at=t + 2500,
                 patch=[{"op": "test", "path": "/title", "value": "Thumbnails are blurry"},
                        {"op": "replace", "path": "/title", "value": "Blurry"}])
    p.events.add("ticket.submitted", item="ticket/7", source="developer", at=t + 5400,
                 data={"notes": "raised it to 75; tests pass", "hours": 1.5})
    sess = [
        {"type": "user", "uuid": "u1", "parentUuid": None, "timestamp": "2026-11-15T10:00:00Z",
         "message": {"role": "user", "content": "Raise the thumbnail quality and check the sizes."}},
        {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "timestamp": "2026-11-15T10:00:04Z",
         "message": {"role": "assistant", "id": "m1", "usage": {"input_tokens": 1200, "output_tokens": 80},
                     "content": [{"type": "text", "text": "I'll look at the encoder settings first."},
                                 {"type": "tool_use", "id": "t1", "name": "Grep", "input": {"pattern": "quality"}}]}},
        {"type": "user", "uuid": "r1", "parentUuid": "a1", "timestamp": "2026-11-15T10:00:05Z",
         "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                                  "content": "squeeze/encode.py:12: QUALITY = 60"}]}},
        {"type": "assistant", "uuid": "a2", "parentUuid": "r1", "timestamp": "2026-11-15T10:00:09Z",
         "message": {"role": "assistant", "id": "m2", "usage": {"input_tokens": 1400, "output_tokens": 40},
                     "content": [{"type": "text", "text": "Quality is 60; raising it to 75 keeps every case under its size target."}]}},
    ]
    (d / "run" / "s.jsonl").write_text("".join(json.dumps(x) + "\n" for x in sess))
    p.events.add("session.started", item="session/developer-1a2b", source="developer", at=t,
                 data={"role": "developer", "model": "opus", "transcript": "file:run/s.jsonl"})
    assert tr.Ingester(p, p.model.spec).once() == 4
    p.events.add("session.ran", item="session/developer-1a2b", source="developer", data={"cost_usd": 0.31, "turns": 2})
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    shots = Path(os.environ["ERGOSTAT_SHOTS"]) if os.environ.get("ERGOSTAT_SHOTS") else None
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1400, "height": 1300})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/item/ticket%2F7")
        pg.wait_for_selector("table.fields tr[data-field=title] details.history", timeout=10000)
        assert "Thumbnails are blurry at quality 60" in pg.locator("table.fields tr[data-field=title] > td").first.inner_text()
        notes = pg.locator("tr[data-field=notes] details.history")
        assert notes.locator("summary").inner_text() == "history (4 changes)"
        notes.locator("summary").click()
        rows = notes.locator("table.history tr")
        assert rows.count() == 5                                           # the head and four changes, the latest first
        assert "add (append)" in rows.nth(1).inner_text() and "/notes/2" in rows.nth(1).inner_text()
        assert "raised it to 75" in rows.nth(1).inner_text() and "ticket.submitted" in rows.nth(1).inner_text()
        pg.locator("tr[data-field=hours] details.history summary").click()
        assert "(sum)" in pg.locator("tr[data-field=hours] table.history").inner_text()
        title = pg.locator("tr[data-field=title] details.history")
        title.locator("summary").click()
        assert "replace by patch" in title.inner_text()
        assert pg.locator("h2", has_text="Refused").count() == 1 and "test /title" in pg.locator("table.refused").inner_text()
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(shots / "item-history.png"), full_page=True)
        title.locator("table.history a", has_text="ticket.retitled").first.click()
        pg.wait_for_selector("#detail h2", timeout=5000)
        assert pg.locator("#detail h2").inner_text() == "ticket.retitled" and "/title" in pg.locator("#detail").inner_text()
        pg.goto(f"{url}/item/session%2Fdeveloper-1a2b")
        pg.wait_for_selector("tr[data-field=messages] table.sub", timeout=10000)
        msgs = pg.locator("tr[data-field=messages] > td").first.inner_text()
        assert "Raise the thumbnail quality" in msgs and "keeps every case under its size target" in msgs
        assert "Grep" in pg.locator("tr[data-field=tool_calls] > td").first.inner_text()
        assert "2,600" in pg.locator("tr[data-field=tokens_in] > td").first.inner_text() or \
            "2600" in pg.locator("tr[data-field=tokens_in] > td").first.inner_text()
        assert "4 more events are its transcript" in pg.locator("main").inner_text()
        pg.wait_for_selector(".convo .turn.tool", timeout=10000)                  # the file still shows the conversation
        if shots:
            pg.screenshot(path=str(shots / "session-folded.png"), full_page=True)
        assert not errors, errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)


LINE_LINKS = """async () => {
  // every line's panel: each part it names is a link, and the link opens that part's panel (also a
  // part inside a closed system, which only its system's port stands for)
  const bad = [];
  for (const e of S.graph.edges) {
    await openEdge(e);
    const links = [...document.querySelectorAll("#detail dl a")].filter((a) => !/^(the evidence|close)$/.test(a.textContent));
    const named = [...document.querySelectorAll("#detail dl b")].map((b) => b.textContent);
    if (named.length && e.kind !== "pipe") bad.push(`${e.id}: names ${named.join(", ")} without a link`);
    for (let i = 0; i < links.length; i++) {
      await openEdge(e);
      const a = [...document.querySelectorAll("#detail dl a")].filter((a) => !/^(the evidence|close)$/.test(a.textContent))[i];
      const want = a.textContent, before = document.querySelector("#detail h2")?.textContent;
      a.click();
      let now = null;                                       // wait for the panel to change (slow under load), up to 5s
      for (let t = 0; t < 50; t++) {
        await new Promise((r) => setTimeout(r, 100));
        now = document.querySelector("#detail h2")?.textContent;
        if (!document.querySelector("#detail").hidden && now && now !== before) break;
      }
      if (document.querySelector("#detail").hidden || !now || now === before) bad.push(`${e.id}: link ${want} opened nothing`);
    }
  }
  return bad;
}"""


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_lines_panel_links_to_the_parts_it_joins(browser, tmp_path, example):
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        drawn(pg, url, "", 0)                               # everything closed: lines end at systems' ports
        bad = pg.evaluate(LINE_LINKS)
        assert not bad, bad[:8]
        pg.close()


WHEEL = """([dx, dy, mods]) => {
  const svg = document.querySelector('svg.canvas'), r = svg.getBoundingClientRect();
  const cx = r.left + r.width * 0.6, cy = r.top + r.height * 0.4, before = { ...S.view };
  const ev = new WheelEvent('wheel', { deltaX: dx, deltaY: dy, deltaMode: 0, clientX: cx, clientY: cy,
                                       bubbles: true, cancelable: true, ...mods });
  svg.dispatchEvent(ev);
  const mx = cx - r.left, my = cy - r.top;   // the diagram point under the cursor, before and after
  return { before, after: { ...S.view }, prevented: ev.defaultPrevented,
           p0: [(mx - before.x) / before.k, (my - before.y) / before.k],
           p1: [(mx - S.view.x) / S.view.k, (my - S.view.y) / S.view.k] };
}"""


def test_scroll_pans_and_command_scroll_or_a_pinch_zooms_at_the_pointer(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=product", 0)
        r = pg.evaluate(WHEEL, [30, -20, {}])
        assert r["prevented"], "the page scrolled"
        assert r["after"]["k"] == r["before"]["k"]
        assert abs(r["after"]["x"] - (r["before"]["x"] - 30)) < 1e-6 and abs(r["after"]["y"] - (r["before"]["y"] + 20)) < 1e-6
        for mods, dy in (({"metaKey": True}, -40), ({"ctrlKey": True}, -8), ({"metaKey": True}, 60)):
            r = pg.evaluate(WHEEL, [0, dy, mods])
            assert r["prevented"], mods
            assert (r["after"]["k"] > r["before"]["k"]) == (dy < 0) and r["after"]["k"] != r["before"]["k"], (mods, r)
            p0, p1 = r["p0"], r["p1"]
            assert abs(p0[0] - p1[0]) * r["after"]["k"] < 2 and abs(p0[1] - p1[1]) * r["after"]["k"] < 2, (mods, r)
        for _ in range(60):
            r = pg.evaluate(WHEEL, [0, -500, {"ctrlKey": True}])
        assert r["after"]["k"] <= 4
        pg.get_by_role("button", name="+").click()
        pg.get_by_role("button", name="fit").click()
        pg.close()


WIRE_PANELS = """() => {
  const bad = [];
  for (const e of S.graph.edges) {
    openEdge(e);
    const kind = (document.querySelector('#detail .kind')?.textContent || '').toLowerCase();   // (in sentence case)
    if (!kind.startsWith('wire')) bad.push(`${e.id}: ${kind}`);
  }
  for (const n of S.graph.nodes) {
    openNode(n);
    const kind = (document.querySelector('#detail .kind')?.textContent || '').toLowerCase();   // (in sentence case)
    if (!kind.startsWith('machine')) bad.push(`${n.id}: ${kind}`);
  }
  const dashed = [...document.querySelectorAll('g.edge.wire')].filter((g) => g.dataset.id.startsWith('wire-unseen:')).length;
  return { bad, dashed, unseen: S.graph.edges.filter((e) => !e.seen).length, edges: S.graph.edges.length,
           nodes: document.querySelectorAll('svg.canvas g.node').length, want: S.graph.nodes.length };
}"""


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_wiring_view_draws_what_the_record_shows(browser, tmp_path, example):
    """The wiring of each example, with a record that shows half of what its model declares (and
    two machines it never names): drawn cleanly, the declared but unseen dashed, every panel opening."""
    from ergostat import graph
    from ergostat import model as mdl
    from ergostat.store import Project
    with served(example, tmp_path) as url:
        p = Project(mdl.load(tmp_path / example))
        for i, (a, b) in enumerate(sorted(graph.declared_wires(p.model))):
            if i % 2:
                continue
            sent = p.events.add("thing.sent", source=a)
            p.events.add("agent.started", item=b, source="ergostat", causedby=sent["id"])
        inv = p.events.add("invoice.sent", source="billing/1")
        p.events.add("mail.sent", source="mailer", causedby=inv["id"])
        time.sleep(1.6)                                   # past the page's snapshot of the moment it started
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=wiring", 0)
        r = pg.evaluate(AUDIT)
        problems = [f"{k}: {x}" for k in ("through", "overlap", "partOverlap") for x in r[k]]
        w = pg.evaluate(WIRE_PANELS)
        pg.close()
    assert not errors, errors
    assert not problems, f"{example}: " + "\n".join(problems)
    assert w["nodes"] == w["want"] and w["dashed"] == w["unseen"] and 0 < w["unseen"] < w["edges"], w
    assert not w["bad"], w["bad"][:8]


BLOCKS_DOM = """() => {
  // the control view's own conventions, as drawn: a function in every block, a sign at every input of
  // every summing junction, no placeholder, one ink (no fill on a block)
  const bad = [];
  for (const el of document.querySelectorAll("svg.canvas g.node.bd-block")) {
    if (!(el.dataset.fn || "").trim() || el.dataset.fn === "block") bad.push(`${el.dataset.id}: no function`);
    if (!el.querySelector("text")) bad.push(`${el.dataset.id}: nothing written in it`);
    const fill = getComputedStyle(el.querySelector(".hit")).fill;
    if (!/transparent|rgba\\(0, 0, 0, 0\\)|none/.test(fill)) bad.push(`${el.dataset.id}: filled ${fill}`);
  }
  for (const n of S.graph.nodes.filter((n) => n.kind === "sum")) {
    const signs = document.querySelectorAll(`svg.canvas text.bd-sign[data-sum="${CSS.escape(n.id)}"]`).length;
    if (signs !== n.ins.length) bad.push(`${n.id}: ${signs} signs for ${n.ins.length} inputs`);
  }
  if (/no valve|no sensor/.test(document.querySelector("svg.canvas").textContent)) bad.push("a placeholder");
  // Simulink's ports: every line crossing an open system's frame has a mark there, and none runs along a frame's edge
  const byLe = Object.fromEntries(S.layout.edges.map((le) => [le.id, le]));
  const marks = [...document.querySelectorAll("svg.canvas rect.bd-portmark")]
    .map((r) => [+r.getAttribute("x") + 4.5, +r.getAttribute("y") + 4.5]);
  for (const c of bdFrameCrossings(S.layout, S.graph, byLe))
    if (!marks.some(([x, y]) => Math.abs(x - c.x) < 1 && Math.abs(y - c.y) < 1))
      bad.push(`${c.edge.id}: crosses ${c.frame.id} with no port mark`);
  for (const le of S.layout.edges) { const p = bdPts(le);
    for (let i = 2; i < p.length - 1; i++) for (const f of S.layout.containers)
      if (bdOnFrame(p[i - 1], p[i], f)) bad.push(`${le.id}: runs along the edge of ${f.id}`); }
  const frames = Object.fromEntries((S.layout.containers || []).map((c) => [c.id, c]));
  for (const n of S.graph.nodes) for (const f of n.systems || []) {        // a part inside every frame it is in
    const c = S.layout.children.find((k) => k.id === n.id), o = frames[f];
    if (c && o && !(c.x >= o.x && c.y >= o.y && c.x + c.width <= o.x + o.width && c.y + c.height <= o.y + o.height))
      bad.push(`${n.id} outside ${f}`);
  }
  return bad;
}"""


# a feedback path runs back beneath the forward path by design (out of the process to the right, down, back
# left to the sensor and on to the junction): a line is a detour past twice its way plus that run back
BLOCKS_DETOUR = """() => {
  const out = [];
  for (const le of S.layout.edges) {
    const s0 = (le.sections || [])[0]; if (!s0) continue;
    const p = [s0.startPoint, ...(s0.bendPoints || []), s0.endPoint];
    const L = p.slice(1).reduce((s, q, i) => s + Math.abs(q.x - p[i].x) + Math.abs(q.y - p[i].y), 0);
    const M = Math.abs(p[0].x - p[p.length - 1].x) + Math.abs(p[0].y - p[p.length - 1].y);
    if (L > 2 * M + 240) out.push(`${le.id}: ${Math.round(L)} for ${Math.round(M)}`);
  }
  return out;
}"""


def blocks_views(tree: dict) -> list[str]:
    return ["view=blocks", "view=blocks&open=*", *(f"view=blocks&open={s}" for s in tree), *(f"view=blocks&system={s}" for s in tree)]


def test_the_control_view_draws_every_example_cleanly_as_a_block_diagram(browser, page_of):
    name, url = page_of
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    drawn(pg, url, "view=blocks", 0)
    problems = []
    for i, v in enumerate(blocks_views(pg.evaluate("() => S.graph.tree || {}"))):
        drawn(pg, url, v, i + 1)
        r = pg.evaluate(AUDIT)
        problems += [f"[{v}] {k}: {x}" for k in ("through", "overlap", "netCrossings", "partOverlap") for x in r[k]]
        problems += [f"[{v}] {x}" for x in pg.evaluate(BLOCKS_DOM)]
        problems += [f"[{v}] detour: {x}" for x in pg.evaluate(BLOCKS_DETOUR)]
        if max(r["size"]["aspect"], 1 / r["size"]["aspect"]) > MAX_ASPECT + 1 and r["size"]["fit"] < MIN_FIT:
            problems.append(f"[{v}] {r['size']}")
    pg.close()
    assert not errors, errors
    assert not problems, f"{name}: " + "\n".join(problems)


def test_the_control_view_nests_a_cascades_inner_loop_and_opens_a_blocks_definition(browser, tmp_path):
    from tests.test_spec_systems import MODEL
    d = tmp_path / "cascade"
    d.mkdir()
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=*", 0)
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["overlap"] and not r["partOverlap"], r
        assert pg.evaluate(BLOCKS_DOM) == []
        nest = pg.evaluate("""() => {
          const f = (id) => S.layout.containers.find((c) => c.id === id);
          const inner = f("casc:burner-rate"), heater = f("frame:heater");
          const el = document.querySelector('g.bd-frame-cascade[data-hull="casc:burner-rate"]');
          return { drawn: !!el, dashed: el && getComputedStyle(el.querySelector("rect")).strokeDasharray,
                   inside: inner.x >= heater.x && inner.x + inner.width <= heater.x + heater.width,
                   members: S.graph.nodes.filter((n) => n.parent === "casc:burner-rate").map((n) => n.id).sort() }; }""")
        assert nest["drawn"] and nest["dashed"] not in ("none", "") and nest["inside"], nest
        assert nest["members"] == ["blk:burner", "blk:watcher", "sum:burner-rate"], nest
        # a block clicked: its definition, as MathML
        pg.locator('g.node[data-id="blk:thermostat"] .hit').click()
        pg.wait_for_selector("#detail math", timeout=5000)
        mi = pg.evaluate("() => [...document.querySelectorAll('#detail .bd-math math mi')].map((x) => x.textContent)")
        assert "K" in mi and "p" in mi, mi                       # C_thermostat = K_p = 0.5
        assert not errors, errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)


SD_CHECK = """() => {
  // the system dynamics view as drawn: no sensor, controller or agent; every loop that shows here (two of its
  // parts drawn as themselves) has its marker; every connector whose polarity is known shows it at its head;
  // connectors are curves that cut through no part; and the drawing is in one ink (no fill or stroke in colour
  // but what is pointed at; the correspondence colours' rings are not drawn unless asked for)
  const bad = [], svg = document.querySelector("svg.canvas");
  if (!svg.classList.contains("sd")) bad.push("not drawn as the dynamics view");
  for (const n of S.graph.nodes) if (["sensor", "controller", "agent"].includes(n.kind)) bad.push(`drawn: ${n.kind} ${n.id}`);
  if (svg.querySelector(".badge, .k-sensor, .k-controller")) bad.push("an agent badge, a sensor or a controller is drawn");
  const marked = new Set([...svg.querySelectorAll(".loop-marker")].flatMap((m) => (m.dataset.loops || "").split("|")));
  for (const { loops } of sdLoopGroups(S.graph)) for (const c of loops) if (!marked.has(c.name)) bad.push(`no marker: ${c.name}`);
  for (const m of svg.querySelectorAll(".loop-marker")) {
    const c = S.graph.causalLoops.find((x) => x.name === m.dataset.loop);
    const t = m.querySelector(".marker-letter")?.textContent || "";
    if (!c || t[0] !== (c.polarity || "?")) bad.push(`marker ${m.dataset.loop} says ${t}`);
  }
  const box = S.layout.children;
  for (const e of S.graph.edges.filter((x) => x.kind === "connector")) {
    const eg = svg.querySelector(`.edge[data-id="${CSS.escape(e.id)}"]`);
    if (!eg) { bad.push(`not drawn: ${e.id}`); continue; }
    const sign = eg.querySelector("text.polarity")?.textContent;
    const want = { "+": "+", "-": "−" }[e.polarity];
    if (want !== sign) bad.push(`${e.id}: polarity ${e.polarity}, shows ${sign}`);
    const path = eg.querySelector("path.sd-connector"), len = path.getTotalLength();
    for (let d = 8; d < len - 8; d += 6) {
      const p = path.getPointAtLength(d);
      const hit = box.find((c) => c.id !== e.source && c.id !== e.target && !c.id.startsWith("cloud:") &&
        p.x > c.x + 4 && p.x < c.x + c.width - 4 && p.y > c.y + 4 && p.y < c.y + c.height - 4);
      if (hit) { bad.push(`${e.id} cuts through ${hit.id}`); break; }
    }
  }
  const grey = (c) => { const m = c.match(/\\d+(\\.\\d+)?/g); if (!m || m.length < 3) return true;
    const [r, g, b] = m.map(Number); return Math.max(r, g, b) - Math.min(r, g, b) < 24; };
  for (const el of svg.querySelectorAll(".node *, .edge *, .loop-marker *")) {
    const cs = getComputedStyle(el);
    if (cs.display === "none") continue;
    for (const v of [cs.fill, cs.stroke]) {
      if (v && v !== "none" && !v.startsWith("rgba(0,") && !grey(v)) { bad.push(`colour ${v}: ${el.getAttribute("class")}`); break; }
    }
    if (bad.length > 40) break;
  }
  return bad;
}"""


@pytest.mark.parametrize("example", ["image-squeeze", "software-factory", "deps"])
def test_the_dynamics_view_draws_only_system_dynamics_symbols_each_loop_marked_each_sign_shown(browser, tmp_path, example):
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        views = ["", "open=*", "view=control&open=*"]        # (view=control: its old name, the same view)
        views += {"image-squeeze": ["open=lab", "system=lab"], "software-factory": ["open=product"]}.get(example, [])
        for i, v in enumerate(views):
            drawn(pg, url, v, i)
            bad = pg.evaluate(SD_CHECK)
            assert not bad, (v, bad[:10])
        assert pg.locator(".toolbar .seg button.on").inner_text().lower() == "dynamics"
        assert not errors, errors
        pg.close()


def test_a_loop_marker_lights_its_loop_and_opens_its_panel(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="fit").click()
        pg.locator('.loop-marker[data-loop="backlog-clear"]').dispatch_event("click")
        pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail .what')", timeout=5000)
        assert pg.locator("#detail h2").inner_text().startswith("B")           # its label, R1 or B2, as Sterman numbers them
        assert pg.locator("#detail .subtitle").inner_text() == "backlog-clear"   # its name beneath
        assert "balancing" in pg.locator("#detail .kind").inner_text().lower()
        lit = pg.evaluate("""() => [...document.querySelectorAll('svg.canvas .node.in-loop')].map((n) => n.dataset.id).sort()""")
        assert lit == ["flow:submitted", "gap:backlog-clear", "stock:backlog"], lit
        assert pg.evaluate("() => document.querySelectorAll('svg.canvas .edge.in-loop').length") >= 3
        pg.close()


SD_WORDS = r"\b(controller|setpoint|rule|goal)s?\b|<=|>="   # (a valve is Sterman's word for where a rate is set)


def unsign_rollout(d: Path) -> None:
    """image-squeeze with the signs on what its rollout reads taken off: loops of unknown polarity again."""
    f = d / "rollout.yaml"
    f.write_text(f.read_text().replace("paired: +stock.paired", "paired: stock.paired")
                 .replace("saved: +auxiliary.bytes-saved", "saved: auxiliary.bytes-saved"))


def test_the_dynamics_view_speaks_system_dynamics_and_marks_only_loops_whose_sign_is_known(browser, tmp_path):
    import re
    with served("image-squeeze", tmp_path, unsign_rollout) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        r = pg.evaluate("""() => {
          const known = S.graph.causalLoops.filter((c) => c.polarity), unknown = S.graph.causalLoops.filter((c) => !c.polarity);
          const marks = [...document.querySelectorAll('svg.canvas .loop-marker')];
          const sizes = [...document.querySelectorAll('svg.canvas .marker-letter')].map((t) => getComputedStyle(t).fontSize);
          const sum = document.querySelector('details.sd-unknown summary')?.textContent || '';
          const hull = document.querySelector('svg.canvas .sys-hull rect:not(.hull-grip)');
          return { known: known.length, unknown: unknown.length, marked: marks.map((m) => m.dataset.loop),
                   unknownMarked: marks.filter((m) => !S.graph.causalLoops.find((c) => c.name === m.dataset.loop)?.polarity)
                     .length,
                   sizes: [...new Set(sizes)], sum,
                   hullStroke: hull && getComputedStyle(hull).stroke, hullFill: hull && getComputedStyle(hull).fill,
                   side: document.querySelector('#side, .side, aside')?.innerText || '' };
        }""")
        assert r["unknown"] > 0 and r["unknownMarked"] == 0 and r["marked"]
        assert r["sum"].startswith(f"+{r['unknown']} of unknown polarity"), r["sum"]
        assert r["sizes"] == ["11px"], r["sizes"]                               # every marker at full size, never 8.5px
        assert r["hullStroke"] in ("none", None) or "0)" in r["hullStroke"], r["hullStroke"]   # a sector: a tint, no outline
        assert r["hullFill"] not in ("none", "rgba(0, 0, 0, 0)"), r["hullFill"]
        assert not re.search(SD_WORDS, r["side"].split("How to read it")[0], re.I), r["side"][:600]
        # every panel: a loop's, a desired level's, a gap's, a connector's
        for sel in [".loop-marker", '.node[data-id^="desired:"]', '.node[data-id^="gap:"]']:
            pg.locator(f"svg.canvas {sel}").first.dispatch_event("click") if sel == ".loop-marker" else None
            if sel != ".loop-marker":
                el = pg.locator(f"svg.canvas {sel}").first
                pg.evaluate("(id) => openNode(S.graph.nodes.find((n) => n.id === id))", el.get_attribute("data-id"))
            pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail .what')", timeout=5000)
            pg.wait_for_timeout(300)
            text = pg.locator("#detail").inner_text()
            assert not re.search(SD_WORDS, text, re.I), (sel, text[:800])
        assert not errors, errors
        pg.close()


def test_a_module_says_as_many_loops_inside_as_the_side_list_and_draws_no_port_squares(browser, tmp_path):
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=-", 0)
        r = pg.evaluate("""() => {
          const caps = Object.fromEntries([...document.querySelectorAll('svg.canvas .node[data-id^="system:"]')].map((n) =>
            [n.dataset.id.slice(7), (n.querySelector('text.t-sub')?.textContent.match(/^(\\d+)/) || [])[1]]));
          const rows = Object.fromEntries([...document.querySelectorAll('.looprow.sd-inside')].map((r) =>
            [r.querySelector('b').textContent, (r.textContent.match(/: (\\d+) feedback/) || [])[1]]));
          const dup = [...document.querySelectorAll('svg.canvas .node[data-id^="system:"]')].some((n) => {
            const names = [...n.querySelectorAll('.sd-port-name')].map((t) => t.dataset.part + t.dataset.side);
            return new Set(names).size !== names.length; });
          return { caps, rows, squares: document.querySelectorAll('svg.canvas .sd-port').length, dup };
        }""")
        assert r["caps"] and r["caps"] == r["rows"], r
        assert r["squares"] == 0 and not r["dup"]
        pg.close()


def test_a_loop_marker_moves_with_its_system_when_the_system_is_dragged(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="fit").click()
        pg.wait_for_timeout(300)
        where = ("(n) => { const r = document.querySelector(`.loop-marker[data-loop=\"${n}\"]`).getBoundingClientRect(); "
                 "return [r.x, r.y]; }")
        before = pg.evaluate(where, "missing-ops")                          # inside product: missing-ops → asks … shipped
        grip = pg.locator('svg.canvas g.hull[data-hull="product"] rect.hull-grip').bounding_box()
        x, y = grip["x"] + 60, grip["y"] + 10
        pg.mouse.move(x, y)
        pg.mouse.down()
        for i in range(1, 11):
            pg.mouse.move(x + 12 * i, y + 8 * i)
        mid = pg.evaluate(where, "missing-ops")                             # during the drag it goes along
        assert mid[0] - before[0] > 60 and mid[1] - before[1] > 40, (before, mid)
        pg.mouse.up()
        pg.wait_for_timeout(500)
        after = pg.evaluate(where, "missing-ops")                           # and placed again where its loop now is
        assert after[0] - before[0] > 60 and after[1] - before[1] > 40, (before, after)
        pg.close()


def test_each_loop_marker_sits_inside_its_loop_as_drawn(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        for i, v in enumerate(["open=*", "system=delivery", "open=product"]):
            drawn(pg, url, v, i)
            r = pg.evaluate("""() => {
              const box = Object.fromEntries(S.layout.children.map((c) => [c.id, c])), out = [];
              for (const m of document.querySelectorAll('svg.canvas .loop-marker')) {
                const c = S.graph.causalLoops.find((x) => x.name === m.dataset.loop), { poly, members } = sdPolygon(c, S.graph, box);
                if (members.some((id) => id.startsWith('system:'))) continue;   // (through a closed module: its box fills the loop)
                let area = 0;
                for (let i = 0; i < poly.length; i++) { const p = poly[i], q = poly[(i + 1) % poly.length]; area += p.x * q.y - q.x * p.y; }
                if (poly.length >= 3 && Math.abs(area) > 400) out.push([c.name, sdInPolygon(+m.dataset.x, +m.dataset.y, poly)]);
              }
              return out;
            }""")
            outside = [n for n, ok in r if not ok]
            assert r and not outside, (v, outside)
        pg.close()


# ---- the Guide: every frame drawn by the real renderers, live and in a snapshot

GUIDE_FRAME = """(i) => { const d = document.querySelector('.g-deck'), c = d && d.querySelector('.g-count');
  return !!c && c.textContent.startsWith(`${i + 1} /`) && d.dataset.drawn === d.dataset.frame; }"""
GUIDE_SEEN = """() => { const d = document.querySelector('.g-deck'), all = (sel) => [...d.querySelectorAll(sel)];
  return { id: d.dataset.frame,
           svgs: all('svg.g-canvas').map((s) => [s.dataset.drawn || '', s.querySelectorAll('g.node').length]),
           markers: all('.loop-marker .marker-letter').map((t) => t.textContent).sort(),
           signs: all('text.polarity').map((t) => t.textContent),
           sums: all('.bd-sign').map((t) => t.textContent),
           plotted: all('svg.g-plot path.g-line').length }; }"""


def guide_port() -> int:
    """A free port in 8790-8799 (the range this repository's tests may use)."""
    for port in range(8790, 8800):
        with socket.socket() as s, contextlib.suppress(OSError):
            s.bind(("127.0.0.1", port))
            return port
    pytest.skip("no free port in 8790-8799")


def walk_guide(pg, url: str, shots: Path | None = None) -> dict:
    """Every frame, stepped with the arrow key: what each drew."""
    pg.goto(url)
    pg.wait_for_function(GUIDE_FRAME, arg=0, timeout=60000)
    n = pg.locator(".g-dot").count()
    seen = {}
    for i in range(n):
        if i:
            pg.keyboard.press("ArrowRight")
            pg.wait_for_function(GUIDE_FRAME, arg=i, timeout=60000)
        got = pg.evaluate(GUIDE_SEEN)
        seen[got["id"]] = got
        if shots:
            pg.screenshot(path=str(shots / f"{i + 1:02d}-{got['id']}.png"))
    return seen


def check_guide(seen: dict) -> None:
    assert len(seen) == 13, list(seen)
    for fid, got in seen.items():
        assert got["svgs"] and all(view and nodes for view, nodes in got["svgs"]), (fid, got["svgs"])
    assert len(seen["between"]["svgs"]) == 2 and len(seen["yours"]["svgs"]) == 2            # both ways, side by side
    assert [v for v, _ in seen["between"]["svgs"]] == ["dynamics", "blocks"]
    assert not seen["links"]["markers"] and "+" in seen["links"]["signs"]                    # a sign, before its loop
    assert seen["balancing"]["markers"] == ["B1"]
    assert seen["reinforcing"]["markers"] == ["B1", "R1"]
    assert seen["between"]["markers"] == ["B1"]
    assert {"+", "−"} <= set(seen["controller"]["sums"])                                    # e = r − y
    for fid in ("fills", "levels", "links", "balancing", "reinforcing", "closed", "disturbance"):
        assert seen[fid]["plotted"], fid
    assert seen["reinforcing"]["plotted"] == 2 and seen["closed"]["plotted"] == 2           # two runs; y and r


def test_the_guide_draws_every_frame_live_and_in_a_snapshot(browser, tmp_path, monkeypatch):
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.snapshot import build
    d = tmp_path / "first-loop"
    shutil.copytree(ROOT / "examples" / "first-loop", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    home = tmp_path / "home"
    shots = Path(os.environ["GUIDE_SHOTS"]) if os.environ.get("GUIDE_SHOTS") else None
    port = guide_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1400, "height": 800})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
        check_guide(walk_guide(pg, url + "/guide", shots))
        # the cascade's inner block opens on a click, and closes again
        pg.goto(url + "/guide?frame=11&v=1")
        pg.wait_for_function(GUIDE_FRAME, arg=11, timeout=60000)
        assert pg.locator("svg.g-canvas .bd-frame").count() == 0
        pg.locator("svg.g-canvas .bd-toggle").first.click()
        pg.wait_for_function("() => document.querySelectorAll('svg.g-canvas .bd-frame').length >= 2", timeout=30000)
        if shots:
            pg.screenshot(path=str(shots / "12b-cascade-opened.png"))
        pg.keyboard.press("ArrowLeft")                                       # back, by the other arrow
        pg.wait_for_function(GUIDE_FRAME, arg=10, timeout=60000)
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)
    # the snapshot: offline, nothing asked of a server
    monkeypatch.setenv("ERGOSTAT_HOME", str(home))
    out = tmp_path / "snapshot.html"
    out.write_text(build(Project(mdl.load(d))))
    pg = browser.new_page(viewport={"width": 1400, "height": 800})
    errors, asked = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:"))
             else (asked.append(rt.request.url), rt.abort()))
    check_guide(walk_guide(pg, f"file://{out}#/guide"))
    pg.close()
    assert not errors and not asked, (errors, asked)


def test_a_loop_lit_from_its_marker_lets_go_the_way_everything_else_does(browser, tmp_path):
    """The owner could not unselect a loop: clicking its marker again, the background, Escape, and the
    detail's close each let it go (no loop lit, nothing faded)."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="Fit").or_(pg.get_by_role("button", name="fit")).first.click()
        pg.wait_for_timeout(300)
        lit = "() => [S.hlCausal, document.querySelector('svg.canvas').classList.contains('loop-hl'), " \
              "document.querySelectorAll('svg.canvas .loop-marker.on, svg.canvas .node.dim').length]"
        marker = pg.locator('.loop-marker[data-loop="backlog-clear"]')

        def light():
            marker.dispatch_event("click")
            pg.wait_for_function("() => S.hlCausal === 'backlog-clear' && !document.querySelector('#detail').hidden", timeout=5000)
            assert pg.evaluate(lit)[1]

        def gone(how):
            pg.wait_for_function("() => !S.hlCausal", timeout=5000)
            assert pg.evaluate(lit) == [None, False, 0], how
        light()
        marker.dispatch_event("click")                                   # the marker again: a toggle
        gone("marker again")
        light()
        pg.keyboard.press("Escape")
        gone("Escape")
        light()
        pg.locator("#detail button.close").click()
        gone("the detail's close")
        light()
        box = pg.locator("svg.canvas").bounding_box()                    # the background, where nothing is drawn
        spot = pg.evaluate("""([x0, y0, w, h]) => {
            for (let y = y0 + 8; y < y0 + h; y += 12) for (let x = x0 + 8; x < x0 + w; x += 12) {
              const el = document.elementFromPoint(x, y);
              if (el && el.closest('svg.canvas') && !el.closest('.node, .edge, .loop-marker, [data-act], .hull')) return [x, y];
            }
            return null; }""",
                           [box["x"], box["y"], box["width"], box["height"]])
        assert spot
        pg.mouse.click(*spot)
        gone("the background")
        pg.close()


CHARTED = """
name: charted
items:
  ticket:
    id: ticket/*
    states: [open, doing, done]
    on:
      ticket.started: doing
      ticket.done: done
stocks:
  backlog:
    unit: tickets
    sensor:
      manual: true
flows:
  arriving:
    to: backlog
    sensor:
      manual: true
  finishing:
    from: backlog
auxiliaries:
  pressure:
    unit: share
    driven-by: +stock.backlog
    sensor:
      manual: true
goals:
  short-backlog:
    stock: backlog
    hold: "<= 5"
    tolerance: 1
blocks:
  worker:
    type: program
    run: echo 1
    goal: short-backlog
    max: 3
    out: flow.finishing
"""
CHARTS = "() => [...document.querySelectorAll('{0} .chart-plot canvas')].length"
CURSORS = "() => [...document.querySelectorAll('{0} .u-cursor-x:not(.u-off)')].length"


def charted(tmp_path: Path, monkeypatch) -> Path:
    """A small project with forty minutes of record: readings, valve openings, a loop off and back, items moving."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "charted"
    d.mkdir()
    (d / "ergostat.yaml").write_text(CHARTED)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))       # the server is given it too
    p = Project(mdl.load(d))
    now = time.time()
    for i in range(240):
        t = now - 2400 + i * 10
        p.measurements.add("sensor/backlog.main", 4 + 3 * math.sin(i / 30), at=t)
        p.measurements.add("sensor/arriving.main", 6 + 2 * math.cos(i / 25), at=t)
        p.measurements.add("sensor/pressure.main", 0.5 + 0.3 * math.sin(i / 30), at=t)
        if i % 6 == 0:
            p.events.add("valve.opened", item="worker", data={"amount": 1 + i % 3, "flow": "finishing"}, at=t)
    p.events.add("loop.off", item="short-backlog", data={"value": 7}, at=now - 2000)
    p.events.add("loop.holding", item="short-backlog", data={"value": 5}, at=now - 1500)
    for n in range(12):
        p.events.add("ticket.opened", item=f"ticket/{n}", at=now - 2300 + n * 150)
        if n < 9:
            p.events.add("ticket.started", item=f"ticket/{n}", at=now - 2200 + n * 160)
        if n < 6:
            p.events.add("ticket.done", item=f"ticket/{n}", at=now - 1900 + n * 200)
    return d


def test_charts_draw_beside_the_model_with_one_cursor_and_in_a_snapshot(browser, tmp_path, monkeypatch):
    """Clicking a stock draws its causes strip (it, its inflow and its outflow), a flow and an auxiliary
    theirs; parts chosen chart in the side panel; a loop's comparator and the Loops page's sparkline
    open its scope (y, u, e); the Items page draws each kind's flow and cycle times. Hovering one
    chart moves the cursor on every chart beside it. A snapshot, opened from a file with nothing
    else reachable, draws the same."""
    d = charted(tmp_path, monkeypatch)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"

    def hover_all(pg, where):
        box = pg.locator(f"{where} .chart-plot").first.bounding_box()
        pg.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.5)
        pg.wait_for_timeout(200)
        return pg.evaluate(CHARTS.format(where)), pg.evaluate(CURSORS.format(where))

    def opened(pg, js, where, n):
        pg.evaluate(js)
        pg.wait_for_function(f"() => ({CHARTS.format(where)})() >= {n}", timeout=20000)
        pg.wait_for_timeout(300)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        # a stock, clicked: it, its inflow, its outflow; one cursor across them
        hit = pg.locator('g.node[data-id="stock:backlog"] .hit').first.bounding_box()
        pg.mouse.click(hit["x"] + hit["width"] / 2, hit["y"] + hit["height"] / 2)
        pg.wait_for_function(f"() => ({CHARTS.format('#detail')})() >= 3", timeout=20000)
        names = pg.evaluate("() => [...document.querySelectorAll('#detail .chart-name')].map((x) => x.textContent)")
        assert names == ["value", "arriving", "finishing"], names
        first = "(el) => el.compareDocumentPosition(document.querySelector('#detail dl')) & 4"
        assert pg.locator("#detail .chart").first.evaluate(first), "the charts come first, what it is after"
        charts, cursors = hover_all(pg, "#detail")
        assert cursors == charts == 3 and pg.locator("#detail .chart-when").inner_text(), (charts, cursors)
        # a flow (its rate, the stock it drains) and an auxiliary (its value, what drives it)
        opened(pg, "() => openNode(S.graph.nodes.find((n) => n.id === 'flow:finishing'))", "#detail", 2)
        assert "opened by worker" in pg.locator("#detail .chart-head").first.inner_text()
        opened(pg, "() => openNode(S.graph.nodes.find((n) => n.id === 'stock:pressure'))", "#detail", 2)
        assert hover_all(pg, "#detail") == (2, 2)
        # parts chosen: each one's strip in the side panel, on one time axis; nothing chosen: the user's charts
        pg.evaluate("() => closeDetail()")
        opened(pg, "() => { S.sel = new Set(['stock.backlog', 'flow.arriving']); markInteraction(document.querySelector('svg.canvas')); }",
               ".side .side-charts", 5)
        charts, cursors = hover_all(pg, ".side .side-charts")
        assert charts == cursors == 5, (charts, cursors)
        pg.evaluate("() => { S.sel.clear(); markInteraction(document.querySelector('svg.canvas')); }")
        pg.wait_for_function("() => document.querySelector('.side .side-charts h3')?.textContent === 'Your charts'", timeout=20000)
        # the blocks view: the loop's comparator opens its scope
        drawn(pg, url, "view=blocks", 1)
        opened(pg, "() => openBlock(S.graph.nodes.find((n) => n.role === 'comparator'))", "#detail .scope", 3)
        names = pg.evaluate("() => [...document.querySelectorAll('#detail .scope .chart-name')].map((x) => x.textContent)")
        assert names == ["y", "u", "e"], names
        assert hover_all(pg, "#detail .scope") == (3, 3)
        assert "Saturated" in pg.locator("#detail .scope dl").inner_text()
        # the Loops page: the sparkline opens the same scope
        pg.goto(url + "/loops")
        pg.locator("td.spark-cell").first.click()
        pg.wait_for_function(f"() => ({CHARTS.format('#detail .scope')})() >= 3", timeout=20000)
        # the Items page: the kind's flow, and under its table its cycle times
        pg.goto(url + "/items")
        pg.wait_for_function(f"() => ({CHARTS.format('.cfd')})() >= 1 && ({CHARTS.format('.chart.cycle')})() >= 1", timeout=20000)
        states = pg.evaluate("() => [...document.querySelectorAll('.cfd-states .stbox')].map((x) => x.textContent)")
        assert states == ["3open", "3doing", "6done"], states
        assert hover_all(pg, ".page") == (2, 2)
        pg.locator(".cfd-states .stbox", has_text="doing").click()        # a state's label filters the table, as its count did
        pg.wait_for_function("() => location.search.includes('state=doing')", timeout=5000)
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)
    # the snapshot: the same charts, from the file, with nothing reachable
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.snapshot import build
    out = tmp_path / "snapshot.html"
    out.write_text(build(Project(mdl.load(d)), since="1h"))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors, asked = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:"))
             else (asked.append(rt.request.url), rt.abort()))
    pg.goto(f"file://{out}#/diagram")
    pg.wait_for_function("() => typeof uPlot === 'function' && S.graph && document.querySelectorAll('svg.canvas g.node').length",
                         timeout=60000)
    for js, where, n in (("() => openNode(S.graph.nodes.find((n) => n.id === 'stock:backlog'))", "#detail", 3),
                         ("() => openLoop('short-backlog')", "#detail .scope", 3)):
        pg.evaluate(js)
        pg.wait_for_function(f"() => ({CHARTS.format(where)})() >= {n}", timeout=20000)
    pg.goto(f"file://{out}#/items")
    pg.wait_for_function(f"() => ({CHARTS.format('.cfd')})() >= 1", timeout=20000)
    pg.close()
    assert not errors and not asked, (errors, asked)


def test_the_loop_markers_can_be_hidden_and_it_is_remembered(browser, tmp_path):
    """They help and they clutter: the ⋯ menu hides them; a reload keeps them hidden; it shows them again."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        drawn(pg, url, "open=*", 0)
        js = "() => [...document.querySelectorAll('.loop-markers')].some((g) => g.getBoundingClientRect().width > 0)"
        shown = lambda: pg.evaluate(js)  # noqa: E731
        assert shown()
        pg.get_by_title("More: wrap, open or close every system, unpin").click()
        pg.get_by_text("Show loop markers").click()
        assert not shown()
        drawn(pg, url, "open=*", 1)
        assert not shown(), "hidden after a reload"
        pg.get_by_title("More: wrap, open or close every system, unpin").click()
        pg.get_by_text("Show loop markers").click()
        assert shown()
        pg.close()


def test_a_closed_systems_panel_charts_its_measures(browser, tmp_path):
    """What a closed system's box used to draw as sparklines is charted in its panel: its show: measures."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)                                  # everything closed: each system a module
        got = pg.evaluate("""async () => {
          const n = S.graph.nodes.find((x) => x.kind === "system" && x.label === "benchmark");
          await openNode(n);
          await new Promise((r) => setTimeout(r, 1500));
          return { measures: (n.charted || n.measures || []).length, strip: !!document.querySelector("#detail .strip"),
                   text: document.querySelector("#detail .strip")?.textContent || "" };
        }""")
        assert got["measures"] > 0 and got["strip"], got
        assert "…" != got["text"].strip(), got                 # it answered: charts, or "nothing measured"


def test_a_valve_says_its_rate_inputs_and_equation_and_its_pipe_what_moves(browser, tmp_path):
    """Clicking a flow's valve (the bowtie) opens the valve: the rate of the flow, its inputs (the
    connectors into it, each signed) and its equation, or what of it is not known yet; clicking its
    pipe opens the flow: what moves, from where, to where."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="fit").click()
        box = pg.locator('g.node[data-id="flow:regressions"] .hit').first.bounding_box()
        pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pg.wait_for_function("() => document.querySelector('#detail .kind')?.textContent === 'Valve'", timeout=5000)
        text = pg.locator("#detail").inner_text()
        assert "the rate of regressions" in text, text[:600]
        inputs = pg.evaluate("""() => { const dt = [...document.querySelectorAll('#detail dt')].find((d) => d.textContent === 'inputs');
                                        return dt ? dt.nextElementSibling.textContent : null; }""")
        assert inputs and "deployed (+)" in inputs and "ops-broken-per-ticket (+)" in inputs, inputs
        pg.wait_for_function("() => document.querySelector('#detail math.eq')", timeout=5000)     # its equation, written
        assert pg.evaluate("() => [...document.querySelectorAll('#detail math.eq mi')].map((x) => x.textContent)") == \
            ["regressions", "ops-broken-per-ticket", "deployed"]
        assert "What is a valve?" in text
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'flow:asks'))")             # and one with none
        pg.wait_for_function("() => /the rate of asks/.test(document.querySelector('#detail').textContent)", timeout=5000)
        pg.wait_for_timeout(300)
        assert "not known yet: a declared cause with a sign, its size not estimated" in pg.locator("#detail").inner_text()
        pg.evaluate("() => openEdge(S.graph.edges.find((e) => e.kind === 'pipe' && e.flow === 'regressions'))")
        pg.wait_for_function("() => document.querySelector('#detail .kind')?.textContent === 'Flow'", timeout=5000)
        pg.wait_for_timeout(300)
        text = pg.locator("#detail").inner_text()
        assert "what moves" in text.lower() and "ops" in text and "bugs-live" in text and "a source outside the model" in text, text[:600]
        assert "What is a flow?" in text
        assert not errors, errors
        pg.close()


# ---- two views at once: one selection of model parts, lit in both (correspond.py, interact.js, split.js)

SHOTS = Path(os.environ.get("SPLIT_SHOTS", str(ROOT.parent / "split-shots")))
LIT = "() => [...document.querySelectorAll('svg.canvas g.node.selected')].map((e) => e.dataset.id).sort()"
PANE_READY = "() => typeof S !== 'undefined' && S.layout && S.graphSig && document.querySelectorAll('svg.canvas g.node').length > 0"


def pane_of(pg):
    """The second pane's frame, drawn."""
    for _ in range(100):
        fr = next((f for f in pg.frames if "pane=1" in f.url), None)
        if fr is not None:
            break
        pg.wait_for_timeout(100)
    assert fr is not None, "no second pane"
    fr.wait_for_function(PANE_READY, timeout=60000)
    return fr


def drag(pg, x0, y0, x1, y1, steps=12):
    pg.mouse.move(x0, y0)
    pg.mouse.down()
    for i in range(1, steps + 1):
        pg.mouse.move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
    pg.mouse.up()
    pg.wait_for_timeout(200)


def split_state(pg) -> dict:
    return pg.evaluate("""() => { const r = document.querySelector('.split-pane')?.getBoundingClientRect();
      return { on: document.body.classList.contains('split-on'), edge: SPLIT.edge, open: SPLIT.open, frac: SPLIT.frac,
               pane: r && !document.querySelector('.split-pane').hidden ? [r.left, r.top, r.width, r.height] : null,
               main: (() => { const m = document.querySelector('svg.canvas').getBoundingClientRect();
                              return [m.left, m.top, m.width, m.height]; })(),
               saved: JSON.parse(localStorage.getItem('ergostat.split') || 'null') }; }""")


def open_split(pg, edge="right", frac=0.5):
    """The split opened by dragging the edge's grip inward to ``frac`` of the way."""
    g = pg.locator(f'.split-grip[data-edge="{edge}"]').bounding_box()
    x, y = g["x"] + g["width"] / 2, g["y"] + g["height"] / 2
    W, H = pg.viewport_size["width"], pg.viewport_size["height"]
    top = pg.evaluate("() => document.querySelector('header.bar').getBoundingClientRect().bottom")
    to = {"right": (W * (1 - frac), y), "left": (W * frac, y), "top": (x, top + (H - top) * frac),
          "bottom": (x, H - (H - top) * frac)}[edge]
    drag(pg, x, y, *to)
    return pane_of(pg)


def click_part(pg, nid: str) -> None:
    """A part of the canvas clicked where nothing is drawn over it (its title may be)."""
    pt = pg.evaluate("""(id) => { const r = document.querySelector(`g.node[data-id="${id}"] .hit`).getBoundingClientRect();
      for (let y = r.top + 2; y < r.bottom; y += 3) for (let x = r.left + 2; x < r.right; x += 3) {
        const el = document.elementFromPoint(x, y); if (el && el.closest('g.node')?.dataset.id === id) return [x, y]; }
      return [r.left + r.width / 2, r.top + r.height / 2]; }""", nid)
    pg.mouse.click(*pt)


LOOK_AT_CHOSEN = """() => {
  // the view moved to what is chosen, at a size to read it (for the pictures)
  const ids = new Set([...document.querySelectorAll('svg.canvas g.node.selected')].map((e) => e.dataset.id));
  const cs = S.layout.children.filter((c) => ids.has(c.id)), svg = document.querySelector('svg.canvas');
  const r = svg.getBoundingClientRect();
  const x0 = Math.min(...cs.map((c) => c.x)), y0 = Math.min(...cs.map((c) => c.y));
  const x1 = Math.max(...cs.map((c) => c.x + c.width)), y1 = Math.max(...cs.map((c) => c.y + c.height));
  const k = Math.max(0.5, Math.min(1.2, (r.width - 160) / (x1 - x0 + 1), (r.height - 200) / (y1 - y0 + 1)));
  S.view = { k, x: r.width / 2 - ((x0 + x1) / 2) * k, y: r.height / 2 + 20 - ((y0 + y1) / 2) * k };
  applyView(svg);
}"""


def fit(page_or_frame):
    page_or_frame.get_by_role("button", name="Fit", exact=True).click()
    page_or_frame.wait_for_timeout(150)


def test_a_selection_is_model_parts_and_survives_switching_view(browser, tmp_path):
    """A part chosen in the dynamics view is chosen in the block diagram after switching: the same parts,
    lit there by the shapes that are them (a stock: its integrator and its output y)."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        fit(pg)
        click_part(pg, "stock:capabilities")
        pg.wait_for_function("() => S.sel.size > 0", timeout=5000)
        assert pg.evaluate("() => [...S.sel]") == ["stock.capabilities"]
        assert pg.evaluate(LIT) == ["stock:capabilities"]
        pg.locator(".toolbar .seg button", has_text="Blocks").click()
        pg.wait_for_function("() => S.graph?.kind === 'blocks' && document.querySelectorAll('svg.canvas g.node.selected').length > 0",
                             timeout=60000)
        assert pg.evaluate("() => [...S.sel]") == ["stock.capabilities"]
        assert pg.evaluate(LIT) == ["out:stock.capabilities", "proc:stock.capabilities"]
        # Shift adds and takes away, in the block diagram too; the background lets everything go
        fit(pg)
        pg.keyboard.down("Shift")
        pg.locator('g.node[data-id="ref:every-case"]').click()
        pg.keyboard.up("Shift")
        assert set(pg.evaluate("() => [...S.sel]")) == {"stock.capabilities", "goal.every-case.r"}
        pg.keyboard.down("Shift")
        pg.locator('g.node[data-id="ref:every-case"]').click()
        pg.keyboard.up("Shift")
        assert pg.evaluate("() => [...S.sel]") == ["stock.capabilities"]
        pg.keyboard.press("Escape")
        assert pg.evaluate("() => S.sel.size") == 0 and pg.evaluate(LIT) == []
        assert not errors, errors
        pg.close()


def test_a_summing_junction_chosen_in_blocks_lights_its_stock_and_flows_in_the_dynamics_pane(browser, tmp_path):
    """With the split open (dynamics here, the block diagram in the second pane), a stock's summing
    junction chosen in blocks lights, in the dynamics pane, the stock and its flows: three shapes of
    some hundred, not everything it touches; its panel opens over the pane clicked in only. Hovering a
    shape lights what it is in the other pane, lightly, and chooses nothing."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pane = open_split(pg, "right")
        assert pane.evaluate("() => S.graph.kind") == "blocks"
        fit(pg)
        fit(pane)
        pane.locator('g.node[data-id="psum:stock.capabilities"]').dispatch_event("click")   # (the zoom may cover it)
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.selected').length === 3", timeout=5000)
        assert pg.evaluate(LIT) == ["flow:gained", "flow:lost", "stock:capabilities"]
        total = pg.evaluate("() => document.querySelectorAll('svg.canvas g.node').length")
        assert total > 60
        assert set(pane.evaluate("() => [...S.sel]")) == {"stock.capabilities", "flow.gained", "flow.lost"}
        assert "psum:stock.capabilities" in pane.evaluate(LIT)
        assert not pane.evaluate("() => document.querySelector('#detail').hidden")          # its panel, over its pane
        assert pg.evaluate("() => document.querySelector('#detail').hidden")
        # a turnover chosen in dynamics: in blocks, the process holding it, dashed, and its panel says so
        fit(pg)
        click_part(pg, "flow:quality-turnover")
        pane.wait_for_function("() => document.querySelector('svg.canvas g.node.selected.within')", timeout=5000)
        assert pane.evaluate(LIT) == ["proc:service"]
        assert pane.evaluate("() => document.querySelector('#detail').hidden")             # the other pane's panel let go
        pg.wait_for_function("() => document.querySelector('#detail .where-else')", timeout=10000)
        assert "inside P" in pg.locator("#detail .where-else").inner_text()
        # pointing at a shape: what it is, lightly, over there; nothing chosen
        pg.keyboard.press("Escape")
        pane.wait_for_function("() => S.sel.size === 0", timeout=5000)
        pg.locator('g.node[data-id="stock:capabilities"]').hover(position={"x": 4, "y": 4})
        pane.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.xhover').length > 0", timeout=5000)
        assert pane.evaluate("() => [...document.querySelectorAll('svg.canvas g.node.xhover')].map((e) => e.dataset.id).sort()") == \
            ["out:stock.capabilities", "proc:stock.capabilities"]
        assert pane.evaluate("() => S.sel.size") == 0 and pg.evaluate("() => S.sel.size") == 0
        pg.mouse.move(2, 400)
        pane.wait_for_function("() => !document.querySelector('svg.canvas .xhover')", timeout=5000)
        pane.locator('g.node[data-id="sum:every-case"]').hover()
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.xhover').length === 2", timeout=5000)
        assert pg.evaluate("() => [...document.querySelectorAll('svg.canvas g.node.xhover')].map((e) => e.dataset.id).sort()") == \
            ["desired:every-case", "gap:every-case"]
        assert not errors, errors
        pg.close()


def test_the_split_opens_from_each_edge_resizes_halves_and_closes_at_the_edge(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        W, H = 1440, 900
        for edge in ("right", "left", "top", "bottom"):
            open_split(pg, edge, 0.35)
            st = split_state(pg)
            assert st["on"] and st["edge"] == edge and st["saved"]["open"], st
            assert abs(st["frac"] - 0.35) < 0.03, st
            pane, main = st["pane"], st["main"]
            horiz = edge in ("left", "right")
            assert (pane[0] >= main[0] + main[2] - 1) if edge == "right" else (pane[0] + pane[2] <= main[0] + 1) if edge == "left" else \
                (pane[1] + pane[3] <= main[1] + 1) if edge == "top" else (pane[1] >= main[1] + main[3] - 1), (edge, st)
            # the separator dragged: the pane follows
            sep = pg.locator(".split-sep").bounding_box()
            sx, sy = sep["x"] + sep["width"] / 2, sep["y"] + sep["height"] / 2
            to = {"right": (W * 0.4, sy), "left": (W * 0.6, sy), "top": (sx, 120 + (H - 120) * 0.6), "bottom": (sx, H * 0.4)}[edge]
            drag(pg, sx, sy, *to)
            st2 = split_state(pg)
            assert st2["frac"] > 0.5, (edge, st2)
            # double-click: half and half
            sep = pg.locator(".split-sep").bounding_box()
            pg.mouse.dblclick(sep["x"] + sep["width"] / 2, sep["y"] + sep["height"] / 2)
            pg.wait_for_timeout(150)
            st3 = split_state(pg)
            k = 2 if horiz else 3
            assert abs(st3["frac"] - 0.5) < 1e-6 and abs(st3["pane"][k] - st3["main"][k]) < 30, st3
            # remembered: a reload opens it again, on its edge, at its size
            pg.reload()
            pg.wait_for_function(READY, timeout=60000)
            st4 = split_state(pg)
            assert st4["on"] and st4["edge"] == edge and abs(st4["frac"] - 0.5) < 1e-6, st4
            pane_of(pg)
            # dragged back to its edge: closed
            sep = pg.locator(".split-sep").bounding_box()
            sx, sy = sep["x"] + sep["width"] / 2, sep["y"] + sep["height"] / 2
            to = {"right": (W - 3, sy), "left": (3, sy), "top": (sx, 60), "bottom": (sx, H - 3)}[edge]
            drag(pg, sx, sy, *to)
            st5 = split_state(pg)
            assert not st5["on"] and not st5["open"] and not st5["saved"]["open"] and st5["pane"] is None, st5
            assert st5["main"][2] > W - 400, st5                        # the canvas has its room back
        # on a phone, no split, whatever was remembered
        open_split(pg, "right", 0.4)
        pg.set_viewport_size({"width": 400, "height": 800})
        pg.wait_for_timeout(300)
        assert not split_state(pg)["on"] and pg.locator(".split-grip").first.is_hidden()
        assert not errors, errors
        pg.close()


def test_with_the_split_open_the_side_panel_slides_over_the_pane_clicked_in(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pane = open_split(pg, "right", 0.5)
        main = split_state(pg)["main"]
        assert main[2] > 650, main                                       # the side panel gives its column up
        assert pg.locator(".diagram > .side").is_hidden()
        fit(pg)
        click_part(pg, "stock:backlog")
        pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail h2')", timeout=5000)
        pg.wait_for_timeout(300)                                         # (it slides in)
        d = pg.locator("#detail").bounding_box()
        assert d["x"] >= main[0] - 1 and d["x"] + d["width"] <= main[0] + main[2] + 1, (d, main)   # over the main pane only
        assert d["width"] <= 0.9 * main[2] + 1
        assert split_state(pg)["main"] == main                          # nothing moved
        pg.locator("#detail button.close").click()
        assert pg.locator("#detail").is_hidden()
        click_part(pg, "stock:backlog")
        pg.wait_for_function("() => !document.querySelector('#detail').hidden", timeout=5000)
        pg.keyboard.press("Escape")
        assert pg.locator("#detail").is_hidden()
        # in the second pane: its own panel, over it
        fit(pane)
        pane.locator('g.node[data-id="sum:backlog-clear"]').click()
        pane.wait_for_function("() => !document.querySelector('#detail').hidden", timeout=5000)
        pane.wait_for_timeout(300)
        pd = pane.evaluate("() => { const r = document.querySelector('#detail').getBoundingClientRect(); "
                           "return [r.left, r.width, innerWidth]; }")
        assert pd[0] + pd[1] <= pd[2] + 1 and pd[1] < pd[2], pd
        assert pg.locator("#detail").is_hidden()
        pane.locator("#detail button.close").click()
        assert pane.locator("#detail").is_hidden()
        # the background clicked: first what is chosen lets go; then the side panel (its loops) over the pane; again: gone
        box = pg.locator("svg.canvas").bounding_box()
        assert pg.evaluate("() => S.sel.size") > 0
        pg.mouse.click(box["x"] + box["width"] - 30, box["y"] + box["height"] / 2)
        assert pg.evaluate("() => S.sel.size") == 0 and pg.locator(".diagram > .side").is_hidden()
        pg.mouse.click(box["x"] + box["width"] - 30, box["y"] + box["height"] / 2)
        assert pg.locator(".diagram > .side").is_visible()
        pg.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2 + 60)
        assert pg.locator(".diagram > .side").is_hidden()
        assert not errors, errors
        pg.close()


def test_a_loop_clicked_chooses_its_members_in_both_panes_and_the_split_is_pictured(browser, tmp_path):
    """A feedback loop's marker clicked in the dynamics pane chooses its members, lit in the block
    diagram pane too; and the pictures of the split (side by side, stacked) with a choice lit in both."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pane = open_split(pg, "right", 0.5)
        fit(pg)
        fit(pane)
        pg.locator('.loop-marker[data-loop="backlog-clear"]').dispatch_event("click")
        pg.wait_for_function("() => S.sel.size > 2", timeout=5000)
        members = set(pg.evaluate("() => [...S.sel]"))
        assert {"stock.backlog", "goal.backlog-clear"} <= members, members
        pane.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.selected').length > 1", timeout=5000)
        assert set(pane.evaluate("() => [...S.sel]")) == members
        lit_there = pane.evaluate(LIT)
        assert "sum:backlog-clear" in lit_there and "proc:stock.backlog" in lit_there, lit_there
        # the pictures: a stock's summing junction chosen in the block diagram, side by side; a loop, stacked
        pg.keyboard.press("Escape")
        SHOTS.mkdir(parents=True, exist_ok=True)
        pane.locator('g.node[data-id="psum:stock.in-review"]').click()
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.selected').length >= 4", timeout=5000)
        assert pg.evaluate(LIT) == ["flow:merged", "flow:rejected", "flow:submitted", "stock:in-review"]
        pane.locator("#detail button.close").click()
        for x in (pg, pane):
            x.evaluate(LOOK_AT_CHOSEN)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(SHOTS / "split-side-by-side.png"))
        sep = pg.locator(".split-sep").bounding_box()
        drag(pg, sep["x"] + 3, sep["y"] + sep["height"] / 2, 1437, sep["y"] + sep["height"] / 2)
        assert not split_state(pg)["on"]
        pane = open_split(pg, "bottom", 0.5)
        pg.locator('.loop-marker[data-loop="backlog-clear"]').dispatch_event("click")
        pane.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.selected').length >= 3", timeout=5000)
        pg.locator("#detail button.close").click()
        for x in (pg, pane):
            x.evaluate(LOOK_AT_CHOSEN)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(SHOTS / "split-stacked.png"))
        assert not errors, errors
        pg.close()

# ---- colour by correspondence (colours.js): each part ringed in its group's colour, on demand; and what is
# pointed at in one pane found at a glance in the other

RINGS = """(id) => [...(document.querySelector(`svg.canvas g.node[data-id="${id}"]`)?.querySelectorAll('.corr-ring') || [])]
  .map((r) => { const cs = getComputedStyle(r); return { display: cs.display, stroke: cs.stroke, width: parseFloat(cs.strokeWidth),
                                                         dash: cs.strokeDasharray }; })"""
SHOWN = ("(id) => [...document.querySelectorAll(`svg.canvas g.node[data-id=\"${id}\"] .corr-ring`)]"
         ".some((r) => getComputedStyle(r).display !== 'none')")
ACCENT = "() => { const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect'); r.style.stroke = 'var(--accent)'; " \
         "document.querySelector('svg.canvas').append(r); const c = getComputedStyle(r).stroke; r.remove(); return c; }"


def toggle_colours(pg):
    pg.get_by_title("More: wrap, open or close every system, unpin").click()
    pg.get_by_text("Colour by correspondence").click()


def test_colour_by_correspondence_rings_matching_parts_alike_in_both_panes_and_is_remembered(browser, tmp_path):
    """Off at first. The ⋯ menu's toggle rings every part in both panes in its group's colour: a stock in
    the dynamics view and its integrator and output y in the block diagram alike, its flow otherwise; a
    controller, which is its block and the valves it moves, in segments of several; a closed system's
    box in its system's colour, as its outline is when open. A reload keeps it; the toggle again hides it."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pane = open_split(pg, "right")
        assert not pg.evaluate(SHOWN, "stock:capabilities") and not pane.evaluate(SHOWN, "out:stock.capabilities")
        toggle_colours(pg)
        pane.wait_for_function("() => document.body.classList.contains('corr-on')", timeout=5000)
        stock = pg.evaluate(RINGS, "stock:capabilities")
        assert len(stock) == 1 and stock[0]["display"] != "none" and stock[0]["width"] >= 3, stock
        for there in ("out:stock.capabilities", "proc:stock.capabilities"):
            rings = pane.evaluate(RINGS, there)
            assert [r["stroke"] for r in rings] == [stock[0]["stroke"]], (there, rings, stock)
        gained = pg.evaluate(RINGS, "flow:gained")
        assert gained and gained[0]["stroke"] != stock[0]["stroke"]
        # every part drawn in either pane ringed, and many colours among them
        for x in (pg, pane):
            left = x.evaluate("""() => [...document.querySelectorAll('svg.canvas g.node')].filter((n) =>
                (S.graph.corr.shapes[n.dataset.id]?.is || []).length && !S.graph.corr.shapes[n.dataset.id].aside &&
                ![...n.querySelectorAll('.corr-ring')].some((r) => getComputedStyle(r).display !== 'none')).map((n) => n.dataset.id)""")
            assert not left, left
            hues = x.evaluate("() => new Set([...document.querySelectorAll('svg.canvas .corr-ring')]"
                              ".map((r) => getComputedStyle(r).stroke)).size")
            assert hues >= 15, hues
        # a controller: its block and its valves, a segment of each colour in turn
        tuner = pane.evaluate(RINGS, "blk:tuner")
        assert len({r["stroke"] for r in tuner}) >= 2 and all(r["dash"] not in ("none", "") for r in tuner), tuner
        steps = pg.evaluate(RINGS, "flow:quality-steps")
        assert {r["stroke"] for r in steps} <= {r["stroke"] for r in tuner} and steps, (steps, tuner)
        # remembered; a closed system's box in the colour its outline has when open
        hull = pane.evaluate("() => getComputedStyle(document.querySelector('svg.canvas g.hull[data-hull] > .corr-ring')).stroke")
        name = pane.evaluate("() => S.graph.corr.shapes[document.querySelector('svg.canvas g.hull[data-hull]').dataset.hull]?.system")
        drawn(pg, url, "open=-", 1)
        assert pg.evaluate("() => document.body.classList.contains('corr-on')")
        box = pg.evaluate(f"() => S.graph.nodes.find((n) => n.kind === 'system' && n.label === {name!r})?.id")
        assert box and [r["stroke"] for r in pg.evaluate(RINGS, box)] == [hull]
        toggle_colours(pg)
        assert not pg.evaluate(SHOWN, box)
        drawn(pg, url, "open=-", 2)
        assert not pg.evaluate(SHOWN, box)
        assert not errors, errors
        pg.close()


def test_holding_c_shows_the_colours_in_both_panes_until_let_go_but_not_while_typing(browser, tmp_path):
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        drawn(pg, url, "open=*", 0)
        pane = open_split(pg, "right")
        pg.mouse.click(5, 300)
        pg.keyboard.down("c")
        assert pg.evaluate(SHOWN, "stock:capabilities")
        pane.wait_for_function(f"() => ({SHOWN})('out:stock.capabilities')", timeout=5000)
        pg.keyboard.up("c")
        assert not pg.evaluate(SHOWN, "stock:capabilities")
        pane.wait_for_function(f"() => !({SHOWN})('out:stock.capabilities')", timeout=5000)
        assert pg.evaluate("() => localStorage.getItem('ergostat.colours')") is None      # held, not remembered
        pg.evaluate("() => { const i = document.createElement('input'); i.id = 'typing'; document.body.append(i); i.focus(); }")
        pg.keyboard.down("c")
        assert not pg.evaluate(SHOWN, "stock:capabilities")
        pg.keyboard.up("c")
        assert pg.evaluate("() => document.getElementById('typing').value") == "c"
        pg.close()


def test_a_part_pointed_at_is_found_at_a_glance_in_the_other_pane(browser, tmp_path):
    """Pointing at a stock in the dynamics pane rings its integrator and output y in the block diagram pane
    thick, in the accent, wider on the screen than the stock's own outline, and the rest of that pane steps
    back; with the colours on, the ring is the stock's own colour. Letting go, all is as it was."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pane = open_split(pg, "right")
        fit(pg)
        fit(pane)
        accent = pane.evaluate(ACCENT)
        pg.locator('g.node[data-id="stock:capabilities"]').hover(position={"x": 4, "y": 4})
        pane.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.xhover').length > 0", timeout=5000)
        own = pg.evaluate("""() => { const h = document.querySelector('svg.canvas g.node[data-id="stock:capabilities"] .hit');
          return parseFloat(getComputedStyle(h).strokeWidth) * S.view.k; }""")
        for there in ("out:stock.capabilities", "proc:stock.capabilities"):
            rings = pane.evaluate(RINGS, there)
            strong = all(r["display"] != "none" and r["width"] >= 4 and r["width"] >= own and r["stroke"] == accent for r in rings)
            assert rings and strong, (there, rings, own, accent)
        pane.wait_for_timeout(400)                                       # (it steps back over a moment)
        dim = pane.evaluate("""() => { const ns = [...document.querySelectorAll('svg.canvas g.node:not(.xhover)')];
          return ns.filter((n) => parseFloat(getComputedStyle(n).opacity) < 0.5).length / ns.length; }""")
        assert dim > 0.9, dim
        assert pane.evaluate("() => parseFloat(getComputedStyle(document.querySelector('svg.canvas g.node.xhover')).opacity)") == 1
        # the pane pointed in: as it is
        assert pg.evaluate("() => document.querySelector('svg.canvas').classList.contains('xhovering')") is False
        pg.mouse.move(2, 400)
        pane.wait_for_function("() => !document.querySelector('svg.canvas.xhovering') && !document.querySelector('svg.canvas .xhover')",
                               timeout=5000)
        assert not pane.evaluate(SHOWN, "out:stock.capabilities")
        # with the colours on: the same thick ring, in the stock's colour
        toggle_colours(pg)
        colour = pg.evaluate(RINGS, "stock:capabilities")[0]["stroke"]
        assert colour != accent
        pg.locator('g.node[data-id="stock:capabilities"]').hover(position={"x": 4, "y": 4})
        pane.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.xhover').length > 0", timeout=5000)
        rings = pane.evaluate(RINGS, "out:stock.capabilities")
        assert rings and all(r["width"] >= 4 and r["stroke"] == colour for r in rings), (rings, colour)
        # and the other way: a controller pointed at in blocks, its valve in dynamics, ringed in segments of its colours
        pg.mouse.move(2, 400)
        pane.locator('g.node[data-id="blk:tuner"]').hover(position={"x": 3, "y": 3}, force=True)
        pg.wait_for_function("() => document.querySelector('svg.canvas g.node.xhover')", timeout=5000)
        steps = pg.evaluate(RINGS, "flow:quality-steps")
        assert pg.evaluate("() => document.querySelector('svg.canvas g.node[data-id=\"flow:quality-steps\"]').classList.contains('xhover')")
        assert len({r["stroke"] for r in steps}) >= 2 and all(r["width"] >= 4 for r in steps), steps
        assert not errors, errors
        pg.close()


QUEUE = """\
name: queue
# the queue drains at k an hour of what is in it
parameters:
  k:
    value: 2          # what we believe
    unit: 1/h
    estimate: true
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
flows:
  arrivals:
    to: queue
    sensor:
      manual: true
  served:
    from: queue
    driven-by: +stock.queue
    equation: k * stock.queue
"""


def queued(tmp_path: Path, monkeypatch) -> Path:
    """The queue model, and two hours of record as the world ran it with k = 3 (an hour is under three of
    the queue's time constant, 30 minutes: too little to propose a value from)."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "queue"
    d.mkdir()
    (d / "ergostat.yaml").write_text(QUEUE)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    p = Project(mdl.load(d))
    now, q = time.time(), 0.0
    for i in range(241):
        a = 10 + 5 * ((i // 20) % 2)
        p.measurements.add("sensor/queue.main", q, at=now - 7200 + i * 30)
        p.measurements.add("sensor/arrivals.main", a, at=now - 7200 + i * 30)
        for _ in range(30):
            q += (a - 3 * q) / 3600
    return d


def test_an_equation_its_numbers_its_replay_and_a_proposal_accepted_from_the_page(browser, tmp_path, monkeypatch):
    """A valve with an equation shows it in MathML, each parameter with its value and where it comes
    from; its causes strip draws the replay (dashed) over the measured line and the projection past
    now. The Model page has each stock's fit with Theil's breakdown; Calibrate makes a proposal,
    shown there and in the valve's panel with Accept; accepting writes the smallest edit to the YAML
    and the history records it. A snapshot shows the same, and offers no Accept."""
    d = queued(tmp_path, monkeypatch)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        # nothing but the page may write: a request without its header is refused
        req = urllib.request.Request(url + "/api/estimate", method="POST", data=b"")
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(req, timeout=5)
        assert refused.value.code == 403
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=dynamics", 0)
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'flow:served'))")
        pg.wait_for_function("() => document.querySelector('#detail math.eq')", timeout=20000)
        maths = pg.evaluate("() => [...document.querySelectorAll('#detail math.eq mi')].map((x) => x.textContent)")
        assert maths == ["served", "k", "queue"], maths
        assert pg.locator("#detail math.eq mo", has_text="×").count() == 1
        row = pg.locator("#detail table.params tr").nth(1).inner_text()
        assert "k" in row and "1/h" in row and "declared" in row, row
        assert pg.locator("#detail input.whatif-in[data-name=k]").input_value() == "2"     # the value, to type over
        # the strip: the rate measured (none: it is worked out), its replay, and past now its projection
        pg.wait_for_function(f"() => ({CHARTS.format('#detail')})() >= 2", timeout=20000)
        assert "the model's replay" in pg.locator("#detail .chart-foot").first.inner_text()
        assert pg.locator("#detail .chart.modelled").count() >= 2
        # a what-if: typed over, drawn on the strip, put back; the file never touched
        before = (d / "ergostat.yaml").read_text()
        box = pg.locator("#detail input.whatif-in[data-name=k]")
        box.fill("4")
        box.press("Enter")
        foot = "document.querySelector('#detail .chart-foot')?.textContent || ''"
        pg.wait_for_function(f"() => /what if k were 4/.test({foot})", timeout=20000)
        assert "Nothing is saved" in pg.locator("#detail .whatif").inner_text()
        pg.wait_for_function("() => /scaled error/.test(document.querySelector('#detail .whatif').textContent)", timeout=20000)
        assert "queue" in pg.locator("#detail .whatif dl").inner_text()            # its fit, before anything is stored
        pg.locator("#detail .whatif button", has_text="Put it back").click()
        pg.wait_for_function(f"() => !/what if k/.test({foot})", timeout=20000)
        assert (d / "ergostat.yaml").read_text() == before
        # the Model page: what is available (k, where it lives, whether the record is long enough), the stock's fit,
        # Theil's breakdown, and a proposal once estimated
        pg.goto(url + "/model")
        pg.wait_for_function("() => document.querySelector('.available table.avail')", timeout=20000)
        k = pg.locator(".available table.avail tr", has_text="k").filter(has_text="served").first.inner_text()
        assert "served" in k and "not calibrated yet" in k, k
        pg.wait_for_function("() => document.querySelector('table.fit td')", timeout=20000)
        head = pg.locator("table.fit tr").first.inner_text()
        assert all(x in head for x in ("R²", "MAPE", "UM", "US", "UC")), head
        assert "queue" in pg.locator("table.fit").first.inner_text()
        pg.get_by_role("button", name="Calibrate").click()
        pg.wait_for_function("() => document.querySelector('.entry')", timeout=30000)
        entry = pg.locator(".entry").first
        assert entry.locator("h3").inner_text() == "A parameter's value"            # the kind of change, its title
        entry.get_by_role("button", name="Effect and diff").click()
        prop = entry.inner_text()
        assert "k: 2 1/h → 3" in prop and "value: 2" in prop and "Accept" in prop, prop
        # its valve's panel offers it too; accepted there, the file says the new value, its comment kept
        drawn(pg, url, "view=dynamics", 1)
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'flow:served'))")
        pg.wait_for_function("() => document.querySelector('#detail .proposal button')", timeout=20000)
        cal = pg.locator("#detail table.calibrations").inner_text()          # each calibration a row of its own
        assert "each part alone" in cal and re.search(r"\b(3|2\.99|3\.0\d)", cal), cal
        pg.locator("#detail .proposal button", has_text="Accept").click()
        pg.wait_for_function("() => /Accepted/.test(document.querySelector('#detail .proposal').textContent)", timeout=20000)
        text = (d / "ergostat.yaml").read_text()
        assert re.search(r"    value: (3|2\.99\d*|3\.0\d*) ", text) and "# what we believe" in text and "# the queue drains" in text, text
        pg.goto(url + "/model")
        pg.wait_for_function("() => /accepted: k/.test(document.body.textContent)", timeout=20000)
        assert "Nothing waiting." in pg.locator(".page").inner_text()
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.snapshot import build
    out = tmp_path / "snapshot.html"
    out.write_text(build(Project(mdl.load(d)), since="1h"))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors, asked = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:"))
             else (asked.append(rt.request.url), rt.abort()))
    pg.goto(f"file://{out}#/diagram?view=dynamics")
    pg.wait_for_function("() => S.graph && document.querySelectorAll('svg.canvas g.node').length", timeout=60000)
    pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'flow:served'))")
    pg.wait_for_function(f"() => document.querySelector('#detail math.eq') && ({CHARTS.format('#detail')})() >= 2", timeout=20000)
    pg.goto(f"file://{out}#/model")
    pg.wait_for_function("() => document.querySelector('table.fit td')", timeout=20000)
    assert pg.get_by_role("button", name="Estimate now").count() == 0
    pg.close()
    assert not errors and not asked, (errors, asked)


# ---- the Model page's review queue: Show on diagram

def test_the_model_page_says_what_is_available_and_opens_each_tools_panel(browser, tmp_path):
    """The Model page (the Fit page's old address goes there) opens with what is available for the project: each
    loop, whether its process is identified and what would identify it, each parameter to estimate with the parts
    it is in; a loop's "process" link opens the block diagram with that loop's process block chosen and its panel
    open, and a parameter's part opens the dynamics view with its valve's panel (its equation and what-if)."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/fit?v=1")
        pg.wait_for_function("() => location.pathname === '/model' && document.querySelector('.available table.avail')", timeout=30000)
        assert pg.locator("h1").inner_text() == "Model"
        assert pg.locator("#nav a.on").inner_text() == "Model"
        avail = pg.locator(".available")
        pg.wait_for_function("() => !/analysing/.test(document.querySelector('.available').textContent)", timeout=120000)
        row = avail.locator("tr", has_text="quality-held").first.inner_text()
        assert "quality-setting → quality" in row and "not identified" in row, row
        assert "small-images" in avail.locator("p", has_text="no one process").inner_text()
        assert "window-time" in avail.inner_text() and "quality-turnover" in avail.inner_text()
        avail.locator("tr", has_text="quality-held").first.get_by_role("link", name="process", exact=True).click()
        pg.wait_for_function("() => S.graph?.kind === 'blocks' && !document.querySelector('#detail').hidden", timeout=60000)
        pg.wait_for_function("() => /The loop quality-held/.test(document.querySelector('#detail').textContent)", timeout=60000)
        assert pg.evaluate("() => S.graph.nodes.find((n) => n.id === S.bdSel?.node)?.role") == "process"
        pg.goto(url + "/model?v=1")
        pg.wait_for_function("() => document.querySelector('.available table.avail')", timeout=30000)
        pg.locator(".available tr", has_text="window-time").first.get_by_role("link", name="quality-turnover").click()
        pg.wait_for_function("() => S.graph?.kind === 'dynamics' && document.querySelector('#detail input.whatif-in')", timeout=60000)
        assert pg.evaluate("() => [...S.sel]") == ["flow.quality-turnover"]
        assert not errors, errors
        pg.close()


def flip_turnover_sign(d: Path) -> None:
    """A link drawn with the sign its equation contradicts: check finds it, and proposes the sign flipped."""
    f = d / "service.yaml"
    f.write_text(f.read_text().replace("driven-by: [+auxiliary.batch-quality, -stock.quality]",
                                       "driven-by: [-auxiliary.batch-quality, -stock.quality]"))


def test_show_on_diagram_chooses_a_proposals_parts_in_both_views(browser, tmp_path):
    """A proposal's Show on diagram chooses the parts it touches and opens the diagram with the other view
    beside it: lit in the dynamics view and in the block diagram's pane, the same parts chosen in both."""
    with served("image-squeeze", tmp_path, flip_turnover_sign) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/model?v=1")
        entry = pg.locator('.entry[data-kind="structure"]', has_text="quality-turnover").first
        entry.wait_for(timeout=60000)
        assert "A link's sign flipped" in entry.locator("h3").inner_text()
        for label in ("where", "why", "how found"):
            assert entry.locator("dt", has_text=label).count() == 1
        entry.get_by_role("button", name="Show on diagram").click()
        pg.wait_for_function(READY, timeout=60000)
        want = {"flow.quality-turnover", "auxiliary.batch-quality"}
        assert set(pg.evaluate("() => [...S.sel]")) == want
        assert pg.evaluate("() => S.graph.kind") == "dynamics"
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas g.node.selected').length >= 1", timeout=10000)
        lit = pg.evaluate(LIT)                       # the parts, or the closed system holding them, marked
        assert "flow:quality-turnover" in lit, lit          # its system opened: the part itself, not the box holding it
        pane = pane_of(pg)
        assert pane.evaluate("() => S.graph.kind") == "blocks"
        pane.wait_for_function("() => S.sel.size === 2 && document.querySelectorAll('svg.canvas g.node.selected').length > 0",
                               timeout=10000)
        assert set(pane.evaluate("() => [...S.sel]")) == want
        assert not errors, errors
        pg.close()
