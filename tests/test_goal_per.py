"""Goals held per item or per group (SPEC §8, ``per:``): a goal on a stock counted from items, held by each item or
each group of them, off while any breaks it and naming those that do (spec/goal_per.py, the engine, the snapshot)."""

from __future__ import annotations

import textwrap
import time

from ergostat import model as mdl
from ergostat import state as st
from ergostat.spec.engine import Engine
from ergostat.spec.goal_per import worst
from ergostat.store import Project

MODEL = """
name: t
projections:
  epic: {id: epic/*, states: [planned, underway, shipped]}
  ticket:
    id: ticket/*
    states: [todo, doing, review, done]
    on: {ticket.started: doing, ticket.review: review, ticket.done: done}
    relations: {parent: epic}
stocks:
  review-age:
    unit: hours
    sensor: {projection: ticket, state: review, measure: oldest, every: 0.2s}
  open-tickets:
    unit: tickets
    sensor: {projection: ticket, state: [todo, doing, review], every: 0.2s}
flows:
  reviewing: {from: review-age}
  closing: {from: open-tickets}
goals:
  review-fresh: {stock: review-age, hold: "<= 48", per: item}
  epics-small: {stock: open-tickets, hold: "<= 2", per: parent}
blocks:
  reviewer: {type: program, run: echo 0, every: 1h, goal: review-fresh, out: flow.reviewing}
  closer: {type: program, run: echo 0, every: 1h, goal: epics-small, out: flow.closing}
"""
HOUR = 3600.0


def project(tmp_path, text=MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def record(p: Project, now: float) -> None:
    for n, (epic, review_h) in enumerate([("epic/1", 73), ("epic/1", 50), ("epic/1", None), ("epic/2", 3),
                                          ("epic/2", None)], 1):
        t = f"ticket/{n}"
        p.events.add("ticket.found", item=t, data={"parent": epic}, at=now - 100 * HOUR)
        if review_h is not None:
            p.events.add("ticket.review", item=t, at=now - review_h * HOUR)


def test_a_per_item_goal_goes_off_naming_the_items_older_than_its_setpoint(tmp_path):
    p = project(tmp_path)
    now = time.time()
    record(p, now)
    spec = p.model.spec
    value, breaking, n = worst(spec, spec.goals["review-fresh"], None, p.events, now)
    assert round(value) == 73 and n == 2
    assert [b["item"] for b in breaking] == ["ticket/1", "ticket/2"]
    # the engine: off, its event naming them
    e = Engine(p, say=lambda s: None)
    e.start_all()
    deadline = time.monotonic() + 15
    while not p.events.query(n=1, type="loop.off", item="review-fresh") and time.monotonic() < deadline:
        time.sleep(0.1)
    e.close()
    off = p.events.query(n=1, type="loop.off", item="review-fresh")
    assert off, "the goal went off"
    assert [b["item"] for b in off[-1]["data"]["breaking"]] == ["ticket/1", "ticket/2"]
    assert off[-1]["data"]["breaking_n"] == 2


def test_a_per_group_goal_holds_each_parents_open_items(tmp_path):
    p = project(tmp_path)
    now = time.time()
    record(p, now)
    spec = p.model.spec
    value, breaking, n = worst(spec, spec.goals["epics-small"], None, p.events, now)
    assert (value, n, breaking) == (3.0, 1, [{"group": "epic/1", "value": 3.0}])   # epic/1 has 3 open, epic/2 has 2
    p.events.add("ticket.done", item="ticket/3")
    value, breaking, n = worst(spec, spec.goals["epics-small"], None, p.events, time.time())
    assert (value, n) == (2.0, 0)
    # as it stood: time travel reads the item index as of then
    assert worst(spec, spec.goals["epics-small"], None, p.events, now)[2] == 1


def test_per_needs_a_stock_counted_from_items(tmp_path):
    from ergostat.spec import SpecError, load
    for extra, says in (('  plain: {stock: plain, hold: "<= 1", per: item}\n', "stock counted from items"),
                        ('  counted: {stock: open-tickets, hold: "<= 1", per: item}\n', "each item counts one"),
                        ('  floor: {stock: open-tickets, hold: ">= 1", per: parent}\n', "a group with no items is no group")):
        text = MODEL.replace("stocks:\n", "stocks:\n  plain: {unit: x, sensor: {run: echo 1, every: 1m}}\n").replace(
            "blocks:\n", extra + "blocks:\n")
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
        try:
            load(tmp_path / "ergostat.yaml")
        except SpecError as e:
            assert says in str(e), str(e)
        else:
            raise AssertionError(f"not refused: {extra}")


def test_needs_attention_and_the_loop_name_the_items_that_break_it(tmp_path):
    p = project(tmp_path)
    now = time.time()
    record(p, now)
    for name in ("review-age", "open-tickets"):                 # a reading of each stock, as its sensor would take
        s = next(iter(p.model.spec.stocks[name].sensors.values()))
        p.measurements.add(s.series, 1.0, at=now - 5)
    snap = st.snapshot(p, now=now)
    lp = snap["loops"]["review-fresh"]
    assert lp["status"] == "off" and round(lp["value"]) == 73 and lp["breaking_n"] == 2
    assert snap["loops"]["epics-small"]["breaking"] == [{"group": "epic/1", "value": 3.0}]
    said = {a["what"]: a["says"] for a in st.attention(snap)}
    assert "ticket/1 (73)" in said["goal review-fresh"] and "2 items break it" in said["goal review-fresh"], said
    assert said["goal epics-small"].startswith("1 parent breaks it (each parent's open-tickets <= 2): epic/1 (3)"), said


def test_a_field_neither_related_nor_known_is_said(tmp_path):
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace("per: parent", "per: team"))
    _, problems = read(tmp_path / "ergostat.yaml")
    said = [p for p in problems if p.code == "goal-per-field"]
    assert said and said[0].level != "error" and "'team'" in said[0].message
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    assert not [p for p in read(tmp_path / "ergostat.yaml")[1] if p.code == "goal-per-field"]


def test_with_no_items_nothing_breaks_it_and_it_holds(tmp_path):
    p = project(tmp_path)
    spec, now = p.model.spec, time.time()
    assert worst(spec, spec.goals["review-fresh"], None, p.events, now) == (0.0, [], 0)
    g = spec.goals["review-fresh"]
    g.hold = type(g.hold)(">=", 1.0)                             # a floor: 0 would break it, so its value is the setpoint
    assert worst(spec, g, None, p.events, now) == (1.0, [], 0)


def test_a_block_serving_it_is_given_the_worst_and_who_breaks_it(tmp_path):
    p = project(tmp_path)
    now = time.time()
    record(p, now)
    s = next(iter(p.model.spec.stocks["review-age"].sensors.values()))
    p.measurements.add(s.series, 1.0, at=now - 5)                   # the stock's own reading: the total, not the worst
    e = Engine(p, say=lambda s: None)
    try:
        e.evaluate(full=True)
        ctx = e.context(p.model.spec.blocks["reviewer"], "command")["goals"]["review-fresh"]
    finally:
        e.close()
    assert round(ctx["value"]) == 73 and ctx["status"] == "off" and ctx["per"] == "item"
    assert [b["item"] for b in ctx["breaking"]] == ["ticket/1", "ticket/2"] and ctx["breaking_n"] == 2


def test_the_items_are_read_again_only_when_the_record_changed(tmp_path, monkeypatch):
    from ergostat.spec import goal_per
    p = project(tmp_path)
    record(p, time.time())
    reads = []
    real = goal_per.members
    monkeypatch.setattr(goal_per, "members", lambda *a: reads.append(1) or real(*a))
    e = Engine(p, say=lambda s: None)
    try:
        e._per(time.time(), True, None)
        e._per(time.time(), True, None)
        assert len(reads) == 2                                   # once for each of the two goals
        p.events.add("ticket.done", item="ticket/1")
        e._per(time.time(), True, None)
        assert len(reads) == 4
    finally:
        e.close()


def test_the_snapshot_holds_it_to_the_cascades_setpoint_and_says_when_none_is_past_its_tolerance(tmp_path):
    text = MODEL.replace("  epics-small:", "  outer: {stock: open-tickets, hold: \"<= 100\"}\n  epics-small:").replace(
        "blocks:\n", "blocks:\n  setter: {type: proportional, goal: outer, out: goal.epics-small, gain: 1}\n")
    p = project(tmp_path, text)
    now = time.time()
    record(p, now)
    for name in ("review-age", "open-tickets"):
        s = next(iter(p.model.spec.stocks[name].sensors.values()))
        p.measurements.add(s.series, 1.0, at=now - 5)
    p.measurements.add("block/setter", 3.0, at=now - 5)          # the outer loop lets each epic have 3
    snap = st.snapshot(p, now=now)
    lp = snap["loops"]["epics-small"]
    assert lp["setpoint"] == "<= 3" and lp["status"] == "holding" and lp["breaking_n"] == 0
    # off from before, back past the setpoint but within the tolerance: off, and none named
    snap["loops"]["epics-small"] = {**lp, "status": "off", "value": 3.0, "breaking": [], "error": 0.0}
    said = {a["what"]: a["says"] for a in st.attention(snap)}["goal epics-small"]
    assert said.startswith("the worst parent's open-tickets is 3") and "none is past its tolerance" in said, said
