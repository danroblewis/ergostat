"""The projection workbench's page (docs/roadmap/projection-workbench.md; SPEC §5a, *The workbench*), in Chromium, on a
record of the EC2 simulator (tests/fixtures/ec2_stream.py, batch mode): a new projection made from the nav bar's +
through its five steps (its key set at the top of the panel on the right before any mapping, a new field made there;
what it is: its fields, and the key picked from them in order; the query, what each change added and dropped, and Accept all
right after its count, no suggestion left that takes nothing; the mapping: each kind's key solved from its key fields
(✓ or ✗ a part, a ✗ clicked to map it), a value hovered opening a floating panel that goes when the pointer leaves, a
value clicked keeping it, a field made from a pick, another kind mapped the same way at once and one taken back, a path
ignored in every kind's events; the review, and the panel on the right: its objects stepped with ‹ ›, the lifecycle,
the distributions, the residual at the bottom with no 0 shown), saved with its dated comments and reopened on its
review; a kind folding itself once every path is mapped, Enter and Escape on the floating panel, the objects stepped
and found, and a reload keeping the draft; a new projection surviving a change to the address (the bug that lost a
draft: a search dropped the history state saying it was new) and a reload; a projection with nothing unexplained (one
check; the panel below the steps on a narrow page); and an existing projection's drift, events of a new shape shown in
its remainder; and the residual's groups (no key, refused, a possible split) opened in the mapping step, their events
there to map until each is fixed.

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

    # its key, at the top of the panel on the right, set before anything is mapped: a new field made there
    side = pg.locator("aside.wb-side")
    assert side.locator("section.wb-keyside").bounding_box()["y"] <= side.bounding_box()["y"] + 40
    side.get_by_label("A new key field's name").fill("account")
    side.get_by_role("button", name="Add to the key").click()
    yaml_has(pg, "key: account")
    assert "account: {type: text}" in pg.locator(".wb-yaml .cm-content").inner_text()

    # 1. what it is: its fields, and the key picked from them, in order
    for f in ("state", "instance_type", "region", "instance_id"):
        pg.get_by_label("A new field's name").fill(f)
        pg.get_by_role("button", name="Add a field").click()
        pg.get_by_label(f"The name of {f}").wait_for(timeout=WAIT)
    pg.get_by_label("The values of state").fill(STATES)
    pg.keyboard.press("Enter")
    yaml_has(pg, "values: [pending")
    for f in ("instance_id", "region"):
        pg.get_by_label("Add a field to the key").select_option(f)
    yaml_has(pg, "key: [account, instance_id, region]")
    pg.get_by_role("button", name="Move region up").click()
    yaml_has(pg, "key: [account, region, instance_id]")
    assert pg.locator("ol[aria-label=\"The projection's key\"] li code").all_inner_texts() == ["account", "region", "instance_id"]

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

    assert pg.locator("[data-testid^=key-missing-]").count() >= 5     # each kind that doesn't tell the key says so, on the left

    # 4. the mapping: a value hovered opens a floating panel by it, gone once the pointer leaves; a value clicked keeps it
    change = kind_box(pg, CHANGE)
    state_value = change.locator(".wb-sample button[data-path='[\"data\",\"detail\",\"state\"]']")
    state_value.hover(timeout=WAIT)
    pop = change.locator(".wb-pop")
    pop.wait_for(timeout=WAIT)
    assert pg.locator(".wb-picked:not(.wb-pop)").count() == 0                            # no bar above the event
    pg.mouse.move(5, 5)
    pop.wait_for(state="detached", timeout=WAIT)
    state_value.click()
    pop.wait_for(timeout=WAIT)
    box = state_value.bounding_box()
    pg.mouse.move(box["x"] - 200, box["y"] - 80)                                          # away, never into the panel
    pg.wait_for_timeout(600)
    assert pop.count() == 1                                                               # clicked: it stays
    pop.get_by_role("button", name="state", exact=True).click()
    yaml_has(pg, "state: data.detail.state")
    change.locator(".wb-sample .jv-to", has_text="state").wait_for(timeout=WAIT)          # tagged with the field it fills
    change.locator(".wb-record").get_by_text("Keyed to nothing").wait_for(timeout=WAIT)          # no key yet
    change.locator(".wb-sample button[data-path='[\"data\",\"id\"]']").click()
    assert pop.get_by_label("The new field's name").input_value() == "id"
    assert pop.get_by_label("The new field's type").input_value() == "text"
    assert pop.get_by_role("button", name="its key part").count() == 0                  # a key field is a field
    pop.get_by_role("button", name="Create and map").click()
    yaml_has(pg, "id: data.id")
    assert "id: {type: text}" in pg.locator(".wb-yaml .cm-content").inner_text()
    # its key, solved from the key's fields: a ✗ for each it does not tell, clicked to map it, then a ✓
    key = change.locator(f"[data-testid=key-{CHANGE}]")
    assert " ".join(key.inner_text().split()) == "account ✗ not told · region ✗ not told · instance_id ✗ not told"
    change.locator(".wb-sample button[data-path='[\"data\",\"account\"]']").click()
    pop.get_by_role("button", name="account", exact=True).click()
    yaml_has(pg, "account: data.account")
    key.get_by_text("account ✓ data.account").wait_for(timeout=WAIT)
    for f, expr in (("region", "data.region"), ("instance_id", "data.detail['instance-id']")):
        key.get_by_role("button", name=f"Map {f} for {CHANGE}").click()
        box = pg.get_by_label(f"{CHANGE}: {f}")
        pg.wait_for_function("(l) => document.activeElement?.getAttribute('aria-label') === l", arg=f"{CHANGE}: {f}", timeout=WAIT)
        box.fill(expr)
        pg.keyboard.press("Enter")
    pg.wait_for_function("(t) => document.querySelector(t).textContent.replace(/\\s+/g, ' ').includes(\"instance_id ✓ data.detail['instance-id']\")",
                         arg=f"[data-testid=key-{CHANGE}]", timeout=WAIT)
    assert "✗" not in key.inner_text()
    change.locator(".wb-record").get_by_text("state").first.wait_for(timeout=WAIT)        # the record it makes, keyed
    # what it maps by a plain path, mapped in the other kinds at once (no Apply), each a × to take back
    run = kind_box(pg, "runinstances")
    same = run.locator("[data-testid=same-runinstances]")
    same.wait_for(timeout=WAIT)
    pg.wait_for_function("() => /data\\.region → region/.test(document.querySelector('[data-testid=same-runinstances]').textContent)", timeout=WAIT)
    said = " ".join(same.inner_text().split())
    assert f"Mapped the same way as {CHANGE}" in said and "data.account → account" in said
    assert same.get_by_role("button", name="Apply").count() == 0
    pg.wait_for_function("() => /runinstances:[\\s\\S]*account: data.account/.test(document.querySelector('.wb-yaml .cm-content').textContent)", timeout=WAIT)
    assert run.get_by_label("runinstances: id").input_value() == "data.id"
    same.get_by_role("button", name="Unmap id for runinstances").click()
    pg.wait_for_function("() => !/data\\.id → id/.test(document.querySelector('[data-testid=same-runinstances]').textContent)", timeout=WAIT)
    pg.wait_for_timeout(1000)
    assert run.get_by_label("runinstances: id", exact=True).count() == 0                  # taken back, not mapped again
    # ignore a path: hidden in every kind's event, written as ignore:
    assert pg.locator(".wb-sample button[data-path='[\"type\"]']").count() >= 2
    change.locator(".wb-sample button[data-path='[\"type\"]']").click()
    pop.get_by_role("button", name="ignore this path").click()
    yaml_has(pg, "ignore: [type]")
    pg.wait_for_function("() => document.querySelectorAll(\".wb-sample button[data-path='[\\\"type\\\"]']\").length === 0", timeout=WAIT)
    change.get_by_role("button", name="show ignored (1)").click()
    assert change.locator(".wb-sample button[data-path='[\"type\"]']").count() == 1
    # an expression typed for a field it does not tell yet, and its key's last part: each(...), one object a launch
    run.get_by_label("runinstances: tell another field").select_option("instance_type")
    pg.get_by_label("runinstances: instance_type").fill("data.detail.requestParameters.instanceType")
    pg.keyboard.press("Enter")
    run_key = run.locator("[data-testid=key-runinstances]")
    run_key.get_by_role("button", name="Map instance_id for runinstances").click()
    pg.get_by_label("runinstances: instance_id").fill("each(data.detail.responseElements.instancesSet.items, 'instanceId')")
    pg.keyboard.press("Enter")
    run_key.get_by_text("instance_id ✓ each(").wait_for(timeout=WAIT)

    # 5. the review, and the panel on the right: its objects one at a time, the lifecycle, the fields, the residual (no
    # 0 shown) at the bottom
    pg.locator("[data-testid=lifecycle-state]").wait_for(timeout=WAIT)
    pg.wait_for_function("() => [...document.querySelectorAll('.wb-side .wb-dist h4')].some((h) => h.textContent.includes('instance_type'))", timeout=WAIT)
    pg.wait_for_function("() => document.querySelector('[data-testid=lifecycle-state]').textContent.includes('running')", timeout=WAIT)
    assert number(pg, "review-objects") > 5
    residual = side.locator("ul[aria-label='The residual']").inner_text()
    assert "no key" in residual and "remainder" not in residual                          # its 0 not shown
    side.locator("ul[aria-label='The residual'] li", has_text="no key").locator("summary").click()
    assert "tells no instance_id" in side.locator("ul[aria-label='No key, by kind']").inner_text()
    unexpl = pg.locator("[data-testid=unexplained]").inner_text()
    assert "Unexplained" in unexpl and " 0 " not in unexpl
    assert pg.locator("ul[aria-label='Unmapped paths'] li").count() > 0                  # what is left to decide
    first = side.locator("[data-testid=object-key]")
    first.wait_for(timeout=WAIT)
    k1 = first.inner_text()
    assert side.locator("[data-testid=object-at]").inner_text().startswith("1 of ")
    side.get_by_role("button", name="The next object").click()
    pg.wait_for_function("(k) => document.querySelector('[data-testid=object-key]')?.textContent !== k", arg=k1, timeout=WAIT)
    assert side.locator("[data-testid=object-at]").inner_text().startswith("2 of ")
    side.locator("table[aria-label=\"The object's timeline\"] tbody tr").first.wait_for(timeout=WAIT)
    side.get_by_role("button", name="The previous object").click()
    pg.wait_for_function("(k) => document.querySelector('[data-testid=object-key]')?.textContent === k", arg=k1, timeout=WAIT)
    side.locator("table[aria-label=\"The object's timeline\"] tbody tr").first.wait_for(timeout=WAIT)
    assert "pending" in side.locator("table[aria-label=\"The object's timeline\"]").inner_text()
    assert "state" in side.locator("ul[aria-label=\"The object's record\"]").inner_text()
    assert side.locator("[data-testid=state-path]").inner_text().startswith("(new) → pending")
    box = side.bounding_box()
    assert box and box["x"] > 700                                                        # on the right
    order = [side.locator(x).first.bounding_box()["y"] for x in
             ("section.wb-keyside", "section.wb-objects", ".wb-dist", ".wb-residual-h")]
    assert order == sorted(order)                                                        # key, objects, fields, residual

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
    key: [account, region, instance_id]
    fields:
      state: {values: [pending, running, stopping, stopped, shutting-down, terminated]}
      account: text
      region: text
      instance_id: text
    events:
      state-change:
        when: "true"
        state: data.detail.state
        account: data.account
        region: data.region
        instance_id: data.detail['instance-id']
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
    key: [account, region, instance_id]
    fields:
      state: {values: [pending, running, stopping, stopped, shutting-down, terminated]}
      account: text
      region: text
      instance_id: text
    events:
      state-change:
        when: data['detail-type'] == 'EC2 Instance State-change Notification'
        state: data.detail.state
        account: data.account
        region: data.region
        instance_id: data.detail['instance-id']
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


THINGS = """\
name: wb
projections:
  thing:
    query: type == 'thing.made'
    key: id
    ignore: [type]
    fields:
      id: text
      n: integer
    events:
      made:
        when: "true"
        id: data.id
"""


@pytest.fixture
def things(tmp_path):
    d = tmp_path / "wb"
    d.mkdir(parents=True)
    (d / "ergostat.yaml").write_text(THINGS)
    p = Project(mdl.load(d))
    for i, k in enumerate("abc"):
        p.events.add("thing.made", data={"id": k, "n": i + 1})
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def test_a_kind_folds_once_every_path_is_mapped_the_objects_are_stepped_and_a_reload_keeps_the_draft(browser, things):
    p, url = things
    pg = opened(browser, url + "/thing")
    pg.get_by_role("button", name="Edit", exact=True).first.click()
    pg.locator("[data-step='4'] .wb-step-head button").click()
    made = kind_box(pg, "made")
    n_value = made.locator(".wb-sample button[data-path='[\"data\",\"n\"]']")
    n_value.wait_for(timeout=WAIT)
    assert made.get_attribute("open") is not None and "1 path left" in made.locator("summary").inner_text()
    # Enter on a value opens the panel too; Escape closes it
    n_value.focus()
    pg.keyboard.press("Enter")
    made.locator(".wb-pop").wait_for(timeout=WAIT)
    pg.keyboard.press("Escape")
    made.locator(".wb-pop").wait_for(state="detached", timeout=WAIT)
    # hovered, then into the panel (it stays), a field picked there: every path mapped, the kind folds with a ✓
    n_value.hover()
    pop = made.locator(".wb-pop")
    pop.wait_for(timeout=WAIT)
    pop.hover()
    pg.wait_for_timeout(400)
    pop.get_by_role("button", name="n", exact=True).click()
    yaml_has(pg, "n: data.n")
    pg.locator("[data-testid=done-made]").wait_for(timeout=WAIT)
    pg.wait_for_function("() => !document.querySelector('details.wb-map').open", timeout=WAIT)
    made.locator("summary").click()                                                      # it opens again
    assert made.get_attribute("open") is not None

    # the objects, stepped through with › : each its record and change history
    side = pg.locator("aside.wb-side")
    side.locator("[data-testid=object-key]", has_text="a").wait_for(timeout=WAIT)
    assert side.locator("[data-testid=object-at]").inner_text() == "1 of 3"
    side.get_by_role("button", name="The next object").click()
    side.locator("[data-testid=object-key]", has_text="b").wait_for(timeout=WAIT)
    pg.wait_for_function("() => /n\\s*2/.test(document.querySelector(\"ul[aria-label=\\\"The object's record\\\"]\")?.textContent || '')", timeout=WAIT)
    hist = side.locator("table[aria-label=\"The object's timeline\"]").inner_text()
    assert "made" in hist and "→ 2" in hist
    side.get_by_label("Find an object by its key").fill("c")
    pg.keyboard.press("Enter")
    side.locator("[data-testid=object-key]", has_text="c").wait_for(timeout=WAIT)
    assert side.get_by_role("button", name="The next object").is_disabled()

    # a reload keeps the draft: the page opens editing, the mapping as it was
    pg.reload()
    pg.locator(".wb-yaml .cm-content").wait_for(timeout=WAIT)
    yaml_has(pg, "n: data.n")
    assert "n: data.n" not in p.model.path.read_text()
    assert pg.locator("[data-step='4'].open").count() == 1                               # the steps as they were
    pg.get_by_role("button", name="Cancel", exact=True).click()
    pg.reload()
    pg.get_by_role("button", name="Edit", exact=True).first.wait_for(timeout=WAIT)
    assert pg.locator(".wb").count() == 0                                                # cancelled: forgotten
    assert settled(pg) == []
    pg.close()


@pytest.mark.parametrize("name", ["ec2instance", "ec2-instance"])
def test_a_new_projection_survives_a_change_to_the_address_and_a_reload(browser, served, name):
    p, url = served
    pg = opened(browser, url + "/goals")
    pg.hover("#nav")
    pg.get_by_role("button", name="New projection").click()
    pg.get_by_label("The new projection's name").fill(name)
    pg.keyboard.press("Enter")
    pg.wait_for_url(f"**/{name}", timeout=WAIT)
    pg.get_by_label("A new field's name").fill("state")
    pg.get_by_role("button", name="Add a field").click()
    yaml_has(pg, "state: {type: text}")
    # a search in the list below replaces the address without the history state that said "new": the draft stays
    pg.get_by_placeholder("Search ids and fields").fill("x")
    pg.wait_for_url(f"**/{name}?q=x", timeout=WAIT)
    pg.wait_for_timeout(800)
    assert pg.locator(".wb").count() == 1 and pg.locator("h1", has_text="Nothing here").count() == 0
    yaml_has(pg, "state: {type: text}")
    pg.reload()
    pg.locator(".wb-yaml .cm-content").wait_for(timeout=WAIT)
    yaml_has(pg, "state: {type: text}")
    pg.get_by_role("button", name="Cancel", exact=True).click()
    pg.close()


# ---- a residual group opened in the mapping step: its events there to map, until it is fixed

OPENING = """\
name: wb
projections:
  instance:
    query: data.source == 'aws.ec2'
    key: [account, region, instance_id]
    fields:
      state: {values: [pending, running, stopped, shutting-down, terminated]}
      account: text
      region: text
      instance_id: text
    ignore: [type]
    events:
      state-change:
        when: data['detail-type'] == 'EC2 Instance State-change Notification'
        state: data.detail.state
        account: data.account
        region: data.region
        instance_id: data.detail['instance-id']
      stop-call:
        when: data.detail.eventName == 'StopInstances'
        account: data.account
        region: data.region
      reboot-call:
        when: data.detail.eventName == 'RebootInstances'
        account: data.account
        region: data.detail.eventSource
        instance_id: each(data.detail.requestParameters.instancesSet.items, 'instanceId')
"""


def unexplained_has(pg, text: str, yes: bool = True) -> None:
    pg.wait_for_function("([t, y]) => document.querySelector('[data-testid=unexplained]').textContent.includes(t) === y",
                         arg=[text, yes], timeout=WAIT)


@pytest.mark.parametrize("served", [OPENING], indirect=True)
def test_no_key_refused_and_a_split_open_their_events_in_the_mapping_until_fixed(browser, served):
    p, url = served
    pg = opened(browser, url + "/instance")
    pg.get_by_role("button", name="Edit", exact=True).first.click()
    pg.locator("[data-step='5'].open [data-testid=review-objects]").wait_for(timeout=WAIT)
    unexplained_has(pg, "no key")
    side = pg.locator("aside.wb-side")

    # no key: the kind that lacks instance_id, opened from the residual in the panel
    side.locator("ul[aria-label='The residual'] li", has_text="no key").locator("summary").click()
    side.get_by_role("button", name="Open stop-call's events with no key in the mapping").click()
    stop = kind_box(pg, "stop-call")
    banner = stop.locator("[data-testid=opened-stop-call]")
    banner.wait_for(timeout=WAIT)
    said = banner.inner_text()
    assert "of 31 events with no key" in said and "instance_id is not told" in said and "show its usual samples" in said
    assert "StopInstances" in stop.locator(".wb-sample").inner_text()
    assert stop.locator("[data-testid=key-stop-call] .wb-key-no.wb-hl").count() == 1          # the ✗ highlighted
    box = stop.get_by_label("stop-call: instance_id")
    pg.wait_for_function("() => document.activeElement?.getAttribute('aria-label') === 'stop-call: instance_id'", timeout=WAIT)
    box.fill("each(data.detail.requestParameters.instancesSet.items, 'instanceId')")
    pg.keyboard.press("Enter")
    stop.locator("[data-testid=opened-stop-call]", has_text="✓ fixed").wait_for(timeout=WAIT)
    unexplained_has(pg, "no key", False)
    stop.get_by_role("button", name="Close").click()
    assert stop.locator("[data-testid=opened-stop-call]").count() == 0

    # refused: from the line above the steps; the value refused marked in the event, the field highlighted
    pg.locator("[data-testid=unexplained]").get_by_role("button", name="refused").click()
    change = kind_box(pg, "state-change")
    banner = change.locator("[data-testid=opened-state-change]")
    banner.wait_for(timeout=WAIT)
    assert "refused events" in banner.inner_text() and 'state: "stopping" is not one of its states' in banner.inner_text()
    assert change.locator(".wb-sample .jv-flag").first.inner_text() == '"stopping"'
    assert change.locator("tr.wb-hl th").inner_text() == "state"
    pg.locator("[data-step='1'] .wb-step-head button").click()
    pg.get_by_label("The values of state").fill("pending, running, stopping, stopped, shutting-down, terminated")
    pg.keyboard.press("Enter")
    change.locator("[data-testid=opened-state-change]", has_text="✓ fixed").wait_for(timeout=WAIT)
    assert change.locator(".wb-sample .jv-flag").count() == 0                                   # its usual samples
    unexplained_has(pg, "refused", False)

    # a possible split: the object's events, and those of the object keyed the main way, the key part that differs
    side.locator("ul[aria-label='The residual'] li", has_text="possible splits").locator("summary").click()
    side.get_by_role("button", name="Open the split keyed by reboot-call in the mapping").click()
    reboot = kind_box(pg, "reboot-call")
    banner = reboot.locator("[data-testid=opened-reboot-call]")
    banner.wait_for(timeout=WAIT)
    assert "possible split" in banner.inner_text() and "region read differently" in banner.inner_text()
    assert "RebootInstances" in reboot.locator(".wb-sample").inner_text()
    assert "region" in reboot.locator("[data-testid=key-reboot-call] .wb-hl").inner_text()
    assert change.locator("[data-testid=opened-state-change]").count() == 1                    # the main way, too
    reboot.get_by_label("reboot-call: region").fill("data.region")
    pg.keyboard.press("Enter")
    reboot.locator("[data-testid=opened-reboot-call]", has_text="✓ fixed").wait_for(timeout=WAIT)
    unexplained_has(pg, "possible splits", False)
    assert settled(pg) == []
    pg.close()
