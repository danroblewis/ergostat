"""The Inbox page (/inbox, a default dashboard: ergostat.inbox's list page, its summary, states and list panels): exactly
what `ergostat inbox` lists, each a waiting item of ergostat.inbox drawn as a card answered on the page (approve a change, deny an action with a reason, a person's number done); the header's "N for
you" counts those decisions only and links here; a failing sensor is a fault, never "for you"."""

from __future__ import annotations

import pytest

from ergostat import web
from ergostat.inbox import entries
from ergostat.web import server as ws

from tests.test_inbox import MODEL, project, seed
from tests.test_react_pages import WAIT, browser, opened, settled  # noqa: F401  (browser: the module's fixture)

pytestmark = pytest.mark.skipif(not (ws.STATIC / "app" / "index.html").is_file(), reason="the React page is not built")


PROBE = """auxiliaries:
  probe:
    unit: "1"
    sensor:
      run: echo 1
      every: 1h
"""


@pytest.fixture()
def site(tmp_path):
    p, snap = project(tmp_path, MODEL + PROBE)
    seed(p, snap)
    for _ in range(3):                                   # a fault: the probe's sensor failing, three reads in a row
        p.events.add("sensor.failed", item="probe.main", source="ergostat", data={"why": "it printed nothing"})
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def test_the_inbox_lists_what_ergostat_inbox_lists_and_the_header_links_there(site, browser):
    p, url = site
    ids = [e["id"] for e in entries.entries(p)]
    pg = opened(browser, url + "/overview")
    pg.wait_for_selector("#waits", timeout=WAIT)
    assert pg.locator("#waits").inner_text() == f"{len(ids)} for you"            # decisions only: not the failing sensor
    assert pg.locator("#waits").get_attribute("href").endswith("/inbox")
    assert pg.locator("#sensors-failing").inner_text() == "1 sensor failing"
    assert "around=" in pg.locator("#sensors-failing").get_attribute("href")     # the diagram around it, not the side list
    assert pg.locator("#nav [data-inbox-count]").inner_text().strip() == str(len(ids))
    pg.locator("#waits").click()
    pg.wait_for_selector(".panel-kind-item-list .wait-card", timeout=WAIT)          # the cards: the list's waiting items
    assert pg.locator(".wait-card").evaluate_all("xs => xs.map(x => x.dataset.row)") == ids
    summary = pg.locator(".panel-kind-projection-summary .projection-bar[data-projection='ergostat.inbox']")
    assert summary.locator("h1").inner_text().startswith("Inbox")                 # the page's heading: a panel
    assert f"{len(ids)} not finished" in summary.inner_text()                      # how many wait
    assert pg.locator(".panel-kind-projection-states .stbox[data-state=waiting] .n").inner_text() == str(len(ids))
    assert pg.locator('[data-row="sensor probe.main"]').count() == 0              # a fault is not on the Inbox
    person = pg.locator('.wait-card[data-kind="person"]')
    assert "Jobs done, along reviewed (number)" in person.inner_text()
    assert settled(pg) == []
    pg.close()


def test_each_is_answered_on_the_page(site, browser):
    p, url = site
    es = {e["kind"]: e for e in entries.entries(p)}
    pg = opened(browser, url + "/inbox")
    pg.wait_for_selector(".wait-card", timeout=WAIT)

    change = pg.locator(f'[data-row="{es["change"]["id"]}"]')                    # approve a change: written
    change.locator('button[data-answer="approve"]').click()
    change.locator("[data-answered]").wait_for(timeout=WAIT)
    assert "Approved" in change.locator("[data-answered]").inner_text()
    assert p.events.query(type="ergostat.model-change.accepted")

    action = pg.locator(f'[data-row="{es["action"]["id"]}"]')                    # deny an action, with why
    action.locator('button[data-answer="deny"]').click()
    action.locator("[data-deny-note]").fill("not today")
    action.locator("button[data-confirm]").click()
    action.locator("[data-answered]").wait_for(timeout=WAIT)
    [denied] = [a for a in p.events.query(n=None) if a["type"] == "ergostat.action.denied"]
    assert denied["data"].get("note") == "not today"

    person = pg.locator(f'[data-row="{es["person"]["id"]}"]')                    # a person's number, done
    assert person.locator('button[data-answer="done"]').is_disabled()
    person.locator("[data-done-n]").fill("4")
    person.locator('button[data-answer="done"]').click()
    person.locator("[data-answered]").wait_for(timeout=WAIT)
    [ran] = p.events.query(type="agent.ran", item="reviewer")
    assert ran["data"]["done"] == 4.0
    pg.close()


def test_nothing_waiting_says_so(tmp_path, browser):
    p, _ = project(tmp_path)
    server, url = web.serve(p, 0)
    try:
        pg = opened(browser, url + "/inbox")
        pg.wait_for_selector("#may-do", timeout=WAIT)
        assert pg.locator("#may-do").inner_text() == "Nothing waits for you."
        assert pg.locator("#waits").count() == 0
        pg.close()
    finally:
        server.shutdown()
        server.server_close()


def test_a_past_decision_is_listed_below_with_its_answer(site, browser):
    from ergostat.inbox import answer
    p, url = site
    es = {e["kind"]: e for e in entries.entries(p)}
    answer.answer(p, p.model.spec, es["advise"]["id"], "deny", note="not this week")
    pg = opened(browser, url + "/inbox")
    pg.wait_for_selector(".wait-card", timeout=WAIT)
    pg.locator(".panel-kind-projection-states .projection-states[data-projection='ergostat.inbox'] .stbox").first.wait_for(
        timeout=WAIT)                                                             # its graph of states: a panel above
    hist = pg.locator(".panel-kind-item-list")
    row = hist.locator("tr", has_text="not this week")
    row.wait_for(timeout=WAIT)
    assert "denied" in row.inner_text() and "owner" in row.inner_text()
    assert pg.locator(f'.wait-card[data-row="{es["advise"]["id"]}"]').count() == 0   # no longer waiting above
    assert settled(pg) == []
    pg.close()
