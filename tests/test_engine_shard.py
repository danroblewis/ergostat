"""An engine that works only on its shard (SPEC §9.8): ``Engine(project, shard=NAME)`` keeps to the parts ``Plan.of``
puts in its shard, and the shards of one plan split the whole engine's work between them, nothing twice, nothing left."""

from __future__ import annotations

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.daemons.supervise import Supervisor
from ergostat.spec import shards
from ergostat.spec.engine import Engine
from ergostat.spec.joins import JOINED
from ergostat.store import Project

# Systems a, b and c. b and c share the daemon `probe` through two sensors only, so they are one shard (b); `spare`
# serves nothing and the kind `loose` has no system: the lead's. A goal of a reads a stock of b; a's block reads an
# estimate (the observer); b's reads one too.
MODEL = """
name: sh
systems:
  a: {description: one}
  b: {description: two}
  c: {description: three}
daemons:
  probe: {run: "sleep 60"}
  spare: {run: "sleep 60"}
items:
  epic:
    id: epic/*
    states: [planned, shipped]
    system: a
    join:
      - {children: parent, all: done, to: shipped}
  ticket:
    id: ticket/*
    states: [todo, done]
    system: b
    on: {ticket.done: done}
    relations: {parent: epic}
  job: {id: job/*, states: [new, done], system: a}
  loose: {id: loose/*}
stocks:
  a-q: {unit: things, system: a, sensor: {run: echo 1, every: 1h}}
  a-tank: {unit: things, system: a, sensor: {run: echo 5, every: 1h}}
  b-q: {unit: things, system: b, sensor: {run: echo 2, every: 1h}}
  b-far: {unit: things, system: b, sensor: {run: echo 3, cron: "0 3 * * *"}}
  b-own: {unit: things, system: b, sensor: {run: echo 4, every: 1h}}
  b-p: {unit: things, system: b, sensor: {daemon: probe, every: 1h}}
  c-q: {unit: things, system: c, sensor: {daemon: probe, every: 1h}}
flows:
  a-made: {to: a-q, system: a}
  a-ticked: {to: a-q, system: a}
  a-fired: {to: a-q, system: a}
  b-fired: {to: b-q, system: b}
  b-made: {to: b-q, system: b}
goals:
  a-low: {stock: a-q, hold: "<= 5", system: a}
  a-far: {stock: b-far, hold: "<= 5", system: a}
  b-low: {stock: b-q, hold: "<= 5", system: b}
blocks:
  a-on: {type: onoff, goal: a-low, out: block.a-work, system: a}
  a-est: {type: expr, in: {e: stock.a-tank.estimate}, expr: e, system: a}
  a-work: {type: program, run: "true", out: flow.a-made, system: a}
  a-tick: {type: program, run: "true", every: 1h, out: flow.a-ticked, system: a}
  a-take: {type: program, run: "true", takes: {kind: job, at: new}, system: a}
  a-trig: {type: program, run: "true", on: {event: thing.happened}, out: flow.a-fired, system: a}
  judge: {type: judge, system: a}
  b-trig: {type: program, run: "true", on: {event: thing.happened}, out: flow.b-fired, system: b}
  b-cron: {type: program, run: "true", cron: "0 4 * * *", out: flow.b-made, system: b}
  b-est: {type: expr, in: {e: stock.b-own.estimate}, expr: e, system: b}
"""


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    spawned: list[str] = []
    monkeypatch.setattr(Supervisor, "_spawn_claimed", lambda self, slot: spawned.append(slot.d.name))
    monkeypatch.setattr(Supervisor, "_loop", lambda self: None)
    yield spawned
    runner.STOPPING.clear()


def project(tmp_path, text: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def engines(p) -> tuple[Engine, dict[str, Engine]]:
    plan = shards.plan(p.model.spec)
    return Engine(p, say=lambda s: None), {n: Engine(p, say=lambda s: None, shard=n) for n in plan.shards}


def sensor_key(s) -> str:
    return f"{s.of.kind}.{s.of.name}.{s.name}"


def lists(e: Engine) -> dict[str, set]:
    """Everything an engine works on, read from the engine itself."""
    timed, timed_blocks, judges, crons, _ = e._plan(e.spec, {}, {})
    before = set(e.signals)
    e.goals(time.time(), out=[])
    e.observe(time.time(), [], [])
    e.daemons.sync(e.spec)
    return {"builtins": set(e.builtins), "machines": {b.name for b in e.machines},
            "goals": {k for k in set(e.signals) - before if k.startswith("goal.") and k.count(".") == 1},
            "timed": {sensor_key(s) for s in timed}, "timed_blocks": {b.name for b in timed_blocks},
            "judges": {b.name for b in judges}, "crons": set(crons),
            "dispatch_blocks": {b.name for b in e.dispatch.blocks}, "kinds": set(e.dispatch.kinds()),
            "observer": set(e.observer.tracks), "daemons": set(e.daemons.slots),
            "observers": set(e.daemons.observers), "triggers": {b.name for b in e.spec.blocks.values()
                                                                 if b.on is not None and e.own(f"block.{b.name}")}}


def test_one_shard_lead_is_whole_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(shards, "MAX_SHARDS", 1)
    p = project(tmp_path)
    assert set(shards.plan(p.model.spec).shards) == {"lead"}
    whole = lists(Engine(p, say=lambda s: None))
    assert lists(Engine(p, say=lambda s: None, shard="lead")) == whole
    assert all(whole.values()), "every list has something in it"


def test_shards_partition_the_work(tmp_path):
    p = project(tmp_path)
    whole, by = engines(p)
    plan = shards.plan(p.model.spec)
    assert set(by) == {"lead", "a", "b"} and plan.of("stock.c-q") == "b" and plan.of("daemon.probe") == "b"
    assert plan.of("daemon.spare") == "lead" and plan.of("kind.loose") == "lead" and plan.of("kind.ticket") == "b"
    want, got = lists(whole), {n: lists(e) for n, e in by.items()}
    for k, all_of in want.items():
        each = [got[n][k] for n in sorted(got)]
        assert sum(len(x) for x in each) == len(set().union(*each)), f"{k}: in two shards"
        assert set().union(*each) == all_of, f"{k}: not the whole engine's"
    assert got["a"]["builtins"] == {"a-on", "a-est"} and got["b"]["builtins"] == {"b-est"}
    assert got["a"]["kinds"] == {"job", "epic"} and got["lead"]["kinds"] == {"loose"}
    assert got["b"]["daemons"] == {"probe"} and not got["a"]["daemons"] and not got["lead"]["daemons"]
    assert got["a"]["observer"] == {"a-tank"} and got["b"]["observer"] == {"b-own"}
    assert got["a"]["goals"] == {"goal.a-low", "goal.a-far"} and got["b"]["goals"] == {"goal.b-low"}
    assert got["b"]["crons"] == {s.series for s in p.model.spec.stocks["b-far"].sensors.values()} | {"block/b-cron"}
    assert got["a"]["timed_blocks"] == {"a-tick"} and got["a"]["judges"] == {"judge"}
    assert got["a"]["triggers"] == {"a-trig"} and got["b"]["triggers"] == {"b-trig"}


def test_trigger_and_join_only_in_owning_shard(tmp_path, monkeypatch):
    p = project(tmp_path)
    _, by = engines(p)
    started: dict[str, list] = {n: [] for n in by}
    for n, e in by.items():
        monkeypatch.setattr(e, "start", lambda b, why, extra=None, cause=None, n=n: started[n].append(b.name) or True)
        e.triggers.look()                                  # (from now: the event below is new to each)
    p.events.add("thing.happened", item="x", source="t")
    for e in by.values():
        e.triggers.look()
    assert started == {"a": ["a-trig"], "b": ["b-trig"], "lead": []}
    p.events.add("epic.planned", item="epic/1", source="t")
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"parent": "epic/1"})
    p.events.add("ticket.done", item="ticket/1", source="t")
    for n in ("b", "lead"):                                # the children's shard and the lead: the parent stays
        by[n].joins.look()
    assert not p.events.query(n=None, item="epic/1", type=JOINED)
    by["a"].joins.look()
    assert len(p.events.query(n=None, item="epic/1", type=JOINED)) == 1


def test_sync_starts_only_own_daemons(tmp_path, _quiet):
    p = project(tmp_path)
    _, by = engines(p)
    by["a"].daemons.sync(p.model.spec)
    by["lead"].daemons.sync(p.model.spec)
    assert _quiet == []
    by["b"].daemons.sync(p.model.spec)
    assert _quiet == ["probe"] and {d for d, _ in by["b"].daemons.observers} == {"probe"}
    assert not by["a"].daemons.observers and not by["a"].daemons.push


def test_measure_reads_own_and_read_parts(tmp_path):
    p = project(tmp_path)
    s = p.model.spec
    for i, x in enumerate(s.sensors()):
        p.measurements.add(x.series, float(i + 1))
    _, by = engines(p)
    by["a"].measure()
    got = {k.split(".")[1] for k in by["a"].signals}
    assert got == {"a-q", "a-tank", "b-far"}, got        # its own, and b's stock its goal a-far reads; never b-q, b-own
    assert "stock.b-far" in by["a"].signals and f"stock.b-far.{next(iter(s.stocks['b-far'].sensors))}" in by["a"].signals
    by["b"].measure()
    assert {k.split(".")[1] for k in by["b"].signals} == {"b-q", "b-far", "b-own", "b-p", "c-q"}


def test_swap_moves_part_out(tmp_path, monkeypatch):
    p = project(tmp_path)
    for x in p.model.spec.sensors():
        p.measurements.add(x.series, 3.0)
    e = Engine(p, say=lambda s: None, shard="a")
    monkeypatch.setattr(e, "start", lambda *a, **k: False)
    e.evaluate(full=True)
    e.outputs["a-tick"] = {"out": 1.0}
    assert "block.a-on" in e.signals and "a-low" in e.status and "goal.a-low" in e.signals
    assert "a-tank" in e.observer.tracks and "stock.a-tank.estimate" in e.signals
    assert "a-tick" in {b.name for b in e.machines}
    moved = MODEL
    for part in ("a-on: {type: onoff", "a-tick: {type: program", "a-tank: {unit", "a-low: {stock"):
        line = next(x for x in moved.splitlines() if x.strip().startswith(part))
        moved = moved.replace(line, line.replace("system: a", "system: c"))
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(moved))
    new = mdl.load(tmp_path)
    before, after = shards.plan(p.model.spec), shards.plan(new.spec)
    for k in ("block.a-on", "block.a-tick", "stock.a-tank", "goal.a-low"):
        assert before.of(k) == "a" and after.of(k) == "b", k
    e.swap(new)
    timed, timed_blocks, *_ = e._plan(e.spec, {}, {})
    assert "a-on" not in e.builtins and "a-tick" not in {b.name for b in e.machines}
    assert "a-tick" not in {b.name for b in timed_blocks} and "stock.a-tank" not in {f"stock.{s.of.name}" for s in timed}
    assert "a-low" not in e.status and "a-tick" not in e.outputs and "a-tank" not in e.observer.tracks
    assert not [k for k in e.signals if k.split(".")[1] in ("a-on", "a-low", "a-tank", "a-tick")], e.signals
    assert "a-est" in e.builtins and "goal.a-far" in e.signals            # what stayed, stays


def test_unknown_shard_refused(tmp_path):
    p = project(tmp_path)
    with pytest.raises(ValueError, match="nope"):
        Engine(p, say=lambda s: None, shard="nope")
    e = Engine(p, say=lambda s: None, shard="a")
    old, version = e.spec, e.version
    gone = MODEL.replace("  a: {description: one}\n", "").replace("system: a", "system: b")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(gone))
    new = mdl.load(tmp_path)
    assert "a" not in shards.plan(new.spec).shards
    with pytest.raises(ValueError, match="no shard 'a'"):
        e.swap(new)
    assert e.spec is old and e.version == version and set(e.builtins) == {"a-on", "a-est"}
