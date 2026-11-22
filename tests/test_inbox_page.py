"""Acceptance: the inbox on the page (SPEC §12o). *Needs attention* lists what waits on the owner first, each with its
answer inline: Approve on a held action approves it (an event from the owner) and the entry leaves the panel; a
person's request takes a number and Done.

It needs Playwright and a Chromium, so the usual run skips it:

    uv run --with playwright==1.63.0 python -m pytest tests/test_inbox_page.py -v

With ``ERGOSTAT_SHOTS=DIR`` it also saves screenshots of the panel there."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from tests.ports import free_port

playwright = pytest.importorskip("playwright.sync_api")


MOVE = """actions:
  move:
    run: "python3 bin/move.py {key}"
    gate: approve
    args: {key: the issue}
    description: Move an issue to done
"""
ASK = "Review the queue.\\nOutward acts wait for you: `ergostat actions` lists them.\\nThird.\\nFourth.\\nThe fifth line."


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
def sentences(tmp_path, home):
    """A held action with a description, an argument and a python3 command, and a person asked five lines with code."""
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project

    from .test_inbox import MODEL
    (tmp_path / "ergostat.yaml").write_text(MODEL.replace("actions:\n", MOVE, 1)
                                            .replace("ask: review the queue", f'ask: "{ASK}"'))
    p = Project(mdl.load(tmp_path))
    a = gate.request(p, p.model.spec, "move", {"key": "SCRUM-7"}, {"block": "pusher", "item": "queue"})
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3})
    yield from serve(tmp_path, home, p, a)


@pytest.fixture
def deny_only(tmp_path, home):
    """A modelling request held with no AI tier to hand it back to: Deny is its only answer."""
    from .test_inbox import held_request
    p, r, eid = held_request(tmp_path, ai=False)
    yield from serve(tmp_path, home, p, eid)


@pytest.fixture
def ladder(tmp_path, home):
    """A class the owner approved six times this week, none denied, with one more held: up the ladder."""
    from ergostat import model as mdl
    from ergostat.actions import gate, record
    from ergostat.inbox import answer
    from ergostat.store import Project

    from .test_inbox import MODEL
    (tmp_path / "ergostat.yaml").write_text(MODEL)
    p = Project(mdl.load(tmp_path))
    for _ in range(6):
        a = gate.request(p, p.model.spec, "push", {}, {"block": "pusher"})
        answer.answer(p, p.model.spec, f"action/{record.short(a['id'])}", "approve")
    a = gate.request(p, p.model.spec, "push", {}, {"block": "pusher"})
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


def waiting_entries(pg) -> list[dict]:
    """Each entry waiting on the owner in the side list: its text, its first line, its command box and its answers."""
    pg.locator("[data-inbox]").first.wait_for(timeout=20000)
    return pg.eval_on_selector_all("[data-inbox]", """els => els.map(e => ({
        id: e.dataset.inbox, text: e.textContent, first: e.querySelector('.ask-first')?.textContent,
        ladder: e.querySelector('.ladder')?.textContent,
        cmd: e.querySelector('details.cmd')?.textContent, cmdOpen: e.querySelector('details.cmd')?.open,
        rest: e.querySelector('details.ask')?.textContent, restOpen: e.querySelector('details.ask')?.open,
        verbs: [...e.querySelectorAll('button[data-verb]')].map(b => b.dataset.verb)}))""")


def readable(e: dict) -> None:
    """The acceptance on every entry: no '...', no backtick, a first line before any python3, the command closed."""
    assert "..." not in e["text"] and "`" not in e["text"], e
    assert e["first"] and "python3" not in e["first"] and "ergostat inbox" not in e["first"], e
    assert e["cmd"] and e["cmdOpen"] is False and "ergostat inbox" in e["cmd"], e
    if e["verbs"] == ["deny"]:
        assert re.search(r"(^|[.:;] )Deny ", e["text"]), e


def test_a_request_reads_as_a_sentence_with_its_command_folded(sentences):
    from ergostat.actions import record
    url, p, a = sentences
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        es = {e["id"].split("/")[0]: e for e in waiting_entries(pg)}
        for e in es.values():
            readable(e)
        act = es["action"]
        assert act["first"].startswith("Move an issue to done (key SCRUM-7), for queue, asked by pusher"), act
        assert "python3 bin/move.py SCRUM-7" in act["cmd"] and act["id"] == f"action/{record.short(a['id'])}"
        person = es["person"]
        assert person["first"].startswith("reviewer asks: Review the queue.") and "Fourth" not in person["first"]
        assert "ergostat actions" in person["first"] and person["restOpen"] is False and "The fifth line." in person["rest"]
        pg.goto(f"{url}/item/{a['id']}")                    # the action's own page: the sentence first, the command closed
        says = pg.locator(".action-says")
        says.wait_for(timeout=20000)
        assert says.inner_text().startswith("Move an issue to done (key SCRUM-7), for queue, asked by pusher")
        box = pg.locator(".claim details.cmd")
        assert box.count() == 1 and not box.evaluate("d => d.open") and "python3 bin/move.py SCRUM-7" in box.text_content()
        assert not errors, errors
        b.close()


def test_a_deny_only_modelling_request_says_what_deny_does(deny_only):
    url, p, eid = deny_only
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.goto(f"{url}/diagram?view=blocks")
        es = waiting_entries(pg)
        req = [e for e in es if e["id"] == eid]
        assert req and req[0]["verbs"] == ["deny"], es
        for e in es:
            readable(e)
        assert "Modelling cannot decide it" in req[0]["first"] and "Deny tells it to stop asking" in req[0]["text"]
        b.close()


def test_an_entry_keeps_its_class_record_and_its_suggestion_up_the_ladder(ladder):
    """SPEC §12o: each entry shows its class's record, and a class always approved is suggested up the ladder."""
    from ergostat.actions import record
    url, p, a = ladder
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.goto(f"{url}/diagram?view=blocks")
        es = {e["id"]: e for e in waiting_entries(pg)}
        act = es[f"action/{record.short(a['id'])}"]
        readable(act)
        assert act["ladder"] and act["ladder"].startswith("7 asked this week, 6 approved, 0 denied"), act
        assert "6 approvals of outward this week, all approved: consider gate: auto" in act["ladder"], act
        assert "python3" not in act["ladder"] and "consider gate" not in act["first"], act
        b.close()
