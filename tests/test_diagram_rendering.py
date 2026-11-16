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
    pg.goto(f"{url}/?v={n}#/diagram?{view}")            # a new query: the page loads afresh, no layout carried over
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
def served(example: str, tmp_path: Path):
    """An example's page, served from a fresh copy (the model is not run)."""
    d = tmp_path / example
    shutil.copytree(ROOT / "examples" / example, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
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
        hull = pg.evaluate("() => { const c = S.layout.containers.find((c) => c.name === 'product'); return [c.x, c.y]; }")
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
        moved = pg.evaluate("() => { const c = S.layout.containers.find((c) => c.name === 'product'); return [c.x, c.y]; }")
        assert before and set(before) == set(after)
        offs = {(round(after[i][0] - before[i][0]), round(after[i][1] - before[i][1])) for i in before}
        assert len(offs) == 1, offs                                   # all by the same amount
        (dx, dy), = offs
        assert abs(dx - 180) < 8 and abs(dy - 90) < 8, (dx, dy)
        assert abs(moved[0] - hull[0] - dx) < 2 and abs(moved[1] - hull[1] - dy) < 2   # its outline with them
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["partOverlap"] and not r["netCrossings"], (r["through"], r["partOverlap"])
        drawn(pg, url, "open=*", 9)                                   # a new visit: still where it was put
        again = pg.evaluate(places)
        assert all(abs(again[i][0] - after[i][0]) < 2 and abs(again[i][1] - after[i][1]) < 2 for i in after)
        pg.locator('g.pins .pin[data-id="hull:product"]').dispatch_event("click")
        pg.wait_for_function("() => !S.pins['hull:product']", timeout=10000)
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
        pg.goto(f"{url}/#/item/session%2Fx")
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
      await new Promise((r) => setTimeout(r, 400));
      const now = document.querySelector("#detail h2")?.textContent;
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


SD_CHECK = """() => {
  // the system dynamics view as drawn: no sensor, controller or agent; every loop that shows here (two of its
  // parts drawn as themselves) has its marker; every connector whose polarity is known shows it at its head;
  // connectors are curves that cut through no part; and the drawing is in one ink (no fill or stroke in colour
  // but what is pointed at)
  const bad = [], svg = document.querySelector("svg.canvas");
  if (!svg.classList.contains("sd")) bad.push("not drawn as the dynamics view");
  for (const n of S.graph.nodes) if (["sensor", "controller", "agent"].includes(n.kind)) bad.push(`drawn: ${n.kind} ${n.id}`);
  if (svg.querySelector(".badge, .k-sensor, .k-controller")) bad.push("an agent badge, a sensor or a controller is drawn");
  const marked = new Set([...svg.querySelectorAll(".loop-marker")].flatMap((m) => (m.dataset.loops || "").split(" ")));
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
        assert pg.locator(".toolbar .seg button.on").inner_text() == "dynamics"
        assert not errors, errors
        pg.close()


def test_a_loop_marker_lights_its_loop_and_opens_its_panel(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="fit").click()
        pg.locator('.loop-marker[data-loop="backlog-clear"]').dispatch_event("click")
        pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail .what')", timeout=5000)
        assert "backlog-clear" in pg.locator("#detail h2").inner_text()
        assert "balancing" in pg.locator("#detail .kind").inner_text().lower()
        lit = pg.evaluate("""() => [...document.querySelectorAll('svg.canvas .node.in-loop')].map((n) => n.dataset.id).sort()""")
        assert lit == ["flow:submitted", "gap:backlog-clear", "stock:backlog"], lit
        assert pg.evaluate("() => document.querySelectorAll('svg.canvas .edge.in-loop').length") >= 3
        pg.close()
