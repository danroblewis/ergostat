"""The projection workbench's page (docs/roadmap/projection-workbench.md; SPEC §5a, *The workbench*), in Chromium, on a
record of the EC2 simulator (tests/fixtures/ec2_stream.py, batch mode): a new projection made from the nav bar's +
through its five steps (what it is: its key and fields; the query, what each change added and dropped, and Accept all
right after its count, no suggestion left that takes nothing; the mapping: a value clicked into a field, a field made
from a pick, another kind mapped the same way, a path ignored in every kind's events; the review, and the panel on the
right: the residual with no 0 shown, the lifecycle, the distributions, one object's record and lifespan), saved with
its dated comments and reopened on its review; a projection with nothing unexplained (one check; the panel below the
steps on a narrow page); and an existing projection's drift, events of a new shape shown in its remainder.

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
    return pg.locator("[data-step='2'] .cm-content")


def number(pg, testid: str) -> int:
    return int(pg.locator(f"[data-testid={testid}]").inner_text().replace(",", ""))


def yaml_has(pg, text: str) -> None:
    pg.wait_for_function("(t) => document.querySelector('.wb-yaml .cm-content').textContent.includes(t)", arg=text, timeout=WAIT)


STATES = "pending, running, stopping, stopped, shutting-down, terminated"
CHANGE = "ec2-instance-state-change-notification"


def kind_box(pg, name: str):
    return pg.locator("details.wb-map", has=pg.locator("summary strong", has_text=name))


def test_a_new_projection_is_made_in_the_workbench_saved_and_reopened_on_its_review(browser, served):
    p, url = served
    pg = opened(browser, url + "/goals")
    pg.hover("#nav")
    pg.get_by_role("button", name="New projection").click()
    pg.get_by_label("The new projection's name").fill("instance")
    pg.keyboard.press("Enter")
    pg.wait_for_url("**/instance", timeout=WAIT)
    pg.locator("[data-step='5'] .wb-step-head").wait_for(timeout=WAIT)
    steps = pg.locator(".wb-step-head button").all_inner_texts()
    assert [s.split(" ", 1)[1] for s in steps] == ["What it is", "Query", "Kinds of event", "Mapping", "Review"]

    # 1. what it is: its key, one part a row (no quoting), and its fields
    for part in ("data.account", "data.region", "data.detail['instance-id']"):
        pg.get_by_label("The projection's key, a new part").fill(part)
        pg.keyboard.press("Enter")
    yaml_has(pg, "key: [data.account, data.region")
    for f in ("state", "instance_type"):
        pg.get_by_label("A new field's name").fill(f)
        pg.get_by_role("button", name="Add a field").click()
        pg.get_by_label(f"The name of {f}").wait_for(timeout=WAIT)
    pg.get_by_label("The values of state").fill(STATES)
    pg.keyboard.press("Enter")
    yaml_has(pg, "values: [pending")

    # 2. the query: its count, and what a change added and dropped
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
    # the newest events are folded; opened, a value clicked narrows the query by it
    assert not pg.locator("[data-step='2'] .wb-events").is_visible()
    pg.locator("[data-step='2'] .wb-newest > summary").click()
    pg.locator("[data-step='2'] .wb-events summary").first.click()
    pg.locator("[data-step='2'] button[data-path='[\"data\",\"source\"]']").first.click()
    pg.get_by_role("button", name="and data.source == 'aws.ec2'").click()
    pg.wait_for_function("() => document.querySelector(\"[data-step='2'] .cm-content\").textContent.endsWith(\"and data.source == 'aws.ec2'\")", timeout=WAIT)
    query_box(pg).fill("data.source == 'aws.ec2'")

    # right after the count: what the kinds it holds cover, and Accept all; then every event taken, no suggestion left
    line = pg.locator("[data-step='2'] [data-testid=accept-line]")
    pg.wait_for_function("() => /cover 100% of these events/.test(document.querySelector('[data-testid=accept-line]')?.textContent || '')", timeout=WAIT)
    assert pg.locator("[data-step='2'] .wb-count + [data-testid=accept-line]").count() == 1
    line.get_by_role("button", name="Accept all").click()
    pg.locator("[data-testid=all-taken]").wait_for(timeout=WAIT)                     # no 0 shown: a check
    pg.wait_for_function("() => /All events taken by \\d+ kinds/.test(document.querySelector('[data-testid=accept-line]')?.textContent || '')", timeout=WAIT)
    kinds = pg.locator("table[aria-label='Its kinds of event'] tbody tr")
    assert kinds.count() >= 5
    assert pg.locator("ul[aria-label='The remainder, by shape']").count() == 0          # no suggestion that takes nothing
    takes = [t.strip() for t in kinds.locator("td:nth-child(3)").all_inner_texts()]
    assert "0" not in takes and "" not in takes
    assert f"{CHANGE}:" in pg.locator(".wb-yaml .cm-content").inner_text()

    # 4. the mapping: a value clicked into a field; a new field made from the pick; the same mapping applied elsewhere
    change = kind_box(pg, CHANGE)
    change.locator(".wb-sample button[data-path='[\"data\",\"detail\",\"state\"]']").click(timeout=WAIT)
    change.locator(".wb-picked").get_by_role("button", name="state", exact=True).click()
    yaml_has(pg, "state: data.detail.state")
    change.locator(".wb-sample .jv-to", has_text="state").wait_for(timeout=WAIT)          # tagged with the field it fills
    change.locator(".wb-record").get_by_text("state").first.wait_for(timeout=WAIT)        # the record it makes
    change.locator(".wb-sample button[data-path='[\"data\",\"account\"]']").click()
    assert change.get_by_label("The new field's name").input_value() == "account"
    assert change.get_by_label("The new field's type").input_value() == "text"
    change.get_by_role("button", name="Create and map").click()
    yaml_has(pg, "account: data.account")
    assert "account: {type: text}" in pg.locator(".wb-yaml .cm-content").inner_text()
    run = kind_box(pg, "runinstances")
    same = run.locator("[data-testid=same-runinstances]")
    same.wait_for(timeout=WAIT)
    assert "data.account → account" in " ".join(same.inner_text().split())
    same.get_by_role("button", name="Apply").click()
    pg.wait_for_function("() => /runinstances:[\\s\\S]*account: data.account/.test(document.querySelector('.wb-yaml .cm-content').textContent)", timeout=WAIT)
    # ignore a path: hidden in every kind's event, written as ignore:
    assert pg.locator(".wb-sample button[data-path='[\"type\"]']").count() >= 2
    change.locator(".wb-sample button[data-path='[\"type\"]']").click()
    change.get_by_role("button", name="ignore this path").click()
    yaml_has(pg, "ignore: [type]")
    pg.wait_for_function("() => document.querySelectorAll(\".wb-sample button[data-path='[\\\"type\\\"]']\").length === 0", timeout=WAIT)
    change.get_by_role("button", name="show ignored (1)").click()
    assert change.locator(".wb-sample button[data-path='[\"type\"]']").count() == 1
    # an expression typed for a field it does not tell yet, and a key of its own
    run.get_by_label("runinstances: tell another field").select_option("instance_type")
    pg.get_by_label("runinstances: instance_type").fill("data.detail.requestParameters.instanceType")
    pg.keyboard.press("Enter")
    run.get_by_role("button", name="Its ids are elsewhere: give it its own").click()   # starts from the projection's
    pg.get_by_label("The key of runinstances, part 3").fill("each(data.detail.responseElements.instancesSet.items, 'instanceId')")
    pg.keyboard.press("Enter")

    # 5. the review, and the panel on the right: the residual (no 0 shown), the lifecycle, the fields, one object
    side = pg.locator("aside.wb-side")
    pg.locator("[data-testid=lifecycle-state]").wait_for(timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('.wb-side .wb-dist h4')].some((h) => h.textContent.includes('instance_type'))", timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('[data-testid=lifecycle-state]').textContent.includes('running')", timeout=WAIT)
    assert number(pg, "review-objects") > 5
    residual = side.locator("ul[aria-label='The residual']").inner_text()
    assert "no key" in residual and "remainder" not in residual                          # its 0 not shown
    unexpl = pg.locator("[data-testid=unexplained]").inner_text()
    assert "Unexplained" in unexpl and " 0 " not in unexpl
    assert pg.locator("ul[aria-label='Unmapped paths'] li").count() > 0                  # what is left to decide
    side.locator(".wb-examples button.mono").first.click()
    side.locator("table[aria-label=\"The object's timeline\"] tbody tr").first.wait_for(timeout=WAIT)
    assert "pending" in side.locator("table[aria-label=\"The object's timeline\"]").inner_text()
    assert "state" in side.locator("ul[aria-label=\"The object's record\"]").inner_text()
    assert side.locator("[data-testid=state-path]").inner_text().startswith("(new) → pending")
    box = side.bounding_box()
    assert box and box["x"] > 700                                                        # on the right

    # Save: the YAML written with its dates; reopened, it lands on its review
    assert "instance:" not in p.model.path.read_text()
    pg.get_by_role("button", name="Save", exact=True).click()
    pg.get_by_role("button", name="Edit", exact=True).wait_for(timeout=WAIT)
    text = p.model.path.read_text()
    assert "  instance:\n" in text and "# updated" in text and "state: data.detail.state" in text and "ignore: [type]" in text
    pg.get_by_role("button", name="Edit", exact=True).click()
    pg.locator("[data-step='5'].wb-step.open [data-testid=review-objects]").wait_for(timeout=WAIT)
    assert pg.locator("[data-step='2'].open").count() == 0
    assert settled(pg) == []
    pg.close()


EXPLAINED = """\
name: wb
projections:
  instance:
    query: data['detail-type'] == 'EC2 Instance State-change Notification'
    key: [data.account, data.region, "data.detail['instance-id']"]
    fields:
      state: {values: [pending, running, stopping, stopped, shutting-down, terminated]}
    events:
      state-change:
        when: "true"
        state: data.detail.state
"""


@pytest.mark.parametrize("served", [EXPLAINED], indirect=True)
def test_nothing_unexplained_is_one_check_and_a_narrow_page_puts_the_panel_below(browser, served):
    p, url = served
    pg = opened(browser, url + "/instance")
    pg.get_by_role("button", name="Edit", exact=True).first.click()
    pg.locator("[data-testid=residual-ok]").wait_for(timeout=WAIT)
    assert pg.locator("ul[aria-label='The residual']").count() == 0
    assert "Nothing unexplained" in pg.locator("[data-testid=unexplained]").inner_text()
    pg.set_viewport_size({"width": 600, "height": 900})
    pg.wait_for_timeout(300)
    main, side = pg.locator(".wb-main").bounding_box(), pg.locator("aside.wb-side").bounding_box()
    assert side["y"] >= main["y"] + main["height"] - 1
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
    pg.locator("[data-step='5'].open [data-testid=review-objects]").wait_for(timeout=WAIT)
    rem = pg.locator("ul[aria-label='The residual'] li", has_text="remainder")
    assert rem.locator(".wb-kind-n").first.inner_text() == "3"
    rem.locator("summary").click()
    assert "Spot Instance Interruption" in rem.inner_text()
    assert "3 remainder" in pg.locator("[data-testid=unexplained]").inner_text()
    pg.locator("[data-step='3'] .wb-step-head button").click()             # step 3 shows it too, acceptable as a kind
    assert pg.locator("[data-testid=remainder-count]").inner_text() == "3"
    assert "Spot Instance Interruption" in pg.locator("ul[aria-label='The remainder, by shape']").inner_text()
    assert settled(pg) == []
    pg.close()
