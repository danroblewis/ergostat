"""The observer (spec/observer.py, SPEC §9.6): a reading's staleness and what a goal or block does about it; each
stock's estimate between readings, its uncertainty and innovations; the model found disagreeing with a stock; and no
change for a model that uses none of it."""

from __future__ import annotations

import math
import random
import shutil
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import state
from ergostat.spec import observer as ob
from ergostat.spec import watch
from ergostat.spec.engine import Engine
from ergostat.store import Project
from tests.test_rollup import EXAMPLES

T0 = 1_800_000_000.0

QUEUE = """
name: t
stocks:
  queue:
    unit: jobs
    sensor: {run: "echo 0", every: 10s}
flows:
  served:
    from: queue
goals:
  short:
    stock: queue
    hold: "<= 5"
    POLICY
blocks:
  keep:
    type: onoff
    goal: short
    out: block.worker
  push:
    type: proportional
    goal: short
    gain: 1
    BLOCKPOLICY
    out: block.worker
  worker:
    type: program
    run: "true"
    in: [block.keep, block.push, stock.queue]
    out: flow.served
"""


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self) -> float:
        return self.t


def _engine(tmp_path, text: str, monkeypatch, clock: Clock | None = None) -> Engine:
    clock = clock or Clock()
    monkeypatch.setattr(time, "time", clock)
    monkeypatch.setattr(time, "monotonic", clock)              # (no sleep: the wall clock and the monotonic move together)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    p = Project(mdl.load(tmp_path))
    assert not [x for x in p.model.problems if x.level == "error"], p.model.problems
    e = Engine(p, say=lambda s: None)
    e.clock, e.started = clock, []

    def start(b, why):                                     # nothing runs: what would start is recorded
        e.started.append(b.name)
    e.start = start
    return e


def _read(e: Engine, series: str, value: float, at: float | None = None) -> None:
    e.p.measurements.add(series, value, e.clock.t if at is None else at)


def _queue(tmp_path, monkeypatch, policy: str = "", block_policy: str = "") -> Engine:
    text = QUEUE.replace("POLICY", f"on-stale: {policy}" if policy else "", 1) \
        .replace("BLOCKPOLICY", f"on-stale: {block_policy}" if block_policy else "")
    return _engine(tmp_path, text, monkeypatch)


@pytest.mark.parametrize("policy", ["act", "hold", "off"])
def test_a_stale_reading_turns_a_goal_stale_for_each_policy(tmp_path, monkeypatch, policy):
    from ergostat import runner
    monkeypatch.setattr(runner, "running_pid", lambda p, wait=True: 4242)    # (the page says stale only while it runs)
    e = _queue(tmp_path, monkeypatch, policy)
    _read(e, "sensor/queue.main", 10)                      # fresh, and off its goal: the onoff acts
    e.evaluate(tick=True)
    assert e.signals["goal.short.off"] == 1 and e.signals["block.keep"] == 1 and not e.stale
    e.clock.t += 100                                       # a reading of 2 lands, taken 95 s ago: older than 3 x 10 s
    _read(e, "sensor/queue.main", 2, T0 + 5)
    e.evaluate(tick=True)
    assert e.stale.get("short") == pytest.approx(95)
    went = e.p.events.query(n=None, type="ergostat.goal.stale", item="short")
    assert len(went) == 1 and went[0]["data"]["on_stale"] == policy
    snap = state.snapshot(e.p, now=e.clock.t)
    assert snap["loops"]["short"]["status"] == "stale" and snap["loops"]["short"]["on_stale"] == policy
    assert any(a["what"] == "goal short" and "stale" in a["says"] for a in state.attention(snap, True, e.p.model))
    expect = {"act": (0.0, 0.0), "hold": (1.0, 1.0), "off": (1.0, 1.0)}[policy]   # (the goal's .off, the onoff's output)
    assert (e.signals["goal.short.off"], e.signals["block.keep"]) == expect
    assert bool(e.p.events.query(n=None, type="loop.holding", item="short")) == (policy == "act")
    e.clock.t += 1                                         # read again: fresh, holding under every policy
    _read(e, "sensor/queue.main", 2)
    e.evaluate(tick=True)
    assert not e.stale and e.signals["goal.short.off"] == 0 and e.signals["block.keep"] == 0
    assert e.p.events.query(n=None, type="ergostat.goal.fresh", item="short")
    e.clock.t += 100                                       # no reading at all: stale while it holds
    e.evaluate(tick=True)
    assert "short" in e.stale
    assert e.signals["goal.short.off"] == (1.0 if policy == "off" else 0.0)
    assert e.signals["block.keep"] == (1.0 if policy == "off" else 0.0)


def test_a_block_on_stale_hold_keeps_its_last_command(tmp_path, monkeypatch):
    out = {}
    for policy in ("act", "hold"):
        e = _queue(tmp_path / policy, monkeypatch, block_policy=policy)
        _read(e, "sensor/queue.main", 10)
        e.evaluate(tick=True)
        assert e.signals["block.push"] == 5                # gain x |error|
        e.clock.t += 100
        _read(e, "sensor/queue.main", 20, T0 + 5)          # stale, and further off
        e.evaluate(tick=True)
        out[policy] = e.signals["block.push"]
    assert out == {"act": 15, "hold": 5}


def test_a_machine_blocks_input_names_its_stale_readings(tmp_path, monkeypatch):
    e = _queue(tmp_path, monkeypatch, "act")
    _read(e, "sensor/queue.main", 10)
    e.evaluate(tick=True)
    worker = e.spec.blocks["worker"]
    assert "stale" not in e.context(worker, "command")
    e.clock.t += 100
    e.evaluate(tick=True)
    ctx = e.context(worker, "command")
    assert ctx["stale"] == {"stock.queue": 100.0}
    assert ctx["inputs"]["stock.queue"] == 10              # it still reads the measured value (act: as before)


TANK = """
name: tank
parameters:
  k: {value: K, unit: 1/h}
stocks:
  tank:
    unit: litres
    sensor: {run: "echo 0", every: 30m}
flows:
  filling:
    to: tank
    sensor: {manual: true}
  draining:
    from: tank
    driven-by: +stock.tank
    equation: k * stock.tank
blocks:
  watch:
    type: expr
    in: {e: stock.tank.estimate, u: stock.tank.uncertainty}
    expr: e + u
"""


def _tank(tmp_path, monkeypatch, k_model: float = 0.5, k_true: float = 0.5, noise: float = 0.5, hours: float = 24,
          seed: int = 1) -> tuple[Engine, list[tuple[float, float, float, float]]]:
    """A tank filled at a varying, measured rate and drained at k_true an hour of what is in it, read every 30 min with
    noise; the model drains it at k_model. Passes every minute. Returns the engine and (t, truth, estimate, last reading)."""
    e = _engine(tmp_path, TANK.replace("K", str(k_model)), monkeypatch)
    rnd = random.Random(seed)
    x, last, rows = 40.0, None, []
    for i in range(int(hours * 60) + 1):
        t = i / 60.0
        f = 20 + 10 * math.sin(2 * math.pi * t / 6)
        _read(e, "sensor/filling.main", f)
        if i % 30 == 0:
            last = x + rnd.gauss(0, noise)
            _read(e, "sensor/tank.main", last)
        e.evaluate(tick=True)
        rows.append((t, x, e.signals["stock.tank.estimate"], last))
        for _ in range(10):                                # the truth, finely
            x += (f - k_true * x) / 600
        e.clock.t += 60
    return e, rows


def test_the_estimate_tracks_a_stock_between_sparse_readings_better_than_the_last_reading(tmp_path, monkeypatch):
    e, rows = _tank(tmp_path, monkeypatch)
    late = [r for r in rows if r[0] >= 4]                  # once the gain is learnt
    rms = lambda i: math.sqrt(sum((r[i] - r[1]) ** 2 for r in late) / len(late))   # noqa: E731
    est, held = rms(2), rms(3)
    tr = e.observer.tracks["tank"]
    print(f"estimate rms {est:.3f}, last reading rms {held:.3f} ({held / est:.1f}x); gain {tr.k:.3f}, "
          f"noise sd {math.sqrt(tr.r):.3f}, model error sd/h {math.sqrt(max(tr.q, 0)):.3f}")
    assert est < held / 3
    assert e.signals["block.watch"] == pytest.approx(e.signals["stock.tank.estimate"] + e.signals["stock.tank.uncertainty"])


def test_a_block_reads_the_estimate_and_its_uncertainty(tmp_path, monkeypatch):
    e, rows = _tank(tmp_path, monkeypatch, hours=6)
    tr = e.observer.tracks["tank"]
    after = tr.uncertainty(tr.last)
    assert tr.uncertainty(tr.last + 1800) > after          # it grows between readings, by the model's error
    assert e.signals["stock.tank.uncertainty"] > 0 and e.signals["block.watch"] is not None


def test_the_gain_comes_from_the_sensor_noise_and_the_model_error():
    """A random walk read with noise: the noise's and the walk's variances found from the open-loop errors alone,
    and the gain the steady state's for them."""
    rnd = random.Random(7)
    sv, sw, T = 2.0, 1.0, 0.5                               # sensor sd; the model's error sd per sqrt(hour); hours apart
    x, y_prev, errors = 0.0, None, []
    for _ in range(20000):
        x += rnd.gauss(0, sw * math.sqrt(T))
        y = x + rnd.gauss(0, sv)
        if y_prev is not None:
            errors.append(y - y_prev)
        y_prev = y
    r, q, k = ob.gain(errors, [T] * len(errors))
    assert r == pytest.approx(sv ** 2, rel=0.1) and q == pytest.approx(sw ** 2, rel=0.15)
    a = sw ** 2 * T
    p = (a + math.sqrt(a * a + 4 * a * sv ** 2)) / 2
    assert k == pytest.approx(p / (p + sv ** 2), rel=0.1)
    print(f"gain {k:.3f} (true {p / (p + sv ** 2):.3f})")
    assert ob.gain(errors[:3], [T] * 3) == (0.0, 0.0, 1.0)  # too few: each reading taken whole
    assert ob.gain([1.0] * 10, [T] * 10)[2] == 1.0          # no noise at all: the reading is the truth


def test_innovations_are_recorded_as_a_series(tmp_path, monkeypatch):
    e, rows = _tank(tmp_path, monkeypatch, hours=6)
    got = e.p.measurements.range("observer/tank/innovation", 0)
    readings = e.p.measurements.range("sensor/tank.main", 0)
    assert len(got) == len(readings) - 1 and [t for t, _ in got] == [t for t, _ in readings[1:]]
    assert max(abs(v) for _, v in got[4:]) < 3                 # a true model: within the noise
    assert not e.p.events.query(n=None, type="ergostat.model.disagrees")


def test_a_planted_model_error_raises_model_disagrees(tmp_path, monkeypatch):
    e, _ = _tank(tmp_path, monkeypatch, k_model=0.5, k_true=1.0, hours=8)
    said = e.p.events.query(n=None, type="ergostat.model.disagrees")
    assert said and said[0]["item"] == "stock.tank" and said[0]["data"]["run"] == ob.RUN
    found = [f for f in watch.find(e.p, e.spec, now=e.clock.t) if f.code == "model-disagrees"]
    assert len(found) == 1 and found[0].about == "stock.tank" and "observer/tank/innovation" in found[0].message
    good, _ = _tank(tmp_path / "good", monkeypatch, hours=8)
    assert not good.p.events.query(n=None, type="ergostat.model.disagrees")


def test_on_stale_and_the_estimate_ports_are_checked(tmp_path):
    from ergostat import spec as sp
    base = textwrap.dedent(QUEUE).replace("BLOCKPOLICY", "on-stale: off").replace("POLICY", "on-stale: hold")
    (tmp_path / "ergostat.yaml").write_text(base)
    spec, probs = sp.read(tmp_path / "ergostat.yaml")
    assert not [x for x in probs if x.level == "error"]
    assert spec.goals["short"].on_stale == "hold" and spec.blocks["push"].on_stale == "off"
    assert spec.blocks["keep"].on_stale is None
    for bad, code in (("on-stale: hold", "on-stale: later"), ("in: [block.keep, block.push, stock.queue]",
                                                               "in: [block.keep, stock.queue.guess]")):
        (tmp_path / "ergostat.yaml").write_text(base.replace(bad, code, 1))
        _, probs = sp.read(tmp_path / "ergostat.yaml")
        assert [x for x in probs if x.level == "error"], code
    (tmp_path / "ergostat.yaml").write_text(base.replace("stock.queue]", "stock.queue.estimate]"))
    spec, probs = sp.read(tmp_path / "ergostat.yaml")
    assert not [x for x in probs if x.level == "error"] and ob.estimated(spec, spec.blocks["worker"].inputs["in3"])


def test_the_page_says_a_goal_is_stale_and_needs_attention(tmp_path, monkeypatch):
    from ergostat import runner
    e = _queue(tmp_path, monkeypatch, "off")
    _read(e, "sensor/queue.main", 3)
    snap = state.snapshot(e.p, now=e.clock.t)
    assert snap["loops"]["short"]["status"] == "holding" and "stale" not in snap["loops"]["short"]
    assert state.snapshot(e.p, now=e.clock.t + 31)["loops"]["short"]["status"] == "holding"   # ergostat is not running
    monkeypatch.setattr(runner, "running_pid", lambda p, wait=True: 4242)
    e.p.events.add("ergostat.started", source="ergostat", data={})
    assert state.snapshot(e.p, now=e.clock.t + 25)["loops"]["short"]["status"] == "holding"   # its sensor not due yet
    snap = state.snapshot(e.p, now=e.clock.t + 31)
    lp = snap["loops"]["short"]
    assert lp["status"] == "stale" and lp["stale"] == pytest.approx(31) and lp["on_stale"] == "off"
    said = [a for a in state.attention(snap, True, e.p.model) if a["what"] == "goal short"]
    assert said and said[0]["level"] == "warn" and "it counts as off" in said[0]["says"]
    _read(e, "sensor/queue.main", 9)                            # off outranks stale
    assert state.snapshot(e.p, now=e.clock.t + 31)["loops"]["short"]["status"] == "off"


class _Nothing:
    """What ``opted`` gives with the observer stubbed out: nothing asked for."""
    stocks, goals, blocks, parts = [], {}, set(), []

    def __bool__(self):
        return False


def _stub_observer(monkeypatch) -> None:
    """The observer taken out entirely: its entry points in the engine, the page, the MCP status and the compiler."""
    from ergostat import state
    from ergostat.spec import compile as compile_
    from ergostat.spec import engine
    monkeypatch.setattr(ob, "opted", lambda spec: _Nothing())
    monkeypatch.setattr(engine, "opted", lambda spec: _Nothing())
    monkeypatch.setattr(engine.Engine, "observe", lambda self, now, rows, out: set())
    monkeypatch.setattr(engine.Engine, "staleness", lambda self, now, out, mono=None: set())
    monkeypatch.setattr(engine.Engine, "stale_mode", lambda self, b: None)
    monkeypatch.setattr(engine.Engine, "stale_in", lambda self, b: {})
    monkeypatch.setattr(ob, "shown_stale", lambda *a: None)
    monkeypatch.setattr(state, "shown_stale", lambda *a: None)
    monkeypatch.setattr(compile_.Compiler, "on_stale", lambda self, m, what: None)


def _record(src: Path, tmp: Path, monkeypatch) -> dict:
    """Everything an example records, driven alike each time: readings (some late, some after long silences), runs
    ending; its events, series, signals, statuses and setpoints at each pass, starts, page statuses and attention,
    findings and compile problems."""
    from ergostat import runner
    from ergostat.spec.engine import Engine
    clock = Clock()
    monkeypatch.setattr(time, "time", clock)
    monkeypatch.setattr(time, "monotonic", clock)
    monkeypatch.setattr(runner, "running_pid", lambda p, wait=True: 4242)    # as if it runs: the page's statuses then
    d = tmp / src.name
    shutil.copytree(src, d, ignore=shutil.ignore_patterns("run", "outbox", "__pycache__", ".ergostat"))
    m = mdl.load(d)
    p = Project(m)
    e = Engine(p, say=lambda s: None)
    started = []

    def start(b, why):
        with e.lock:
            if b.name in e.running:
                return
            e.running.add(b.name)
        started.append((b.name, why))
    e.start = start
    series = [s.series for s in e.spec.sensors() if s.measured or s.manual]
    r = random.Random(5)
    passes = []
    for step in range(60):
        clock.t += r.choice([0.5, 1.0, 3.0, 20.0, 400.0])
        for s in r.sample(series, min(len(series), r.randrange(0, 6))):
            p.measurements.add(s, r.choice([0.0, 1.0, 2.0, 5.0, 12.0, 30.0, 100.0]), clock.t - r.choice([0.0, 0.0, 200.0]))
        for b in sorted(e.running):
            if r.random() < 0.5:
                with e.lock:
                    e.running.discard(b)
                    e.finished[b] = clock.t
                e.poke(b, now=False)
        e.evaluate(tick=True)
        passes.append([step, dict(e.signals), dict(e.status), dict(e.setpoint)])
    evs = p.events.query(n=None)
    at = {x["id"]: i for i, x in enumerate(evs)}
    snap = state.snapshot(p, now=clock.t)
    return {"events": [(x["type"], x["item"], x["source"], x["data"], at.get(x["causedby"])) for x in evs
                       if x["type"] != "ergostat.started"],
            "series": {s["series"]: p.measurements.range(s["series"], 0) for s in p.measurements.series()},
            "passes": passes, "started": started,
            "page": {n: [lp["status"], lp.get("value"), lp.get("error")] for n, lp in snap["loops"].items()},
            "attention": state.attention(snap, True, p.model),
            "findings": [(f.code, f.about, f.message) for f in watch.find(p, e.spec, now=clock.t)],
            "problems": [(x.level, x.code, x.about, x.message.replace(str(d), "")) for x in m.problems]}


@pytest.mark.parametrize("example", [x for x in EXAMPLES if mdl.load(x).spec and mdl.load(x).spec.goals],
                         ids=lambda p: p.name)
def test_models_that_use_none_of_it_record_what_they_did_without_it(tmp_path, example, monkeypatch):
    """Every example asks nothing of the observer: driven alike, as it is and with the observer stubbed out entirely,
    it records the same, section by section."""
    assert not ob.opted(mdl.load(example).spec), example.name
    with monkeypatch.context() as mp:
        as_is = _record(example, tmp_path / "as-is", mp)
    with monkeypatch.context() as mp:
        _stub_observer(mp)
        without = _record(example, tmp_path / "without", mp)
    for k in as_is:
        assert as_is[k] == without[k], k


IMPLIED = """
name: t
stocks:
  queue:
    unit: jobs
    sensor: {run: "echo 0", every: 10s}
flows:
  served:
    from: queue
goals:
  short:
    stock: queue
    hold: "<= 5"
    on-stale: off
blocks:
  worker:
    type: program
    run: "true"
    goal: short
    until: "<= 2"
    out: flow.served
"""


@pytest.mark.parametrize("first", [10, 1])
def test_on_stale_off_with_until_does_not_chatter(tmp_path, monkeypatch, first):
    """The onoff a machine block's goal: and until: imply, its goal stale and counted off: on, and held on, never
    released by the stale value inside its until (which would turn it off, then on again, every other pass)."""
    e = _engine(tmp_path, IMPLIED, monkeypatch)
    keep = next(n for n, b in e.spec.blocks.items() if b.implied)

    def start(b, why):                                     # what would start; it stays running until said
        e.started.append(b.name)
        e.running.add(b.name)
    e.start = start
    _read(e, "sensor/queue.main", first)
    e.evaluate(tick=True)
    e.clock.t += 40
    _read(e, "sensor/queue.main", 1, T0 + 1)               # stale, and inside the until
    seen = []
    for _ in range(12):
        e.evaluate(tick=True)
        seen.append(e.signals[f"block.{keep}"])
        if e.running:                                      # each run ends at once: a new start needs a new command
            e.running.clear()
            e.finished["worker"] = e.clock.t
            e.poke("worker", now=False)
        e.clock.t += 1
    assert "short" in e.stale and seen == [1.0] * 12
    assert e.started.count("worker") == 1


def test_a_count_is_judged_no_finer_than_its_resolution():
    """A count read exactly by a perfect model expects no innovation at all; one count off is still within half a count
    of resolution three times over, so a run of them is no disagreement. A measure read finely has no such floor."""
    sds = {}
    for name, ys in (("count", [5.0] * 12 + [6.0] * 6), ("fine", [5.5] * 12 + [5.6] * 6)):
        tr, t, got = ob.Track(), T0, []
        for y in ys:
            got.append(tr.read(t, y))
            t += 60
        sds[name] = got[11][1]
    assert sds == {"count": 0.5, "fine": 0.0}


def test_a_cron_sensor_is_stale_after_its_third_scheduled_time(tmp_path):
    from ergostat import spec as sp
    from ergostat.cron import Cron
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(QUEUE).replace("every: 10s", 'cron: "0 * * * *"')
                                            .replace("BLOCKPOLICY", "").replace("POLICY", "on-stale: hold"))
    spec, _ = sp.read(tmp_path / "ergostat.yaml")
    c = Cron("0 * * * *")
    last = c.next_after(T0) + 55 * 60                      # read 5 minutes before the hour
    third = c.next_after(c.next_after(c.next_after(last)))
    assert third - last < 3 * 3600                         # (not three hours after the reading)
    ref = ob.Ref("stock", "queue")
    assert ob.stale_age(spec, ref, last, third - 1) is None
    assert ob.stale_age(spec, ref, last, third + 1) == pytest.approx(third + 1 - last)


def test_after_a_sleep_nothing_is_stale_until_its_sensors_could_read(tmp_path, monkeypatch):
    e = _queue(tmp_path, monkeypatch, "hold")
    wall = Clock()
    monkeypatch.setattr(time, "time", wall)
    e.clock = wall
    _read(e, "sensor/queue.main", 2)
    e.evaluate(tick=True)
    wall.t += 3600                                         # the laptop slept an hour: the monotonic clock stood still
    e.evaluate(tick=True)
    assert not e.stale
    wall.t += 31
    monkeypatch.setattr(time, "monotonic", lambda: T0 + 31)
    e.evaluate(tick=True)
    assert e.stale["short"] == pytest.approx(3631)


def test_a_swap_drops_what_the_new_model_does_not_ask_for(tmp_path, monkeypatch):
    """A goal stale under hold, and a stock estimated, then a model that asks for neither: no error at any pass after,
    nothing left stale, no estimate left in the signals, no observer kept."""
    e = _queue(tmp_path / "q", monkeypatch, "hold")
    _read(e, "sensor/queue.main", 10)
    e.evaluate(tick=True)
    e.clock.t += 100
    _read(e, "sensor/queue.main", 2, T0 + 5)
    e.evaluate(tick=True)
    assert "short" in e.stale and e.signals["goal.short.off"] == 1
    (tmp_path / "q" / "ergostat.yaml").write_text(textwrap.dedent(QUEUE.replace("BLOCKPOLICY", "").replace("POLICY", "")))
    e.swap(mdl.load(tmp_path / "q"))
    for full in (True, False):
        e.clock.t += 1
        _read(e, "sensor/queue.main", 3)
        e.evaluate(tick=True, full=full)
    assert not e.stale and not e.stale_parts and e.signals["goal.short.off"] == 0
    t, _ = _tank(tmp_path / "t", monkeypatch, hours=2)
    assert "stock.tank.estimate" in t.signals and t.observer is not None
    (tmp_path / "t" / "ergostat.yaml").write_text(textwrap.dedent(TANK.replace("K", "0.5").split("blocks:")[0]))
    t.swap(mdl.load(tmp_path / "t"))
    t.clock.t += 1
    t.evaluate(tick=True)
    assert t.observer is None and not [k for k in t.signals if k.endswith((".estimate", ".uncertainty"))]


def test_a_late_reading_is_weighed_against_the_estimate_at_its_own_time():
    tr = ob.Track()
    tr.read(T0, 10.0)
    tr.x += 5.0                                            # the estimate moved on an hour, at 5 an hour
    tr.open += 5.0
    nu, _ = tr.read(T0 + 1800, 12.5, back=2.5)             # read half an hour in, as predicted then
    assert nu == pytest.approx(0) and tr.x == pytest.approx(15.0)


def test_the_page_hears_of_a_sleep(tmp_path, monkeypatch):
    from ergostat import runner
    monkeypatch.setattr(runner, "running_pid", lambda p, wait=True: 4242)
    e = _queue(tmp_path, monkeypatch, "hold")
    wall = Clock()
    monkeypatch.setattr(time, "time", wall)
    e.clock = wall
    _read(e, "sensor/queue.main", 2)
    e.evaluate(tick=True)
    wall.t += 3600                                         # slept: the monotonic clock stood still
    e.evaluate(tick=True)
    assert e.p.events.query(n=None, type="ergostat.engine.woke")
    assert state.snapshot(e.p, now=wall.t + 5)["loops"]["short"]["status"] == "holding"
    assert state.snapshot(e.p, now=wall.t + 31)["loops"]["short"]["status"] == "stale"
