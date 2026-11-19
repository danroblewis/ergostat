"""The closed-loop projection (numbers/closedloop.py): the control structure run forward beside the stocks and flows.
Built-ins decide as the engine decides, a machine block's stand-in is identified from its record, an on/off drain
loop settles where theory says, the risk is the same from the same seed, and the what-ifs reach it."""

from __future__ import annotations

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.numbers import closedloop as cl
from ergostat.numbers import observe as ob
from ergostat.numbers import simulate as sim
from ergostat.spec.engine import Engine
from ergostat.store import Project


def project_of(tmp_path, text: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


# ---- the built-ins decide here as the engine decides

BUILTINS = """\
name: b
stocks:
  queue:
    unit: jobs
    sensor: {manual: true}
  backlog:
    unit: jobs
    sensor: {manual: true}
goals:
  queue-short:
    stock: queue
    hold: "<= 20"
    tolerance: 2
  backlog-short:
    stock: backlog
    hold: "<= 50"
blocks:
  keep:
    type: onoff
    goal: queue-short
    until: "<= 10"
    min-on: 30s
    out: block.worker
  limiter:
    type: limit
    in: stock.queue
    max: 25
    rate: 3600
  later:
    type: delay
    in: block.limiter
    delay: 20s
  big:
    type: compare
    in: stock.queue
    above: 15
    back-below: 12
  times:
    type: counter
    in: block.big
  cascade:
    type: expr
    in: {b: stock.backlog}
    expr: 10 + b / 10
    out: goal.queue-short
  worker:
    type: program
    run: "true"
    in: block.keep
    out: block.nothing
  nothing:
    type: program
    run: "true"
"""


def test_built_ins_decide_exactly_as_the_engine_does(tmp_path):
    p = project_of(tmp_path, BUILTINS)
    spec = p.model.spec
    e = Engine(p, say=lambda s: None)
    signals: dict = {}
    sh = cl.Shadow(spec, signals)
    t0 = 1_800_000_000.0
    levels = [0, 5, 12, 18, 23, 27, 24, 19, 14, 9, 6, 11, 16, 22, 30, 21, 13, 8, 4, 2]
    for i, q in enumerate(levels * 3):
        now = t0 + i * 7.0
        for sig in (e.signals, signals):
            sig["stock.queue"], sig["stock.backlog"] = float(q), float(40 + i)
        e.goals(now, out=[])
        _, set_goals, _ = e._builtins(now, None, {}, [], [])
        if set_goals:
            e.goals(now, out=[])
        sh.step(now)
        for name in ("keep", "limiter", "later", "big", "times", "cascade"):
            assert signals.get(f"block.{name}") == e.signals.get(f"block.{name}"), (i, name)
        for g in spec.goals:
            assert signals.get(f"goal.{g}.off") == e.signals.get(f"goal.{g}.off"), (i, g)
            assert sh.setpoint.get(g) == e.setpoint.get(g)
        assert sh.on("worker") == bool(e.command_of(spec.blocks["worker"])[0])
    assert e.status == sh.status and signals["block.times"] > 0


def test_the_engines_own_pass_and_the_shadow_agree_on_a_reading(tmp_path):
    """The engine's whole pass (``evaluate``), reading what was measured, leaves its built-ins where the shadow's pass
    does from the same values."""
    p = project_of(tmp_path, BUILTINS)
    spec = p.model.spec
    e = Engine(p, say=lambda s: None)
    e.machines = []                                     # nothing is run: only the pass
    now = time.time()
    p.measurements.add("sensor/queue.main", 27.0, at=now - 1)
    p.measurements.add("sensor/backlog.main", 300.0, at=now - 1)
    e.evaluate(full=True)
    signals = {"stock.queue": 27.0, "stock.backlog": 300.0}
    sh = cl.Shadow(spec, signals)
    sh.step(now)
    for name in ("keep", "big", "cascade", "limiter"):
        assert signals[f"block.{name}"] == e.signals[f"block.{name}"]
    assert sh.setpoint["queue-short"] == e.setpoint["queue-short"] == 40.0
    assert signals["goal.queue-short.off"] == e.signals["goal.queue-short.off"] == 0.0


# ---- a machine block's stand-in, identified from its record

DRAIN = """\
name: d
stocks:
  queue:
    unit: jobs
    sensor: {manual: true}
flows:
  arrivals:
    to: queue
    sensor: {manual: true}
  served:
    from: queue
    sensor: {manual: true}
blocks:
  worker:
    type: program
    run: "true"
    in: [+stock.queue]
    every: 30s
    out: flow.served
"""


def test_a_draining_blocks_stand_in_is_little_s_law_from_its_record(tmp_path):
    p = project_of(tmp_path, DRAIN)
    now = time.time()
    q, tau = 4.0, 0.5                                   # it moves what waits in half an hour, on average
    for i in range(241):
        t = now - 7200 + i * 30
        a = 10 + 6 * ((i // 30) % 2)
        p.measurements.add("sensor/queue.main", q, at=t)
        p.measurements.add("sensor/arrivals.main", a, at=t)
        p.measurements.add("sensor/served.main", q / tau, at=t)
        q += (a - q / tau) * 30 / 3600
    for i in range(12):
        p.events.add("agent.ran", item="worker", data={"exit": 0, "seconds": 2.0}, at=now - 3600 + i * 300)
    got = cl.identify(p, p.model.spec, ob.measured(p, ob.Grid(now - 7200, now, 120)))
    s = got["flow.served"]
    assert s.form == "drain" and not s.assumed and s.gate is None
    assert s.tau == pytest.approx(tau, rel=0.1)
    assert "draining queue" in s.said and "12 runs" in s.said and s.se["tau"] > 0


TAKES = """\
name: t
items:
  job:
    id: job/*
    states: [ready, done]
    on: {job.done: done}
stocks:
  ready:
    unit: jobs
    sensor: {items: job, state: ready, every: 5s}
flows:
  arrivals:
    to: ready
    sensor: {manual: true}
  worked:
    from: ready
    sensor: {items: job, entering: done, over: 10m}
blocks:
  developer:
    type: program
    run: "true"
    takes: {kind: job, at: ready, to: [done]}
    pool: 3
    lease: {ttl: 30m}
    out: flow.worked
"""


def test_a_block_that_takes_items_is_seats_from_its_runs(tmp_path):
    p = project_of(tmp_path, TAKES)
    now = time.time()
    for i in range(20):                                 # 20 runs of 20 minutes; 4 failed
        p.events.add("agent.failed" if i % 5 == 4 else "agent.ran", item="developer",
                      data={"exit": 1 if i % 5 == 4 else 0, "seconds": 1200.0, "item": f"job/{i}"}, at=now - 3000 + i * 100)
    s = cl.identify(p, p.model.spec, ob.measured(p, ob.Grid(now - 3600, now, 60)))["flow.worked"]
    assert s.form == "seats" and s.seats == 3 and not s.assumed
    assert s.service == pytest.approx(1 / 3) and s.success == pytest.approx(0.8) and s.ttl == pytest.approx(0.5)
    assert "3 seats" in s.said and "80% success" in s.said and "20 runs" in s.said
    # its rate: 0.8 × min(waiting, 3) / (20 min): 7.2 an hour once three or more wait
    assert s.rate({"stock.ready": 10.0}, True) == pytest.approx(7.2)
    assert s.rate({"stock.ready": 1.0}, True) == pytest.approx(2.4)
    assert s.rate({"stock.ready": 10.0}, False) == 0.0
    (tmp_path / "few").mkdir()
    few = project_of(tmp_path / "few", TAKES)
    a = cl.identify(few, few.model.spec, ob.measured(few, ob.Grid(now - 3600, now, 60)))["flow.worked"]
    assert a.assumed and "assumed" in a.said


# ---- the loop run forward: an on/off drain settles where theory says

ONOFF = """\
name: o
stocks:
  queue:
    unit: jobs
    sensor: {manual: true}
flows:
  arrivals:
    to: queue
    sensor: {manual: true}
  served:
    from: queue
goals:
  queue-short:
    stock: queue
    hold: "<= 20"
blocks:
  keep:
    type: onoff
    goal: queue-short
    until: "<= 10"
    out: block.worker
  worker:
    type: program
    run: "true"
    in: block.keep
    out: flow.served
"""


def onoff_run(tmp_path, horizon_h: float = 6.0, whatif: cl.WhatIf | None = None, cap: float = 30.0):
    p = project_of(tmp_path, ONOFF)
    spec = p.model.spec
    now = time.time()
    for i in range(61):                                 # an hour of record: arrivals 10 an hour, the queue at 25 now
        p.measurements.add("sensor/arrivals.main", 10.0, at=now - 3600 + i * 60)
        p.measurements.add("sensor/queue.main", 25.0, at=now - 3600 + i * 60)
    data = ob.measured(p, ob.Grid(now - 3600, now, 60))
    run = sim.replay(spec, data)
    worker = cl.StandIn("worker", "flow.served", "drain", gate="keep", source="queue", tau=1e-4, cap=cap,
                        said="worker modelled as draining queue at most 30/h")
    start = cl.Start(status={"queue-short": "off"}, outputs={"keep": (now - 60, 1.0)})
    got = cl.closed(spec, data, run, horizon_h * 3600, None, 360, {"flow.served": worker}, start, whatif=whatif)
    return spec, data, run, got


def test_an_onoff_drain_loop_settles_between_its_release_point_and_its_setpoint(tmp_path):
    """Arrivals 10 an hour; the worker drains at 30 an hour while on; on at 20, off at 10. From 25 the queue falls at 20
    an hour to 10 (in 45 minutes), then cycles: an hour rising to 20, half an hour falling to 10."""
    spec, data, run, got = onoff_run(tmp_path)
    q = got.values["stock.queue"]
    times = [(t - data.grid.until) / 3600 for t in got.times]
    at = {round(h, 3): v for h, v in zip(times, q, strict=True)}
    assert at[0.75] == pytest.approx(10.0, abs=0.3)                 # (25 − 10) / (30 − 10)
    later = [v for h, v in zip(times, q, strict=True) if h > 1.0]
    assert min(later) == pytest.approx(10.0, abs=0.3) and max(later) == pytest.approx(20.0, abs=0.3)
    assert sum(later) / len(later) == pytest.approx(15.0, abs=0.6)   # a sawtooth between 10 and 20
    served = [v for h, v in zip(times, got.values["flow.served"], strict=True) if 0.75 < h <= 5.25]   # three whole cycles
    assert sum(served) / len(served) == pytest.approx(10.0, rel=0.03)   # what comes in goes out
    assert got.off_hours["queue-short"] == pytest.approx(0.25, abs=0.05) and got.valid   # off only until it falls past 20
    held = sim.project(spec, data, run, 6 * 3600, points=360, held=set())
    assert held.values["stock.queue"][-1] > 80                       # held: nothing drains it
    assert any("stand-in" in n for n in got.notes)


def test_arrivals_doubled_the_queue_grows_and_the_controller_saturates(tmp_path):
    """Extreme conditions: arrivals of 40 an hour against a worker of 30: the goal goes off, the worker runs flat out,
    and the queue grows at the difference."""
    _, data, _, got = onoff_run(tmp_path, whatif=cl.WhatIf(flows={"flow.arrivals": ("x", 4.0)}))
    q = got.values["stock.queue"]
    assert q[-1] == pytest.approx(25 + 6 * 10, abs=1.0)
    assert all(v == pytest.approx(30.0, rel=0.01) for v in got.values["flow.served"])
    assert got.off_end["queue-short"][-1] == 1 and got.off_hours["queue-short"] == pytest.approx(6.0, abs=0.05)


def test_a_setpoint_tried_moves_where_the_loop_settles(tmp_path):
    _, _, _, got = onoff_run(tmp_path, whatif=cl.WhatIf(setpoints={"queue-short": 40.0}))
    q = got.values["stock.queue"]
    assert max(q) == pytest.approx(40.0, abs=0.3) and min(q[100:]) == pytest.approx(10.0, abs=0.3)


# ---- risk: the same seed, the same answer

def test_risk_is_reproducible_with_a_seed_and_bounded(tmp_path):
    spec, data, run, _ = onoff_run(tmp_path)
    now = data.grid.until
    worker = cl.StandIn("worker", "flow.served", "drain", gate="keep", source="queue", tau=1e-4, cap=30.0, se={"cap": 6.0})
    start = cl.Start(status={"queue-short": "off"}, outputs={"keep": (now - 60, 1.0)})
    args = (spec, data, run, 6 * 3600, 48, {"flow.served": worker}, start)
    a = cl.risk(*args, runs=40, seed=7)
    b = cl.risk(*args, runs=40, seed=7)
    c = cl.risk(*args, runs=40, seed=8)
    assert a["goals"] == b["goals"] and a["bands"] == b["bands"]
    assert a["bands"] != c["bands"]
    assert a["runs"] == 40 and not a["stopped"]
    x = a["goals"]["queue-short"]
    assert 0.0 <= x["p_off_end"] <= 1.0 and x["expected_off"] >= 0 and len(x["p_off"]) == 48
    assert "worker.cap" in {u["name"] for u in a["sampled"]}
    said = cl.risk_said(spec, a, "queue-short")
    assert said.startswith("queue-short: ") and "(40 runs)" in said
    capped = cl.risk(*args, runs=10_000, seed=7, budget=0.3)
    assert capped["asked"] == cl.MOST_RUNS and capped["stopped"] and capped["made"] < cl.MOST_RUNS


# ---- the what-ifs, on the page's API

def test_the_page_projects_with_the_loops_running_and_tries_what_ifs(tmp_path):
    from ergostat.web.server import Live, api
    p = project_of(tmp_path, ONOFF)
    now = time.time()
    for i in range(121):
        t = now - 7200 + i * 60
        p.measurements.add("sensor/arrivals.main", 10.0, at=t)
        p.measurements.add("sensor/queue.main", 12.0 + (i % 40) / 4, at=t)
        p.measurements.add("block/keep", float((i // 20) % 2), at=t)
    for i in range(30):
        p.events.add("agent.ran", item="worker", data={"exit": 0, "seconds": 1.0}, at=now - 7000 + i * 200)
    live = Live(p)
    q = {"since": ["2h"], "refs": ["stock.queue"], "strip": ["1"], "replay": ["1"]}
    got = api(live, "series", q)
    assert got["loops"] == "closed" and got["loops_can_close"] and "with the loops running" in got["inputs"]
    assert any("worker" in x for x in got["standins"])
    held = api(live, "series", {**q, "loops": ["held"]})
    assert held["loops"] == "held" and "open loop" in held["inputs"]
    s = {x["ref"]: x for x in api(live, "series", {**q, "whatif": ["flow.arrivals:x3"]})["series"]}
    assert s["stock.queue"]["whatif_projection"][-1] > s["stock.queue"]["projection"][-1]
    assert api(live, "series", {**q, "whatif": ["goal.nope:1"]})["whatif_error"]
    assert "only with the loops running" in api(live, "series", {**q, "loops": ["held"], "whatif": ["goal.queue-short:5"]})["whatif_error"]
    rk = api(live, "risk", {"since": ["2h"], "goal": ["queue-short"]})
    said = rk["goals"][0]["said"]
    assert rk["goals"][0]["goal"] == "queue-short" and rk["runs"] > 0 and ("p≈" in said or "holding" in said)
    si = api(live, "standins", {"since": ["2h"], "block": ["worker"]})
    assert si["standins"][0]["block"] == "worker" and si["standins"][0]["said"]
    assert api(live, "whatif-fit", {"since": ["2h"], "whatif": ["goal.queue-short:5"]}) == {}


def test_parse_whatif_splits_parameters_from_what_only_the_closed_loop_tries(tmp_path):
    p = project_of(tmp_path, TAKES)
    params, w = cl.parse_whatif(p.model.spec, {"k": "2", "flow.arrivals": "x2", "block.developer.pool": "5"})
    assert params == {"k": "2"} and w.flows == {"flow.arrivals": ("x", 2.0)} and w.pools == {"developer": 5}
    for bad in ({"flow.nope": "1"}, {"block.developer.pool": "0"}, {"goal.x": "1"}, {"flow.arrivals": "fast"}):
        with pytest.raises(cl.WhatIfError):
            cl.parse_whatif(p.model.spec, bad)


PERSON = """\
name: p
stocks:
  waiting:
    unit: notes
    sensor: {manual: true}
flows:
  answered:
    from: waiting
    sensor: {manual: true}
goals:
  none-late:
    stock: waiting
    hold: "<= 50"
blocks:
  me:
    type: person
    goal: none-late
    ask: answer them
    out: flow.answered
"""


def test_a_block_that_moves_while_nothing_commands_it_is_not_gated_by_its_command(tmp_path):
    """A person answers before being asked: the record shows the flow moving while the goal held and the on/off in front
    of the person was off. The stand-in is then what the flow did, whether or not it was commanded, and says so."""
    p = project_of(tmp_path, PERSON)
    now = time.time()
    p.measurements.add("block/keep-none-late", 0.0, at=now - 7300)
    for i in range(121):
        t = now - 7200 + i * 60
        p.measurements.add("sensor/waiting.main", 4.0, at=t)
        p.measurements.add("sensor/answered.main", 2.0, at=t)
    s = cl.identify(p, p.model.spec, ob.measured(p, ob.Grid(now - 7200, now, 60)))["flow.answered"]
    assert s.gate is None and s.form == "drain" and not s.assumed
    assert s.tau == pytest.approx(2.0, rel=0.05) and "whether or not keep-none-late commands it" in s.said
