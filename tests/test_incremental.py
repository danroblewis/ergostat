"""The engine's pass works out only what changed (spec/engine.py, docs/proposals/scale.md #1): it must do what a pass
over everything does. Two engines on copies of the same model take the same readings, commands and runs ending, at
the same moments; one works out everything every pass, the other only what changed. After every pass they hold the
same signals, statuses and setpoints, start the same blocks in the same order, and have recorded the same events.

Time moves only on the clock's pass (as the loop's tick is the only pass that time alone calls for): a block paced by
``every``, a timer or a delay is due at a tick in both."""

from __future__ import annotations

import random
import shutil
import time

import pytest

from ergostat import model as mdl
from ergostat.spec.engine import Engine
from ergostat.store import Project
from tests.test_rollup import EXAMPLES

T0 = 1_787_904_000.0


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self) -> float:
        return self.t


def _engine(tmp_path, src, name: str, incremental: bool):
    d = tmp_path / name
    shutil.copytree(src, d, ignore=shutil.ignore_patterns("run", "outbox", "__pycache__", ".ergostat"))
    p = Project(mdl.load(d))
    e = Engine(p, say=lambda s: None)
    e.incremental = incremental
    e.started = []

    def start(b, why):                                    # nothing runs: what would start, and when, is recorded
        with e.lock:
            if b.name in e.running:
                return
            e.running.add(b.name)
            e.began[b.name] = time.time()
        e.started.append((b.name, why))
    e.start = start
    return e


def _record(e) -> list:
    evs = e.p.events.query(n=None)
    at = {x["id"]: i for i, x in enumerate(evs)}
    return [(x["type"], x["item"], x["source"], x["data"], at.get(x["causedby"])) for x in evs]


def _state(e) -> dict:
    return {"signals": dict(e.signals), "status": dict(e.status), "setpoint": dict(e.setpoint), "started": list(e.started),
            "running": set(e.running), "commanded": {k: v for k, v in e.was_commanded.items() if v}}


def _drive(tmp_path, src, seed: int, steps: int = 60, monkeypatch=None):
    clock = Clock()
    monkeypatch.setattr(time, "time", clock)
    full, inc = _engine(tmp_path, src, "full", False), _engine(tmp_path, src, "inc", True)
    spec = full.spec
    r = random.Random(seed)
    series = [s.series for s in spec.sensors() if s.measured or s.manual]
    commanders = [b.name for b in spec.blocks.values() if b.machine]       # (what they say: commands, read by others)
    goals_set = [t.name for b in spec.blocks.values() if b.machine for t in b.targets() if t.kind == "goal"]
    for step in range(steps):
        tick = r.random() < 0.4
        if tick:
            clock.t += r.choice([0.5, 1.0, 3.0, 20.0, 400.0])
        for s in r.sample(series, min(len(series), r.randrange(0, 6))):     # new readings, some the same as before
            v = r.choice([0.0, 1.0, 2.0, 5.0, 12.0, 30.0, 100.0, -3.0])
            for e in (full, inc):
                e.p.measurements.add(s, v, clock.t)
        if commanders and r.random() < 0.3:                                 # a run's command (Said)
            b = r.choice(commanders)
            v = r.choice([0.0, 1.0, 4.0])
            for e in (full, inc):
                with e.lock:
                    e.outputs.setdefault(b, {})["out"] = v
                e.touch(f"block.{b}")
        if goals_set and r.random() < 0.15:                                 # a setpoint a run set
            g = r.choice(goals_set)
            v = r.choice([1.0, 10.0, 50.0])
            for e in (full, inc):
                with e.lock:
                    e.setpoint[g] = v
                e.touch(goals=(g,))
        for b in sorted(full.running):                                      # runs that end
            if r.random() < 0.5:
                for e in (full, inc):
                    with e.lock:
                        e.running.discard(b)
                        e.finished[b] = clock.t
                    e.poke(b, now=False)
        full.evaluate(tick=tick)
        inc.evaluate(tick=tick)
        a, b_ = _state(full), _state(inc)
        assert a == b_, (step, {k: (a[k], b_[k]) for k in a if a[k] != b_[k]})
        assert _record(full) == _record(inc), step
    return full


MODELS = [e for e in EXAMPLES if mdl.load(e).spec and mdl.load(e).spec.goals]


@pytest.mark.parametrize("example", MODELS, ids=lambda p: p.name)
def test_a_pass_over_what_changed_does_what_a_pass_over_everything_does(tmp_path, example, monkeypatch):
    for seed in range(3):
        e = _drive(tmp_path / f"s{seed}", example, seed, monkeypatch=monkeypatch)
        assert e.spec.goals


EVERY_KIND = """
stocks:
  a:
    unit: x
    sensor: {manual: true}
  b:
    unit: x
    sensor: {manual: true}
  c:
    unit: x
    sensor: {manual: true}
flows:
  f1:
    from: a
    sensor: {manual: true}
  f2:
    to: b
  f3:
    from: c
  f4:
    to: c
auxiliaries:
  x:
    sensor: {manual: true}
goals:
  ga: {stock: a, hold: "<= 20", tolerance: 2}
  gb: {stock: b, hold: ">= 5"}
  gc: {stock: c, hold: "<= 10"}
  gm: {stock: a, hold: "<= 30"}
blocks:
  cmp:
    type: compare
    in: stock.a
    above: 10
    back-below: 5
    out: block.asker
  ex:
    type: expr
    in: {a: stock.a, b: stock.b}
    expr: "a * 2 - b"
    out: goal.gc
  lk:
    type: lookup
    in: block.ex
    table: {0: 0, 100: 10}
    out: block.advisor
  sel:
    type: select
    pick: max
    in: [stock.c, auxiliary.x, block.lim]
    out: block.paced
  prop:
    type: proportional
    goal: ga
    gain: 0.5
    max: 8
    out: block.m1
  lim:
    type: limit
    in: block.m4
    max: 3
  pc:
    type: proportional
    goal: gc
    gain: 2
  slew:
    type: limit
    in: stock.b
    rate: 3600
  dl:
    type: delay
    in: block.lk
    delay: 2
  tm:
    type: timer
    in: block.cmp
    after: 5
  cn:
    type: counter
    in: block.cmp
  al:
    type: alarm
    in: stock.c
    above: 50
    for: 3
  m1:
    type: program
    run: "true"
    in: block.prop
    out: flow.f1
  free:
    type: program
    run: "true"
    in: stock.c
    out: flow.f3
  paced:
    type: program
    run: "true"
    in: block.sel
    every: 5s
    out: flow.f2
  asker:
    type: person
    in: block.cmp
    ask: "look at a"
  advisor:
    type: program
    mode: advise
    run: "true"
    in: block.lk
    out: flow.f4
  m4:
    type: program
    run: "true"
    in: stock.b
    every: 1m
  m5:
    type: program
    run: "true"
    in: stock.a
    out: goal.gm
    every: 1m
"""


def test_every_kind_of_built_in_and_of_start(tmp_path, monkeypatch):
    """Every built-in type (those that keep time and those that do not, a cascade, a delay's loop), and machine blocks
    commanded, started by any reading, paced by every, a person, an advised block, one read by a built-in, one that
    sets a setpoint."""
    d = tmp_path / "model"
    d.mkdir()
    (d / "ergostat.yaml").write_text(EVERY_KIND)
    for seed in range(8):
        _drive(tmp_path / f"s{seed}", d, seed, steps=120, monkeypatch=monkeypatch)


def test_on_a_scale_model(tmp_path, monkeypatch):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    d = tmp_path / "n10"
    subprocess.run([sys.executable, str(root / "scripts/scale_model.py"), "10", str(d)], check=True, capture_output=True)
    e = _drive(tmp_path / "run", d, 7, steps=80, monkeypatch=monkeypatch)
    assert any(e.started) or e.status
