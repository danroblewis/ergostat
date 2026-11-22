"""The owner's asks, by shard (SPEC §9.8): each ask in the record is followed by the one engine whose shard ``Plan.of``
gives for what it names (an ask about something the model does not have: by the lead), and only the lead does what is
done once for the model."""

from __future__ import annotations

import io
import textwrap
import threading
import time
from types import SimpleNamespace

import pytest

from ergostat import history, runner, transcripts
from ergostat import model as mdl
from ergostat.actions import record
from ergostat.control import steptest
from ergostat.daemons.proc import Handle
from ergostat.daemons.supervise import Supervisor
from ergostat.messages import deliver
from ergostat.spec import shards
from ergostat.spec.engine import RESTART_ASKED, STOP_ASKED, Engine
from ergostat.store import Project

MODEL = """
name: asks
systems:
  a: {description: one}
  b: {description: two}
daemons:
  da: {run: "sleep 60"}
  db: {run: "sleep 60"}
stocks:
  a-q: {unit: things, system: a, sensor: {run: echo 1, every: 1h}}
  a-d: {unit: things, system: a, sensor: {daemon: da, every: 1h}}
  b-q: {unit: things, system: b, sensor: {run: echo 2, every: 1h}}
  b-d: {unit: things, system: b, sensor: {daemon: db, every: 1h}}
flows:
  a-made: {to: a-q, system: a}
  a-fired: {to: a-q, system: a}
  b-made: {to: b-q, system: b}
  b-fired: {to: b-q, system: b}
goals:
  a-low: {stock: a-q, hold: "<= 5", system: a}
  b-low: {stock: b-q, hold: "<= 5", system: b}
blocks:
  a-work: {type: program, run: "true", out: flow.a-made, system: a}
  a-trig: {type: program, run: "true", on: {event: thing.happened}, out: flow.a-fired, system: a}
  b-work: {type: program, run: "true", out: flow.b-made, system: b}
  b-trig: {type: program, run: "true", on: {event: thing.happened}, out: flow.b-fired, system: b}
"""
ASKS = ("block.approved,block.denied,trigger.reset,ergostat.action.approved,steptest.approved,"
        f"{STOP_ASKED},{RESTART_ASKED}")


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(Supervisor, "_spawn_claimed", lambda self, slot: None)
    monkeypatch.setattr(Supervisor, "_loop", lambda self: None)
    yield
    runner.STOPPING.clear()


def project(tmp_path, text: str = MODEL) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def watched(monkeypatch, engines: dict[str, Engine]) -> list[tuple]:
    """Every act an ask can lead to, recorded as (engine, act, what) instead of done."""
    acts: list[tuple] = []
    for n, e in engines.items():
        for name, how in (("start", lambda b, why, extra=None, cause=None, n=n: acts.append((n, "start", b.name)) or True),
                          ("stop_run", lambda name, n=n: acts.append((n, "stop", name)) or True),
                          ("run_action", lambda aid, spec=None, n=n: acts.append((n, "action", aid))),
                          ("command_of", lambda b: (1.0, {}))):
            monkeypatch.setattr(e, name, how)
        monkeypatch.setattr(e.triggers, "reset", lambda name, n=n: acts.append((n, "reset", name)))
        monkeypatch.setattr(e.triggers, "answered", lambda b, ok, ask, n=n: acts.append((n, "approved" if ok else "denied",
                                                                                           b.name)))
        monkeypatch.setattr(e.daemons, "revive", lambda name, n=n: acts.append((n, "restart", name)) or True)
    monkeypatch.setattr(steptest, "begin", lambda eng, e, spec=None: acts.append((eng.shard or "whole", "steptest",
                                                                                  e["data"]["goal"])))
    return acts


def follow(p, engines: dict[str, Engine], after: int = 0) -> None:
    """Each engine follows the record's asks since ``after``, as ``_follow`` does."""
    asks = p.events.query(n=None, after_seq=after, type=ASKS)
    for e in engines.values():
        for ev in asks:
            e._ask(ev)


def settled(acts: list, n: int) -> list:
    """(actions run in a thread of their own: waited for, then a moment more for any that should not come)"""
    end = time.monotonic() + 5
    while len(acts) < n and time.monotonic() < end:
        time.sleep(0.01)
    time.sleep(0.1)
    return sorted(acts)


def by_shard(p) -> dict[str, Engine]:
    return {n: Engine(p, say=lambda s: None, shard=n) for n in shards.plan(p.model.spec).shards}


def test_block_asks_followed_by_owner_only(tmp_path, monkeypatch):
    p = project(tmp_path)
    by = by_shard(p)
    assert set(by) == {"lead", "a", "b"}
    acts = watched(monkeypatch, by)
    for x in ("a", "b"):
        p.events.add("block.approved", item=f"{x}-work", source="person")
        p.events.add("block.denied", item=f"{x}-trig", source="person", data={"ask": 1})
        p.events.add("trigger.reset", item=f"{x}-trig", source="person")
        p.events.add(STOP_ASKED, item=f"{x}-work", source="person")
    follow(p, by)
    assert sorted(acts) == sorted((x, act, f"{x}-{b}") for x in ("a", "b")
                                  for act, b in (("start", "work"), ("denied", "trig"), ("reset", "trig"), ("stop", "work")))


def test_restart_and_steptest_by_owner_only(tmp_path, monkeypatch):
    p = project(tmp_path)
    by = by_shard(p)
    acts = watched(monkeypatch, by)
    p.events.add(RESTART_ASKED, item="db", source="person")
    p.events.add("steptest.approved", item="a-low", source="person", data={"id": "t1", "goal": "a-low", "block": "a-work"})
    follow(p, by)
    assert sorted(acts) == [("a", "steptest", "a-low"), ("b", "restart", "db")]
    acts.clear()
    p.events.add("steptest.approved", item="b-low", source="person", data={"id": "t2", "goal": "b-low", "block": "b-work"})
    p.events.add("steptest.started", item="a-low", source="ergostat", data={"test": "t0"})     # cut off by a stop
    for n in ("lead", "b"):                              # (not a-low's: its cut-off test is left alone)
        steptest.resume(by[n])
    assert not p.events.query(n=None, type="steptest.finished")
    steptest.resume(by["a"])
    assert sorted(acts) == [("a", "steptest", "a-low"), ("b", "steptest", "b-low")]
    cut = p.events.query(n=None, type="steptest.finished")
    assert [e["data"]["test"] for e in cut] == ["t0"], "said finished once, by a-low's shard"


def test_action_run_by_asking_blocks_shard(tmp_path, monkeypatch):
    p = project(tmp_path)
    by = by_shard(p)
    acts = watched(monkeypatch, by)
    for aid, block in (("ergostat.action/aaa1", "b-work"), ("ergostat.action/aaa2", "gone")):
        record.step(p, aid, "requested", {"block": block, "asker": "program", "action": "x"})
        record.step(p, aid, "approved", {})
    assert record.get(p, "ergostat.action/aaa1")["block"] == "b-work"
    follow(p, by)
    assert settled(acts, 2) == [("b", "action", "ergostat.action/aaa1"), ("lead", "action", "ergostat.action/aaa2")]


def test_unplaced_ask_goes_to_lead_once(tmp_path, monkeypatch):
    p = project(tmp_path)
    by = by_shard(p)
    acts = watched(monkeypatch, by)
    p.events.add(STOP_ASKED, item="removed", source="person")
    p.events.add(RESTART_ASKED, item="nope", source="person")
    p.events.add("block.approved", item="ghost", source="person")
    p.events.add("block.approved", item="", source="person")
    follow(p, by)
    assert sorted(acts) == [("lead", "restart", "nope"), ("lead", "stop", "removed")]   # (ghost, "": nothing to run)
    plan = shards.plan(p.model.spec)
    for k in ("block.removed", "daemon.nope", "block.ghost"):
        with pytest.raises(KeyError):
            plan.of(k)
    assert [e.follows(k) for e in by.values() for k in ("block.ghost", "block.")].count(True) == 2   # the lead's alone
    # a removed block's run held in b's procs: stopped by b (the lead finds nothing of it to stop)
    fresh = by_shard(p)
    killed: list = []
    monkeypatch.setattr(runner, "_kill", killed.append)
    monkeypatch.setattr(fresh["lead"].daemons, "stop_block", lambda name: False)
    proc = object()
    fresh["b"].procs["removed"] = proc
    got = {}
    for n, e in fresh.items():
        real = e.stop_run
        monkeypatch.setattr(e, "stop_run", lambda name, n=n, real=real: got.setdefault(n, real(name)))
    follow(p, fresh, after=p.events.query(n=None, type=STOP_ASKED)[-1]["seq"] - 1)
    assert killed == [proc] and got == {"b": True, "lead": False} and "removed" in fresh["b"].stopping_runs
    # a removed block's run held by b's daemon (never in procs): b's daemon cancels it; the lead's real stop finds none
    held = by_shard(p)
    h = Handle(block="removed")
    daemon = SimpleNamespace(lock=threading.Lock(), runs={"run1": h}, log=io.StringIO())
    held["b"].daemons.draining.append((None, daemon))
    got = {}
    for n, e in held.items():
        real = e.stop_run
        monkeypatch.setattr(e, "stop_run", lambda name, n=n, real=real: got.setdefault(n, real(name)))
    follow(p, held, after=p.events.query(n=None, type=STOP_ASKED)[-1]["seq"] - 1)
    assert got == {"b": True, "lead": False} and h.asked and h.cancelled is not None


def test_ask_after_swap_goes_to_new_owner(tmp_path, monkeypatch):
    p = project(tmp_path)
    said: list[str] = []
    by = by_shard(p)
    by["a"].say = said.append
    a_start = by["a"].start                              # (a's real start: the act, under the model as it is then)
    acts = watched(monkeypatch, by)
    monkeypatch.setattr(by["a"], "start", a_start)
    monkeypatch.setattr(by["a"], "_run", lambda b, *args: acts.append(("a", "run", b.name)))
    moved = MODEL.replace('a-work: {type: program, run: "true", out: flow.a-made, system: a}',
                          'a-work: {type: program, run: "true", on: {event: other.thing}, out: flow.a-made, system: b}')
    new = project(tmp_path / "next", moved).model
    assert shards.plan(p.model.spec).of("block.a-work") == "a" and shards.plan(new.spec).of("block.a-work") == "b"
    real = by["a"].follows
    swapped = []

    def swap_between(key, spec=None):                    # the model swapped after the ask is read, before the act
        got = real(key, spec)
        if not swapped:
            swapped.append(by["a"].swap(new))
        return got
    monkeypatch.setattr(by["a"], "follows", swap_between)
    p.events.add("block.approved", item="a-work", source="person", data={"ask": 1})
    follow(p, {"a": by["a"]})
    assert swapped and by["a"].spec is new.spec
    follow(p, {"b": by["b"], "lead": by["lead"]})        # (these two still under the model before)
    time.sleep(0.1)
    assert acts == [], "judged a's under the model read, but never started outside a's shard as it is now"
    assert "a-work" not in by["a"].running and any("approve it again" in s for s in said)
    by["b"].swap(new)
    by["lead"].swap(new)
    acts.clear()
    seq = p.events.last_seq()
    p.events.add("block.approved", item="a-work", source="person", data={"ask": 1})
    follow(p, by, after=seq)
    assert acts == [("b", "approved", "a-work")], "the next ask: its new owner's alone"


def test_start_refuses_other_shards_block(tmp_path):
    p = project(tmp_path)
    said: list[str] = []
    e = Engine(p, say=said.append, shard="a")
    assert e.start(p.model.spec.blocks["b-work"], "approved") is False
    assert "b-work" not in e.running and "b-work" not in e.began and not e.procs
    assert said and "shard b" in said[-1]


def test_once_duties_only_in_lead(tmp_path, monkeypatch):
    done: list[tuple] = []
    monkeypatch.setattr(history, "note", lambda p, said=None: done.append(("note", "swap" if said else "start")))
    monkeypatch.setattr(runner.Runner, "_prune", lambda self: done.append(("prune", self.shard)))
    monkeypatch.setattr(deliver, "sweep", lambda p, spec: done.append(("sweep", None)))

    class Ingester:
        def __init__(self, p, spec):
            done.append(("ingest", None))

        def kinds(self):
            return ["x"]

        def run(self, stop, say):
            pass
    monkeypatch.setattr(transcripts, "Ingester", Ingester)

    def once(p, engines) -> list:
        done.clear()
        try:
            for e in engines:
                e.start_all()
            time.sleep(0.2)                              # (_prune runs in a thread of its own)
        finally:
            for e in engines:
                e.close()
        done[:] = [x for x in done if x[0] != "sweep"]   # (the loop's own first sweep: counted below, by engine)
        for e in engines:
            e._sweep()
            e.swap(p.model)
        return sorted(x for x in done)

    p = project(tmp_path / "shards")
    by = by_shard(p)
    assert set(by) == {"lead", "a", "b"}
    got = once(p, list(by.values()))
    assert got == [("ingest", None), ("note", "start"), ("note", "swap"), ("prune", "lead"), ("sweep", None)]
    assert len(p.events.query(n=None, type="ergostat.started")) == 1
    w = project(tmp_path / "whole")
    assert once(w, [Engine(w, say=lambda s: None)]) == [("ingest", None), ("note", "start"), ("note", "swap"),
                                                        ("prune", None), ("sweep", None)]
    assert len(w.events.query(n=None, type="ergostat.started")) == 1


def test_one_shard_follows_like_whole(tmp_path, monkeypatch):
    monkeypatch.setattr(shards, "MAX_SHARDS", 1)
    p = project(tmp_path)
    assert set(shards.plan(p.model.spec).shards) == {"lead"}
    for x in ("a", "b"):
        p.events.add("block.approved", item=f"{x}-work", source="person")
        p.events.add("block.denied", item=f"{x}-trig", source="person", data={"ask": 1})
        p.events.add("trigger.reset", item=f"{x}-trig", source="person")
        p.events.add(STOP_ASKED, item=f"{x}-work", source="person")
        p.events.add(RESTART_ASKED, item=f"d{x}", source="person")
        p.events.add("steptest.approved", item=f"{x}-low", source="person", data={"id": x, "goal": f"{x}-low"})
        aid = f"ergostat.action/bbb{x}"
        record.step(p, aid, "requested", {"block": f"{x}-work", "asker": "program", "action": "x"})
        record.step(p, aid, "approved", {})
    p.events.add(STOP_ASKED, item="removed", source="person")
    p.events.add(RESTART_ASKED, item="nope", source="person")
    got = {}
    for name, shard in (("whole", None), ("lead", "lead")):
        e = {name: Engine(p, say=lambda s: None, shard=shard)}
        acts = watched(monkeypatch, e)
        follow(p, e)
        got[name] = [x[1:] for x in settled(acts, 16)]
    assert len(got["whole"]) == 16 and got["lead"] == got["whole"]
