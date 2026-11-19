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
items:
  epic: {id: epic/*, states: [planned, underway, shipped]}
  ticket:
    id: ticket/*
    states: [todo, doing, review, done]
    on: {ticket.started: doing, ticket.review: review, ticket.done: done}
    relations: {parent: epic}
stocks:
  review-age:
    unit: hours
    sensor: {items: ticket, state: review, measure: oldest, every: 0.2s}
  open-tickets:
    unit: tickets
    sensor: {items: ticket, state: [todo, doing, review], every: 0.2s}
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
                        ('  counted: {stock: open-tickets, hold: "<= 1", per: item}\n', "each item counts one")):
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
    assert "ticket/1 (73)" in said["loop review-fresh"] and "2 items break it" in said["loop review-fresh"], said
    assert said["loop epics-small"].startswith("1 parent breaks it (each parent's open-tickets <= 2): epic/1 (3)"), said
