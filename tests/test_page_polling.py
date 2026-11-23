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

try:                           # collected without it too, each test skipped, so a run of this file alone is rc 0, not 5
    from playwright import sync_api as playwright
except ImportError:
    playwright = None
pytestmark = pytest.mark.skipif(playwright is None, reason="needs Playwright: uv run --with playwright==1.63.0")

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = "image-squeeze"
SPEED = 10                     # every poll's wait shortened this much
OPEN_S = float(os.environ.get("POLL_OPEN_S", 40))    # how long each page is left open (x SPEED of refreshes)
HEAP_GROWTH_MB = 3.0           # retained heap (after a collection), from settled to the end
NODE_GROWTH = 0.10             # DOM nodes, as a share of where they settled (and 200 more)
LONG_TASK_P95_MS = 500         # each refresh's longest work on the main thread, on a laptop; generous
SETTLE_S = 120                 # the most a page may take to settle (drawn, routed, charts mounted), however loaded
SCALE_N = int(os.environ.get("POLL_SCALE_N", 20))    # the large model's workflows (scripts/scale_model.py)
REFRESHES = 30                 # the Dynamics page with every system open, watched over this many refreshes
# the CPU slowed this many times (CDP), so refreshes run slow and the router's lines late. (At 4x a whole relayout of
# scale_model 20 stalls the refreshes for many minutes: 31 refreshes in 1440 s; at 2x, 120 s and 566 s a relayout.)
THROTTLE = 2
# A fixed piece of work, timed in the page: how much slower this machine is now than the laptop the bounds were set
# on (REF_MS there, unloaded). The long-task bound scales by it, never below 1, so a loaded machine is held to the
# same work, not to the same milliseconds.
REF_MS = 8.5                   # measured 8.2 to 8.8 ms on the reference laptop (2026-11-18)
SPEED_PROBE = """() => { const t0 = performance.now(); let x = 0;
  for (let i = 0; i < 2e6; i++) x = (x * 31 + i) % 1000003;
  return [performance.now() - t0, x]; }"""
PAGES = ["diagram", "diagram?view=dynamics&open=*", "diagram?view=blocks", "diagram?view=process", "loops",
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
    yield from serve(d, home)


@pytest.fixture(scope="module")
def large_site(tmp_path_factory):
    """scripts/scale_model.py's model of SCALE_N workflows, in systems sharing pools and loops across them."""
    d = tmp_path_factory.mktemp("scale") / "scale"
    subprocess.run([sys.executable, str(ROOT / "scripts/scale_model.py"), str(SCALE_N), str(d)], check=True, capture_output=True)
    yield from serve(d, d.parent / "home")


def serve(d: Path, home: Path):
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


def quiet_metrics(pg, cdp, within: float = SETTLE_S) -> dict:
    """The page's metrics with the drawings it has let go swept: reads after a collection, 300 ms apart, until two in a
    row have the same DOM nodes and listeners. A drawing is built and swapped in one task (diagram.js drawGraph), so
    a read never lands mid-draw; but Chrome sweeps after it collects, so a read right after the collection can still
    count part of the drawing a refresh let go (measured on the Dynamics page, all open, scale_model 20, CPU x4:
    +315 nodes and +901 listeners, gone 300 ms later; never more than that, and never growth, over 30 refreshes).
    Past ``within``, the least read: garbage only adds to a count, so the least is still all that is alive, and
    growth that never stops still meets the bound."""
    deadline, reads = time.monotonic() + within, []
    while True:
        m = metrics(cdp)
        now = (m["Nodes"], m["JSEventListeners"])
        if reads and now == (reads[-1]["Nodes"], reads[-1]["JSEventListeners"]):
            return m
        reads.append(m)
        if time.monotonic() > deadline:
            return min(reads, key=lambda r: (r["Nodes"], r["JSEventListeners"]))
        pg.wait_for_timeout(300)


def settle(pg, cdp, least: float = 8.0) -> dict:
    """The page's metrics once it has settled: at least ``least`` seconds after it opened, and then its DOM nodes and
    retained heap the same over three looks a second apart (heap within a tenth of a MB), each a quiet read (the
    drawings let go swept), however long that takes on a loaded machine, up to SETTLE_S."""
    pg.wait_for_timeout(least * 1000)
    deadline, last, same = time.monotonic() + SETTLE_S, None, 0
    while True:
        m = quiet_metrics(pg, cdp, 10)
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
    end = quiet_metrics(pg, cdp)                      # (not mid-render: the refresh drawing then has finished)
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


# a refresh run beside the one the poll is running: the whole layout again (as a pin does), started while the poll's
# own refresh is on its way, so two refreshes draw over each other
OVERLAP = """() => new Promise((ok) => { const go = () => { if (S.timer && S.timer.running) { S.relayout(); ok(true); }
                                                    else setTimeout(go, 10); }; go(); })"""


def watch_dynamics_open(browser, site, throttle: int = 0, overlaps: int = 0) -> None:
    """The Dynamics page with every system open on the large model: its DOM nodes and listeners read (quiet: what it
    let go swept) after each five refreshes, REFRESHES in all, each within the bound of where it settled; with the
    CPU throttled after it settled, and ``overlaps`` refreshes started beside the poll's own, one a round."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.add_init_script(INIT)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    graphs: list[int] = []
    pg.on("response", lambda r: graphs.append(r.status) if "/api/graph" in r.url else None)
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Performance.enable")
    pg.goto(f"{site}/diagram?view=dynamics&open=*")
    pg.wait_for_function("() => S.layout && document.querySelectorAll('svg.canvas g.node').length > 0", timeout=SETTLE_S * 1000)
    settled = settle(pg, cdp)
    if throttle:
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
    n0, reads, fired, rounds, took = len(graphs), [], 0, REFRESHES // 5, []
    within = 3 * SETTLE_S * max(1, throttle)          # (a ceiling: throttled, a refresh of this model takes seconds)
    t0 = time.monotonic()
    def said() -> str:
        row = lambda xs: " ".join(f"{x:.0f}" for x in xs)   # noqa: E731
        return (f"dynamics open, {SCALE_N} workflows, cpu x{throttle or 1}, {fired} overlapping, {len(graphs) - n0} "
                f"refreshes, rounds of {row(took)} s: nodes {settled['Nodes']:.0f}→{row(m['Nodes'] for m in reads)}, "
                f"listeners {settled['JSEventListeners']:.0f}→{row(m['JSEventListeners'] for m in reads)}")
    for i in range(rounds):                           # each round five refreshes or more, then a read
        start, ts = len(graphs), time.monotonic()
        if fired < overlaps and i % max(1, rounds // overlaps) == rounds // overlaps // 2:
            fired += pg.evaluate(OVERLAP)
        while len(graphs) - start < 5:
            if time.monotonic() > t0 + within:
                pytest.fail(f"the page stopped refreshing ({within} s): {said()}")
            pg.wait_for_timeout(250)
        reads.append(quiet_metrics(pg, cdp))
        took.append(time.monotonic() - ts)
    ctx.close()
    print("\n" + said())
    assert not errors, errors
    assert fired == overlaps
    assert len(graphs) - n0 >= REFRESHES and len(reads) == rounds
    for i, m in enumerate(reads):
        nodes = m["Nodes"] - settled["Nodes"]
        assert nodes < NODE_GROWTH * settled["Nodes"] + 200, f"DOM nodes grew by {nodes:.0f} (read {i + 1} of {len(reads)})"
        assert m["JSEventListeners"] < settled["JSEventListeners"] * (1 + NODE_GROWTH) + 50, f"listeners pile up (read {i + 1})"


@pytest.mark.slow
def test_dynamics_open_stays_bounded_over_30_refreshes(browser, large_site):
    watch_dynamics_open(browser, large_site)


@pytest.mark.slow
def test_dynamics_open_stays_bounded_when_refreshes_overlap(browser, large_site):
    """Under the CPU throttled THROTTLE times (refreshes slow, the router's lines late, however busy the machine is
    besides), with a whole relayout started while the poll's refresh is on its way."""
    watch_dynamics_open(browser, large_site, throttle=THROTTLE, overlaps=1)


def test_leaving_a_page_stops_its_polling(browser, site):
    """Pages left quickly, each before its first answer came: only the header's and the last page's polls go on."""
    pg = browser.new_page()
    pg.add_init_script(INIT)
    pg.goto(f"{site}/loops")
    pg.wait_for_timeout(3000)
    for r in ["/diagram", "/items", "/loops", "/diagram?view=blocks", "/agents", "/model", "/diagram"] * 2 + ["/record"]:
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


FETCHES = """window.__fetches = []; const realFetch = window.fetch;
window.fetch = (url, opts = {}) => { const f = { url: String(url), signal: opts.signal || null, failed: null };
  window.__fetches.push(f);
  return realFetch(url, opts).catch((e) => { f.failed = e.name; throw e; }); };"""


def test_leaving_a_page_cancels_its_fetches_in_flight(browser, site):
    """The Loops page's answer held on its way; the page left for Agents: that fetch is aborted (the server can
    drop it), the left page says nothing of it, and the header's and the new page's fetches are not aborted."""
    pg = browser.new_page()
    pg.add_init_script(FETCHES)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    held = []
    pg.route("**/api/loops?*", lambda r: held.append(r))          # never answered while held
    pg.goto(f"{site}/loops")
    pg.wait_for_function("window.__fetches.some((f) => f.url.includes('/api/loops'))", timeout=60000)
    pg.wait_for_function("window.__fetches.some((f) => f.url.includes('/api/status'))", timeout=60000)
    pg.evaluate("navigate('/agents')")
    pg.wait_for_function("window.__fetches.some((f) => f.url.includes('/api/agents'))", timeout=60000)
    pg.wait_for_timeout(1000)
    got = pg.evaluate("""window.__fetches.map((f) => ({ url: f.url.split('/api/')[1].split('?')[0],
                                                          aborted: !!(f.signal && f.signal.aborted), failed: f.failed }))""")
    pg.unroute("**/api/loops?*")
    pg.close()
    loops = [f for f in got if f["url"] == "loops"]
    assert loops and all(f["aborted"] and f["failed"] == "AbortError" for f in loops), got
    assert not any(f["aborted"] for f in got if f["url"] in ("status", "projects", "agents")), got
    assert not errors, errors


def test_the_loops_page_asks_once_for_every_goal(browser, site):
    """Opening Loops sends at most four API requests (status, loops, projects and one more), none of them the graph
    and none per goal; its performance column fills within a few polls, each goal's as loop-control says."""
    pg = browser.new_page()
    asked: list[str] = []
    pg.on("request", lambda r: asked.append(r.url.split("/api/")[1]) if "/api/" in r.url else None)
    pg.goto(f"{site}/loops")
    pg.wait_for_selector("td[data-perf]", timeout=30000)
    pg.wait_for_timeout(1500)                            # the first tick's answers all asked (the next poll is at 3 s)
    opening = list(asked)
    goals = pg.evaluate("() => [...document.querySelectorAll('td[data-perf]')].map((c) => c.dataset.perf)")
    deadline = time.monotonic() + 60
    while pg.evaluate("() => document.body.innerText.includes('being worked out')"):
        assert time.monotonic() < deadline, "the performance column never filled"
        pg.wait_for_timeout(500)
    cells = pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('td[data-perf]')]"
                        ".map((c) => [c.dataset.perf, c.textContent]))")
    later = asked[len(opening):]
    each = pg.evaluate("async (gs) => Object.fromEntries(await Promise.all(gs.map(async (g) => "
                       "[g, performanceWord(await api('loop-control', { goal: g }))])))", goals)
    pg.close()
    names = [a.split("?")[0] for a in opening]
    assert len(opening) <= 4 and "graph" not in names and "loop-control" not in names, opening
    assert {"status", "loops"} <= set(names), opening
    assert not [a for a in later if a.startswith(("graph", "loop-control"))], later
    assert len(goals) >= 3 and cells == each, (cells, each)


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
