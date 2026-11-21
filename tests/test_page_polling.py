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
THROTTLE = 4                   # the CPU slowed this many times (CDP), so refreshes run slow and the router's lines late
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


# between refreshes: no poll running (util.js), no lines being routed for the drawing (avoid.js); and the count of
# drawings made (diagram.js), so a read a drawing slipped into is seen
BETWEEN = """() => [[...POLLS].every((p) => !p.running) && !(S.layout && S.layout.routing), S.drawN ?? null]"""


def idle_metrics(pg, cdp, deadline: float) -> dict:
    """The page's metrics read between two refreshes: idle before the collection, and no drawing made between that
    look and the read (a refresh that drew meanwhile has its old drawing still on the heap: that read is taken
    again). Past ``deadline`` with no such read, the test fails: an unreadable metric never passes it."""
    while True:
        before = pg.evaluate(BETWEEN)
        if before[0]:
            m = metrics(cdp)
            if pg.evaluate(BETWEEN) == before:
                return m
        if time.monotonic() > deadline:
            pytest.fail("no read of the page between its refreshes before the deadline")
        pg.wait_for_timeout(50)


def quiet_metrics(pg, cdp) -> dict:
    """The page's metrics once the render in progress has finished and its leftovers are collected: two reads between
    refreshes with the same DOM nodes and listeners. Past SETTLE_S, the last read, however high: growth that never
    stops is growth, and the bound judges it."""
    deadline, last = time.monotonic() + SETTLE_S, None
    while True:
        m = idle_metrics(pg, cdp, deadline)
        now = (m["Nodes"], m["JSEventListeners"])
        if now == last or time.monotonic() > deadline:
            return m
        last = now
        pg.wait_for_timeout(300)


def settle(pg, cdp, least: float = 8.0) -> dict:
    """The page's metrics once it has settled: at least ``least`` seconds after it opened, and then its DOM nodes and
    retained heap the same over three looks a second apart (heap within a tenth of a MB), each read between two
    refreshes, however long that takes on a loaded machine, up to SETTLE_S."""
    pg.wait_for_timeout(least * 1000)
    deadline, last, same = time.monotonic() + SETTLE_S, None, 0
    while True:
        m = idle_metrics(pg, cdp, deadline + SETTLE_S)
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
    """The Dynamics page with every system open on the large model: its DOM nodes and listeners read (between
    refreshes, its leftovers collected) every five refreshes over REFRESHES, each within the bound of where it
    settled; with the CPU throttled after it settled, and ``overlaps`` refreshes started beside the poll's own."""
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
    n0, reads, fired = len(graphs), [], 0
    deadline = time.monotonic() + 3 * SETTLE_S
    while len(graphs) - n0 < REFRESHES:
        if time.monotonic() > deadline:
            pytest.fail(f"{len(graphs) - n0} refreshes of {REFRESHES} in {3 * SETTLE_S} s: the page stopped refreshing")
        if fired < overlaps and len(graphs) - n0 >= (fired + 1) * REFRESHES // (overlaps + 1):
            fired += pg.evaluate(OVERLAP)
        pg.wait_for_timeout(250)
        if (len(graphs) - n0) // 5 > len(reads):
            reads.append(quiet_metrics(pg, cdp))
    reads.append(quiet_metrics(pg, cdp))
    ctx.close()
    said = {k: " ".join(f"{m[k]:.0f}" for m in reads) for k in ("Nodes", "JSEventListeners")}
    print(f"\ndynamics open, {SCALE_N} workflows, cpu x{throttle or 1}, {fired} overlapping, {len(graphs) - n0} refreshes: "
          f"nodes {settled['Nodes']:.0f}→{said['Nodes']}, listeners {settled['JSEventListeners']:.0f}→{said['JSEventListeners']}")
    assert not errors, errors
    assert fired == overlaps
    assert len(reads) > REFRESHES // 5
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
    besides), with three whole relayouts started while the poll's refresh is on its way."""
    watch_dynamics_open(browser, large_site, throttle=THROTTLE, overlaps=3)


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
