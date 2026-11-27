"""The charts' data (docs/proposals/charts.md): parts' values bucketed over the window, flow rates by
each source, a loop's scope and a projection's flow."""

import textwrap
import time

from ergostat import model as mdl
from ergostat.store import Project
from ergostat.web.server import Live, api


def get(p, path, **q):
    return api(Live(p), path, {"since": ["1h"], **{k: [str(v)] for k, v in q.items()}})


def by_ref(got):
    return {s["ref"]: s for s in got["series"]}


def test_a_stock_is_its_last_reading_in_each_bucket_and_the_window_starts_with_the_record(project):
    now = time.time()
    project.events.add("ergostat.started", at=now - 600)                     # the record starts here
    for i, v in enumerate([10, 11, 12, 13, 14, 15]):
        project.measurements.add("sensor/disk-usage", v, at=now - 550 + i * 100)
    got = get(project, "series", refs="stock.disk-used", points=6)
    assert abs(got["since"] - (now - 600)) < 1 and len(got["times"]) == 6     # ten minutes recorded: the window is those
    s = got["series"][0]
    assert s["kind"] == "stock" and s["unit"] == "%" and s["values"] == [10, 11, 12, 13, 14, 15]
    assert s["goal"]["name"] == "disk-under-80" and s["goal"]["value"] == 80 and s["goal"]["band"] == [80, 82]
    project.measurements.add("sensor/disk-usage", 99, at=now - 540)          # two in one bucket: the later one
    assert get(project, "series", refs="stock.disk-used", points=6)["series"][0]["values"][0] == 99


def test_flow_rates_come_from_valves_and_else_from_the_stocks_changes(project):
    now = time.time()
    project.events.add("ergostat.started", at=now - 600)
    for i in range(6):                                       # the disk rises 6 points every 100s
        project.measurements.add("sensor/disk-usage", 50 + 6 * i, at=now - 550 + i * 100)
    for i in range(6):                                       # and 1 point is cleaned each time
        project.events.add("valve.opened", item="delete-old-files", data={"amount": 1}, at=now - 560 + i * 100)
    got = by_ref(get(project, "series", refs="stock.disk-used", strip=1, points=6))
    assert [(s["ref"], s["role"]) for s in got.values()] == [("stock.disk-used", ""), ("flow.logs-written", "inflow"),
                                                           ("flow.cleaned", "outflow")]
    cleaned = got["flow.cleaned"]
    assert cleaned["how"].startswith("opened by delete-old-files") and cleaned["per"] == "hour"
    assert all(abs(v - 36) < 0.01 for v in cleaned["values"])               # 1 every 100s: 36 an hour
    logs = got["flow.logs-written"]
    assert logs["how"] == "changes of disk-used" and logs["values"][0] is None
    # the disk rose 216 an hour net, and cleaning took 36: 252 were written
    assert all(abs(v - 252) < 1 for v in logs["values"][1:])


MODEL = """
projections:
  pr:
    match:
      key: pr/*
    states: [open, review, merged, closed]
    events:
      pr.review-asked:
        state: set('review')
      pr.merged:
        state: set('merged')
      pr.closed:
        state: set('closed')
    otherwise: rest
stocks:
  in-review:
    unit: prs
    sensor:
      projection: pr
      state: review
flows:
  merging:
    from: in-review
    sensor:
      projection: pr
      entering: merged
      over: 10m
auxiliaries:
  load:
    unit: share
    driven-by: [+stock.in-review, flow.merging]
    sensor:
      manual: true
goals:
  few-in-review:
    stock: in-review
    hold: "<= 2"
    tolerance: 1
blocks:
  nudge:
    type: program
    run: "true"
    goal: few-in-review
    max: 2
    out: flow.merging
"""


def spec_project(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    return Project(mdl.load(tmp_path))


def test_a_flow_counted_from_items_uses_its_readings_and_else_the_moves(tmp_path):
    p = spec_project(tmp_path)
    now = time.time()
    for n in range(4):
        p.events.add("pr.opened", item=f"pr/{n}", at=now - 1200 + n)
        p.events.add("pr.merged", item=f"pr/{n}", at=now - 150 + n)          # four merged, in the last of four buckets
    s = by_ref(get(p, "series", refs="flow.merging", points=4))["flow.merging"]
    assert s["how"].startswith("items moving, from the record") and s["values"][:3] == [0, 0, 0]
    assert abs(s["values"][3] - 4 * 3600 / 600) < 0.01             # over the sensor's own window (over: 10m), not the page's
    p.measurements.add("sensor/merging.main", 7.0, at=now - 100)
    p.measurements.add("sensor/merging.main", 9.0, at=now - 50)
    s = by_ref(get(p, "series", refs="flow.merging", points=4))["flow.merging"]
    assert s["how"] == "measured by merging.main" and s["values"][3] == 8.0 and s["values"][0] is None   # the mean in its bucket


def test_a_flow_and_an_auxiliary_strip_show_what_drives_them(tmp_path):
    p = spec_project(tmp_path)
    p.events.add("pr.opened", item="pr/1", at=time.time() - 60)
    flow = get(p, "series", refs="flow.merging", strip=1)
    assert [(s["ref"], s["role"]) for s in flow["series"]] == [("flow.merging", ""), ("stock.in-review", "from")]
    aux = get(p, "series", refs="auxiliary.load", strip=1)
    assert [(s["ref"], s["role"]) for s in aux["series"]] == [("auxiliary.load", ""), ("stock.in-review", "driven by"),
                                                             ("flow.merging", "driven by")]
    assert aux["series"][0]["kind"] == "auxiliary"
    assert get(p, "series", refs="stock.nope,flow.in-review")["series"] == []        # unknown, or the wrong kind


def test_a_loop_scope_has_r_y_u_e_and_its_numbers(tmp_path):
    p = spec_project(tmp_path)
    now = time.time()
    p.events.add("ergostat.started", at=now - 600)
    for i, v in enumerate([1, 2, 4, 5, 3, 1]):
        p.measurements.add("sensor/in-review.main", v, at=now - 550 + i * 100)
    for i, amount in enumerate([1, 2, 2]):
        p.events.add("valve.opened", item="nudge", data={"amount": amount, "flow": "merging"}, at=now - 300 + i * 60)
    p.events.add("loop.off", item="few-in-review", data={"value": 4}, at=now - 400)
    p.events.add("loop.holding", item="few-in-review", data={"value": 1}, at=now - 50)
    sc = get(p, "loop-scope", goal="few-in-review", points=6)
    assert sc["r"] == 2 and sc["op"] == "<=" and sc["band"] == [2, 3] and sc["y"] == [1, 2, 4, 5, 3, 1]
    assert sc["e"] == [0, 0, -2, -3, -1, 0]                                   # e = r − y; nothing on the satisfied side
    assert [a for _, a in sc["u"]["openings"]] == [1, 2, 2] and sc["u"]["limits"] == [0, 2]
    assert abs(sc["u"]["saturated"] - 2 / 3) < 1e-9 and sc["numbers"]["saturated"] == sc["u"]["saturated"]
    assert len(sc["off"]) == 1 and abs(sc["off"][0][0] - (now - 400)) < 1e-6 and abs(sc["off"][0][1] - (now - 50)) < 1e-6
    assert get(p, "loop-scope", goal="nope") is None


def test_an_item_kind_flows_through_its_states_and_its_finished_items_have_cycle_times(tmp_path):
    p = spec_project(tmp_path)
    now = time.time()
    t0 = now - 1000
    p.events.add("pr.opened", item="pr/1", at=t0)
    p.events.add("pr.review-asked", item="pr/1", at=t0 + 300)
    p.events.add("pr.merged", item="pr/1", at=t0 + 600)                   # took 600s
    p.events.add("pr.opened", item="pr/2", at=t0 + 100)
    p.events.add("pr.closed", item="pr/2", at=t0 + 900)                   # took 800s
    p.events.add("pr.opened", item="pr/3", at=t0 + 200)                   # still open
    fl = get(p, "items-flow", projection="pr", points=10)
    assert fl["states"] == ["open", "review", "merged", "closed"] and len(fl["times"]) == 10
    assert fl["counts"]["open"][0] == 1 and fl["counts"]["open"][3] == 3 - 1        # at 350s: 1 in review
    last = {s: c[-1] for s, c in fl["counts"].items()}
    assert last == {"open": 1, "review": 0, "merged": 1, "closed": 1} and fl["now"] == last
    assert fl["finished_states"] == ["merged", "closed"]                   # no item left them
    assert [(f["id"], f["took"]) for f in fl["finished"]] == [("pr/1", 600), ("pr/2", 800)] and fl["median"] == 700
    assert get(p, "items-flow", projection="nope") is None
