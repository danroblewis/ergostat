"""Findings from the record: a stock heading for its limit, a block saturating, a person not
answering, a critical goal recovering more slowly than it did."""

import textwrap
import time

from ergostat import model as mdl
from ergostat.spec import watch
from ergostat.store import Project

MODEL = """
stocks:
  disk:
    unit: "%"
    limit: 100
    sensor:
      run: echo 0
      every: 1m
  queue:
    unit: jobs
    sensor:
      run: echo 0
flows:
  served:
    from: queue
  escalated:
    from: queue
goals:
  short:
    stock: queue
    hold: "<= 10"
    critical: true
blocks:
  worker:
    type: program
    goal: short
    run: "true"
    out: flow.served
  oncall:
    type: person
    ask: look at the queue
    in: goal.short.off
    out: flow.escalated
"""


def project(tmp_path, text=MODEL):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def codes(p, now):
    return {f.code: f for f in watch.find(p, p.model.spec, now=now)}


def test_heading_for_a_limit_says_when(tmp_path):
    p = project(tmp_path)
    now = time.time()
    for i in range(10):                                    # 2% an hour, at 60%: 20h to go
        p.measurements.add("sensor/disk.main", 42 + 2 * i, now - (9 - i) * 3600)
    f = codes(p, now)["heading-for-limit"]
    assert "no goal guards it" in f.message and "in 20h" in f.message


def test_saturating_and_critical_unowned(tmp_path):
    text = MODEL.split("  oncall:")[0]
    p = project(tmp_path, text)
    now = time.time()
    for _ in range(4):
        p.events.add("agent.ran", item="worker", data={"commanded": 5.0, "moved": {"served": 1.0}})
    got = codes(p, now + 1)
    assert "saturating" in got and "critical-unowned" in got


def test_a_person_asked_long_ago_is_not_answering(tmp_path):
    p = project(tmp_path)
    p.events.add("person.asked", item="oncall", data={"command": 1})
    got = codes(p, time.time() + 2 * 3600)
    assert "not-answering" in got and "--done" in got["not-answering"].message


def test_recoveries():
    ev = [{"type": "loop.off", "time": 0}, {"type": "loop.holding", "time": 30},
          {"type": "loop.off", "time": 100}, {"type": "loop.holding", "time": 160}]
    assert watch.recoveries(ev) == [30, 60]
