"""Acceptance: the inbox on the page (SPEC §12o). *Needs attention* lists what waits on the owner first, each with its
answer inline: Approve on a held action approves it (an event from the owner) and the entry leaves the panel; a
person's request takes a number and Done.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_inbox_page.py -v

With ``ERGOSTAT_SHOTS=DIR`` it also saves screenshots of the panel there."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.ports import free_port

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def site(tmp_path, home):
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project

    from .test_inbox import MODEL
    (tmp_path / "ergostat.yaml").write_text(MODEL)
    p = Project(mdl.load(tmp_path))
    a = gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None})
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3, "ask": "review the queue"})
    yield from serve(tmp_path, home, p, a)


@pytest.fixture
def ticket_site(tmp_path, home):
    """Two actions asked for about one item: one approved (and run) already, one held for the owner."""
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project

    from .test_inbox import MODEL
    (tmp_path / "ergostat.yaml").write_text(MODEL)
    p = Project(mdl.load(tmp_path))
    p.events.add("ticket.opened", item="ticket/SCRUM-2", source="test")
    done = gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": "ticket/SCRUM-2"})
    gate.approve(p, p.model.spec, done["id"], by="owner")
    a = gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": "ticket/SCRUM-2"})
    yield from serve(tmp_path, home, p, a)


def serve(tmp_path, home, p, a):
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "web", "--port", str(port)],
                            env={**os.environ, "ERGOSTAT_HOME": str(home)}, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
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
    yield url, p, a
    proc.terminate()
    proc.wait(timeout=10)


def shot(pg, name: str) -> None:
    d = os.environ.get("ERGOSTAT_SHOTS")
    if d:
        Path(d).mkdir(parents=True, exist_ok=True)
        pg.locator("#side, .side, aside").first.screenshot(path=str(Path(d) / name))


def test_approve_in_the_side_panel(site):
    from ergostat.actions import record
    url, p, a = site
    short = record.short(a["id"])
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        row = pg.locator(f'[data-inbox="action/{short}"]')
        row.wait_for(timeout=20000)
        assert "push" in row.inner_text() and "waiting" in row.inner_text()
        assert pg.locator('[data-inbox^="person/reviewer@"] input[type=number]').count() == 1
        shot(pg, "side-panel-waiting.png")
        row.locator('button[data-verb="approve"]').click()
        pg.wait_for_function(f"""() => !document.querySelector('[data-inbox="action/{short}"]')""", timeout=20000)
        got = record.get(p, a["id"])
        assert got["state"] == "ran" and got["approved_by"] == "owner"
        person = pg.locator('[data-inbox^="person/reviewer@"]')
        person.locator("input[type=number]").fill("2")
        shot(pg, "side-panel-after-approve.png")
        person.locator('button[data-verb="done"]').click()
        pg.wait_for_function("""() => !document.querySelector('[data-inbox^="person/reviewer@"]')""", timeout=20000)
        assert p.events.query(n=1, type="agent.ran", item="reviewer")[-1]["data"]["done"] == 2.0
        shot(pg, "side-panel-answered.png")
        assert not errors, errors
        b.close()


def test_a_denied_row_says_by_whom_and_links_its_item_whose_page_shows_it(ticket_site):
    from ergostat.actions import record
    url, p, a = ticket_site
    short = record.short(a["id"])
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        row = pg.locator(f'[data-inbox="action/{short}"]')
        row.wait_for(timeout=20000)
        row.locator('input[aria-label="Why"]').fill("not on a Friday")
        row.locator('button[data-verb="deny"]').click()
        done = pg.locator(f'[data-answered="action/{short}"]')
        done.wait_for(timeout=20000)
        for _ in range(2):                              # the side list drawn again from the record: still there
            with pg.expect_response(lambda r: "/api/" in r.url, timeout=20000):
                pass
        assert pg.locator(f'[data-inbox="action/{short}"]').count() == 0 and done.count() == 1
        said = done.inner_text()
        assert "Denied by you at" in said and "reason: not on a Friday" in said, said
        link = done.locator('a[href="/item/ticket%2FSCRUM-2"]')
        assert link.count() == 1 and link.inner_text() == "ticket/SCRUM-2"
        assert record.get(p, a["id"])["state"] == "denied"
        link.click()
        lines = pg.locator('h2:has-text("Gated actions") + div .claim > p:first-child')
        lines.first.wait_for(timeout=20000)
        texts = lines.all_inner_texts()
        assert len(texts) == 2, texts
        assert all("approved by" in t or "denied by" in t for t in texts), texts
        assert any("denied by owner" in t and "not on a Friday" in t for t in texts), texts
        assert any("approved by owner" in t and ", ran " in t for t in texts), texts
        assert not errors, errors
        b.close()
