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
import tempfile
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
    # Playwright's own Chromium, as the other page tests use (the installed Chrome 158 quits when a page is
    # closed, under Playwright 1.63); the installed Chrome only where that is missing
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            try:
                b = p.chromium.launch(channel="chrome")
            except Exception as e:                    # no Chromium or Chrome here
                pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


# the largest drawings route close to ROUTED_BOUND_MS on a quiet machine: under a parallel run they are run alone
HEAVY = {"coordinator"}


@pytest.fixture(scope="module", params=[pytest.param(e, marks=pytest.mark.serial) if e in HEAVY else e for e in EXAMPLES])
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


DRAWN_S = 240                 # the most a view may take to be drawn before a test gives up: a wait, not a check (the
                              # budgets that are checks are LAYOUT_BUDGET_MS and ROUTED_BOUND_MS), long for a loaded machine


def drawn(pg, url: str, view: str, n: int) -> None:
    pg.goto(f"{url}/diagram?v={n}&{view}", timeout=DRAWN_S * 1000)   # a new query: the page loads afresh, no layout carried over
    pg.wait_for_function(READY, timeout=DRAWN_S * 1000)


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
    knowns = json.loads(KNOWN.read_text()) if KNOWN.exists() else {}
    layout_known = {} if os.environ.get("RECORD_LAYOUT") else dict(knowns.get(name, {}))
    for i, v in enumerate(views):
        drawn(pg, url, v, i + 1)
        r = pg.evaluate(AUDIT)
        problems += [f"[{v or 'whole'}] {k}: {x}" for k in ("through", "overlap", "detour", "netCrossings", "partOverlap")
                     for x in r[k]]
        problems += critical(pg, v or "whole", layout_known)      # the layout rules (docs/layout-rules.md)
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
    counts = layout_known.pop("counts", {})
    ceilings = layout_known.pop("ceilings", {})
    problems += [f"{rule}: {counts.get(rule, 0)} instances, the ceiling is {ceilings.get(rule, 0)} (docs/layout-rules.md)"
                 for rule in CEILED if not os.environ.get("RECORD_LAYOUT") and counts.get(rule, 0) > ceilings.get(rule, 0)]
    if os.environ.get("RECORD_LAYOUT"):
        knowns = json.loads(KNOWN.read_text()) if KNOWN.exists() else {}
        mine = {k: v for k, v in layout_known.items() if v}
        mine["ceilings"] = {rule: counts.get(rule, 0) for rule in CEILED}
        KNOWN.write_text(json.dumps({**{k: v for k, v in knowns.items() if k != name}, **({name: mine} if mine else {})},
                                    indent=1, sort_keys=True) + "\n")
    if os.environ.get("RECORD_SIZES"):
        everything = json.loads(SIZES.read_text()) if SIZES.exists() else {}
        SIZES.write_text(json.dumps({**everything, name: sizes}, indent=1, sort_keys=True) + "\n")
    print(f"{name}: {len(views)} views, slowest first draw {slowest[0]:.0f}ms ({slowest[1]}), "
          f"slowest routing {routed[0]:.0f}ms ({routed[1]})")
    assert not errors, errors
    assert not problems, f"{name}: " + "\n".join(problems)
    assert slowest[0] < LAYOUT_BUDGET_MS, f"{name}: drawing {slowest[1]} took {slowest[0]:.0f}ms"
    assert routed[0] < ROUTED_BOUND_MS, f"{name}: routing {routed[1]} took {routed[0]:.0f}ms"


# drawn and routed, or (the Process view of a project with no record yet) saying there is nothing to draw
DRAWN_OR_EMPTY = f"() => ({READY[6:]}) || !!document.querySelector('.canvas-wrap .empty')"


# every part moved by under a pixel to where libavoid, working its width out again from its corners, finds it a hair
# narrower than it is (a system box's or a block's port on its right edge then lay past it), and routed again
ROUNDED_ROUTE = """async () => {
  const spec = () => (S.graph.kind === 'blocks' ? bdAvoidSpec : avoidSpec)(S.layout, S.graph).shapes;
  const edge = spec().flatMap((s) => s.pins.filter((p) => p.abs && p.x >= s.w - 1e-6)).length;
  const under = (x, w) => (x + w) - x < w && ((x + w / 2) + w / 2) - ((x + w / 2) - w / 2) < w;
  let moved = 0;
  for (const c of S.layout.children) for (let i = 1; i < 400; i++) {
    const x = c.x + i / 397, w = c.width + i / 389;
    if (!under(x, w)) continue;
    for (const p of Object.values(S.layout.ports || {}))   // (a block's ports, on the page: those on its right edge kept there)
      if (p.node === c.id) p.x += p.x >= c.x + c.width - 0.5 ? x + w - c.x - c.width : x - c.x;
    c.x = x; c.width = w; moved++;
    break;
  }
  (S.graph.kind === 'blocks' ? bdRoute : avoidStart)(S.layout, S.graph);
  await S.layout.whenRouted;
  return [moved, edge];
}"""


@pytest.mark.parametrize("view,example", [("view=dynamics", "software-factory"), ("view=blocks", "first-loop")])
def test_a_port_on_a_parts_right_edge_is_never_past_it_for_libavoid(browser, tmp_path, view, example):
    """The pin offset clamped to the shape: a system box's (Dynamics) or a block's (Blocks) port on its right edge,
    with the box at a sub-pixel place and width, gives libavoid no 'xOffset ... greater than shape width'."""
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        said: list[str] = []
        pg.on("console", lambda m: said.append(f"{m.type}: {m.text[:200]}") if m.type in ("error", "warning") else None)
        drawn(pg, url, view, 0)
        said.clear()
        moved, ports = pg.evaluate(ROUNDED_ROUTE)
        pg.wait_for_timeout(200)                           # (the worker's last word reaches the page a moment later)
        pg.close()
    assert moved and ports, (moved, ports)                # (the window opened: parts moved, ports on a right edge)
    assert not said, said


def test_every_view_loads_with_no_console_error_or_warning(browser, page_of):
    """Dynamics, Blocks and Process, whole and into each system: the page's console (its workers' too) says
    nothing is wrong: no error, no warning (libavoid's pin past its part's edge, ELK falling back)."""
    name, url = page_of
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    said: list[str] = []
    pg.on("pageerror", lambda e: said.append(f"pageerror: {e}"))
    pg.on("console", lambda m: said.append(f"{m.type}: {m.text[:300]}") if m.type in ("error", "warning") else None)
    pg.on("worker", lambda w: w.on("console", lambda m: said.append(f"worker {m.type}: {m.text[:300]}")
                                   if m.type in ("error", "warning") else None))
    drawn(pg, url, "", 0)
    tree = pg.evaluate("() => S.graph.tree || {}")
    problems, n = [], 0
    for view in ("dynamics", "blocks", "process"):
        for v in ["", *(f"&system={s}" for s in tree)]:
            said.clear()
            n += 1
            pg.goto(f"{url}/diagram?v={n}&view={view}{v}", timeout=DRAWN_S * 1000)
            pg.wait_for_function(DRAWN_OR_EMPTY, timeout=DRAWN_S * 1000)
            pg.wait_for_timeout(200)                       # (a worker's last word reaches the page a moment later)
            problems += [f"[view={view}{v}] {x}" for x in said]
    pg.close()
    assert not problems, f"{name}: " + "\n".join(problems)


# the critical layout faults an example's views had when the rules came (docs/layout-rules.md), each by its rule and
# its parts: known, listed there to fix, and not to grow (RECORD_LAYOUT=1 writes them again)
KNOWN = ROOT / "tests" / "fixtures" / "layout_known.json"
# rules with no gate of their own: an example's instances of each, over all its views, never more than recorded ("ceilings")
CEILED = ["valve-orientation-mismatch", "satellite-far"]


def critical(pg, where: str, known: dict | None = None) -> list[str]:
    """The critical instances of the layout rules (docs/layout-rules.md) in the view drawn, but those known: what reads
    wrongly at once. With known (an example's), what is found is noted in it under the view."""
    from tests import layout_rules as rules
    geo = pg.evaluate(GEOMETRY)
    if not geo:
        return []
    if known is not None:                                # (the ungated rules counted, against their ceilings below)
        for x in rules.check(geo, CEILED):
            known.setdefault("counts", {})[x["rule"]] = known.get("counts", {}).get(x["rule"], 0) + 1
    found = [x for x in rules.check(geo, fast=True) if x["severity"] == "critical"]
    keys = [f"{x['rule']}|{'|'.join(sorted(x['parts']))}" for x in found]
    if known is not None:
        was = set(known.get(where, []))
        known[where] = sorted(set(keys))
        return [f"[{where}] {x['rule']}: {x['what']}" for x, k in zip(found, keys, strict=True) if k not in was]
    return [f"[{where}] {x['rule']}: {x['what']}" for x in found]


@pytest.mark.parametrize("shape", __import__("tests.diagram_corpus", fromlist=["SHAPES"]).SHAPES)
def test_generated_models_of_every_shape_draw_with_no_critical_layout_fault(browser, tmp_path, shape):
    """One generated model of each shape (tests/diagram_corpus.py: chains, fan-outs, joins, rework, many clouds,
    systems linked across, cascades, auxiliaries, mixes, drains), in the Dynamics and Blocks views, whole and with
    everything open: no critical instance of any layout rule. The whole corpus is tests/layout_corpus.py's."""
    from tests import diagram_corpus as corpus
    name = f"gen-{shape}"
    d = tmp_path / name
    corpus.generate(name, shape, 7).write(d)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        problems = []
        for i, v in enumerate(["view=dynamics", "view=dynamics&open=*", "view=blocks", "view=blocks&open=*"]):
            drawn(pg, url, v, i)
            problems += critical(pg, v)
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)
    assert not errors, errors
    assert not problems, "\n".join(problems)


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
        pg.get_by_role("button", name="Fit", exact=True).click()
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
def served(example: str | Path, tmp_path: Path, edit=None):
    """An example's page (or a model folder's), served from a fresh copy (the model is not run; ``edit`` may change
    the copy first)."""
    src = example if isinstance(example, Path) else ROOT / "examples" / example
    d = tmp_path / src.name
    shutil.copytree(src, d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    if edit:
        edit(d)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120                # a loaded machine starts it slowly; wait for it, not a count
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise AssertionError(f"{example}'s page never answered") from None
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


GEOMETRY = (ROOT / "tests" / "layout_geometry.js").read_text()
MODELLING = [e for e in EXAMPLES if any(re.search(r"^\s+modelling:|use[s]?: modelling", f.read_text(), re.M)
                                        for f in (ROOT / "examples" / e).rglob("*.yaml"))]


@pytest.mark.parametrize("example", MODELLING)
def test_model_errors_drain_is_a_short_straight_satellite_of_its_stock(browser, tmp_path, example):
    """The owner's case (ticket-factory's modelling system, and every example's): model-error's outflow to a cloud
    ran far right, down across a link and another flow, into its valve, then down and left to a cloud in the
    bottom-left corner. A flow whose other end is a cloud is its stock's satellite: the valve beside the stock on a
    short pipe, the cloud just beyond, at most one bend, crossing no other line. The links into the valve (from
    model-error, and from accepted-changes' side) travel to it: they never pull it off its pipe."""
    from tests import layout_rules as rules
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        if "modelling" not in pg.evaluate("() => S.graph.tree || {}"):
            pytest.skip(f"{example} has no modelling system")
        for i, view in enumerate(["system=modelling", "open=modelling", "open=*"]):
            drawn(pg, url, view, i + 1)
            geo = pg.evaluate(GEOMETRY)
            g = rules.G(geo)
            stock = next((n for n in g.nodes.values() if n["kind"] == "stock" and n["label"] == "model-error"), None)
            assert stock, f"[{view}] no model-error stock"
            drain = [(v, pin, pout) for v, pin, pout in g.flows()
                     if pin and pout and pin["source"] == stock["id"] and g.kind(pout["target"]) == "cloud"]
            assert drain, f"[{view}] model-error has no outflow to a cloud"
            for v, pin, pout in drain:
                vr, cr, sr = g.rect[v["id"]], g.rect[pout["target"]], g.rect[stock["id"]]
                assert rules.gap(vr, sr) <= 90, f"[{view}] {v['id']} is {rules.gap(vr, sr):.0f}px from model-error"
                assert rules.gap(cr, vr) <= 70, f"[{view}] its cloud is {rules.gap(cr, vr):.0f}px from {v['id']}"
                path = g.flow_path(v, pin, pout)
                assert rules.bends(path) <= 1, f"[{view}] {v['id']} bends {rules.bends(path)} times: {path}"
                mine = {pin["id"], pout["id"]}
                for e in g.edges:
                    if e["id"] in mine:
                        continue
                    hit = [(a, b) for a, b in rules.segs(e["pts"]) for c, d in rules.segs(path) if rules.crosses(a, b, c, d)]
                    assert not hit, f"[{view}] {e['id']} crosses {v['id']}'s flow"
                links = [e for e in g.edges if e["kind"] != "pipe" and e["target"] == v["id"]]
                for e in links:                         # every link reaches the valve, wherever it sits
                    end = e["pts"][-1]
                    assert rules.gap((end[0], end[1], end[0], end[1]), vr) <= 3, f"[{view}] {e['id']} ends off {v['id']}: {end}"
                assert any("accepted" in e["source"] for e in links), f"[{view}] no link from accepted-changes' side"
        pg.close()
    assert not errors, errors


UPKEEP_BOX = """(id) => {
  const me = S.layout.children.find((c) => c.id === id);
  if (!me) return null;
  const el = document.querySelector(`g.node[data-id="${CSS.escape(id)}"]`);
  const others = S.layout.children.filter((c) => c !== me);
  const ahead = others.filter((c) => !(me.x >= c.x + c.width - 0.5 || me.y >= c.y + c.height - 0.5)).map((c) => c.id);
  const rule = document.querySelector("path.bd-upkeep-rule")?.getBBox();
  const dashed = [...(el?.querySelectorAll("rect") || [])].some((r) => r.getAttribute("stroke-dasharray"));
  const below = rule ? others.filter((c) => c.y + c.height > rule.y).map((c) => c.id) : [];
  const said = el?.querySelector(".sys-upkeep")?.getBBox();
  const fits = !!said && said.x >= 0 && said.x + said.width <= me.width && said.y >= 0 && said.y + said.height <= me.height;
  return { ahead, others: others.length, dashed, fits, text: el?.textContent || "", rule: rule ? { y: rule.y, below } : null, top: me.y };
}"""


@pytest.mark.parametrize("example", ["alert-triage", "big"])
def test_modelling_is_drawn_last_set_apart_and_labelled(browser, tmp_path, example):
    """The design review (Q13): at the top level ergostat's model of its own upkeep was the top-left box, read first,
    unexplained. In both views it comes last: its top-left corner below or right of every other part, its outline
    dashed, and it says it is 'ergostat's upkeep of this model, not the system'; in Blocks below a thin rule."""
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, (view, box) in enumerate([("view=dynamics", "system:modelling"), ("view=blocks", "sys:modelling")]):
            drawn(pg, url, view, i)
            r = pg.evaluate(UPKEEP_BOX, box)
            assert r, f"[{view}] no {box} drawn at the top level"
            assert r["others"] >= 2, f"[{view}] too few other parts to be last among: {r}"
            assert not r["ahead"], f"[{view}] {box}'s top-left corner is neither below nor right of {r['ahead']}"
            assert r["dashed"], f"[{view}] {box}'s outline is not dashed"
            assert "upkeep of this model" in r["text"], f"[{view}] {box} does not say what it is: {r['text']!r}"
            assert r["fits"], f"[{view}] the line 'upkeep of this model' runs outside {box}"
            if view == "view=blocks":
                assert r["rule"], "[blocks] no rule above the modelling block"
                assert r["rule"]["y"] < r["top"] and not r["rule"]["below"], f"[blocks] the rule is not between: {r}"
        pg.close()
    assert not errors, errors


def test_a_valve_dragged_over_its_stock_stands_upright_on_its_top(browser, tmp_path):
    """A valve turns to follow its pipe wherever it is put: new-backups (copies-not-offsite's inflow from a cloud, laid
    out standing on the stock's top) dragged beside the stock turns level, its pipe straight into the stock's side;
    dragged back over the stock it stands upright again, its pipe straight into the stock's top. Never a zig-zag through a
    valve facing the wrong way, nor a pipe forced round to another side."""
    from tests import layout_rules as rules
    sid, vid = "stock:copies-not-offsite", "flow:new-backups"
    at = "(id) => { const c = S.layout.children.find((c) => c.id === id); return [c.x, c.y, c.width, c.height]; }"

    def drag_to(pg, x1, y1):                            # the valve's corner to x1, y1 (the diagram's coordinates)
        vx, vy, _, _ = pg.evaluate(at, vid)
        hit = pg.locator(f'g.node[data-id="{vid}"] .hit').first.bounding_box()
        k = pg.evaluate("() => S.view.k")
        x, y = hit["x"] + hit["width"] / 2, hit["y"] + hit["height"] / 2
        pg.mouse.move(x, y)
        pg.mouse.down()
        for step in range(1, 13):
            pg.mouse.move(x + (x1 - vx) * k * step / 12, y + (y1 - vy) * k * step / 12)
        pg.mouse.up()
        pg.wait_for_timeout(300)
        pg.wait_for_function(f"() => S.pins['{vid}'] && !S.layout.routing", timeout=20000)
        pg.wait_for_timeout(500)
        return rules.G(pg.evaluate(GEOMETRY))

    with served("backups", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        sx, sy, sw, sh = pg.evaluate(at, sid)
        _, _, vw, vh = pg.evaluate(at, vid)
        for where, x1, y1, flow, side in [("beside", sx + sw + 60, sy + sh / 2 - vh / 2, "left", "right"),
                                          ("over", sx + sw / 2 - vw / 2, sy - 50 - vh, "down", "top")]:
            g = drag_to(pg, x1, y1)
            assert g.nodes[vid]["turn"]["flow"] == flow, (where, g.nodes[vid]["turn"])
            pipe = next(e for e in g.pipes if e["source"] == vid and e["target"] == sid)
            s, end = g.rect[sid], pipe["pts"][-1]
            on = abs(end[1] - s[1]) < 2 and s[0] < end[0] < s[2] if side == "top" else abs(end[0] - s[2]) < 2 and s[1] < end[1] < s[3]
            assert on, f"{where}: the pipe meets the stock at {end}, not its {side} {s}"
            assert rules.bends(pipe["pts"]) == 0, f"{where}: the pipe zig-zags: {pipe['pts']}"
            found = rules.check(g.geo, ["valve-orientation-mismatch"])     # (on its way into the stock: from the cloud
            assert not [x for x in found if pipe["id"] in x["parts"]], (where, found)    # an elbow may be unavoidable)
        pg.close()
    assert not errors, errors


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
  // (pinned closer over it than before, 100 and 170 instead of 150 and 280: since the layout changed for docs/layout-rules.md,
  // a goal lies further up, and would sit between the valve and its cloud)
  S.pins = { "stock:building": { x: st.x, y: st.y }, "flow:abandoned": { x: Math.round(cx - v.width / 2), y: st.y - 100 },
             "cloud:abandoned:out": { x: Math.round(cx - cl.width / 2), y: st.y - 170 } };
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
        pg.get_by_role("button", name="Fit", exact=True).click()
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


# two-stage routing (avoid.js avoidStart): the worker's careful answers held back on the page (HELD) until RELEASE(seq);
# SEEN, every answer the worker sent, as it sent it
HOLD_CAREFUL = """() => {
  window.HELD = []; window.SEEN = []; window.HOLD = true;
  AV.worker.addEventListener('message', (ev) => SEEN.push({ type: ev.data.type, seq: ev.data.seq, skipped: !!ev.data.skipped,
    slides: Object.keys(ev.data.slides || {}).length, routes: ev.data.type === 'refined' ? ev.data.routes : undefined }));
  AV.worker.onmessage = (ev) => { if (HOLD && ev.data.type === 'refined') HELD.push(ev); else avoidHeard(ev); };
  window.RELEASE = (seq) => { const out = HELD.filter((ev) => ev.data.seq === seq);
    HELD = HELD.filter((ev) => !out.includes(ev)); out.forEach(avoidHeard); return out.length; };
}"""
# the line ends (of the parts named, else of all) more than 4px off their part
ENDS_OFF = """(ids) => {
  const box = Object.fromEntries(S.layout.children.map((c) => [c.id, c])), bad = [];
  for (const le of S.layout.edges) {
    const e = S.graph.edges.find((x) => x.id === le.id), sc = (le.sections || [])[0];
    if (!e || !sc || le.cut) continue;
    for (const [id, p] of [[e.source, sc.startPoint], [e.target, sc.endPoint]]) {
      const c = box[id];
      if (!c || (ids && !ids.includes(id))) continue;
      const dx = Math.max(c.x - p.x, 0, p.x - c.x - c.width), dy = Math.max(c.y - p.y, 0, p.y - c.y - c.height);
      if (Math.hypot(dx, dy) > 4) bad.push([le.id, id, [p.x, p.y], [c.x, c.y, c.width, c.height]]);
    }
  }
  return bad;
}"""
# the lines whose drawn path does not begin and end where the layout's line does (within 4px)
DRAWN_OFF = """() => S.layout.edges.filter((le) => (le.sections || []).length && !le.cut).filter((le) => {
  const el = document.querySelector(`.edge[data-id="${CSS.escape(le.id)}"] .edge-hit`);
  if (!el) return false;
  const a = el.getPointAtLength(0), b = el.getPointAtLength(el.getTotalLength()), s = le.sections[0];
  const near = (p, q) => Math.hypot(p.x - q.x, p.y - q.y) <= 4;
  return !((near(a, s.startPoint) && near(b, s.endPoint)) || (near(a, s.endPoint) && near(b, s.startPoint)));
}).map((le) => le.id)"""
LINES = "() => JSON.stringify(S.layout.edges.map((le) => [le.id, le.sections]))"


def fast_drawn(pg) -> int:
    """A new layout made, its fast lines drawn and its careful answer come and held: the route's seq."""
    seq0 = pg.evaluate("() => AV.seq")
    pg.evaluate("() => { S.relayout(); }")
    pg.wait_for_function(f"() => AV.routed && AV.routed.seq > {seq0} && AV.routed.lay === S.layout && "
                         "HELD.some((ev) => ev.data.seq === AV.routed.seq)", timeout=DRAWN_S * 1000)
    return pg.evaluate("() => AV.routed.seq")


def test_fast_routes_drawn_before_careful(browser, tmp_path):
    """The fast pass's lines are drawn, ending on their parts, while the careful pass is held (routing still on);
    released, the careful lines take their place and routing ends."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=product", 0)
        pg.evaluate(HOLD_CAREFUL)
        seq = fast_drawn(pg)
        assert pg.evaluate("() => S.layout.routing") is True
        assert pg.evaluate("() => SEEN.some((m) => m.type === 'routed' && m.seq === AV.routed.seq && !m.skipped)")
        assert pg.evaluate(ENDS_OFF, None) == []
        assert pg.evaluate(DRAWN_OFF) == []
        assert pg.evaluate(f"() => RELEASE({seq})") == 1
        assert pg.evaluate("() => S.layout.routing") is False
        careful = pg.evaluate(f"() => JSON.stringify(SEEN.find((m) => m.type === 'refined' && m.seq === {seq}).routes)")
        assert pg.evaluate("() => JSON.stringify(AV.raw)") == careful, "the careful lines are drawn"
        assert pg.evaluate(ENDS_OFF, None) == []
        assert pg.evaluate(DRAWN_OFF) == []
        pg.close()


def test_careful_routes_of_replaced_layout_not_drawn(browser, tmp_path):
    """A careful answer that comes after its layout was replaced (S.relayout: a new layout drawn) is dropped: the
    drawing's lines, AV.raw and AV.routed stay the new layout's."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=product", 0)
        pg.evaluate(HOLD_CAREFUL)
        old = fast_drawn(pg)
        new = fast_drawn(pg)
        before = pg.evaluate(LINES), pg.evaluate("() => JSON.stringify(AV.raw)")
        assert pg.evaluate(f"() => RELEASE({old})") == 1
        assert (pg.evaluate(LINES), pg.evaluate("() => JSON.stringify(AV.raw)")) == before
        assert pg.evaluate(f"() => AV.routed.seq === {new} && AV.routed.lay === S.layout && S.layout.routing")
        assert pg.evaluate(f"() => RELEASE({new})") == 1
        assert pg.evaluate("() => S.layout.routing") is False
        pg.close()


def test_careful_routes_dropped_after_a_drag(browser, tmp_path):
    """A part dragged 150px between the fast and the careful answer: the careful lines (to where it was) are dropped,
    and every line of the part still ends on it where it is now."""
    nid = "stock:users"
    at = f"() => {{ const c = S.layout.children.find((c) => c.id === '{nid}'); return [c.x, c.y]; }}"
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=product", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        pg.evaluate(HOLD_CAREFUL)
        seq = fast_drawn(pg)
        before = pg.evaluate(at)
        hit = pg.locator(f'g.node[data-id="{nid}"] .hit').first.bounding_box()
        k = pg.evaluate("() => S.view.k")
        x, y = hit["x"] + hit["width"] / 2, hit["y"] + hit["height"] / 2
        pg.mouse.move(x, y)
        pg.mouse.down()
        for step in range(1, 11):
            pg.mouse.move(x + 15 * step * k, y)
        pg.wait_for_function(f"([x0, ids]) => ({at})()[0] - x0 > 144 && ({ENDS_OFF})(ids).length === 0",
                             arg=[before[0], [nid]], timeout=20000)
        assert pg.evaluate(f"() => RELEASE({seq})") == 1
        assert pg.evaluate(ENDS_OFF, [nid]) == [], "the careful lines (to where it was) were drawn over the dragged ones"
        assert pg.evaluate("() => S.layout.routing") is False
        pg.evaluate("() => { HOLD = false; }")
        pg.mouse.up()
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        assert pg.evaluate(ENDS_OFF, [nid]) == []
        pg.close()


VALVES_AT = """() => JSON.stringify(S.layout.children
  .filter((c) => ['valve', 'disturbance'].includes(S.graph.nodes.find((n) => n.id === c.id)?.kind))
  .map((c) => [c.id, c.x, c.y, c.turn]))"""


def test_valve_slides_applied_once_across_stages(browser, tmp_path):
    """In the dynamics view of deps (one of its valves slid off a corner by the router's first pass), the valves are
    slid once: where they are after the careful lines come is where the fast pass put them."""
    with served("deps", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "view=dynamics", 0)
        pg.evaluate(HOLD_CAREFUL)
        seq = fast_drawn(pg)
        assert pg.evaluate(f"() => SEEN.find((m) => m.type === 'routed' && m.seq === {seq}).slides") >= 1, "no valve slid"
        fast = pg.evaluate(VALVES_AT)
        assert pg.evaluate(f"() => RELEASE({seq})") == 1
        assert pg.evaluate("() => S.layout.routing") is False
        assert pg.evaluate(VALVES_AT) == fast
        pg.close()


def test_queued_careful_pass_skipped_for_newer_route(browser, tmp_path):
    """Two routes asked back to back (and one more just before, so the worker is busy): the first's careful pass is
    answered skipped and only the second's careful lines are drawn. And a route with a move queued behind it: its
    careful pass is skipped too, and its fast lines stay."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=product", 0)
        pg.evaluate(HOLD_CAREFUL)
        pg.evaluate("() => { HOLD = false; }")
        busy, first, second = pg.evaluate("""async () => {
          avoidStart(S.layout, S.graph); const z = AV.seq;
          avoidStart(S.layout, S.graph); const a = AV.seq;
          avoidStart(S.layout, S.graph); const b = AV.seq;
          await S.layout.whenRouted;
          return [z, a, b]; }""")
        seen = pg.evaluate("() => SEEN.filter((m) => m.type === 'refined').map((m) => [m.seq, m.skipped])")
        # (the busy one's careful pass too: either drained with the two, or queued behind them; skipped either way)
        assert [busy, True] in seen and [first, True] in seen and [second, False] in seen, seen
        careful = pg.evaluate(f"() => JSON.stringify(SEEN.find((m) => m.type === 'refined' && m.seq === {second}).routes)")
        assert pg.evaluate("() => JSON.stringify(AV.raw)") == careful
        assert pg.evaluate(f"() => AV.routed.seq === {second} && !S.layout.routing")
        moved = pg.evaluate("""async () => {
          const c = S.layout.children.find((c) => c.id === 'stock:users');
          avoidStart(S.layout, S.graph); const a = AV.seq;
          AV.worker.postMessage({ type: 'move', seq: a, n: -1, id: c.id, x: c.x, y: c.y });
          await S.layout.whenRouted;
          return a; }""")
        assert pg.evaluate(f"() => SEEN.find((m) => m.type === 'refined' && m.seq === {moved}).skipped") is True
        assert pg.evaluate(f"() => AV.routed.seq === {moved} && !S.layout.routing")
        assert pg.evaluate(ENDS_OFF, None) == []
        pg.close()


def test_an_open_system_dragged_by_its_outline_takes_its_parts_and_stays(browser, tmp_path):
    """An open system's outline, dragged by its top, moves with everything in it by the same amount;
    its lines are routed again, cleanly; nothing lands under it; and it stays there after a new visit."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
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
        pg.get_by_role("button", name="Fit", exact=True).click()
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
        pg.get_by_role("button", name="Fit", exact=True).click()
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


# the page's answers from the paths matching window.__slow (a pattern) held back 2.5s: a slow server, made on purpose
SLOW_FETCH = """(() => { const f = window.fetch;
  window.fetch = async (u, o) => {
    if (window.__slow && new RegExp(window.__slow).test(String(u.url || u))) await new Promise((r) => setTimeout(r, 2500));
    return f(u, o);
  }; })();"""
# some text in the canvas drawn where it can be seen: non-empty, inside the canvas's box, not hidden
CANVAS_TEXT = """() => { const svg = document.querySelector('svg.canvas'), r = svg.getBoundingClientRect();
  return [...svg.querySelectorAll('text')].filter((t) => { const b = t.getBoundingClientRect(), st = getComputedStyle(t);
    return t.textContent.trim() && b.width > 0 && b.right > r.left && b.left < r.right && b.bottom > r.top && b.top < r.bottom
      && st.visibility !== 'hidden' && st.display !== 'none'; }).map((t) => t.textContent.trim()); }"""


def test_into_open_and_a_panel_link_show_at_once_that_something_is_happening(browser, tmp_path):
    """With the server slow: 300 ms after Into on api the canvas has text to read (the old diagram dimmed under
    'Opening api…') and the side list is not empty; 300 ms after an agent's link in a goal's panel, the panel is that
    agent's, with its name and 'Loading…'. Then each is drawn as it is when the answer comes."""
    with served("big", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.add_init_script(SLOW_FETCH)
        drawn(pg, url, "open=-", 0)
        pg.wait_for_function("() => document.querySelector('.diagram .side').innerText.trim()", timeout=30000)
        pg.evaluate("() => { window.__slow = '/api/graph'; }")
        pg.locator('svg.canvas g.node:has(text.sys-title:text-is("api")) g.sys-btn:has(text:text-is("Into"))').first.click()
        pg.wait_for_timeout(300)
        assert "system=api" in pg.url
        seen = pg.evaluate(CANVAS_TEXT)
        assert seen, "300 ms after Into the canvas has no text to read"
        assert "Opening api…" in seen, seen
        assert pg.evaluate("() => document.querySelector('.diagram .side').innerText.trim()"), "the side list went blank"
        pg.evaluate("() => { window.__slow = null; }")
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        assert pg.evaluate("() => !document.querySelector('svg.canvas g.was, svg.canvas .opening-note, .diagram.opening')"), \
            "the old diagram or the note stayed once the new one was drawn"
        # a goal's panel, and in it the link to the agent that fills its valve
        pg.evaluate("() => openLoop('api-q0-low')")
        link = pg.locator('#detail table.parts a:text-is("api-q0-drain")').first
        link.wait_for(timeout=30000)
        pg.evaluate("() => { window.__slow = '/api/agents'; }")
        link.click()
        pg.wait_for_timeout(300)
        assert pg.locator("#detail h2").first.inner_text().strip() == "api-q0-drain"
        assert "Loading…" in pg.locator("#detail").inner_text()
        pg.wait_for_function("() => /Recent runs/.test(document.querySelector('#detail').innerText)", timeout=30000)
        assert "Loading…" not in pg.locator("#detail").inner_text()
        assert not errors, errors
        pg.close()


@pytest.mark.parametrize("path", ["loops", "items"])
def test_loops_and_items_say_loading_under_their_heading_until_their_answer(browser, tmp_path, path):
    """With the server slow, Loops and Items say 'Loading…' under their heading at once, and not once drawn."""
    with served("big", tmp_path) as url:
        pg = browser.new_page()
        pg.add_init_script(f"window.__slow = '/api/{path}\\\\b';")
        pg.add_init_script(SLOW_FETCH)
        pg.goto(f"{url}/{path}")
        pg.wait_for_selector(".page h1", timeout=30000)
        pg.wait_for_timeout(300)
        assert "Loading…" in pg.locator(".page").inner_text(), pg.locator(".page").inner_text()
        pg.evaluate("() => { window.__slow = null; }")
        # its answer drawn (a table of loops; the items' kinds, or that there are none yet): no longer loading
        pg.wait_for_function("() => !document.querySelector('.page').innerText.includes('Loading…')", timeout=30000)
        assert pg.locator(".page table, .page .kind-flow, .page p.muted").count(), "nothing drawn in its place"
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


BOX_TEXTS = """() => Object.fromEntries([...document.querySelectorAll('svg.canvas g.node.k-system')].map((g) =>
  [g.querySelector('.sys-title')?.textContent, [...g.querySelectorAll('text')].map((t) => t.textContent)]))"""


@pytest.mark.parametrize("example,box,description", [("the-job", "job", "what I am expected to do, and what I am judged on"),
                                                    ("software-factory", "product", "textkit and its customers")])
def test_each_closed_system_box_says_what_the_system_is(browser, tmp_path, example, box, description):
    """A closed system's box in Dynamics prints its description under its name, and no longer counts its
    feedback loops (the count is on its panel)."""
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=-", 0)
        boxes = pg.evaluate(BOX_TEXTS)
        assert box in boxes, f"no closed box {box!r} drawn: {sorted(boxes)}"
        said = " ".join(pg.evaluate("""(name) => [...[...document.querySelectorAll('svg.canvas g.node.k-system')]
          .find((g) => g.querySelector('.sys-title')?.textContent === name).querySelectorAll('text.sys-desc')]
          .map((t) => t.textContent)""", box))
        assert said == description, f"{box}'s box says {said!r}, not its description"
        counted = {n: [t for t in ts if re.search(r"feedback loops? inside", t)] for n, ts in boxes.items()}
        assert not any(counted.values()), f"a closed box still counts its loops: {counted}"
        assert not errors, errors
        pg.close()


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
        pg.goto(url + "/items?view=list")                     # every kind's list (bare, /items is the overview)
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
        pg.wait_for_function("() => document.querySelector('.toolbar .seg button.on')?.textContent.startsWith('Blocks')", timeout=30000)
        # old #/ addresses (bookmarks, briefs, messages): shown at their paths
        for old, new in (("/#/item/ticket%2F7", "/item/ticket%2F7"), ("/#/items?kind=ticket", "/items/ticket"),
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
    """Each field with its current value and 'N changes' opening the one Changes section narrowed to it: each change,
    oldest last, with the event that made it (a click opens it); a refused patch said; and a session item whose
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
        pg.wait_for_selector(".field-grid [data-field=title] .changes-of", timeout=10000)
        assert "Thumbnails are blurry at quality 60" in pg.locator("[data-field=title]").first.inner_text()
        assert pg.locator("[data-field] details.history").count() == 0          # one Changes section, not one per field
        changes = pg.locator("details.changes")
        notes = pg.locator("[data-field=notes] .changes-of")
        assert notes.inner_text().strip() == "4 changes"
        notes.click()
        pg.wait_for_selector("details.changes[open] table.history", timeout=10000)
        rows = changes.locator("table.history tr")
        assert rows.count() == 5                                           # the head and four changes, the latest first
        assert "add (append)" in rows.nth(1).inner_text() and "/notes/2" in rows.nth(1).inner_text()
        assert "raised it to 75" in rows.nth(1).inner_text() and "ticket.submitted" in rows.nth(1).inner_text()
        pg.locator("[data-field=hours] .changes-of").click()
        pg.wait_for_function("() => document.querySelector('details.changes table.history')?.innerText.includes('(sum)')")
        pg.locator("[data-field=title] .changes-of").click()
        pg.wait_for_function("() => document.querySelector('details.changes table.history')?.innerText.includes('replace by patch')")
        title = changes
        assert pg.locator("h2", has_text="Refused").count() == 1 and "test /title" in pg.locator("table.refused").inner_text()
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(shots / "item-history.png"), full_page=True)
        title.locator("table.history a", has_text="ticket.retitled").first.click()
        pg.wait_for_selector("#detail h2", timeout=5000)
        assert pg.locator("#detail h2").inner_text() == "ticket.retitled" and "/title" in pg.locator("#detail").inner_text()
        pg.goto(f"{url}/item/session%2Fdeveloper-1a2b")
        pg.wait_for_selector("[data-field=messages] table.sub", timeout=10000)
        msgs = pg.locator("[data-field=messages]").first.inner_text()
        assert "Raise the thumbnail quality" in msgs and "keeps every case under its size target" in msgs
        assert "Grep" in pg.locator("[data-field=tool_calls]").first.inner_text()
        assert "2,600" in pg.locator("[data-field=tokens_in]").first.inner_text() or \
            "2600" in pg.locator("[data-field=tokens_in]").first.inner_text()
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
        pg.get_by_role("button", name="Zoom in", exact=True).click()
        pg.get_by_role("button", name="Fit", exact=True).click()
        pg.close()


PROCESS_PANELS = """() => {
  const bad = [];
  for (const e of S.graph.edges) {
    openEdge(e);
    const kind = (document.querySelector('#detail .kind')?.textContent || '').toLowerCase();   // (in sentence case)
    if (!(e.kind === 'caused' ? kind.startsWith('caused') : kind.startsWith('directly follows'))) bad.push(`${e.id}: ${kind}`);
  }
  for (const n of S.graph.nodes) {
    openNode(n);
    const kind = (document.querySelector('#detail .kind')?.textContent || '').toLowerCase();
    if (!['state', 'activity', 'start', 'end'].includes(kind)) bad.push(`${n.id}: ${kind}`);
  }
  closeDetail();
  const dashed = document.querySelectorAll('svg.canvas g.edge.pm-caused').length;
  return { bad, dashed, caused: S.graph.edges.filter((e) => e.kind === 'caused').length, edges: S.graph.edges.length,
           drawnEdges: document.querySelectorAll('svg.canvas g.edge').length,
           nodes: document.querySelectorAll('svg.canvas g.node').length, want: S.graph.nodes.length,
           rework: document.querySelectorAll('svg.canvas g.edge.rework').length };
}"""


def item_id(glob: str, n: str) -> str:
    """An id its kind's glob matches."""
    out = re.sub(r"\[[^\]]*\]", "x", glob)
    return out.replace("**", n).replace("*", n).replace("?", "x")


def seed_workflows(p, now: float, items: int = 4) -> dict:
    """A record for every kind of item the example declares: each item arrives, moves through its kind's states
    by the events its kind maps (one item in two goes back a state and on again: rework), and the first events
    of each kind's items are caused by an event on an item of the kind before it (a fan-out across kinds)."""
    from ergostat.spec.item_systems import BUILT_IN
    spec = p.model.spec
    kinds = [k for k in spec.items.values() if not k.name.startswith(BUILT_IN + ".")]
    last = None
    t = now - 3000
    seen = {}
    for ki, k in enumerate(kinds):
        to = {}
        for ty, st in k.on.items():
            to.setdefault(st, ty)
        made, cause = 0, last
        for i in range(items):
            it = item_id(k.id, f"pm{ki}x{i}")
            if not k.matches(it) or any(x.matches(it) for x in kinds[:ki]):
                continue
            e = p.events.add(f"{k.name}.opened", item=it, causedby=cause["id"] if cause and i < 2 else None, at=t)
            made += 1
            t += 7
            path = [st for st in k.states[1:] if st in to]
            if i % 2 and len(path) >= 2:
                path = path[:2] + [path[0]] + path[1:]
            for st in path:
                e = p.events.add(to[st], item=it, at=t)
                t += 11
            if not k.states:
                p.events.add(f"{k.name}.noted", item=it, at=t)
                e = p.events.add(f"{k.name}.noted", item=it, at=t + 3)
            last = e
            t += 5
        seen[k.name] = made
    return {k: n for k, n in seen.items() if n}


@pytest.mark.parametrize("example", EXAMPLES)
def test_every_process_view_draws_its_workflows_cleanly(browser, tmp_path, example):
    """The Process view of each example, with a record of every kind's items moving through their states (rework
    and a fan-out across kinds among them): drawn cleanly (no line through a part, none on top of another, no
    part on another or on another kind's frame), in states and in events, every line's and node's panel opening."""
    from ergostat import model as mdl
    from ergostat.store import Project
    with served(example, tmp_path) as url:
        p = Project(mdl.load(tmp_path / example))
        seeded = seed_workflows(p, time.time())
        time.sleep(1.6)                                   # past the page's snapshot of the moment it started
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        problems, panels = [], []
        kinds = ",".join(seeded)
        for i, v in enumerate([f"view=process&kinds={kinds}", f"view=process&by=events&kinds={kinds}", "view=process"]):
            pg.goto(f"{url}/diagram?v={i}&{v}")
            if not seeded:
                pg.wait_for_selector(".canvas-wrap .empty")
                break
            if v == "view=process" and not pg.evaluate("async () => (await api('graph', { view: 'process' })).nodes.length"):
                continue                                  # the system's kinds are ergostat's own: nothing seeded there
            pg.wait_for_function(READY, timeout=60000)
            r = pg.evaluate(AUDIT)
            problems += [f"[{v}] {k}: {x}" for k in ("through", "overlap", "partOverlap") for x in r[k]]
            panels.append(pg.evaluate(PROCESS_PANELS))
        pg.close()
    assert not errors, errors
    assert not problems, f"{example}: " + "\n".join(problems)
    for w in panels:
        assert w["nodes"] == w["want"] and w["dashed"] == w["caused"] and w["drawnEdges"] == w["edges"], w
        assert not w["bad"], w["bad"][:8]
    if len(seeded) > 1:
        assert panels[0]["caused"] > 0, panels[0]
    if any(len([st for st in k.states[1:] if st in k.on.values()]) >= 2      # (seeded with rework: two moves or more;
           for k in p.model.spec.items.values() if k.name in seeded):        # a lease's leased and dead are none)
        assert panels[0]["rework"] > 0, panels[0]


def test_a_system_alone_at_its_level_beside_modelling_opens_at_first_load(browser, tmp_path):
    """The-job at / on first load: 'job' open, its ten domains drawn as boxes, modelling closed (a once template's
    system is not counted beside it); one click on Open draws a stock of incidents."""
    with served("the-job", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/")
        pg.wait_for_function(READY, timeout=60000)
        boxes = pg.evaluate("() => [...document.querySelectorAll('svg.canvas g.node.k-system')].map((g) => g.dataset.id)")
        domains = ["awareness", "delivery", "documents", "incidents", "messages", "rhythm", "safety", "stewardship",
                   "support", "team"]
        assert sorted(boxes) == sorted(["system:modelling", *(f"system:{d}" for d in domains)]), boxes
        assert pg.evaluate("() => S.graph.open") == ["job"]
        pg.locator('svg.canvas g.node[data-id="system:incidents"] g.sys-btn', has_text="Open").click()
        pg.wait_for_function("""() => S.graph.open.includes('incidents') && S.graph.nodes.some((n) => n.kind === 'stock'
          && (n.systems || []).includes('incidents')
          && document.querySelector(`svg.canvas g.node.k-stock[data-id="${CSS.escape(n.id)}"]`))""",
                             timeout=60000)                    # one click: a stock of incidents is drawn
        pg.close()
        assert not errors, errors


def test_a_process_lines_panel_lists_its_items_and_the_paths_slider_hides_rare_ones(browser, tmp_path):
    """Clicking a line of the process map lists the items that went along it, and links to the Items page
    filtered to exactly them; the Paths slider leaves out the lines rarer than its share; Times shows the median
    time on each line; the old wiring address opens the Process view."""
    from ergostat import model as mdl
    from ergostat.store import Project
    with served("the-job", tmp_path) as url:
        p = Project(mdl.load(tmp_path / "the-job"))
        now = time.time()
        for i in range(10):                               # ten tickets: all triaged, one in five back to new (rework)
            it = f"ticket/pm{i}"
            p.events.add("ticket.filed", item=it, at=now - 2000 + i)
            for j, ty in enumerate(["ticket.triaged", *(["ticket.reopened", "ticket.triaged"] if i % 5 == 0 else [])]):
                p.events.add(ty, item=it, at=now - 1500 + i * 10 + j)
        kind = next(k for k in p.model.spec.items.values() if k.matches("ticket/pm0"))
        time.sleep(1.6)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=wiring&by=events&kinds={kind.name}")
        pg.wait_for_function(READY, timeout=60000)
        assert "view=process" in pg.url
        busy = pg.evaluate("() => S.graph.edges.filter((e) => e.kind === 'follows').sort((a, b) => b.count - a.count)[0]")
        rare = pg.evaluate("() => S.graph.edges.filter((e) => e.kind === 'follows').sort((a, b) => a.count - b.count)[0]")
        assert rare["count"] < busy["count"] / 2, (rare, busy)
        at = pg.evaluate("""(id) => { const el = document.querySelector(`.edge[data-id="${CSS.escape(id)}"] .edge-hit`);
          const q = el.getPointAtLength(el.getTotalLength() / 2), m = el.getScreenCTM(); return [m.a * q.x + m.e, m.d * q.y + m.f]; }""",
                         busy["id"])
        pg.mouse.click(*at)
        pg.wait_for_selector("#detail .item-set table.item-list")
        listed = pg.evaluate("() => [...document.querySelectorAll('#detail .item-list a')].map((a) => a.textContent)")
        assert len(listed) == min(10, busy["items"]) and all(x.startswith("ticket/pm") for x in listed), listed
        href = pg.evaluate("() => [...document.querySelectorAll('#detail .item-set a')].find((a) => /Items page/.test(a.textContent)).href")
        assert "followed=" in href and "by=events" in href, href
        pg.goto(href)
        pg.wait_for_selector(".set-chip .n")
        assert pg.inner_text(".set-chip .n").strip().startswith(f"{busy['items']} items")
        # the slider: the rare line goes, the busy one stays
        pg.goto(f"{url}/diagram?view=process&by=events&kinds={kind.name}")
        pg.wait_for_function(READY, timeout=60000)
        pg.evaluate("() => { const r = document.querySelector('.pm-paths'); r.value = 50; r.dispatchEvent(new Event('change')); }")
        pg.wait_for_function("() => S.graph && S.graph.paths === 0.5 && S.layout && !S.layout.routing", timeout=30000)
        ids = pg.evaluate("() => S.graph.edges.map((e) => e.id)")
        assert busy["id"] in ids and rare["id"] not in ids and "paths=50" in pg.url
        drawn = pg.evaluate("() => [...document.querySelectorAll('svg.canvas g.edge')].map((g) => g.dataset.id)")
        assert sorted(drawn) == sorted(ids)
        pg.get_by_role("button", name="Times", exact=True).click()
        pg.wait_for_function("() => S.pmShow === 'times' && document.querySelector('svg.canvas g.edge .elabel')")
        assert "show=times" in pg.url
        pg.close()
    assert not errors, errors


# each state's count as the Items page's legend shows it, in one kind's card (a chart's labels or the plain boxes)
ITEMS_LEGEND = """(kind) => {
  const card = document.querySelector('a.pm-link[href*="kind=' + kind + '&"]').closest('.kind-flow');
  return Object.fromEntries([...card.querySelectorAll('a.stbox')].map((a) => {
    const n = a.querySelector('.n').textContent;
    return [a.textContent.slice(n.length).trim(), Number(n)]; })); }"""
# each node's words, and the smallest of its text as drawn on the screen (its font size times the map's scale)
NODE_TEXT = """() => [...document.querySelectorAll('svg.canvas .pm-node')].map((g) => ({ id: g.dataset.id,
  sub: g.querySelector('.t-sub')?.textContent,
  px: Math.min(...[...g.querySelectorAll('text')].map((t) => parseFloat(getComputedStyle(t).fontSize) * t.getScreenCTM().a)) }))"""


def test_items_links_each_kind_to_its_process_map_whose_states_say_how_many_are_there_now(browser, tmp_path):
    """From Items, a kind's 'process map' link opens its map in States; each state's node says 'now N', N the
    Items legend's count for that state; at Fit no node's text is drawn under 11px, and a map wider than the
    screen says which way more lies."""
    from ergostat import model as mdl
    from ergostat.store import Project
    with served("the-job", tmp_path) as url:
        p = Project(mdl.load(tmp_path / "the-job"))
        now = time.time()
        for i, last in enumerate(["new"] * 3 + ["explained"] * 2 + ["answered"]):   # 3 new, 2 explained, 1 answered
            it = f"ticket/now{i}"
            p.events.add("ticket.filed", item=it, at=now - 2000 + i)
            for j, st in enumerate(["explained", "answered"][:["new", "explained", "answered"].index(last)]):
                p.events.add(f"ticket.{st}", item=it, at=now - 1500 + i * 10 + j)
        time.sleep(1.6)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/items?states=all")              # the overview, its legends by each state (not state groups)
        pg.wait_for_selector('.kind-card a.pm-link[href*="kind=ticket&"]')
        pg.wait_for_function("() => document.querySelector('a.pm-link[href*=\"kind=ticket&\"]')"   # its chart's legend
                             ".closest('.kind-flow').querySelector('.cfd')")
        legend = pg.evaluate(ITEMS_LEGEND, "ticket")
        assert {k: v for k, v in legend.items() if v} == {"new": 3, "explained": 2, "answered": 1}, legend
        link = pg.locator('a.pm-link[href*="kind=ticket&"]')
        assert "view=process" in link.get_attribute("href") and "mode=states" in link.get_attribute("href")
        link.click()
        pg.wait_for_function(READY, timeout=60000)
        assert pg.evaluate("() => [S.graph.by, S.graph.kinds.map((k) => k.name)]") == ["states", ["ticket"]]   # that kind alone
        nodes = {n["id"]: n for n in pg.evaluate(NODE_TEXT)}
        states = pg.evaluate("() => S.graph.nodes.filter((n) => n.kind === 'activity').map((n) => [n.id, n.activity])")
        assert sorted(a for _, a in states) == ["answered", "explained", "new"], states
        for nid, st in states:                            # every state's node: how many are there now, as Items counts them
            assert nodes[nid]["sub"].startswith(f"now {legend[st]} · "), (st, nodes[nid]["sub"], legend)
        assert all(n["px"] >= 10.99 for n in nodes.values()), nodes
        pg.set_viewport_size({"width": 760, "height": 700})   # narrow: Fit keeps the text, and says where the rest is
        pg.get_by_role("button", name="Fit").click()
        assert all(n["px"] >= 10.99 for n in pg.evaluate(NODE_TEXT)), pg.evaluate(NODE_TEXT)
        assert pg.evaluate("() => S.layout.width * S.view.k > document.querySelector('svg.canvas').getBoundingClientRect().width")
        assert pg.is_visible("#panhint") and "→" in pg.inner_text("#panhint"), pg.inner_text("#panhint")
        pg.set_viewport_size({"width": 390, "height": 800})   # a phone (fitNarrow): first view and Fit keep 11px too
        pg.reload()
        pg.wait_for_function(READY, timeout=60000)
        assert all(n["px"] >= 10.99 for n in pg.evaluate(NODE_TEXT)), pg.evaluate(NODE_TEXT)
        pg.get_by_role("button", name="Fit").click()
        assert all(n["px"] >= 10.99 for n in pg.evaluate(NODE_TEXT)), pg.evaluate(NODE_TEXT)
        assert pg.is_visible("#panhint") and pg.inner_text("#panhint").startswith("More beyond the edge "), pg.inner_text("#panhint")
        pg.close()
    assert not errors, errors


def test_a_snapshot_lists_a_process_lines_items(browser, tmp_path):
    """From the file (snapshot_sets.py): a process map node's panel and a line's list their items, and the line's
    Items page link shows them; nothing says "not in this snapshot", and nothing is asked of a server."""
    from ergostat.web.snapshot import build
    from tests.test_snapshot_sets import sets_project
    (tmp_path / "m").mkdir()
    out = tmp_path / "snapshot.html"
    out.write_text(build(sets_project(tmp_path / "m")))
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors, asked = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:"))
             else (asked.append(rt.request.url), rt.abort()))
    pg.goto(f"file://{out}#/diagram?view=process")
    pg.wait_for_function(READY, timeout=60000)
    listed = "() => [...document.querySelectorAll('#detail .item-set table.item-list a')].map((a) => a.textContent).sort()"
    pg.evaluate("() => openProcessNode(S.graph.nodes.find((n) => n.itemKind === 'ticket' && n.activity === 'awaiting'))")
    pg.wait_for_selector("#detail .item-set table.item-list", timeout=20000)
    assert pg.evaluate(listed) == [f"ticket/{i}" for i in range(1, 7)]
    assert "not in this snapshot" not in pg.locator("#detail").inner_text()
    for kind, want in (("caused", ["ticket/1", "ticket/2"]), ("follows", None)):
        e = pg.evaluate(f"() => S.graph.edges.filter((e) => e.kind === '{kind}').sort((a, b) => b.count - a.count)[0]")
        pg.evaluate("(id) => openProcessEdge(S.graph.edges.find((e) => e.id === id))", e["id"])
        pg.wait_for_selector("#detail .item-set table.item-list", timeout=20000)
        got = pg.evaluate(listed)
        assert got == (want or got) and len(got) == min(10, e["items"]), (kind, got, e)
        assert "not in this snapshot" not in pg.locator("#detail").inner_text()
    pg.locator("#detail .item-set a[href^='#/items?']").first.click()          # the follows line's set
    pg.wait_for_selector(".set-chip", timeout=20000)
    pg.wait_for_function("(n) => [...document.querySelectorAll('.page table td:first-child')]"
                         ".filter((t) => t.textContent.trim().startsWith('ticket/')).length === n", arg=len(got), timeout=20000)
    shown = pg.evaluate("() => [...document.querySelectorAll('.page table td:first-child')].map((t) => t.textContent.trim())"
                        ".filter((t) => t.startsWith('ticket/')).sort()")
    assert shown == got
    assert "not in this snapshot" not in pg.locator(".page").inner_text()
    pg.close()
    assert not errors and not asked, (errors, asked)


# ---- the Process view in hand: the same dragging, pinning and unpinning as the other views (interact.js, places.js)

PM_SLANTED = """() => {
  // straight pieces of the process map's lines as drawn that run neither across nor up and down
  let n = 0;
  for (const p of document.querySelectorAll("svg.canvas g.edge path.pm-line")) {
    let at = null;
    for (const m of (p.getAttribute("d") || "").matchAll(/([MLQ])([^MLQ]*)/g)) {
      const v = m[2].trim().split(/[\\s,]+/).map(Number), pt = { x: v[v.length - 2], y: v[v.length - 1] };
      if (m[1] === "L" && at && Math.abs(pt.x - at.x) > 1 && Math.abs(pt.y - at.y) > 1) n++;
      at = pt;
    }
  }
  return n;
}"""
# its lines routed and drawn, nothing in hand, no line waiting for libavoid
PM_ROUTED = ("() => S.layout && S.graph && S.graph.kind === 'process' && S.graphSig && !S.layout.routing && "
             "!S.nodeDrag && !S.hullDrag && !S.layout.edges.some((le) => le.stale)")
PM_KIND = """(kind) => Object.fromEntries(S.layout.children.filter((c) => S.graph.nodes.find((n) => n.id === c.id)?.itemKind === kind)
  .map((c) => [c.id, [c.x, c.y]]))"""


def pm_served(pg, url, n, by="events", kinds="ticket,pr,release"):
    pg.goto(f"{url}/diagram?v={n}&view=process&by={by}&kinds={kinds}")
    pg.wait_for_function(PM_ROUTED, timeout=60000)


def test_a_process_node_dragged_stays_pinned_through_a_reload_a_refresh_and_states_and_unpin_all_restores_it(browser, tmp_path):
    """In the Process view a node dragged moves, its lines (within its kind, and the dashed ones to other kinds)
    never drawn across meanwhile; let go, it is pinned there with no new layout and its lines end on it; the pin is
    the Process view's own, and holds through a reload, the map refreshed in place as events come, and States and
    back (kept by the node's kind and name); the ⋯ menu's Unpin all parts puts it back where ELK laid it."""
    from ergostat import model as mdl
    from ergostat.store import Project
    with served("software-factory", tmp_path) as url:
        p = Project(mdl.load(tmp_path / "software-factory"))
        assert set(seed_workflows(p, time.time())) == {"ticket", "pr", "release"}
        time.sleep(1.6)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pm_served(pg, url, 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        nid = "p:pr:pr.merged"                         # lines in and out within pr, and one back (rework)
        caused = pg.evaluate("() => S.graph.edges.find((e) => e.kind === 'caused' && e.target === 'p:pr:pr.opened')?.id")
        assert caused, "a dashed line from ticket into pr"
        before = pg.evaluate(BD_AT, nid)
        layouts = pg.evaluate("() => S.layouts")
        slanted = bd_drag(pg, pg.locator(f'svg.canvas g.node[data-id="{nid}"]').bounding_box(), 60, 150, check=PM_SLANTED)
        assert slanted == 0, f"{slanted} slanted pieces drawn while dragging"
        pg.wait_for_function(f"() => S.pins['{nid}'] && ({PM_ROUTED})()", timeout=20000)
        pg.wait_for_timeout(300)
        assert pg.evaluate("() => S.layouts") == layouts, "letting go laid the map out again"
        after = pg.evaluate(BD_AT, nid)
        assert abs(after[0] - before[0] - 60) < 6 and abs(after[1] - before[1] - 150) < 6, (before, after)
        assert pg.evaluate(PM_SLANTED) == 0
        ends = pg.evaluate(BD_ENDS, nid)
        assert len(ends) >= 3 and all(ends), "every line of the moved node ends on it"
        assert all(pg.evaluate(BD_ENDS, "p:pr:pr.opened")), "the dashed line into pr still ends on its node"
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["partOverlap"], (r["through"], r["partOverlap"])
        assert pg.locator(f'svg.canvas g.pins .pin[data-id="{nid}"]').count() == 1
        kept = pg.evaluate("() => Object.fromEntries(Object.keys(localStorage).filter((k) => k.startsWith('ergostat.pins.'))"
                           ".map((k) => [k, JSON.parse(localStorage.getItem(k))]))")
        assert [k for k, v in kept.items() if nid in v and ".process." in k], kept
        assert not [k for k in kept if ".process." not in k], kept       # the Process view's pins are its own
        assert next(v for v in kept.values() if nid in v)[nid].get("in") == "pr"   # kept from its kind's frame
        pm_served(pg, url, 1)                                             # a new visit: still where it was put
        assert pg.evaluate(BD_AT, nid) == pytest.approx(after, abs=2)
        # the map refreshed: in place (an answer whose values differ and whose shape does not, as the page's poll
        # brings it: drawn again, nothing laid out), then laid out again (a new line in pr, from the record); the
        # pin holds through both
        held = ("(id) => { const c = S.layout.children.find((c) => c.id === id); return [c.x, c.y, "
                "!!document.querySelector(`svg.canvas g.pins .pin[data-id=\"${id}\"]`), S.drawN, S.layouts]; }")
        x, y, _, drew, layouts = pg.evaluate(held, nid)
        pg.evaluate("""async () => { const g = structuredClone(S.graph);
          for (const e of g.edges) e.median = (e.median || 0) + 7;                  // (values only: the same map)
          S.graph = g; await drawProcessView(document.querySelector('svg.canvas'), g); }""")
        x, y, pinned, drawn_now, relaid = pg.evaluate(held, nid)
        assert drawn_now > drew and relaid == layouts, "a refresh in place laid the map out again"
        assert [x, y] == pytest.approx(after, abs=2) and pinned
        shown = pg.evaluate("() => S.graph.events")
        p.events.add("pr.merged", item="pr/pm1x0", at=time.time())
        pg.wait_for_function(f"() => S.graph.events > {shown} && S.layouts > {layouts} && ({PM_ROUTED})()", timeout=30000)
        x, y, pinned, _, _ = pg.evaluate(held, nid)
        assert [x, y] == pytest.approx(after, abs=2) and pinned
        assert all(pg.evaluate(BD_ENDS, nid))
        # States and back: one pin for the node's name, in either mode it is drawn in
        pm_served(pg, url, 2, by="states")
        assert pg.evaluate(f"() => !!S.pins['{nid}']"), "the pin was lost"
        pm_served(pg, url, 3)
        assert pg.evaluate(BD_AT, nid) == pytest.approx(after, abs=2)
        pg.locator(".toolbar .menu-btn.dots").click()                    # ⋯, Unpin all parts: as ELK laid it out
        pg.get_by_role("menuitem", name=re.compile("Unpin all parts")).click()
        pg.wait_for_function(f"() => !Object.keys(S.pins).length && ({PM_ROUTED})() && "
                             f"Math.abs(S.layout.children.find((c) => c.id === '{nid}').y - {after[1]}) > 20", timeout=20000)
        # (where ELK puts it: a line more since, so not to the pixel where it first was)
        assert pg.evaluate("() => S.layout.children.every((c) => c.x === c.x0 && c.y === c.y0)")
        assert pg.evaluate(BD_AT, nid) == pytest.approx(before, abs=40)
        assert pg.locator("svg.canvas g.pins .pin").count() == 0
        assert not errors, errors
        pg.close()


def test_a_kinds_frame_dragged_in_the_process_view_takes_its_map_and_nodes_chosen_move_together(browser, tmp_path):
    """A kind's frame in the Process view, dragged by its top, moves with its whole map by the same amount (its
    lines keep their way), stays after a reload, and its lines to other kinds end on their nodes; nodes chosen with
    Shift and a box move together, each pinned, with no new layout and no line drawn across."""
    from ergostat import model as mdl
    from ergostat.store import Project
    with served("software-factory", tmp_path) as url:
        p = Project(mdl.load(tmp_path / "software-factory"))
        seed_workflows(p, time.time())
        time.sleep(1.6)
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pm_served(pg, url, 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        frame = "(name) => { const c = S.layout.containers.find((c) => c.name === name); return [c.bx ?? c.x, c.by ?? c.y]; }"
        ways = """(kind) => Object.fromEntries(S.layout.edges.filter((le) => S.graph.edges.find((e) => e.id === le.id &&
          e.kind === 'follows' && e.itemKind === kind)).map((le) => [le.id, [le.sections[0].startPoint,
          ...(le.sections[0].bendPoints || [])].map((q) => [q.x, q.y])]))"""
        before, corner, lines = pg.evaluate(PM_KIND, "release"), pg.evaluate(frame, "release"), pg.evaluate(ways, "release")
        layouts = pg.evaluate("() => S.layouts")
        grip = pg.locator('svg.canvas g.hull[data-hull="release"] > rect.hull-grip').bounding_box()
        slanted = bd_drag(pg, grip, 160, 90, at=(0.3, 0.5), check=PM_SLANTED)
        assert slanted == 0, f"{slanted} slanted pieces drawn while dragging"
        pg.wait_for_function(f"() => S.pins['hull:release'] && ({PM_ROUTED})()", timeout=20000)
        assert pg.evaluate("() => S.layouts") == layouts, "letting go laid the map out again"
        after = pg.evaluate(PM_KIND, "release")
        assert before and set(before) == set(after)
        offs = {(round(after[i][0] - before[i][0]), round(after[i][1] - before[i][1])) for i in before}
        assert len(offs) == 1, offs                                   # all by the same amount
        (dx, dy), = offs
        assert abs(dx - 160) < 8 and abs(dy - 90) < 8, (dx, dy)
        assert pg.evaluate(frame, "release") == pytest.approx([corner[0] + dx, corner[1] + dy], abs=2)
        moved = pg.evaluate(ways, "release")                          # its own lines: ELK's way, moved with it
        for k, pts in lines.items():
            assert [c for q in moved[k] for c in q] == pytest.approx([c for x, y in pts for c in (x + dx, y + dy)], abs=1), k
        for nid in before:
            assert all(pg.evaluate(BD_ENDS, nid)), nid
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["partOverlap"], (r["through"], r["partOverlap"])
        pm_served(pg, url, 1)                                         # a new visit: still where it was put
        again = pg.evaluate(PM_KIND, "release")
        assert all(again[i] == pytest.approx(after[i], abs=2) for i in after)
        # two nodes chosen with Shift and a box, dragged together
        pg.get_by_role("button", name="Fit", exact=True).click()
        ids = ["p:ticket:ticket.started", "p:ticket:ticket.submitted"]
        boxes = [pg.locator(f'svg.canvas g.node[data-id="{i}"]').bounding_box() for i in ids]
        x0, y0 = min(b["x"] for b in boxes) - 4, min(b["y"] for b in boxes) - 4
        x1, y1 = max(b["x"] + b["width"] for b in boxes) + 4, max(b["y"] + b["height"] for b in boxes) + 4
        pg.keyboard.down("Shift")
        pg.mouse.move(x0, y0)
        pg.mouse.down()
        pg.mouse.move((x0 + x1) / 2, (y0 + y1) / 2)
        pg.mouse.move(x1, y1)
        pg.mouse.up()
        pg.keyboard.up("Shift")
        chosen = pg.evaluate("() => [...document.querySelectorAll('svg.canvas g.node.selected')].map((e) => e.dataset.id)")
        assert set(ids) <= set(chosen), chosen
        was = pg.evaluate("() => Object.fromEntries(S.layout.children.map((c) => [c.id, [c.x, c.y]]))")
        layouts = pg.evaluate("() => S.layouts")
        slanted = bd_drag(pg, pg.locator(f'svg.canvas g.node[data-id="{ids[1]}"]').bounding_box(), 40, 120, check=PM_SLANTED)
        assert slanted == 0, f"{slanted} slanted pieces drawn while dragging"
        pg.wait_for_function(f"() => {json.dumps(chosen)}.every((i) => S.pins[i]) && ({PM_ROUTED})()", timeout=20000)
        assert pg.evaluate("() => S.layouts") == layouts, "letting go laid the map out again"
        now = pg.evaluate("() => Object.fromEntries(S.layout.children.map((c) => [c.id, [c.x, c.y]]))")
        for i in chosen:
            assert abs(now[i][0] - was[i][0] - 40) < 6 and abs(now[i][1] - was[i][1] - 120) < 6, (i, was[i], now[i])
            assert all(pg.evaluate(BD_ENDS, i)), i
        assert pg.evaluate(PM_SLANTED) == 0
        assert not errors, errors
        pg.close()


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
  // each block's tier, written in its top band: inside it, clear of its function
  for (const n of S.graph.nodes.filter((n) => n.tier)) {
    const el = document.querySelector(`svg.canvas g.node[data-id="${CSS.escape(n.id)}"]`);
    if (!el) continue;
    const t = el.querySelector("text.bd-tier");
    if (!t || t.dataset.tier !== n.tier) { bad.push(`${n.id}: its tier (${n.tier}) not drawn`); continue; }
    const box = el.querySelector(".hit").getBoundingClientRect(), tb = t.getBoundingClientRect();
    if (tb.left < box.left || tb.right > box.right || tb.top < box.top || tb.bottom > box.bottom) bad.push(`${n.id}: its tier outside it`);
    for (const o of el.querySelectorAll("text:not(.bd-tier), .bd-sketch, .bd-toggle")) {
      const ob = o.getBoundingClientRect();
      if (ob.width && ob.left < tb.right && tb.left < ob.right && ob.top < tb.bottom - 1 && tb.top < ob.bottom - 1)
        bad.push(`${n.id}: its tier on ${o.textContent || o.getAttribute("class")}`);
    }
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


CROSSING_RULES = ["crossing-without-hop", "dot-not-at-takeoff", "slash-on-crossing"]


def crossing_rules(geo) -> list:
    """The Blocks view's crossings, dots and slashes (docs/layout-rules.md): a hop at every crossing and no dot there, a
    dot only at a take-off, no vector's slash within 12px of a crossing."""
    from tests import layout_rules as rules
    return rules.check(geo, CROSSING_RULES) if geo else []


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
        problems += [f"[{v}] {x['rule']}: {x['what']}" for x in crossing_rules(pg.evaluate(GEOMETRY))]
        if max(r["size"]["aspect"], 1 / r["size"]["aspect"]) > MAX_ASPECT + 1 and r["size"]["fit"] < MIN_FIT:
            problems.append(f"[{v}] {r['size']}")
    pg.close()
    assert not errors, errors
    assert not problems, f"{name}: " + "\n".join(problems)


# no hover tooltips on a diagram's parts: no <title> in the drawing, no title attribute on anything in it
NO_TOOLTIPS = ("() => [...document.querySelectorAll('svg.canvas title, svg.canvas [title]')]"
               ".map((x) => (x.closest('[data-id]')?.dataset.id || x.tagName) + ': ' + "
               "(x.textContent || x.getAttribute('title')).slice(0, 60))")
# every sensor block drawn: its function and what it reads, as text in it
SENSORS = ("() => [...document.querySelectorAll('svg.canvas g.bd-sensor, svg.canvas g.bd-collector')]"
           ".map((g) => ({ id: g.dataset.id, fn: g.dataset.fn, "
           "text: [...g.querySelectorAll('text')].map((t) => t.textContent).join(' | ') }))")


def test_sensors_are_blocks_with_what_they_read_and_no_part_has_a_tooltip(browser, page_of):
    name, url = page_of
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    problems: list[str] = []
    for i, v in enumerate(["view=blocks&open=*", "view=dynamics&open=*", "view=blocks", "view=dynamics"]):
        drawn(pg, url, v, i)
        problems += [f"[{v}] tooltip on {x}" for x in pg.evaluate(NO_TOOLTIPS)]
        if v.startswith("view=blocks"):
            for s in pg.evaluate(SENSORS):
                if s["id"].startswith("sen:") and not re.search(r"H(\(s\))? [=:]", s["text"]):
                    problems.append(f"[{v}] sensor {s['id']} draws no function: {s['text']}")
                if not re.search(r"every|by hand|on cron|reading|ergostat", s["text"]):
                    problems.append(f"[{v}] {s['id']} does not say what it reads and how often: {s['text']}")
    if name == "the-job":                                  # its alerts loop: polled, reading the alerts its collector records
        drawn(pg, url, "view=blocks&system=incidents", 9)
        got = {s["id"]: s for s in pg.evaluate(SENSORS)}
        sen, col = got.get("sen:stock.alerts-to-draft"), got.get("col:alerts-fired.main")
        assert sen and "H(s) = e" in sen["text"] and "items: alert, fired, every" in sen["text"], got
        assert col and "watch.py alert" in col["text"] and "records alert items" in col["text"], got
    pg.close()
    assert not problems, f"{name}: " + "\n".join(problems)


def test_sensors_polled_alike_are_drawn_alike_with_a_sampler(browser, tmp_path):
    """image-squeeze's service: any two sensors with the same period have the same main label and both a
    sampler; a sampler whose T is slight against its loop's is drawn in the muted stroke, and its panel gives
    the ratio."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&system=service", 0)
        got = pg.evaluate("""() => [...document.querySelectorAll('svg.canvas g.bd-sensor')].map((g) => {
          const sm = g.querySelector('.bd-sensor-sampler'), t = g.querySelector('text.bd-expr');
          return { id: g.dataset.id, T: (/every ([^,)]+)/.exec(g.dataset.fn) || [])[1] || null,   // its period, as it reads
                   head: [...t.childNodes].filter((c) => !c.classList?.contains('bd-note')).map((c) => c.textContent).join(''),
                   sampler: !!sm, slight: !!sm?.classList.contains('bd-slight'),
                   stroke: sm ? getComputedStyle(sm.querySelector('.bd-line')).stroke : null };
        })""")
        ink, muted = pg.evaluate("""() => ['--ink', '--muted'].map((v) => { const p = document.createElement('div');
          p.style.color = `var(${v})`; document.body.append(p); const c = getComputedStyle(p).color; p.remove(); return c; })""")
        by: dict[str, list] = {}
        for s in got:
            if s["T"]:
                by.setdefault(s["T"], []).append(s)
        assert any(len(v) >= 2 for v in by.values()), got     # two sensors polled alike: the case the check is for
        for T, ss in by.items():
            assert len({s["head"] for s in ss}) == 1, (T, ss)
            assert all(s["sampler"] for s in ss), (T, ss)
        slight = [s for s in got if s["slight"]]
        assert slight and all(s["stroke"] == muted for s in slight), (got, muted)
        assert all(s["stroke"] == ink for s in got if s["sampler"] and not s["slight"]), (got, ink)
        panel = pg.evaluate(f"""() => {{ openBlock(S.graph.nodes.find((n) => n.id === {json.dumps(slight[0]['id'])}));
          return document.querySelector('#detail').textContent; }}""")
        assert re.search(r"T / loop\s*\S+ s / .+ = [0-9.e-]+", panel), panel
        assert not errors, errors
        pg.close()


# each block as drawn: its main label (what is written inside it, but its caption) and its caption, the band at its top
BLOCK_LABELS = """() => [...document.querySelectorAll('svg.canvas g.node.bd-block')].map((g) => {
  const box = g.querySelector('.hit').getBoundingClientRect(), cap = g.querySelector(':scope > text.bd-tier');
  const inside = [...g.querySelectorAll('text')].filter((t) => t !== cap && t.getBoundingClientRect().top >= box.top);
  return { id: g.dataset.id, main: inside.map((t) => t.textContent).join(' | '), cap: cap ? cap.textContent : null,
           capAtTop: cap ? cap.getBoundingClientRect().bottom <= box.top + 16 : null };
})"""


def test_every_block_carries_a_function_with_the_agents_name_as_its_caption(browser, tmp_path):
    # Blocks, the ticket factory's making: open-pr (a program) and work (an AI agent) state no law, so each says
    # f(·), its name and kind the caption in its top band; a counting sensor polled every 3 s says e^(−sT),
    # its T (with its collector's) and how often it polls
    with served("ticket-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "view=blocks&system=making", 0)
        got = pg.evaluate(BLOCK_LABELS)
        pg.close()
    assert len(got) >= 4, got
    bad = [b for b in got if not re.search(r"=|\(s\)|\(z\)|f\(·\)", b["main"])]
    assert not bad, f"a block whose main label is no function: {bad}"
    named = [b for b in got if re.search(r"(?<![\w-])(open-pr|work)(?![\w-])", b["main"])]
    assert not named, f"a block's name written as its main label: {named}"
    caps = {b["id"]: b for b in got}
    for bid, cap in (("blk:open-pr", "open-pr · program"), ("blk:work", "work · AI agent")):
        assert caps[bid]["cap"] == cap and caps[bid]["capAtTop"], caps.get(bid)
        assert "f(·), law not stated" in caps[bid]["main"], caps[bid]
    assert any(re.search(r"H\(s\) = e−sT\s*T = \d+ s.*every\s3\ss", b["main"]) for b in got if b["id"].startswith("sen:")), \
        [b for b in got if b["id"].startswith("sen:")]


def test_the_blocks_view_draws_a_declared_law_cleanly_with_its_mark(browser, tmp_path):
    # Blocks, the ticket factory's copy with its model replaced by one whose external block declares a kubernetes-hpa
    # law (tests/test_known_laws.py): the law is drawn inside the block as its function, its mark where an identified
    # law's is written, and the view passes its own drawing audit
    from tests.test_known_laws import HPA, model
    (tmp_path / "law").mkdir()
    text = model(tmp_path / "law", HPA).read_text()

    def edit(d):
        (d / "ergostat.yaml").write_text(text)
    with served("ticket-factory", tmp_path, edit) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks", 0)
        audit, dom, labels = pg.evaluate(AUDIT), pg.evaluate(BLOCKS_DOM), pg.evaluate(BLOCK_LABELS)
        mark = pg.evaluate("() => [...document.querySelectorAll('g[data-id=\"blk:hpa\"] text.bd-ident')]"
                           ".map((t) => t.textContent)")
        pg.close()
    assert not errors, errors
    assert not [x for k in ("through", "overlap", "netCrossings", "partOverlap") for x in audit[k]] and not dom, (audit, dom)
    assert mark == ["declared kubernetes-hpa"], mark
    got = {x["id"]: x for x in labels}["blk:hpa"]
    assert "u = ⌈u x / 0.6⌉" in got["main"], got


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


LOOP_PANEL = """() => {
  // the side panel: its first table, whether it comes before every <p>, its rows, its text, and each <math> against its edge
  // (a <math> wider than its box: whether that box, inside the panel, scrolls sideways)
  const d = document.querySelector('#detail'), t = d.querySelector('table'), right = d.getBoundingClientRect().right;
  const before = [...d.querySelectorAll('p')].every((p) => t && (t.compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING));
  const scrolls = (m) => { const b = m.parentElement;
    return m.scrollWidth <= b.clientWidth + 1 || (b !== d && ["auto", "scroll"].includes(getComputedStyle(b).overflowX)
                                                  && b.getBoundingClientRect().right <= right + 0.5); };
  return { before, rows: t ? [...t.rows].map((r) => [r.cells[0].textContent, r.cells[1].textContent]) : [], text: d.textContent,
           maths: [...d.querySelectorAll('math')].map((m) => ({ over: m.getBoundingClientRect().right - right,
                                                               alt: m.getAttribute('alttext'), scrolls: scrolls(m) })) };
}"""
SETTLED = """() => { const d = document.querySelector('#detail');
  return !d.hidden && d.querySelector('table.loop-table') && d.querySelector('.strip.scope .chart') && d.querySelector('.control h3')
    && ![...d.querySelectorAll('.control')].some((c) => !c.children.length); }"""


def test_a_loops_controller_panel_starts_with_its_table_and_its_math_stays_inside(browser, tmp_path):
    """C_tuner clicked in Blocks: the panel's first table precedes any <p> and has the rows law, process, held-out fit,
    time off, settling, saturation, the fit naming its measure (NRMSE); only its own loop's text (no small-images, a
    loop it is only on the path of); each <math> has alttext and none reaches past the panel's right edge, the process
    block's 4 × 4 matrix included."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        pg.locator('g.node[data-id="blk:tuner"] .hit').first.click()
        pg.wait_for_function(SETTLED, timeout=60000)
        got = pg.evaluate(LOOP_PANEL)
        assert got["before"], got["text"][:400]
        assert [k for k, _ in got["rows"]] == ["law", "process", "held-out fit", "time off", "settling", "saturation"], got["rows"]
        fit = dict(got["rows"])["held-out fit"]
        assert "NRMSE" in fit and "100% is perfect" in fit and "validation" in fit, fit
        assert dict(got["rows"])["process"].startswith("not identified: needs a step of u"), got["rows"]
        assert "small-images" not in got["text"], got["text"]
        assert got["maths"] and all(m["alt"] and m["over"] <= 0.5 and m["scrolls"] for m in got["maths"]), got["maths"]
        own = pg.evaluate("""async () => {   // a table for each loop the tuner holds, none for a loop it is only on the path of
          const n = S.graph.nodes.find((x) => x.id === 'blk:tuner'), ds = [];
          for (const l of (n.loops || []).filter((x) => S.status?.loops?.[x])) ds.push(await loopControl(l));
          const mine = ds.filter((d) => d && !d.why && (d.controller?.block === 'tuner' || (d.controllers || []).includes('tuner')));
          return [mine.length, document.querySelectorAll('#detail table.loop-table').length];
        }""")
        assert own[0] >= 1 and own[0] == own[1], own
        pg.evaluate("() => { const d = document.querySelector('#detail'); d.hidden = true; d.replaceChildren(); }")
        pg.evaluate("() => openBlock(S.graph.nodes.find((n) => n.id === 'proc:service'))")
        pg.wait_for_function("""() => document.querySelector('#detail table.loop-table') && document.querySelector('#detail .bd-math math')
          && document.querySelectorAll('#detail .control h3').length >= 3
          && ![...document.querySelectorAll('#detail .control')].some((c) => !c.children.length)""", timeout=60000)
        pg.evaluate("() => { document.querySelector('#detail').style.width = '300px'; }")    # narrow: the matrix is wider
        got = pg.evaluate(LOOP_PANEL)
        assert got["before"] and got["rows"][0][0] == "law", got
        assert "small-images" not in got["text"], got["text"]       # a loop with no one process: not this block's to identify
        assert got["maths"] and all(m["alt"] and m["over"] <= 0.5 and m["scrolls"] for m in got["maths"]), got["maths"]
        assert pg.evaluate(PROC_ORDER), "the process panel's identification charts come after its words"
        # one loop's answer failing leaves only that loop unknown: the others keep their tables and identification
        goals = pg.evaluate("() => S.graph.nodes.find((n) => n.id === 'proc:service').y_of || []")
        assert len(goals) >= 2, goals
        from urllib.parse import parse_qs, urlparse
        pg.route(lambda u: "/api/loop-control" in u and parse_qs(urlparse(u).query).get("goal") == [goals[0]],
                 lambda r: r.fulfill(status=500, body="no"))
        tables = pg.evaluate("() => document.querySelectorAll('#detail table.loop-table').length")
        pg.evaluate("() => { CTL.clear(); openBlock(S.graph.nodes.find((n) => n.id === 'proc:service')); }")
        pg.wait_for_function("""() => { const cs = [...document.querySelectorAll('#detail .control')];
          return cs.some((c) => c.textContent.includes('loop-control: 500')) && cs.some((c) => c.querySelector('h3')); }""",
                             timeout=60000)
        left = pg.evaluate("() => document.querySelectorAll('#detail table.loop-table').length")
        assert 1 <= left <= tables, (left, tables)
        assert not errors, errors
        pg.close()


def test_a_loops_table_is_drawn_again_when_a_proposal_below_it_is_accepted(browser, tmp_path):
    """The tuner's panel: a tuning proposal accepted in its controller section redraws the panel's first table too,
    so the law row says the new law, as the section below it does. (The loop's answer is routed: before the accept it
    carries a proposal, after it a new law; the accept itself is answered without an edit.)"""
    import json
    accepted: list[str] = []

    def answer(route):
        got = route.fetch()
        d = got.json()
        if d and not d.get("why"):
            if accepted:
                d["controller"] = {**(d.get("controller") or {}), "says": "the new law, accepted"}
                d["proposals"] = []
            else:
                d["proposals"] = [{"id": "tune-test", "kind": "tuning", "title": "a new gain", "reason": "a test's"}]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(d))

    def accept(route):
        accepted.append(route.request.url)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"edit": {"files": []}}))

    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/loop-control?*", answer)
        pg.route("**/api/control/tune-test/accept?*", accept)
        drawn(pg, url, "view=blocks&open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        pg.locator('g.node[data-id="blk:tuner"] .hit').first.click()
        pg.wait_for_function(SETTLED, timeout=60000)
        law = "() => document.querySelector('#detail table.loop-table tr td').textContent"
        assert "the new law" not in pg.evaluate(law)
        pg.locator("#detail .proposal button", has_text="Accept").first.click()
        pg.wait_for_function(law + ".includes('the new law, accepted')", timeout=20000)
        assert accepted, "the accept was not posted"
        assert not errors, errors
        pg.close()


PROC_ORDER = """() => {
  // the process panel: its identification (the first .control) before the block's words and headings outside it
  const d = document.querySelector('#detail'), c = d.querySelector('.control');
  const words = [...d.querySelectorAll('p.what, h3')].filter((x) => !x.closest('.control'));
  return !!c && words.length > 0 && words.every((w) => c.compareDocumentPosition(w) & Node.DOCUMENT_POSITION_FOLLOWING);
}"""


# ---- the Blocks view in hand: the same dragging, pinning and unpinning as the dynamics view (interact.js, places.js)

BD_SLANTED = """() => {
  // straight pieces of the block diagram's lines as drawn that run neither across nor up and down
  let n = 0;
  for (const p of document.querySelectorAll("svg.canvas g.bd-edge path.bd-wire")) {
    let at = null;
    for (const m of (p.getAttribute("d") || "").matchAll(/([ML])([-\\d.e]+),([-\\d.e]+)/g)) {
      const pt = { x: +m[2], y: +m[3] };
      if (m[1] === "L" && at && Math.abs(pt.x - at.x) > 1 && Math.abs(pt.y - at.y) > 1) n++;
      at = pt;
    }
  }
  return n;
}"""
BD_AT = "(id) => { const c = S.layout.children.find((c) => c.id === id); return c && [c.x, c.y]; }"
BD_ENDS = """(id) => S.layout.edges.filter((le) => { const e = S.graph.edges.find((x) => x.id === le.id);
    return e && (e.source === id || e.target === id); }).map((le) => {
  const c = S.layout.children.find((c) => c.id === id), s = le.sections[0], e = S.graph.edges.find((x) => x.id === le.id);
  const p = e.source === id ? s.startPoint : s.endPoint;
  return p.x >= c.x - 2 && p.x <= c.x + c.width + 2 && p.y >= c.y - 2 && p.y <= c.y + c.height + 2; })"""
# laid out for the graph now drawn (not the last one, while the new one is laid out), its lines routed and drawn
BD_ROUTED = ("() => S.layout && S.graph && S.graphSig === bdSig(S.graph) && !S.layout.routing && !S.layout.undrawn && "
             "!S.nodeDrag && !S.hullDrag")


def bd_drag(pg, box, dx, dy, at=(0.5, 0.5), steps=10, check=None) -> int:
    """Press at a point of a box on the screen and move by (dx, dy) in the diagram's units; the slanted pieces
    seen on the way (check), summed."""
    k = pg.evaluate("() => S.view.k")
    x, y = box["x"] + box["width"] * at[0], box["y"] + box["height"] * at[1]
    pg.mouse.move(x, y)
    pg.mouse.down()
    seen = 0
    for step in range(1, steps + 1):
        pg.mouse.move(x + dx * step / steps * k, y + dy * step / steps * k)
        if check:
            pg.wait_for_timeout(40)
            seen += pg.evaluate(check)
    pg.mouse.up()
    return seen


def test_a_block_dragged_in_the_blocks_view_stays_pinned_its_lines_end_on_it_and_unpin_all_restores_it(browser, tmp_path):
    """In the Blocks view a block dragged moves, its lines never drawn across meanwhile; let go, it is pinned
    there with no new layout, its lines routed again to end on it; it is still there after a reload (kept for
    the Blocks view, not the Dynamics view's); and the ⋯ menu's Unpin all parts puts it back where it was."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        nid = "blk:product-manager"
        before = pg.evaluate(BD_AT, nid)
        layouts = pg.evaluate("() => S.layouts")
        slanted = bd_drag(pg, pg.locator(f'svg.canvas g.node[data-id="{nid}"]').bounding_box(), 40, 160, check=BD_SLANTED)
        assert slanted == 0, f"{slanted} slanted pieces drawn while dragging"
        pg.wait_for_function(f"() => S.pins['{nid}'] && ({BD_ROUTED})()", timeout=20000)
        pg.wait_for_timeout(300)
        assert pg.evaluate("() => S.layouts") == layouts, "letting go laid the diagram out again"
        after = pg.evaluate(BD_AT, nid)
        assert abs(after[0] - before[0] - 40) < 6 and abs(after[1] - before[1] - 160) < 6, (before, after)
        assert pg.evaluate(BD_SLANTED) == 0
        ends = pg.evaluate(BD_ENDS, nid)
        assert ends and all(ends), "every line of the moved block ends on it"
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["partOverlap"], (r["through"], r["partOverlap"])
        assert pg.evaluate(BLOCKS_DOM) == []
        assert pg.locator(f'svg.canvas g.pins .pin[data-id="{nid}"]').count() == 1
        kept = pg.evaluate("() => Object.fromEntries(Object.keys(localStorage).filter((k) => k.startsWith('ergostat.pins.'))"
                           ".map((k) => [k, Object.keys(JSON.parse(localStorage.getItem(k)))]))")
        assert [k for k, ids in kept.items() if nid in ids and ".blocks." in k], kept
        assert not [k for k in kept if ".dynamics." in k], kept           # the Dynamics view's pins are its own
        drawn(pg, url, "view=blocks&open=*", 9)                          # a new visit: still where it was put
        again = pg.evaluate(BD_AT, nid)
        assert abs(again[0] - after[0]) < 2 and abs(again[1] - after[1]) < 2, (after, again)
        drawn(pg, url, "view=dynamics&open=*", 10)
        assert nid not in pg.evaluate("() => S.pins")
        drawn(pg, url, "view=blocks&open=*", 11)
        pg.locator(".toolbar .menu-btn.dots").click()                    # ⋯, Unpin all parts: as ELK laid it out
        pg.get_by_role("menuitem", name=re.compile("Unpin all parts")).click()
        pg.wait_for_function(f"() => !Object.keys(S.pins).length && ({BD_ROUTED})() && "
                             f"Math.abs(S.layout.children.find((c) => c.id === '{nid}').y - {before[1]}) < 2", timeout=20000)
        assert pg.evaluate(BD_AT, nid) == pytest.approx(before, abs=2)
        assert pg.locator("svg.canvas g.pins .pin").count() == 0
        assert not errors, errors
        pg.close()


def test_blocks_crossings_hop_dots_only_at_takeoffs_slashes_clear_and_a_drag_and_the_export_keep_them(browser, tmp_path):
    """Two lines crossing in the Blocks view are told from a connection: the level one hops over the other, with no
    dot; a dot is drawn only where one signal's lines part; a vector's slash sits 12px or more from any crossing.
    So after a block is dragged and its lines routed again, and in the exported SVG (its hops kept); and where two
    crossings fall at one place or within a hop of each other, one hop, the wire never drawn back beneath it."""
    from tests import layout_rules as rules
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=*", 0)
        geo = pg.evaluate(GEOMETRY)
        crossings = rules.wire_crossings(rules.G(geo))
        assert crossings and geo["hops"] and geo["dots"], (len(crossings), geo["hops"], geo["dots"])   # (something to judge)
        bad = crossing_rules(geo)
        assert bad == [], "\n".join([str(bad)] + [f"{e['id']} {e['pts']}" for e in geo["edges"] if any(e["id"] in x["parts"] for x in bad)]
                                    + [str(h) for h in geo["hops"] if any(h["edge"] in x["parts"] for x in bad)])
        nid = "blk:product-manager"
        pg.get_by_role("button", name="fit").click()
        bd_drag(pg, pg.locator(f'svg.canvas g.node[data-id="{nid}"]').bounding_box(), 40, 160)
        pg.wait_for_function(f"() => S.pins['{nid}'] && ({BD_ROUTED})()", timeout=20000)
        pg.wait_for_timeout(300)
        after = pg.evaluate(GEOMETRY)
        assert after["edges"] != geo["edges"], "the drag changed no line"
        assert crossing_rules(after) == []
        hops = len(after["hops"])
        assert hops >= len({(round(x), round(y), h) for x, y, h, *_ in rules.wire_crossings(rules.G(after))}) > 0
        text = pg.evaluate("() => standaloneSvg(document.querySelector('svg.canvas'), null).text")
        assert len(re.findall(r'<path d="[^"]*A[\d.]+,[\d.]+ 0 0 [01] ', text)) >= len({h["edge"] for h in after["hops"]})
        # two crossings on one level stretch at one place (two lines of a signal on one upright track), 2px or 6px
        # apart: one hop over each place, never the wire drawn back under a hop
        wire = pg.evaluate("""(xs) => xs.map((x2) => bdEdgeContent({ id: 'w', signal: { n: 1 } }, [{ x: 0, y: 50 }, { x: 100, y: 50 },
          { x: 100, y: 90 }], [50, x2].map((x) => ({ x, y: 50, h: 'w', v: 'u' + x, head: false })))
          .els[1].getAttribute('d'))""", [50, 52, 56])
        assert [rules.wire_backtracks(d) for d in wire] == [[], [], []], wire
        assert [d.count("A") for d in wire] == [1, 1, 2], wire
        assert not errors, errors
        pg.close()


def test_blocks_chosen_with_a_box_move_together_in_the_blocks_view(browser, tmp_path):
    """Shift and a drag on the Blocks view's background chooses what it touches; one of them dragged moves
    them all by the same amount, each pinned, with no new layout and no line drawn across."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        ids = ["sum:all-live", "blk:keep-all-live"]
        boxes = [pg.locator(f'svg.canvas g.node[data-id="{i}"]').bounding_box() for i in ids]
        x0, y0 = min(b["x"] for b in boxes) - 4, min(b["y"] for b in boxes) - 4
        x1, y1 = max(b["x"] + b["width"] for b in boxes) + 4, max(b["y"] + b["height"] for b in boxes) + 4
        pg.keyboard.down("Shift")
        pg.mouse.move(x0, y0)
        pg.mouse.down()
        pg.mouse.move((x0 + x1) / 2, (y0 + y1) / 2)
        pg.mouse.move(x1, y1)
        pg.mouse.up()
        pg.keyboard.up("Shift")
        chosen = pg.evaluate("() => [...document.querySelectorAll('svg.canvas g.node.selected')].map((e) => e.dataset.id)")
        assert set(ids) <= set(chosen), chosen
        before = pg.evaluate("() => Object.fromEntries(S.layout.children.map((c) => [c.id, [c.x, c.y]]))")
        layouts = pg.evaluate("() => S.layouts")
        slanted = bd_drag(pg, pg.locator('svg.canvas g.node[data-id="blk:keep-all-live"]').bounding_box(), 30, -70, check=BD_SLANTED)
        assert slanted == 0, f"{slanted} slanted pieces drawn while dragging"
        pg.wait_for_function(f"() => {json.dumps(chosen)}.every((i) => S.pins[i]) && ({BD_ROUTED})()", timeout=20000)
        pg.wait_for_timeout(300)
        assert pg.evaluate("() => S.layouts") == layouts, "letting go laid the diagram out again"
        after = pg.evaluate("() => Object.fromEntries(S.layout.children.map((c) => [c.id, [c.x, c.y]]))")
        for i in chosen:
            assert abs(after[i][0] - before[i][0] - 30) < 6 and abs(after[i][1] - before[i][1] + 70) < 6, (i, before[i], after[i])
        for i in chosen:
            assert all(pg.evaluate(BD_ENDS, i)), i
        assert pg.evaluate(BD_SLANTED) == 0
        assert pg.evaluate(BLOCKS_DOM) == []
        assert not errors, errors
        pg.close()


def test_an_open_systems_frame_dragged_in_the_blocks_view_takes_its_parts_and_its_pins_survive_closing_and_opening(browser, tmp_path):
    """An open system's frame in the Blocks view, dragged by its top, moves with everything in it, stays after
    a reload, and closed it is a block where the frame was put; opened again, its parts are back where they
    were. A block put by hand inside a frame keeps its place in that frame through closing and opening it."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        places = """() => Object.fromEntries(S.layout.children.filter((c) => (S.graph.nodes.find((n) => n.id === c.id)?.systems || [])
                       .includes('frame:product')).map((c) => [c.id, [c.x, c.y]]))"""
        frame = "(id) => { const c = S.layout.containers.find((c) => c.id === id); return c && [c.bx ?? c.x, c.by ?? c.y]; }"
        before, corner = pg.evaluate(places), pg.evaluate(frame, "frame:product")
        grip = pg.locator('svg.canvas g.hull[data-hull="frame:product"] > rect.hull-grip').bounding_box()
        bd_drag(pg, grip, 180, 90, at=(0.5, 0.5))
        pg.wait_for_function(f"() => S.pins['hull:frame:product'] && ({BD_ROUTED})()", timeout=20000)
        after = pg.evaluate(places)
        assert before and set(before) == set(after)
        offs = {(round(after[i][0] - before[i][0]), round(after[i][1] - before[i][1])) for i in before}
        assert len(offs) == 1, offs                                   # all by the same amount
        (dx, dy), = offs
        assert abs(dx - 180) < 8 and abs(dy - 90) < 8, (dx, dy)
        moved = pg.evaluate(frame, "frame:product")
        assert abs(moved[0] - corner[0] - dx) < 2 and abs(moved[1] - corner[1] - dy) < 2
        r = pg.evaluate(AUDIT)
        assert not r["through"] and not r["partOverlap"], (r["through"], r["partOverlap"])
        assert pg.evaluate(BLOCKS_DOM) == []
        drawn(pg, url, "view=blocks&open=*", 9)                      # a new visit: still where it was put
        again = pg.evaluate(places)
        assert all(abs(again[i][0] - after[i][0]) < 2 and abs(again[i][1] - after[i][1]) < 2 for i in after)
        # closed: one block where its frame was put; opened again: its parts where they were
        pg.evaluate("() => S.toggleSystem('product')")
        pg.wait_for_function(f"() => S.graph && !(S.graph.open || []).includes('product') && ({BD_ROUTED})() && "
                             "S.graph.nodes.some((n) => n.role === 'subsystem' && n.label === 'product')", timeout=30000)
        box = pg.evaluate("() => { const n = S.graph.nodes.find((n) => n.role === 'subsystem' && n.label === 'product'); "
                          "const c = S.layout.children.find((c) => c.id === n.id); return [c.x, c.y]; }")
        assert abs(box[0] - moved[0]) < 2 and abs(box[1] - moved[1]) < 2, (moved, box)
        assert pg.evaluate("() => !!S.pins['hull:frame:product']"), "the pin was lost"
        pg.evaluate("() => S.toggleSystem('product')")
        pg.wait_for_function(f"() => S.graph && (S.graph.open || []).includes('product') && ({BD_ROUTED})()", timeout=30000)
        again = pg.evaluate(places)
        assert set(again) == set(after) and all(abs(again[i][0] - after[i][0]) < 2 and abs(again[i][1] - after[i][1]) < 2 for i in after)
        # a block put by hand inside intake: its place in intake's frame kept through closing and opening it
        nid = "blk:support"
        pg.get_by_role("button", name="Fit", exact=True).click()                 # (wider with its sensors: all of it on the screen)
        bd_drag(pg, pg.locator(f'svg.canvas g.node[data-id="{nid}"]').bounding_box(), 0, 110)
        pg.wait_for_function(f"() => S.pins['{nid}'] && ({BD_ROUTED})()", timeout=20000)
        offset = ("(id) => { const c = S.layout.children.find((c) => c.id === id), "
                  "f = S.layout.containers.find((o) => o.id === 'frame:intake'); return [c.x - f.bx, c.y - f.by]; }")
        put = pg.evaluate(offset, nid)
        assert pg.evaluate(f"() => S.pins['{nid}'].in") == "frame:intake"
        for opened in (False, True):
            pg.evaluate("() => S.toggleSystem('intake')")
            pg.wait_for_function(f"() => S.graph && (S.graph.open || []).includes('intake') === {str(opened).lower()} && "
                                 f"({BD_ROUTED})()", timeout=30000)
            assert pg.evaluate(f"() => !!S.pins['{nid}']"), "the pin was lost"
        assert pg.evaluate(offset, nid) == pytest.approx(put, abs=2)
        assert pg.evaluate(BLOCKS_DOM) == []
        assert not errors, errors
        pg.close()


def test_a_system_is_drawn_c_p_or_named_with_the_same_p_by_m_closed_and_open(browser, tmp_path):
    """dev/records/blocks-subsystems-classified-c-p.md: no block drawn Q; each closed block's letter, name and p × m
    drawn again in its frame's title when it is opened; the legend defines C, P and p × m."""
    no_q = "() => [...document.querySelectorAll('svg.canvas tspan.bd-mi')].filter((t) => t.textContent === 'Q').length"
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=-", 0)
        boxes = pg.evaluate("""() => S.graph.nodes.filter((n) => n.role === 'subsystem').map((n) => [n.label,
            (n.fn.sym || '') + (n.fn.sub || ''), n.fn.expr,
            document.querySelector(`svg.canvas g.node[data-id="${n.id}"]`)?.textContent])""")
        assert {b[0]: b[1] for b in boxes} == {"factory": "Cfactory", "product": "Pproduct", "modelling": "modelling"}, boxes
        assert pg.evaluate(no_q) == 0
        legend = pg.evaluate("() => document.querySelector('.bd-legend')?.textContent || ''")
        assert "C_name" in legend and "P_name" in legend and "p × m" in legend and not re.search(r"\bQ\b", legend), legend
        for i, (name, head, dims, text) in enumerate(boxes, 1):
            assert text and head in text and dims in text, (name, text)          # drawn in the closed block
            drawn(pg, url, f"view=blocks&open={name}", i)
            title = pg.evaluate("(id) => document.querySelector(`svg.canvas g.hull[data-hull='${id}'] > text`)?.textContent",
                                f"frame:{name}")
            assert title and title.startswith(head) and title.endswith(dims), (name, head, dims, title)
            assert pg.evaluate(no_q) == 0
        assert not errors, errors
        pg.close()


SD_CHECK = """() => {
  // the system dynamics view as drawn: no sensor, controller or agent; every loop that shows here (two of its
  // parts drawn as themselves) has its marker; every connector shows its polarity (? where not known) at its head;
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
    if (!c || t[0] !== (sdPol(c) || "?")) bad.push(`marker ${m.dataset.loop} says ${t}`);
  }
  const box = S.layout.children;
  for (const e of S.graph.edges.filter((x) => x.kind === "connector")) {
    const eg = svg.querySelector(`.edge[data-id="${CSS.escape(e.id)}"]`);
    if (!eg) { bad.push(`not drawn: ${e.id}`); continue; }
    const sign = eg.querySelector("text.polarity")?.textContent;
    const want = { "+": "+", "-": "−" }[e.polarity] || "?";
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
        assert pg.locator(".toolbar .seg button.on").inner_text().lower().startswith("dynamics")
        assert not errors, errors
        pg.close()


SIGNS_CHECK = """() => {
  // every link drawn has one sign (+, − or ?); no two signs' boxes overlap or lie within 10 px; each sign's nearest
  // link line is its own (data-edge, and the line it is drawn with); a link declared with driven-by is dashed
  const svg = document.querySelector("svg.canvas"), bad = [];
  const links = [...svg.querySelectorAll(".edge")].filter((g) => g.querySelector("path.sd-connector"));
  for (const g of links) {
    const t = g.querySelectorAll("text.polarity");
    if (t.length !== 1 || !["+", "−", "?"].includes(t[0].textContent))
      bad.push(`sign of ${g.dataset.id}: ${[...t].map((x) => x.textContent)}`);
    else if (t[0].dataset.edge !== g.dataset.id) bad.push(`${g.dataset.id}'s sign says ${t[0].dataset.edge}`);
  }
  const glyphs = [...svg.querySelectorAll(".edge text.polarity")], boxes = glyphs.map((t) => t.getBBox());
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    const gap = Math.max(b.x - a.x - a.width, a.x - b.x - b.width, b.y - a.y - a.height, a.y - b.y - b.height);
    if (gap < 10) bad.push(`${glyphs[i].dataset.edge} and ${glyphs[j].dataset.edge}: ${gap.toFixed(1)} px apart`);
  }
  const pts = links.flatMap((g) => { const p = g.querySelector("path.sd-connector"), L = p.getTotalLength(), out = [];
    for (let d = 0; d <= L; d += 1) { const q = p.getPointAtLength(d); out.push([q.x, q.y, g.dataset.id]); }
    return out; });
  glyphs.forEach((t, i) => {
    const cx = boxes[i].x + boxes[i].width / 2, cy = boxes[i].y + boxes[i].height / 2;
    let best = null, bd = Infinity;
    for (const [x, y, id] of pts) { const d = Math.hypot(x - cx, y - cy); if (d < bd) { bd = d; best = id; } }
    if (best !== t.dataset.edge) bad.push(`${t.dataset.edge}'s sign at ${Math.round(cx)},${Math.round(cy)} is nearest ${best}`);
  });
  for (const e of S.graph.edges.filter((x) => x.drivenBy)) {
    const p = svg.querySelector(`.edge[data-id="${CSS.escape(e.id)}"] path.sd-connector`);
    if (p && getComputedStyle(p).strokeDasharray === "none") bad.push(`driven-by, drawn solid: ${e.id}`);
  }
  return { bad, links: links.length, drivenBy: S.graph.edges.filter((x) => x.drivenBy).length };
}"""


@pytest.mark.parametrize("example", [pytest.param(e, marks=pytest.mark.serial) if e in HEAVY else e for e in EXAMPLES])
def test_each_polarity_sign_sits_on_its_own_link_apart_from_the_others_and_every_link_has_one(browser, tmp_path, example):
    """The design review's Q25: on the demos' first page (software-factory's, and every example's) the signs were
    stacked where many links meet, the nearest one belonging to another link; deployed → shipped had none; and the
    links declared with driven-by were solid."""
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        r = pg.evaluate(SIGNS_CHECK)
        assert not r["bad"], "\n".join(r["bad"][:12])
        if example == "software-factory":                    # (its links between factory and product: driven-by)
            assert r["links"] >= 5 and r["drivenBy"], r
        assert not errors, errors
        pg.close()


def test_the_view_switch_says_what_each_view_shows_on_a_wide_screen_and_a_phone(browser, tmp_path):
    want = [("Dynamics", "what is"), ("Blocks", "what is controlled"), ("Process", "what happened")]
    with served("software-factory", tmp_path) as url:
        for width, height in ((1440, 900), (390, 844)):
            pg = browser.new_page(viewport={"width": width, "height": height})
            drawn(pg, url, "", 0)
            buttons = pg.locator('.toolbar .seg[aria-label="View"] button')
            assert buttons.count() == 3, width
            for i, (name, what) in enumerate(want):
                b = buttons.nth(i)
                text = " ".join(b.inner_text().split())           # inner_text: only what is rendered visibly
                assert text.startswith(name) and what in text, (width, text)
                assert b.get_attribute("title"), (width, name)    # the hover title is kept
                half = b.locator(".what")
                assert half.is_visible(), (width, name)
                box, page_w = half.bounding_box(), pg.evaluate("document.documentElement.clientWidth")
                assert box and box["x"] >= 0 and box["x"] + box["width"] <= page_w + 1, (width, name, box)
            if width > 700:                                     # the longer labels leave the top edge's split grip reachable
                assert pg.evaluate("""() => { const r = document.querySelector('.split-grip[data-edge="top"]').getBoundingClientRect();
                  return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.closest('.split-grip') !== null; }""")
            pg.close()


def test_a_loop_marker_lights_its_loop_and_opens_its_panel(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        pg.locator('.loop-marker[data-loop="backlog-clear"]').dispatch_event("click")
        pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail .what')", timeout=5000)
        assert pg.locator("#detail h2").inner_text().startswith("B")           # its label, R1 or B2, as Sterman numbers them
        assert pg.locator("#detail .subtitle").inner_text() == "backlog-clear"   # its name beneath
        assert "balancing" in pg.locator("#detail .kind").inner_text().lower()
        lit = pg.evaluate("""() => [...document.querySelectorAll('svg.canvas .node.in-loop')].map((n) => n.dataset.id).sort()""")
        assert lit == ["flow:submitted", "gap:backlog-clear", "stock:backlog"], lit
        assert pg.evaluate("() => document.querySelectorAll('svg.canvas .edge.in-loop').length") >= 3
        pg.close()


FOCUSED = ("() => { const a = document.activeElement; "
           "return a && [a.tagName, a.getAttribute('aria-label') || '', a.dataset.key || '', a.getAttribute('role') || '']; }")
# every element the svg points at as clickable, and whether a keyboard button (tabindex 0, or -1 under the roving stop) is it or holds it
UNREACHED = """() => [...document.querySelectorAll('svg.canvas *')].filter((el) => getComputedStyle(el).cursor === 'pointer'
  && !el.closest('svg.canvas [tabindex][role="button"][aria-label]')).map((el) => el.getAttribute('class') || el.tagName)"""


def tab_to(pg, want, most=600) -> list:
    """Tab (and only Tab) until the focus is on what ``want`` (a JS predicate on the focused element) accepts."""
    seen = []
    for _ in range(most):
        pg.keyboard.press("Tab")
        if pg.evaluate(f"() => {{ const a = document.activeElement; return !!a && ({want})(a); }}"):
            return pg.evaluate(FOCUSED)
        seen.append(pg.evaluate(FOCUSED))
    raise AssertionError(f"Tab never reached {want}; it went {seen[:40]} ... {seen[-10:]}")


IN_SVG = "(a) => !!a.closest('svg.canvas')"


def step_to(pg, want, most=600) -> list:
    """Into the diagram by Tab (its one stop), then Shift+Right round its parts in drawing order (keys.js) until the
    focus is on what ``want`` accepts."""
    if not pg.evaluate(f"() => ({IN_SVG})(document.activeElement)"):
        tab_to(pg, IN_SVG)
    seen = []
    for _ in range(most):
        if pg.evaluate(f"() => {{ const a = document.activeElement; return !!a && ({want})(a); }}"):
            return pg.evaluate(FOCUSED)
        seen.append(pg.evaluate(FOCUSED))
        pg.keyboard.press("Shift+ArrowRight")
        if pg.evaluate(FOCUSED) == seen[0]:
            break                                        # round every part drawn, and back to the first
    raise AssertionError(f"Shift+Right never reached {want}; it went {seen[:40]} ... {seen[-10:]}")


def test_everything_clickable_in_the_diagram_is_reached_and_acted_on_by_keyboard(browser, tmp_path):
    """Only the keyboard: Open on factory reached and pressed opens it; a stock reached and pressed opens its panel
    with the focus on its heading, and Escape gives the focus back to the stock. In every view, everything the svg
    shows as clickable is a named keyboard button, one of them the diagram's tab stop, and the side panel's loop rows
    are buttons. (Tab reaches the diagram once; Shift and an arrow step through its parts: keys.js.)"""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=-", 0)
        step_to(pg, "(a) => a.getAttribute('aria-label') === 'Open factory'")
        pg.keyboard.press("Enter")
        pg.wait_for_function("() => (S.graph?.open || []).includes('factory') && document.querySelector('svg.canvas g.node')",
                             timeout=30000)
        step_to(pg, "(a) => a.getAttribute('aria-label') === 'Open intake'")   # (factory holds systems; intake, the backlog)
        pg.keyboard.press("Enter")
        pg.wait_for_function("() => (S.graph?.open || []).includes('intake') && document.querySelector('svg.canvas g.node.k-stock')",
                             timeout=30000)
        stock = step_to(pg, "(a) => a.matches('svg.canvas g.node.k-stock')")
        assert stock[3] == "button" and stock[1].startswith("stock "), stock
        pg.keyboard.press("Enter")
        pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail h2')", timeout=10000)
        pg.wait_for_function("() => document.activeElement?.matches('#detail h2, #detail h3')", timeout=5000)
        pg.keyboard.press("Escape")
        pg.wait_for_function("() => document.querySelector('#detail').hidden", timeout=5000)
        back = pg.evaluate(FOCUSED)
        assert back[2] == stock[2] and back[1].startswith("stock "), (stock, back)
        from ergostat import model as mdl
        from ergostat.store import Project
        seed_workflows(Project(mdl.load(tmp_path / "software-factory")), time.time())   # (the Process view's maps)
        for i, view in enumerate(("view=dynamics&open=*", "view=blocks&open=*", "view=dynamics&open=-", "process")):
            if view == "process":
                pm_served(pg, url, 9)
            else:
                drawn(pg, url, view, i + 1)
            assert pg.evaluate("() => document.querySelectorAll('svg.canvas [tabindex=\"0\"]').length") == 1, view
            assert not pg.evaluate(UNREACHED), (view, pg.evaluate(UNREACHED)[:10])
            rows = pg.evaluate("() => [...document.querySelectorAll('.looprow[data-loop], .looprow.sd-inside')].map((r) => r.tagName)")
            assert (rows or "open=*" not in view) and set(rows) <= {"BUTTON"}, (view, rows)   # the side panel's loop rows
        assert not errors, errors
        pg.close()


# the demos swept (dev/records/diagram-spoken-names.md): every focusable part's spoken name, and what the page knows
# of it to check that name against (its name as drawn, a stock's unit)
SPOKEN_DEMOS = ["software-factory", "ticket-factory", "image-squeeze", "first-loop", "autoscaler", "ops"]
SPOKEN = """() => [...document.querySelectorAll('svg.canvas [tabindex="0"]:is(.node, .edge, .bd-frame)')].map((el) => {
  const n = el.matches('.node') && S.graph.nodes.find((x) => x.id === el.dataset.id);
  const e = el.matches('.edge') && S.graph.edges.find((x) => x.id === el.dataset.id);
  const f = el.matches('.bd-frame') && (S.graph.frames || []).find((x) => x.id === el.dataset.hull);
  const name = n ? (['gap', 'desired'].includes(n.role) ? n.goal : ['cloud', 'sampler', 'mux', 'demux'].includes(n.kind) ? ''
                    : String(n.label).replace(/^Σ /, '')) : e ? e.signal?.sym || e.flow || '' : f ? f.label : '';
  return { id: el.dataset.id || el.dataset.hull, role: el.getAttribute('role'), label: el.getAttribute('aria-label') || '',
           name, unit: n && n.kind === 'stock' ? (n.unit || '').trim() : '' };
})"""
SPOKEN_KINDS = {   # each view's kind words, the first words of every name (an allowlist: a part named otherwise fails)
    "dynamics": r"(stock|flow|pipe of flow|connector|auxiliary|exogenous input|desired level|goal gap|goal excess|decision|"
                r"cloud|module|shadow variable)\b",
    "blocks": r"(signal|summing junction|mux|demux|sampler|subsystem|inner loop|controller|actuator|process|sensor|collector|"
              r"reference input|disturbance input|output|In port|Out port|zero-order hold|block)\b"}
NOT_SPOKEN = {"dynamics": r"sensor|controller", "blocks": r"stock"}   # the other discipline's words


@pytest.mark.parametrize("example", SPOKEN_DEMOS)
def test_every_focusable_part_is_named_in_its_views_words_with_its_kind_and_name(browser, tmp_path, example):
    """Done items 1-3 of diagram-spoken-names: in Dynamics and in Blocks, every part Tab reaches has a non-empty name
    that starts with its kind word and contains its name, with no 'undefined' and no raw id; a stock's says its unit;
    no Dynamics name says sensor or controller, no Blocks name says stock."""
    assert example in EXAMPLES, example
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, view in enumerate(("dynamics", "blocks")):
            drawn(pg, url, f"view={view}&open=*", i)
            parts = pg.evaluate(SPOKEN)
            assert len(parts) > 3, (view, parts)
            for p in parts:
                said = p["label"]
                assert p["role"] == "button" and re.match(SPOKEN_KINDS[view], said), (view, p)
                assert p["name"] in said and p["unit"] in said, (view, p)
                assert not re.search(r"undefined|null|NaN|\w:\w", said), (view, p)
                assert not re.search(NOT_SPOKEN[view], said, re.I), (view, p)
        assert not errors, errors
        pg.close()


# the focused part: its key, what it is called, its id, and the graph's kind and role of it
ON = ("() => { const a = document.activeElement, n = a && S.graph?.nodes.find((x) => x.id === a.dataset?.id); "
      "return a && { key: a.dataset?.key || '', aria: a.getAttribute('aria-label') || '', id: a.dataset?.id || '', "
      "edge: a.matches('.edge'), kind: n?.kind || '', role: n?.role || '', label: n?.flow || n?.label || '', "
      "inSvg: !!a.closest('svg.canvas'), inPanel: !!a.closest('#detail') }; }")
VIEWS = ("view=dynamics&open=*", "view=blocks&open=*")


def test_the_diagram_is_one_tab_stop_that_remembers_the_part_last_on(browser, tmp_path):
    """Done 1 (software-factory stands in for :8791, as the other page tests serve it), in both views: one part of the
    svg is its tab stop; Tab reaches the diagram once and the next Tab leaves it, and no Tab after comes back into it;
    Shift+Tab back in lands on the part the arrows last moved to."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, view in enumerate(VIEWS):
            drawn(pg, url, view, i)
            assert pg.evaluate("() => document.querySelectorAll('svg.canvas [data-key][tabindex=\"0\"]').length") == 1, view
            assert pg.evaluate("() => document.querySelectorAll('svg.canvas [data-key]').length") > 20, view
            tab_to(pg, IN_SVG, most=200)
            pg.keyboard.press("Shift+ArrowRight")            # moved on, by the keyboard: this part is remembered
            moved = pg.evaluate(ON)
            assert moved["inSvg"], (view, moved)
            pg.keyboard.press("Tab")
            after = pg.evaluate(ON)
            assert after and not after["inSvg"], (view, "the next Tab stayed in the diagram", after)
            pg.keyboard.press("Shift+Tab")
            assert pg.evaluate(ON)["key"] == moved["key"], (view, moved, pg.evaluate(ON))
            pg.keyboard.press("Tab")
            for _ in range(150):                             # on through the rest of the page: never into the diagram again
                pg.keyboard.press("Tab")
                now = pg.evaluate(ON)
                if not now or now["aria"] == after["aria"] and now["key"] == after["key"]:
                    break
                assert not now["inSvg"], (view, "a second tab stop in the diagram", now)
        assert not errors, errors
        pg.close()


SPOKEN_UNIT = """() => {
  const off = { 'users-at-180': { word: 'off', error: -28 }, 'located-worked': { word: 'off', error: -36 }, other: { word: 'holding' } };
  S.status = { ...S.status, loops: off };
  const sd = { kind: 'dynamics', nodes: [
    { id: 'stock:users', kind: 'stock', label: 'users', valueText: '152', unit: 'users', systems: ['product'],
      goals: [{ name: 'users-at-180', desired: '180' }] },
    { id: 'flow:signups', kind: 'valve', label: 'signups', rate: 3.1, rateText: '3.1 per hour' },
    { id: 'cloud:signups:in', kind: 'cloud' },
    { id: 'gap:users-at-180', kind: 'auxiliary', role: 'gap', label: 'users gap', goal: 'users-at-180', of: 'users', offBy: 'off by 28' },
    { id: 'desired:users-at-180', kind: 'auxiliary', role: 'desired', goal: 'users-at-180', of: 'users', valueText: '180' },
    { id: 'auxiliary:churn', kind: 'auxiliary', label: 'churn', valueText: '2', unit: 'per day' },
    { id: 'decision:route', kind: 'auxiliary', role: 'decision', label: 'route' },
    { id: 'system:product', kind: 'system', label: 'product', description: 'what users get', loops: { holding: 2, off: 1 } },
    { id: 'term:load', kind: 'terminal', role: 'shadow', label: 'load' }],
    edges: [{ id: 'p1', kind: 'pipe', source: 'cloud:signups:in', target: 'flow:signups', flow: 'signups' },
            { id: 'p2', kind: 'pipe', source: 'flow:signups', target: 'stock:users', flow: 'signups', causal: ['word of mouth'] },
            { id: 'c1', kind: 'connector', source: 'auxiliary:churn', target: 'gap:users-at-180', polarity: '+' }],
    causalLoops: [{ name: 'word of mouth', polarity: 'B', nodes: ['stock:users', 'flow:signups', 'gap:users-at-180'] },
                  { name: 'l2', polarity: 'R', nodes: ['stock:users'] }, { name: 'l3', polarity: null, nodes: ['stock:users'] }] };
  const bd = { kind: 'blocks', nodes: [
    { id: 'blk:k', kind: 'block', role: 'controller', label: 'keep-located-worked', fn: { sym: 'C', kind: 'on-off' },
      loops: ['located-worked'] },
    { id: 'sum:located-worked', kind: 'sum', role: 'comparator', label: 'Σ located-worked', loops: ['located-worked'], ins: [] },
    { id: 'psum:backlog', kind: 'sum', role: 'process-sum', label: 'Σ backlog', ins: [{ sign: '+' }, { sign: '−' }] },
    { id: 'ref', kind: 'input', role: 'reference', label: 'r located-worked', fn: { value: '180' } },
    { id: 'sens', kind: 'block', role: 'sensor', label: 'located', fn: {} },
    { id: 'smp', kind: 'sampler', role: 'sampler', label: 'T', fn: { T: '5m' } },
    { id: 'mux1', kind: 'mux', label: 'mux', n: 3 },
    { id: 'sub', kind: 'block', role: 'subsystem', label: 'intake', description: 'takes work in', loops: ['located-worked', 'other'] },
    { id: 'pin', kind: 'port', role: 'in-port', label: 'demand' },
    { id: 'proc', kind: 'block', role: 'process', label: 'located', fn: { sym: 'P' } },
    { id: 'y', kind: 'output', role: 'output', label: 'y located' }],
    edges: [{ id: 'e1', source: 'sum:located-worked', target: 'blk:k', signal: { sym: 'e', sub: 'located-worked', what: 'error' } }],
    frames: [{ id: 'casc:x', kind: 'frame', frame: 'cascade', label: 'located-worked' },
             { id: 'sys:intake', kind: 'frame', frame: 'system', label: 'intake' }] };
  return { sd: [...sd.nodes, ...sd.edges].map((x) => sdSpoken(x, sd)),
           bd: [...bd.nodes, ...bd.edges, ...bd.frames].map((x) => bdSpoken(x, bd)) };
}"""


def test_each_views_name_function_speaks_every_part_kind_with_its_state_and_loops(browser, tmp_path):
    """Done items 2 and 4 of diagram-spoken-names: each view's name function (sdSpoken, bdSpoken) on a part of every
    kind, an off goal's saying 'off' (the server's word), a stock its value and unit, a part its loops."""
    with served("first-loop", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "view=dynamics", 0)
        said = pg.evaluate(SPOKEN_UNIT)
        assert said["sd"] == [
            "stock users, 152 users of desired 180, off, in product, in balancing loop word of mouth and 2 others",
            "flow signups, 3.1 per hour, from cloud to users, in balancing loop word of mouth",
            "cloud, outside the model's boundary",
            "goal gap users-at-180, off, off by 28, in balancing loop word of mouth",
            "desired level users-at-180, of users, 180",
            "auxiliary churn, 2 per day",
            "decision route",
            "module product, what users get, 2 goals holding, 1 goal off",
            "shadow variable load",
            "pipe of flow signups, from cloud to signups",
            "pipe of flow signups, from signups to users, in balancing loop word of mouth",
            "connector from churn to users gap, positive"], said["sd"]
        assert said["bd"] == [
            "controller C keep-located-worked, on-off, control loop located-worked, off",
            "summing junction of located-worked, reference minus measurement, control loop located-worked, off",
            "summing junction of backlog, plus minus",
            "reference input r located-worked, 180",
            "sensor (feedback path) located",
            "sampler (A/D), T = 5m",
            "mux of 3 signals",
            "subsystem intake, takes work in, control loop located-worked, off, control loop other, holding",
            "In port demand",
            "process P located",
            "output y located",
            "signal e located-worked, error, minus 36, off",
            "inner loop (cascade) of located-worked",
            "subsystem intake, open"], said["bd"]
        pg.close()


def test_the_arrows_follow_pipes_connectors_and_signals(browser, tmp_path):
    """Done 2: in Dynamics, from the stock backlog Right goes to its outflow valve (submitted) and on to the next stock
    (in-review), Left back; Down steps onto a connector into or out of the stock, saying its other end and its sign. In
    Blocks, from a summing junction Right reaches C, then the actuator, then P, and Down from P takes the return path."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, VIEWS[0], 0)
        step_to(pg, "(a) => a.dataset.id === 'stock:backlog'")
        # the server lists pipes first: the walk must not lean on that (the lines turned round, until the next refresh)
        outs = pg.evaluate("() => S.graph.edges.reverse().filter((e) => e.source === 'stock:backlog').map((e) => e.kind)")
        assert outs == ["connector", "pipe"], outs
        pg.keyboard.press("ArrowRight")
        valve = pg.evaluate(ON)
        assert valve["kind"] == "valve" and valve["label"] == "submitted", valve
        pg.keyboard.press("ArrowRight")
        assert pg.evaluate(ON)["id"] == "stock:in-review", pg.evaluate(ON)
        pg.keyboard.press("ArrowRight")                      # on: in-review's outflow, and the stock it fills (never a connector's end)
        on = pg.evaluate(ON)
        assert on["kind"] == "valve" and on["label"] in ("merged", "rejected"), on
        pg.keyboard.press("ArrowRight")
        assert pg.evaluate(ON)["id"] in ("stock:awaiting-deploy", "stock:backlog"), (on, pg.evaluate(ON))
        pg.keyboard.press("ArrowLeft")
        pg.keyboard.press("ArrowLeft")
        assert pg.evaluate(ON)["id"] == "stock:in-review", pg.evaluate(ON)
        pg.keyboard.press("ArrowLeft")
        assert pg.evaluate(ON)["id"] == valve["id"], pg.evaluate(ON)
        pg.keyboard.press("ArrowLeft")
        assert pg.evaluate(ON)["id"] == "stock:backlog", pg.evaluate(ON)
        pg.keyboard.press("ArrowDown")
        line = pg.evaluate(ON)
        assert line["edge"] and line["aria"].startswith("connector line") and "backlog" in line["aria"] and "sign" in line["aria"], line
        pg.keyboard.press("ArrowDown")                       # the next connector of the stock (or the same, if it has one)
        assert pg.evaluate(ON)["edge"] and pg.evaluate(ON)["aria"].startswith("connector line"), pg.evaluate(ON)
        pg.keyboard.press("Home")
        assert pg.evaluate(ON)["inSvg"] and not pg.evaluate(ON)["edge"], pg.evaluate(ON)

        drawn(pg, url, VIEWS[1], 1)
        # backlog-clear's loop: Σ, its rule (C), the developer filling the actuator, the backlog (P, after the summing
        # point where its flows add; the developer drives in-review's too, a longer way round), its sensor
        step_to(pg, "(a) => a.dataset.id === 'sum:backlog-clear'")
        went = []
        for _ in range(3):
            pg.keyboard.press("ArrowRight")
            went.append((pg.evaluate(ON)["role"], pg.evaluate(ON)["id"]))
        assert went == [("controller", "blk:keep-backlog-clear"), ("actuator", "blk:developer"),
                        ("process", "proc:stock.backlog")], went
        pg.keyboard.press("ArrowDown")                       # the return path: the sensor, then round to the junction
        assert (pg.evaluate(ON)["role"], pg.evaluate(ON)["id"]) == ("sensor", "sen:stock.backlog"), pg.evaluate(ON)
        pg.keyboard.press("ArrowDown")
        assert pg.evaluate(ON)["id"] == "sum:backlog-clear", pg.evaluate(ON)
        for want in ("blk:keep-backlog-clear", "blk:developer", "proc:stock.backlog"):
            pg.keyboard.press("ArrowRight")
            assert pg.evaluate(ON)["id"] == want, pg.evaluate(ON)
        pg.keyboard.press("ArrowLeft")                       # and back along the signal, through the summing point
        assert pg.evaluate(ON)["id"] == "blk:developer", pg.evaluate(ON)
        assert not errors, errors
        pg.close()


def test_enter_opens_the_panel_with_the_focus_inside_and_escape_returns_to_the_part(browser, tmp_path):
    """Done 3, in both views: a part reached by the keyboard, Enter opens its panel with the focus inside it; Escape
    closes it and gives the focus back to the same part, still the diagram's tab stop."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        for i, (view, want) in enumerate(zip(VIEWS, ("(a) => a.dataset.id === 'stock:backlog'",
                                                    "(a) => S.graph.nodes.find((x) => x.id === a.dataset.id)?.role === 'controller'"),
                                             strict=True)):
            drawn(pg, url, view, i)
            step_to(pg, want)
            part = pg.evaluate(ON)
            pg.keyboard.press("Enter")
            try:
                pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.activeElement?.closest('#detail')",
                                     timeout=10000)
            except playwright.TimeoutError as e:
                raise AssertionError((view, part, pg.evaluate(ON), pg.evaluate("() => document.querySelector('#detail').hidden"))) from e
            pg.keyboard.press("Escape")
            pg.wait_for_function("() => document.querySelector('#detail').hidden", timeout=5000)
            back = pg.evaluate(ON)
            assert back["key"] == part["key"], (view, part, back)
            assert pg.evaluate("() => document.activeElement.getAttribute('tabindex')") == "0", view
        pg.close()


def test_i_goes_into_a_system_and_escape_comes_back_out_onto_it(browser, tmp_path):
    """Done 4, in both views: on the closed box factory, I goes Into it (the view of factory, the focus on its first
    part); Escape goes back out, with the focus on factory again. Backspace goes out as Escape does."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, view in enumerate(("view=dynamics&open=-", "view=blocks&open=-")):
            drawn(pg, url, view, i)
            step_to(pg, "(a) => a.matches('.node') && systemOf(a) === 'factory'")
            for out in ("Escape", "Backspace"):
                pg.keyboard.press("i")
                pg.wait_for_function(f"() => S.here === 'factory' && ({READY})() && ({IN_SVG})(document.activeElement)",
                                     timeout=DRAWN_S * 1000)
                assert pg.evaluate("() => new URLSearchParams(location.search).get('system')") == "factory", view
                pg.keyboard.press(out)
                pg.wait_for_function(f"() => S.here === '' && ({READY})() && ({IN_SVG})(document.activeElement)",
                                     timeout=DRAWN_S * 1000)
                on = pg.evaluate(ON)
                assert on["label"] == "factory" or "factory" in on["aria"], (view, out, on)
        assert not errors, errors
        pg.close()


def _contrast(a: str, b: str) -> float:
    """WCAG's contrast of two computed colours (rgb() or rgba(), opaque)."""
    def lum(c: str) -> float:
        r, g, b = (int(x) / 255 for x in re.findall(r"[\d.]+", c)[:3])
        f = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in (r, g, b)]
        return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_the_focus_ring_is_the_accent_and_stands_3_to_1_in_both_themes(browser, tmp_path):
    """Done 5: the part the keyboard is on has a ring (its outline, and its shape's outline) in the accent token, the
    selection's colour, at least 3:1 against the canvas, in the light and the dark theme."""
    ring = ("() => { const a = document.activeElement, st = getComputedStyle(a), hit = a.querySelector('.hit'); "
            "return { outline: st.outlineStyle + ' ' + st.outlineWidth, color: st.outlineColor, "
            "hit: hit && getComputedStyle(hit).stroke, accent: (() => { const p = document.createElement('p'); "
            "p.style.color = 'var(--accent)'; document.body.append(p); const c = getComputedStyle(p).color; p.remove(); return c; })(), "
            "bg: getComputedStyle(document.querySelector('svg.canvas')).backgroundColor, "
            "body: getComputedStyle(document.body).backgroundColor }; }")
    with served("software-factory", tmp_path) as url:
        for i, scheme in enumerate(("light", "dark")):
            pg = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme=scheme)
            drawn(pg, url, VIEWS[0], i)
            step_to(pg, "(a) => a.dataset.id === 'stock:backlog'")
            r = pg.evaluate(ring)
            bg = r["bg"] if not r["bg"].startswith("rgba(0, 0, 0, 0") else r["body"]
            assert r["outline"].startswith("solid") and r["color"] == r["accent"] and r["hit"] == r["accent"], (scheme, r)
            assert _contrast(r["color"], bg) >= 3, (scheme, r, _contrast(r["color"], bg))
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
                   // the panel but its legend (first now) and Q42's group words ('Goals off', 'No goal is off.', the
                   // same in every view), every fold opened: no control word in any of it
                   side: (() => { const s = document.querySelector('.side').cloneNode(true);
                                  s.querySelector('details.legend-box').remove();
                                  for (const x of s.querySelectorAll('h3.att-head, .att > .none')) x.remove();
                                  for (const d of s.querySelectorAll('details')) d.open = true;
                                  return s.textContent; })() };
        }""")
        assert r["unknown"] > 0 and r["unknownMarked"] == 0 and r["marked"]
        assert r["sum"].startswith(f"+{r['unknown']} of unknown polarity"), r["sum"]
        assert r["sizes"] == ["11px"], r["sizes"]                               # every marker at full size, never 8.5px
        assert r["hullStroke"] in ("none", None) or "0)" in r["hullStroke"], r["hullStroke"]   # a sector: a tint, no outline
        assert r["hullFill"] not in ("none", "rgba(0, 0, 0, 0)"), r["hullFill"]
        assert "Feedback loops" in r["side"] and not re.search(SD_WORDS, r["side"], re.I), r["side"][:600]
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


def held_requests(d: Path) -> None:
    """the-job with two modelling requests held, as the running demo has them: queue-goal-tolerance on
    goal.ci-upgrade-planned (the owner's), and one the rule tier has no certain change for."""
    from ergostat import model as mdl
    from ergostat.numbers import requests as rq
    from ergostat.store import Project
    p, now = Project(mdl.load(d)), time.time()
    for code, about, tier, why in [
            ("queue-goal-tolerance", "goal.ci-upgrade-planned", "owner", rq.OWNER["queue-goal-tolerance"]),
            ("no-description", "stock.backlog", "rule", "the rule tier has no certain change for it: no words to carry")]:
        k = rq.rid("craft", code, about)
        rq.event(p, k, "raised", {"source": "craft", "code": code, "about": about, "says": f"{code} on {about}",
                                  "level": "note", "tier": tier, "raised": now, "since": now, "change": None, "why": None})
        rq.event(p, k, "held", {"why": why, "owner": tier == "owner", "tier": tier})


def test_the_dynamics_wording_never_touches_a_requests_code_id_or_tier(browser, tmp_path):
    """The side list says a request in system dynamics' words in Dynamics, but its code, the part it is about and the
    tier holding it are the request's own, the same as in Blocks: never 'desired level.' or 'desired level-'."""
    from ergostat.numbers import requests as rq
    goal, unit = rq.rid("craft", "queue-goal-tolerance", "goal.ci-upgrade-planned"), rq.rid("craft", "no-description", "stock.backlog")
    assert goal == "80fe1e93e1"                            # the demo's request/80fe1e93e1
    with served("the-job", tmp_path, held_requests) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        said = {}
        for view in ("dynamics", "blocks"):
            drawn(pg, url, f"view={view}", 0)
            # (held requests sit in the folded Model housekeeping: read the card's text, open or folded)
            said[view] = pg.evaluate("""(ids) => ids.map((id) =>
              document.querySelector(`[data-inbox="request/${id}"]`)?.textContent || '')""", [goal, unit])
        for view, (g, u) in said.items():
            assert "queue-goal-tolerance" in g and "goal.ci-upgrade-planned" in g, (view, g)
            assert "desired level." not in g and "desired level-" not in g, (view, g)
            assert "rule tier" in u and "decision tier" not in u, (view, u)
        assert "desired level's desired level" not in said["dynamics"][0], said["dynamics"][0]
        assert "setpoint" not in said["dynamics"][0], said["dynamics"][0]     # its own words still in Dynamics'
        assert not errors, errors
        pg.close()


def test_a_stocks_panel_names_its_goal_and_what_serves_it_and_never_says_nothing_acts_on_it(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'stock:users'))")
        pg.wait_for_function("() => !document.querySelector('#detail').hidden && document.querySelector('#detail .what')", timeout=5000)
        pg.wait_for_function("() => document.querySelector('#detail').innerText.includes('desired users')", timeout=10000)
        text = pg.locator("#detail").inner_text()
        assert "users-growing" in text and "product-manager" in text, text[:1500]
        assert "nothing in the model acts" not in text, text[:1500]
        row = next(ln for ln in text.splitlines() if ln.startswith("desired users"))
        assert "product-manager in factory" in row and not re.search(SD_WORDS, row, re.I), row   # in the discipline's words
        assert not errors, errors
        pg.close()


def test_a_module_counts_its_loops_in_the_side_list_not_on_its_box_and_draws_no_port_squares(browser, tmp_path):
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=-", 0)
        r = pg.evaluate("""() => {
          const caps = Object.fromEntries([...document.querySelectorAll('svg.canvas .node[data-id^="system:"]')].map((n) =>
            [n.dataset.id.slice(7), [...n.querySelectorAll('text')].some((t) => /feedback loops? inside/.test(t.textContent))]));
          const rows = Object.fromEntries([...document.querySelectorAll('.looprow.sd-inside')].map((r) =>
            [r.querySelector('b').textContent, (r.textContent.match(/: (\\d+) feedback/) || [])[1]]));
          const dup = [...document.querySelectorAll('svg.canvas .node[data-id^="system:"]')].some((n) => {
            const names = [...n.querySelectorAll('.sd-port-name')].map((t) => t.dataset.part + t.dataset.side);
            return new Set(names).size !== names.length; });
          return { caps, rows, squares: document.querySelectorAll('svg.canvas .sd-port').length, dup };
        }""")
        # (its box says what it is; the side list counts each module's loops: as many rows as boxes with loops)
        assert r["caps"] and not any(r["caps"].values()), r
        assert r["rows"] and set(r["rows"]) <= set(r["caps"]) and all(v and v.isdigit() for v in r["rows"].values()), r
        assert r["squares"] == 0 and not r["dup"]
        pg.close()


@contextlib.contextmanager
def side_site(tmp_path: Path, asks: int):
    """The inbox's queue model, edited once (The model has an edit to fold), with ``asks`` requests waiting: none, 2 (a
    held action and a person asked) or 5 (one of each kind), served."""
    from ergostat import history
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project

    from .test_inbox import MODEL, seed
    from .test_numbers import queue_project
    d = tmp_path / "site"
    d.mkdir()
    p, snap = queue_project(d, text=MODEL)
    history.note(p)
    (d / "ergostat.yaml").write_text(MODEL.replace('hold: "<= 20"', 'hold: "<= 25"'))
    p = Project(mdl.load(d))
    assert history.note(p)
    if asks == 2:
        gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None})
        p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3, "ask": "review the queue"})
    elif asks:
        seed(p, snap)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise AssertionError("the page never answered") from None
                time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        proc.wait(10)


# the side panel with nothing chosen: its own headings in order (a fold's summary is one; an entry's own folds are
# not), each on screen or not, the
# legend open or not, each fold's state and summary, and any chart drawn in it (a legend's symbols are not charts)
SIDE = """() => {
  const side = document.querySelector('.side'), legend = side.querySelector('details.legend-box');
  const on = (el) => { const r = el.getBoundingClientRect(); return r.height > 0 && r.top >= 0 && r.bottom <= innerHeight; };
  const heads = [...side.querySelectorAll(':scope > h3, :scope > details > summary')].map((x) => ({ text: x.textContent.trim(), on: on(x),
    legend: x.parentElement === legend }));
  const fold = (sel) => { const d = side.querySelector(sel);
    return d && { open: d.open, sum: d.querySelector(':scope > summary').textContent }; };
  return { heads, open: !!legend?.open, loops: fold(':scope > details.loops'), model: fold(':scope > details.changes'),
           suggest: fold(':scope > details.suggest'), waiting: fold(':scope > details.waiting-fold'),
           asks: side.querySelectorAll('[data-inbox]').length,
           charts: [...side.querySelectorAll('svg')].filter((s) => !s.closest('.legend')).length };
}"""
SIDE_VIEWS = ["view=dynamics", "view=blocks", "view=process"]


def side_of(pg, url: str, view: str, asks: int = 0, reload: bool = False) -> dict:
    if reload:
        pg.reload()
    else:
        pg.goto(f"{url}/diagram?{view}", timeout=DRAWN_S * 1000)
    pg.wait_for_function(f"""() => document.querySelector('.side details.legend-box') &&
      document.querySelectorAll('.side [data-inbox]').length === {asks}""", timeout=DRAWN_S * 1000)
    if "process" not in view:                             # (the queue model has no item moved: no process map drawn)
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
    return pg.evaluate(SIDE)


@pytest.mark.parametrize("view", SIDE_VIEWS)
def test_the_side_panel_with_nothing_waiting_opens_on_the_legend_and_folds_the_rest(browser, tmp_path, view):
    with side_site(tmp_path, 0) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})      # a new page: fresh localStorage
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/diagram")                       # one chart remembered: with nothing chosen it is not drawn
        pg.wait_for_function("() => typeof rememberChart === 'function' && S.status", timeout=DRAWN_S * 1000)
        pg.evaluate("() => rememberChart('stock.queue')")
        for reload in (False, True):                    # the first visit, then the second
            r = side_of(pg, url, view, reload=reload)
            assert r["heads"][0]["text"].startswith("How to read it") and r["heads"][0]["legend"], r["heads"]
            assert r["open"] and r["heads"][0]["on"], r                                  # 1: first, open, on screen
            type_ = {"view=dynamics": "stock and flow diagram", "view=blocks": "block diagram", "view=process": "process map"}
            assert type_[view] in r["heads"][0]["text"], r["heads"][0]
            if r["suggest"] is None:                      # (the queue model makes no controller hint: one given here)
                pg.evaluate("""() => { (S.graph.attention || S.status.attention).push(
                  { level: 'hint', what: 'controller q', says: 'loop queue-short: a hint' }); S.redrawSide(); }""")
                r = pg.evaluate(SIDE)
            for f in ("loops", "model", "suggest"):                                       # 4: folded, with a count
                assert r[f] and r[f]["open"] is False and re.search(r"\d", r[f]["sum"]), (f, r[f])
            assert r["charts"] == 0, r                                                    # 5: no chart
        # 3: closed, it stays closed after a reload; opened again, it stays open
        pg.locator(".side details.legend-box > summary").click()
        pg.wait_for_function("() => localStorage.getItem('ergostat.legend') === 'closed'", timeout=5000)
        assert side_of(pg, url, view, reload=True)["open"] is False
        pg.locator(".side details.legend-box > summary").click()
        pg.wait_for_function("() => localStorage.getItem('ergostat.legend') === 'open'", timeout=5000)
        assert side_of(pg, url, view, reload=True)["open"] is True
        assert not errors, errors
        pg.close()


@pytest.mark.parametrize("view", SIDE_VIEWS)
def test_what_waits_for_you_comes_first_and_the_legend_second_both_on_screen(browser, tmp_path, view):
    with side_site(tmp_path, 2) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for reload in (False, True):
            r = side_of(pg, url, view, asks=2, reload=reload)
            assert r["heads"][0]["text"].startswith("Waiting for you 2"), r["heads"]
            assert r["heads"][1]["legend"] and r["open"], r["heads"]                     # 2: the legend second
            assert r["heads"][0]["on"] and r["heads"][1]["on"], r["heads"]               # both on screen at 1440x900
            assert r["waiting"] is None and r["charts"] == 0, r                           # 2 shown as they are
        assert not errors, errors
        pg.close()


def test_more_than_three_waiting_fold_into_one_line_that_opens_them(browser, tmp_path):
    with side_site(tmp_path, 5) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        r = side_of(pg, url, "view=blocks", asks=5)
        assert [h["text"] for h in r["heads"][:2]] == ["Waiting for you 5", "5 wait for you"], r["heads"]
        assert r["waiting"]["open"] is False and r["heads"][2]["legend"] and r["heads"][2]["on"], r
        pg.locator(".side details.waiting-fold > summary").click()
        assert pg.locator(".side details.waiting-fold [data-inbox] button").first.is_visible()
        pg.close()


# each row of the Blocks legend (by how its text starts) and where its symbol is drawn
BD_LEGEND_DRAWN = {
    "a block, its function": "g.bd-node:not(.bd-sensor):not(.bd-collector):not(.bd-sum):not(.bd-mux):not(.bd-demux)"
                             ":not(.bd-input):not(.bd-output):not(.bd-sampler):not(.bd-port)",
    "a sensor,": ".bd-sensor", "a collector,": ".bd-collector", "a sampler (T)": ".bd-sampler",
    "a zero-order hold": '.bd-node[data-id^="zoh:"]', "an In or Out port": ".bd-port", "a port mark": ".bd-portmark",
    "a block's tier": ".bd-tier", "not linear": '.bd-node:not(.bd-collector):not([data-id^="zoh:"]) text.bd-name',
    "a summing junction": ".bd-sum", "a take-off point": ".bd-dots .bd-dot", "a vector of signals": ".bd-vec, .bd-mux, .bd-demux",
    "an inner loop": ".bd-frame-cascade", "reference (its value)": ".bd-sig", "a loop's state": ".bd-sig .bd-state",
    "a system as one block": ".bd-subsystem, .bd-frame-system",
}


@pytest.mark.parametrize("example,view", [("software-factory", "view=blocks&open=*"), ("image-squeeze", "view=blocks"),
                                          ("image-squeeze", "view=blocks&open=*")])
def test_each_blocks_legend_row_is_a_symbol_drawn(browser, tmp_path, example, view):
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, view, 0)
        pg.wait_for_function("() => document.querySelector('.side .bd-legend')", timeout=DRAWN_S * 1000)
        rows = pg.evaluate("""(sels) => [...document.querySelectorAll('.side .bd-legend > span:nth-child(even)')].map((t) => {
          const key = Object.keys(sels).find((k) => t.textContent.startsWith(k));
          return [t.textContent.slice(0, 40), key ? !!document.querySelector('svg.canvas').querySelector(sels[key]) : null];
        })""", BD_LEGEND_DRAWN)
        assert rows and all(ok for _, ok in rows), rows                                 # 6: every row's symbol drawn
        assert len(rows) < len(BD_LEGEND_DRAWN), rows                                   # and not every symbol listed
        pg.close()


def test_a_loop_marker_moves_with_its_system_when_the_system_is_dragged(browser, tmp_path):
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
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


LOOP_SIGNS = """(label) => {
  // a loop's panel: each row of 'Around the loop' (its text, its sign), its marker's letters, and each row whose
  // connector is drawn here with the sign that connector shows (one sign per link across panels)
  const c = S.graph.causalLoops.find((x) => x.label === label);
  if (!c) return null;
  openCausal(c.name);
  const rows = [...document.querySelectorAll("#detail table.parts tr")].map((tr) => [tr.innerText.replace(/\\s+/g, " ").trim(),
    tr.querySelector("td.num").textContent]);
  const m = [...document.querySelectorAll("svg.canvas .loop-marker")].find((x) => (x.dataset.loops || "").split("|").includes(c.name));
  const drawnSigns = (c.around || []).map((r) => {
    const e = S.graph.edges.find((x) => x.kind === "connector" && (x.from ?? x.source) === r.from && (x.to ?? x.target) === r.to);
    const t = e && document.querySelector(`svg.canvas .edge[data-id="${CSS.escape(e.id)}"] text.polarity`);
    return e ? [r.from + " → " + r.to, t ? t.textContent : "?", r.sign ? sdSign(r.sign) : "?"] : null;
  }).filter(Boolean);
  return { rows, letter: m ? m.querySelector(".marker-letter").textContent : null, panel: document.querySelector("#detail").innerText,
           markers: [...document.querySelectorAll("svg.canvas .loop-marker text")].map((t) => t.firstChild?.textContent || ""), drawnSigns,
           alike: [...document.querySelectorAll("svg.canvas .marker-more")]
             .map((t) => [t.firstChild.textContent, t.querySelector("title")?.textContent || ""]) };
}"""


def test_a_loop_is_called_r_or_b_only_when_every_link_has_a_sign(browser, tmp_path):
    """software-factory's product system: R2's 'Around the loop' gives every link (all of them, through delivery
    too) a sign, or its marker reads '?'; each part by its plain name; a connector drawn here shows the row's sign;
    no marker reads '+1' (loops drawn alike: 'N alike')."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, v in enumerate(["system=product", "", "open=*"]):       # (open: every connector drawn, to compare)
            drawn(pg, url, v, i)
            r = pg.evaluate(LOOP_SIGNS, "R2")
            assert v != "open=*" or len(r["drawnSigns"]) >= 4, r["drawnSigns"]
            assert r and len(r["rows"]) >= 2, (v, r)
            unsigned = [t for t, sign in r["rows"] if sign not in ("+", "−")]
            assert not unsigned or r["letter"] == "?", (v, unsigned, r["letter"])
            if unsigned:
                assert "No sign on" in r["panel"], (v, r["panel"])
            named = [t for t, _ in r["rows"] if re.search(r"\b(stock|gap|flow|desired|term|system|shadow|stub):", t)]
            assert not named, (v, named)
            assert not [t for t in r["markers"] if re.search(r"\+\d$", t)], (v, r["markers"])
            assert all(shown == row for _, shown, row in r["drawnSigns"]), (v, r["drawnSigns"])
            assert all(re.fullmatch(r"\d+ alike", t) and re.search(r"[RB?]\d+ ", title) for t, title in r["alike"]), (v, r["alike"])
        assert not errors, errors
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
    return free_port()


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


def check_guide_steps(pg) -> None:
    """A section's name goes to its first frame; each dot is a 24px target named 'Step n of 13', and the
    current one, alone, is aria-current='step'."""
    from ergostat.guide import frames
    first = next(k for k, f in enumerate(frames()["frames"]) if f["part"] == "control")
    pg.locator(".g-part", has_text="Control: what we control").click()
    pg.wait_for_function(GUIDE_FRAME, arg=first, timeout=60000)
    assert re.search(rf"[?&]frame={first}\b", pg.url), pg.url
    dots = pg.evaluate("""() => [...document.querySelectorAll('.g-dot')].map((b) => {
        const r = b.getBoundingClientRect();
        return [r.width, r.height, b.getAttribute('aria-label'), b.getAttribute('aria-current')]; })""")
    assert len(dots) == 13
    assert all(w >= 24 and hgt >= 24 for w, hgt, _, _ in dots), dots
    assert [lab for _, _, lab, _ in dots] == [f"Step {n} of 13" for n in range(1, 14)]
    assert [k for k, (_, _, _, cur) in enumerate(dots) if cur is not None] == [first]
    assert dots[first][3] == "step"


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
        check_guide_steps(pg)
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
    check_guide_steps(pg)
    pg.close()
    assert not errors and not asked, (errors, asked)


SYS_BOXES = """(sel) => {
  const rgb = (c) => (c.match(/[\\d.]+/g) || []).slice(0, 4).map(Number);
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
                               return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const svg = document.querySelector(sel);
  return [...svg.querySelectorAll('g.node.k-system')].map((n) => {
    // every rect the box draws (its Into and Open buttons are transparent controls, not the box)
    const rects = [...n.querySelectorAll('rect')].filter((r) => !r.closest('.sys-btn') && getComputedStyle(r).display !== 'none')
      .map((r) => getComputedStyle(r).fill);
    const title = getComputedStyle(n.querySelector('.sys-title')).fill;
    return { rects, title, contrast: ratio(title, rects[0]) };
  }); }"""


def test_the_guides_last_frame_draws_its_boxes_as_the_live_diagram_does_and_says_it_is_drawing(browser, tmp_path):
    """Design review Q06: in light mode the last frame's system dynamics thumbnail draws each system box with the
    live diagram's fill, its text readable on it; and arriving there by the arrow, the stage says something at once,
    before the project's own graphs have come back (they are slowed here, so the wait is seen)."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 800}, color_scheme="light")
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        live = pg.evaluate(SYS_BOXES, "svg.canvas")
        assert live, "software-factory's dynamics view draws no closed system"
        fill = live[0]["rects"][0]
        pg.goto(url + "/guide?frame=12")
        pg.wait_for_function(GUIDE_FRAME, arg=12, timeout=60000)
        boxes = pg.evaluate(SYS_BOXES, ".g-view:first-child svg.g-canvas")
        assert boxes, "the thumbnail draws no system box"
        for b in boxes:
            assert b["rects"] and all(f == fill for f in b["rects"]), (fill, b)
            assert b["contrast"] >= 4.5, b
        pg.add_init_script("""(() => { const f = window.fetch;
          const later = (u, a) => new Promise((r) => setTimeout(r, 1500)).then(() => f(u, ...a));
          window.fetch = (u, ...a) => String(u).includes('/api/graph') ? later(u, a) : f(u, ...a); })()""")
        pg.goto(url + "/guide?frame=11&v=1")
        pg.wait_for_function(GUIDE_FRAME, arg=11, timeout=60000)
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(200)
        said = pg.locator(".g-stage").inner_text().strip()
        assert said and pg.locator(".g-stage").get_by_text(said.splitlines()[0]).first.is_visible(), repr(said)
        pg.wait_for_function(GUIDE_FRAME, arg=12, timeout=60000)
        assert pg.locator(".g-stage svg.g-canvas").count() == 2
        assert "Drawing your system" not in pg.locator(".g-stage").inner_text()        # gone once both are drawn
        assert not errors, errors
        pg.close()


def test_a_loop_lit_from_its_marker_lets_go_the_way_everything_else_does(browser, tmp_path):
    """The owner could not unselect a loop: clicking its marker again, the background, Escape, and the
    detail's close each let it go (no loop lit, nothing faded)."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
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


def test_the_goals_page_says_each_goals_word_as_the_server_does_live_and_from_a_snapshot(browser, tmp_path, monkeypatch):
    """One goal of each word (holding, off, open, unknown), drawn by goalRow: each row's status is /api/loops' word,
    on the page served and on the page read from a snapshot file, with nothing asked of a server."""
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.snapshot import build
    from tests.conftest import FOUR_GOALS
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "four"
    d.mkdir()
    (d / "ergostat.toml").write_text(FOUR_GOALS)
    p = Project(mdl.load(d))
    p.measurements.add("sensor/disk-usage", 70)
    rows = ("() => Object.fromEntries([...document.querySelectorAll('.page tr.click')]"
            ".map((r) => [r.querySelector('td b').textContent, r.querySelector('td .status').textContent]))")
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        loops = json.loads(urllib.request.urlopen(url + "/api/loops", timeout=30).read())
        want = {n: lp["word"] for n, lp in loops.items()}
        assert sorted(want.values()) == ["holding", "off", "open", "unknown"], want
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/loops")
        pg.wait_for_function("() => document.querySelectorAll('.page tr.click').length === 4", timeout=30000)
        live = pg.evaluate(rows)
        pg.goto(url + "/diagram?view=blocks")           # the side list's lines: the same word, holding left unsaid
        pg.wait_for_function("() => document.querySelectorAll('.side button.looprow[data-loop]').length > 0",
                           timeout=60000)
        side = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('.side button.looprow[data-loop]')]"
                           ".map((r) => [r.querySelector('b').textContent, r.querySelector('.status')?.textContent || '']))")
        assert side == {n: "" if w == "holding" else w for n, w in want.items()}, (side, want)
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)
    out = tmp_path / "snapshot.html"
    out.write_text(build(p))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    asked: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:"))
             else (asked.append(rt.request.url), rt.abort()))
    pg.goto(f"file://{out}#/loops")
    pg.wait_for_function("() => document.querySelectorAll('.page tr.click').length === 4", timeout=30000)
    offline = pg.evaluate(rows)
    pg.close()
    assert live == want and offline == want, (live, offline, want)
    assert not errors and not asked, (errors, asked)


BD_STATES = """() => Object.fromEntries(S.graph.nodes.filter((n) => n.role === 'comparator').map((n) => {
  const t = document.querySelector(`svg.canvas text.bd-sig[data-sum="${CSS.escape(n.id)}"]`), st = t?.querySelector('.bd-state');
  const wires = [...document.querySelectorAll('svg.canvas .bd-edge')].filter((e) => e.dataset.nodes.split(' ').includes(n.id))
    .map((e) => getComputedStyle(e.querySelector('.bd-wire')).stroke);
  const b = t?.getBBox(), cuts = b && S.layout.edges.some((le) => { const q = bdPts(le); return q.slice(1).some((p, i) =>
    Math.max(p.x, q[i].x) > b.x && Math.min(p.x, q[i].x) < b.x + b.width &&
    Math.max(p.y, q[i].y) > b.y && Math.min(p.y, q[i].y) < b.y + b.height); });
  return [n.loops[0], t && { text: t.textContent, state: st?.textContent || '', weight: st ? getComputedStyle(st).fontWeight : '',
    size: parseFloat(getComputedStyle(st || t).fontSize), wires: [...new Set(wires)], cuts }];
}))"""


def test_a_loops_state_is_printed_on_its_error_in_its_word_bold_when_off_and_never_by_colour(browser, tmp_path, monkeypatch):
    """Acceptance (blocks-status-without-colour): one goal of each word; in ?view=blocks&open=* each comparator's
    error label says e's value, /api/loops' error, and the goal's word when it is not holding, bold only when off;
    at least 11 px, clear of every wire; an off loop's wires are stroked as a holding loop's; the legend says so."""
    from ergostat import model as mdl
    from ergostat.store import Project
    from tests.conftest import FOUR_GOALS
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "four"
    d.mkdir()
    (d / "ergostat.toml").write_text(FOUR_GOALS)
    Project(mdl.load(d)).measurements.add("sensor/disk-usage", 70)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        loops = json.loads(urllib.request.urlopen(url + "/api/loops", timeout=30).read())
        assert sorted(lp["word"] for lp in loops.values()) == ["holding", "off", "open", "unknown"], loops
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&open=*", 0)
        pg.wait_for_function("() => document.querySelector('svg.canvas .bd-state')", timeout=DRAWN_S * 1000)
        got = pg.evaluate(BD_STATES)
        legend = pg.locator(".side .bd-legend").inner_text()
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)
    assert not errors, errors
    assert set(got) == set(loops) and all(got.values()), [n for n, x in got.items() if not x]   # every loop's error labelled
    for name, lp in loops.items():
        g, word = got[name], lp["word"]
        value = "" if lp["error"] is None else " = " + pg_number(lp["error"])
        assert g["state"] == value + ("" if word == "holding" else f" {word}"), (name, g, lp)   # 1: its value, its word
        assert g["weight"] == ("600" if word == "off" else "400"), (name, g)                      # bold only when off
        assert g["size"] >= 11 and not g["cuts"], (name, g)                                       # 3: readable, clear of wires
    off, holding = (next(n for n, lp in loops.items() if lp["word"] == w) for w in ("off", "holding"))
    assert got[off]["text"].endswith(" off") and got[off]["wires"] and got[off]["wires"] == got[holding]["wires"], got   # 2
    assert "a loop's state, on its error" in legend, legend                        # 4


SD_GAPS = """() => { const bad = getComputedStyle(document.body).getPropertyValue('--bad').trim(), probe = document.createElement('i');
  probe.style.color = bad; document.body.append(probe); const badRgb = getComputedStyle(probe).color; probe.remove();
  const gaps = Object.fromEntries([...document.querySelectorAll('svg.canvas g.node[data-id^="gap:"]')].map((n) => {
    const g = n.querySelector('.gap-word'), w = n.querySelector('.sd-word'), r = n.querySelector('.hit.sd-aux').getBBox();
    const spill = Math.max(0, ...[...n.querySelectorAll('text')].map((t) => t.getBBox())
      .map((b) => Math.max(r.x - b.x, b.x + b.width - r.x - r.width)));
    return [n.dataset.id.slice(4), { word: g?.dataset.word || 'holding', text: n.textContent, off: !!n.querySelector('.gap-off'), spill,
      stroke: getComputedStyle(n.querySelector('.hit.sd-aux')).stroke, fill: w ? getComputedStyle(w).fill : null }]; }));
  const markers = [...document.querySelectorAll('svg.canvas .loop-marker')].map((m) => ({ loops: m.dataset.loops.split('|'),
    off: m.classList.contains('goal-off'), stroke: getComputedStyle(m.querySelector('.marker-arc')).stroke }));
  const lit = [...document.querySelectorAll('svg.canvas .edge.in-loop .sd-connector')].map((e) => getComputedStyle(e).stroke);
  return { badRgb, gaps, markers, lit, layouts: S.layouts }; }"""


THREE_GOALS = """
name: three-goals
stocks:
  backlog: {unit: tickets, sensor: {manual: true}}
  queue: {unit: jobs, sensor: {manual: true}}
  inbox: {unit: mails, sensor: {manual: true}}
flows:
  arriving: {to: backlog}
  finishing: {from: backlog}
  queued: {to: queue}
  served: {from: queue}
  mailed: {to: inbox}
  read: {from: inbox}
goals:
  short-backlog: {stock: backlog, hold: "<= 5", tolerance: 1}
  short-queue: {stock: queue, hold: "<= 5", tolerance: 1}
  short-inbox: {stock: inbox, hold: "<= 5", tolerance: 1}
blocks:
  worker: {type: program, run: echo 1, goal: short-backlog, max: 3, out: flow.finishing}
  server: {type: program, run: echo 1, goal: short-queue, max: 3, out: flow.served}
  reader: {type: program, run: echo 1, goal: short-inbox, max: 3, out: flow.read}
"""


def test_a_goals_gap_in_dynamics_says_its_word_and_an_off_one_is_red_never_the_accent(browser, tmp_path, monkeypatch):
    """Acceptance (dynamics-off-status-on-the-part): a goal off, one holding and one never read (unknown), each
    closing a balancing loop, ?view=dynamics&open=*. 1: the off goal's gap says 'off' and how far, and its outline,
    its word and its balancing loop's marker compute to --bad; the holding goal's has no word and is not red. 2: the
    word on each gap is /api/loops' word. 3: a lit loop's lines and an off gap's outline differ in colour, light and
    dark. 4: a goal going off between polls is marked with no new layout."""
    from ergostat import model as mdl
    from ergostat.guide import FRAMES
    from ergostat.store import Project
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "three"
    d.mkdir()
    (d / "ergostat.yaml").write_text(THREE_GOALS)
    p, now = Project(mdl.load(d)), time.time()
    for i in range(6):
        p.measurements.add("sensor/backlog.main", 12, at=now - 50 + i * 10)
        p.measurements.add("sensor/queue.main", 2, at=now - 50 + i * 10)
    p.events.add("loop.off", item="short-backlog", data={"value": 12}, at=now - 50)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        loops = json.loads(urllib.request.urlopen(url + "/api/loops", timeout=30).read())
        assert {n: lp["word"] for n, lp in loops.items()} == {"short-backlog": "off", "short-queue": "holding",
                                                              "short-inbox": "unknown"}, loops
        off, holding = "short-backlog", "short-queue"
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=dynamics&open=*", 0)
        pg.wait_for_function("() => document.querySelector('svg.canvas .gap-off')", timeout=DRAWN_S * 1000)
        # the drawing's text at the width the sizes assume (CH, 6.7 px a character): this container's fallback font
        # is narrower than the owner's, and would hide a word overrunning its box
        pg.evaluate("""() => { const svg = document.querySelector('svg.canvas');
          const t = s('text', { 'font-family': 'monospace', 'font-size': 10 }, 'x'.repeat(40));
          svg.append(t); const px = 10 * CH / (t.getBBox().width / 40); t.remove();
          const st = document.createElement('style'); document.head.append(st);
          st.textContent = `svg.sd text, svg.sd tspan { font-family: monospace !important; font-size: ${px}px !important; }`; }""")
        got = pg.evaluate(SD_GAPS)
        assert set(got["gaps"]) == set(loops), (got["gaps"], loops)
        for name, lp in loops.items():                                                   # 2: the server's word
            assert got["gaps"][name]["word"] == lp["word"], (name, got["gaps"][name], lp)
        g = got["gaps"][off]                                                             # 1: off, and how far, in --bad
        assert g["off"] and " · off" in g["text"] and g["stroke"] == g["fill"] == got["badRgb"], (g, got["badRgb"])
        assert g["text"].endswith(" · off by 7 tickets") and loops[off]["off_by_words"] == "off by 7 tickets", (g, loops[off])
        u = got["gaps"]["short-inbox"]                                                   # a neutral word: printed, muted
        assert u["text"].endswith(" · unknown") and not u["off"] and u["fill"] not in (None, got["badRgb"]), u
        h = got["gaps"][holding]
        assert not h["off"] and h["fill"] is None and h["stroke"] != got["badRgb"] and " · " not in h["text"], h
        mine = [m for m in got["markers"] if any(f"gap:{off}" in c["nodes"] and c["polarity"] == "B" and c["name"] in m["loops"]
                                                 for c in pg.evaluate("() => S.graph.causalLoops"))]
        assert mine and all(m["off"] and m["stroke"] == got["badRgb"] for m in mine), got["markers"]
        assert not [m for m in got["markers"] if m["off"] and m not in mine], got["markers"]
        assert "a goal not holding: its word under its gap" in pg.evaluate("() => sdLegend().textContent")
        assert "'off by 36' in red" in next(f["text"] for f in FRAMES if f["id"] == "between")
        loop = next(m["loops"][0] for m in mine)                                         # 3: lit, it is the accent
        pg.evaluate("(n) => sdHighlight(n)", loop)
        for theme in ("light", "dark"):
            pg.emulate_media(color_scheme=theme)
            lit = pg.evaluate(SD_GAPS)
            assert lit["lit"] and lit["gaps"][off]["stroke"] == lit["badRgb"], (theme, lit)
            assert lit["gaps"][off]["stroke"] not in lit["lit"], (theme, lit["lit"], lit["gaps"][off])
        pg.evaluate("() => sdHighlight(null)")
        pg.emulate_media(color_scheme="light")
        layouts = got["layouts"]                                                         # 4: off between polls
        p.measurements.add("sensor/queue.main", 12)
        p.events.add("loop.off", item=holding, data={"value": 12})
        pg.wait_for_function(f"() => document.querySelector('svg.canvas g.node[data-id=\"gap:{holding}\"] .gap-off')",
                             timeout=60000)
        now = json.loads(urllib.request.urlopen(url + "/api/loops", timeout=30).read())
        after = pg.evaluate(SD_GAPS)
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)
    assert not errors, errors
    assert now[holding]["word"] == "off" and after["gaps"][holding]["word"] == "off", (now[holding], after["gaps"][holding])
    assert after["layouts"] == layouts, (after["layouts"], layouts)
    # with no new layout, each gap's box still holds its text: a word come since the layout widens it, never spills out
    assert all(gp["spill"] <= 0.5 for gp in (*got["gaps"].values(), *after["gaps"].values())), (got["gaps"], after["gaps"])


def pg_number(x: float) -> str:
    """A number as the page's fmt writes it: integers as they are, others to three figures, a real minus."""
    t = str(int(x)) if float(x).is_integer() else str(round(x)) if abs(x) >= 100 else f"{float(f'{x:.3g}'):g}"
    return t.replace("-", "−")


def test_one_goals_distance_reads_the_same_on_every_surface_outside_blocks(browser, tmp_path, monkeypatch):
    """A goal past its ceiling (backlog <= 5, tolerance 1, read at 12 tickets) says how far it is in one phrase, the
    state's: on the Loops page, the Dynamics side list, its gap's panel and its evidence (the loop's panel). Blocks
    keeps the discipline's e = r − y, its signed e charted, and never the phrase."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = charted(tmp_path, monkeypatch)
    p, now = Project(mdl.load(d)), time.time()
    for i in range(6):
        p.measurements.add("sensor/backlog.main", 12, at=now - 50 + i * 10)
    p.events.add("loop.off", item="short-backlog", data={"value": 12}, at=now - 50)
    want = "off by 7 tickets"
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        loops = json.loads(urllib.request.urlopen(url + "/api/loops", timeout=30).read())
        assert loops["short-backlog"]["off_by_words"] == want, loops["short-backlog"]
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/loops")
        cell = pg.locator('td[data-off="short-backlog"]')
        cell.wait_for(timeout=30000)
        said = {"loops page": cell.inner_text().strip()}
        drawn(pg, url, "view=dynamics", 0)
        side = "() => [...document.querySelectorAll('.side .att')].map((x) => x.textContent).join(' | ')"
        pg.wait_for_function(f"() => ({side})().includes('short-backlog')", timeout=30000)
        side = pg.evaluate(side)
        said["side list"] = want if f"desired backlog = 5: {want}" in side else side
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'gap:short-backlog'))")
        pg.wait_for_function("() => document.querySelector('#detail dl')?.textContent.includes('now ')", timeout=30000)
        gap = pg.locator("#detail dl").inner_text()
        said["gap"] = want if f"now {want}" in gap else gap
        pg.evaluate("() => openLoop('short-backlog')")
        pg.wait_for_function("() => [...document.querySelectorAll('#detail dt')].some((t) => t.textContent === 'how far')",
                             timeout=30000)
        rows = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('#detail dl dt')]"
                           ".map((t) => [t.textContent, t.nextElementSibling?.textContent]))")
        said["evidence"] = rows.get("how far")
        assert said == dict.fromkeys(said, want), said
        drawn(pg, url, "view=blocks", 1)                 # Blocks: the error as control writes it, e = r − y, signed
        pg.evaluate("() => openBlock(S.graph.nodes.find((n) => n.role === 'comparator'))")
        pg.wait_for_function(f"() => ({CHARTS.format('#detail .scope')})() >= 3", timeout=30000)
        names = pg.evaluate("() => [...document.querySelectorAll('#detail .scope .chart-name')].map((x) => x.textContent)")
        text = pg.locator("#detail").inner_text()
        assert "e" in names and "e = r − y" in text and want not in text, (names, text)
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def test_the_window_in_the_header_never_claims_more_than_the_record(browser, tmp_path, monkeypatch):
    """Acceptance (ui-the-window-in-the-header-never-claims-more-than): on a project whose record began 33 minutes
    ago, the header's window control says the window and how much of it is recorded ('Last 1h (33m recorded)'),
    and a suggestion giving a share '% of the time' says it is of the 33m recorded; on the 10m window, all recorded,
    the control says the window only. The Loops page's footnote says the same span."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "charted"
    d.mkdir()
    (d / "ergostat.yaml").write_text(CHARTED)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    p = Project(mdl.load(d))
    now = time.time()
    for i in range(198):                                   # 33 minutes of readings, the valve opening now and then
        t = now - 1980 + i * 10
        p.measurements.add("sensor/backlog.main", 8 + math.sin(i / 30), at=t)
        if i % 6 == 0:
            p.events.add("valve.opened", item="worker", data={"amount": 1, "flow": "finishing"}, at=t)
    p.events.add("loop.off", item="short-backlog", data={"value": 8}, at=now - 1900)   # off since, most of the record
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
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        when = "() => document.querySelector('#when .menu-btn')?.textContent || ''"
        pg.wait_for_function(f"() => ({when})().includes('recorded')", timeout=10000)
        label = pg.evaluate(when)
        assert re.fullmatch(r"Last 1h \(3[234]m recorded\)", label), label
        hints = pg.evaluate("() => [...document.querySelectorAll('.side .suggest .hint')].map((x) => x.textContent)")
        timed = [x for x in hints if "% of the" in x]
        assert timed, hints
        for x in timed:                                     # every share of the time says of what record
            assert "% of the time" not in x and re.search(r"% of the 3[234]m recorded", x), x
        pg.goto(url + "/loops")
        pg.wait_for_function("() => document.querySelector('.page p.note')?.textContent.includes('recorded')", timeout=10000)
        assert re.search(r"over the 3[234]m recorded", pg.locator(".page p.note").first.inner_text())
        assert re.fullmatch(r"Last 1h \(3[234]m recorded\)", pg.evaluate(when))
        pg.locator("#when .menu-btn").click()                # a window the record fills: the window alone
        pg.locator("#when .menu-pop").get_by_text("Last 10 minutes").click()
        pg.wait_for_function(f"() => ({when})() === 'Last 10m'", timeout=10000)
        assert not errors, errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)


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
        # parts chosen: each one's strip in the side panel, on one time axis; nothing chosen: no chart there
        pg.evaluate("() => closeDetail()")
        opened(pg, "() => { S.sel = new Set(['stock.backlog', 'flow.arriving']); markInteraction(document.querySelector('svg.canvas')); }",
               ".side .side-charts", 5)
        charts, cursors = hover_all(pg, ".side .side-charts")
        assert charts == cursors == 5, (charts, cursors)
        pg.evaluate("() => { S.sel.clear(); markInteraction(document.querySelector('svg.canvas')); }")
        pg.wait_for_function("() => !document.querySelector('.side .side-charts')", timeout=20000)
        # the blocks view: the loop's comparator opens its scope
        drawn(pg, url, "view=blocks", 1)
        opened(pg, "() => openBlock(S.graph.nodes.find((n) => n.role === 'comparator'))", "#detail .scope", 3)
        names = pg.evaluate("() => [...document.querySelectorAll('#detail .scope .chart-name')].map((x) => x.textContent)")
        assert names == ["y", "u", "e"], names
        assert hover_all(pg, "#detail .scope") == (3, 3)
        assert "Saturated" in pg.locator("#detail .scope dl").inner_text()
        # the Goals page: the sparkline opens the same scope
        pg.goto(url + "/goals")
        pg.locator("td.spark-cell").first.click()
        pg.wait_for_function(f"() => ({CHARTS.format('#detail .scope')})() >= 3", timeout=20000)
        # the Items page: the kind's flow, and under its table its cycle times
        pg.goto(url + "/items/ticket")
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


def test_a_goals_behaviour_holds_across_reloads_and_flapping_is_named(browser, tmp_path, monkeypatch):
    """Five reloads of the Loops page, each answered with a share past its bound that flips (4%, 0%, 4%, ...) and
    no change of status: the behaviour text stays the same; no cell says '0%' beside 'past', and a share under
    1% is '<1%'; a goal that went off 23 times in the window reads 'flapping' with its count. The scope's
    'past its bound' says what it is beside time off."""
    d = charted(tmp_path, monkeypatch)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    loaded = [0]
    row = {"stock": "backlog", "value": 5, "setpoint": "<= 8", "band": "", "error": 0, "status": "holding",
           "off_share": 0.003, "back_in": None, "times_off": 1, "observed": True}

    def loops(rt):                                       # the share past its bound flips with each answer, its status not
        loaded[0] += "perf=1" in rt.request.url
        perf = {"performance": {"constraint": {"share": 0.04 if loaded[0] % 2 else 0.0, "share_off": 0, "mean": 1, "worst": 1}}}
        rt.fulfill(status=200, content_type="application/json", body=json.dumps(
            {"steady": {**row, "perf": perf}, "flappy": {**row, "times_off": 23, "off_share": 0.05, "perf": perf}}))
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
        pg.route(lambda u: "/api/loops?" in u, loops)
        seen = []
        for _ in range(5):
            pg.goto(url + "/loops")
            pg.wait_for_function("() => { const c = [...document.querySelectorAll('td[data-perf]')];"
                                 " return c.length === 2 && c.every((x) => x.textContent); }", timeout=20000)
            cells = pg.evaluate("() => [...document.querySelectorAll('td')].map((c) => c.textContent)")
            perf = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('td[data-perf]')]"
                               ".map((c) => [c.dataset.perf, c.textContent]))")
            seen.append(perf["steady"])
            assert not [c for c in cells if "past" in c and re.search(r"(?<![\d<])0%", c)], cells
            assert "<1%" in cells and "0%" not in cells, cells
            assert "flapping" in perf["flappy"] and "23 crossings" in perf["flappy"], perf
        assert loaded[0] >= 5 and len(set(seen)) == 1, (loaded, seen)

        def flappy_after(kept):                          # kept words, by key suffix and age in ms; then a reload
            pg.evaluate("""(kept) => { const t = Date.now();
                for (const [k, age] of kept) localStorage.setItem(k.replace('$P', S.status.name + '.' + S.since),
                  JSON.stringify({ word: 'within its bound', at: t - age, seen: t - age })); }""", kept)
            pg.goto(url + "/loops")
            pg.wait_for_function("() => document.querySelector('td[data-perf=\"flappy\"]')?.textContent", timeout=20000)
            return pg.evaluate("() => document.querySelector('td[data-perf=\"flappy\"]').textContent")
        own = "ergostat.behaviour.$P.flappy"
        assert flappy_after([[own, 1000]]) == "within its bound"       # seen a moment ago: the change is held back
        # seen a day ago (older than the hold), or kept under another project or no project: the new word at once
        word = flappy_after([[own, 864e5], ["ergostat.behaviour.another.flappy", 0], ["ergostat.behaviour.flappy", 0]])
        assert "flapping" in word and "23 crossings" in word, word
        rows = pg.evaluate("() => performanceRows({ performance: { constraint: { share: 0.003, share_off: 0, mean: 1, worst: 1 } } })")
        past = dict(rows)["past its bound"]
        assert re.match(r"<1% of the (time|\S+ recorded) \(0% past its tolerance\)", past), past
        assert "by any amount" in past and "time off" in past, past
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def test_a_goals_behaviour_holds_across_refreshes_of_an_open_page(browser, tmp_path, monkeypatch):
    """The Loops page left open: each answer of its behaviours flips the share past its bound (4%, 0%, 4%, ...) with
    no change of status. Across refreshes 5 minutes apart (the page's clock jumped forward, as the server works each
    behaviour out again) the behaviour text stays the same."""
    d = charted(tmp_path, monkeypatch)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    loaded = [0]
    row = {"stock": "backlog", "value": 5, "setpoint": "<= 8", "band": "", "error": 0, "status": "holding",
           "off_share": 0.003, "back_in": None, "times_off": 1, "observed": True}

    def loops(rt):                                       # its share past its bound flips with each answer, its status not
        loaded[0] += "perf=1" in rt.request.url
        perf = {"performance": {"constraint": {"share": 0.04 if loaded[0] % 2 else 0.0, "share_off": 0, "mean": 1, "worst": 1}}}
        rt.fulfill(status=200, content_type="application/json", body=json.dumps({"steady": {**row, "perf": perf}}))
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
        pg.clock.install()
        pg.route(lambda u: "/api/loops?" in u, loops)
        pg.goto(url + "/loops")
        cell = "() => document.querySelector('td[data-perf=\"steady\"]')?.textContent"
        pg.wait_for_function(cell, timeout=20000)
        kept = "() => JSON.parse(localStorage.getItem('ergostat.behaviour.' + S.status.name + '.' + S.since + '.steady')).seen"
        seen = [pg.evaluate(cell)]
        for _ in range(3):                               # three refreshes, each 5 minutes after the last
            before, calls = pg.evaluate("() => Date.now()"), loaded[0]
            pg.clock.fast_forward(301_000)
            pg.wait_for_function(f"() => ({kept})() > {before}", timeout=20000)
            assert loaded[0] > calls, "asked again"
            seen.append(pg.evaluate(cell))
        assert loaded[0] >= 4 and len(set(seen)) == 1, (loaded, seen)
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def test_a_past_moment_shows_its_own_behaviour_at_once_and_keeps_the_live_one(browser, tmp_path, monkeypatch):
    """Live, the goal is within its bound (a fresh word kept). Moved to a past moment (S.at), whose answer is past its
    bound, the row shows that moment's word at once, not the kept live word; back to live, the live word is still the
    one kept, and is shown at once."""
    d = charted(tmp_path, monkeypatch)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    row = {"stock": "backlog", "value": 5, "setpoint": "<= 8", "band": "", "error": 0, "status": "holding",
           "off_share": 0.003, "back_in": None, "times_off": 1, "observed": True}

    def loops(rt):                                       # the past moment was past its bound, live is within it
        share = 0.04 if "at=" in rt.request.url else 0.0
        perf = {"performance": {"constraint": {"share": share, "share_off": 0, "mean": 1, "worst": 1}}}
        rt.fulfill(status=200, content_type="application/json", body=json.dumps({"steady": {**row, "perf": perf}}))
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
        pg.route(lambda u: "/api/loops?" in u, loops)
        pg.goto(url + "/loops")
        cell = "() => document.querySelector('td[data-perf=\"steady\"]')?.textContent || ''"
        pg.wait_for_function(f"() => ({cell})().startsWith('within')", timeout=20000)
        kept = "() => JSON.parse(localStorage.getItem('ergostat.behaviour.' + S.status.name + '.' + S.since + '.steady')).word"
        live = pg.evaluate(kept)
        assert live.startswith("within"), live
        pg.evaluate("() => { S.at = Date.now() / 1000 - 600; route(); }")
        pg.wait_for_function(f"() => ({cell})().startsWith('past')", timeout=5000)   # at once: well inside the hold
        assert pg.evaluate(kept) == live, "the live word kept, not the past one"
        pg.evaluate("() => { S.at = null; route(); }")
        pg.wait_for_function(f"() => ({cell})().startsWith('within')", timeout=5000)
        assert pg.evaluate(kept) == live
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def test_a_change_of_window_shows_that_windows_behaviour_at_once(browser, tmp_path, monkeypatch):
    """Over the last ten minutes the goal is within its bound (a fresh word kept). Switched to the last day, over
    which it went off 23 times, the row reads 'flapping (23 crossings in <the day's recorded span>)' at once, not the
    ten minutes' kept word nor their span; back to ten minutes, their own kept word is shown at once. Each window
    keeps its own word."""
    d = charted(tmp_path, monkeypatch)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    row = {"stock": "backlog", "value": 5, "setpoint": "<= 8", "band": "", "error": 0, "status": "holding",
           "off_share": 0.003, "back_in": None, "times_off": 1, "observed": True}

    def loops(rt):                                       # over a day it flapped; over the hour it went off once
        day = "since=1d" in rt.request.url
        perf = {"performance": {"constraint": {"share": 0.0, "share_off": 0, "mean": 1, "worst": 1}}}
        rt.fulfill(status=200, content_type="application/json",
                   body=json.dumps({"steady": {**row, "times_off": 23 if day else 1, "perf": perf}}))
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
        pg.route(lambda u: "/api/loops?" in u, loops)
        pg.goto(url + "/loops")
        cell = "() => document.querySelector('td[data-perf=\"steady\"]')?.textContent || ''"
        pg.wait_for_function(f"() => ({cell})().startsWith('within')", timeout=20000)
        switch = "(k) => setWindow(k)"                   # what the window menu calls (it puts window= in the address)
        pg.evaluate(switch, "10m")                       # (the record is longer than ten minutes, shorter than a day)
        pg.wait_for_function("() => S.status.window === 600 && S.status.at - S.status.first > 700", timeout=10000)
        pg.wait_for_function(f"() => ({cell})().startsWith('within')", timeout=5000)
        pg.evaluate(switch, "1d")
        pg.wait_for_function(f"() => ({cell})().startsWith('flapping (23 crossings')", timeout=5000)   # at once
        said = pg.evaluate(f"() => [({cell})(), `flapping (23 crossings in ${{dur(Math.min(86400, S.status.at - S.status.first))}})`]")
        assert said[0] == said[1] and "in 10m" not in said[0], said   # the day's span from the first answer, not the old window's
        pg.evaluate(switch, "10m")
        pg.wait_for_function(f"() => ({cell})().startsWith('within')", timeout=5000)
        kept = pg.evaluate("""() => ['10m', '1d'].map((k) =>
            JSON.parse(localStorage.getItem(`ergostat.behaviour.${S.status.name}.${k}.steady`)).word)""")
        assert kept[0].startswith("within") and kept[1].startswith("flapping"), kept
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


OFF_PIXELS = """(c, [x, y, w, hh]) => {      // a canvas region's pixels near the bad wash, and near the bad ink
  const css = getComputedStyle(document.documentElement), hex = (n) => { const s = css.getPropertyValue(n).trim().slice(1);
    return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16)); };
  const wash = hex("--bad-wash"), bad = hex("--bad");
  const near = (d, i, k, tol) => Math.abs(d[i] - k[0]) + Math.abs(d[i + 1] - k[1]) + Math.abs(d[i + 2] - k[2]) <= tol;
  const d = c.getContext("2d").getImageData(x, y, w, hh).data;
  let a = 0, b = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) { if (near(d, i, wash, 24)) a++; else if (near(d, i, bad, 60)) b++; }
  return [a, b];
}"""
CONTRAST = """(els, [prop, pseudo]) => els.map((el) => {   // each element's (or pseudo's) colour against the ground under it
  const rgb = (s) => s.match(/[\\d.]+/g).map(Number), lum = (c) => { const [r, g, b] = c.slice(0, 3).map((v) => v / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  let ground = null;
  for (let p = el.parentElement; p && !ground; p = p.parentElement) {
    const c = rgb(getComputedStyle(p).backgroundColor);
    if (c.length < 4 || c[3] > 0) ground = c;
  }
  const fg = lum(rgb(getComputedStyle(el, pseudo)[prop])), bg = lum(ground || [255, 255, 255]);
  return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
})"""


def test_off_in_the_scope_is_hatched_labelled_and_keyed_and_the_arrows_read_in_both_themes(browser, tmp_path, monkeypatch):
    """A loop's off stretch is hatched on its y, u and e charts (the bad ink's stripes over the wash, not the
    wash alone), labelled 'off' on the chart over the time axis, and keyed by a swatch of the same hatch and
    the word 'off' (no 'Red: off'). The lifecycle's arrows and the Guide's dots are 3:1 or more on their page,
    light and dark."""
    d = charted(tmp_path, monkeypatch)
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
        for scheme in ("light", "dark"):
            pg = browser.new_page(viewport={"width": 1500, "height": 1000}, color_scheme=scheme)
            errors: list[str] = []
            pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            pg.goto(url + "/loops")
            pg.evaluate("""() => { window.SAID = []; const f = CanvasRenderingContext2D.prototype.fillText;
                CanvasRenderingContext2D.prototype.fillText = function (t, ...r) {
                  SAID.push([String(t), this.canvas]); return f.call(this, t, ...r); }; }""")
            pg.locator("td.spark-cell").first.click()
            pg.wait_for_function(f"() => ({CHARTS.format('#detail .scope')})() >= 3 && document.querySelector('#detail .scope .off-key')",
                                 timeout=20000)
            pg.wait_for_timeout(300)
            for i in range(3):                     # y, u, e: each its off stretch hatched, along the top of its plot
                wash, ink = pg.evaluate(f"""() => {{ const u = document.querySelectorAll('#detail .scope .chart-plot')[{i}].plot;
                    return ({OFF_PIXELS})(u.ctx.canvas, [u.bbox.left, u.bbox.top + 2, u.bbox.width, 10]); }}""")
                assert wash > 30 and ink > 10, (scheme, i, wash, ink)
            assert pg.evaluate("""() => { const c = document.querySelectorAll('#detail .scope .chart-plot')[2].plot.ctx.canvas;
                return SAID.some(([t, k]) => t === 'off' && k === c); }"""), "the e chart, over the time axis, says 'off'"
            foot = pg.locator("#detail .scope .chart-foot")
            assert "Red: off" not in foot.inner_text() and foot.locator(".off-said").inner_text().strip() == "off"
            wash, ink = foot.locator("canvas.off-key").evaluate(f"(c) => ({OFF_PIXELS})(c, [0, 0, c.width, c.height])")
            assert wash > 10 and ink > 10, (scheme, wash, ink)
            pg.goto(url + "/item/ticket%2F1")
            pg.wait_for_selector(".track .arrow")
            arrows = pg.locator(".track .arrow").evaluate_all(CONTRAST, ["color", None])
            assert len(arrows) == 2 and min(arrows) >= 3, (scheme, arrows)
            pg.goto(url + "/guide")
            pg.wait_for_selector(".g-dot")
            dots = pg.locator(".g-dot:not(.on)").evaluate_all(CONTRAST, ["borderTopColor", "::before"])   # (the dot in its target)
            assert dots and min(dots) >= 3, (scheme, dots)
            pg.close()
            assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


@contextlib.contextmanager
def off_for(tmp_path: Path, span: float):
    """CHARTED's page, its record ``span`` seconds long and its loop off nearly all of it, the worker opening
    every 30s (served; the model is not run)."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / f"off-{int(span)}"
    d.mkdir()
    (d / "ergostat.yaml").write_text(CHARTED)
    env = {**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}    # (the caller has set it here too)
    p = Project(mdl.load(d))
    now = time.time()
    p.events.add("ergostat.started", source="ergostat", at=now - span)
    for i in range(int(span // 30)):
        t = now - span + 5 + i * 30
        p.measurements.add("sensor/backlog.main", 8 + i * 0.05, at=t)
        p.measurements.add("sensor/arriving.main", 6, at=t)
        p.events.add("valve.opened", item="worker", data={"amount": 1, "flow": "finishing"}, at=t)
    p.events.add("loop.off", item="short-backlog", data={"value": 8}, at=now - span + 6)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise AssertionError("the page never answered") from None
                time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        proc.wait(10)


RINGED = "() => [...document.querySelectorAll('svg.canvas .node.selected')].map((n) => n.dataset.id)"
TITLED = "(name) => (document.querySelector('#detail:not([hidden]) h2')?.firstChild?.textContent || '') === name"


def goal_named(tmp_path: Path, monkeypatch, boxed: bool) -> Path:
    """charted, its goal off now; boxed: every part inside a system 'desk' (drawn closed beside an empty 'other')."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = charted(tmp_path, monkeypatch)
    if boxed:
        y = re.sub(r"^(  [a-z-]+:)$", r"\1\n    system: desk", CHARTED, flags=re.M).replace("    system: desk\n    id:", "    id:")
        (d / "ergostat.yaml").write_text(y.replace("name: charted\n", "name: charted\nsystems:\n  desk:\n    description: the desk\n"
                                                   "  other:\n    description: nothing yet\n"))
    p = Project(mdl.load(d))
    p.measurements.add("sensor/backlog.main", 9, at=time.time())
    p.events.add("loop.off", item="short-backlog", data={"value": 9}, at=time.time() - 1400)   # off most of the window: a hint
    return d


@pytest.mark.parametrize("boxed", [False, True])
def test_a_goal_name_opens_its_evidence_and_rings_its_stock_or_its_summing_junction(browser, tmp_path, monkeypatch, boxed):
    """The off goal's name in Needs attention is a button: it opens the panel 'Evidence' opens, titled with the goal,
    and rings one shape, its stock in Dynamics and its summing junction in Blocks, opening the closed system that holds
    it. On /loops each row's first cell is a focusable button, and Enter on it opens the same panel."""
    d = goal_named(tmp_path, monkeypatch, boxed)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for view, ring in (("", "stock:backlog"), ("view=blocks", "sum:short-backlog")):
            drawn(pg, url, view, 1)
            if boxed:
                assert not pg.evaluate(f"() => !!document.querySelector('svg.canvas [data-id=\"{ring}\"]')"), "drawn closed first"
            pg.locator(".side .att button.name", has_text=f"{'loop' if view else 'goal'} short-backlog").click()
            pg.wait_for_function(TITLED, arg="short-backlog", timeout=20000)
            # (the closed box holding it is ringed until it is drawn open)
            pg.wait_for_function(f"(r) => JSON.stringify(({RINGED})()) === JSON.stringify([r])", arg=ring, timeout=60000)
            if boxed:
                assert pg.evaluate("() => S.graph.open") == ["desk"]
            pg.evaluate("() => { closeDetail(); choose([]); }")
            if not boxed and not view:                   # the name under Suggestions: the same
                pg.locator(".side details.suggest").evaluate("(d) => { d.open = true; }")
                pg.locator(".side .suggest .hint button.name").first.click()
                pg.wait_for_function(TITLED, arg="short-backlog", timeout=20000)
                assert pg.evaluate(RINGED) == [ring], pg.evaluate(RINGED)
                pg.evaluate("() => { closeDetail(); choose([]); }")
        pg.goto(url + "/loops")
        pg.wait_for_selector("tr.click")
        rows, names = pg.locator("tr.click"), pg.locator("tr.click > td:first-child > button.name")
        assert rows.count() == names.count() >= 1
        names.first.focus()
        assert pg.evaluate("() => document.activeElement.matches('td:first-child > button')")
        pg.keyboard.press("Enter")
        pg.wait_for_function(TITLED, arg="short-backlog", timeout=20000)
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


PHONE_GOALS = """
name: phone
stocks:
  queue:
    sensor:
      manual: true
  requests-handled:
    sensor:
      manual: true
goals:
  short-queue:
    stock: queue
    hold: "<= 5"
  requests-handled:
    stock: requests-handled
    hold: "<= 0"
flows:
  draining:
    from: queue
  handling:
    from: requests-handled
blocks:
  drainer:
    type: program
    run: echo 1
    goal: short-queue
    out: flow.draining
  handler:
    type: program
    run: echo 1
    goal: requests-handled
    out: flow.handling
"""


def test_on_a_phone_each_goal_is_a_card_its_value_against_its_bound_and_how_long_off(browser, tmp_path, monkeypatch):
    """At 390x844, in light and dark, the Loops page is one card per goal, off goals first: its name and status, then
    its value against its bound, how long it has been off and how soon it is usually back; nothing scrolls sideways."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "phone"
    d.mkdir()
    (d / "ergostat.yaml").write_text(PHONE_GOALS)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    p = Project(mdl.load(d))
    now = time.time()
    for t in (now - 3600, now - 30):                       # an hour of record
        p.measurements.add("sensor/queue.main", 3, at=t)
        p.measurements.add("sensor/requests-handled.main", 36, at=t)
    p.events.add("loop.off", item="requests-handled", data={"value": 4}, at=now - 3000)     # an earlier spell, 30s long
    p.events.add("loop.holding", item="requests-handled", data={"value": 0}, at=now - 2970)
    p.events.add("loop.off", item="requests-handled", data={"value": 36}, at=now - 2160)    # off these 36 minutes
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        for scheme in ("light", "dark"):
            pg = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme=scheme)
            errors: list[str] = []
            pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            pg.goto(url + "/loops")
            pg.wait_for_function("() => document.querySelectorAll('table.loops td.card').length === 2", timeout=20000)
            got = pg.evaluate("""() => [...document.querySelectorAll('table.loops td.card')].map((c) => {
                const r = c.getBoundingClientRect();
                return {text: c.innerText, left: r.left, right: r.right, shown: r.width > 0 && r.height > 0};
            })""")
            assert [c["text"].split("\n")[0] for c in got] == ["requests-handled · off", "short-queue · holding"], (scheme, got)
            assert got[0]["text"].split("\n")[1] == "36 against ≤ 0 · off 36m · usually back in 30s", (scheme, got)
            assert all(c["shown"] and c["left"] >= 0 and c["right"] <= 390 for c in got), (scheme, got)
            hidden = pg.evaluate("() => [...document.querySelectorAll('table.loops th, table.loops td:not(.card)')]"
                                 ".filter((x) => x.getBoundingClientRect().width > 0).length")
            assert hidden == 0, (scheme, hidden)
            widths = pg.evaluate("() => [document.documentElement, document.querySelector('main'), "
                                 "document.querySelector('.table-wrap')].map((x) => [x.scrollWidth, x.clientWidth])")
            assert all(sw == cw for sw, cw in widths), (scheme, widths)
            pg.close()
            assert not errors, errors
        # at a past moment, half an hour ago (as the time slider sets it): off 6 minutes then, not to the clock now
        pg = browser.new_page(viewport={"width": 390, "height": 844})
        pg.goto(url + "/loops")
        pg.wait_for_function("() => document.querySelectorAll('table.loops td.card').length === 2", timeout=20000)
        pg.evaluate(f"() => {{ S.at = {now - 1800}; route(); }}")
        pg.wait_for_function("() => / off 6m /.test(document.querySelector('table.loops td.card')?.innerText || '')",
                             timeout=20000)
        assert pg.locator("table.loops td.card").first.inner_text().split("\n")[1] == \
            "36 against ≤ 0 · off 6m · usually back in 30s"
        pg.close()
        pg = browser.new_page(viewport={"width": 1200, "height": 844})       # wider: the table as it was, no cards
        pg.goto(url + "/loops")
        pg.wait_for_function("() => document.querySelectorAll('table.loops tr.click').length === 2", timeout=20000)
        assert pg.evaluate("() => [...document.querySelectorAll('table.loops td.card')].every((c) => !c.offsetWidth)")
        assert pg.locator("table.loops th").first.is_visible()
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)


HINTS =("() => [...document.querySelectorAll('details.suggest .hint')].map((e) => [...e.childNodes]"   # (less its Evidence link)
         ".filter((n) => n.nodeName !== 'A').map((n) => n.textContent).join('').trim())")
LOOP_ENTRY = ("() => [...document.querySelectorAll('.att > div')].map((e) => e.textContent)"
              ".filter((t) => /^[a-z]+ · loop short-backlog/.test(t))")   # (after its state word)
CAUSE = re.compile(r"off \d+% of [^:]+: ([^.;]+)")


def test_a_suggestion_appears_when_it_has_a_verdict(browser, tmp_path, monkeypatch):
    """Before ten minutes of record nothing can say why a loop is off: no suggestion, and the goal's entry in
    Needs attention says when it will be said. After, the suggestion names its goal once, never defers, and
    says its cause in the same words on /diagram (both drawings) and /agents."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    with off_for(tmp_path, 300) as url:                      # 5m of record: no verdict yet
        for i, view in enumerate(("view=blocks", "view=dynamics")):
            drawn(pg, url, view, i)
            pg.wait_for_function(f"() => ({LOOP_ENTRY})().length > 0", timeout=20000)
            assert pg.evaluate(HINTS) == [], view
            (entry,) = pg.evaluate(LOOP_ENTRY)
            assert re.search(r"diagnosis in [45]m$", entry), (view, entry)
    with off_for(tmp_path, 1200) as url:                     # 20m: a verdict
        causes = []
        for i, view in enumerate(("view=blocks", "view=dynamics")):
            drawn(pg, url, view, i)
            pg.wait_for_function(f"() => ({HINTS})().length > 0", timeout=20000)
            hints = pg.evaluate(HINTS)
            for t in hints:
                assert "is said after" not in t and "diagnosis in" not in t, t
                assert t.count("short-backlog") <= 1, t
            (mine,) = [t for t in hints if "short-backlog" in t]
            assert CAUSE.search(mine), (view, hints)
            causes.append(CAUSE.search(mine).group(1))
            assert not any("diagnosis in" in t for t in pg.evaluate(LOOP_ENTRY)), view
        pg.goto(f"{url}/agents")
        pg.wait_for_function("() => document.querySelectorAll('ul.hints li').length > 0", timeout=20000)
        said = pg.evaluate("() => [...document.querySelectorAll('ul.hints li')].map((e) => e.textContent)")
        (mine,) = [t for t in said if "short-backlog" in t]
        assert "is said after" not in mine and mine.count("short-backlog") == 1, mine
        assert causes == [CAUSE.search(mine).group(1)] * 2, (causes, mine)
    pg.close()
    assert not errors, errors


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


FLOWS_SEEN = """() => {
  const seen = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 || r.height > 0; };
  const of = (sel) => [...document.querySelectorAll('svg.canvas ' + sel)].filter(seen).length;
  const where = (sel) => [...document.querySelectorAll('svg.canvas ' + sel)].map((el) => el.getAttribute('transform'));
  return { info: of('.edge .info'), aux: of('g.node.k-auxiliary'), pins: of('g.pins .pin'),
           markers: of('.loop-markers'), stocks: of('g.node.k-stock'), valves: of('g.node.k-valve'),
           pipes: of('.edge.pipe .pipe-out, .edge.pipe .sd-pipe-out, .edge.pipe path:not(.edge-hit)'),
           places: where('g.node.k-stock').join('|') };
}"""


def flows_menu(pg) -> None:
    pg.get_by_title("More: wrap, open or close every system, unpin").click()
    pg.get_by_text("Flows only").click()


def test_flows_only_hides_links_and_non_flow_parts(browser, tmp_path):
    """The ⋯ menu's Flows only: the pipes, their valves, stocks and clouds stay where they are; the rest is hidden."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        assert pg.evaluate("() => S.graph.kind") == "dynamics"
        pinned = pg.evaluate("""() => {
          const c = S.layout.children.find((c) => S.graph.nodes.find((n) => n.id === c.id)?.kind === 'auxiliary');
          S.pins[c.id] = pinFor(S.layout, S.graph, c.id, c.x, c.y); savePins(); return c.id; }""")
        drawn(pg, url, "open=*", 1)                                 # an auxiliary, pinned (kept in this browser)
        assert pg.locator(f"svg.canvas g.pins .pin[data-id={json.dumps(pinned)}]").count() == 1, pinned
        before = pg.evaluate(FLOWS_SEEN)
        assert before["info"] and before["aux"] and before["markers"] and before["stocks"] and before["pipes"], before
        assert before["pins"] == 1, before                          # (only it: nothing else here is pinned)
        flows_menu(pg)
        on = pg.evaluate(FLOWS_SEEN)
        assert pg.evaluate("() => document.body.classList.contains('flows-only')")
        assert on["info"] == on["aux"] == on["pins"] == on["markers"] == 0, on   # its pin hidden with it: nothing to unpin unseen
        assert (on["stocks"], on["valves"], on["pipes"]) == (before["stocks"], before["valves"], before["pipes"]), (before, on)
        assert on["places"] == before["places"], "the parts keep their places"
        flows_menu(pg)
        assert pg.evaluate(FLOWS_SEEN) == before, "off: as before"
        exported = "() => standaloneSvg(document.querySelector('svg.canvas'), '').text"
        aux = pg.evaluate("""() => [...document.querySelectorAll('svg.canvas g.node.k-auxiliary text')].map((t) => t.textContent)
                               .find((t) => t.length > 3 && document.querySelector('svg.canvas').textContent.split(t).length === 2)""")
        assert aux and f">{aux}<" in pg.evaluate(exported), aux
        flows_menu(pg)
        svg = pg.evaluate(exported)                   # the export is what is shown: flows only
        assert f">{aux}<" not in svg and "<path" in svg, aux
        flows_menu(pg)
        assert pg.evaluate(FLOWS_SEEN) == before, "off: as before"
        pg.close()
        assert not errors, errors


def test_flows_only_is_remembered(browser, tmp_path):
    """Flows only is kept per browser: a reload keeps it; turned off, a reload keeps it off."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        drawn(pg, url, "open=*", 0)
        flows_menu(pg)
        assert pg.evaluate("() => localStorage.getItem('ergostat.flowsOnly')") == "1"
        drawn(pg, url, "open=*", 1)
        assert pg.evaluate("() => document.body.classList.contains('flows-only')"), "on after a reload"
        assert pg.evaluate(FLOWS_SEEN)["info"] == 0
        flows_menu(pg)
        drawn(pg, url, "open=*", 2)
        got = pg.evaluate(FLOWS_SEEN)
        assert not pg.evaluate("() => document.body.classList.contains('flows-only')") and got["info"] and got["aux"], got
        pg.close()


# software-factory with its systems closed (the view the page opens with): six lines cross between factory and product,
# all drawn as connectors. Three carry a flow (the rate of deployed, driving fixes, regressions and shipped as a release
# goes live); three carry information only (the gaps of the product's goals on bugs-live, missing-ops and users, read
# by intake's flows: dynamics.py draws a serving block's read of its goal's stock through the goal's gap)
CLOSED_FLOW_LINKS = {"connector:flow:deployed->flow:fixes~", "connector:flow:deployed->flow:regressions~",
                     "connector:flow:deployed->flow:shipped~"}
CLOSED_INFO_LINKS = {"connector:gap:no-live-bugs->flow:filed-bugs~", "connector:gap:few-missing->flow:filed-features~",
                     "connector:gap:users-growing->flow:filed-features~"}
SEEN = "const seen = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 || r.height > 0; };"
LINKS_SEEN = "() => { " + SEEN + """
  return Object.fromEntries([...document.querySelectorAll('svg.canvas g.edge')].map((g) => {
    const line = g.querySelector('path.info, path.pipe-out'); return [g.dataset.id, !!line && seen(line)]; })); }"""
BOXES_SEEN = "() => { " + SEEN + " return [...document.querySelectorAll('svg.canvas g.node.k-system')].filter(seen).length; }"
PORTS_SEEN = "() => { " + SEEN + """
  return [...document.querySelectorAll('svg.canvas .sd-port-name')].filter(seen).map((t) => t.dataset.part).sort(); }"""
NOTE_SEEN = "() => { " + SEEN + """
  return [...document.querySelectorAll('svg.canvas #viewport .flows-none')].filter(seen).map((t) => t.textContent); }"""


def test_flows_only_keeps_flows_between_closed_systems(browser, tmp_path):
    """Systems closed: a line between two boxes that carries a flow stays, with the boxes; nothing says the level is
    empty of flows; off, everything is as before."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "", 0)
        assert pg.evaluate("() => S.graph.kind") == "dynamics" and not pg.evaluate("() => S.graph.open?.length"), "closed"
        before, boxes = pg.evaluate(LINKS_SEEN), pg.evaluate(BOXES_SEEN)
        assert set(before) == CLOSED_FLOW_LINKS | CLOSED_INFO_LINKS and all(before.values()), before
        assert boxes == 3, boxes
        flows_menu(pg)
        on = pg.evaluate(LINKS_SEEN)
        assert all(on[i] for i in CLOSED_FLOW_LINKS), on
        assert pg.evaluate(BOXES_SEEN) == boxes
        assert pg.evaluate(NOTE_SEEN) == [], "flows cross here: no note"
        flows_menu(pg)
        assert pg.evaluate(LINKS_SEEN) == before, "off: as before"
        pg.close()
        assert not errors, errors


def test_process_view_with_no_kinds_says_so_inside_the_canvas(browser, tmp_path):
    """big has no kinds of item: its Process view says so, and where to look instead, wholly inside the canvas at
    every width (it was drawn below it, at y=900, unseen); the link opens Dynamics."""
    inside = """() => {
      const e = [...document.querySelectorAll('.canvas-wrap .empty')].find((x) => x.textContent.includes('No kinds of item'));
      const t = e.querySelector('span') || e, r = t.getBoundingClientRect();
      const c = document.querySelector('svg.canvas').getBoundingClientRect();
      return { text: e.textContent, in: r.width > 0 && r.left >= c.left && r.right <= c.right && r.top >= c.top && r.bottom <= c.bottom,
               mid: Math.abs((r.top + r.bottom) / 2 - (c.top + c.bottom) / 2) < 40,
               r: [r.left, r.top, r.right, r.bottom], c: [c.left, c.top, c.right, c.bottom] }; }"""
    errors: list[str] = []
    with served("big", tmp_path) as url:
        for i, w in enumerate((1440, 1024, 600)):
            pg = browser.new_page(viewport={"width": w, "height": 900})
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"{url}/diagram?v={i}&view=process")
            pg.wait_for_function("() => [...document.querySelectorAll('.canvas-wrap .empty')].some((x) => "
                                 "x.textContent.includes('No kinds of item'))", timeout=DRAWN_S * 1000)
            got = pg.evaluate(inside)
            assert got["in"] and got["mid"], (w, got)
            assert got["text"] == "No kinds of item in big: its parts are counted by sensors. See Dynamics.", got
            if w == 1440:
                pg.locator(".canvas-wrap .empty a", has_text="Dynamics").click()
                pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
                assert "view=dynamics" in pg.url, pg.url
            pg.close()
            assert not errors, errors


def test_no_flows_line_is_under_the_boxes_and_seen(browser, tmp_path):
    """big's top level carries no flow between its systems: with Flows only, the line saying so lies under the boxes
    and within the viewport at 1440x900 (it was drawn above them, at y=-14)."""
    with served("big", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(url + "/", timeout=DRAWN_S * 1000)
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        flows_menu(pg)
        got = pg.evaluate("""() => { const t = [...document.querySelectorAll('svg.canvas #viewport .flows-none')];
          const boxes = [...document.querySelectorAll('svg.canvas g.node.k-system')].map((b) => b.getBoundingClientRect().bottom);
          return { n: t.length, text: t[0]?.textContent, r: t[0] && t[0].getBoundingClientRect().toJSON(),
                   below: Math.max(...boxes), boxes: boxes.length }; }""")
        assert got["n"] == 1 and got["text"].startswith("No flows at this level"), got
        r = got["r"]
        assert r["height"] > 0 and 0 <= r["top"] and r["bottom"] <= 900 and 0 <= r["left"] and r["right"] <= 1440, got
        assert got["boxes"] and r["top"] >= got["below"], got
        pg.close()


def test_flows_only_hides_information_links_between_closed_systems(browser, tmp_path):
    """Systems closed: a line that carries only information (a stock read across) is hidden, and only those; all six
    are drawn alike, as connectors, so what decides is the model (the part at each line's tail), not the class."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        drawn(pg, url, "", 0)
        kinds = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('svg.canvas g.edge')].map((g) => "
                            "[g.dataset.id, g.classList.contains('connector') && !g.classList.contains('pipe')]))")
        assert set(kinds) == CLOSED_FLOW_LINKS | CLOSED_INFO_LINKS and all(kinds.values()), kinds   # one drawing class
        flows_menu(pg)
        on = pg.evaluate(LINKS_SEEN)
        assert {i for i, shown in on.items() if shown} == CLOSED_FLOW_LINKS, on
        assert not any(on[i] for i in CLOSED_INFO_LINKS), on
        pg.close()


def test_flows_only_hides_ports_with_no_connection(browser, tmp_path):
    """Systems closed: a box's port whose every line is hidden is hidden too; turned off, its row is back."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        drawn(pg, url, "", 0)
        before = pg.evaluate(PORTS_SEEN)
        assert set(before) >= {"gap:no-live-bugs", "gap:few-missing", "gap:users-growing", "flow:filed-bugs",
                               "flow:filed-features", "flow:deployed", "flow:fixes", "flow:regressions", "flow:shipped"}, before
        flows_menu(pg)
        assert pg.evaluate(PORTS_SEEN) == ["flow:deployed", "flow:fixes", "flow:regressions", "flow:shipped"]
        flows_menu(pg)
        assert pg.evaluate(PORTS_SEEN) == before, "off: every row back"
        pg.close()


def without_flows_across(d: Path) -> None:
    """software-factory with deployed no longer driving the product's flows: only stocks are read across."""
    p = d / "product.yaml"
    t = p.read_text()
    t = t.replace(", {cause: +flow.deployed, instant: true}", "").replace("{cause: +flow.deployed, instant: true}, ", "")
    t = re.sub(r"\n    equation: [^\n]*flow\.deployed[^\n]*", "", t)
    assert "flow.deployed" not in t
    p.write_text(t)


def test_flows_only_says_when_a_level_has_no_flows(browser, tmp_path):
    """Systems closed and nothing crossing as a flow: the drawing says so where it is, and names the way to see them
    (open a system); off, it says nothing."""
    with served("software-factory", tmp_path, without_flows_across) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        drawn(pg, url, "", 0)
        assert pg.evaluate(NOTE_SEEN) == []
        assert pg.evaluate(LINKS_SEEN) and all(pg.evaluate(LINKS_SEEN).values())
        flows_menu(pg)
        assert not any(pg.evaluate(LINKS_SEEN).values())
        said = pg.evaluate(NOTE_SEEN)
        assert len(said) == 1 and "No flows" in said[0] and "Open a system" in said[0], said
        flows_menu(pg)
        assert pg.evaluate(NOTE_SEEN) == []
        pg.close()


LEGEND = """() => {
  const t = standaloneSvg(document.querySelector('svg.canvas'), ['software-factory', 'now']).text;
  const d = new DOMParser().parseFromString(t, 'image/svg+xml').documentElement;
  const g = [...d.children].find((c) => c.tagName === 'g' && (c.getAttribute('style') || '').includes('font-size:11px'));
  return g ? [...g.children].filter((c) => c.tagName === 'text').map((c) => c.textContent) : null; }"""
# each legend row, and what must be seen for it to be listed
LEGEND_SHOWS = {"stock": "g.node.k-stock", "flow": ".edge.pipe .pipe-out", "biflow": ".edge.pipe .pipe-tail",
                "source / sink": "g.node.k-cloud", "auxiliary": "g.node.k-auxiliary", "exogenous": "g.node.k-auxiliary",
                "connector +": ".edge .polarity", "connector −": ".edge .polarity", "reinforcing": ".loop-markers",
                "balancing": ".loop-markers"}


def test_flows_only_export_legend_lists_only_what_is_shown(browser, tmp_path):
    """The saved picture's legend, with Flows only, lists only what is drawn: no auxiliary, no loop, no connector sign
    nothing shown carries. Product open, factory closed: <deployed>'s lines into product's flows are kept."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        drawn(pg, url, "open=product", 0)
        assert pg.evaluate("() => S.graph.open") == ["product"]
        off = pg.evaluate(LEGEND)
        assert off and {"auxiliary", "reinforcing", "balancing", "connector +"} <= set(off), off   # all of it, off
        flows_menu(pg)
        on = pg.evaluate(LEGEND)
        assert on and {"stock", "flow", "source / sink"} <= set(on), on
        for row in on:
            sel = LEGEND_SHOWS[row]
            signs = pg.evaluate("(sel) => { " + SEEN + """ return [...document.querySelectorAll('svg.canvas ' + sel)]
                                  .filter(seen).map((el) => el.textContent); }""", sel)
            assert signs, (row, "listed, not shown")
            if row.startswith("connector"):
                assert row[-1] in signs, (row, signs)
        assert not {"auxiliary", "exogenous", "reinforcing", "balancing"} & set(on), on
        pg.close()


PRODUCT_GOALS = {"no-live-bugs": "filed-bugs", "few-missing": "filed-features", "users-growing": "filed-features"}
# each goal's desired level and gap as drawn: its canvas texts, and where the gap's drawn lines end
GOALS_DRAWN = """(goals) => Object.fromEntries(goals.map((k) => {
  const node = (id) => document.querySelector(`svg.canvas g.node[data-id="${id}"]`);
  const out = S.graph.edges.filter((e) => e.source === `gap:${k}` && document.querySelector(`svg.canvas g.edge[data-id="${e.id}"]`));
  return [k, { desired: !!node(`desired:${k}`), gap: node(`gap:${k}`)?.textContent || null,
               to: out.map((e) => S.graph.nodes.find((n) => n.id === e.target)?.label) }]; }))"""
PANEL_GOALS = "() => [...document.querySelectorAll('#detail dt')].filter((t) => t.textContent === 'desired level')" \
              ".map((t) => t.nextElementSibling.textContent)"


def test_every_product_goal_is_drawn_in_product_and_its_stock_panel_names_the_same(browser, tmp_path):
    """software-factory, ?system=product: each of the three goals is drawn as its desired level and its gap, the gap's
    line ending at the flow intake's block moves (named at product's edge); the users stock's panel names the goals the
    drawing draws, each bound as the goal writes it. A goal nothing acts on keeps its gap, marked 'no feedback' with no
    line, and the legend says what the mark means; no new critical layout fault either way."""
    def unserved(d: Path) -> None:                         # support reads users instead: nothing serves no-live-bugs now
        p = d / "factory" / "intake.yaml"
        p.write_text(p.read_text().replace("in: stock.bugs-live", "in: stock.users"))
    known = json.loads(KNOWN.read_text()).get("software-factory", {}) if KNOWN.exists() else {}
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=product", 0)
        got = pg.evaluate(GOALS_DRAWN, list(PRODUCT_GOALS))
        for k, flow in PRODUCT_GOALS.items():
            assert got[k]["desired"] and got[k]["gap"] and got[k]["to"] == [flow], (k, got[k])
            assert "no feedback" not in got[k]["gap"], got[k]
        assert critical(pg, "system=product", dict(known)) == []
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'stock:users'))")
        pg.wait_for_function(f"() => ({PANEL_GOALS})().length > 0", timeout=DRAWN_S * 1000)
        said = pg.evaluate(PANEL_GOALS)
        named = [x.split("(")[1].split(")")[0] for x in said]
        drawn_goals = pg.evaluate("() => S.graph.nodes.filter((n) => n.role === 'gap' && n.of === 'users').map((n) => n.goal)")
        assert named == drawn_goals == ["users-growing"], (said, drawn_goals)
        assert said[0].startswith("desired users ≥ 180 (users-growing), served by product-manager in factory"), said
        assert "no feedback" not in pg.evaluate("() => sdLegend().textContent")
        pg.close()
    with served("software-factory", tmp_path / "unserved", unserved) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=product", 0)
        got = pg.evaluate(GOALS_DRAWN, ["no-live-bugs"])["no-live-bugs"]
        assert got["desired"] and "→ no feedback" in got["gap"] and got["to"] == [], got
        assert "no feedback: nothing in the model acts on this gap" in pg.evaluate("() => sdLegend().textContent")
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'stock:bugs-live'))")
        pg.wait_for_function(f"() => ({PANEL_GOALS})().length > 0", timeout=DRAWN_S * 1000)
        assert pg.evaluate(PANEL_GOALS) == ["desired bugs-live ≤ 0 (no-live-bugs) (nothing in the model acts on its gap: "
                                            "no feedback closes it)"]
        assert critical(pg, "system=product", dict(known)) == []
        pg.close()
    assert not errors, errors


# Export PNG's picture: the standalone SVG rasterised as exportPng does (at 1x), and for each of its texts, how many
# dark pixels the image has where the text is (found by laying the same SVG in the page) that the same picture with no
# text at all lacks (the text's own ink: not a line under it, and nothing over it); and the image's corner colour
EXPORTED_PNG = """async () => {
  const out = standaloneSvg(document.querySelector('svg.canvas'), exportTitle());
  const raster = async (text) => {
    const img = new Image();
    await new Promise((ok, bad) => { img.onload = ok; img.onerror = bad;
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(text); });
    const c = document.createElement('canvas'); c.width = out.w; c.height = out.hgt;
    const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
    return ctx;
  };
  const bare = new DOMParser().parseFromString(out.text, 'image/svg+xml');
  bare.querySelectorAll('text').forEach((t) => t.remove());
  const ctx = await raster(out.text), ctx0 = await raster(new XMLSerializer().serializeToString(bare));
  const dark = (d, i) => d[i + 3] > 200 && d[i] + d[i + 1] + d[i + 2] < 420;
  const host = document.createElement('div'); host.style.cssText = 'position:fixed;left:0;top:0;z-index:99';
  host.innerHTML = out.text; document.body.append(host);
  const at = host.firstElementChild.getBoundingClientRect();
  const texts = [...host.querySelectorAll('text')].filter((t) => t.textContent.trim()).map((t) => {
    const r = t.getBoundingClientRect(), x = Math.max(0, Math.floor(r.left - at.left)), y = Math.max(0, Math.floor(r.top - at.top));
    const box = [x, y, Math.max(1, Math.ceil(r.width)), Math.max(1, Math.ceil(r.height))];
    const px = ctx.getImageData(...box).data, px0 = ctx0.getImageData(...box).data;
    let ink = 0;
    for (let i = 0; i < px.length; i += 4) if (dark(px, i) && !dark(px0, i)) ink++;
    const inside = r.left >= at.left - 0.5 && r.top >= at.top - 0.5 && r.right <= at.right + 0.5 && r.bottom <= at.bottom + 0.5;
    return [t.textContent, ink, inside];
  });
  host.remove();
  // what is seen through on the page (a loop marker's ground over the lines under it) is seen through in the picture
  const thin = (el) => +getComputedStyle(el).fillOpacity < 1;
  const shown = [...document.querySelectorAll('svg.canvas *')].filter((el) => el.checkVisibility() && thin(el)).length;
  const kept = (out.text.match(/fill-opacity:0\\.\\d+/g) || []).length;
  return { texts, corner: [...ctx.getImageData(1, 1, 1, 1).data], shown, kept };
}"""


def test_the_exported_png_shows_every_loop_name_the_values_and_its_legend_on_white_in_dark_mode(browser, tmp_path, monkeypatch):
    """Export PNG of the product system, with the page in dark mode: the picture is light (a white ground, dark ink);
    every loop name on screen and '225 users' are drawn legibly in it (not hidden under their own halos); the Blocks
    picture carries the Blocks legend's words, and both carry the title, date and window."""
    from ergostat import model as mdl
    from ergostat.store import Project

    def users(d: Path) -> None:
        monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))         # where served() points the server too
        Project(mdl.load(d)).measurements.add("sensor/users.main", 225.0, at=time.time() - 5)

    with served("software-factory", tmp_path, users) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=product", 0)
        assert pg.evaluate("() => getComputedStyle(document.body).backgroundColor") != "rgb(255, 255, 255)"   # dark, on screen
        pg.wait_for_function("() => [...document.querySelectorAll('svg.canvas text')].some((t) => t.textContent === '225 users')",
                             timeout=30000)
        loops = pg.evaluate("""() => [...document.querySelectorAll('svg.canvas .loop-marker .marker-name')]
                                 .filter((t) => t.getBBox().width > 0).map((t) => t.textContent)""")
        assert loops, "no loop names on screen"
        got = pg.evaluate(EXPORTED_PNG)
        assert got["corner"] == [255, 255, 255, 255], got["corner"]
        assert got["shown"] and got["kept"] >= got["shown"], (got["shown"], got["kept"])   # the lines under loop names unbroken
        assert all(t[2] for t in got["texts"]), [t for t in got["texts"] if not t[2]]   # nothing cut at the edge
        ink = {}
        for text, n, _ in got["texts"]:
            ink[text] = max(ink.get(text, 0), n)
        for want in [*loops, "225 users"]:
            assert ink.get(want, 0) >= 5, (want, ink.get(want))
        title = pg.evaluate("() => exportTitle()")
        assert "product" in title[0] and "window" in title[1] and all(ink.get(t, 0) >= 5 for t in title), (title, ink)

        drawn(pg, url, "system=product&view=blocks", 1)
        rows = pg.evaluate("() => [...blocksLegend().children].filter((_, i) => i % 2).map((e) => e.textContent)")
        got = pg.evaluate(EXPORTED_PNG)
        assert got["corner"] == [255, 255, 255, 255], got["corner"]
        said = " ".join(t for t, _, _ in got["texts"])
        assert len(rows) > 10 and all(r in said for r in rows), [r for r in rows if r not in said]
        assert all(t in said for t in pg.evaluate("() => exportTitle()"))
        assert all(n >= 5 for t, n, _ in got["texts"] if "summing junction" in t), got["texts"]
        assert all(t[2] for t in got["texts"]), [t for t in got["texts"] if not t[2]]   # no subscript cut at the edge
        assert not errors, errors
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
        assert got["text"].strip() not in ("…", "being worked out"), got                # it answered: charts, or "nothing measured"


LEFTOVER = """() => [...document.querySelectorAll('#detail *')].map((e) => e.textContent.trim())
  .filter((t) => t === '…' || t.endsWith(' …'))"""


def test_no_panel_shows_a_leftover_ellipsis(browser, tmp_path):
    """The product box, the users stock and marker R2 each open a panel that says its value is being worked out,
    or what it is, or why not: no element of it reads '…' or ends in ' …', from the click until it settles."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        def watched(what: str) -> list[str]:
            pg.wait_for_function("() => !document.querySelector('#detail').hidden", timeout=10000)
            seen = []
            for _ in range(24):                                # at once, and as each answer comes in (6 s)
                seen += [f"{what}: {t}" for t in pg.evaluate(LEFTOVER)]
                pg.wait_for_timeout(250)
            return seen

        drawn(pg, url, "", 0)                                  # every system closed: product is a box
        pg.wait_for_timeout(10000)
        click_part(pg, "system:product")
        bad = watched("product")
        assert pg.locator("#detail h2").inner_text() == "product"
        drawn(pg, url, "open=*", 1)
        fit(pg)
        click_part(pg, "stock:users")
        bad += watched("users")
        assert pg.locator("#detail h2").inner_text() == "users"
        r2 = pg.evaluate("() => (S.graph.causalLoops || []).find((c) => c.label === 'R2')?.name")
        assert r2, "no loop R2 drawn"
        pg.locator(f'.loop-marker[data-loop="{r2}"]').dispatch_event("click")
        bad += watched("R2")
        assert pg.locator("#detail .subtitle").inner_text() == r2
        assert pg.locator("#detail .strip.dominance").inner_text().strip(), "the loop says nothing of when it drives"
        assert not bad and not errors, (sorted(set(bad)), errors)
        pg.close()


def test_the_system_panel_names_stocks_to_aggregate(browser, tmp_path, monkeypatch):
    """A system whose chain of stocks no loop beyond each stock's own drove over the window says so in an
    `aggregate` row of its panel (from /api/dominance); a system with no such chain has no row."""
    from ergostat import model as mdl
    from ergostat.store import Project
    from tests.test_aggregation import CHAIN
    d = tmp_path / "plant"
    d.mkdir()
    (d / "ergostat.yaml").write_text(CHAIN.replace("stocks:\n", "stocks:\n  e:\n    unit: x\n    system: other\n    sensor:\n"
                                                   "      manual: true\n", 1)
                                     + "  oute:\n    from: e\n    system: other\n    driven-by: +stock.e\n    equation: stock.e / tau\n"
                                     + "  ine:\n    to: e\n    system: other\n    sensor:\n      manual: true\n")
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))       # the server is given it too
    p = Project(mdl.load(d))
    now = time.time()
    for i in range(61):
        t = now - 3600 + i * 60
        p.measurements.add("sensor/in.main", 10 + 8 * math.sin(i / 5), at=t)
        p.measurements.add("sensor/ine.main", 10 + 8 * math.cos(i / 5), at=t)
        for s in "abce":
            p.measurements.add(f"sensor/{s}.main", 2.0, at=t)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise AssertionError("the page never answered") from None
                time.sleep(0.2)
        got = json.loads(urllib.request.urlopen(url + "/api/dominance?since=1h&points=120", timeout=60).read())
        assert [(g["system"], g["stocks"]) for g in got["aggregate"]] == [("plant", ["stock.a", "stock.b", "stock.c"])], got
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=dynamics", 0)                        # everything closed: each system a module
        row = """() => { const dt = [...document.querySelectorAll('#detail dt')].find((x) => x.textContent === 'aggregate');
                         return dt ? dt.nextElementSibling.textContent : null; }"""
        pg.evaluate("() => openNode(S.graph.nodes.find((x) => x.kind === 'system' && x.label === 'plant'))")
        pg.wait_for_function(row, timeout=20000)
        assert pg.evaluate(row) == got["aggregate"][0]["said"]
        assert "stock.a, stock.b, stock.c: a candidate to aggregate into one delay" in pg.evaluate(row)
        asked = ("() => performance.getEntriesByType('resource')"
                 ".filter((r) => r.name.includes('/api/dominance') && r.responseEnd > 0).length")
        before = pg.evaluate(asked)
        pg.evaluate("() => openNode(S.graph.nodes.find((x) => x.kind === 'system' && x.label === 'other'))")
        pg.wait_for_function("() => document.querySelector('#detail h2')?.textContent === 'other'", timeout=5000)
        pg.wait_for_function(f"() => ({asked})() > {before}", timeout=20000)   # its own answer came, and gave it no row
        pg.wait_for_timeout(300)
        assert pg.evaluate(row) is None
        assert not errors, errors
        pg.close()
    finally:
        proc.terminate()
        proc.wait(10)


def test_a_valve_says_its_rate_inputs_and_equation_and_its_pipe_what_moves(browser, tmp_path):
    """Clicking a flow's valve (the bowtie) opens the valve: the rate of the flow, its inputs (the
    connectors into it, each signed) and its equation, or what of it is not known yet; clicking its
    pipe opens the flow: what moves, from where, to where."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        pg.get_by_role("button", name="Fit", exact=True).click()
        box = pg.locator('g.node[data-id="flow:regressions"] .hit').first.bounding_box()
        pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pg.wait_for_function("() => document.querySelector('#detail .kind')?.textContent === 'Valve' && "
                             "document.querySelector('#detail dl')", timeout=5000)   # (filled: it opens at once, then fills)
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


def seed_product_calibrations(d: Path) -> None:
    """The software factory's copy with a calibration kept of two of the product's parameters: churn-per-failing-op
    0.404 ± 0.116 against its declared 2 (the record's short-record note), fixes-per-ticket 0.01 ± 0.5."""
    from ergostat import model as mdl
    from ergostat.numbers import estimate as es
    from ergostat.numbers import version as ver
    from ergostat.store import Project
    old = os.environ.get("ERGOSTAT_HOME")
    os.environ["ERGOSTAT_HOME"] = str(d.parent / "home")                # where served() points the page's server
    try:
        p = Project(mdl.load(d))
        p.measurements.add("sensor/users.main", 120.0, at=time.time() - 33 * 60)    # a record begun 33 minutes ago
        short =("held, inconclusive: too little record to identify it (40 points fitted, under 60). Nothing says the "
                 "value written is wrong: it needs about 20m more record (as the record has gone so far)")
        f = es.path(p, ver.structure(p.model.spec), "parts")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({
            "churn-per-failing-op": {"parameter": "churn-per-failing-op", "scope": "parts", "value": 0.404, "se": 0.116,
                                     "n": 40, "refused": short},
            "fixes-per-ticket": {"parameter": "fixes-per-ticket", "scope": "parts", "value": 0.01, "se": 0.5, "n": 40,
                                 "refused": short}}))
    finally:
        if old is None:
            os.environ.pop("ERGOSTAT_HOME", None)
        else:
            os.environ["ERGOSTAT_HOME"] = old


VALVE_OF = "((n, f) => ['valve', 'disturbance'].includes(n.kind) && (n.flow || n.label) === f)"


def test_a_flow_with_no_value_says_why_and_an_estimate_with_no_basis_says_so(browser, tmp_path):
    """On the product's Dynamics view no flow's label is a bare '–' (one not measured says so, one that did not move
    says 0, and its panel how long nothing moved); the churn panel does not say 'Nothing says the value written is
    wrong' while the declared 2 lies outside 0.404 ± 3σ, and no interval more than ten times its estimate is printed."""
    with served("software-factory", tmp_path, seed_product_calibrations) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=product", 0)
        labels = pg.evaluate("""() => Object.fromEntries(S.graph.nodes.filter((n) => n.kind === 'valve' || n.kind === 'disturbance')
          .map((n) => [n.flow || n.label, [...document.querySelectorAll(`svg.canvas g.node[data-id="${n.id}"] text.sd-value`)]
                                            .map((t) => t.textContent.trim())]))""")
        assert {"regressions", "fixes", "shipped", "asks", "churn"} <= set(labels), labels
        assert not [f for f, t in labels.items() if "–" in t or not t], labels
        assert labels["regressions"] == ["not measured"], labels
        zero = [f for f, t in labels.items() if t and t[0].startswith("0")]
        assert zero, labels                                     # (the market's flows: its block has moved nothing yet)
        for flow in zero[:1] + ["regressions"]:
            pg.evaluate("(f) => openNode(S.graph.nodes.find((n) => VALVE_OF(n, f)))".replace("VALVE_OF", VALVE_OF), flow)
            pg.wait_for_function("(f) => new RegExp('the rate of ' + f).test(document.querySelector('#detail').textContent)", arg=flow,
                                 timeout=5000)
            pg.wait_for_timeout(300)
            rate = pg.evaluate("""() => { const dt = [...document.querySelectorAll('#detail dt')]
                                            .find((d) => d.textContent === 'rate, over the window');
                                          return dt ? dt.nextElementSibling.textContent : null; }""")
            assert rate == "not measured" if flow == "regressions" else re.match(r"^0 .*: no movement in 3[34]m$", rate or ""), (flow, rate)
        pg.evaluate("(f) => openNode(S.graph.nodes.find((n) => VALVE_OF(n, f)))".replace("VALVE_OF", VALVE_OF), "churn")
        pg.wait_for_function("() => document.querySelector('#detail table.calibrations')", timeout=10000)
        text, cal = pg.locator("#detail").inner_text(), pg.locator("#detail table.calibrations").inner_text()
        assert "Nothing says the value written is wrong" not in text, cal
        assert "the record so far rejects 2 but cannot yet settle a value" in cal.lower(), cal
        assert "0.404 ± 0.116" in cal, cal
        pg.evaluate("(f) => openNode(S.graph.nodes.find((n) => VALVE_OF(n, f)))".replace("VALVE_OF", VALVE_OF), "fixes")
        pg.wait_for_function("() => /fixes-per-ticket/.test(document.querySelector('#detail table.calibrations')?.textContent || '')",
                             timeout=10000)
        cal = pg.locator("#detail table.calibrations").inner_text()
        assert "not enough record yet" in cal and "± 0.5" not in cal, cal
        assert "Nothing says the value written is wrong" in cal, cal     # 0.4 lies within 0.01 ± 3σ: the note stays
        assert not errors, errors
        pg.close()


# ---- two views at once: one selection of model parts, lit in both (correspond.py, interact.js, split.js)

# (beside the checkout; where that cannot be written, as for a clone at /work in a container, the temporary folder)
SHOTS = Path(os.environ.get("SPLIT_SHOTS") or (ROOT.parent if os.access(ROOT.parent, os.W_OK) else Path(
    tempfile.gettempdir())) / "split-shots")
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
    fr.wait_for_function(PANE_READY, timeout=DRAWN_S * 1000)
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


STILL = """() => { const v = JSON.stringify([S.view, S.layout && S.layout.width, S.layout && S.layout.height]);
  const same = v === window.__still; window.__still = v; return same; }"""


def fit(page_or_frame):
    """Fit pressed, and waited on until the view stands still (two looks a tenth of a second apart agree), however
    slow the machine."""
    page_or_frame.get_by_role("button", name="Fit", exact=True).click()
    page_or_frame.wait_for_timeout(150)
    page_or_frame.evaluate("() => { window.__still = null; }")
    page_or_frame.wait_for_function(STILL, polling=100, timeout=30000)


def test_a_selection_is_model_parts_and_survives_switching_view(browser, tmp_path):
    """A part chosen in the dynamics view is chosen in the block diagram after switching: the same parts,
    lit there by the shapes that are them (a stock: its integrator and its output y)."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(120000)                 # its clicks wait for the shapes as long as a loaded machine needs
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "open=*", 0)
        fit(pg)
        click_part(pg, "stock:capabilities")
        pg.wait_for_function("() => S.sel.size > 0", timeout=30000)
        assert pg.evaluate("() => [...S.sel]") == ["stock.capabilities"]
        assert pg.evaluate(LIT) == ["stock:capabilities"]
        pg.locator(".toolbar .seg button", has_text="Blocks").click()
        pg.wait_for_function("() => S.graph?.kind === 'blocks' && document.querySelectorAll('svg.canvas g.node.selected').length > 0",
                             timeout=DRAWN_S * 1000)
        assert pg.evaluate("() => [...S.sel]") == ["stock.capabilities"]
        lit = ["out:stock.capabilities", "proc:stock.capabilities", "sen:stock.capabilities"]
        pg.wait_for_function(f"() => JSON.stringify(({LIT})()) === {json.dumps(json.dumps(lit, separators=(',', ':')))}", timeout=30000)
        # Shift adds and takes away, in the block diagram too; the background lets everything go (each waited on
        # until the selection says so, then checked exactly)
        fit(pg)
        sel = "() => JSON.stringify([...S.sel].sort())"
        pg.keyboard.down("Shift")
        pg.locator('g.node[data-id="ref:every-case"]').click()
        pg.keyboard.up("Shift")
        pg.wait_for_function(f"() => ({sel})() !== {json.dumps(json.dumps(['stock.capabilities'], separators=(',', ':')))}", timeout=30000)
        assert set(pg.evaluate("() => [...S.sel]")) == {"stock.capabilities", "goal.every-case.r"}
        pg.keyboard.down("Shift")
        pg.locator('g.node[data-id="ref:every-case"]').click()
        pg.keyboard.up("Shift")
        pg.wait_for_function("() => S.sel.size === 1", timeout=30000)
        assert pg.evaluate("() => [...S.sel]") == ["stock.capabilities"]
        pg.keyboard.press("Escape")
        pg.wait_for_function("() => S.sel.size === 0", timeout=30000)
        assert pg.evaluate("() => S.sel.size") == 0 and pg.evaluate(LIT) == []
        assert not errors, errors
        pg.close()


PANEL = "() => document.querySelector('#detail').hidden ? null : document.querySelector('#detail h2')?.textContent"


def test_a_panel_open_on_what_is_chosen_stays_open_across_a_switch_of_view_in_its_words(browser, tmp_path):
    """The stock quality chosen with its panel open, then Blocks: within a second of the block diagram being drawn,
    its output y_quality at the process output has the selection ring and the panel is still open, titled in the
    block diagram's words, 'output y_quality of P_service'; back in Dynamics, the stock's own panel. A flow's label
    clicked plainly opens the flow's panel at once, before its numbers come (held back here, as a slow server would),
    and filled when they do; carried to Blocks it is the actuating signal u_tuner, and a goal's reference, r = 0.93
    and its summing junction. (The acceptance names the demo at :8793; this is the same model, served fresh.)"""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(120000)
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=service", 0)
        fit(pg)

        def switch(to: str, shape: str) -> None:       # the view's button, waited on until that view is drawn
            pg.locator(".toolbar .seg button", has_text=to).click()
            pg.wait_for_function(f"() => S.graph?.kind === {to.lower()!r} && "
                                 f"document.querySelector('svg.canvas g.node[data-id=\"{shape}\"]')", timeout=DRAWN_S * 1000)
        y = "document.querySelector('svg.canvas g.node[data-id=\"out:stock.quality\"]')"
        click_part(pg, "stock:quality")
        pg.wait_for_function(f"() => ({PANEL})() === 'quality'", timeout=30000)
        switch("Blocks", "out:stock.quality")
        pg.wait_for_function(f"() => {y}.classList.contains('selected') && /y/.test(({PANEL})() || '')", timeout=1000)
        ring = pg.evaluate(f"() => getComputedStyle({y}.querySelector('.hit')).stroke")
        assert ring == pg.evaluate(ACCENT), ring
        assert pg.evaluate(PANEL) == "output y_quality of P_service"
        assert pg.evaluate("() => [...S.sel]") == ["stock.quality"]
        switch("Dynamics", "stock:quality")
        pg.wait_for_function(f"() => ({PANEL})() === 'quality'", timeout=5000)
        # a flow's label, clicked plainly: its panel at once, while its numbers are held back; filled when they come
        held = []
        pg.route("**/api/part/flow/**", lambda r: held.append(r))
        fit(pg)
        pg.locator('g.node[data-id="flow:quality-steps"] text.sd-name').click()
        pg.wait_for_function(f"() => ({PANEL})() === 'quality-steps'", timeout=1000)
        assert pg.evaluate("() => [...S.sel]") == ["flow.quality-steps"] and held
        for r in held:
            r.continue_()
        pg.unroute("**/api/part/flow/**")
        pg.wait_for_function("() => /rate, over the window/.test(document.querySelector('#detail').textContent)", timeout=30000)
        assert pg.evaluate(PANEL) == "quality-steps"
        switch("Blocks", "blk:tuner")
        pg.wait_for_function(f"() => ({PANEL})() === 'actuating signal u_tuner'", timeout=5000)
        # the race: the flow's numbers come only after the switch to Blocks; the Dynamics answer, arriving late,
        # does not paint its valve panel over the Blocks one
        switch("Dynamics", "flow:quality-steps")
        held.clear()
        pg.route("**/api/part/flow/**", lambda r: held.append(r))
        fit(pg)
        pg.locator('g.node[data-id="flow:quality-steps"] text.sd-name').click()
        pg.wait_for_function(f"() => ({PANEL})() === 'quality-steps'", timeout=5000)
        assert held
        switch("Blocks", "blk:tuner")
        pg.wait_for_function(f"() => ({PANEL})() === 'actuating signal u_tuner'", timeout=5000)
        with pg.expect_response(lambda r: "/api/part/flow/" in r.url):
            for r in held:
                r.continue_()
        pg.unroute("**/api/part/flow/**")
        pg.wait_for_timeout(500)                       # the late answer handled (it has come; its handler is a tick)
        assert pg.evaluate(PANEL) == "actuating signal u_tuner"
        assert pg.evaluate("() => document.querySelector('#detail .kind')?.textContent") != "Valve"
        # a reference chosen in Blocks, carried to Dynamics (its desired level) and back
        pg.locator('g.node[data-id="ref:quality-held"]').dispatch_event("click")
        pg.wait_for_function("() => [...S.sel].join() === 'goal.quality-held.r' && !document.querySelector('#detail').hidden", timeout=5000)
        switch("Dynamics", "desired:quality-held")
        pg.wait_for_function(f"() => ({PANEL})() === 'desired quality'", timeout=5000)
        switch("Blocks", "ref:quality-held")
        pg.wait_for_function(f"() => ({PANEL})() === 'reference r = 0.93 and its summing junction'", timeout=5000)
        # a panel closed before the switch stays closed, though its part is still chosen
        pg.locator("#detail button.close").click()
        assert pg.evaluate(PANEL) is None and pg.evaluate("() => S.sel.size") == 1
        switch("Dynamics", "desired:quality-held")
        pg.wait_for_timeout(500)
        assert pg.evaluate(PANEL) is None and pg.evaluate(LIT) == ["desired:quality-held"]
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
            ["out:stock.capabilities", "proc:stock.capabilities", "sen:stock.capabilities"]
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
        avail.locator("tr", has_text="quality-held").first.get_by_role("link", name="quality-held process", exact=True).click()
        pg.wait_for_function("() => S.graph?.kind === 'blocks' && !document.querySelector('#detail').hidden", timeout=60000)
        pg.wait_for_function("() => /The control loop of goal quality-held/.test(document.querySelector('#detail').textContent)",
                             timeout=60000)
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


def test_a_remote_boxs_panel_dims_a_stale_measure_and_shows_its_age(browser, tmp_path, monkeypatch):
    """A closed remote module's panel lists its measures under the remote note (SPEC §4c): a fresh one with its number,
    a stale one dimmed with its age (never the bare number), one it does not serve as not served, never charted."""
    from ergostat import model as mdl
    from ergostat.remote import cache, serve
    from ergostat.store import Project
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))       # as served() runs the page

    def edit(d):
        y = d / "ergostat.yaml"
        y.write_text(y.read_text().replace("    every: 10s\n", "    every: 10s\n    show: [stock.open, flow.resolved, stock.waiting]\n"))
        shutil.copytree(ROOT / "examples" / "remote-pair" / "incidents", tmp_path / "incidents-src")
        body, now = serve.model(tmp_path / "incidents-src" / "ergostat.yaml"), time.time()
        c = cache.folder("support", d, "incidents")
        (c / cache.MODEL).write_text(json.dumps({**body, "fetched": now}))
        (c / cache.STATUS).write_text(json.dumps({"checked": now, "ok": True, "version": body["version"], "answered": now,
                                                  "read": now, "read_ok": True, "next": now + 3600}))
        p = Project(mdl.load(d))
        p.measurements.add("sensor/incidents-open.main", 4.0, at=now - 5)               # fresh
        p.measurements.add("sensor/incidents-resolved.remote", 2.5, at=now - 3600)      # an hour old
    with served("remote-pair/support", tmp_path, edit) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        asked: list[str] = []
        pg.on("request", lambda r: asked.append(r.url) if "/api/series" in r.url else None)
        drawn(pg, url, "", 0)                                  # the default view: the remote a closed module
        rows = pg.evaluate("""async () => {
          const n = S.graph.nodes.find((x) => x.kind === "system" && x.label === "incidents");
          await openNode(n);
          await new Promise((r) => setTimeout(r, 1500));
          const note = document.querySelector("#detail .remote-note");
          const t = document.querySelector("#detail .remote-measures");
          return { after: !!(note && t && (note.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING)),
                   rows: [...(t ? t.querySelectorAll("tr") : [])].map((r) => ({ stale: r.classList.contains("measure-stale"),
                     label: r.cells[0].textContent, value: r.cells[1].textContent })) };
        }""")
        assert rows["after"], rows                             # listed under the remote note
        got = {r["label"]: r for r in rows["rows"]}
        assert set(got) == {"incidents-open", "incidents-resolved", "incidents-waiting"}, got
        fresh, old, gone = got["incidents-open"], got["incidents-resolved"], got["incidents-waiting"]
        assert not fresh["stale"] and fresh["value"].startswith("4") and "old" not in fresh["value"], fresh
        assert old["stale"] and old["value"].startswith("last ") and old["value"].endswith(" · 1h old"), old
        assert gone["stale"] and gone["value"] == "not served", gone
        assert asked and not [u for u in asked if "incidents-waiting" in urllib.parse.unquote(u)], asked
        assert pg.evaluate("""() => moduleCharts({ charted: [{ part: "stock:incidents-open", unchecked: true },
                                                             { part: "stock:incidents-waiting", missing: true }] })""") is None
        assert not errors, errors
        pg.close()


# ---- one large system's lines routed in parts (routeparts.js: partGroups)

PART_GROUPS = "([c, a, g]) => partGroups(c, a, g)"
CAP = 100                                              # routeparts.js GROUP_CAP and SHARED_CAP
HUB_OVER = 8                                           # routeparts.js HUB


@pytest.fixture(scope="module")
def parts_page(browser, tmp_path_factory):
    """A served page, for partGroups on lines made up here (no DOM, no router: it is pure)."""
    with served("software-factory", tmp_path_factory.mktemp("parts")) as url:
        pg = browser.new_page()
        pg.goto(f"{url}/diagram", timeout=DRAWN_S * 1000)
        pg.wait_for_function("() => typeof partGroups === 'function'", timeout=DRAWN_S * 1000)
        yield pg
        pg.close()


def chain(parts: int = 261) -> tuple[list[dict], dict, dict]:
    """A straight chain along x, each part joined to the next (conns[i] from the i-th to the next); the parts' and the
    lines' ids in no order of x, so that only their positions put them in order."""
    import random
    ids = [f"p{n:03d}" for n in random.Random(3).sample(range(parts), parts)]
    lines = [f"l{n:03d}" for n in random.Random(4).sample(range(parts - 1), parts - 1)]
    conns = [{"id": lines[i], "s": ids[i], "t": ids[i + 1]} for i in range(parts - 1)]
    return conns, {p: [i * 10, 0] for i, p in enumerate(ids)}, {c["id"]: "s0" for c in conns}


def check_parts(conns: list[dict], given: dict, at: dict, out: dict) -> dict:
    """The guarantees (routeparts.js) on a grouping: (i) each group but "" within the cap; (ii) a part's lines outside ""
    all in one group; every line in "" there for a reason: it touches a hub of its group, an end has no position, its
    ends lie in two different groups' parts (a band's edge), or it was in "" at a part with a line of another group
    given. Its group sizes, by name."""
    sizes: dict[str, int] = {}
    for c in conns:
        sizes[out[c["id"]]] = sizes.get(out[c["id"]], 0) + 1
    assert all(n <= CAP for g, n in sizes.items() if g), sizes                                       # (i)
    part_group: dict[str, set] = {}
    for c in conns:
        if out[c["id"]]:
            for p in (c["s"], c["t"]):
                part_group.setdefault(p, set()).add(out[c["id"]])
    assert all(len(x) == 1 for x in part_group.values()), {p: x for p, x in part_group.items() if len(x) > 1}   # (ii)
    degree: dict[tuple, int] = {}
    for c in conns:
        for p in {c["s"], c["t"]}:
            degree[(given[c["id"]], p)] = degree.get((given[c["id"]], p), 0) + 1
    grouped = {p for c in conns if given[c["id"]] for p in (c["s"], c["t"])}
    for c in conns:
        if out[c["id"]]:
            continue
        g, s, t = given[c["id"]], c["s"], c["t"]
        hub = degree[(g, s)] > HUB_OVER or degree[(g, t)] > HUB_OVER
        # (a band's edge: its ends not both in one group. Not "in two groups": a part may join a band with no line to
        # its parts yet, both its lines then cross, and it is in no group itself. Every line in "" passes this, so the
        # tests also count the groups)
        bands = not (s in part_group and t in part_group and part_group[s] == part_group[t])
        edge = g == "" and (s in grouped or t in grouped)
        assert hub or s not in at or t not in at or bands or edge, f"{c['id']} in \"\" for no reason"
    return sizes


def bound(n: int) -> int:                               # guarantee (iii): the most groups a group of n lines is parted into
    return 2 * -(-n // CAP) + 1


def test_a_chain_over_the_cap_is_cut_into_bands(parts_page):
    conns, at, given = chain()
    r = parts_page.evaluate(PART_GROUPS, [conns, at, given])
    sizes = check_parts(conns, given, at, r["groups"])
    bands = sorted(g for g in sizes if g)
    assert len(bands) >= 3 and all(g.startswith("s0#") for g in bands), sizes
    shared = sorted(i for i, g in r["groups"].items() if g == "")
    assert len(shared) == len(bands) - 1, (shared, sizes)            # one line at each cut, and only those
    assert sizes == {"s0#0": CAP, "s0#1": CAP, "s0#2": 58, "": 2}, sizes   # each band as full as the cap lets it
    assert len(sizes) <= bound(len(conns)) and not r["free"]
    # the same inputs as sets: the lines in another order, the positions in reverse key order
    import random
    mixed = conns[:]
    random.Random(7).shuffle(mixed)
    again = parts_page.evaluate(PART_GROUPS, [mixed, dict(reversed(list(at.items()))), given])
    assert again == r


def test_a_part_with_more_than_eight_lines_is_a_hub_and_its_lines_alone_go_to_the_shared_group(parts_page):
    conns, at = [], {"hub": [-50, 300]}
    for k in range(12):                                 # 12 chains of 11 lines, and a line from the hub to each one's first
        for i in range(12):
            at[f"c{k:02d}p{i:02d}"] = [i * 10, k * 50]
        conns += [{"id": f"c{k:02d}l{i:02d}", "s": f"c{k:02d}p{i:02d}", "t": f"c{k:02d}p{i + 1:02d}"} for i in range(11)]
        conns.append({"id": f"h{k:02d}", "s": "hub", "t": f"c{k:02d}p00"})
    given = {c["id"]: "s0" for c in conns}
    assert len(conns) == 144
    r = parts_page.evaluate(PART_GROUPS, [conns, at, given])
    sizes = check_parts(conns, given, at, r["groups"])                # (i), (ii), and a reason for each "" line
    assert sorted(i for i, g in r["groups"].items() if g == "") == [f"h{k:02d}" for k in range(12)]
    for k in range(12):
        assert len({r["groups"][f"c{k:02d}l{i:02d}"] for i in range(11)}) == 1, f"chain {k} split"
    assert len(sizes) <= bound(len(conns)), sizes                     # (iii)


def test_groups_within_the_cap_are_returned_unchanged(parts_page):
    conns = [{"id": f"l{i:03d}", "s": f"p{i:03d}", "t": f"p{i + 1:03d}"} for i in range(210)]
    at = {f"p{i:03d}": [i * 10, 0] for i in range(211)}
    given = {c["id"]: ("a" if i < 100 else "b" if i < 160 else "") for i, c in enumerate(conns)}
    r = parts_page.evaluate(PART_GROUPS, [conns, at, given])
    assert r == {"groups": given, "free": False}


def test_a_part_with_no_position_sends_its_lines_to_the_shared_group(parts_page):
    conns, at, given = chain()
    # the 51st part along x, its lines conns[49] and conns[50]: taken as at 0, it would be in its neighbours' band
    del at[conns[50]["s"]]
    r = parts_page.evaluate(PART_GROUPS, [conns, at, given])
    assert r["groups"][conns[49]["id"]] == "" and r["groups"][conns[50]["id"]] == ""
    sizes = check_parts(conns, given, at, r["groups"])
    assert sum(1 for g in sizes if g) >= 3, sizes


def test_the_shared_group_over_the_cap_is_parted_and_keeps_its_lines_at_a_systems_parts(parts_page):
    # an open system a (60 lines) and "" over the cap: a chain of 120 lines between parts in no system, and 10 lines
    # from it to a's parts; those 10 stay in "" (else they would share an end with a's lines in another group: (ii))
    conns = [{"id": f"a{i:03d}", "s": f"pa{i:03d}", "t": f"pa{i + 1:03d}"} for i in range(60)]
    conns += [{"id": f"x{i:03d}", "s": f"px{i:03d}", "t": f"px{i + 1:03d}"} for i in range(120)]
    conns += [{"id": f"e{i}", "s": f"px{i * 10:03d}", "t": f"pa{i * 6:03d}"} for i in range(10)]
    at = {**{f"pa{i:03d}": [i * 10, 0] for i in range(61)}, **{f"px{i:03d}": [i * 10, 200] for i in range(121)}}
    given = {c["id"]: "a" if c["id"].startswith("a") else "" for c in conns}
    r = parts_page.evaluate(PART_GROUPS, [conns, at, given])
    out = r["groups"]
    sizes = check_parts(conns, given, at, out)
    assert all(out[f"a{i:03d}"] == "a" for i in range(60))             # (iv): a, within the cap, as it was
    assert all(out[f"e{i}"] == "" for i in range(10))
    assert sorted(sizes) == ["", "#0", "#1", "a"] and sizes[""] == 11, sizes   # the chain in two bands, one line between
    assert len(sizes) - 1 <= bound(130) and not r["free"]


def hubs_of_ten(n: int, extra: int = 0) -> tuple[list[dict], dict]:
    """n hubs of 10 lines each, and a chain of extra lines."""
    conns = [{"id": f"h{j:02d}l{i}", "s": f"h{j:02d}", "t": f"h{j:02d}x{i}"} for j in range(n) for i in range(10)]
    conns += [{"id": f"z{i:03d}", "s": f"z{i:03d}", "t": f"z{i + 1:03d}"} for i in range(extra)]
    parts = sorted({x for c in conns for x in (c["s"], c["t"])})
    return conns, {p: [k * 7, (k * 13) % 50] for k, p in enumerate(parts)}


def test_the_shared_group_over_its_cap_is_routed_free(parts_page, browser, tmp_path):
    # pure: 15 hubs of 10 lines each are all in "" and it is free; at exactly SHARED_CAP (given in "" or in a group) it
    # is not yet
    conns, at = hubs_of_ten(15)
    given = {c["id"]: "s0" for c in conns}
    r = parts_page.evaluate(PART_GROUPS, [conns, at, given])
    check_parts(conns, given, at, r["groups"])
    assert sum(1 for g in r["groups"].values() if g == "") == 150 and r["free"] is True
    conns, at = hubs_of_ten(10, 20)
    for name in ("s0", ""):
        given = {c["id"]: name for c in conns}
        r = parts_page.evaluate(PART_GROUPS, [conns, at, given])
        check_parts(conns, given, at, r["groups"])
        assert sum(1 for g in r["groups"].values() if g == "") == CAP and r["free"] is False, (name, r)
        assert {g for g in r["groups"].values() if g} == {f"{name}#0"}, r
    # end to end: 12 valves each driving the 10 flows of a chain, in one system (12 lines at each: 144 in "")
    with model_served(tmp_path, hub_chains()) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=s0", 0)
        got = pg.evaluate(SPEC_GROUPS)
        pg.close()
    shared = sum(1 for g in got["groups"].values() if g == "")
    print(f"hubs: {len(got['conns'])} lines, \"\" {shared}, prof {got['prof']}")
    assert shared > CAP and got["penalties"] == {"": 0}
    assert got["prof"]["free"] == shared == got["prof"]["shared"], got["prof"]
    assert got["invalid"] == 0 and not errors, (got["invalid"], errors)


# the routed view's lines, its groups and what the router said of them
SPEC_GROUPS = """() => { const s = avoidSpec(S.layout, S.graph);
  return { groups: s.groups, penalties: s.penalties || null, conns: s.conns.map((c) => ({ id: c.id, s: c.s, t: c.t })),
           at: Object.fromEntries(s.shapes.map((x) => [x.id, [x.x + x.w / 2, x.y + x.h / 2]])),
           edges: S.graph.edges.map((e) => [e.id, e.source, e.target]), prof: AV.prof, invalid: AV.invalid }; }"""


@contextlib.contextmanager
def model_served(tmp_path: Path, model: str):
    """A generated model's page, served (the model is not run)."""
    d = tmp_path / "model"
    d.mkdir()
    (d / "ergostat.yaml").write_text(model)
    port = free_port()
    log = tmp_path / "web.log"
    with log.open("w") as err:
        proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                                env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}, stdout=err, stderr=err)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise AssertionError(f"the model's page never answered: {log.read_text()[-2000:]}") from None
                time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        proc.wait(10)


def hub_chains(hubs: int = 12, each: int = 10) -> str:
    """One system: `hubs` chains of `each` flows between stocks, and a flow by each (draining the chain's first stock)
    driving every flow of its chain. (Shaped otherwise it was worse to test with: each ten flows filling one stock took
    minutes to route; one long chain of 120 flows left a line libavoid found no way for, grouped as on main too.)"""
    stocks, flows = ["stocks:"], ["flows:"]
    for j in range(hubs):
        stocks += [f"  c{j}-{i}:\n    system: s0\n    unit: jobs\n    sensor:\n      manual: true" for i in range(each + 1)]
        flows += [f"  h{j}:", "    system: s0", f"    from: c{j}-0"]
        flows += [f"  d{j}-{i}:\n    system: s0\n    from: c{j}-{i}\n    to: c{j}-{i + 1}\n    driven-by: flow.h{j}"
                  for i in range(each)]
    return "name: hubs\nsystems:\n  s0:\n    description: one system\n" + "\n".join(stocks + flows) + "\n"


def one_system(chains: list[int], hub: bool) -> str:
    """One system of chains of stocks, a flow between each two (as big_model writes them); with hub, one flow driving
    each chain's first flow."""
    stocks, flows = ["stocks:"], ["flows:"]
    for k, n in enumerate(chains):
        for i in range(n):
            stocks += [f"  q{k}-{i}:", "    system: s0", "    unit: jobs", "    sensor:", "      manual: true"]
            if i + 1 < n:
                flows += [f"  f{k}-{i}:", "    system: s0", f"    from: q{k}-{i}", f"    to: q{k}-{i + 1}"]
                if hub and i == 0:
                    flows.append("    driven-by: flow.hub")
    if hub:
        stocks += ["  qhub:", "    system: s0", "    unit: jobs", "    sensor:", "      manual: true"]
        flows += ["  hub:", "    system: s0", "    to: qhub"]
    return "name: one\nsystems:\n  s0:\n    description: one system\n" + "\n".join(stocks + flows) + "\n"


@pytest.mark.slow
@pytest.mark.serial
def test_one_systems_lines_are_routed_in_parts(browser, tmp_path):
    with model_served(tmp_path, one_system([8] * 12, hub=True)) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=s0", 0)
        first, final = pg.evaluate(TIMED)
        r = pg.evaluate(AUDIT)
        got = pg.evaluate(SPEC_GROUPS)
        pg.close()
    conns, out = got["conns"], got["groups"]
    print(f"one system: {len(conns)} lines, routed {final:.0f}ms, {got['prof']['groups']} groups, "
          f"\"\" {got['prof']['shared']}, net crossings {len(r['netCrossings'])}")
    assert len(conns) > 150 and got["prof"]["groups"] >= 3
    # "" counted on its own: the lines at a part with more than HUB of the view's lines (in a one-system view no part
    # is in an open system, so every line is in "" before the parting: the view's lines are the group's)
    ids = {c["id"] for c in conns}
    degree: dict[str, int] = {}
    for eid, s, t in got["edges"]:
        if eid in ids:
            for p in {s, t}:
                degree[p] = degree.get(p, 0) + 1
    hubs = {eid for eid, s, t in got["edges"] if eid in ids and (degree[s] > HUB_OVER or degree[t] > HUB_OVER)}
    assert hubs and {i for i, g in out.items() if g == ""} == hubs
    sizes = check_parts(conns, {c["id"]: "" for c in conns}, got["at"], out)     # (i), (ii)
    assert len(sizes) <= bound(len(conns)), sizes                                   # (iii)
    assert got["invalid"] == 0 and not errors, (got["invalid"], errors)
    assert not r["through"] and not r["detour"], (r["through"][:5], r["detour"][:5])
    assert final < ROUTED_BOUND_MS, f"routed in {final:.0f}ms"


@pytest.mark.slow
@pytest.mark.serial
def test_one_long_chain_with_no_hub_is_routed_in_bands(browser, tmp_path):
    with model_served(tmp_path, one_system([90], hub=False)) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "system=s0", 0)
        r = pg.evaluate(AUDIT)
        got = pg.evaluate(SPEC_GROUPS)
        drawn(pg, url, "system=s0", 1)                                # a reload: the same groups
        again = pg.evaluate(SPEC_GROUPS)
        pg.close()
    conns, out = got["conns"], got["groups"]
    print(f"one chain: {len(conns)} lines, {got['prof']['groups']} groups, \"\" {got['prof']['shared']}")
    assert len(conns) > 150
    sizes = check_parts(conns, {c["id"]: "" for c in conns}, got["at"], out)
    assert sum(1 for g in sizes if g) >= 2, sizes
    # every line in "" at a band's edge (checked in check_parts: its ends not in one group; where the chain runs across
    # the axis, its parts may join a band with no line to it, so that many lines cross at one cut)
    shared = [c for c in conns if out[c["id"]] == ""]
    assert shared and len(shared) <= CAP, len(shared)
    assert again["groups"] == out
    assert got["invalid"] == 0 and not errors, (got["invalid"], errors)
    assert not r["through"] and not r["detour"], (r["through"][:5], r["detour"][:5])


def test_a_snapshot_page_still_routes_its_lines(browser, tmp_path, monkeypatch):
    """No snapshot test routes a large view: the parting (routeparts.js) is at least inlined in a snapshot page."""
    from ergostat import model as mdl
    from ergostat.store import Project
    from ergostat.web.snapshot import build
    d = tmp_path / "first-loop"
    shutil.copytree(ROOT / "examples" / "first-loop", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    out = tmp_path / "snapshot.html"
    out.write_text(build(Project(mdl.load(d))))
    pg = browser.new_page()
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:")) else rt.abort())
    pg.goto(f"file://{out}")
    assert pg.evaluate("() => typeof partGroups") == "function"
    pg.close()


def test_a_line_to_a_remote_is_drawn_dashed_between_the_frames(browser, tmp_path, monkeypatch):
    """A relation naming a remote's kind (SPEC §4c, §5a): the line from our ticket's step to the step the remote says
    its incident was last at is drawn dashed (pm-remote) from the ticket frame to the remote's frame; its panel says
    the items named are the remote's; the side list says how many links to it are not drawn, and why."""
    from ergostat.web.snapshot import build
    from tests.test_remote_lines import World, a_ticket_at_doing_naming, an_incident_fixing
    w = World(tmp_path, monkeypatch)
    now = time.time()
    a_ticket_at_doing_naming(w, now)
    a_ticket_at_doing_naming(w, now, item="ticket/2", target="incident/99")     # the remote has no such item
    an_incident_fixing(w, now - 400)
    out = tmp_path / "snapshot.html"
    out.write_text(build(w.lp))
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:")) else rt.abort())
    pg.goto(f"file://{out}#/diagram?view=process")
    pg.wait_for_function(READY, timeout=60000)
    got = pg.evaluate("""() => {
      const frame = (k) => { const r = document.querySelector(`.pm-frame[data-kind="${k}"] rect`); return r && r.getBBox(); };
      const inside = (p, b) => b && p.x >= b.x - 4 && p.x <= b.x + b.width + 4 && p.y >= b.y - 4 && p.y <= b.y + b.height + 4;
      const lines = [...document.querySelectorAll("svg.canvas g.edge.pm-related.pm-remote")];
      const path = lines[0]?.querySelector("path.pm-line");
      const a = path?.getPointAtLength(0), b = path?.getPointAtLength(path.getTotalLength());
      const mine = frame("ticket"), theirs = frame("incidents-incident");
      return { n: lines.length, nodes: lines[0]?.dataset.nodes, dash: path && getComputedStyle(path).strokeDasharray,
               ends: !!(a && b && inside(a, mine) && inside(b, theirs)),
               title: document.querySelector('.pm-frame[data-kind="incidents-incident"] .pm-title')?.textContent || "",
               side: (() => { for (const d of document.querySelectorAll('.side details.loops')) d.open = true;   // (folded)
                              return document.body.innerText; })() };
    }""")
    assert got["n"] == 1, got["n"]
    assert got["nodes"] == "p:ticket:doing p:incidents-incident:fixing", got["nodes"]
    assert got["ends"], got
    assert got["title"].startswith("remote incidents: incidents-incident"), got["title"]
    assert got["dash"] and got["dash"].replace("px", "").replace(" ", "") == "9,5", got["dash"]
    assert "1 link to it not drawn (not-answered 1)" in got["side"], got["side"]
    pg.evaluate("() => openProcessEdge(S.graph.edges.find((e) => e.remote && e.kind === 'related'))")
    assert "remote incidents's" in pg.locator("#detail").inner_text()
    pg.close()
    assert not errors, errors


# each subsystem drawn, closed (a block) or open (a frame): its letter's style, its name, and the text it shows
SUBSYSTEMS = """() => [...document.querySelectorAll('svg.canvas g.bd-subsystem, svg.canvas g.bd-frame-system')].map((g) => {
  const n = S.graph.nodes.find((n) => n.id === g.dataset.id) || (S.graph.frames || []).find((f) => f.id === g.dataset.hull);
  const t = g.classList.contains('bd-frame') ? g.querySelector(':scope > text') : g.querySelector('text.bd-sym');
  const q = t.querySelector('tspan.bd-mi'), cs = q && getComputedStyle(q);
  return { name: n.label, frame: g.classList.contains('bd-frame'), letter: q ? q.textContent : null, named: !!n.fn?.named,
           style: cs ? cs.fontStyle + ' ' + cs.fontWeight : null,
           text: [...g.querySelectorAll('text')].map((x) => x.textContent).join(' ') }; })"""


def test_the_blocks_legend_defines_the_subsystem_letter_and_its_size_and_a_name_is_printed_once(browser, tmp_path):
    """In the Blocks view the legend defines the subsystem letter drawn and p×m (outputs × inputs); a subsystem's
    name is printed once in its block or frame; its letter has one style and weight, closed at the top and open."""
    with served("software-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        seen = []
        for i, v in enumerate(["view=blocks", "view=blocks&open=factory"]):
            drawn(pg, url, v, i)
            got = pg.evaluate(SUBSYSTEMS)
            assert got, f"[{v}] no subsystem drawn"
            seen += [(v, x) for x in got]
            legend = pg.locator(".legend-box .bd-legend").text_content()
            assert "×" in legend and "outputs" in legend and "inputs" in legend, legend
            for x in got:                                  # the letter drawn is defined: C_name, P_name, or a name alone
                said = "its name alone" if x["named"] else f"{x['letter']}_name"
                assert x["named"] or x["letter"] in ("C", "P"), x
                assert said in legend, (x, legend)
        opened = {(x["name"], x["frame"]) for v, x in seen if v.endswith("open=factory")}
        assert ("factory", True) in opened and ("intake", False) in opened, opened     # the frame, and a block inside it
        assert ("factory", False) in {(x["name"], x["frame"]) for v, x in seen if v == "view=blocks"}
        for v, x in seen:
            assert x["text"].count(x["name"]) == 1, f"[{v}] {x['name']} printed more than once: {x['text']!r}"
        styles = {x["style"] for _, x in seen if x["letter"]}
        assert len(styles) == 1, styles                    # C and P alike, closed and open, bold on neither
        assert {x["letter"] for _, x in seen if x["frame"]} & {x["letter"] for v, x in seen if v == "view=blocks"}, seen
        pg.close()
        assert not errors, errors



MAY_DO ="You can look at everything. Approving or denying these is the only thing that changes the system."
MAY_DO_NONE = "Nothing waits for you. Looking never changes the system."
MAY_DO_SEEN = """() => {
  const g = document.querySelector('[role="group"][aria-describedby="may-do"]'), may = document.getElementById("may-do");
  const legend = document.querySelector("details.legend-box");
  return { first: g?.firstElementChild === may, text: may?.textContent, lead: g?.innerText.trim().split("\\n")[0],
           group: !!g, top: !!(may && legend && may.compareDocumentPosition(legend) & Node.DOCUMENT_POSITION_FOLLOWING),
           live: !!may?.closest("[aria-live]"), right: may?.getBoundingClientRect().right, width: innerWidth,
           over: may ? may.scrollWidth > may.clientWidth : null, shown: (may?.getBoundingClientRect().width || 0) > 0 };
}"""


def hold_an_action(d: Path) -> None:
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project
    p = Project(mdl.load(d))
    gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None})


@pytest.mark.parametrize("waiting", [True, False], ids=["waiting", "none"])
def test_the_requests_group_opens_by_saying_what_a_person_may_do(browser, tmp_path, waiting):
    """Needs attention opens with the one sentence on what a person may do, its group described by it (a screen reader
    reads it once on entering, and a redraw neither replaces nor changes it); with nothing waiting, its empty form;
    the gated actions on the Items page say the same; at 390 px it wraps within the page."""
    from .test_inbox import MODEL
    src = tmp_path / "src" / "inbox"
    src.mkdir(parents=True)
    (src / "ergostat.yaml").write_text(MODEL)
    said = MAY_DO if waiting else MAY_DO_NONE
    with served(src, tmp_path, edit=hold_an_action if waiting else None) as url:
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        if waiting:
            pg.wait_for_selector('[data-inbox^="action/"]', timeout=30000)
        pg.wait_for_selector("#may-do", timeout=30000)
        got = pg.evaluate(MAY_DO_SEEN)
        assert got["text"] == said and got["top"], got           # where the group is: above How to read it
        if waiting:                                               # the first text of Waiting for you, which it describes
            assert got["first"] and got["lead"] == said, got
        else:                                                     # nothing waits: no group, only its empty form
            assert not got["group"], got
        assert not got["live"], "said with the group, not as a live region"
        pg.evaluate("""() => { window.__may = document.getElementById("may-do"); window.__muts = 0;
          new MutationObserver((rs) => { window.__muts += rs.length; })
            .observe(window.__may, { childList: true, characterData: true, subtree: true, attributes: true }); }""")
        pg.evaluate("() => { S.redrawSide(); S.redrawSide(); }")
        assert pg.evaluate("() => document.getElementById('may-do') === window.__may && window.__muts === 0")
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.reload()
        pg.wait_for_selector("#may-do", timeout=30000)
        got = pg.evaluate(MAY_DO_SEEN)
        assert got["text"] == said and got["shown"] and not got["over"] and got["right"] <= got["width"], got
        pg.set_viewport_size({"width": 1400, "height": 900})
        for actions in ("items?kind=ergostat.action", "items/ergostat.action"):    # the Items tab's and their own page
            pg.goto(f"{url}/{actions}")
            pg.wait_for_selector("p.may-do:not([hidden])", timeout=30000)
            assert pg.locator("p.may-do:not([hidden])").inner_text() == MAY_DO, actions
        pg.goto(f"{url}/items")
        pg.wait_for_selector(".filters", timeout=30000)
        assert pg.locator("p.may-do:not([hidden])").count() == 0
        pg.close()
        assert not errors, errors


SIDE_WORDS = """() => ({
  side: [...document.querySelectorAll('.side .att b, .side .suggest .hint b')].map((b) => b.textContent),
  says: [...document.querySelectorAll('.side .suggest .hint')].map((d) => d.textContent.replace(/^\\S+ \\S+ /, '')),
  heads: [...document.querySelectorAll('.side h3, .side details.loops > summary')].map((x) => x.firstChild.textContent),
  serves: [...document.querySelectorAll('.side .looprow .sub')].map((x) => x.textContent).filter((t) => /serves goals? \\S/.test(t)),
  goals: (S.graph.causalLoops || []).filter((c) => c.nodes.some((n) => n.startsWith('gap:'))).length })"""


def test_in_dynamics_a_goal_is_called_a_goal_and_loop_means_an_r_or_b_loop(browser, tmp_path, monkeypatch):
    """Dynamics' side list called a controlled goal 'loop requests-handled' right above 'Feedback loops 18: R2, R3 …'.
    There it is 'goal requests-handled'; an R or B loop that closes a goal says 'serves goal …'; Blocks lists its
    'Control loops'. (A suggestion's words are the unit tests' in test_dynamics_view.py: none is seeded here.)"""
    from ergostat import model as mdl
    from ergostat.store import Project

    def off(d):                                           # a reading of backlog above its goal: backlog-clear is off
        monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
        p = Project(mdl.load(d))
        p.measurements.add(next(iter(p.model.spec.stocks["backlog"].sensors.values())).series, 5.0, at=time.time() - 5)
    with served("software-factory", tmp_path, off) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=dynamics&open=*", 0)
        pg.wait_for_function("() => document.querySelector('.side .looprow')", timeout=20000)
        got = pg.evaluate(SIDE_WORDS)
        assert not [w for w in got["side"] + got["says"] if w.startswith("loop ")], got
        assert any(w.startswith("goal ") for w in got["side"]), got           # (so a card about a goal was seen)
        assert "Feedback loops" in got["heads"] and "Control loops" not in got["heads"], got
        assert got["goals"] and len(got["serves"]) == got["goals"], got       # each loop through a goal names it
        drawn(pg, url, "view=blocks&open=*", 1)
        pg.wait_for_function("() => document.querySelector('.side details.loops > summary')", timeout=20000)
        got = pg.evaluate(SIDE_WORDS)
        assert "Control loops" in got["heads"] and "Loops" not in got["heads"], got
        pg.close()
        assert not errors, errors


def test_the_address_holds_what_is_chosen_and_the_window(browser, tmp_path):
    """A loop chosen on the Loops page, and the window chosen, are in the address (?select=, ?window=): the address
    opened in a new tab shows the same panel and window. Changing the window leaves the panel open and says
    'Loading…' in the table until it is answered. A stock chosen on the diagram is in the address, and a reload rings
    it; the Record's filter is in the address, and a reload keeps it. (first-loop's inbox-short stands in for the
    review's api-q2-low, a demo's goal no test has.)"""
    d = tmp_path / "first-loop"
    shutil.copytree(ROOT / "examples" / "first-loop", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    panel = "(n) => !document.querySelector('#detail').hidden && (document.querySelector('#detail h2')?.textContent || '').includes(n)"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        ctx = browser.new_context(viewport={"width": 1500, "height": 1000})
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url + "/loops")
        pg.locator("#main tr.click", has_text="inbox-short").first.click()
        pg.wait_for_function(panel, arg="inbox-short", timeout=20000)
        assert "select=inbox-short" in pg.url, pg.url
        # the window changed: the loops' answer held back, so what the table says meanwhile is seen
        held: list = []
        pg.route(lambda u: u.split("?")[0].endswith("/api/loops"), lambda rt: held.append(rt))
        pg.locator("#when .menu-btn").click()
        pg.locator(".menu-item", has_text="Last 6 hours").click()
        loading = "() => [...document.querySelectorAll('#main .page p.muted')].some((p) => p.textContent === 'Loading…')"
        pg.wait_for_function(loading, timeout=20000)
        assert pg.evaluate(panel, "inbox-short"), "the panel closed when the window changed"
        assert "window=6h" in pg.url and "select=inbox-short" in pg.url, pg.url
        for rt in held:
            rt.continue_()
        pg.unroute_all()
        pg.wait_for_function(f"() => document.querySelector('#main tr.click') && !({loading})()", timeout=20000)
        # the address, in a new tab: the same panel and window
        tab = ctx.new_page()
        tab.on("pageerror", lambda e: errors.append(str(e)))
        tab.goto(pg.url)
        tab.wait_for_function(panel, arg="inbox-short", timeout=20000)
        assert tab.evaluate("[S.since, document.querySelector('#when .menu-btn').textContent]") == ["6h", "Last 6h"]
        tab.locator("#detail button.close").click()                  # closed by hand: no longer in the address
        tab.wait_for_function("() => !location.search.includes('select=')", timeout=5000)
        tab.close()
        # back and forward: each entry's address names the window it shows, and the page shows that window
        agree = "() => [S.since, new URLSearchParams(location.search).get('window'), document.querySelector('#when .menu-btn').textContent]"
        pg.evaluate("() => setWindow('1d')")
        pg.evaluate("() => navigate('/items')")
        assert "window=1d" in pg.url, pg.url
        overview = "() => !!document.querySelector('#main .kind-overview')"    # bare /items: the kinds' overview, whatever the window
        assert pg.evaluate(overview), "/items?window=1d is not the overview"
        pg.evaluate("() => setWindow('6h')")
        assert "window=6h" in pg.url and pg.evaluate(overview), pg.url
        pg.evaluate("() => setWindow('1h')")
        assert pg.evaluate(agree) == ["1h", None, "Last 1h"]
        pg.go_back()
        pg.wait_for_function("() => location.pathname === '/goals'", timeout=5000)
        assert pg.evaluate(agree) == ["1d", "1d", "Last 1d"]
        pg.go_forward()
        pg.wait_for_function("() => location.pathname === '/items'", timeout=5000)
        assert pg.evaluate(agree) == ["1h", None, "Last 1h"]
        pg.goto(url + "/items?window=1d")                              # a pasted link with a window: still the overview
        pg.wait_for_function(overview, timeout=20000)
        assert pg.evaluate(agree) == ["1d", "1d", "Last 1d"]
        # the diagram: a stock chosen is in the address, and a reload rings it
        pg.goto(url + "/diagram")
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        hit = pg.locator('g.node[data-id="stock:inbox"] .hit').first.bounding_box()
        pg.mouse.click(hit["x"] + hit["width"] / 2, hit["y"] + hit["height"] / 2)
        pg.wait_for_function("() => new URLSearchParams(location.search).get('select') === 'stock.inbox'", timeout=5000)
        pg.reload()
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        pg.wait_for_function("() => document.querySelector('g.node[data-id=\"stock:inbox\"]').classList.contains('selected')",
                             timeout=5000)
        # a stock's panel, then a flow's (shown by no opener the window asks again): the window changed keeps the
        # flow's, not the stock's asked again in its place
        pg.goto(url + "/diagram?view=dynamics")
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        kind = "() => document.querySelector('#detail .kind')?.textContent"
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'stock:inbox'))")
        assert pg.evaluate(kind) == "Stock" and pg.evaluate(panel, "inbox")
        pg.evaluate("() => openEdgeSD(S.graph.edges.find((e) => e.kind === 'pipe'))")
        assert pg.evaluate(kind) == "Flow", pg.evaluate(kind)
        pg.evaluate("() => setWindow('1d')")                         # (resolves once the panel's opener, if any, answered)
        assert pg.evaluate(kind) == "Flow", "the window changed: the flow's panel was replaced by " + str(pg.evaluate(kind))
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'stock:inbox'))")
        pg.evaluate("() => { document.querySelector('#detail').append(Object.assign(document.createElement('i'), { id: 'stale' })); }")
        pg.evaluate("() => setWindow('6h')")                         # a stock's own panel is asked again in the new window
        assert pg.evaluate(kind) == "Stock" and not pg.evaluate("() => !!document.querySelector('#stale')")
        # Back with another page's panel open: the panel shown is the address's select= loop, not the stock's left over;
        # Forward again: no panel left over, and a window change there opens none
        pg.goto(url + "/loops")
        pg.locator("#main tr.click", has_text="inbox-short").first.click()
        pg.wait_for_function(panel, arg="inbox-short", timeout=20000)
        pg.evaluate("() => navigate('/diagram?view=dynamics')")
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        pg.evaluate("() => openNode(S.graph.nodes.find((n) => n.id === 'stock:inbox'))")
        assert pg.evaluate(kind) == "Stock"
        pg.go_back()
        pg.wait_for_function("() => location.pathname === '/goals'", timeout=5000)
        assert "select=inbox-short" in pg.url, pg.url
        pg.wait_for_function(f"() => ({panel})('inbox-short') && ({kind})() === 'Goal' && !!document.querySelector('#detail dl')",
                             timeout=20000)          # (its answer in, not its 'Loading…': a late one is another matter)
        pg.go_forward()
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        assert pg.evaluate("() => document.querySelector('#detail').hidden"), "a panel was left over after Forward"
        pg.evaluate("() => setWindow('1d')")
        assert pg.evaluate("() => document.querySelector('#detail').hidden"), "a window change reopened the loop's panel"
        # the Record's filter: written as main's match=, a link's filter= read as well
        pg.goto(url + "/record")
        pg.locator(".filters input[type=search]").fill("valve.*")
        pg.locator(".filters input[type=search]").press("Enter")
        pg.wait_for_function("() => new URLSearchParams(location.search).get('match') === 'valve.*'", timeout=5000)
        pg.reload()
        pg.wait_for_function("() => document.querySelector('.filters input[type=search]')?.value === 'valve.*'", timeout=20000)
        pg.goto(url + "/record?filter=agent.*")
        pg.wait_for_function("() => document.querySelector('.filters input[type=search]')?.value === 'agent.*'", timeout=20000)
        ctx.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


ON_PHONE = """() => {
  // what a phone shows of the drawing: the canvas's box, each system box wholly inside it, and the parts in view
  const c = document.querySelector("svg.canvas").getBoundingClientRect();
  const inside = (r) => r.width > 0 && r.left >= c.left - 1 && r.right <= c.right + 1 && r.top >= c.top - 1 && r.bottom <= c.bottom + 1;
  const label = (g) => S.graph.nodes.find((n) => n.id === g.dataset.id)?.label || g.dataset.id;
  const boxes = [...document.querySelectorAll("svg.canvas g.node.k-system")];
  const hint = document.getElementById("panhint");
  return { canvas: [c.width, c.height], k: S.view.k, lay: [S.layout.width, S.layout.height], boxes: boxes.length,
           whole: boxes.filter((g) => inside(g.querySelector(".hit").getBoundingClientRect())).map(label),
           seen: [...document.querySelectorAll("svg.canvas g.node")].filter((g) => inside(g.getBoundingClientRect())).map(label),
           hint: hint && !hint.hidden && hint.getBoundingClientRect().width > 0 ? hint.textContent : "" };
}"""


@pytest.mark.parametrize("example", ["the-job", "software-factory"])
def test_on_a_phone_the_diagram_opens_with_a_whole_system_box_in_view(browser, tmp_path, example):
    """At 390x844 the canvas showed nothing of the-job (neither box in view) and part of one box of
    software-factory, and opened mid-drawing inside a system: on a narrow screen each view opens fitted to the
    canvas, so a whole system box is in it, and inside a system its first part or which way the rest lies."""
    with served(example, tmp_path) as url:
        pg = browser.new_page(viewport={"width": 390, "height": 844})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram", timeout=DRAWN_S * 1000)
        pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
        got = pg.evaluate(ON_PHONE)
        assert got["boxes"] and got["whole"], got
        if example == "software-factory":
            pg.goto(f"{url}/diagram?system=product", timeout=DRAWN_S * 1000)
            pg.wait_for_function(READY, timeout=DRAWN_S * 1000)
            got = pg.evaluate(ON_PHONE)
            # (the acceptance asks for either; both hold: centred on its first stock, the hint says where the rest is)
            assert "users" in got["seen"] and re.search("[←↑→↓]", got["hint"]), got
            pg.get_by_role("button", name="Blocks").click()      # a change of view: fitted again
            pg.wait_for_function(READY + " && S.graph.kind !== 'dynamics'", timeout=DRAWN_S * 1000)
            got = pg.evaluate(ON_PHONE)
            assert got["seen"] or got["hint"], got
        pg.close()
        assert not errors, errors


def leave_list(pg) -> None:
    """The reader leaves the side list (pointer and focus), so it no longer holds still and a refresh is applied."""
    pg.mouse.move(2, 400)
    pg.evaluate("() => document.activeElement?.blur()")


FOLD_SYSTEMS = ["api", "billing", "build", "data", "support", "web"]
FOLD_ROW = '.side .att > [data-fold^="no-description|"]'
IN_VIEW = """() => {
  // every entry of Needs attention inside the side panel's visible box, the panel not scrolled
  const side = document.querySelector('.side'), box = side.getBoundingClientRect();
  const bottom = Math.min(innerHeight, box.bottom);
  return {scrolled: side.scrollTop, out: [...side.querySelectorAll('.att > div')].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.height === 0 || r.top < Math.max(0, box.top) || r.bottom > bottom;
  }).map((el) => el.textContent.slice(0, 60))};
}"""


def test_alike_modelling_requests_fold_into_one_entry_with_a_count_and_one_answer(browser, tmp_path, home):
    """Design review Q50: 24 stocks with no unit, each its own held request with its own Deny, filled the side list and
    pushed the one real alarm away, while /model said 'Nothing waiting'. Alike requests (one code, one asker) are one
    entry: the count, the systems, and Deny all; opened, each with its own answer. /model counts them as waiting.
    (A missing unit is a check finding now, not a request (dev record missing-unit-is-a-check-finding), so the 24 alike
    requests here are stocks with no description: the same fold, another code.)"""
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.numbers import requests as rq
    from ergostat.store import Project

    from .test_inbox import MODEL
    from .test_modelling_core import MODELLING
    mine = {f"stock.{s}-{i}" for s in FOLD_SYSTEMS for i in range(4)}
    stocks = "".join(f"  {s}-{i}:\n    system: {s}\n    unit: things\n    sensor: {{manual: true}}\n"
                     for s in FOLD_SYSTEMS for i in range(4))
    systems = "systems:\n" + "".join(f"  {s}:\n    description: the {s} work\n" for s in FOLD_SYSTEMS)
    (tmp_path / "ergostat.yaml").write_text(MODEL.replace("stocks:\n", systems + "stocks:\n" + stocks, 1) + MODELLING)
    p = Project(mdl.load(tmp_path))
    assert not [x for x in p.model.problems if x.level == "error"], [str(x) for x in p.model.problems]
    gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None})      # the real alarm, held for the owner
    rq.sync(p)
    held = [r for r in rq.current(p, ("open",)) if r["code"] == "no-description" and r["about"] in mine]
    assert len(held) == 24, sorted(r["about"] for r in held)
    for r in held:
        rq.mark(p, r, "held", "no tier has a change for it")
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram")
        pg.locator('.side .att [data-inbox^="action/"]').wait_for(timeout=60000)
        pg.locator(FOLD_ROW).wait_for(state="attached", timeout=60000)
        house = pg.locator(".side details.housekeeping")             # held requests are housekeeping (folded)
        if not house.evaluate("(d) => d.open"):
            house.locator(":scope > summary").click()
        pg.locator(FOLD_ROW).wait_for(timeout=20000)
        assert pg.locator(".side .att > [data-fold]").count() == 1
        summary = pg.locator(f"{FOLD_ROW} > details.fold > summary").inner_text()
        assert "24 stocks" in summary and "no description" in summary and "(api, billing, build, data, support, web)" in summary, summary
        assert pg.locator('.side .att > [data-inbox^="request/"]').count() == 0     # no member left as a row of its own
        legend = pg.locator(".side details.legend-box")              # main puts the legend first; the reader may close it
        if legend.evaluate("(d) => d.open"):
            legend.locator(":scope > summary").click()
        got = pg.evaluate(IN_VIEW)
        assert got == {"scrolled": 0, "out": []}, got
        pg.locator(f"{FOLD_ROW} > details.fold > summary").click()
        members = pg.locator(f'{FOLD_ROW} > details.fold > [data-inbox^="request/"]')
        assert members.count() == 24
        assert all(members.nth(i).locator('button[data-verb="deny"]').count() == 1 for i in range(24))
        model = browser.new_page(viewport={"width": 1440, "height": 900})
        model.goto(f"{url}/model")
        model.wait_for_function("() => /waiting/.test(document.querySelector('#review-queue')?.textContent || '')", timeout=60000)
        text = model.locator(".page").first.inner_text()
        assert "Nothing waiting" not in text and "24 modelling requests held" in text, text[:2000]
        model.close()
        pg.locator(f"{FOLD_ROW} > .inbox-act input").fill("these stocks say what they are by name")
        # as a person types: the side list is rebuilt and patched in between (a poll asked after the first one's
        # answer was drawn), so Deny all must read the reason from the row on the page, not from an earlier build;
        # the reader steps out of the list meanwhile, as it holds still while they are in it
        leave_list(pg)
        for _ in range(2):
            with pg.expect_response(lambda r: "/api/graph" in r.url, timeout=60000):
                pass
        pg.locator(f'{FOLD_ROW} button[data-verb="deny-all"]').click()
        pg.locator(f"{FOLD_ROW} > .inbox-act .note").filter(has_text="24 denied").wait_for(timeout=60000)
        leave_list(pg)
        pg.wait_for_function(f"() => !document.querySelector('{FOLD_ROW}')", timeout=60000)
        assert {r["state"] for r in rq.stored(p).values() if r["about"] in mine and r["code"] == "no-description"} == {"dismissed"}
        assert pg.locator('.side .att [data-inbox^="action/"]').count() == 1            # the alarm still waits
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def test_two_folds_each_keep_their_own_reason_across_a_refresh(browser, tmp_path, home):
    """Two folds, A above B (lesson-5): denying all of A, then a refresh, leaves B's reason field empty (B is not drawn
    into A's old nodes with A's reason typed in), and Deny all on B denies B's members under B's own reason."""
    from ergostat import model as mdl
    from ergostat.numbers import requests as rq
    from ergostat.store import Project

    from .test_inbox import MODEL
    from .test_modelling_core import MODELLING
    # (no-unit is a check finding now, raising no request: the second fold is flows with no equation)
    mine = {f"flow.e-{i}": "no-equation" for i in range(3)} | {f"stock.u-{i}": "no-description" for i in range(3)}
    stocks = "".join(f"  u-{i}:\n    unit: things\n    sensor: {{manual: true}}\n" for i in range(3))
    flows = "".join(f"  e-{i}:\n    from: queue\n    to: u-{i}\n    description: what moves on, part {i}\n"
                    f"    sensor: {{manual: true}}\n" for i in range(3))
    text = MODEL.replace("stocks:\n", "stocks:\n" + stocks, 1).replace("flows:\n", "flows:\n" + flows, 1)
    (tmp_path / "ergostat.yaml").write_text(text + MODELLING)
    p = Project(mdl.load(tmp_path))
    rq.sync(p)
    held = [r for r in rq.current(p, ("open",)) if mine.get(r["about"]) == r["code"]]
    assert len(held) == 6, sorted((r["code"], r["about"]) for r in held)
    for r in held:
        rq.mark(p, r, "held", "no tier has a change for it")
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram")
        folds = pg.locator(".side .att > [data-fold]")
        pg.wait_for_function("() => document.querySelectorAll('.side .att > [data-fold]').length >= 2", timeout=60000)
        house = pg.locator(".side details.housekeeping")
        if not house.evaluate("(d) => d.open"):
            house.locator(":scope > summary").click()
        a, b = folds.nth(0).get_attribute("data-fold"), folds.nth(1).get_attribute("data-fold")
        assert {a.split("|")[0], b.split("|")[0]} == {"no-equation", "no-description"}, (a, b)
        row = lambda f: pg.locator(f'.side .att > [data-fold="{f}"]')       # noqa: E731
        row(b).locator(":scope > .inbox-act input").fill("reason B")        # typed in B while A is answered
        row(a).locator(":scope > .inbox-act input").fill("reason A")
        # the field as it is when A's row says it is done (a refresh may take A away straight after)
        row(a).locator(":scope > .inbox-act").evaluate("""(act) => new MutationObserver(() => {
          window.__foldDone = [act.querySelector('.note').textContent, act.querySelector('input').value];
        }).observe(act.querySelector('.note'), {childList: true, characterData: true, subtree: true})""")
        row(a).locator('button[data-verb="deny-all"]').click()
        pg.wait_for_function("() => window.__foldDone", timeout=60000)
        assert pg.evaluate("() => window.__foldDone") == [" 3 denied", ""]          # the reason goes with its fold
        leave_list(pg)                                        # the list holds still while the reader is in it
        pg.wait_for_function(f"() => !document.querySelector('.side .att > [data-fold=\"{a}\"]')", timeout=60000)
        for _ in range(2):                                    # a refresh after A went: B now stands where A stood
            with pg.expect_response(lambda r: "/api/graph" in r.url, timeout=60000):
                pass
        assert row(b).locator(":scope > .inbox-act input").input_value() == "reason B"   # its own, not A's nodes
        row(b).locator('button[data-verb="deny-all"]').click()
        row(b).locator(":scope > .inbox-act .note").filter(has_text="3 denied").wait_for(timeout=60000)
        leave_list(pg)
        pg.wait_for_function(f"() => !document.querySelector('.side .att > [data-fold=\"{b}\"]')", timeout=60000)
        notes = {r["about"]: (r["code"], r["state"], r.get("note")) for r in rq.stored(p).values() if r["about"] in mine}
        want = {x: (c, "dismissed", "reason A" if c == a.split("|")[0] else "reason B") for x, c in mine.items()}
        assert notes == want, notes
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def test_a_one_sided_limit_is_drawn_and_named_as_a_limit(browser, tmp_path):
    """ticket-factory's worked-opened holds worked ≤ 0: its reference is drawn 'r ≤ 0' and its panel calls it a limit,
    never a setpoint; the on-off controller serving it switches on and off at one threshold, so it is an ideal relay,
    drawn with one step, and nothing says hysteresis. The controller panel and the Loops page say 'limit ≤ 0'."""
    with served("ticket-factory", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.set_default_timeout(60000)
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=blocks&system=making", 0)
        ref = pg.locator('svg.canvas g.node[data-id="ref:worked-opened"]')
        assert "≤ 0" in ref.text_content(), ref.text_content()
        fit(pg)
        click_part(pg, "ref:worked-opened")
        pg.wait_for_function("() => document.querySelector('#detail .kind')?.textContent === 'reference input'")
        text = pg.locator("#detail").inner_text()
        assert "limit" in text and "setpoint" not in text, text
        relay = pg.locator('svg.canvas g.node[data-id="blk:keep-worked-opened"]')
        assert relay.locator(".bd-sketch .bd-curve").get_attribute("d") == "M2,18 H14 V5 H26"   # one step: no loop
        click_part(pg, "blk:keep-worked-opened")
        pg.wait_for_function("() => document.querySelector('#detail h2')?.textContent === 'keep-worked-opened'")
        text = pg.locator("#detail").inner_text()
        assert "ideal relay" in text and "hysteresis" not in text, text
        pg.evaluate("() => openLoop('worked-opened', true)")
        pg.wait_for_function("() => document.querySelector('#detail .kind')?.textContent === 'Controller'")
        pg.wait_for_function("() => [...document.querySelectorAll('#detail dd')].some((d) => d.textContent === 'worked, limit ≤ 0')")
        pg.goto(url + "/loops")
        row = pg.locator("tr", has_text="worked-opened")
        row.wait_for()
        assert "limit ≤ 0" in row.inner_text(), row.inner_text()
        assert not errors, errors
        pg.close()


NO_UNIT = """() => Object.fromEntries([...document.querySelectorAll('svg.canvas g.node')].filter((g) => g.querySelector('.sd-stock'))
  .map((g) => { const t = g.querySelector('.sd-nounit'), v = g.querySelector('.sd-value');
    return [g.querySelector('.sd-name').textContent, { value: v ? v.textContent : '', muted: t ? getComputedStyle(t).fill : null }]; }))"""


def test_a_stock_with_no_unit_reads_unit_query_after_its_value_and_the_legend_explains_it(browser, tmp_path, monkeypatch):
    """A missing unit is check's finding (no-unit), drawn on the stock (the dev record missing-unit-is-a-check-finding):
    its value reads '12 unit ?', the 'unit ?' in the muted tone, a legend row says what it means, a stock with a unit
    has none; and /api/status's check list (the Check page's) names each unitless stock once."""
    from ergostat import model as mdl
    from ergostat.store import Project
    from tests.test_missing_unit import UNITLESS
    d = tmp_path / "units"
    d.mkdir()
    (d / "ergostat.yaml").write_text(UNITLESS)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))       # the server is given it too
    p = Project(mdl.load(d))
    p.measurements.add("sensor/backlog.main", 12.0, at=time.time() - 5)
    p.measurements.add("sensor/tickets-open.main", 3.0, at=time.time() - 5)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                st = json.loads(urllib.request.urlopen(url + "/api/status", timeout=2).read())
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        said = [c["message"].split(": no unit.")[0].rsplit(" ", 1)[-1] for c in st["check"] if ": no unit." in c["message"]]
        assert sorted(said) == ["backlog", "done", "parked"], said              # each once
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        drawn(pg, url, "view=dynamics", 0)
        pg.wait_for_function("() => [...document.querySelectorAll('svg.canvas .sd-value')].some((t) => t.textContent.startsWith('12'))",
                             timeout=30000)
        got = pg.evaluate(NO_UNIT)
        assert got["backlog"]["value"] == "12 unit ?", got
        assert got["tickets-open"]["value"] == "3 tickets", got                  # a stock with a unit: none
        assert got["done"]["value"].endswith(" unit ?") and got["parked"]["value"].endswith(" unit ?"), got
        muted = pg.evaluate("() => { const t = document.createElementNS('http://www.w3.org/2000/svg', 'text'); "
                            "t.setAttribute('fill', 'var(--sd-muted)'); document.querySelector('svg.canvas').append(t); "
                            "const c = getComputedStyle(t).fill; t.remove(); return c; }")
        assert got["backlog"]["muted"] == muted, (got["backlog"], muted)        # the muted tone, as the legend draws it
        legend = pg.evaluate("() => sdLegend().textContent")
        assert "unit ?: the stock's value has no unit" in legend, legend
        pg.goto(f"{url}/model", timeout=DRAWN_S * 1000)                         # the Model page's Tools table lists them
        row = pg.locator("table.avail tr", has_text="units").first
        row.wait_for(timeout=60000)
        assert row.locator(".no-unit a").all_inner_texts() == ["backlog", "done", "parked"], row.inner_text()
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


def open_all(pg) -> str:
    """The ⋯ menu's Open all, clicked: its label as it read."""
    pg.get_by_title("More: wrap, open or close every system, unpin").click()
    item = pg.locator(".menu-pop .menu-item", has_text="Open all")
    label = item.inner_text()
    item.click()
    return label


OPENED = """(want) => typeof S !== 'undefined' && S.graph && [...(S.graph.open || [])].sort().join(',') === want &&
  S.layout && S.graphSig && !S.layout.routing && document.querySelectorAll('svg.canvas g.node').length > 0"""
LEVEL_SAID = "() => document.querySelector('.canvas-wrap .open-level')?.textContent || ''"


@pytest.mark.serial
def test_open_all_on_a_model_that_will_not_fit_opens_the_first_level_and_says_into_for_the_rest(browser, tmp_path):
    """the-job (about 200 parts open) at 1600x1000: 'Open all (first level)' opens job and modelling, the ten systems
    within job stay closed boxes with their Into, the canvas says so, the lines come within 3s, Blocks draws (never a
    blank canvas), and the address lists what was opened, so a reload shows the same."""
    with served("the-job", tmp_path) as url:
        tree = json.loads(urllib.request.urlopen(url + "/api/graph?view=dynamics", timeout=60).read())["tree"]
        first = sorted(s for s, t in tree.items() if not t["within"])
        nested = sorted(set(tree) - set(first))
        assert first == ["job", "modelling"] and len(nested) == 10, (first, nested)
        said = f"Opened to the first level: {len(nested)} systems stay closed. Use Into to open one."
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, (view, box, ctl) in enumerate([("view=dynamics", "system:", ".sys-btn"), ("view=blocks", "sys:", ".bd-toggle")]):
            drawn(pg, url, view, i)
            assert pg.evaluate(LEVEL_SAID) == ""
            t0 = time.monotonic()
            assert open_all(pg).startswith("Open all (first level)")
            pg.wait_for_function(OPENED, arg=",".join(first), timeout=DRAWN_S * 1000)
            took = time.monotonic() - t0
            if view == "view=dynamics":
                assert took < 3, f"the first level open, its lines routed, took {took:.1f}s"
            assert f"open={','.join(first)}" in pg.url.replace("%2C", ","), pg.url
            for _ in range(2):                                       # as opened, then as reloaded from the address
                got = pg.evaluate("""([box, ctl, nested]) => nested.map((x) => {
                  const el = document.querySelector(`svg.canvas g.node[data-id="${CSS.escape(box + x)}"]`);
                  return [x, !!el, !!el?.querySelector(ctl)]; }).filter(([, drawn, has]) => !drawn || !has)""", [box, ctl, nested])
                assert not got, f"[{view}] not drawn as a closed box with its control: {got}"
                assert pg.evaluate("() => document.querySelectorAll('svg.canvas g.node').length") > len(nested)
                assert pg.evaluate(LEVEL_SAID) == (said if view == "view=dynamics" else said.replace("Into", "a block's +"))
                pg.reload()
                pg.wait_for_function(OPENED, arg=",".join(first), timeout=DRAWN_S * 1000)
        pg.close()
        assert not errors, errors


@pytest.mark.serial
def test_open_all_on_a_flat_model_that_will_not_fit_stays_at_the_system_boxes_and_says_into(browser, tmp_path):
    """big (its systems all first level, too big open at 1600x1000): 'Open all (system boxes)' keeps every system a
    closed box with its Into (Blocks: its +), the canvas says how many, and the address (open=-) shows the same on a
    reload; the page as first drawn says nothing."""
    with served("big", tmp_path) as url:
        tree = json.loads(urllib.request.urlopen(url + "/api/graph?view=dynamics", timeout=60).read())["tree"]
        assert tree and not any(t["within"] for t in tree.values()), tree
        said = f"Opened to the system boxes: {len(tree)} systems stay closed. Use Into to open one."
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for i, (view, box, ctl) in enumerate([("view=dynamics", "system:", ".sys-btn"), ("view=blocks", "sys:", ".bd-toggle")]):
            drawn(pg, url, view, i)
            assert pg.evaluate(LEVEL_SAID) == ""
            t0 = time.monotonic()
            assert open_all(pg).startswith("Open all (system boxes)")
            pg.wait_for_function(OPENED, arg="-", timeout=DRAWN_S * 1000)    # (the server says back what was asked: "-")
            if view == "view=dynamics":
                assert time.monotonic() - t0 < 3, "the system boxes and their lines took 3s or more"
            assert "open=-" in pg.url, pg.url
            for _ in range(2):                                       # as opened, then as reloaded from the address
                got = pg.evaluate("""([box, ctl, names]) => names.filter((x) =>
                  !document.querySelector(`svg.canvas g.node[data-id="${CSS.escape(box + x)}"]`)?.querySelector(ctl))""",
                                  [box, ctl, sorted(tree)])
                assert not got, f"[{view}] not drawn as a closed box with its control: {got}"
                assert pg.evaluate(LEVEL_SAID) == (said if view == "view=dynamics" else said.replace("Into", "a block's +"))
                pg.reload()
                pg.wait_for_function(OPENED, arg="-", timeout=DRAWN_S * 1000)
        pg.close()
        assert not errors, errors


def test_open_all_on_a_model_that_fits_opens_every_system_as_before(browser, tmp_path):
    """software-factory (about 65 parts open, a system within another) fits: Open all opens every system (open=*)."""
    with served("software-factory", tmp_path) as url:
        tree = json.loads(urllib.request.urlopen(url + "/api/graph?view=dynamics", timeout=60).read())["tree"]
        assert any(t["within"] for t in tree.values()), tree
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        for i, view in enumerate(["view=dynamics", "view=blocks"]):
            drawn(pg, url, view, i)
            assert open_all(pg) == "Open all systems"
            pg.wait_for_function(OPENED, arg=",".join(sorted(tree)), timeout=DRAWN_S * 1000)
            assert "open=*" in pg.url.replace("%2A", "*"), pg.url
            assert pg.evaluate(LEVEL_SAID) == ""
        pg.close()


# the reader's pages say what the reader can see or do, never a command, a line of the YAML or a section of SPEC
NOT_FOR_READERS = re.compile(r"SPEC §|ergostat\.yaml|`ergostat |relations:|under with:|/private/tmp")
READERS_DEMOS = ["first-loop", "image-squeeze", "roadmap", "software-factory", "the-job", "ticket-factory"]
PANELS = """async (which) => {
  // each panel the page opens, as a click opens it: its text once what it asks for has come
  const out = [], settle = () => new Promise((r) => setTimeout(r, 300));
  const take = async (what, open) => {
    try { await open(); } catch (e) { out.push([what, `failed to open: ${e}`]); return; }
    await settle();
    for (let i = 0; i < 20 && document.querySelector('#detail')?.innerText.includes('\\u2026'); i++) await settle();
    out.push([what, document.querySelector('#detail')?.innerText || '']);
  };
  if (which === "diagram") for (const n of S.graph.nodes.filter((n) => n.kind !== 'cloud')) await take(n.id, () => openNode(n));
  if (which === "systems") for (const n of S.graph.nodes.filter((n) => n.kind === 'system')) await take(n.id, () => openNode(n));
  if (which === "loops") for (const n of Object.keys(await api('loops'))) await take(`loop ${n}`, () => openLoop(n));
  if (which === "agents") for (const n of Object.keys(await api('agents'))) await take(`agent ${n}`, () => openAgent(n));
  return out;
}"""


@pytest.mark.slow
@pytest.mark.parametrize("example", READERS_DEMOS)
def test_the_readers_pages_name_no_command_yaml_line_or_spec_section(browser, tmp_path, example):
    """/diagram (its side panel and each part's panel), /loops (each loop's panel), /agents (each agent's panel) and
    /items (its list and its graph) say none of: a SPEC section, ergostat.yaml, a command, a YAML key, or an absolute
    path into the project (an agent's log is named by its file)."""
    with served(example, tmp_path) as url:
        folder = str(tmp_path.resolve())                  # the project and its home (its logs) are under it
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        said: list[tuple[str, str]] = []
        # both drawings: every part's panel with every system open, each system's own with them closed
        for i, (view, which) in enumerate([("view=dynamics&open=*", "diagram"), ("view=blocks&open=*", "diagram"),
                                           ("view=dynamics", "systems"), ("view=blocks", "systems")]):
            drawn(pg, url, view, i)
            said.append(("/diagram", pg.inner_text("body")))
            said += [(f"/diagram {w}", t) for w, t in pg.evaluate(PANELS, which)]
        for path, which in (("/loops", "loops"), ("/agents", "agents")):
            pg.goto(url + path)
            pg.wait_for_selector(".page h1")
            pg.wait_for_timeout(800)
            said.append((path, pg.inner_text("body")))
            said += [(f"{path} {w}", t) for w, t in pg.evaluate(PANELS, which)]
        pg.goto(url + "/items")
        pg.wait_for_selector(".page h1")
        pg.wait_for_timeout(800)
        said.append(("/items", pg.inner_text("body")))
        graph = pg.locator("button", has_text="Graph")
        if graph.count():
            graph.first.click()
            pg.wait_for_timeout(1500)
            said.append(("/items graph", pg.inner_text("body")))
        pg.close()
    found = re.compile(f"{NOT_FOR_READERS.pattern}|ergostat explain |{re.escape(folder)}")   # (a <code> shows no backticks)
    bad = sorted({(where.split(" ")[0], m.group(0), t[max(0, m.start() - 60):m.end() + 60]) for where, t in said
                  for m in found.finditer(t)})
    assert any(w.startswith("/agents agent") for w, _ in said), "no agent's panel was opened"
    assert any(w.startswith("/loops loop") for w, _ in said), "no loop's panel was opened"
    assert not bad, "\n".join(map(str, bad))
    assert not errors, errors


def test_the_harris_row_says_what_is_missing_not_where_to_write_it(browser, tmp_path):
    """A loop whose dead time is not known: its Harris row says so, not which YAML key to write it in (the demos are
    not run, so the row is drawn here from the answer the server gives such a loop, control/monitor.py)."""
    from ergostat.control.monitor import performance
    t = [float(i) for i in range(20)]
    hr = performance({"t": t, "h": 1.0, "e": [0.0] * 20, "u": [0.0] * 20}, "==", 0.0, None, None, [], "setting")["harris"]
    assert hr.get("needs_theta") and "process:" in hr["why"], hr         # the answer as the server gives it
    with served("first-loop", tmp_path) as url:
        pg = browser.new_page()
        pg.goto(url + "/loops")
        pg.wait_for_selector(".page h1")
        row = pg.evaluate("(hr) => performanceRows({ performance: { harris: hr } })[0]", hr)
        pg.close()
    assert row == ["Harris index", "needs the loop's dead time"], row


def test_the_diagram_has_one_caption_naming_its_type_the_models_purpose_and_its_verdict(browser, tmp_path):
    """/diagram has exactly one h1, one line under the view switch: the view's diagram type, the model's purpose, its
    systems and its verdict (Dynamics: goals; Blocks: control loops, the goals a controller holds); the svg is named
    by it (aria-labelledby), and switching to Blocks changes the type words."""
    purpose = "keep my work moving and nothing on fire"

    def with_purpose(d):
        f = d / "ergostat.yaml"
        f.write_text(f.read_text().replace("name: the-job\n", f"name: the-job\npurpose: {purpose}\n", 1))

    with served("the-job", tmp_path, with_purpose) as url:
        st = json.loads(urllib.request.urlopen(url + "/api/status", timeout=10).read())
        assert st["purpose"] == purpose and st["top"] >= 1, st.get("purpose")
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        seen = {}
        for view, words in [("dynamics", "Stock-and-flow diagram (system dynamics)"), ("blocks", "Block diagram (control)")]:
            if view == "dynamics":
                drawn(pg, url, "view=dynamics", 0)
            else:
                pg.click(".toolbar .seg[aria-label='View'] button:text-is('Blocks')")
                pg.wait_for_function("() => /view=blocks/.test(location.href) && S.graph?.kind === 'blocks'",
                                     timeout=DRAWN_S * 1000)
            got = pg.evaluate("""() => { const hs = [...document.querySelectorAll('h1')], c = hs[0];
              const sw = document.querySelector(".toolbar .seg[aria-label='View']").getBoundingClientRect();
              const r = c && c.getBoundingClientRect(), lh = c ? parseFloat(getComputedStyle(c).lineHeight) || 20 : 20;
              return { n: hs.length, text: c?.textContent || '', id: c?.id || '', visible: !!(r && r.width && r.height),
                       under: !!(r && r.top >= sw.bottom - 1), line: !!(r && r.height < 2 * lh),
                       label: document.querySelector('svg.canvas')?.getAttribute('aria-labelledby') }; }""")
            assert got["n"] == 1, got
            assert got["text"].startswith(words + " · the-job: " + purpose), got["text"]
            assert got["id"] and got["label"] == got["id"], got
            assert got["visible"] and got["under"] and got["line"], got
            seen[view] = got["text"]
        # the system's goals and the server's count of them off (state.goals_off), model upkeep apart (an upkeep goal
        # off: tests/test_items_page.py::test_every_surface_prints_the_servers_one_count_of_goals_off)
        def said(names, g, word):
            up = sum(g["own"].values())
            return (f"{sum(not st['loops'][x].get('upkeep') for x in names)} {word}, {g['system']} off"
                    + (f" · model upkeep {up}" if up else ""))
        assert seen["dynamics"].endswith(said(st["loops"], st["goals_off"], "goals")), seen["dynamics"]
        assert seen["blocks"].endswith(said(st["controlled"], st["controlled_off"], "control loops")), seen
        assert f" · {st['top']} system" in seen["blocks"], seen["blocks"]
        assert "system dynamics" not in seen["blocks"] and "(control)" not in seen["dynamics"], seen
        pg.close()
    assert not errors, errors


GROUPED = """
name: grouped
stocks:
  backlog:
    unit: tickets
    sensor:
      manual: true
flows:
  finishing:
    from: backlog
goals:
  short-backlog:
    stock: backlog
    hold: "<= 5"
blocks:
  reviewer:
    type: person
    ask: review the backlog
    goal: short-backlog
    out: flow.finishing
uses:
  modelling:
    use: modelling
"""
GROUPS = """() => [...document.querySelectorAll('.side h3.att-head')].map((hd) => {
  const det = hd.closest('details'), list = det ? det.querySelector('.att') : hd.nextElementSibling;
  const rows = [...list.children].filter((x) => !x.classList.contains('none') && !x.classList.contains('may-do'));
  return { head: hd.textContent.trim(), open: det ? det.open : true,
           rows: rows.map((x) => x.tagName === 'HR' ? '---' : x.textContent.trim()),
           words: rows.filter((x) => x.tagName === 'DIV')
                      .map((x) => x.firstElementChild?.classList.contains('att-word') ? x.firstElementChild.textContent : '') };
})"""


def test_needs_attention_is_three_headed_groups_in_a_fixed_order(browser, tmp_path, monkeypatch):
    """The side list (design review Q42): 'Waiting for you N', 'Goals off N' (the system's goals first, modelling's
    after a rule), 'Model housekeeping N' (folded), always in that order, each ending in its count; the 'Goals off'
    count is the header's (the server's goals_off: the system's, model upkeep apart); every entry
    begins with its state or kind word, so colour is not the only cue."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "grouped"
    d.mkdir()
    (d / "ergostat.yaml").write_text(GROUPED)
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))       # the server is given it too
    p = Project(mdl.load(d))
    now = time.time()
    p.measurements.add("sensor/backlog.main", 9, at=now - 30)                    # the system's goal: off
    p.measurements.add("sensor/unanswered-requests.main", 3, at=now - 30)        # modelling's goal: off
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 2, "ask": "review the backlog"})
    from ergostat.numbers import requests as rq
    for code in ("collector-undescribed", "flow-unmeasured"):                  # modelling's held requests: housekeeping
        rq.event(p, rq.rid("check", code, "flow.x"), "held", {"code": code, "about": "flow.x", "source": "check",
                                                               "tier": "ai", "why": "its tries are used"})
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for view in ("", "diagram?view=blocks"):
            pg.goto(f"{url}/{view}")
            pg.wait_for_function("() => document.querySelectorAll('.side h3.att-head').length === 3 && "
                                 "/goals? off/.test(document.querySelector('#running')?.textContent || '')", timeout=30000)
            groups = pg.evaluate(GROUPS)
            heads = [g["head"] for g in groups]
            assert [re.sub(r" \d+( · model upkeep \d+)?$", "", x) for x in heads] == ["Waiting for you", "Goals off",
                                                                                      "Model housekeeping"], heads
            waiting, off, house = groups
            assert [int(heads[i].rsplit(" ", 1)[1]) for i in (0, 2)] == [len(waiting["rows"]), len(house["rows"])], heads
            # the 'Goals off' count is the header's, the server's (state.goals_off): the system's, model upkeep apart
            header, upkeep = pg.locator("#running").inner_text(), pg.locator("#upkeep").inner_text().strip()
            assert int(re.match(r"(\d+) goals? off", header).group(1)) == 1 and upkeep == "· model upkeep 1", (header, upkeep)
            assert heads[1] == "Goals off 1 · model upkeep 1", heads
            assert len(waiting["rows"]) == 1 and waiting["rows"][0].startswith("waiting · ") \
                and "request/" not in waiting["rows"][0], waiting                # only the person's ask
            held = [r for r in house["rows"] if r.startswith("request · ")]   # each read as its sentence
            assert len(held) == 2 and all("Modelling cannot decide it" in r for r in held), house
            word = "loop" if view else "goal"                   # (Dynamics calls a controlled goal a goal)
            assert off["rows"][0].startswith(f"off · {word} short-backlog"), off       # the system's first,
            assert off["rows"][1] == "---", off                                         # a rule,
            assert off["rows"][2].startswith(f"off · {word} requests-handled"), off    # then modelling's
            assert not house["open"] or "fault · " in house["words"], house            # folded, unless a fault is in it
            for g in groups:                                    # a state or kind word first, never colour alone
                assert all(re.fullmatch(r"[a-z]+ · ", w) for w in g["words"]), g
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


# plots.js's heatmap of rows (dev/records/dashboard-new-chart-forms.md), mounted with fixed data on a test page
# served by route() beside the real static files; the checks read the drawn canvas so each can fail
PLOTS_PAGE = ('<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/static/style.css">'
              '<main id="m" style="width:720px"></main>' + "".join(
                  f'<script src="/static/{f}.js"></script>' for f in ("elk.bundled", "uplot/uPlot.iife.min", "util", "charts", "plots")))
PLOTS_SEED = """import time, sys; from pathlib import Path; from ergostat import model as mdl; from ergostat.store import Project
p = Project(mdl.load(Path(sys.argv[1]))); now = time.time(); p.events.add("ergostat.started", at=now - 600)
for i in range(6):
    p.measurements.add(p.model.spec.stocks["disk-used"].sensors["main"].series, 50 + 6 * i, at=now - 550 + i * 100)
    p.events.add("valve.opened", item="delete-old-files", data={"amount": 1}, at=now - 560 + i * 100)"""
PLOTS_MOUNT = """async () => {
  const T = Array.from({ length: 12 }, (_, i) => 1.7e9 + i * 60), m = document.getElementById("m");
  m.append(heatmap(heatOfStates({ kind: "pr", times: T, states: ["open", "review", "merged"],
    counts: { open: T.map((_, i) => (i % 2 ? 4 : 0)), review: T.map(() => 2), merged: T.map(() => 4) } })));
  m.append(heatmap(heatOfGoals([{ goal: "g", unit: "%", times: T, off: [[T[3], T[5]]], e: T.map((_, i) => -i) }])));
  for (let n = 0; n < 100 && [...m.querySelectorAll(".chart-plot")].some((e) => !e.plot); n++) await new Promise((r) => setTimeout(r, 50));
  const plot = (c) => m.querySelector(`.${c} .chart-plot`).plot, one = document.createElement("canvas").getContext("2d");
  const rgb = (t) => { one.fillStyle = tok(t); one.fillRect(0, 0, 1, 1); return [...one.getImageData(0, 0, 1, 1).data].slice(0, 3); };
  const at = (u, x, y) => [...u.ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data].slice(0, 3);
  const near = (a, b) => a.every((v, i) => Math.abs(v - b[i]) < 40);
  const hm = plot("plot-heat"), cell = (i, k) => at(hm, hm.valToPos(T[i], "x", true), hm.valToPos(3 - k - 0.5, "y", true));
  const want = { 0: (i) => (i % 2 ? "--ink" : "--fill"), 1: () => "--fan-50", 2: () => "--ink" };
  return {
    heatCols: m.querySelector(".plot-heat").querySelectorAll("thead th").length - 1,
    cells: [0, 1, 2].every((k) => T.every((_, i) => near(cell(i, k), rgb(want[k](i))))),
    off: [4, 8].map((i) => { const g = m.querySelectorAll(".plot-heat .chart-plot")[1].plot;
      return near(at(g, g.valToPos(T[i], "x", true), g.valToPos(1, "y", true) + 1), rgb("--bad")); }),
    goalKey: m.querySelectorAll(".plot-heat .plot-key")[1].textContent,
    named: [...m.querySelectorAll("figure")].map((f) => f.getAttribute("aria-label")) };
}"""


def test_the_heatmap_of_rows_draws_in_each_theme(browser, tmp_path):
    """A heatmap of a kind's states: a row per state, a cell per bucket on the ramp, a goal's off stretch hatched; every
    figure named; light and dark, no console error."""
    seed = lambda d: subprocess.run([sys.executable, "-c", PLOTS_SEED, str(d)], check=True, capture_output=True,  # noqa: E731
                                    env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")})
    errors: list[str] = []
    with served("disk-space", tmp_path, edit=seed) as url:
        for theme in ("light", "dark"):
            pg = browser.new_page(color_scheme=theme, viewport={"width": 900, "height": 1200})
            pg.on("pageerror", lambda e, t=theme: errors.append(f"{t}: {e}"))
            pg.on("console", lambda m, t=theme: errors.append(f"{t}: {m.text}") if m.type == "error" else None)
            pg.route(f"{url}/plots-test", lambda r: r.fulfill(content_type="text/html", body=PLOTS_PAGE))
            pg.goto(f"{url}/plots-test")
            got = pg.evaluate(PLOTS_MOUNT)
            pg.close()
            assert got["heatCols"] == 3 and got["cells"], (theme, got)              # one row per state, a cell per bucket
            assert got["off"] == [True, False] and "its own lowest" in got["goalKey"] and "off" in got["goalKey"], (theme, got)
            assert len(got["named"]) == 2 and all(got["named"]), (theme, got["named"])
    assert not errors, errors


# the header's link: its text, its box, and whether it is the header's first element
WAITS_LINK = """() => { const a = [...document.querySelectorAll('header a')].find((x) => /wait/.test(x.textContent));
  if (!a || a.hidden) return null;
  const r = a.getBoundingClientRect(), box = (x) => x.getBoundingClientRect();
  const first = [...document.querySelectorAll('header *')].filter((x) => !x.children.length && box(x).width > 0)
    .sort((p, q) => box(p).top - box(q).top || box(p).left - box(q).left)[0];
  return { text: a.textContent.trim(), bottom: r.bottom + scrollY, first: first === a }; }"""
WAITING_HEAD = """() => { const hd = document.getElementById('waiting'); if (!hd) return null;
  const r = hd.getBoundingClientRect();
  return { text: hd.textContent, top: r.top, bottom: r.bottom, height: r.height, inner: innerHeight,
           focused: document.activeElement === hd, active: document.activeElement?.outerHTML.slice(0, 80) }; }"""
WAITING_SHOWN = f"""() => {{ const w = ({WAITING_HEAD})();
  return !!w && /^Waiting for you/.test(w.text) && w.top >= 0 && w.bottom <= w.inner && w.height > 0 && w.focused; }}"""


def waiting_shown(pg, what) -> None:
    try:
        pg.wait_for_function(WAITING_SHOWN, timeout=60000)
    except Exception:
        raise AssertionError((what, pg.url, pg.evaluate(WAITING_HEAD))) from None


def test_what_waits_for_you_is_one_step_from_every_page(browser, tmp_path, monkeypatch):
    """Design review Q43: beside the loops count the header says 'N wait for you', in the first 200 px of /items,
    /agents, /loops and /record at 1440 and 390 px (at 390 the header's first thing); following it shows the Diagram's
    'Waiting for you' heading, focused, inside the viewport. N is the side list's own count of that group."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "waits"
    d.mkdir()
    (d / "ergostat.yaml").write_text(GROUPED.replace("goals:\n", "  archiving:\n    from: backlog\ngoals:\n").replace(
        "uses:\n", "  approver:\n    type: person\n    ask: approve the plan\n    goal: short-backlog\n"
                   "    out: flow.archiving\nuses:\n"))                     # a second person block
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    p = Project(mdl.load(d))
    now = time.time()
    p.measurements.add("sensor/backlog.main", 9, at=now - 30)                    # a goal off: not waiting on a person
    for who, ask in (("reviewer", "review the backlog"), ("approver", "approve the plan")):   # two asks: "2 wait for you"
        p.events.add("person.asked", item=who, source="ergostat", data={"command": 2, "ask": ask})
    from ergostat.numbers import requests as rq
    rq.event(p, rq.rid("check", "flow-unmeasured", "flow.x"), "held", {"code": "flow-unmeasured", "about": "flow.x",
                                                                       "source": "check", "tier": "ai", "why": "used"})
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        for width, height in ((1440, 900), (390, 844)):
            pg = browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            for path in ("items", "agents", "loops", "record"):
                pg.goto(f"{url}/{path}")
                pg.wait_for_function(WAITS_LINK, timeout=30000)
                got = pg.evaluate(WAITS_LINK)
                assert got["text"] == "2 wait for you", (width, path, got)
                assert got["bottom"] <= 200, (width, path, got)
                if width < 700:
                    assert got["first"], (width, path, got)            # on a phone, the header's first thing
                pg.locator("header a", has_text="wait for you").click()
                waiting_shown(pg, (width, path))
                assert pg.evaluate("location.pathname") == "/diagram", path
                head = pg.locator("#waiting").inner_text()
                assert re.sub(r"\s+", " ", head).strip() == "Waiting for you 2", head   # the side list's own count
            pg.goto("about:blank")
            pg.goto(f"{url}/diagram#waiting")                          # the address itself, loaded afresh
            waiting_shown(pg, (width, "loaded"))
            pg.evaluate("() => { document.activeElement.blur(); document.querySelector('main').scrollTop = 0; scrollTo(0, 0); "
                        "history.replaceState(null, '', '/diagram'); }")
            pg.evaluate("() => { location.hash = 'waiting'; }")         # and asked for on the Diagram itself
            waiting_shown(pg, (width, "hash"))
            pg.close()
            assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


# the header's "N wait for you" as found, then after every write into the polite live region holding it (null when none
# holds it): a write of the same text again counts too, since a screen reader may say it again
WAITS_HEARD = """() => { const a = document.getElementById('waits'), live = a && a.closest('[aria-live="polite"]');
  if (!live) return null;
  if (!window.__heard) { window.__heard = [live.textContent];
    new MutationObserver(() => { window.__heard.push(live.textContent); })
      .observe(live, { subtree: true, childList: true, characterData: true }); }
  return window.__heard; }"""


@pytest.mark.slow
def test_a_changed_count_of_what_waits_is_announced(browser, tmp_path, monkeypatch):
    """Design review Q77: the header's 'N wait for you' sits in an aria-live='polite' region, and its text changes only
    when N changes: polls with nothing new write nothing a screen reader would say, and a new request is said once."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "heard"
    d.mkdir()
    (d / "ergostat.yaml").write_text(GROUPED.replace("goals:\n", "  archiving:\n    from: backlog\ngoals:\n").replace(
        "uses:\n", "  approver:\n    type: person\n    ask: approve the plan\n    goal: short-backlog\n"
                   "    out: flow.archiving\nuses:\n"))
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    p = Project(mdl.load(d))
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 2, "ask": "review the backlog"})
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                assert time.monotonic() < deadline and proc.poll() is None, "the page never answered"
                time.sleep(0.2)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.add_init_script("performance.setResourceTimingBufferSize(100000)")   # every header poll counted
        pg.goto(f"{url}/items")
        pg.wait_for_function("() => document.getElementById('waits')?.textContent === '1 wait for you'", timeout=30000)
        assert pg.evaluate(WAITS_HEARD) == ["1 wait for you"]           # inside a polite region, watched from here
        polls = pg.evaluate("() => performance.getEntriesByType('resource').filter((r) => /api\\/status/.test(r.name)).length")
        pg.wait_for_function(f"() => performance.getEntriesByType('resource').filter((r) => /api\\/status/.test(r.name))"
                             f".length >= {polls + 2}", timeout=30000)   # two header polls with nothing new
        assert pg.evaluate(WAITS_HEARD) == ["1 wait for you"]           # wrote nothing
        p.events.add("person.asked", item="approver", source="ergostat", data={"command": 2, "ask": "approve the plan"})
        pg.wait_for_function("() => document.getElementById('waits').textContent === '2 wait for you'", timeout=30000)
        polls = pg.evaluate("() => performance.getEntriesByType('resource').filter((r) => /api\\/status/.test(r.name)).length")
        pg.wait_for_function(f"() => performance.getEntriesByType('resource').filter((r) => /api\\/status/.test(r.name))"
                             f".length >= {polls + 1}", timeout=30000)
        assert pg.evaluate(WAITS_HEARD) == ["1 wait for you", "2 wait for you"]   # the change, said once
        pg.close()
        assert not errors, errors
    finally:
        proc.terminate()
        proc.wait(10)


# ---- drawn alone: what an item passed through, or what a kind touches (item= and kind=, SPEC §5a)

def seed_scrum2(p, t: float) -> None:
    """ticket/SCRUM-2 on ticket-factory: new, taken by pick-up to picked, taken by locate (a nack: picked again, a
    second run) to located, taken by work to worked; nothing after."""
    from ergostat.leases import ENDED, TAKEN
    ev, i = p.events, "ticket/SCRUM-2"
    ev.add("ticket.found", item=i, data={"title": "a ticket"}, at=t)
    for n, (run, block, back, then, how) in enumerate([("r1", "pick-up", "new", "ticket.pick-up", "ack"),
                                                        ("r2", "locate", "picked", None, "nack"),
                                                        ("r3", "locate", "picked", "ticket.locate", "ack"),
                                                        ("r4", "work", "located", "ticket.work", "ack")]):
        at = t + 10 * (n + 1)
        ev.add(TAKEN, item=i, data={"run": run, "block": block, "fence": n + 1, "ttl": 300, "max": 3, "back": back}, at=at)
        if then:
            ev.add(then, item=i, causedby=run, at=at + 1)
        ev.add(ENDED, item=i, data={"run": run, "fence": n + 1, "how": how, **({"why": "x"} if how == "nack" else {})},
               at=at + 2)


SCRUM2 = {"stock:new", "stock:picked", "stock:located", "stock:worked", "flow:pick-up", "flow:locate", "flow:work"}
SUBSET_DRAWN = ("() => typeof S !== 'undefined' && S.layout && S.graphSig && S.graph?.subset && "
                "document.querySelectorAll('svg.canvas g.node').length > 0")


def graph_of(url: str, **q) -> dict:
    from urllib.parse import urlencode
    return json.loads(urllib.request.urlopen(f"{url}/api/graph?{urlencode(q)}", timeout=60).read())


def test_an_items_path_is_drawn_alone(browser, tmp_path):
    """Dynamics with item=: exactly the stocks and valves on ticket/SCRUM-2's path, each stock numbered by its steps
    in move order (picked twice: a nack), each valve with the runs that took it; the chip clears it back to the whole,
    with no page error, and the subset lays out in under a second."""
    from ergostat import model as mdl
    from ergostat.store import Project
    with served("ticket-factory", tmp_path) as url:
        seed_scrum2(Project(mdl.load(tmp_path / "ticket-factory")), time.time() - 3000)
        time.sleep(1.6)                                   # past the page's snapshot of the moment it started
        g = graph_of(url, view="dynamics", item="ticket/SCRUM-2")
        assert {n["id"] for n in g["nodes"]} == SCRUM2, sorted(n["id"] for n in g["nodes"])
        marks = {n["id"]: n.get("path") for n in g["nodes"] if n["kind"] == "stock"}
        assert marks == {"stock:new": [1], "stock:picked": [2, 3], "stock:located": [4], "stock:worked": [5]}, marks
        runs = {n["id"]: n.get("attempts") for n in g["nodes"] if n["kind"] == "valve"}
        assert runs == {"flow:pick-up": 1, "flow:locate": 2, "flow:work": 1}, runs
        assert g["subset"]["says"] == "what ticket/SCRUM-2 passed through" and g["subset"]["kind"] == "ticket"
        whole = graph_of(url, view="dynamics", open="*")
        assert SCRUM2 < {n["id"] for n in whole["nodes"]} and "subset" not in whole
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(f"{url}/diagram?view=dynamics&item=ticket%2FSCRUM-2")
        pg.wait_for_function(SUBSET_DRAWN, timeout=DRAWN_S * 1000)
        drawn_ids = pg.evaluate("() => [...document.querySelectorAll('svg.canvas g.node')].map((g) => g.dataset.id)")
        assert set(drawn_ids) == SCRUM2, drawn_ids
        nums = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('svg.canvas g.node')]"
                           ".filter((g) => g.querySelector('.sd-path'))"
                           ".map((g) => [g.dataset.id, g.querySelector('.sd-path').textContent]))")
        assert nums == {"stock:new": "1", "stock:picked": "2, 3", "stock:located": "4", "stock:worked": "5"}, nums
        assert "2 attempts" in pg.locator('svg.canvas g.node[data-id="flow:locate"]').text_content()
        assert pg.evaluate("() => S.pinKey").endswith(".kind:ticket")     # an item's pins are its kind's
        assert pg.evaluate("() => S.showHulls") is False                  # flat, as around= is
        first, _ = pg.evaluate(TIMED)
        assert first < 1000, first
        chip = pg.locator(".toolbar .subset")
        assert chip.inner_text().startswith("what ticket/SCRUM-2 passed through")
        chip.locator("button").click()
        pg.wait_for_function("() => !location.search.includes('item=') && S.graph && !S.graph.subset && S.layout",
                             timeout=DRAWN_S * 1000)
        assert pg.locator(".toolbar .subset").count() == 0
        pg.close()
    assert not errors, errors


def test_blocks_draws_whole_loops_an_item_touched(tmp_path):
    """Blocks with item=: the control loops whose parts ticket/SCRUM-2 passed through, each drawn whole (every node
    of each, as the whole diagram opened draws them), nothing outside them but ports, no system closed into a box;
    kind=ticket draws the kind's footprint, and a kind nothing counts says so and draws nothing."""
    from ergostat import model as mdl
    from ergostat.store import Project

    def edit(d):
        (d / "local").mkdir(exist_ok=True)
        (d / "local" / "note.yaml").write_text("items:\n  note: {id: note/*, states: [open, closed]}\n")
    with served("ticket-factory", tmp_path, edit) as url:
        p = Project(mdl.load(tmp_path / "ticket-factory"))
        seed_scrum2(p, time.time() - 3000)
        p.events.add("note.made", item="note/1")
        time.sleep(1.6)
        g = graph_of(url, view="blocks", item="ticket/SCRUM-2")
        whole = graph_of(url, view="blocks", open="*")
        drawn = [n for n in g["nodes"] if n.get("kind") != "port"]
        touched = {n["id"].split(":", 1)[1] for n in drawn if n["id"].startswith("ref:")}    # a loop's own reference
        assert {"new-picked-up", "picked-located", "located-worked", "worked-opened"} <= touched, touched
        assert not touched & {"opened-asked", "reviews-answered", "merged-closed"}, touched
        ids = {n["id"] for n in drawn}
        looped = {n["id"] for n in drawn if set(n["loops"]) & touched}
        between = {e["target"] for e in g["edges"] if e["source"] in looped} & {e["source"] for e in g["edges"]
                                                                                if e["target"] in looped}
        assert ids == looped | between, sorted(ids - looped - between)    # a loop's parts, and what joins two of them
        assert {"psum:stock.picked", "psum:stock.located"} <= ids         # a stock's sum: the loop not cut there
        assert not [n["id"] for n in g["nodes"] if n["id"].startswith("sys:")]
        for goal in touched:                              # each whole: as the whole diagram, everything open, draws it
            want = {n["id"] for n in whole["nodes"] if goal in n.get("loops", [])}
            assert want == {n["id"] for n in drawn if goal in n["loops"]}, goal
        assert len(drawn) < len([n for n in whole["nodes"] if n.get("kind") != "port"])
        fp = json.loads(urllib.request.urlopen(f"{url}/api/kinds/ticket").read())
        k = graph_of(url, view="dynamics", kind="ticket")
        want = {f"{'flow' if c['kind'] == 'flow' else 'stock'}:{c['name']}" for c in fp["counted_in"]}
        want |= {f"flow:{f.split('.', 1)[1]}" for t in fp["taken_by"] for f in t["out"]}
        assert {n["id"] for n in k["nodes"] if n["kind"] in ("stock", "auxiliary", "valve", "disturbance")
                and not n.get("outside")} == want and k["subset"]["says"] == "what kind ticket touches"
        for view in ("dynamics", "blocks"):
            none = graph_of(url, view=view, item="note/1")
            assert not none["nodes"] and none["subset"]["says"] == "what note/1 passed through: not counted anywhere in the model"


# ---- a closed module's sparklines (dev/records/module-box-sparklines.md)

SPARKED = """
name: sparked
systems:
  reception-and-triage:
    description: the desk
    show: [stock.backlog, auxiliary.pressure, flow.arriving, stock.spare]
  archive:
    description: what it serves
    show: [stock.filed]
stocks:
  backlog: {unit: tickets, system: reception-and-triage, sensor: {manual: true}}
  spare: {unit: things, system: reception-and-triage, sensor: {manual: true}}
  filed: {unit: tickets, system: archive, sensor: {manual: true}}
flows:
  arriving: {to: backlog, system: reception-and-triage, sensor: {manual: true}}
  finishing: {from: backlog, to: filed, system: reception-and-triage}
auxiliaries:
  pressure: {unit: share, driven-by: +stock.backlog, system: reception-and-triage, sensor: {manual: true}}
  load: {driven-by: +stock.spare, system: archive}
  heat: {driven-by: +auxiliary.pressure, system: archive}
"""
DESK = "system:reception-and-triage"
# every spark row drawn: its box, whether that box is a closed module, its texts, its line, whether it is inside its box
SPARKS = """() => [...document.querySelectorAll('svg.canvas .sd-spark')].map((r) => {
  const g = r.closest('g.node'), a = r.getBoundingClientRect(), b = g.querySelector('.hit').getBoundingClientRect();
  const line = r.querySelector('.sd-spark-line');
  return { box: g.dataset.id, module: g.classList.contains('k-system'), ref: r.dataset.ref,
           texts: [...r.querySelectorAll('text')].map((t) => t.textContent), d: line?.getAttribute('d') || '',
           inside: a.left >= b.left - 0.5 && a.right <= b.right + 0.5 && a.top >= b.top - 0.5 && a.bottom <= b.bottom + 0.5,
           stroke: line ? getComputedStyle(line).stroke : null,
           paper: getComputedStyle(document.querySelector('svg.canvas')).backgroundColor };
})"""
# where every box is, and how big: its layout, its transform, its outline and all it draws, on the screen
PLACES = """() => [...document.querySelectorAll('svg.canvas g.node')].map((g) => {
  const c = S.layout.children.find((x) => x.id === g.dataset.id), r = g.getBoundingClientRect();
  const h = g.querySelector('.hit')?.getBoundingClientRect();
  const at = (b) => [b.x, b.y, b.width, b.height].map((v) => Math.round(v * 10) / 10);
  return [g.dataset.id, g.getAttribute('transform'), c ? [c.x, c.y, c.width, c.height] : null, at(r), h ? at(h) : null];
}).sort()"""


@contextlib.contextmanager
def sparked(tmp_path: Path):
    """SPARKED's page, an hour and more of readings every 30s, backlog's missing from 30 to 10 minutes ago."""
    from ergostat import model as mdl
    from ergostat.store import Project
    d = tmp_path / "sparked"
    d.mkdir()
    (d / "ergostat.yaml").write_text(SPARKED)
    env = {**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")}
    old = os.environ.get("ERGOSTAT_HOME")
    os.environ["ERGOSTAT_HOME"] = env["ERGOSTAT_HOME"]
    try:
        p = Project(mdl.load(d))
        now = time.time()
        for i in range(150):
            t = now - 4500 + i * 30
            if not now - 1800 <= t < now - 600:
                p.measurements.add("sensor/backlog.main", 4 + 3 * math.sin(i / 9), at=t)
            p.measurements.add("sensor/pressure.main", 0.5 + 0.3 * math.cos(i / 11), at=t)
            p.measurements.add("sensor/arriving.main", 6 + i % 4, at=t)
            p.measurements.add("sensor/spare.main", 2, at=t)
            p.measurements.add("sensor/filed.main", i, at=t)
    finally:
        if old is None:
            os.environ.pop("ERGOSTAT_HOME", None)
        else:
            os.environ["ERGOSTAT_HOME"] = old
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                urllib.request.urlopen(url + "/api/status", timeout=2)
                break
            except Exception:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise AssertionError("the page never answered") from None
                time.sleep(0.2)
        yield url
    finally:
        proc.terminate()
        proc.wait(10)


def _asked_again(pg, asked: list, n: int) -> None:
    for _ in range(100):
        if len(asked) > n:
            return
        pg.wait_for_timeout(100)


@pytest.mark.slow
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_closed_module_draws_three_sparklines_after_its_structure_without_moving_a_box(browser, tmp_path, scheme):
    """Done items 1 to 4: a closed module shows its first three headline measures (its show:), each its name, its value
    now, its line and its scale, inside its box; the boxes are where they were and as big before the one batched answer
    (held back here) and after it; the line has a gap where backlog was not read; too small to read when zoomed out,
    none is drawn; a click on one opens the module's panel; an open module, a stock or a flow draws none."""
    import urllib.parse
    with sparked(tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000}, color_scheme=scheme)
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        asked: list[str] = []
        held: list = []
        failing = [False]

        def hold(route):                                 # the first answer held until the boxes are measured
            asked.append(route.request.url)
            if len(asked) == 1:
                held.append(route)
            elif failing[0]:
                route.fulfill(status=500, body="no")
            else:
                route.continue_()
        pg.route(re.compile(r"/api/series\?.*measured=1"), hold)
        drawn(pg, url, "view=dynamics", 0)
        _asked_again(pg, asked, 0)
        assert len(held) == 1, asked
        before = pg.evaluate(PLACES)
        assert pg.evaluate(SPARKS) == [], "drawn before its answer"
        refs = urllib.parse.parse_qs(urllib.parse.urlsplit(asked[0]).query)["refs"][0].split(",")
        assert sorted(refs) == ["flow.arriving", "stock.backlog", "stock.filed", "stock.pressure"], refs   # every box's
        assert len(asked) == 1, asked                                                                       # in one ask
        held[0].continue_()
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas .sd-spark').length >= 4", timeout=30000)
        assert pg.evaluate(PLACES) == before, "a box moved or changed its size when its sparklines came"
        got = pg.evaluate(SPARKS)
        mine = {x["ref"]: x for x in got if x["box"] == DESK}
        assert sorted(mine) == ["auxiliary.pressure", "flow.arriving", "stock.backlog"], got      # three: the first three
        assert [x["ref"] for x in got if x["box"] != DESK] == ["stock.filed"], got
        assert all(x["module"] and x["inside"] for x in got), got
        charted = pg.evaluate(f"() => S.graph.nodes.find((n) => n.id === '{DESK}').charted")
        for x in mine.values():
            m = next(c for c in charted if c["part"].split(":")[1] == x["ref"].split(".")[1])
            assert x["texts"][0] == m["label"] and x["texts"][1].split(" ")[0] == m["value"].split(" ")[0], (x, m)   # now
            assert re.fullmatch(r"\S+–\S+", x["texts"][2]), x                                          # its own scale
            assert x["stroke"] and x["stroke"] != x["paper"], x
        assert mine["stock.backlog"]["d"].count("M") == 2, mine["stock.backlog"]      # a gap where it was not read
        assert mine["auxiliary.pressure"]["d"].count("M") == 1, mine["auxiliary.pressure"]
        pg.evaluate("() => { S.view.k = 0.3; applyView(document.querySelector('svg.canvas')); }")
        assert pg.evaluate(SPARKS) == [], "drawn too small to read"
        pg.evaluate("() => { S.view.k = 1; applyView(document.querySelector('svg.canvas')); }")
        assert len(pg.evaluate(SPARKS)) == 4
        n = len(asked)
        _asked_again(pg, asked, n)                       # asked again on the page's interval
        assert len(asked) > n, asked
        failing[0] = True                                # not answered: the last lines are not kept as if read now
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas .sd-spark').length === 0", timeout=30000)
        failing[0] = False
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas .sd-spark').length === 4", timeout=30000)
        row = pg.locator(f'svg.canvas g.node[data-id="{DESK}"] .sd-spark[data-ref="stock.backlog"]').bounding_box()
        pg.mouse.click(row["x"] + row["width"] / 2, row["y"] + row["height"] / 2)
        pg.wait_for_function(TITLED, arg="reception-and-triage", timeout=10000)   # its panel, with the full charts
        drawn(pg, url, "view=dynamics&open=reception-and-triage", 1)
        _asked_again(pg, asked, len(asked))
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas .sd-spark').length >= 1", timeout=30000)
        got = pg.evaluate(SPARKS)
        assert all(x["box"] == "system:archive" and x["module"] for x in got), got   # the open one draws none
        drawn(pg, url, "view=dynamics&open=*", 2)
        pg.wait_for_timeout(1500)
        assert pg.evaluate(SPARKS) == [], "a stock, a flow or an auxiliary drew one"
        pg.close()
        assert not errors, errors


def test_a_measure_the_answer_cut_past_its_ceiling_draws_nothing_never_no_readings(browser, tmp_path):
    """The measured answer reads at most MEASURED_REFS parts and names the rest in ``cut``: a box whose measure was cut
    (here archive's, the answer rewritten as the server's would be past its ceiling) draws nothing for it, never 'no
    readings', while the parts answered draw as before."""
    import json as _json
    with sparked(tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        def cut(route):
            d = route.fetch().json()
            d["series"] = [x for x in d["series"] if x["ref"] != "stock.filed"]
            d["cut"] = ["stock.filed"]
            route.fulfill(status=200, content_type="application/json", body=_json.dumps(d))
        pg.route(re.compile(r"/api/series\?.*measured=1"), cut)
        drawn(pg, url, "view=dynamics", 0)
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas .sd-spark').length >= 3", timeout=30000)
        pg.wait_for_timeout(3000)                        # (and asked again on the interval: still nothing for it)
        got = pg.evaluate(SPARKS)
        assert sorted(x["ref"] for x in got) == ["auxiliary.pressure", "flow.arriving", "stock.backlog"], got
        assert all(x["box"] == DESK for x in got), got
        pg.close()
        assert not errors, errors


def test_an_examples_closed_modules_find_room_for_their_measures_and_nothing_read_is_no_line(browser, tmp_path):
    """image-squeeze, served unrun (nothing read): every closed module with a show: draws at least one of its measures in
    its box (room found in its own rows), each with no line and said as having no readings, and none outside its box."""
    with served("image-squeeze", tmp_path) as url:
        pg = browser.new_page(viewport={"width": 1600, "height": 1000})
        drawn(pg, url, "view=dynamics", 0)
        pg.wait_for_function("() => document.querySelectorAll('svg.canvas .sd-spark').length > 0", timeout=30000)
        got = pg.evaluate(SPARKS)
        boxes = pg.evaluate("""() => S.graph.nodes.filter((n) => n.kind === 'system' && !n.upkeep && !n.remote &&
          (n.charted || []).length && document.querySelector(`svg.canvas g.node[data-id="${n.id}"]`)).map((n) => n.id)""")
        drew = {b: len([x for x in got if x["box"] == b]) for b in boxes}
        assert boxes and all(drew.values()), drew
        assert all(x["inside"] and x["module"] and not x["d"] and x["texts"][2] == "no readings" for x in got), got
        pg.close()
