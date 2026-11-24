"""Acceptance (merge-run-stages-with-times, done 4): the default dashboard of a project whose batch kind declares a
``pipeline:`` has its "Merge queue" row, in a real browser through the real ergostat server, on a record of three green
batches and one running: the running batch's gaps and the waiting line in the order they will be taken, its current
stages with elapsed, expected and time left, and each of the row's panels opening in the panel editor with its query.

    uv run --with playwright==1.63.0 python -m pytest tests/test_dashboard_merge_queue.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat import stages
from ergostat.store import Project
from tests.ports import free_port

playwright = pytest.importorskip("playwright.sync_api")

MODEL = """
    name: mq
    stocks:
      waiting: {unit: gaps}
    items:
      gap:
        id: gap/*
        states: [approved, queued, merged]
        on: {gap.queued: queued, gap.merged: merged}
        show: [rank]
      batch:
        id: batch/*
        states: [testing, pushing, landed]
        on: {batch.started: testing, batch.landed: pushing, batch.ended-landed: landed}
        finished: [landed]
        relations:
          gaps: {kind: gap}
        pipeline:
          title: Merge queue
          stages: [ruff, unit, browser, demo, push-wait]
          waiting: {kind: gap, state: approved, order: [rank, approved_at]}
    sources:
      record: {type: sql}
    """
# a green run: ruff, then unit and browser at once, then demo, then the push wait (seconds)
GREEN = [("ruff", 0, 60), ("unit", 60, 660), ("browser", 60, 560), ("demo", 660, 780), ("push-wait", 780, 1080)]


def say(p, item, span, name, t0, t1=None):
    p.events.add("batch.stage-started", item=item, at=t0, data=stages.started(span, name, 1, "full", t0, t0 + 7200))
    if t1 is not None:
        p.events.add("batch.stage-finished", item=item, at=t1, data=stages.finished(span, "passed", t1))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("mq") / "mq"
    d.mkdir()
    home = d.parent / "home"
    (d / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    with pytest.MonkeyPatch.context() as m:
        m.setenv("ERGOSTAT_HOME", str(home))
        p = Project(mdl.load(d))
        now = time.time()
        for n in range(3):                                   # three green batches, a few hours ago
            b, t = f"batch/old-{n}", now - 4 * 3600 + n * 1200
            p.events.add("batch.started", item=b, at=t, data={"gaps": [f"gap/o{n}"]})
            for s, t0, t1 in GREEN:
                say(p, b, f"{n}-{s}", s, t + t0, t + t1)
            p.events.add("batch.ended-landed", item=b, at=t + 1080)
        for g, rank, at in (("gap/g1", 5, 1), ("gap/g2", 6, 2), ("gap/g3", 2, 3), ("gap/g4", 1, 4), ("gap/g5", None, 5)):
            p.events.add("gap.approved", item=g, at=now - 3600 + at, data={"rank": rank, "approved_at": now - 3600 + at})
        p.events.add("batch.started", item="batch/now", at=now - 160, data={"gaps": ["gap/g1", "gap/g2"]})
        for g in ("gap/g1", "gap/g2"):
            p.events.add("gap.queued", item=g, at=now - 160)
        say(p, "batch/now", "r", "ruff", now - 160, now - 100)
        say(p, "batch/now", "u", "unit", now - 100)
        say(p, "batch/now", "b", "browser", now - 100)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(url + "/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            pytest.fail("the page never came up")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    assert pg.errors == []
    ctx.close()


def drawn(pg, pid: str) -> str:
    cell = pg.locator(f'[data-panel-id="{pid}"]')
    cell.scroll_into_view_if_needed()
    pg.wait_for_function("(id) => !['loading', undefined].includes(document.querySelector(`[data-panel-id=\"${id}\"]`)"
                         "?.dataset.state)", arg=pid, timeout=20000)
    assert cell.get_attribute("data-state") == "drawn", cell.inner_text()
    return cell.inner_text()


def test_the_default_dashboard_s_merge_queue_row_says_the_running_batch_its_stage_times_and_the_waiting_line(page, site):
    page.goto(site + "/dashboard")
    page.wait_for_function("() => (dashboardDraft()?.rows || []).some((r) => r.title === 'Merge queue')", timeout=20000)
    draft = page.evaluate("() => dashboardDraft()")
    row = next(r for r in draft["rows"] if r["title"] == "Merge queue")
    mine = [x for x in draft["panels"] if x["layout"]["y"] > row["layout"]["y"]]
    by = {x["title"].split(": ", 1)[1]: x for x in mine}
    assert set(by) == {"running, and waiting in the order taken", "now", "each stage of the running one", "recent",
                       "median minutes per stage"}
    assert all(q["source"] == "record" for x in mine for q in x["queries"])

    line = drawn(page, by["running, and waiting in the order taken"]["id"])
    order = [g for g in re.findall(r"gap/g\d", line)]
    assert order == ["gap/g1", "gap/g2", "gap/g4", "gap/g3", "gap/g5"], line   # in the batch, then rank, then unranked
    assert "in batch/now" in line and "waiting" in line

    now = drawn(page, by["now"]["id"])
    assert "batch/now" in now and "unit" in now and "browser" in now, now
    cells = page.locator(f'[data-panel-id="{by["now"]["id"]}"] tr').all_inner_texts()
    last = {c.split("\t")[0]: float(c.split("\t")[1]) for c in cells[1:]}      # the table: one line a row and measure
    unit = [last[f"batch/now: unit · {m}"] for m in ("elapsed_min", "expected_min", "samples", "left_min")]
    elapsed, expected, samples, left = unit
    assert 1.6 <= elapsed <= 2.5 and expected == 10.0 and samples == 3, unit   # 100 s and more; 600 s; three runs
    # left: the longer of unit and browser (600 - 100 > 500 - 100), then demo 120 and the push wait 300: 920 s
    assert 14.5 <= left <= 15.4, unit

    each = drawn(page, by["each stage of the running one"]["id"])
    assert [s for s in ("ruff", "unit", "browser") if s in each] == ["ruff", "unit", "browser"] and "running" in each
    recent = drawn(page, by["recent"]["id"])
    assert "batch/old-2" in recent and "landed" in recent
    drawn(page, by["median minutes per stage"]["id"])

    page.get_by_role("button", name="Edit", exact=True).click()
    page.wait_for_selector(".dash-grid.editing")
    for x in mine:                                   # each opens in the panel editor, its query in the SQL box
        page.locator(f'[data-panel="{x["id"]}"]').focus()
        page.keyboard.press("Tab")
        page.keyboard.press("Enter")
        page.wait_for_selector(".pe-overlay[role=dialog]")
        box = page.locator('.pe-q textarea[data-slot="text"]').first
        assert box.input_value() == x["queries"][0]["text"], x["title"]
        assert "Query (SQL)" in page.locator(".pe-q").first.inner_text()
        page.keyboard.press("Escape")
        page.wait_for_selector(".pe-overlay[role=dialog]", state="detached")
