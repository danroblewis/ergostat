"""Acceptance (data-source-model): a Dashboard panel whose query is PromQL, asked of a stub Prometheus through the real
ergostat server, is drawn; a query over the bounds, an unreachable source and a bad query each say so in their panel; and
the panel editor offers the model's source with a text field in its language.

    uv run --with playwright==1.63.0 python -m pytest tests/test_data_source_panels.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from tests.ports import free_port
from tests.test_data_sources import Stub

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    stub = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    d = tmp_path_factory.mktemp("ds") / "ds"
    d.mkdir()
    (d / "ergostat.yaml").write_text(
        "name: ds\nstocks:\n  queue: {unit: tickets}\nsources:\n"
        f"  prom: {{type: prometheus, url: 'http://127.0.0.1:{stub.server_address[1]}'}}\n"
        f"  down: {{type: prometheus, url: 'http://127.0.0.1:{free_port()}'}}\n")
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")},
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
        stub.shutdown()
        pytest.fail("the page never came up")
    yield url
    proc.terminate()
    proc.wait(timeout=10)
    stub.shutdown()
    stub.server_close()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def panel(pid: str, source: str, text: str) -> dict:
    return {"id": pid, "title": pid, "note": "", "form": "line", "size": "m", "tall": False, "display": {},
            "queries": [{"id": "a", "source": source, "text": text}]}


def draft(*panels) -> str:
    raw = json.dumps({"title": "Sources", "panels": list(panels)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def opened(browser, url):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(url)
    return ctx, pg


def state(pg, pid: str) -> str:
    return pg.locator(f'[data-panel-id="{pid}"]').get_attribute("data-state")


def test_a_promql_panel_is_drawn_and_each_failure_says_so_in_its_panel(browser, site):
    ctx, pg = opened(browser, f"{site}/dashboard?draft=" + draft(
        panel("drawn", "prom", "sum by (job) (up)"), panel("many", "prom", "many"),
        panel("down", "down", "up"), panel("bad", "prom", "sum(up")))
    pg.wait_for_function("""() => ['drawn', 'many', 'down', 'bad'].every((id) => {
        const s = document.querySelector(`[data-panel-id="${id}"]`)?.dataset.state; return s && s !== 'loading'; })""",
                         timeout=20000)
    assert state(pg, "drawn") == "drawn"
    assert pg.locator('[data-panel-id="drawn"] .uplot canvas').count() > 0
    legend = pg.locator('[data-panel-id="drawn"]').inner_text()
    assert 'up{job="a"}' in legend and 'up{job="b"}' in legend
    said = {pid: pg.locator(f'[data-panel-id="{pid}"] .panel-message').inner_text() for pid in ("many", "down", "bad")}
    assert {pid: state(pg, pid) for pid in said} == {"many": "error", "down": "error", "bad": "error"}
    assert "51 series, more than the 50" in said["many"]
    assert "could not reach source 'down'" in said["down"]
    assert "parse error: unclosed left parenthesis" in said["bad"]
    assert pg.errors == []
    ctx.close()


def test_a_source_that_trickles_its_answer_says_so_in_its_panel_at_the_time_bound(browser, site):
    t0 = time.monotonic()
    ctx, pg = opened(browser, f"{site}/dashboard?draft=" + draft(panel("slow", "prom", "trickle")))
    pg.wait_for_function("""() => { const s = document.querySelector('[data-panel-id="slow"]')?.dataset.state;
                                    return s && s !== 'loading'; }""", timeout=30000)
    took = time.monotonic() - t0
    assert state(pg, "slow") == "error"
    assert "did not answer within" in pg.locator('[data-panel-id="slow"] .panel-message').inner_text()
    assert took < 16, took                          # the 10 s bound, and the page's own load (the stub would go on 30 s)
    assert pg.errors == []
    ctx.close()


def test_the_editor_offers_the_source_and_a_text_in_its_language(browser, site):
    ctx, pg = opened(browser, f"{site}/dashboard?draft=" + draft(panel("drawn", "prom", "up")))
    pg.wait_for_selector('[data-panel-id="drawn"][data-state="drawn"]', timeout=20000)
    pg.evaluate("""() => openPanelEditor({ id: 'n', title: 'New', note: '', form: 'line', queries: [{ id: 'a' }],
                                           display: {}, size: 'm', tall: false }, {})""")
    source = pg.locator('.pe-q select[data-slot="source"]').first
    pg.wait_for_function("() => [...document.querySelectorAll('.pe-q select[data-slot=source] option')].some((o) => o.value === 'prom')")
    assert "prom (PromQL)" in source.inner_text()
    source.select_option("prom")
    text = pg.locator('.pe-q textarea[data-slot="text"]')
    assert "Query (PromQL)" in pg.locator(".pe-q").first.inner_text()
    assert pg.locator('.pe-q select[data-slot="agg"]').count() == 0           # nothing is built: the text is the query
    text.fill("sum(up")
    pg.wait_for_function("() => document.querySelector('.pe-q-msg')?.textContent.includes('parse error')", timeout=10000)
    assert pg.errors == []
    ctx.close()
