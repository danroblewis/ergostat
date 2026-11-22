"""Acceptance: the Agents page shows what each agent's runs cost over the window (dollars, tokens, CPU, peak memory),
marks an estimated cost, and an agent's panel draws its history (dollars by hour, tokens, CPU and memory run by run)
with uPlot, and lists its runs with their numbers (SPEC §9.1).

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_agents_page.py -v -s

With ``RUNCOST_SHOTS=DIR`` it leaves screenshots of the page and the panel there."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

import pytest

from tests.ports import free_port

playwright = pytest.importorskip("playwright.sync_api")

MODEL = """
name: agents-costs
stocks:
  pages:
    unit: pages
    sensor: {daemon: counter}
daemons:
  counter: {run: ./count.py}
flows:
  written:
    from: pages
  checked:
    from: pages
  tidied:
    from: pages
blocks:
  writer:
    type: ai
    prompt: "Rewrite one stale page."
    run: $ERGOSTAT_CMD session writer --model sonnet
    out: flow.written
  reviewer:
    type: ai
    prompt: "Review it."
    model: haiku
    out: flow.checked
  tidy:
    type: program
    run: ./tidy.sh
    out: flow.tidied
"""

HISTORY = """
import random, time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
from ergostat.costs import record as cr
p = Project(mdl.load(Path(DIR)))
random.seed(7)
now = time.time()
for i in range(60):                                   # the last twenty hours, a run every twenty minutes each
    t = now - 72000 + i * 1200
    for block, model, usd, how in (("writer", "claude-sonnet-5-5", 0.05 + 0.04 * random.random(), "reported"),
                                   ("reviewer", "claude-haiku-5-5", 0.002 + 0.002 * random.random(), "estimated"),
                                   ("tidy", None, None, None)):
        data = {"exit": 0, "seconds": round(20 + 40 * random.random(), 1), "why": "schedule",
                "resources": {"cpu": round((9 if model else 0.4) * random.random() + 0.1, 3),
                              "memory_peak": int((300e6 if model else 40e6) * (1 + random.random())), "samples": 5,
                              "method": "wait4+sampled"}}
        if model:
            toks = int(30000 + 40000 * random.random())
            data["ai"] = {"cost_usd": round(usd, 5), "cost": how, "tokens": {"total": toks}, "model": model}
        begun = p.events.add("agent.started", item=block, source="ergostat", at=t - data["seconds"], data={})
        e = p.events.add("agent.ran", item=block, source="ergostat", causedby=begun["id"], at=t, data=data)
        cr.write_series(p, block, data, t)
import json
(p.dir / "daemons.json").write_text(json.dumps({"at": now, "daemons": {"counter": {   # as the engine writes it (SPEC §9.7)
    "state": "running", "pid": 4242, "restarts": 2, "restarts_total": 3, "last_line": now - 4, "in_flight": 1,
    "concurrency": 10, "users": ["sensor.pages.main"], "cpu": 1.5, "memory": 21e6, "alarm": None, "run": "./count.py"}}}))
"""




@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("agents") / "agents-costs"
    d.mkdir()
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    home = d.parent / "home"
    env = {**os.environ, "ERGOSTAT_HOME": str(home)}
    subprocess.run([sys.executable, "-c", HISTORY.replace("DIR", repr(str(d)))], env=env, check=True, capture_output=True)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
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
        pytest.fail("the page never answered")
    yield {"url": url, "dir": d}
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


def shot(pg, name: str) -> None:
    out = os.environ.get("RUNCOST_SHOTS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(Path(out) / name), full_page=True)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_agents_page_shows_costs_and_an_agents_panel_draws_their_history(site, browser, theme):
    pg = browser.new_page(viewport={"width": 1400, "height": 900}, color_scheme=theme)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site['url']}/agents")
    pg.wait_for_selector("td[data-use=cost]")
    pg.click("text=Last 1h")                                # the window: the last day, as a reader picks it
    pg.click("text=Last day")
    pg.wait_for_function("() => [...document.querySelectorAll('td[data-use=cost]')].some((td) => td.textContent.startsWith('$'))")
    pg.wait_for_timeout(3500)                                # (the window's words follow the header's next look)
    rows = {r[0]: r[1:] for r in pg.evaluate("""() => [...document.querySelectorAll('tr.click')].map((tr) =>
        [tr.querySelector('b').textContent,
         ...['cost', 'tokens', 'cpu', 'memory'].map((k) => tr.querySelector(`td[data-use=${k}]`).textContent)])""")}
    assert rows["writer"][0].startswith("$") and "est." not in rows["writer"][0]
    assert rows["reviewer"][0].startswith("$") and rows["reviewer"][0].endswith("est.")   # priced from tokens
    assert rows["tidy"][0] == "–" and rows["tidy"][1] == "–"                     # a program: no AI
    assert rows["tidy"][2].endswith("s") and rows["tidy"][3].endswith("MB")                # but its CPU and memory
    assert rows["writer"][1].endswith("M") or rows["writer"][1].endswith("k")
    assert "What the runs cost" in pg.inner_text(".page .note")
    shot(pg, f"agents-page-{theme}.png")
    pg.click("tr.click:has(b:text-is('writer'))")
    pg.wait_for_selector(".use-charts .chart canvas")
    pg.wait_for_timeout(800)
    names = pg.eval_on_selector_all(".use-charts .chart-name", "els => els.map((e) => e.textContent)")
    assert names == ["cost", "tokens", "CPU", "peak memory"]
    assert pg.eval_on_selector_all(".use-charts canvas", "els => els.filter((c) => c.width > 100 && c.height > 20).length") == 4
    assert "per hour" in pg.inner_text(".use-charts .chart:first-of-type .chart-head")
    totals = pg.inner_text(".use-totals")
    assert "60 runs" in totals and "$" in totals and "tokens" in totals and "CPU" in totals
    runs = pg.eval_on_selector_all("#detail table:has(th:text-is('tokens')) tr", "trs => trs.slice(1).map((tr) => tr.innerText)")
    assert len(runs) == 10 and all("$" in r and "MB" in r for r in runs)
    # the cursor on one chart moves them all, and each says its value there
    box = pg.locator(".use-charts .chart-plot").first.bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] / 2)
    pg.wait_for_timeout(200)
    vals = pg.eval_on_selector_all(".use-charts .chart-val", "els => els.map((e) => e.textContent)")
    assert "in the hour from" in vals[0] and all(" at " in v for v in vals[1:])
    shot(pg, f"agent-panel-{theme}.png")
    pg.eval_on_selector("#detail table:has(th:text-is('tokens'))", "el => el.scrollIntoView({ block: 'end' })")
    shot(pg, f"agent-panel-runs-{theme}.png")
    assert not errors, errors
    pg.close()


REQUESTS = """
import time
from pathlib import Path
from ergostat import model as mdl
from ergostat.runner import log_path
from ergostat.store import Project
p = Project(mdl.load(Path(DIR)))
now = time.time()
for i in range(34):                                   # the rule tier commanded every minute, each run moving nothing
    t = now - 2100 + i * 60
    begun = p.events.add("agent.started", item="fixer", source="ergostat", at=t, data={})
    p.events.add("block.commanded", item="fixer", source="ergostat", causedby=begun["id"], at=t,
                 data={"amount": 1, "from": "keep-requests-handled"})
    p.events.add("agent.ran", item="fixer", source="ergostat", causedby=begun["id"], at=t + 1,
                 data={"exit": 0, "seconds": 1, "why": "commanded", "commanded": 1})
p.measurements.add("sensor/unanswered-requests.main", 36, at=now - 2)   # its sensor read, by no agent of the model's
log_path(p, "fixer").write_text("--- 2026-11-22 10:00:00 run 0a1b2c3d (commanded)\\nno open request the rule tier answers\\n")
"""


@pytest.fixture(scope="module")
def requests_site(tmp_path_factory):
    """The modelling template's requests loop (as image-squeeze's): its goal closes the long way, through the judge."""
    d = tmp_path_factory.mktemp("requests") / "requests"
    d.mkdir()
    (d / "ergostat.yaml").write_text("name: requests\nuses:\n  modelling:\n    use: modelling\n")
    env = {**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")}
    subprocess.run([sys.executable, "-c", REQUESTS.replace("DIR", repr(str(d)))], env=env, check=True, capture_output=True)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)], env=env,
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
        pytest.fail("the page never answered")
    yield url
    proc.terminate()
    proc.wait(10)


def test_the_evidence_says_in_one_line_whether_the_actor_was_commanded_ran_and_moved_anything(requests_site, browser):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{requests_site}/agents")
    pg.wait_for_selector("tr.click:has(b:text-is('fixer'))")
    runs = pg.inner_text("tr.click:has(b:text-is('fixer')) td.num")
    assert runs == "34"
    keep = pg.inner_text("tr.click:has(b:text-is('keep-requests-handled'))")
    assert "controller requests-handled" in keep and "no roles" not in keep    # the implied rule fills its controller
    pg.goto(f"{requests_site}/loops")
    pg.click("tr.click:has-text('requests-handled')")
    pg.wait_for_selector("#detail .actor-line")
    line = pg.inner_text("#detail .actor-line")
    assert line == f"fixer: commanded {runs} times, ran {runs}, moved nothing (its log: no open request the rule tier answers)"
    pg.wait_for_selector("#detail .chart-val")                  # its scope drawn: the u chart's word is there too
    evidence = pg.inner_text("#detail")
    assert not ("never opened" in evidence and re.search(r"moves\s+requests-answered", evidence, re.I))
    assert "requests-answered" not in pg.inner_text("#detail dl")   # its own valve moves none of what answers it
    sensor = pg.inner_text("#detail table.parts tr:has(td:text-is('sensor'))")
    assert ": 36" in sensor and "unfilled" not in sensor            # a sensor that reads is not unfilled
    assert not errors, errors
    pg.close()


def test_the_agents_page_lists_the_daemons(site, browser):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site['url']}/agents")
    pg.wait_for_selector("tr[data-daemon=counter]")
    row = pg.inner_text("tr[data-daemon=counter]")
    assert "running" in row and "sensor.pages.main" in row and "2" in row and "1 of 10" in row
    assert "1.5s" in row and "21 MB" in row and "ago" in row
    assert "wall time only" in pg.inner_text(".page")
    assert not errors, errors
    pg.close()
