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

DECIDER = """\
  decider:
    type: person
    ask: push the queue, or not?
    goal: queue-short
    out:
      declared: flow.declared
      dismissed: flow.dismissed
"""
DECIDED = "  declared:\n    from: queue\n  dismissed:\n    from: queue\ngoals:"   # its two flows, beside the others


@pytest.fixture
def site(tmp_path, home):
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project

    from .test_inbox import MODEL
    (tmp_path / "ergostat.yaml").write_text(MODEL.replace("notify:", DECIDER + "notify:", 1).replace("goals:", DECIDED, 1))
    p = Project(mdl.load(tmp_path))
    a = gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None})
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3, "ask": "review the queue"})
    p.events.add("person.asked", item="decider", source="ergostat", data={"command": 1, "ask": "push it?"})
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


def test_every_answer_in_the_side_list_has_a_full_label_and_a_number_its_unit(site):
    """Acceptance (ui-a-number-or-reason-asked-of-a-person-has-a-full): each input of the side list sits under a
    visible <label> shown whole (scrollWidth <= clientWidth), as wide as its row, with no placeholder to be cut; a
    number's label names its unit; a yes-or-no ask gets Yes and No, no number box, and Yes records one."""
    url, p, _ = site
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        pg.locator('[data-inbox^="person/decider@"]').wait_for(timeout=20000)
        got = pg.evaluate("""() => [...document.querySelectorAll('.att .inbox-act input')].map((i) => {
            const l = i.closest('label'), row = i.closest('.inbox-act');
            return { label: l ? l.innerText : null, shown: !!l && l.getBoundingClientRect().height > 0,
                     whole: !!l && [l, ...l.children].every((x) => x.scrollWidth <= x.clientWidth),
                     placeholder: i.placeholder, wide: i.getBoundingClientRect().width / row.clientWidth }; })""")
        assert len(got) == 2, got                       # the reviewer's number and the held action's reason
        for x in got:
            assert x["label"] and x["shown"] and x["whole"] and not x["placeholder"] and x["wide"] > 0.9, x
        labels = [" ".join(x["label"].split()) for x in got]
        assert "Jobs done, along reviewed (number)" in labels and "Reason for denying (optional)" in labels, labels
        decider = pg.locator('[data-inbox^="person/decider@"]')
        assert decider.locator("input").count() == 0
        assert decider.locator("button").all_inner_texts() == ["Yes", "No"]
        assert "Yes moves one of jobs, along declared" in decider.inner_text()
        decider.locator("button", has_text="Yes").click()
        pg.wait_for_function("""() => !document.querySelector('[data-inbox^="person/decider@"]')""", timeout=20000)
        assert p.events.query(n=1, type="agent.ran", item="decider")[-1]["data"]["done"] == 1.0
        assert not errors, errors
        b.close()
