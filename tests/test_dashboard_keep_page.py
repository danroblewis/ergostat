"""Acceptance: Keep on the Dashboard page, on a served copy of examples/image-squeeze (the real server, nothing faked).
Keep makes one model-change of kind display and writes no file; Accept under Changes to review writes it; then
/dashboard?name=NAME draws it, and `ergostat check` passes.

    uv run --with playwright==1.63.0 python -m pytest tests/test_dashboard_keep_page.py -v
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.ports import free_port

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
DRAFT = {"title": "Lab watch", "since": "1d", "panels": [
    {"id": "p1", "title": "hypotheses held", "form": "line", "size": "m", "note": "",
     "queries": [{"id": "a", "source": "counts", "kind": "hypothesis", "group_by": "kind", "agg": "last",
                  "transform": "none", "label": "held"}], "display": {"unit": "items"}}]}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("keep") / "image-squeeze"
    shutil.copytree(ROOT / "examples" / "image-squeeze", d, ignore=shutil.ignore_patterns("run", "__pycache__"))
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
        pytest.fail("the page never came up")
    yield url, d
    proc.terminate()
    proc.wait(timeout=10)


def texts(d: Path) -> dict:
    return {f.name: f.read_text() for f in sorted(d.glob("*.yaml"))}


def test_keep_makes_one_display_change_and_after_accept_the_dashboard_draws_it(site):
    url, d = site
    before = texts(d)
    enc = base64.urlsafe_b64encode(json.dumps(DRAFT).encode()).decode().rstrip("=")
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/dashboard?draft={enc}")
        pg.wait_for_selector(".dash-keep")
        pg.click(".dash-keep")
        pg.wait_for_function("() => /Kept as a change/.test(document.querySelector('.dash-said')?.textContent || '')",
                             timeout=30000)
        assert texts(d) == before                                    # Keep writes nothing
        pg.goto(f"{url}/model")
        pg.wait_for_selector("article.entry[data-kind=display]", timeout=60000)
        entries = pg.locator("article.entry[data-kind=display]")
        assert entries.count() == 1
        assert "you (Keep, on the Dashboard)" in entries.first.inner_text()
        assert texts(d) == before
        entries.first.get_by_role("button", name="Effect and diff").click()
        assert "lab-watch:" in entries.first.inner_text()            # the diff, worked out by the server, shown
        entries.first.get_by_role("button", name="Accept", exact=True).click()
        entries.first.get_by_role("button", name="Write it").click()
        pg.wait_for_function("() => /Accepted:/.test(document.body.textContent)", timeout=60000)
        assert "lab-watch:" in texts(d)["ergostat.yaml"]
        assert [k for k in before if texts(d)[k] != before[k]] == ["ergostat.yaml"]
        pg.goto(f"{url}/dashboard?name=lab-watch")
        pg.wait_for_selector(".dash-cell")
        assert pg.locator(".dash-head h1").inner_text() == "Lab watch"
        assert "hypotheses held" in pg.locator(".dash-grid").inner_text()
        assert pg.locator(".dash-keep").count() == 0               # a declared one is not kept again as it is
        b.close()
    assert not errors, errors
    listed = json.loads(urllib.request.urlopen(url + "/api/dashboards", timeout=10).read())
    assert "lab-watch" in [x["name"] for x in listed]
    got = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), "check"], capture_output=True, text=True,
                         env={**os.environ, "ERGOSTAT_HOME": str(d.parent / "home")})
    assert got.returncode == 0, got.stdout[-2000:] + got.stderr[-2000:]
