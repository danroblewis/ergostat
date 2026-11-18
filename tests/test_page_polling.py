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
        pytest.fail("the page never answered")
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
    pg.wait_for_timeout(8000)                         # drawn, its lines routed, its charts mounted
    settled = metrics(cdp)
    lt0 = pg.evaluate("window.__lt.length")
    n0 = len(asked)
    pg.wait_for_timeout(OPEN_S * 1000)
    end = metrics(cdp)
    lts = pg.evaluate(f"window.__lt.slice({lt0})")
    ctx.close()
    heap = (end["JSHeapUsedSize"] - settled["JSHeapUsedSize"]) / 1e6
    nodes = end["Nodes"] - settled["Nodes"]
    p95 = sorted(lts)[int(0.95 * len(lts))] if lts else 0
    print(f"\n{route}: heap {settled['JSHeapUsedSize'] / 1e6:.1f}→{end['JSHeapUsedSize'] / 1e6:.1f} MB, nodes "
          f"{settled['Nodes']:.0f}→{end['Nodes']:.0f}, listeners {settled['JSEventListeners']:.0f}→{end['JSEventListeners']:.0f}, "
          f"{len(lts)} long tasks (p95 {p95:.0f} ms), {len(asked) - n0} requests")
    assert not errors, errors
    assert len(asked) - n0 > 5, "the page stopped refreshing"
    assert heap < HEAP_GROWTH_MB, f"retained heap grew {heap:.1f} MB"
    assert nodes < NODE_GROWTH * settled["Nodes"] + 200, f"DOM nodes grew by {nodes:.0f}"
    assert end["JSEventListeners"] < settled["JSEventListeners"] * (1 + NODE_GROWTH) + 50, "listeners pile up"
    assert p95 < LONG_TASK_P95_MS, f"refreshes hold the page {p95:.0f} ms (p95)"


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
