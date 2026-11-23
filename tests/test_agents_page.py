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
actions:
  push:
    run: "echo pushed"
    description: Push the page
"""

HISTORY = """
import random, time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
from ergostat.costs import record as cr
from ergostat.actions import record as ar
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
        if block == "writer":                         # its runs are each about a page: done, refused or failed
            data["item"] = f"page/{i}"
            if i == 58:                               # pool full: agent.ran with its note, given back (engine.py)
                data["note"] = ("no workspace free: every one of the pool's three workspaces is held by an "
                                "item under review, so this run was given back and put off until one is")
            if i == 57:
                data["note"] = "exited 2"
        begun = p.events.add("agent.started", item=block, source="ergostat", at=t - data["seconds"], data={})
        e = p.events.add("agent.failed" if i == 57 and block == "writer" else "agent.ran", item=block, source="ergostat",
                         causedby=begun["id"], at=t, data=data)
        if block == "writer":                         # its lease's end, as leases/dispatch.py writes it: 54 gave it back
            nack = {58: data.get("note"), 57: "exited 2", 54: "the page was rewritten by another run already"}.get(i)
            p.events.add("ergostat.lease.ended", item=data["item"], source="ergostat", causedby=begun["id"], at=t,
                         data={"run": begun["id"], "fence": 1, "exit": data["exit"], **({"how": "nack", "why": nack}
                                                                                       if nack else {"how": "ack"})})
        cr.write_series(p, block, data, t)
        if block == "writer" and i >= 55:             # the outward actions it asked for, as the gate records them
            aid = ar.new_id("push")
            ar.step(p, aid, "requested", {"action": "push", "class": "push", "gate": "owner", "args": {},
                                          "command": "git push", "item": data["item"], "run": begun["id"],
                                          **({"session": "session/w1"} if i == 56 else {"block": "writer"})},
                    by="writer", causedby=begun["id"])
            ar.step(p, aid, "approved", {"approved_by": "owner", "note": "offline stand-in"}, by="owner")
            p.events.add("page.edited", item=data["item"], source="writer", at=t, data={})
import json
(p.dir / "daemons.json").write_text(json.dumps({"at": now, "daemons": {"counter": {   # as the engine writes it (SPEC §9.7)
    "state": "running", "pid": 4242, "restarts": 2, "restarts_total": 3, "last_line": now - 4, "in_flight": 1,
    "concurrency": 10, "users": ["sensor.pages.main"], "cpu": 1.5, "memory": 21e6, "alarm": None, "run": "./count.py"}}}))
"""




LEASED = """
name: agents-leased
items:
  ticket:
    id: ticket/*
    states: [located, worked, stopped]
stocks:
  located:
    unit: tickets
    sensor: {items: ticket, state: located}
  worked:
    unit: tickets
    sensor: {items: ticket, state: worked}
flows:
  work:
    from: located
    to: worked
goals:
  located-worked:
    stock: located
    hold: "<= 0"
blocks:
  work:
    type: ai
    goal: located-worked
    prompt: "Do the ticket."
    run: ./work.sh
    takes: {kind: ticket, at: located, to: [worked, stopped]}
    out: flow.work
"""

LEASED_HISTORY = """
import time
from pathlib import Path
from ergostat import model as mdl
from ergostat.store import Project
p = Project(mdl.load(Path(DIR)))
now = time.time()
full = "workspace pool code has none free for ticket/1: 1 in use, 0 held for review, 0 quarantined (of 1)"
for i in range(28):                                   # nine worked, nineteen given back for want of a workspace
    data = {"exit": 0, "seconds": 2.0, "why": "lease", "item": f"ticket/{i}", **({} if i < 9 else {"note": full})}
    begun = p.events.add("agent.started", item="work", source="ergostat", at=now - 1200 + i * 30, data={})
    p.events.add("agent.ran", item="work", source="ergostat", causedby=begun["id"], at=now - 1198 + i * 30, data=data)
"""


def serve(tmp_path_factory, name: str, model: str, history: str):
    d = tmp_path_factory.mktemp("agents") / name
    d.mkdir()
    (d / "ergostat.yaml").write_text(textwrap.dedent(model))
    home = d.parent / "home"
    env = {**os.environ, "ERGOSTAT_HOME": str(home)}
    subprocess.run([sys.executable, "-c", history.replace("DIR", repr(str(d)))], env=env, check=True, capture_output=True)
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
def site(tmp_path_factory):
    yield from serve(tmp_path_factory, "agents-costs", MODEL, HISTORY)


@pytest.fixture(scope="module")
def leased(tmp_path_factory):
    yield from serve(tmp_path_factory, "agents-leased", LEASED, LEASED_HISTORY)


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
    runs = pg.eval_on_selector_all(".runs-table > table tr", "trs => trs.slice(1).map((tr) => tr.textContent)")
    assert len(runs) == 10 and all("$" in r for r in runs)
    used = pg.eval_on_selector_all("#detail table:has(th:text-is('tokens')) tr", "trs => trs.slice(1).map((tr) => tr.textContent)")
    assert len(used) == 10 and all("MB" in r for r in used)                 # behind its 'resources' disclosure
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
    if i < MADE:                                      # and in the other site its first runs each made a change
        p.events.add("ergostat.model-change.made", item=f"ergostat.model-change/fix-{i}", source="fixer", at=t + 1,
                     causedby=begun["id"], data={"kind": "unit", "title": f"unit {i}", "made_by": "fixer"})
p.measurements.add("sensor/unanswered-requests.main", 36, at=now - 2)   # its sensor read, by no agent of the model's
p.events.add("loop.off", item="requests-handled", source="ergostat", at=now - 2100, data={})   # off all the window
p.events.add("controller.decided", item="requests-handled", source="ergostat", at=now - 60, data={"decision": "on"})
for t in (now - 1800, now - 600, now - 5):            # requests came in at 2/h; the fixer's changes came at MADE/h
    p.measurements.add("sensor/requests-raised.main", 2, at=t)
    p.measurements.add("sensor/changes-made-by-fixer.main", MADE, at=t)
log_path(p, "fixer").write_text("--- 2026-11-22 10:00:00 run 0a1b2c3d (commanded)\\nno open request the rule tier answers\\n")
"""


@pytest.fixture(scope="module", params=[0, 3], ids=["moved-nothing", "made-changes"])
def requests_site(tmp_path_factory, request):
    """The modelling template's requests loop (as image-squeeze's): its goal closes the long way, through the judge.
    Its fixer made no change in one site, and 3 in the other (`request.param`)."""
    d = tmp_path_factory.mktemp("requests") / "requests"
    d.mkdir()
    (d / "ergostat.yaml").write_text("name: requests\nuses:\n  modelling:\n    use: modelling\n")
    env = {**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")}
    subprocess.run([sys.executable, "-c", REQUESTS.replace("DIR", repr(str(d))).replace("MADE", str(request.param))],
                   env=env, check=True, capture_output=True)
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
    yield url, request.param
    proc.terminate()
    proc.wait(10)


def test_the_evidence_says_in_one_line_whether_the_actor_was_commanded_ran_and_moved_anything(requests_site, browser):
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    url, made = requests_site
    pg.goto(f"{url}/agents")
    pg.wait_for_selector("tr.click:has(b:text-is('fixer'))")
    runs = pg.inner_text("tr.click:has(b:text-is('fixer')) td.num")
    assert runs == "34"
    keep = pg.inner_text("tr.click:has(b:text-is('keep-requests-handled'))")
    assert "controller requests-handled" in keep and "no roles" not in keep    # the implied rule fills its controller
    pg.goto(f"{url}/loops")
    pg.click("tr.click:has-text('requests-handled')")
    pg.wait_for_selector("#detail .actor-line")
    line = pg.inner_text("#detail .actor-line")
    moved = f"moved {made}" if made else "moved nothing"           # its changes, counted from the record
    assert line == f"fixer: commanded {runs} times, ran {runs}, {moved} (its log: no open request the rule tier answers)"
    pg.wait_for_selector("#detail .chart-val")                  # its scope drawn: the u chart's word is there too
    evidence = pg.inner_text("#detail")
    assert not ("never opened" in evidence and re.search(r"moves\s+requests-answered", evidence, re.I))
    moves = pg.locator("#detail dl", has_text="cycled").inner_text()   # the loop's own rows
    assert "requests-answered" not in moves and "changes-made-by-fixer" in moves   # what its own valve moves
    hint = pg.inner_text("#detail p:has(b:text-is('Suggestion:'))")
    if made:                                                     # 3/h made against 2/h raised: it keeps up
        assert "keeps up on average" in hint and "moves nothing" not in hint
    else:                                                        # it ran 34 times and moved nothing
        assert "acts but moves nothing" in hint and "per run" not in hint.lower()
    sensor = pg.inner_text("#detail table.parts tr:has(td:text-is('sensor'))")
    assert ": 36" in sensor and "unfilled" not in sensor            # a sensor that reads is not unfilled
    assert not errors, errors
    pg.close()


@pytest.mark.slow
def test_the_agents_table_holds_still_while_the_pointer_is_on_a_row(site, browser):
    """Each answer of /api/agents comes in the other order (as rows re-sort when runs end): hovering a row for 20 s
    leaves the order as it was, the table saying what waits; off the table, the newer order is drawn."""
    import json
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    n = [0]

    def turned(route):
        resp = route.fetch()
        body = resp.json()
        n[0] += 1
        route.fulfill(response=resp, body=json.dumps(dict(reversed(list(body.items()))) if n[0] % 2 else body))
    pg.route("**/api/agents?*", turned)
    pg.goto(f"{site['url']}/agents")
    pg.wait_for_selector("tr[data-row=reviewer]")
    order = "() => [...document.querySelectorAll('tr[data-row]')].map((tr) => tr.dataset.row).join(' ')"
    pg.hover("tr[data-row=reviewer] td:nth-child(3)")
    was, seen = pg.evaluate(order), n[0]
    for _ in range(20):
        pg.wait_for_timeout(1000)
        assert pg.evaluate(order) == was
    assert n[0] >= seen + 4, n                                   # (the answers kept coming, in turns)
    # what waits is said once an answer in the other order is the last built (every other one): not at a fixed moment
    pg.wait_for_function("() => document.querySelector('.waiting')?.textContent.includes('updates waiting')", timeout=10000)
    assert pg.evaluate(order) == was
    pg.mouse.move(700, 20)                                       # off the table: the newest drawn
    pg.wait_for_function(f"() => ({order})() !== {json.dumps(was)}", timeout=20000)
    assert not errors, errors
    pg.close()


def test_an_agents_recent_runs_name_the_item_the_outcome_and_the_actions_asked_and_fit_the_panel(site, browser):
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{site['url']}/agents")
    pg.click("tr.click:has(b:text-is('writer'))")
    pg.wait_for_selector(".runs-table td a[href^='/item/']")
    rows = pg.eval_on_selector_all(".runs-table > table tr", """trs => trs.slice(1).map((tr) => ({
        item: tr.cells[1].querySelector("a")?.getAttribute("href"), outcome: tr.cells[2].textContent,
        asked: [...tr.cells[3].querySelectorAll("a")].map((a) => a.getAttribute("href"))}))""")
    assert len(rows) == 10 and all((r["item"] or "").startswith("/item/page") for r in rows)
    words = [r["outcome"].split(":")[0] for r in rows]                         # newest first: 59 .. 50
    assert words == ["done", "refused", "failed", "done", "done", "refused", "done", "done", "done", "done"], words
    assert "no workspace free" in rows[1]["outcome"] and "exited 2" in rows[2]["outcome"]
    assert "rewritten by another run" in rows[5]["outcome"]                    # exit 0, but its item given back
    assert [len(r["asked"]) for r in rows] == [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]  # the runs that asked for a push
    assert all(h.startswith("/item/ergostat.action") for r in rows for h in r["asked"])
    edge = pg.evaluate("""() => [document.querySelector('.runs-table > table').getBoundingClientRect().right,
                                document.querySelector('#detail').getBoundingClientRect().right]""")
    assert edge[0] <= edge[1] + 0.5, edge                                     # not clipped by the panel
    assert not pg.is_visible("#detail th:text-is('CPU')")                     # behind 'resources' until opened
    pg.click("details.runs-resources summary")
    assert pg.is_visible("#detail th:text-is('CPU')")
    pg.goto(f"{site['url']}/items?kind=ergostat.action")
    pg.wait_for_selector("table.items tr.click, table tr.click")
    heads = pg.eval_on_selector_all("table:has(th button[title='Sort by author']) th", "ths => ths.map((t) => t.textContent.trim())")
    by, ok = heads.index("by"), heads.index("approved by")
    cells = pg.eval_on_selector_all("table:has(th button[title='Sort by author']) tr.click",
                                    f"trs => trs.map((tr) => [tr.cells[{by}].textContent, tr.cells[{ok}].textContent])")
    assert len(cells) == 5 and all(c[0] not in ("", "–") for c in cells), cells
    assert sorted(c[0] for c in cells) == ["session/w1"] + ["writer"] * 4
    assert all(c[1] == "owner (offline stand-in)" for c in cells), cells
    pg.goto(f"{site['url']}/item/{'page%2F59'}")                              # the item's own 'Gated actions'
    pg.wait_for_selector("h2:has-text('Gated actions')")
    assert "asked by writer, approved by owner (offline stand-in)" in pg.inner_text("body")
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
    assert "SPEC §" not in pg.inner_text(".page")            # what a daemon is, said; not where SPEC says it
    assert not errors, errors
    pg.close()


def test_each_row_says_how_it_is_engaged_and_which_goal_it_serves(site, leased, browser):
    """Design review Q38: no 'runs when' cell is blank; a leased block reads 'on demand, per item (leased)', its role
    names the goal it serves, and its panel tallies the runs given back for a full workspace pool apart from those done."""
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    for s in (site, leased):
        pg.goto(f"{s['url']}/agents")
        pg.wait_for_selector("tr.click")
        when = pg.eval_on_selector_all("tr.click", "trs => trs.map((tr) => tr.children[4].textContent.trim())")
        assert when and all(when), when
    row = pg.inner_text("tr.click:has(b:text-is('work'))")
    assert "on demand, per item (leased)" in row and "valve work → goal located-worked" in row, row
    pg.click("tr.click:has(b:text-is('work'))")
    pg.wait_for_selector("#detail h2:text-is('work')")
    panel = pg.inner_text("#detail")
    assert "not run by ergostat" not in panel
    assert "started per item by its lease, not on a schedule" in panel
    assert "28 runs: 9 done, 19 refused (workspace pool full), 0 failed" in panel, panel
    assert not errors, errors
    pg.close()
