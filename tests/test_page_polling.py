"""Acceptance: a page left open does not grow. Each page of an example, served with a record, is left
open in a real browser with its polling sped up (every wait shortened tenfold, so a minute open is
ten minutes of refreshes); its retained heap and its DOM nodes stay within a bound of where they
settled, and no refresh holds the page up for long. Leaving a page stops its polling, even one left
while its first answer was on its way; a hidden tab asks for nothing.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_page_polling.py -v -s
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
SPEED = 10                     # every poll's wait shortened this much
OPEN_S = float(os.environ.get("POLL_OPEN_S", 40))    # how long each page is left open (x SPEED of refreshes)
HEAP_GROWTH_MB = 3.0           # retained heap (after a collection), from settled to the end
NODE_GROWTH = 0.10             # DOM nodes, as a share of where they settled (and 200 more)
LONG_TASK_P95_MS = 500         # each refresh's longest work on the main thread, on a laptop; generous
SETTLE_S = 120                 # the most a page may take to settle (drawn, routed, charts mounted), however loaded
# A fixed piece of work, timed in the page: how much slower this machine is now than the laptop the bounds were set
# on (REF_MS there, unloaded). The long-task bound scales by it, never below 1, so a loaded machine is held to the
# same work, not to the same milliseconds.
REF_MS = 8.5                   # measured 8.2 to 8.8 ms on the reference laptop (2026-11-18)
SPEED_PROBE = """() => { const t0 = performance.now(); let x = 0;
  for (let i = 0; i < 2e6; i++) x = (x * 31 + i) % 1000003;
  return [performance.now() - t0, x]; }"""
PAGES = ["diagram", "diagram?view=dynamics&open=*", "diagram?view=blocks", "diagram?view=process", "goals",
         "agents", "items", "item/hypothesis%2F1", "record", "model"]
INIT = f"""window.ERGOSTAT_POLL_SPEED = {SPEED}; window.__lt = [];
try {{ new PerformanceObserver((l) => {{ for (const e of l.getEntries()) window.__lt.push(e.duration); }})
        .observe({{ type: "longtask", buffered: true }}); }} catch (e) {{}}"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(d: Path, home: Path) -> None:
    """A record to show: items of two kinds moving through their states, some with large fields."""
    code = f"""
import time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path({str(d)!r})))
t = time.time() - 3000
for i in range(1, 41):
    p.events.add("hypothesis.proposed", item=f"hypothesis/{{i}}", data={{"title": f"idea {{i}}", "why": "x" * 400}}, at=t + i * 60)
    p.events.add("session.ran", item=f"session/s{{i}}", data={{"role": "researcher", "said": "y" * 300}}, at=t + i * 60 + 5)
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
    deadline = time.monotonic() + 120                    # a loaded machine starts it slowly: wait for it, not a count
    while True:
        try:
            urllib.request.urlopen(url + "/api/status", timeout=2)
            break
        except Exception:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                pytest.fail("the page never answered")
            time.sleep(0.2)
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                        # no Chromium here
            pytest.skip(f"no Chromium to drive: {e}")
        yield b
        b.close()


def metrics(cdp) -> dict:
    cdp.send("HeapProfiler.collectGarbage")
    return {x["name"]: x["value"] for x in cdp.send("Performance.getMetrics")["metrics"]}


def settle(pg, cdp, least: float = 8.0) -> dict:
    """The page's metrics once it has settled: at least ``least`` seconds after it opened, and then its DOM nodes and
    retained heap the same over three looks a second apart (heap within a tenth of a MB), however long that takes
    on a loaded machine, up to SETTLE_S."""
    pg.wait_for_timeout(least * 1000)
    deadline, last, same = time.monotonic() + SETTLE_S, None, 0
    while True:
        m = metrics(cdp)
        now = (m["Nodes"], m["JSHeapUsedSize"])
        same = same + 1 if last and now[0] == last[0] and abs(now[1] - last[1]) < 1e5 else 0
        if same >= 2 or time.monotonic() > deadline:
            return m
        last = now
        pg.wait_for_timeout(1000)


def slowness(pg) -> float:
    """How many times slower than the reference laptop the page's thread runs now (the best of three, at least 1)."""
    return max(1.0, min(pg.evaluate(SPEED_PROBE)[0] for _ in range(3)) / REF_MS)


@pytest.mark.parametrize("route", PAGES)
def test_a_page_left_open_does_not_grow(browser, site, route):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(INIT)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    asked = []
    pg.on("request", lambda r: asked.append(r.url) if "/api/" in r.url else None)
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Performance.enable")
    pg.goto(f"{site}/{route}")
    settled = settle(pg, cdp)                         # drawn, its lines routed, its charts mounted
    slow = slowness(pg)
    lt0 = pg.evaluate("window.__lt.length")
    n0 = len(asked)
    pg.wait_for_timeout(OPEN_S * 1000)
    end = metrics(cdp)
    slow = max(slow, slowness(pg))
    lts = pg.evaluate(f"window.__lt.slice({lt0})")
    ctx.close()
    heap = (end["JSHeapUsedSize"] - settled["JSHeapUsedSize"]) / 1e6
    nodes = end["Nodes"] - settled["Nodes"]
    p95 = sorted(lts)[int(0.95 * len(lts))] if lts else 0
    print(f"\n{route}: heap {settled['JSHeapUsedSize'] / 1e6:.1f}→{end['JSHeapUsedSize'] / 1e6:.1f} MB, nodes "
          f"{settled['Nodes']:.0f}→{end['Nodes']:.0f}, listeners {settled['JSEventListeners']:.0f}→{end['JSEventListeners']:.0f}, "
          f"{len(lts)} long tasks (p95 {p95:.0f} ms), {len(asked) - n0} requests, {slow:.1f}x slower than the reference")
    assert not errors, errors
    assert len(asked) - n0 > 5, "the page stopped refreshing"
    assert heap < HEAP_GROWTH_MB, f"retained heap grew {heap:.1f} MB"
    assert nodes < NODE_GROWTH * settled["Nodes"] + 200, f"DOM nodes grew by {nodes:.0f}"
    assert end["JSEventListeners"] < settled["JSEventListeners"] * (1 + NODE_GROWTH) + 50, "listeners pile up"
    assert p95 < LONG_TASK_P95_MS * slow, f"refreshes hold the page {p95:.0f} ms (p95; the bound {LONG_TASK_P95_MS * slow:.0f} ms " \
        f"on a machine {slow:.1f}x slower than the reference)"


def test_leaving_a_page_stops_its_polling(browser, site):
    """Pages left quickly, each before its first answer came: only the header's and the last page's polls go on."""
    pg = browser.new_page()
    pg.add_init_script(INIT)
    pg.goto(f"{site}/goals")
    pg.wait_for_timeout(3000)
    for r in ["/diagram", "/items", "/goals", "/diagram?view=blocks", "/agents", "/model", "/diagram"] * 2 + ["/record"]:
        pg.evaluate(f"navigate({r!r})")
        pg.wait_for_timeout(150)
    pg.wait_for_timeout(4000)
    alive = pg.evaluate("POLLS.size")
    asked = []
    pg.on("request", lambda r: asked.append(r.url.split("/api/")[1].split("?")[0]) if "/api/" in r.url else None)
    pg.wait_for_timeout(5000)
    pg.close()
    assert alive == 2, f"{alive} polls alive (the header's and the Record's)"
    assert set(asked) <= {"events", "status", "projects"}, f"pages left behind still ask: {sorted(set(asked))}"


def test_the_goals_page_and_its_old_address(browser, site):
    """What is held or off is a goal: /goals is the page (h1 'Goals', first column 'goal'), /loops lands there with
    its query, the header never says 'loop', a goal's panel is a Goal; 'control loop' and 'Feedback loops' stay."""
    pg = browser.new_page()
    rows = "() => [...document.querySelectorAll('#main tr.click td:first-child b')].map((b) => b.textContent)"
    pg.goto(f"{site}/goals?status=off")
    pg.wait_for_function("() => document.querySelector('#main tr.click')", timeout=30000)
    assert pg.locator("#main h1").inner_text() == "Goals"
    assert pg.locator("#main th").first.inner_text() == "goal"
    nav = pg.locator("#nav").inner_text()
    assert "Goals" in nav and "Loops" not in nav, nav
    goals = pg.evaluate(rows)
    pg.goto(f"{site}/loops?status=off")
    pg.wait_for_function("() => location.pathname === '/goals' && document.querySelector('#main tr.click')", timeout=30000)
    assert pg.evaluate("location.search") == "?status=off" and pg.evaluate(rows) == goals
    pg.wait_for_function("() => document.querySelector('#running').textContent", timeout=10000)
    assert "loop" not in pg.locator("header").first.inner_text().lower()
    pg.locator("#main tr.click").first.click()
    pg.wait_for_function("() => document.querySelector('#detail .kind')", timeout=20000)
    assert pg.locator("#detail .kind").first.inner_text() in ("Goal", "Goal, open loop")
    pg.goto(f"{site}/diagram?view=blocks&open=*")
    pg.wait_for_function("() => S.graph?.nodes?.length && document.querySelector('.side h3')", timeout=60000)
    ctl = "S.graph.nodes.find((n) => n.role === 'controller' && (n.loops || []).length)"
    assert pg.evaluate(f"() => !!{ctl}"), pg.evaluate("() => S.graph.nodes.map((n) => [n.kind, n.role, n.loops])")
    pg.evaluate(f"() => openBlock({ctl})")
    pg.wait_for_function("() => document.querySelector('#detail .kind')", timeout=20000)
    assert "control loop" in pg.locator("#detail").inner_text()
    assert "Goals and their control loops" in pg.locator(".side").first.inner_text()
    pg.goto(f"{site}/diagram?view=dynamics&open=*")
    pg.wait_for_function("() => [...document.querySelectorAll('.side h3')].some((x) => x.textContent.startsWith('Feedback loops'))",
                         timeout=60000)
    pg.close()


def test_a_hidden_tab_asks_for_nothing(browser, site):
    pg = browser.new_page()
    pg.add_init_script(INIT)
    pg.goto(f"{site}/diagram")
    pg.wait_for_timeout(4000)
    pg.evaluate("""() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
                           document.dispatchEvent(new Event("visibilitychange")); }""")
    pg.wait_for_timeout(2000)                         # what was on its way arrives
    asked = []
    pg.on("request", lambda r: asked.append(r.url) if "/api/" in r.url else None)
    pg.wait_for_timeout(4000)
    hidden = len(asked)
    pg.evaluate("""() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
                           document.dispatchEvent(new Event("visibilitychange")); }""")
    pg.wait_for_timeout(2000)
    shown = len(asked) - hidden
    pg.close()
    assert hidden == 0, f"{hidden} requests while hidden"
    assert shown > 0, "it did not start again when shown"


CANON = """(x) => { const c = (v) => Array.isArray(v) ? v.map(c) : v && typeof v === "object"
                        ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, c(v[k])])) : v; return JSON.stringify(c(x)); }"""


@pytest.mark.parametrize("route", ["diagram", "diagram?view=dynamics", "diagram?view=dynamics&open=*", "diagram?view=blocks"])
def test_a_diagram_left_open_asks_for_its_values_and_has_the_whole_answer(browser, site, route):
    """Once drawn, a diagram asks for its graph with the structure it holds (``have``), and is sent only the values
    while that structure stands (docs/proposals/scale.md, #12); put into what it holds, they make the answer a whole
    one gives."""
    pg = browser.new_page()
    pg.add_init_script(INIT)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    got: list[tuple[str, dict]] = []
    pg.on("response", lambda r: got.append((r.url, r)) if "/api/graph" in r.url else None)
    pg.goto(f"{site}/{route}")
    pg.wait_for_function("() => S.layout && S.held && document.querySelectorAll('svg.canvas g.node').length > 0", timeout=60000)
    pg.wait_for_timeout(3000)                         # (sped up tenfold: a dozen asks)
    bodies = [(u, r.json()) for u, r in got if r.status == 200]
    whole = [b for u, b in bodies if "structure" in b]
    small = [(u, b) for u, b in bodies if "same" in b]
    assert whole and small, [(u[-80:], r.status) for u, r in got]      # (a 304: the same values again)
    assert all("have=" in u for u, _ in small)
    url, last = small[-1]
    full_url = "&".join(x for x in url.split("&") if not x.startswith("have="))
    same = pg.evaluate(f"""async () => {{ const canon = {CANON};
        const full = await (await fetch({full_url!r})).json();
        return [canon(withValues(S.held.base, {json_dumps(last)})), canon(full)]; }}""")
    sizes = (len(str(last)), len(str(whole[-1])))
    pg.close()
    assert not errors, errors
    assert same[0] == same[1], "the values put into the structure held are not the whole answer"
    assert sizes[0] < sizes[1]


def json_dumps(x) -> str:
    import json
    return json.dumps(x)


RELEASED = '''
import pytest
playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def test_a_page_test_that_fails_before_its_close(browser):
    pg = browser.new_page()
    browser.new_context().new_page().set_content("<p>left open</p>")
    pg.set_content("<p>left open</p>")
    assert False, "failed with its pages open"


def test_the_next_test_finds_nothing_left_open(browser):
    assert browser.contexts == [], browser.contexts
'''


def test_a_failing_page_test_releases_its_pages(tmp_path):
    """The conftest closes a page test's pages and contexts however it ends: a test that fails before its own
    ``pg.close()`` leaves nothing open in the module's browser (a run with many failures otherwise grows past the
    machine's memory)."""
    shutil.copy(Path(__file__).with_name("conftest.py"), tmp_path / "conftest.py")
    (tmp_path / "test_released.py").write_text(RELEASED)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "ERGOSTAT_SUITE"))}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist", str(tmp_path)],
                       cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert "1 failed, 1 passed" in r.stdout, r.stdout + r.stderr
    assert "FAILED test_released.py::test_a_page_test_that_fails_before_its_close" in r.stdout, r.stdout
