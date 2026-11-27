"""The projection workbench's page (docs/roadmap/projection-workbench.md; SPEC §5a, *The workbench*), in Chromium, on a
record of the EC2 simulator (tests/fixtures/ec2_stream.py, batch mode): a new projection made from the nav bar's +
through its four steps (the query and what each change added and dropped, kinds of event accepted, fields declared and
mapped, a value clicked into a field, the review's distributions, lifecycle, residual and one object's timeline),
saved with its dated comments and reopened on its review; and an existing projection's drift, events of a new shape
shown in its remainder.

    uv run --with playwright==1.63.0 python -m pytest -q tests/test_projection_workbench_page.py
"""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import web
from ergostat.store import Project
from tests.fixtures.ec2_stream import Fleet
from tests.test_react_pages import WAIT, browser, opened, settled  # noqa: F401  (the browser fixture)
from tests.test_react_pages import pytestmark  # noqa: F401  (skipped when the page is not built)

pytest.importorskip("playwright.sync_api")


def ec2_project(d: Path, body: str = "name: wb\n") -> Project:
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(body))
    p = Project(mdl.load(d))
    start = time.time() - 3 * 86400
    f = Fleet(7, 12, start)
    evs = f.deliver(f.advance(start + 2 * 86400), float("inf"))
    t = time.time() - len(evs) - 10
    p.events.add_many([{"type": "aws.eventbridge", "data": e, "at": t + i} for i, e in enumerate(evs)])
    return p


@pytest.fixture
def served(tmp_path, request):
    p = ec2_project(tmp_path / "wb", getattr(request, "param", "name: wb\n"))
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def query_box(pg):
    return pg.locator("[data-step='1'] .cm-content")


def number(pg, testid: str) -> int:
    return int(pg.locator(f"[data-testid={testid}]").inner_text().replace(",", ""))


STATES = "pending, running, stopping, stopped, shutting-down, terminated"


def test_a_new_projection_is_made_in_the_workbench_saved_and_reopened_on_its_review(browser, served):
    p, url = served
    pg = opened(browser, url + "/goals")
    pg.hover("#nav")
    pg.get_by_role("button", name="New projection").click()
    pg.get_by_label("The new projection's name").fill("instance")
    pg.keyboard.press("Enter")
    pg.wait_for_url("**/instance", timeout=WAIT)

    # 1. the query: its count, and what a change added and dropped
    query_box(pg).wait_for(timeout=WAIT)
    query_box(pg).fill("data.source == 'aws.ec2'")
    pg.wait_for_function("() => document.querySelector('[data-testid=query-total]')?.textContent.length > 0", timeout=WAIT)
    total = number(pg, "query-total")
    assert total > 100 and "index" in pg.locator("[data-testid=query-how]").inner_text()
    query_box(pg).fill("data.source == 'aws.ec2' and data.detail.eventName != 'CreateTags'")
    pg.locator("[data-testid=query-compare]").wait_for(timeout=WAIT)
    pg.wait_for_function(f"() => +document.querySelector('[data-testid=query-total]').textContent.replace(/,/g, '') < {total}", timeout=WAIT)
    said = pg.locator("[data-testid=query-compare]").inner_text()
    assert "+0" in said and f"−{total - number(pg, 'query-total')}" in said
    # a value clicked in an event narrows the query by it
    pg.locator("[data-step='1'] .wb-events summary").first.click()
    pg.locator("[data-step='1'] button[data-path='[\"data\",\"source\"]']").first.click()
    pg.get_by_role("button", name="and data.source == 'aws.ec2'").click()
    pg.wait_for_function("() => document.querySelector(\"[data-step='1'] .cm-content\").textContent.endsWith(\"and data.source == 'aws.ec2'\")", timeout=WAIT)
    query_box(pg).fill("data.source == 'aws.ec2'")

    # 2. the kinds of event: every suggestion accepted, the remainder emptied
    pg.get_by_role("button", name="Accept all").click()
    pg.wait_for_function("() => document.querySelector('[data-testid=remainder-count]')?.textContent === '0'", timeout=WAIT)
    kinds = pg.locator("table[aria-label='Its kinds of event'] tbody tr")
    assert kinds.count() >= 5
    yaml_box = pg.locator(".wb-yaml .cm-content")
    assert "ec2-instance-state-change-notification:" in yaml_box.inner_text()

    # 3. the mapping: a key, fields declared, a value clicked into a field, an expression typed
    for part in ("data.account", "data.region", "data.detail['instance-id']"):   # one part a row: no quoting
        pg.get_by_label("The projection's key, a new part").fill(part)
        pg.keyboard.press("Enter")
    pg.wait_for_function("() => document.querySelector('.wb-yaml .cm-content').textContent.includes('key: [data.account, data.region')", timeout=WAIT)
    for f in ("state", "instance_type"):
        pg.get_by_label("A new field's name").fill(f)
        pg.get_by_role("button", name="Add a field").click()
        pg.get_by_label(f"The name of {f}").wait_for(timeout=WAIT)
    pg.get_by_label("The values of state").fill(STATES)
    pg.keyboard.press("Enter")
    pg.wait_for_function("() => document.querySelector('.wb-yaml .cm-content').textContent.includes('values: [pending')", timeout=WAIT)
    change = pg.locator("details.wb-map", has=pg.locator("summary strong", has_text="ec2-instance-state-change-notification"))
    change.locator("button[data-path='[\"data\",\"detail\",\"state\"]']").first.click(timeout=WAIT)
    change.locator(".wb-picked").get_by_role("button", name="state", exact=True).click()
    pg.wait_for_function("() => document.querySelector('.wb-yaml .cm-content').textContent.includes('state: data.detail.state')", timeout=WAIT)
    launch = pg.get_by_label("runinstances: instance_type")
    launch.fill("data.detail.requestParameters.instanceType")
    pg.keyboard.press("Enter")
    run = pg.locator("details.wb-map", has=pg.locator("summary strong", has_text="runinstances"))
    run.get_by_role("button", name="Its ids are elsewhere: give it its own").click()   # starts from the projection's
    pg.get_by_label("The key of runinstances, part 3").fill("each(data.detail.responseElements.instancesSet.items, 'instanceId')")
    pg.keyboard.press("Enter")

    # 4. the review: distributions, the lifecycle, the residual, one object's timeline
    review = pg.locator("[data-step='4']")
    pg.locator("[data-testid=lifecycle-state]").wait_for(timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('.wb-dist h4')].some((h) => h.textContent.includes('instance_type'))", timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('[data-testid=lifecycle-state]').textContent.includes('running')", timeout=WAIT)
    assert number(pg, "review-objects") > 5
    residual = review.locator("ul[aria-label='The residual']").inner_text()
    assert "no key" in residual and "remainder" in residual
    assert "Unexplained" in pg.locator("[data-testid=unexplained]").inner_text()        # the API calls without a key
    review.locator("p.small button.mono").first.click()
    pg.locator("table[aria-label=\"The object's timeline\"] tbody tr").first.wait_for(timeout=WAIT)
    assert "pending" in review.locator("table[aria-label=\"The object's timeline\"]").inner_text()

    # Save: the YAML written with its dates; reopened, it lands on its review
    assert "instance:" not in p.model.path.read_text()
    pg.get_by_role("button", name="Save", exact=True).click()
    pg.get_by_role("button", name="Edit", exact=True).wait_for(timeout=WAIT)
    text = p.model.path.read_text()
    assert "  instance:\n" in text and "# updated" in text and "state: data.detail.state" in text
    pg.get_by_role("button", name="Edit", exact=True).click()
    pg.locator("[data-step='4'].wb-step.open [data-testid=review-objects]").wait_for(timeout=WAIT)
    assert pg.locator("[data-step='1'].open").count() == 0
    assert settled(pg) == []
    pg.close()


DRIFTING = """\
name: wb
projections:
  instance:
    query: data.source == 'aws.ec2'
    key: [data.account, data.region, "data.detail['instance-id']"]
    fields:
      state: {values: [pending, running, stopping, stopped, shutting-down, terminated]}
    events:
      state-change:
        when: data['detail-type'] == 'EC2 Instance State-change Notification'
        state: data.detail.state
      api-call:
        when: data['detail-type'] == 'AWS API Call via CloudTrail'
"""


@pytest.mark.parametrize("served", [DRIFTING], indirect=True)
def test_an_existing_projection_reopened_shows_events_of_a_new_shape_in_its_remainder(browser, served):
    p, url = served
    for i in range(3):                                     # a shape the definition was not written for
        p.events.add("aws.eventbridge", data={
            "source": "aws.ec2", "detail-type": "EC2 Spot Instance Interruption Warning", "account": "111111111111",
            "region": "us-east-1", "detail": {"instance-id": f"i-spot{i}", "instance-action": "terminate"}})
    pg = opened(browser, url + "/instance")
    pg.get_by_role("button", name="Edit", exact=True).first.click()
    pg.locator("[data-step='4'].open [data-testid=review-objects]").wait_for(timeout=WAIT)
    rem = pg.locator("ul[aria-label='The residual'] li", has_text="remainder")
    assert rem.locator(".wb-kind-n").first.inner_text() == "3"
    rem.locator("summary").click()
    assert "Spot Instance Interruption" in rem.inner_text()
    assert "3 remainder" in pg.locator("[data-testid=unexplained]").inner_text()
    pg.locator("[data-step='2'] .wb-step-head button").click()             # step 2 shows it too, acceptable as a kind
    assert pg.locator("[data-testid=remainder-count]").inner_text() == "3"
    assert "Spot Instance Interruption" in pg.locator("ul[aria-label='The remainder, by shape']").inner_text()
    assert settled(pg) == []
    pg.close()
