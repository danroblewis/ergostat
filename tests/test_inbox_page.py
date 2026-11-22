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


def serve(tmp_path, home, requests: int = 1):
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project

    from .test_inbox import MODEL
    (tmp_path / "ergostat.yaml").write_text(MODEL)
    p = Project(mdl.load(tmp_path))
    a = [gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None}) for _ in range(requests)]
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
    return url, p, a, proc


@pytest.fixture
def site(tmp_path, home):
    url, p, a, proc = serve(tmp_path, home)
    yield url, p, a[0]
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def three(tmp_path, home):
    url, p, a, proc = serve(tmp_path, home, requests=3)
    yield url, p, a
    proc.terminate()
    proc.wait(timeout=10)


def leave(pg) -> None:
    """The reader leaves the side list: the pointer off it, the focus off it."""
    off(pg)
    pg.evaluate("() => document.activeElement?.blur()")


def off(pg) -> None:
    """The pointer off the side list, over the diagram beside it."""
    side = pg.locator(".side").bounding_box()
    pg.mouse.move(max(5, side["x"] - 120), side["y"] + 120)


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
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()", arg=row.element_handle(), timeout=20000)
        leave(pg)                                           # answered, it says so in its row until the reader leaves
        pg.wait_for_function(f"""() => !document.querySelector('[data-inbox="action/{short}"]')""", timeout=20000)
        got = record.get(p, a["id"])
        assert got["state"] == "ran" and got["approved_by"] == "owner"
        person = pg.locator('[data-inbox^="person/reviewer@"]')
        person.locator("input[type=number]").fill("2")
        shot(pg, "side-panel-after-approve.png")
        person.locator('button[data-verb="done"]').click()
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()", arg=person.element_handle(), timeout=20000)
        leave(pg)
        pg.wait_for_function("""() => !document.querySelector('[data-inbox^="person/reviewer@"]')""", timeout=20000)
        assert p.events.query(n=1, type="agent.ran", item="reviewer")[-1]["data"]["done"] == 2.0
        shot(pg, "side-panel-answered.png")
        assert not errors, errors
        b.close()


def alarms_coming(pg, gone: set) -> list[int]:
    """New alarms, one more with each answer of the diagram's graph, ahead of what waits on the owner (as alarms are
    listed): the rows below them pushed down and out, unless the list holds still. What is in ``gone`` is taken out
    of the answers (a request withdrawn)."""
    n = [0]

    def more(route):
        resp = route.fetch()
        body = resp.json()
        if isinstance(body, dict) and isinstance(body.get("attention"), list):
            n[0] += 1
            body["attention"] = [{"level": "bad", "what": f"alarm new-{i}", "says": f"raised by the test ({i})"}
                                 for i in range(n[0])] + [a for a in body["attention"] if a["what"] not in gone]
        route.fulfill(response=resp, json=body)
    pg.route("**/api/graph*", more)
    return n


@pytest.mark.slow
def test_the_side_list_holds_still_while_the_reader_is_in_it_and_a_request_stays_until_answered(three):
    """Hover the third request for 40 s: its top moves 0 px and it is still there, though alarms kept coming; type in
    its reason box and wait 40 s: the text and the focus remain. Left, the updates apply; answered or withdrawn while
    the reader is in the list, a request stays in its place and says so in its row."""
    from ergostat.actions import record
    url, p, reqs = three
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        gone: set = set()
        n = alarms_coming(pg, gone)
        pg.goto(f"{url}/diagram?view=blocks")
        pg.locator('[data-inbox^="action/"]').nth(2).wait_for(timeout=20000)
        pg.wait_for_selector('[data-row="alarm new-1"]', timeout=20000)           # the alarms are coming
        what = pg.locator("[data-inbox]").nth(2).get_attribute("data-inbox")
        row = pg.locator(f'[data-inbox="{what}"]')
        row.hover()
        top, seen = row.bounding_box()["y"], n[0]
        for _ in range(20):
            pg.wait_for_timeout(2000)
            assert row.count() == 1 and row.bounding_box()["y"] == top
        assert n[0] >= seen + 5, n                                             # (and the answers kept coming)
        assert "updates waiting" in pg.inner_text(".needs > .waiting")
        why = row.locator('input[aria-label="Why"]')
        why.fill("not this week")
        box = why.element_handle()
        off(pg)                                                                # the focus alone holds it now
        seen = n[0]
        for _ in range(20):
            pg.wait_for_timeout(2000)
            assert box.evaluate("(el) => el.isConnected && el === document.activeElement && el.value") == "not this week"
            assert row.bounding_box()["y"] == top
        assert n[0] >= seen + 5, n
        leave(pg)                                                              # left: what waited is applied
        pg.wait_for_function("([w, y]) => document.querySelector(`[data-inbox=\"${w}\"]`).getBoundingClientRect().y > y + 1",
                             arg=[what, top], timeout=20000)
        assert not pg.locator(".needs > .waiting").count()
        assert pg.locator('[data-inbox^="action/"]').count() == 3              # every request listed, alarms or not
        # answered from its row while the reader is in the list: it stays where it is and says so
        row.locator('input[aria-label="Why"]').fill("not this week")
        row.locator('button[data-verb="deny"]').click()
        top = row.bounding_box()["y"]
        pg.wait_for_timeout(6000)
        assert row.count() == 1 and row.bounding_box()["y"] == top and row.locator(".inbox-act .note").inner_text().strip()
        # another withdrawn meanwhile (gone from the answers): its row stays, saying it no longer waits
        other = pg.locator('[data-inbox^="action/"]').nth(0)
        name = other.get_attribute("data-inbox")
        gone.add(name)
        said = "(w) => document.querySelector(`[data-inbox=\"${w}\"] .inbox-act .note`).textContent.includes('no longer waiting')"
        pg.wait_for_function(said, arg=name, timeout=20000)
        leave(pg)
        pg.wait_for_function("(ws) => ws.every((w) => !document.querySelector(`[data-inbox=\"${w}\"]`))", arg=[what, name], timeout=20000)
        assert any(record.get(p, a["id"])["state"] == "denied" for a in reqs)
        assert not errors, errors
        b.close()
