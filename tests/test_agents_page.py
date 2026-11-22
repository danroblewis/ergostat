"""Acceptance: the Agents page shows what each agent's runs cost over the window (dollars, tokens, CPU, peak memory),
marks an estimated cost, and an agent's panel draws its history (dollars by hour, tokens, CPU and memory run by run)
with uPlot, and lists its runs with their numbers (SPEC §9.1).

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_agents_page.py -v -s

With ``RUNCOST_SHOTS=DIR`` it leaves screenshots of the page and the panel there."""

from __future__ import annotations

import os
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


def test_each_group_heading_counts_its_rows_as_the_summary_does(site, browser):
    """A group's heading says its kind and how many agents are under it ('ai · 2'), the rung only as small text, and
    that number is the summary line's for the same kind."""
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site['url']}/agents")
    pg.wait_for_selector("tbody.group th[data-kind]")
    groups = pg.evaluate("""() => [...document.querySelectorAll('tbody.group')].map((tb) => {
        const th = tb.querySelector('th[data-kind]');
        return [th.dataset.kind, th.textContent, th.querySelector('.count').textContent, tb.querySelectorAll('tr.click').length,
                th.querySelector('small').textContent]; })""")
    summary = dict(pg.evaluate("""() => [...document.querySelectorAll('.ladder-line .step')].map((s) =>
        [s.dataset.kind, s.textContent.trim().split(' ')[0]])"""))
    kinds = [g[0] for g in groups]
    assert "ai" in kinds and "program" in kinds, groups              # the model's two AI blocks and its program
    for kind, text, count, rows, small in groups:
        assert text.startswith(f"{kind} · {rows}"), (kind, text)    # the kind first, then its count
        assert int(count) == rows == int(summary[kind]), (kind, count, rows, summary)
        assert small.strip().startswith("rung "), small              # the rung, said as a rung
    assert {g[0]: g[3] for g in groups}["ai"] == 2                  # writer and reviewer
    line = pg.inner_text(".ladder-line")
    assert line.count("→") == 1 and "most general → most specific" in line
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
