"""Lanes on a block's queue (SPEC §9.5, ``takes: {lanes: ...}``, dev/records/merge-lanes-in-parallel.md): items whose
``apart`` lists share nothing run at once; overlapping ones wait their turn in order, or run on top of a lane and are
discarded, uncounted, when it fails; the lanes held never cost more than ``within`` at the larger of the declared and
the measured cost; and a replay of a fixture queue says merges per hour against one lane."""

from __future__ import annotations

import json
import random
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat.leases import TAKEN, lanes
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.spec.ir import Lanes
from ergostat.store import Project

G = 1 << 30
MODEL = """
name: t
projections:
  batch:
    id: batch/*
    states: [ready, landed, failed]
    on: {batch.ready: ready, batch.landed: landed, batch.failed: failed}
blocks:
  lane:
    type: program
    run: "true"
    pool: 8
    takes: {projection: batch, at: ready, to: [landed, failed]LANES}
"""
LANES = ", lanes: {apart: paths, most: 4, ahead: AHEAD, within: {cpu: 8, memory: 8g}, each: {cpu: 2, memory: 2g}, passed: landed}"


def project(tmp_path, ahead: int = 0, plain: bool = False, each: bool = True) -> Project:
    ln = LANES.replace("AHEAD", str(ahead)).replace("" if each else ", each: {cpu: 2, memory: 2g}", "")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("LANES", "" if plain else ln)))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def dispatcher(p, monkeypatch):
    """The engine's dispatcher with its takes real (the lease written, ``on`` with it) and its runs not started: each
    run is ended by the test (``end``). Kills are recorded, not sent."""
    e = Engine(p, say=lambda *_: None)
    d = e.dispatch
    monkeypatch.setattr(d, "_work", lambda *a, **k: [])
    killed: list[str] = []
    monkeypatch.setattr(lanes, "kill", lambda eng, run, why, item, *a: killed.append(item) or True)
    return d, killed


def ready(p, paths: dict) -> None:
    at = time.time() - 100
    for n, (i, ps) in enumerate(paths.items()):
        p.events.add("batch.ready", item=f"batch/{i}", data={"paths": ps}, at=at + n)


def tick(d, p) -> None:
    d.stale = True
    d.tick_block(p.model.spec.blocks["lane"], time.time())


def held(d) -> dict:
    return {i: tuple(g.get("on") or ()) for i, g in d.going.get("lane", {}).items()}


def end(d, p, i: str, outcome: str, out: dict | None = None) -> None:
    """The run on batch/i ends: its line moves it on (landed, failed), or none does (its run's ``out`` says why)."""
    item, g = f"batch/{i}", d.going["lane"].pop(f"batch/{i}")
    if outcome in ("landed", "failed"):
        p.events.add(f"batch.{outcome}", item=item, source="lane", causedby=g["run"])
    d.finish(p.model.spec.blocks["lane"], item, g["fence"], g["run"], out or {"exit": 0})


def state(p, i: str):
    return its.one(p.events, p.model.spec, f"batch/{i}")


def test_off_by_default_existing_models_unchanged(tmp_path, monkeypatch):
    """No ``lanes:``: the block's Takes has none, and its pool takes overlapping items at once, as before."""
    p = project(tmp_path, plain=True)
    assert p.model.spec.blocks["lane"].takes.lanes is None
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py"], "b": ["x.py"]})
    tick(d, p)
    assert held(d) == {"batch/a": (), "batch/b": ()}
    assert all("on" not in e["data"] for e in p.events.query(n=None, type=TAKEN))


def test_non_overlapping_batches_land_in_parallel(tmp_path, monkeypatch):
    p = project(tmp_path)
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py", "y.py"], "b": ["z.py"], "c": ["w.py"]})
    tick(d, p)
    assert held(d) == {"batch/a": (), "batch/b": (), "batch/c": ()}       # one look: three lanes at once
    for i in "cab":
        end(d, p, i, "landed")
    assert [state(p, i).state for i in "abc"] == ["landed"] * 3


def test_overlapping_batches_are_serialised_in_order(tmp_path, monkeypatch):
    """ahead 0: an item sharing a path with a lane waits, and so does a later one sharing a path with it (no overtaking
    among overlapping items), while an apart one goes; once the lane ends, the waiting ones start."""
    p = project(tmp_path)
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py", "y.py"], "b": ["y.py", "v.py"], "c": ["v.py"], "d": ["z.py"]})
    tick(d, p)
    assert held(d) == {"batch/a": (), "batch/d": ()}
    tick(d, p)
    assert held(d) == {"batch/a": (), "batch/d": ()}                      # still: b waits on a, c on b
    end(d, p, "a", "landed")
    tick(d, p)
    assert held(d) == {"batch/d": (), "batch/b": ()}
    end(d, p, "b", "landed")
    tick(d, p)
    assert set(held(d)) == {"batch/d", "batch/c"}


def test_a_failed_base_discards_its_speculative_lane(tmp_path, monkeypatch):
    """ahead 1: b overlaps a, so it runs on top of it (its lease says so); a goes red (left failed, not in passed:):
    b's run is stopped and, when it ends, given back uncounted (no attempt spent); c, apart, is untouched. Then b on top
    of e, e passing: b stands and lands. Then a base whose run gives it back (a nack): the lane on it is discarded too."""
    p = project(tmp_path, ahead=1)
    d, killed = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py"], "b": ["x.py", "y.py"], "c": ["z.py"], "e": ["y.py"]})
    tick(d, p)
    assert held(d) == {"batch/a": (), "batch/b": ("batch/a",), "batch/c": ()}   # e: on b would be 2 deep
    assert state(p, "b").fields["lease"]["on"] == ["batch/a"]
    end(d, p, "a", "failed", {"exit": 1})
    assert killed == ["batch/b"] and state(p, "a").state == "failed"
    end(d, p, "b", "", {"exit": -15, "note": "killed: its base"})
    b = state(p, "b")
    last = b.fields["lease"]["history"][-1]
    assert b.state == "ready" and b.fields["lease"]["attempts"] == 0 and last["counted"] is False, last
    assert "did not pass" in last["why"]
    assert state(p, "c").state == "leased"

    tick(d, p)                                                            # e apart now, b (back behind it) on e
    assert held(d) == {"batch/c": (), "batch/e": (), "batch/b": ("batch/e",)}
    end(d, p, "e", "landed")
    assert killed == ["batch/b"]                                          # a lane that passed discards nothing
    end(d, p, "b", "landed")
    assert state(p, "b").state == "landed"

    ready(p, {"f": ["q.py"], "g": ["q.py"]})
    tick(d, p)
    assert held(d) == {"batch/c": (), "batch/f": (), "batch/g": ("batch/f",)}
    end(d, p, "f", "", {"exit": 1, "note": "exited 1"})                   # given back by its run: counted, its own
    assert killed == ["batch/b", "batch/g"] and state(p, "f").fields["lease"]["attempts"] == 1


def test_an_expired_base_discards_its_lane_on_top(tmp_path, monkeypatch):
    p = project(tmp_path, ahead=1)
    d, killed = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py"], "b": ["x.py"]})
    tick(d, p)
    a = state(p, "a")
    d.expire(a, a.fields["lease"], time.time() + 10_000, 60.0)
    assert state(p, "a").state == "ready" and killed == ["batch/b"]


def restart(p, monkeypatch, *ids: str):
    """A new engine takes up the kept runs on ``ids`` (spec/adopt.py ``adopt``, still going), from their leases."""
    d, killed = dispatcher(p, monkeypatch)
    for i in ids:
        lease = state(p, i).fields["lease"]
        d.adopt(p.model.spec.blocks["lane"], f"batch/{i}", lease["fence"], lease["holder"], True)
    return d, killed


def test_a_base_failing_under_a_taken_up_lane_discards_it(tmp_path, monkeypatch):
    """lesson-3, lesson-5: after a restart the taken-up lane on top keeps its lease's ``on``, so its base going red, or
    its base's lease expiring, stops it, and its end is given back uncounted."""
    p = project(tmp_path, ahead=1)
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py"], "b": ["x.py"], "c": ["z.py"]})
    tick(d, p)
    d, killed = restart(p, monkeypatch, "a", "b", "c")
    assert held(d) == {"batch/a": (), "batch/b": ("batch/a",), "batch/c": ()} and killed == []
    end(d, p, "a", "failed", {"exit": 1})
    assert killed == ["batch/b"]
    end(d, p, "b", "", {"exit": -15, "note": "killed: its base"})
    last = state(p, "b").fields["lease"]["history"][-1]
    assert state(p, "b").state == "ready" and last["counted"] is False and "did not pass" in last["why"], last

    ready(p, {"e": ["y.py"], "f": ["y.py"]})
    tick(d, p)
    d, killed = restart(p, monkeypatch, "e", "f")
    e = state(p, "e")
    d.expire(e, e.fields["lease"], time.time() + 10_000, 60.0)
    assert killed == ["batch/f"]


def test_a_base_failed_before_its_lane_was_taken_up_discards_it(tmp_path, monkeypatch):
    """lesson-1: the base ended red before the new engine had the lane on top in ``going``, so no ``discard`` found it:
    taking it up stops it, and its end is given back uncounted."""
    p = project(tmp_path, ahead=1)
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py"], "b": ["x.py"], "c": ["z.py"]})
    tick(d, p)
    end(d, p, "a", "failed", {"exit": 1})                                 # (the engine before: its kill did not reach b)
    d, killed = restart(p, monkeypatch, "b", "c")
    assert held(d) == {"batch/b": ("batch/a",), "batch/c": ()} and killed == ["batch/b"]
    end(d, p, "b", "", {"exit": 0})
    last = state(p, "b").fields["lease"]["history"][-1]
    assert state(p, "b").state == "ready" and last["counted"] is False and "did not pass" in last["why"], last
    end(d, p, "c", "landed")
    assert killed == ["batch/b"]                                          # a lane apart: kept

    ready(p, {"e": ["y.py"], "f": ["y.py"]})
    tick(d, p)
    end(d, p, "e", "landed")                                              # its base passed before the restart: kept
    d, killed = restart(p, monkeypatch, "f")
    assert held(d) == {"batch/f": ("batch/e",)} and killed == []
    end(d, p, "f", "landed")
    assert state(p, "f").state == "landed"


def test_red_on_top_of_a_base_under_way_is_not_counted(tmp_path, monkeypatch):
    """A lane on top that goes red while its base still runs is not proven red on its own: given back uncounted (it
    waits behind the base, then runs again); once its base has passed, its red counts."""
    p = project(tmp_path, ahead=1)
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {"a": ["x.py"], "b": ["x.py"]})
    tick(d, p)
    end(d, p, "b", "", {"exit": 1, "note": "exited 1"})
    b = state(p, "b")
    assert b.fields["lease"]["attempts"] == 0 and "on top of batch/a" in b.fields["lease"]["history"][-1]["why"]
    tick(d, p)
    assert held(d) == {"batch/a": (), "batch/b": ("batch/a",)}
    end(d, p, "a", "landed")
    end(d, p, "b", "", {"exit": 1, "note": "exited 1"})
    assert state(p, "b").fields["lease"]["attempts"] == 1


def test_a_look_after_the_base_failed_puts_nothing_on_it(tmp_path, monkeypatch):
    """lesson-1: the base's end and a look race. A look whose index still shows the failed base held (the end written,
    ``discard`` done, the index not yet read again) must not put a lane on it."""
    p = project(tmp_path, ahead=1)
    d, killed = dispatcher(p, monkeypatch)
    b = p.model.spec.blocks["lane"]
    base = SimpleNamespace(id="batch/a", fields={"paths": ["x.py"], "lease": {"holder": "r1", "block": "lane"}})
    new = SimpleNamespace(id="batch/b", fields={"paths": ["x.py"]})
    assert lanes.choose(d, b, [base, new], [new], 8, time.time())[1] == {"batch/b": ("batch/a",)}
    lanes.discard(d, b, "batch/a", "r1", "exited 1")
    assert lanes.choose(d, b, [base, new], [new], 8, time.time()) == ([], {})
    later = SimpleNamespace(id="batch/a", fields={"paths": ["x.py"], "lease": {"holder": "r2", "block": "lane"}})
    assert lanes.choose(d, b, [later, new], [new], 8, time.time())[1] == {"batch/b": ("batch/a",)}   # a new lease


def test_a_base_whose_take_fails_takes_nothing_on_top(tmp_path, monkeypatch):
    """lesson-1, lesson-3: a look plans b on top of a, then a's take fails (the budget, bounds.room, ergostat stopping):
    b is not taken with ``on`` naming a lane that does not run, nor is d on top of b; c, apart, is. The next look,
    the take working, a runs apart and b on top of it."""
    p = project(tmp_path, ahead=2)
    d, _ = dispatcher(p, monkeypatch)
    take, refuse = d.take, {"batch/a"}
    monkeypatch.setattr(d, "take", lambda b, it, **k: None if it.id in refuse else take(b, it, **k))
    ready(p, {"a": ["x.py"], "b": ["x.py"], "c": ["z.py"], "d": ["x.py"]})
    tick(d, p)
    assert held(d) == {"batch/c": ()}
    assert all(state(p, i).state == "ready" for i in "abd")
    refuse.clear()
    tick(d, p)
    assert held(d) == {"batch/c": (), "batch/a": (), "batch/b": ("batch/a",), "batch/d": ("batch/a", "batch/b")}


def test_an_unknown_cost_is_the_worst_case(tmp_path, monkeypatch):
    """lesson-3: no ``each:`` and no run measured yet: one lane, whatever ``most`` and ``within``. Runs measured at 2
    cores and 2g: four within 8 and 8g. Runs measuring cores only: memory unknown, one lane again."""
    p = project(tmp_path, each=False)
    ln = p.model.spec.blocks["lane"].takes.lanes
    assert (ln.cpu, ln.memory) == (0.0, 0)
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {str(n): [f"f{n}.py"] for n in range(6)})
    tick(d, p)
    assert len(held(d)) == 1
    ran(p, cpu=20.0, seconds=10.0, memory=2 * G)
    d.lanes_cost.clear()
    tick(d, p)
    assert len(held(d)) == 4
    assert lanes.room(ln, (None, None)) == 1 and lanes.room(ln, (2.0, None)) == 1 and lanes.room(ln, (None, 2 * G)) == 1
    assert lanes.room(ln, (0.0, 0.0)) == 4                                # measured near nothing: most, never more
    (tmp_path / "x").mkdir()
    p2 = project(tmp_path / "x", each=False)
    p2.events.add("agent.ran", item="lane", source="ergostat", data={"exit": 0, "seconds": 10.0, "resources": {"cpu": 5.0}})
    assert lanes.cost(SimpleNamespace(p=p2, e=None), p2.model.spec.blocks["lane"], time.time()) == (0.5, None)


def ran(p, cpu: float, seconds: float, memory: int) -> None:
    p.events.add("agent.ran", item="lane", source="ergostat",
                 data={"exit": 0, "seconds": seconds, "resources": {"cpu": cpu, "memory_peak": memory}})


def test_lanes_never_exceed_the_declared_resource_bounds(tmp_path, monkeypatch):
    """within 8 cores, 8g; each 2 and 2g, most 4: four lanes. The block's runs measured at 3 cores and 3g: two
    (never more held, as runs end and new ones start). The cost unreadable: one."""
    p = project(tmp_path)
    d, _ = dispatcher(p, monkeypatch)
    ready(p, {str(n): [f"f{n}.py"] for n in range(7)})
    tick(d, p)
    assert len(held(d)) == 4
    ran(p, cpu=30.0, seconds=10.0, memory=3 * G)
    d.lanes_cost.clear()
    for i in list(held(d))[:3]:
        end(d, p, i.split("/")[1], "landed")
    tick(d, p)
    assert len(held(d)) == 2                                              # one left, one new: 2 x 3 cores within 8
    tick(d, p)
    assert len(held(d)) == 2
    ln = p.model.spec.blocks["lane"].takes.lanes
    assert lanes.room(ln, (0.0, 0.0)) == 4 and lanes.room(ln, (3.0, 3 * G)) == 2 and lanes.room(ln, None) == 1
    assert lanes.room(ln, (100.0, 0.0)) == 1                              # one lane always runs (said in SPEC)
    monkeypatch.setattr(p.events, "query", lambda *a, **k: (_ for _ in ()).throw(OSError("unreadable")))
    d.lanes_cost.clear()
    assert lanes.cost(d, p.model.spec.blocks["lane"], time.time()) is None


def test_the_bound_holds_for_any_queue():
    """Random queues through ``plan``: never more starts than free, never two apart lanes overlapping, never deeper than
    ahead, and an item never starts before an earlier waiting one it overlaps."""
    rnd = random.Random(7)
    for _ in range(400):
        files = [f"f{k}" for k in range(rnd.randint(1, 6))]
        pick = lambda fs=files: frozenset(rnd.sample(fs, rnd.randint(1, len(fs)))) if rnd.random() > 0.05 else None  # noqa: E731
        running = [(f"r{k}", pick(), ()) for k in range(rnd.randint(0, 2))]
        waiting = [(f"w{k}", pick()) for k in range(rnd.randint(0, 6))]
        free, ahead = rnd.randint(-1, 4), rnd.randint(0, 2)
        got = lanes.plan(waiting, running, free, ahead)
        assert len(got) <= max(0, free)
        paths = {i: p for i, p, _ in running} | dict(waiting)
        before = [i for i, _, _ in running]
        for i, on in got:                         # every lane it shares a path with is on its chain, not too deep
            assert len(on) <= ahead
            assert all(j in on for j in before if lanes.overlap(paths[i], paths[j])), (i, on, running, got)
            before.append(i)
        started = {i for i, _ in got}
        for k, (i, p) in enumerate(waiting):      # never ahead of an earlier waiting item it shares a path with
            if i in started:
                assert all(j in started for j, q in waiting[:k] if lanes.overlap(p, q)), (waiting, got)


def test_lanes_checked_with_their_bounds(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("LANES", LANES.replace("AHEAD", "1"))))
    spec, _ = read(tmp_path / "ergostat.yaml")
    assert spec.blocks["lane"].takes.lanes == Lanes("paths", 4, 8.0, 8 * G, 2.0, 2 * G, 1, ("landed",))
    good = "{apart: paths, most: 2, within: {cpu: 4, memory: 4g}}"
    for bad in ("{apart: paths, most: 17, within: {cpu: 4, memory: 4g}}", "{apart: paths, most: 0, within: {cpu: 4, memory: 4g}}",
                "{apart: paths, most: 2, ahead: 5, within: {cpu: 4, memory: 4g}}", "{apart: paths, most: 2}",
                "{apart: paths, most: 2, within: {cpu: .nan, memory: 4g}}", "{apart: paths, most: 2, within: {cpu: 4, memory: 0}}",
                "{apart: paths, most: 2, within: {cpu: 4, memory: " + "9" * 400 + "}}",
                "{apart: paths, most: 2, within: {cpu: 4, memory: 4g}, each: {cpu: 5}}", "{most: 2, within: {cpu: 4, memory: 4g}}",
                "{apart: paths, most: 2, within: {cpu: 4, memory: 4g}, passed: nowhere}", "3",
                good.replace("most: 2", "most: true"), good[:-1] + ", later: 1}"):
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("LANES", f", lanes: {bad}")))
        _, problems = read(tmp_path / "ergostat.yaml")
        assert any("takes.lanes" in x.message for x in problems if x.level == "error"), bad
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("LANES", f", lanes: {good}")))
    spec, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"] and spec.blocks["lane"].takes.lanes.most == 2
    assert len(lanes.plan([(str(k), frozenset({str(k)})) for k in range(40)], [], 10_000, 99)) == 40
    assert lanes.plan([("a", frozenset("x")), ("b", frozenset("x"))], [("r", frozenset("x"), ())], 9, 99)[1][1] == ("r", "a")


def test_a_lane_on_top_needs_its_passed_states(tmp_path):
    """Without ``passed:`` no base could be told failed (a base left ``failed`` would let its lane on top stand), so
    ``ahead`` above 0 needs it, and a falsy ``passed`` (false, 0, {}, [], "") is refused, not read as none declared.
    At run time an end with no ``passed`` declared never passes (lesson-3: the worst case)."""
    good = "{apart: paths, most: 2, within: {cpu: 4, memory: 4g}"
    for bad in (", ahead: 1}", ", ahead: 2, passed: []}", ", ahead: 1, passed: false}", ", passed: false}",
                ", passed: 0}", ", passed: {}}", ", passed: []}", ', passed: ""}', ", ahead: 1, passed: [landed, 0]}"):
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("LANES", f", lanes: {good}{bad}")))
        _, problems = read(tmp_path / "ergostat.yaml")
        assert any("takes.lanes" in x.message and x.code == "bad-lanes" for x in problems if x.level == "error"), bad
    for ok, ps in ((", ahead: 1, passed: landed}", ("landed",)), ("}", ())):
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("LANES", f", lanes: {good}{ok}")))
        spec, problems = read(tmp_path / "ergostat.yaml")
        assert not [x for x in problems if x.level == "error"], ok
        assert spec.blocks["lane"].takes.lanes.passed == ps
    b = SimpleNamespace(takes=SimpleNamespace(lanes=Lanes("paths", 2, 4.0, G, 0.0, 0)))
    assert not lanes.passed(b, "ack", "failed") and not lanes.passed(b, "ack", "landed")
    b.takes.lanes = Lanes("paths", 2, 4.0, G, 0.0, 0, 1, ("landed",))
    assert lanes.passed(b, "ack", "landed") and not lanes.passed(b, "ack", "failed")
    assert not lanes.passed(b, "nack", "landed")


FIXTURE = Path(__file__).parent / "fixtures" / "lanes_replay.json"


def test_fixture_replay_merges_per_hour_against_one_lane():
    """The fixture queue through the dispatcher's rule: one lane (today's queue) against three lanes apart by paths,
    one deep on top, within 12 cores at 4 a lane. Every passing batch lands either way; the lanes land them faster,
    and never hold more lanes than the bound."""
    batches = json.loads(FIXTURE.read_text())["batches"]
    one = lanes.replay(batches, Lanes("paths", 1, 12.0, 12 * G, 4.0, G))
    many = lanes.replay(batches, Lanes("paths", 3, 12.0, 12 * G, 4.0, G, ahead=1))
    print(f"\none lane: {one['merged']} merged in {one['minutes']} min, {one['per_hour']}/h; "
          f"three lanes: {many['merged']} merged in {many['minutes']} min, {many['per_hour']}/h, "
          f"{many['discarded']} discarded, at most {many['most_held']} held")
    passing = sum(1 for b in batches if b["passes"])
    assert one["merged"] == many["merged"] == passing and one["failed"] == many["failed"] == 3
    assert one["most_held"] == 1 and many["most_held"] <= 3
    assert many["per_hour"] >= 2 * one["per_hour"], (one, many)
    assert one["order"] == [b["id"] for b in batches if b["passes"]]
    assert many["discarded"] >= 1                                         # batch/10 on top of the red batch/04
    tight = lanes.replay(batches, Lanes("paths", 3, 12.0, 12 * G, 4.0, G, ahead=1), cost=(6.0, 0.0))
    assert tight["most_held"] <= 2 and tight["merged"] == passing          # measured at 6 cores: two lanes

@pytest.mark.parametrize("ahead", [0, 1, 2])
def test_replay_lands_on_top_only_after_its_base(ahead):
    """Every batch overlapping, each on top quicker than its base: a lane on top lands only after all it is on (the
    first four in the queue's order, never one overtaking its base), the red one fails once, and with ahead the lanes
    on top of it are discarded and run again."""
    xs = [{"id": f"b{k}", "at": 0, "minutes": 10 - k, "passes": k != 2, "touches": ["x"]} for k in range(6)]
    got = lanes.replay(xs, Lanes("x", 4, 8.0, G, 1.0, 1, ahead=ahead))
    assert sorted(got["order"]) == ["b0", "b1", "b3", "b4", "b5"] and got["failed"] == 1
    assert got["order"][:2] == ["b0", "b1"]
    assert (got["discarded"] > 0) == (ahead > 0)
