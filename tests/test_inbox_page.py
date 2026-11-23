"""Acceptance: the inbox on the page (SPEC §12o). *Waiting for you* lists what waits on the owner first, each with its
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


MOVE = """actions:
  move:
    run: "python3 bin/move.py {key}"
    gate: approve
    args: {key: the issue}
    description: Move an issue to done
"""
ASK = "Review the queue.\\nOutward acts wait for you: `ergostat actions` lists them.\\nThird.\\nFourth.\\nThe fifth line."


def pushes(tmp_path, requests: int, decider: bool = False):
    """The model with this many push actions held, and a person asked to review the queue (and, with ``decider``, a
    person whose outputs are two named ends, as the-job's declare-incident)."""
    from ergostat import model as mdl
    from ergostat.actions import gate
    from ergostat.store import Project

    from .test_inbox import MODEL
    text = MODEL.replace("notify:", DECIDER + "notify:", 1).replace("goals:", DECIDED, 1) if decider else MODEL
    (tmp_path / "ergostat.yaml").write_text(text)
    p = Project(mdl.load(tmp_path))
    a = [gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None}) for _ in range(requests)]
    p.events.add("person.asked", item="reviewer", source="ergostat", data={"command": 3, "ask": "review the queue"})
    if decider:
        p.events.add("person.asked", item="decider", source="ergostat", data={"command": 1, "ask": "push it?"})
    return p, a


@pytest.fixture
def site(tmp_path, home):
    p, a = pushes(tmp_path, 1)
    yield from serve(tmp_path, home, p, a[0])


@pytest.fixture
def decided(tmp_path, home):
    p, a = pushes(tmp_path, 1, decider=True)
    yield from serve(tmp_path, home, p, a[0])


@pytest.fixture
def three(tmp_path, home):
    p, a = pushes(tmp_path, 3)
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


@pytest.fixture
def held_again(tmp_path, home):
    """A modelling request held for the owner: its id is fixed, so held again it comes back under the same id."""
    from .test_inbox import held_request
    p, r, eid = held_request(tmp_path)
    yield from serve(tmp_path, home, p, (r, eid))


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


def leave(pg) -> None:
    """The reader leaves the side list: the pointer off it, the focus off it."""
    off(pg)
    pg.evaluate("() => document.activeElement?.blur()")


def off(pg) -> None:
    """The pointer off the side list, over the diagram beside it."""
    side = pg.locator(".side").bounding_box()
    pg.mouse.move(max(5, side["x"] - 120), side["y"] + 120)


def unfold(pg) -> None:
    """More than 3 waiting sit in one closed line, "N wait for you": the reader opens it, then moves off it."""
    pg.wait_for_selector(".side details.waiting-fold", state="attached", timeout=20000)
    if not pg.evaluate("() => document.querySelector('.side details.waiting-fold').open"):
        pg.locator(".side details.waiting-fold > summary").click()
    off(pg)


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


INPUTS = """() => [...document.querySelectorAll('.att .inbox-act input')].map((i) => {
    const l = i.closest('label'), row = i.closest('.inbox-act');
    return { label: l ? l.innerText : null, shown: !!l && l.getBoundingClientRect().height > 0,
             whole: !!l && [l, ...l.children].every((x) => x.scrollWidth <= x.clientWidth),
             placeholder: i.placeholder, wide: i.getBoundingClientRect().width / row.clientWidth }; })"""


@pytest.fixture
def folds(tmp_path, home):
    """Three stocks with no description, each a modelling request held for the owner: alike, so one folded entry."""
    from ergostat import model as mdl
    from ergostat.numbers import requests as rq
    from ergostat.store import Project

    from .test_inbox import MODEL
    from .test_modelling_core import MODELLING
    mine = {f"stock.bare-{i}" for i in range(3)}
    stocks = "".join(f"  bare-{i}:\n    unit: things\n    sensor: {{manual: true}}\n" for i in range(3))
    (tmp_path / "ergostat.yaml").write_text(MODEL.replace("stocks:\n", "stocks:\n" + stocks, 1) + MODELLING)
    p = Project(mdl.load(tmp_path))
    rq.sync(p)
    held = [r for r in rq.current(p, ("open",)) if r["code"] == "no-description" and r["about"] in mine]
    assert len(held) == 3, sorted(r["about"] for r in held)
    for r in held:
        rq.mark(p, r, "held", "no tier has a change for it")
    yield from serve(tmp_path, home, p, held)


def test_the_folded_requests_deny_all_reason_has_a_full_label_too(folds):
    """Acceptance, the folded requests (the review of round 5): the fold's own Deny all reason, and each member's
    reason once the fold is opened, sit under a visible <label> shown whole, as wide as the row, with no placeholder."""
    url, p, _ = folds
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        fold = pg.locator('.side .att > [data-fold^="no-description|"]')
        fold.wait_for(state="attached", timeout=60000)
        house = pg.locator(".side details.housekeeping")             # held requests are housekeeping (folded)
        if house.count() and not house.evaluate("(d) => d.open"):
            house.locator(":scope > summary").click()
        fold.locator(":scope > details.fold > summary").click()
        assert fold.locator(':scope > details.fold > [data-inbox^="request/"]').count() == 3
        got = pg.evaluate(INPUTS)
        labels = [" ".join((x["label"] or "").split()) for x in got]
        assert labels.count("Reason for denying all (required)") == 1, got           # the fold's own reason
        assert labels.count("Reason for denying (required)") >= 3, got              # each member's
        for x in got:
            assert x["label"] and x["shown"] and x["whole"] and not x["placeholder"] and x["wide"] > 0.9, x
        assert not errors, errors
        b.close()


def test_every_answer_in_the_side_list_has_a_full_label_and_a_number_its_unit(decided):
    """Acceptance (ui-a-number-or-reason-asked-of-a-person-has-a-full): each input of the side list sits under a
    visible <label> shown whole (scrollWidth <= clientWidth), as wide as its row, with no placeholder to be cut; a
    number's label names its unit and the flow it moves; a person with two named ends (as the-job's approve-ramps and
    declare-incident) keeps its number, which moves its first flow, and Done records what was typed."""
    url, p, _ = decided
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        pg.locator('[data-inbox^="person/decider@"] .inbox-act button').first.wait_for(timeout=20000)
        got = pg.evaluate(INPUTS)
        assert len(got) == 3, got                      # the two numbers and the held action's reason
        for x in got:
            assert x["label"] and x["shown"] and x["whole"] and not x["placeholder"] and x["wide"] > 0.9, x
        labels = [" ".join(x["label"].split()) for x in got]
        assert labels.count("Jobs done, along reviewed (number)") == 1 and "Reason for denying (required)" in labels
        assert "Jobs done, along declared (number)" in labels, labels      # two ends: its first flow, a number
        decider = pg.locator('[data-inbox^="person/decider@"]')
        decider.get_by_label("Jobs done, along declared (number)").fill("2")
        buttons = decider.locator(".inbox-act button")
        assert buttons.all_inner_texts() == ["Done with decider's ask"]
        buttons.nth(0).click()
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()", arg=decider.element_handle(), timeout=20000)
        leave(pg)                                       # answered, it says so in its row until the reader leaves
        pg.wait_for_function("""() => !document.querySelector('[data-inbox^="person/decider@"]')""", timeout=20000)
        assert p.events.query(n=1, type="agent.ran", item="decider")[-1]["data"]["done"] == 2.0
        assert not errors, errors
        b.close()


def test_a_list_the_reader_is_in_is_not_folded_away_when_a_fourth_comes(site):
    """Two waiting, the pointer on the first: alarms that wait come, past 3, and the list stays unfolded and in place
    under the pointer; left, the 4 and more fold into one line, "N wait for you"."""
    from ergostat.actions import record
    url, p, a = site
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        row = pg.locator(f'[data-inbox="action/{record.short(a["id"])}"]')
        row.wait_for(timeout=20000)
        n = alarms_coming(pg, set())
        row.hover()
        top = row.bounding_box()["y"]
        for _ in range(30):                                                    # 3 alarms more than the 2: past 3
            if n[0] >= 4:
                break
            pg.wait_for_timeout(1000)
        assert n[0] >= 4 and "updates waiting" in pg.inner_text(".needs > .waiting"), n
        assert row.is_visible() and row.bounding_box()["y"] == top
        assert not pg.locator(".side details.waiting-fold").count()
        leave(pg)
        pg.wait_for_selector(".side details.waiting-fold:not([open])", state="attached", timeout=20000)
        assert not row.is_visible()
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
        # the keyboard path: from the entry's link, Tab through the row (its folded command first) to the answer's
        # controls: the reason, a reason typed, then Approve, then Deny
        row.locator("a").first.focus()
        seen = []
        for _ in range(8):
            pg.keyboard.press("Tab")
            seen.append(pg.evaluate("() => { const e = document.activeElement; return e.closest('.inbox-act') ? "
                                    "e.getAttribute('data-verb') || e.tagName.toLowerCase() : '-'; }"))
            if seen[-1] == "input":
                pg.keyboard.type("not today")
            if seen[-1] == "deny":
                break
        assert [s for s in seen if s != "-"] == ["input", "approve", "deny"], seen
        pg.wait_for_timeout(3000)                   # a refresh of the list (every 2.5 s) keeps the reason, and Deny on
        assert not deny.is_disabled() and pg.evaluate("() => document.activeElement.dataset.verb") == "deny"
        pg.keyboard.press("Enter")
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()", arg=row.element_handle(), timeout=20000)
        leave(pg)                                   # answered, it says so in its row until the reader leaves
        pg.wait_for_function(f"""() => !document.querySelector('[data-inbox="action/{short}"]')""", timeout=20000)
        got = record.get(p, a["id"])
        assert got["state"] == "denied" and got.get("note") == "not today", got
        assert not errors, errors
        b.close()


def test_a_typed_reason_stays_with_its_entry_when_one_above_is_answered(site):
    """Three pushes wait; a reason is typed for the middle one only, then the top one is approved. The rows shift up,
    and the reason, and Deny's being on, go with the middle entry, not with its old place: the bottom entry shows no
    reason and its Deny stays off, and the middle one's denial is recorded with its own reason."""
    from ergostat.actions import gate, record
    url, p, a = site
    made = [a] + [gate.request(p, p.model.spec, "push", {}, {"block": "pusher", "item": None}) for _ in range(2)]
    ids = {f"action/{record.short(x['id'])}": x["id"] for x in made}
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        pg.wait_for_function("""() => document.querySelectorAll('.att [data-inbox^="action/"]').length === 3""",
                             timeout=20000)
        unfold(pg)                                  # (4 waiting: folded in one line)
        top, mid, low = pg.eval_on_selector_all('.att [data-inbox^="action/"]', "rs => rs.map((r) => r.dataset.inbox)")
        row = lambda what: pg.locator(f'[data-inbox="{what}"]')   # noqa: E731
        waiting = record.get(p, ids[low])["state"]
        row(mid).locator("input[type=text]").fill("not this one")
        assert not row(mid).locator('button[data-verb="deny"]').is_disabled()
        row(top).locator('button[data-verb="approve"]').click()
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()",
                             arg=row(top).element_handle(), timeout=20000)
        leave(pg)                                   # the reader gone, the answered row leaves and the rows shift up
        pg.wait_for_function(f"""() => !document.querySelector('[data-inbox="{top}"]')""", timeout=20000)
        pg.wait_for_timeout(3000)                   # and a refresh after it (every 2.5 s)
        assert row(mid).locator("input[type=text]").input_value() == "not this one"
        assert not row(mid).locator('button[data-verb="deny"]').is_disabled()
        assert row(low).locator("input[type=text]").input_value() == ""
        assert row(low).locator('button[data-verb="deny"]').is_disabled()
        row(mid).locator('button[data-verb="deny"]').click()
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()",
                             arg=row(mid).element_handle(), timeout=20000)
        got = record.get(p, ids[mid])
        assert got["state"] == "denied" and got.get("note") == "not this one", got
        assert record.get(p, ids[low])["state"] == waiting        # untouched
        assert not errors, errors
        b.close()


def alarms_coming(pg, gone: set) -> list[int]:
    """New alarms, one more with each answer of the diagram's graph, ahead of what waits on the owner and in its group
    (``waiting``): the rows below them pushed down and out, unless the list holds still. What is in ``gone`` is taken
    out of the answers (a request withdrawn)."""
    n = [0]

    def more(route):
        resp = route.fetch()
        body = resp.json()
        if isinstance(body, dict) and isinstance(body.get("attention"), list):
            n[0] += 1
            body["attention"] = [{"level": "bad", "what": f"alarm new-{i}", "waiting": True, "says": f"raised by the test ({i})"}
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
        pg.locator('[data-inbox^="action/"]').nth(2).wait_for(state="attached", timeout=20000)
        unfold(pg)                                                             # (4 and more: folded in one line)
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
        why = row.locator('input[aria-label^="Why"]')
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
        row.locator('input[aria-label^="Why"]').fill("not this week")
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
        assert [record.get(p, a["id"]).get("note") for a in reqs
                if record.get(p, a["id"])["state"] == "denied"] == ["not this week"]   # the reason typed, sent
        assert not errors, errors
        b.close()


def test_a_reason_typed_for_one_request_does_not_stay_for_the_request_below_it(three):
    """A reason typed in the top request, Deny, the reader gone: the next request moves up into the place, and its
    Why box is its own (empty, its Deny off until a reason is typed), so its Deny records its own note, not the
    first's."""
    from ergostat.actions import record
    url, p, reqs = three
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        pg.locator('[data-inbox^="action/"]').nth(2).wait_for(state="attached", timeout=20000)
        unfold(pg)                                                             # (4 waiting: folded in one line)
        pg.locator('[data-inbox^="action/"]').nth(2).wait_for(timeout=20000)
        first = pg.locator('[data-inbox^="action/"]').nth(0).get_attribute("data-inbox")
        row = pg.locator(f'[data-inbox="{first}"]')
        row.locator('input[aria-label^="Why"]').fill("not this week")
        row.locator('button[data-verb="deny"]').click()
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()", arg=row.element_handle(), timeout=20000)
        leave(pg)
        pg.wait_for_function(f"""() => !document.querySelector('[data-inbox="{first}"]')""", timeout=20000)
        boxes = pg.locator('[data-inbox^="action/"] input[aria-label^="Why"]')
        assert boxes.count() == 2 and [boxes.nth(i).input_value() for i in range(2)] == ["", ""]
        nxt = pg.locator('[data-inbox^="action/"]').nth(0)
        assert nxt.locator('button[data-verb="deny"]').is_disabled()
        nxt.locator('input[aria-label^="Why"]').fill("its own")
        nxt.locator('button[data-verb="deny"]').click()
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()", arg=nxt.element_handle(), timeout=20000)
        notes = sorted((record.get(p, a["id"]).get("note") or "") for a in reqs if record.get(p, a["id"])["state"] == "denied")
        assert notes == ["its own", "not this week"], notes
        assert not errors, errors
        b.close()


def waiting_entries(pg) -> list[dict]:
    """Each entry waiting on the owner in the side list: its text, its first line, its command box and its answers."""
    pg.locator("[data-inbox]").first.wait_for(state="attached", timeout=20000)   # held requests sit folded in housekeeping
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


def test_a_request_answered_from_the_keyboard_holds_the_list_with_the_pointer_off_it(site):
    """Answered with the keyboard, the pointer off the list: the disabled button does not drop the focus to the body.
    The focus goes to the row's reply, so the answered row stays in its place, saying so, until the reader leaves."""
    from ergostat.actions import record
    url, p, a = site
    what = f"action/{record.short(a['id'])}"
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        n = alarms_coming(pg, set())
        pg.goto(f"{url}/diagram?view=blocks")
        row = pg.locator(f'[data-inbox="{what}"]')
        row.wait_for(timeout=20000)
        off(pg)
        # several refreshes patched in first (the reader not in the list): the row's nodes kept, the handlers handed over
        pg.wait_for_function("() => document.querySelector('[data-row=\"alarm new-3\"]')", timeout=30000)
        unfold(pg)                                                             # (past 3 waiting: folded in one line)
        row.locator('input[aria-label^="Why"]').focus()
        pg.keyboard.type("not this week")
        pg.keyboard.press("Tab")                                             # past Approve to Deny, from the keyboard
        pg.keyboard.press("Tab")
        assert pg.evaluate("() => document.activeElement.dataset.verb") == "deny"
        pg.keyboard.press("Enter")
        pg.wait_for_function("(el) => el.querySelector('.inbox-act .note').textContent.trim()", arg=row.element_handle(), timeout=20000)
        got = record.get(p, a["id"])
        assert (got["state"], got.get("note")) == ("denied", "not this week")          # the reason typed, sent
        assert "denied" in row.locator(".inbox-act .note").inner_text()                 # the reply in the row seen
        top, seen = row.bounding_box()["y"], n[0]
        for _ in range(4):
            pg.wait_for_timeout(2000)
            assert row.count() == 1 and row.bounding_box()["y"] == top
            assert row.evaluate("(el) => el.contains(document.activeElement)")
        assert n[0] >= seen + 2, n                                           # (the answers kept coming)
        leave(pg)
        pg.wait_for_function(f"""() => !document.querySelector('[data-inbox="{what}"]')""", timeout=20000)
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
        row.locator('input[aria-label^="Why deny"]').fill("not on a Friday")
        row.locator('button[data-verb="deny"]').click()
        note = row.locator(".inbox-act .note")          # while the reader is in the list: said in the row held
        pg.wait_for_function("(el) => el.textContent.includes('Denied by you at')", arg=note.element_handle(), timeout=20000)
        assert note.locator('a[href="/item/ticket%2FSCRUM-2"]').count() == 1, note.inner_text()
        leave(pg)                                       # the list let go: the row drawn again as answered
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


def test_a_request_answered_here_and_held_again_under_its_id_waits_again(held_again):
    """lesson-5: a modelling request's id is fixed; approved here, then held again (its change turned away), it is
    listed again with its answers, and the earlier 'Approved by you' row no longer stands for it."""
    from ergostat.numbers import requests as rq
    url, p, (r, eid) = held_again
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{url}/diagram?view=blocks")
        row = pg.locator(f'[data-inbox="{eid}"]')
        row.wait_for(state="attached", timeout=20000)
        pg.locator(".housekeeping > summary").click()  # a modelling request is listed in the housekeeping (main's rule)
        row.wait_for(timeout=20000)
        row.locator('button[data-verb="approve"]').click()
        note = row.locator(".inbox-act .note")
        pg.wait_for_function("(el) => el.textContent.includes('Approved by you at')", arg=note.element_handle(), timeout=20000)
        leave(pg)
        done = pg.locator(f'[data-answered="{eid}"]')
        done.wait_for(timeout=20000)
        assert rq.stored(p)[r["id"]]["state"] == "open"
        for _ in range(2):                              # drawn again from a record where it no longer waits
            with pg.expect_response(lambda x: "/api/" in x.url, timeout=20000):
                pass
        assert done.count() == 1 and pg.locator(f'[data-inbox="{eid}"]').count() == 0
        rq.mark(p, rq.stored(p)[r["id"]], "held", "its change was turned away", tier="ai", tried={"ai": 2})
        row.wait_for(timeout=20000)                     # waiting again, under the same id, with its answers
        assert row.locator('button[data-verb="approve"]').count() == 1
        pg.wait_for_function(f"() => !document.querySelector('[data-answered=\"{eid}\"]')", timeout=20000)
        assert done.count() == 0 and row.count() == 1
        assert not errors, errors
        b.close()
