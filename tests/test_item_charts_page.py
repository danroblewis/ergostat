"""An item's show page, not in edit mode, has charts of its own history (SPEC §4f: item-state-timeline,
item-field-chart, item-events-histogram), here of an instance of the EC2 simulator's record
(tests/fixtures/ec2_stream.py): its states as a band with the time in each, a chart of its reboots (a numeric field
it changed at least twice), and its events per time bucket by kind of event."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

import pytest

from ergostat import web
from tests.test_projection_workbench_page import ec2_project
from tests.test_react_pages import WAIT, browser, opened, settled  # noqa: F401  (the browser fixture)
from tests.test_react_pages import pytestmark  # noqa: F401  (skipped when the page is not built)

pytest.importorskip("playwright.sync_api")

MODEL = """\
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
      reboots: {type: integer, fold: add}
    events:
      state-change:
        when: data['detail-type'] == 'EC2 Instance State-change Notification'
        state: data.detail.state
        account: data.account
        region: data.region
        instance_id: data.detail['instance-id']
      reboot:
        when: data.detail.eventName == 'RebootInstances'
        account: data.account
        region: data.region
        instance_id: each(data.detail.requestParameters.instancesSet.items, 'instanceId')
        reboots: 1
"""


@pytest.fixture
def served(tmp_path):
    p = ec2_project(tmp_path / "wb", MODEL)
    server, url = web.serve(p, 0)
    try:
        yield p, url
    finally:
        server.shutdown()
        server.server_close()


def api(url: str, path: str) -> dict:
    return json.load(urllib.request.urlopen(url + "/api/" + path, timeout=30))


def test_an_items_show_page_charts_its_states_numbers_and_events(browser, served):
    _, url = served
    items = api(url, "items?projection=instance&n=200")["items"]
    rebooted = [i for i in items if isinstance(i["fields"].get("reboots"), int) and i["fields"]["reboots"] >= 2]
    assert rebooted, "the simulator's fleet has an instance rebooted twice"
    it = rebooted[0]["id"]
    d = api(url, f"items/{urllib.parse.quote(it, safe='')}?projection=instance")
    states = list(dict.fromkeys(m["to"] for m in d["moves"]))
    assert len(states) >= 2

    pg = opened(browser, url + "/instance/" + "/".join(urllib.parse.quote(s, safe="") for s in it.split("/")))
    band = pg.locator(".item-timeline-band")
    band.wait_for(timeout=WAIT)
    assert band.locator(".item-timeline-span").count() == len(d["moves"])
    spent = pg.locator(".item-timeline-spent tr")
    assert sorted(spent.evaluate_all("rs => rs.map(r => r.dataset.state)")) == sorted(states)
    assert all(t.strip() for t in pg.locator(".item-timeline-spent td.num").first.all_inner_texts())

    chart = pg.locator(".item-field-chart[data-field=reboots]")
    chart.wait_for(timeout=WAIT)
    assert chart.locator("canvas").count() >= 1 and "reboots" in chart.inner_text()
    assert pg.locator(".item-field-chart[data-field=account]").count() == 0           # text, set once: no chart

    hist = pg.locator(".item-histogram")
    hist.wait_for(timeout=WAIT)
    kinds = hist.locator(".item-histogram-kinds li").evaluate_all("ls => ls.map(l => l.dataset.kind)")
    assert {"state-change", "reboot"} <= set(kinds)
    assert hist.locator("rect[data-kind=reboot]").count() >= 1
    title = pg.locator(".panel-kind-item-events-histogram .panel-title").inner_text()
    assert re.fullmatch(r"Its events per [\w ]+, by kind", title), title        # its bucket's size, said
    bucket = hist.locator("rect.item-histogram-hit").nth(                        # a bucket with events: its tip
        int(hist.locator("rect[data-kind]").first.evaluate("r => Math.floor(+r.getAttribute('x') / (600 / "
                                                              "document.querySelectorAll('.item-histogram-hit').length))")))
    bucket.hover()
    tip = pg.locator("[data-testid=histogram-tip]")
    tip.wait_for(timeout=WAIT)
    assert " to " in tip.locator(".chart-tip-time").inner_text()
    assert re.search(r"\b\d+\b", tip.locator("[data-kind]").first.inner_text()), tip.inner_text()

    # a state's span says the event that moved it there
    span = pg.locator(".item-timeline-span").nth(1)
    assert "moved here by state-change" in (span.get_attribute("title") or ""), span.get_attribute("title")
    span.click()
    assert "moved here by state-change" in pg.locator("[data-testid=state-said]").inner_text()

    kinds = ["panel-kind-item-summary", "panel-kind-item-state-timeline", "panel-kind-item-field-chart",
             "panel-kind-item-events-histogram", "panel-kind-item-fields"]       # summary first, the charts, the rest
    order = pg.evaluate("(ks) => [...document.querySelectorAll(ks.map(k => '.' + k).join(','))]"
                        ".map(e => [...e.classList].find(c => ks.includes(c)))", kinds)
    assert order == kinds, order
    assert settled(pg) == []
    pg.close()


def test_hovering_a_chart_names_its_lines_and_values(browser, served):
    """The charts have no legend: hovering one says, at the cursor, the time and each line's colour, name and value."""
    p, url = served
    its = api(url, "items?projection=instance&n=50")
    rows = its.get("items") or its.get("rows") or []
    it = next(r["id"] for r in rows if (r.get("fields") or r).get("reboots"))
    pg = opened(browser, url + "/instance/" + "/".join(urllib.parse.quote(s, safe="") for s in it.split("/")))
    over = pg.locator(".item-field-chart[data-field=reboots] .u-over")
    over.wait_for(timeout=WAIT)
    box = over.bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.9, box["y"] + box["height"] / 2)
    tip = pg.locator(".item-field-chart[data-field=reboots] .chart-tip")
    tip.wait_for(state="visible", timeout=WAIT)
    text = tip.inner_text()
    assert "reboots" in text and tip.locator(".chart-tip-swatch").count() >= 1, text
    pg.mouse.move(0, 0)
    pg.close()
