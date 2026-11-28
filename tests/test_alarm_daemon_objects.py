"""Alarms and daemons are objects (SPEC §9.2, §9.7): an alarm block's raisings recorded as ``alarm.raised`` and
``alarm.cleared`` on change only, each raising an ``ergostat.alarm`` object with what it watched, the value, the
threshold, when raised and cleared and how long; "raised since" the raise's own time; the attention row and the
Blocks view's mark link to it. Each daemon an ``ergostat.daemon`` object (running, restarting, given-up, stopped) from
the supervisor's events; the attention row links to it, not to a log file."""

from __future__ import annotations

import time

from ergostat import model as mdl
from ergostat import state as st
from ergostat.alarms import ALARM, read_state
from ergostat.daemons.objects import DAEMON
from ergostat.eventquery import as_query, events_matching
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

from .test_daemons import block, events, setup, spawned
from .test_leases import start, wait_for

MODEL = """\
name: q
stocks:
  queue:
    unit: jobs
    sensor:
      manual: true
blocks:
  hot:
    type: alarm
    in: stock.queue
    above: 5
"""


def engine(tmp_path, text: str = MODEL):
    (tmp_path / "ergostat.yaml").write_text(text)
    p = Project(mdl.load(tmp_path))
    assert not [x for x in p.model.problems if x.level == "error"], p.model.problems
    return p, Engine(p, say=lambda s: None)


def read(p, e, v: float, at: float) -> None:
    p.measurements.add("sensor/queue.main", v, at=at)
    e.evaluate(tick=True)


def test_an_alarm_raised_and_cleared_is_two_events_and_one_object(tmp_path):
    p, e = engine(tmp_path)
    now = time.time()
    read(p, e, 1, now - 30)
    assert not events(p, "alarm.*"), "within its bound: nothing"
    read(p, e, 9, now - 20)
    read(p, e, 12, now - 10)                                   # still raised: nothing more
    raised = events(p, "alarm.*")
    assert [x["type"] for x in raised] == ["alarm.raised"]
    r = raised[0]
    assert r["item"] == f"{ALARM}/hot/{r['id']}" and r["source"] == "ergostat"
    assert r["data"]["value"] == 9 and r["data"]["above"] == 5 and r["data"]["watches"] == "stock.queue"
    assert "stock.queue at 9, above 5" in r["data"]["why"]
    assert read_state(p.dir)["hot"]["item"] == r["item"]
    snap = st.snapshot(p)
    a = snap["alarms"]["hot"]
    assert a["item"] == r["item"] and a["since"] == r["data"]["raised"], "raised since: the raise's own time"
    row = next(x for x in st.attention(snap) if x["what"] == "alarm hot")
    assert row["link"] == f"/{r['item']}"
    obj = its.detail(p.events, p.model.spec, r["item"])
    assert obj["state"] == "raised" and obj["fields"]["block"] == "hot" and obj["fields"]["value"] == 9
    read(p, e, 2, now)
    got = events(p, "alarm.*")
    assert [x["type"] for x in got] == ["alarm.raised", "alarm.cleared"]
    c = got[1]
    assert c["item"] == r["item"] and c["causedby"] == r["id"] and c["data"]["lasted"] >= 0
    obj = its.detail(p.events, p.model.spec, r["item"])
    assert obj["state"] == "cleared" and obj["fields"]["cleared"] == c["data"]["cleared"]
    assert "hot" not in read_state(p.dir) and "hot" not in st.snapshot(p)["alarms"]
    read(p, e, 3, now + 1)
    assert len(events(p, "alarm.*")) == 2, "on change only"
    hit, _ = events_matching(p.events, as_query("type.startswith('alarm.')"))
    assert [x["type"] for x in hit] == ["alarm.raised", "alarm.cleared"]


def test_a_second_raising_is_an_object_of_its_own(tmp_path):
    p, e = engine(tmp_path)
    now = time.time()
    for i, v in enumerate([9, 1, 8, 1]):
        read(p, e, v, now - 40 + i * 10)
    raised = events(p, "alarm.raised")
    assert len(raised) == 2 and raised[0]["item"] != raised[1]["item"]
    objs = its.project(p.events, p.model.spec, ALARM)
    assert sorted(i.state for i in objs) == ["cleared", "cleared"] and {i.fields["block"] for i in objs} == {"hot"}


def test_an_engine_started_again_goes_on_with_the_open_raising(tmp_path):
    p, e = engine(tmp_path)
    now = time.time()
    read(p, e, 9, now - 20)
    p2 = Project(mdl.load(tmp_path))
    e2 = Engine(p2, say=lambda s: None)
    read(p2, e2, 10, now - 10)
    assert len(events(p2, "alarm.raised")) == 1, "the same raising: not raised again"
    read(p2, e2, 0, now)
    got = events(p2, "alarm.*")
    assert [x["type"] for x in got] == ["alarm.raised", "alarm.cleared"] and got[0]["item"] == got[1]["item"]


def test_a_raising_whose_block_left_the_model_is_cleared(tmp_path):
    p, e = engine(tmp_path)
    read(p, e, 9, time.time() - 5)
    (tmp_path / "ergostat.yaml").write_text(MODEL.split("blocks:")[0])
    p2 = Project(mdl.load(tmp_path))
    e2 = Engine(p2, say=lambda s: None)
    read(p2, e2, 9, time.time())
    c = events(p2, "alarm.cleared")
    assert len(c) == 1 and "no longer an alarm" in c[0]["data"]["cleared_why"] and not read_state(p2.dir)
    assert ALARM not in p2.model.spec.items, "built in only while the model has an alarm"


def test_the_blocks_view_marks_the_raised_alarm_with_its_object(tmp_path):
    from ergostat.blockdiagram import diagram
    p, e = engine(tmp_path)
    read(p, e, 9, time.time())
    snap = st.snapshot(p)
    g = diagram(p.model, snap)
    node = next(n for n in g["nodes"] if n["id"] == "blk:hot")
    assert node["alarm"] == "raised" and node["alarm_item"] == snap["alarms"]["hot"]["item"]


# ---- daemons


def test_a_daemon_is_an_object_whose_history_is_its_starts_restarts_and_give_up(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py crash, restart: {max: 2, within: 1m, backoff: [0.1s, 0.1s]}}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.failed"), 10)
    finally:
        e.close()
    assert spawned(p) == 3
    mine = [x for x in p.events.query(n=None, type="ergostat.daemon.*")]
    assert {x["item"] for x in mine} == {f"{DAEMON}/block.worker"}
    assert [x["type"] for x in mine] == ["ergostat.daemon.started", "ergostat.daemon.restarted"] * 2 + \
        ["ergostat.daemon.started", "ergostat.daemon.failed"], "a given-up one is not said stopped when ergostat stops"
    obj = its.detail(p.events, p.model.spec, f"{DAEMON}/block.worker")
    assert obj["state"] == "given-up" and obj["fields"]["serves"] == ["block.worker"]
    assert obj["fields"]["alarm"]["why"].startswith("given up after 3 restarts")
    assert obj["fields"]["log"].startswith("file:") and obj["fields"]["log"].endswith("daemon-block.worker.log")
    assert [m["to"] for m in obj["moves"]] == ["running", "restarting", "running", "restarting", "running", "given-up"]
    row = next(a for a in st.attention(st.snapshot(p)) if a["what"] == "daemon block.worker")
    assert row["link"] == f"/{DAEMON}/block.worker" and "its log" not in row["says"]
    hit, _ = events_matching(p.events, as_query("type.startswith('ergostat.daemon.')"))
    assert len(hit) == len(mine)


def test_a_daemon_stopped_with_ergostat_is_said_once(tmp_path):
    p = setup(tmp_path, block("{run: python3 d.py}"))
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "ergostat.daemon.started"), 10)
    finally:
        e.close()
    got = [x["type"] for x in p.events.query(n=None, type="ergostat.daemon.*")]
    assert got == ["ergostat.daemon.started", "ergostat.daemon.stopped"]
    obj = its.detail(p.events, p.model.spec, f"{DAEMON}/block.worker")
    assert obj["state"] == "stopped" and obj["fields"]["why"] == "ergostat stopped"
