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


def test_approve_and_deny_say_what_they_answer_in_an_order_the_keyboard_can_use(site):
    """Each answer names its object (seen: 'Approve the push'; heard: with the entry's id, unique in the list); the
    keyboard reaches the reason before Deny, which waits for the reason; Approve and Deny are drawn alike."""
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
        pg.locator('[data-inbox^="person/reviewer@"] button').wait_for(timeout=20000)
        names = pg.eval_on_selector_all(".att [data-inbox] button", "bs => bs.map((b) => b.getAttribute('aria-label') "
                                        "|| b.textContent.trim())")
        assert len(names) >= 3 and all(len(n.split()) > 1 for n in names), names
        assert len(set(names)) == len(names), names
        approve, deny = row.locator('button[data-verb="approve"]'), row.locator('button[data-verb="deny"]')
        assert approve.inner_text() == "Approve the push" and deny.inner_text() == "Deny the push"
        style = "b => { const s = getComputedStyle(b); return [s.borderTopStyle, s.borderTopWidth, s.borderTopColor]; }"
        assert approve.evaluate(style) == deny.evaluate(style) and approve.evaluate(style)[0] != "none"
        assert deny.is_disabled()
        # the keyboard path: from the entry's link, Tab reaches the reason, a reason is typed, then Approve, then Deny
        row.locator("a").first.focus()
        seen = []
        for _ in range(3):
            pg.keyboard.press("Tab")
            seen.append(pg.evaluate("() => document.activeElement.getAttribute('data-verb') || "
                                    "document.activeElement.tagName.toLowerCase()"))
            if seen[-1] == "input":
                pg.keyboard.type("not today")
        assert seen == ["input", "approve", "deny"], seen
        pg.wait_for_timeout(3000)                   # a refresh of the list (every 2.5 s) keeps the reason, and Deny on
        assert not deny.is_disabled() and pg.evaluate("() => document.activeElement.dataset.verb") == "deny"
        pg.keyboard.press("Enter")
        pg.wait_for_function(f"""() => !document.querySelector('[data-inbox="action/{short}"]')""", timeout=20000)
        got = record.get(p, a["id"])
        assert got["state"] == "denied" and got.get("note") == "not today", got
        assert not errors, errors
        b.close()
