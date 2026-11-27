"""A sensor daemon's observations (SPEC §9.7): event lines about items, and relayed messages, tagged with the sensor
that saw them; recorded as a ``run:`` sensor's are, from that sensor; capped at 50 a second, the drops said once."""

import json
import threading
import time

import pytest

from ergostat.daemons import observe
from ergostat.messages.record import MESSAGE
from ergostat.spec.engine import observations

from .test_leases import item, project, start, wait_for

CASES = """
name: s
projections:
  case:
    id: case/*
    states: [open, met]
    on: {case.met: met}
stocks:
  q:
    unit: things
    sensor: {daemon: {run: python3 o.py}, push: true}
  r:
    unit: things
    sensor: {daemon: {run: python3 other.py}, push: true}
"""

BEAT = ("import sys, threading, time\n"
        "def beat():\n    while True:\n        print('{\"heartbeat\": true}', flush=True); time.sleep(0.2)\n"
        "threading.Thread(target=beat, daemon=True).start()\n"
        "for line in sys.stdin:\n    if 'stop' in line:\n        break\n")
QUIET = BEAT


def setup(tmp_path, script: str):
    (tmp_path / "o.py").write_text(script)
    (tmp_path / "other.py").write_text(QUIET)
    return project(tmp_path, CASES)


def events(p, t, source=None):
    return p.events.query(n=None, type=t, source=source)


def refused(p):
    return [x["data"] for x in events(p, "sensor.refused")]


def met(i=0):
    return {"event": "case.met", "item": f"case/n{i}", "data": {"i": i}, "sensor": "q.main"}


def say(lines):
    return f"import json, sys\nsys.stdout.write(''.join(json.dumps(o) + '\\n' for o in {lines!r})); sys.stdout.flush()\n" \
           + BEAT


def mine(e):
    """The daemon of sensor q.main, as the supervisor names it."""
    assert wait_for(lambda: any(s == "q.main" for _, s in e.daemons.observers), 5)
    return next(d for d, s in e.daemons.observers if s == "q.main")


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(observe, "_now", lambda: now[0])
    return now


def test_a_sensor_daemons_observations_are_recorded_from_its_sensor(tmp_path):
    p = setup(tmp_path, say([{"reading": 3, "sensor": "q.main"},
                             {"event": "case.met", "item": "case/a", "data": {"x": 1}, "sensor": "q.main"},
                             {"message": {"text": "that review can wait", "by": "me"}, "sensor": "q.main"}]))
    e = start(p)
    try:
        assert wait_for(lambda: events(p, "case.met") and events(p, f"{MESSAGE}.received"), 10)
    finally:
        e.close()
    got = events(p, "case.met")
    assert len(got) == 1 and got[0]["source"] == "q.main" and got[0]["item"] == "case/a"
    it = item(p, "case/a")
    assert it.state == "met" and it.fields.get("x") == 1
    msg = events(p, f"{MESSAGE}.received")
    assert len(msg) == 1 and msg[0]["data"]["via"] == "sensor q.main" and msg[0]["data"]["text"] == "that review can wait"
    assert "dropped" not in (p.dir / "logs" / "daemon-sensor.q.main.log").read_text()


def test_an_observation_for_a_sensor_not_of_this_daemon_is_stray_not_recorded(tmp_path):
    p = setup(tmp_path, say([{"event": "case.met", "item": "case/a", "sensor": "nope.main"},
                             {"event": "case.met", "item": "case/b", "sensor": "r.main"},
                             {"message": {"text": "hi"}, "sensor": "r.main"},
                             {"event": "case.met", "item": "case/c", "sensor": 7},
                             {"event": "case.met", "item": "case/d", "sensor": "q.main", "reading": 1},
                             {"reading": 2, "sensor": "q.main"}]))
    e = start(p)
    log = p.dir / "logs" / "daemon-sensor.q.main.log"
    try:
        assert wait_for(lambda: log.exists() and log.read_text().count("dropped") >= 5, 10)
        assert wait_for(lambda: p.measurements.latest("sensor/q.main", time.time()), 5)
    finally:
        e.close()
    assert not events(p, "case.met") and not events(p, f"{MESSAGE}.received"), "never recorded under any source"
    text = log.read_text()
    assert text.count("an observation for no sensor of its own") == 4
    assert "a reading or an observation, not both" in text


def test_an_observation_neither_taken_nor_refused_is_stray_and_not_counted(tmp_path, clock):
    """Lesson-3 (review 2): a line observations() neither takes nor refuses ({"message": "text"}) is the log's, and
    never counts against the cap: with it counted, the 50 good lines after it would see drops."""
    p = setup(tmp_path, say([{"message": "just text", "sensor": "q.main"}]))
    e = start(p)
    log = p.dir / "logs" / "daemon-sensor.q.main.log"
    try:
        assert wait_for(lambda: log.exists() and "not one in shape" in log.read_text(), 10)
        d = mine(e)
        for o in ({"message": 5, "sensor": "q.main"}, {"message": "text", "sensor": "q.main"}):
            assert e.daemons._observed(d, "q.main", o) is False
        for i in range(50):
            e.daemons._observed(d, "q.main", met(i))
        clock[0] = 101.0
        e.daemons.flush_observed()
        assert len(events(p, "case.met")) == 50 and not refused(p), "not counted, so nothing dropped"
    finally:
        e.close()


def test_a_refused_observation_is_said_as_for_a_run_sensor(tmp_path, clock):
    p = setup(tmp_path, QUIET)
    e = start(p)
    try:
        d = mine(e)
        bad = [{"event": "case.met", "item": "noslash", "sensor": "q.main"},
               {"event": "agent.ran", "item": "case/a", "sensor": "q.main"}]
        for o in bad:
            assert e.daemons._observed(d, "q.main", o)
    finally:
        e.close()
    want = [observations(json.dumps({k: v for k, v in o.items() if k != "sensor"}))[1][0] for o in bad]
    assert [x["why"] for x in refused(p)] == want
    assert not events(p, "case.met") and not events(p, "agent.ran", source="q.main")


def test_more_than_50_observations_a_second_are_capped_and_the_drop_reported_once(tmp_path, clock):
    p = setup(tmp_path, QUIET)
    e = start(p)
    try:
        d = mine(e)
        for i in range(60):
            e.daemons._observed(d, "q.main", met(i))
        assert len(events(p, "case.met")) == 50 and not refused(p), "50 taken, the drops not yet said"
        clock[0] = 101.0
        e.daemons.flush_observed()
        assert [x.get("dropped") for x in refused(p)] == [10]
        assert refused(p)[0]["why"] == "10 observations dropped: more than 50 a second"
        e.daemons.flush_observed()
        assert len(refused(p)) == 1, "said once"
        for i in range(50):
            e.daemons._observed(d, "q.main", met(100 + i))
        assert len(events(p, "case.met")) == 100 and len(refused(p)) == 1
    finally:
        e.close()


def test_the_window_is_judged_and_written_under_its_lock(tmp_path, clock, monkeypatch):
    """lesson-1: a competing line and a competing flush, each put in the gap between judging the window and writing
    it. Without ``Observed.lock`` the 50th line lets a 51st through and one window's drops are said twice."""
    p = setup(tmp_path, QUIET)
    e = start(p)
    decide, rivals = observe.Observed._decide, []

    def gap(rival):
        def wrapped(w, now):
            got = decide(w, now)
            monkeypatch.setattr(observe.Observed, "_decide", staticmethod(decide))
            t = threading.Thread(target=rival)
            t.start()
            t.join(0.3)                              # (held: it waits for the lock; else it runs in the gap)
            rivals.append(t)
            return got
        monkeypatch.setattr(observe.Observed, "_decide", staticmethod(wrapped))

    try:
        d = mine(e)
        e.daemons.tick = lambda: None                # (its loop's flush never takes the window before the rival)
        for i in range(49):
            e.daemons._observed(d, "q.main", met(i))
        gap(lambda: e.daemons._observed(d, "q.main", met(99)))
        for i in range(49, 59):                      # the 50th (with its rival in the gap), then 9 more: 60
            e.daemons._observed(d, "q.main", met(i))
        rivals[-1].join(5)
        assert len(events(p, "case.met")) == 50
        clock[0] = 101.0
        gap(lambda: e.daemons.flush_observed())
        e.daemons._observed(d, "q.main", met(200))   # closes the window, its rival flushing in the gap
        rivals[-1].join(5)
        e.daemons.flush_observed()
        assert [x.get("dropped") for x in refused(p)] == [10]
    finally:
        e.close()


def test_a_burst_with_nothing_after_it_is_reported_by_the_supervisor(tmp_path):
    p = setup(tmp_path, say([met(i) for i in range(60)]))
    e = start(p)
    try:
        assert wait_for(lambda: any(x.get("dropped") for x in refused(p)), 5), "said by the tick, nothing after it"
        assert len(events(p, "case.met")) == 50
    finally:
        e.close()
    assert [x.get("dropped") for x in refused(p)] == [10]


def test_a_reads_observations_are_judged_at_the_time_it_was_read(tmp_path, clock):
    """Review 1 (lesson-10): 60 lines of one read, the clock moving 0.03 s with each one recorded (as a loaded
    machine's would). Judged when each is recorded, the window would close at the 34th and nothing be dropped."""
    p = setup(tmp_path, QUIET)
    e = start(p)
    try:
        d = mine(e)
        e.daemons.tick = lambda: None
        record = e._observer

        def slow(name):
            def put(*a):
                clock[0] += 0.03
                return record(name)(*a)
            return put
        e._observer = slow
        proc = e.daemons.slots[d].proc
        proc.chunk(b"".join(json.dumps(met(i)).encode() + b"\n" for i in range(60)))
        assert len(events(p, "case.met")) == 50
        e.daemons.flush_observed()
        assert [x.get("dropped") for x in refused(p)] == [10]
    finally:
        e.close()


def test_a_line_after_the_stops_flush_is_logged_not_counted(tmp_path, clock):
    """Review 1: a line read after ``close`` said the drops opens no window whose drops would never be said."""
    p = setup(tmp_path, QUIET)
    e = start(p)
    d = mine(e)
    e.close()
    assert not e.daemons._observed(d, "q.main", met(1))
    assert not e.daemons.observed.windows and not events(p, "case.met")


def test_a_burst_just_before_ergostat_stops_is_reported_at_close(tmp_path, clock):
    p = setup(tmp_path, QUIET)
    e = start(p)
    d = mine(e)
    for i in range(60):
        e.daemons._observed(d, "q.main", met(i))
    e.daemons.tick()                                 # (the window still open: nothing said)
    assert not refused(p)
    e.close()
    got = events(p, "sensor.refused")
    assert [x["data"].get("dropped") for x in got] == [10]
    stopped = events(p, "ergostat.stopped")
    assert stopped and got[0]["seq"] < stopped[-1]["seq"], "said before the record of ergostat's stop"
