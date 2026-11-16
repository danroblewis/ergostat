"""Acceptance: the control diagram of every example, drawn in a real browser, in every view (the
whole, everything open, each system opened, each drawn alone), draws no line through a part that
is not one of its ends, no line on top of another (lines merging into or out of one end are a net),
no line far longer than the way it covers, no two lines of one net crossing, and no page error;
draws within its time (ELK's layout, with ELK's lines), and has libavoid's lines within a
generous bound (routed in a worker, after the first draw).

And a generated model, 16 systems of 6 loops each (STRESS=systems,loops to change it), each
feeding the next and driving a flow two along: about 400 parts and 500 lines, drawn in about
0.2s and routed in about 4s; 1,000 lines (24,8) are drawn in about 0.4s and routed in about 15s.

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
    for i, v in enumerate(views):
        drawn(pg, url, v, i + 1)
        r = pg.evaluate(AUDIT)
        problems += [f"[{v or 'whole'}] {k}: {x}" for k in ("through", "overlap", "detour", "netCrossings") for x in r[k]]
        if r["mostPipeBends"][0] > MAX_PIPE_BENDS:                   # a flow reads best straight: the links bend instead
            problems.append(f"[{v or 'whole'}] pipe {r['mostPipeBends'][1]} bends {r['mostPipeBends'][0]} times")
        first, final = pg.evaluate(TIMED)
        slowest = max(slowest, (first, v or "whole"))
        routed = max(routed, (final, v or "whole"))
    pg.close()
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
  // each valve's information lines attach on the side most of what they join lies: its stem up, or turned down
  const box = Object.fromEntries(S.layout.children.map((c) => [c.id, c])), bad = [];
  for (const n of S.graph.nodes.filter((n) => n.kind === "valve" || n.kind === "disturbance")) {
    const c = box[n.id]; if (!c) continue;
    const ends = S.layout.edges.map((le) => [le, S.graph.edges.find((e) => e.id === le.id)])
      .filter(([, e]) => e && e.kind !== "pipe" && (e.source === n.id || e.target === n.id));
    if (!ends.length) continue;
    const below = ends.filter(([, e]) => {
      const o = box[e.source === n.id ? e.target : e.source];
      return o && o.y + o.height / 2 > c.y + c.height / 2 + 10;
    }).length;
    const wantDown = below > ends.length / 2;
    for (const [le, e] of ends) {
      const sec = le.sections[0], p = e.source === n.id ? sec.startPoint : sec.endPoint;
      const atBottom = Math.abs(p.y - (c.y + c.height)) < 3, atTop = Math.abs(p.y - c.y) < 3;
      if ((wantDown && !atBottom) || (!wantDown && !atTop)) bad.push(`${n.id}: ${le.id} at y ${p.y} (valve ${c.y}..${c.y + c.height})`);
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
