"""Acceptance (forecast-sentence-in-words): a goal's panel says its forecast as a sentence in words, a clock time or a
duration and 'N in 10', with p, the runs and the horizon only in its closed 'How this was worked out' disclosure."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
import time
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat.store import Project
from tests.test_closedloop import ONOFF

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def site(tmp_path):
    d = tmp_path / "o"
    d.mkdir()
    (d / "ergostat.yaml").write_text(textwrap.dedent(ONOFF))
    p, now = Project(mdl.load(d)), time.time()
    for i in range(121):                               # two hours of record of an on/off drain loop
        t = now - 7200 + i * 60
        p.measurements.add("sensor/arrivals.main", 10.0, at=t)
        p.measurements.add("sensor/queue.main", 12.0 + (i % 40) / 4, at=t)
        p.measurements.add("block/keep", float((i // 20) % 2), at=t)
    for i in range(30):
        p.events.add("agent.ran", item="worker", data={"exit": 0, "seconds": 1.0}, at=now - 7000 + i * 200)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(tmp_path / "home")},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 120                   # a loaded machine starts it slowly: wait for it, not a count
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


def test_a_goals_panel_says_its_forecast_in_words(site):
    with playwright.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as e:                          # no Chromium here
            pytest.skip(f"no Chromium to drive: {e}")
        pg = b.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(site + "/")
        pg.wait_for_function("typeof openLoop === 'function' && S.status && S.status.loops")
        pg.evaluate("openLoop('queue-short')")
        pg.wait_for_selector(".ahead .forecast", timeout=60000)
        said = pg.locator(".ahead .forecast > p").inner_text()
        assert said.startswith("queue-short: ") and (" in 10)" in said or "back within its bound by" in said), said
        assert any(w in said for w in ("minute", "hour", "day", ":")), said        # a duration or a clock time
        shown = pg.locator(".ahead").evaluate("""b => [...b.querySelectorAll('*')].filter(e => e.checkVisibility())
            .map(e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.data).join('')).join(' ')""")
        assert "p≈" not in shown and "runs)" not in shown, shown
        assert pg.locator(".ahead details").get_attribute("open") is None    # closed until asked
        assert "p≈" in pg.locator(".ahead .forecast > p").get_attribute("title")
        pg.locator(".ahead details summary").click()
        opened = pg.locator(".ahead details").inner_text().lower()     # the labels are capitalised by the page's style
        for w in ("how this was worked out", "chance off at the horizon", "p≈", "runs", "horizon", "method"):
            assert w in opened, opened
        assert not errors, errors
        b.close()
