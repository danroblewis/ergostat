"""Operating states (SPEC §9.5, *Operating states*): declared in the model, entered by the owner or a goal's trip, left
by the owner only, and the state in force capping the pool of every block that takes items. Dispatch and trips are
driven directly (``tick()``, ``trip(now=...)``), never waited for with a sleep; a run's end is polled with a deadline."""

import json
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.leases import ENDED, TAKEN
from ergostat.leases import dispatch as dispatch_mod
from ergostat.leases.fold import held
from ergostat.operating import ENTERED, KIND, LEFT, WATCHING, acts, item_of, trips
from ergostat.operating import fold as op_fold
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.store import Project

OWNER: dict = {}                                   # the owner's environment: no ERGOSTAT_RUN

# a run that marks it started, then waits for its own go (go-ticket-N) or everyone's (go), then moves its item on
RUN = ('f=$(echo $ERGOSTAT_ITEM | tr / -); touch ran-$f; '
       'while [ ! -f go-$f ] && [ ! -f go ]; do sleep 0.05; done; echo "{\\"event\\": \\"ticket.done\\"}"')

BASE = """
name: t
items:
  ticket:
    id: ticket/*
    states: [ready, doing, done]
    on: {ticket.started: doing, ticket.done: done}
stocks:
  disk:
    unit: GB
    sensors:
      a: {run: "echo SENSE", every: 1h}
      b: {run: "echo SENSE", every: 1h}
goals:
  room: {stock: disk, hold: "<= 5"}
blocks:
  worker:
    type: program
    takes: {kind: ticket, at: ready}
    pool: POOL
    run: RUN
    lease: {ttl: 1m}
"""

EXAMPLE = """
operating:
  incident:
    rank: 3
    pool: 0
    description: harm found; nothing new starts until the owner has looked
  freeze:
    rank: 2
    pool: 0
    description: the mainline is red; running work finishes, nothing new starts
    trips:
      room: {}
  maintenance:
    rank: 1
    pool: 1
    description: one run at a time while the owner works on the system
"""


def write(d, ops: str, pool: int = 3, sense: int = 1, base: str = BASE) -> None:
    text = base.replace("POOL", str(pool)).replace("RUN", json.dumps(RUN)).replace("SENSE", str(sense))
    (d / "ergostat.yaml").write_text(textwrap.dedent(text) + textwrap.dedent(ops))


def setup(tmp_path, ops: str = EXAMPLE, pool: int = 3, n: int = 5, sense: int = 1):
    write(tmp_path, ops, pool, sense)
    p = Project(mdl.load(tmp_path))
    for i in range(n):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", at=time.time() - 100 + i)
    said: list[str] = []
    e = Engine(p, say=said.append)
    return p, e, said


def held_n(p) -> int:
    return sum(1 for it in its.project(p.events, p.model.spec, "ticket", transcript=False) if held(it.fields))


def wait_for(cond, seconds=15.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def release(tmp_path, p, e) -> None:
    (tmp_path / "go").touch()
    try:
        assert wait_for(lambda: held_n(p) == 0 and not e.running), "every run ends"
    finally:
        e.close()


def problems(tmp_path, ops: str) -> list:
    write(tmp_path, ops)
    _, got = read(tmp_path / "ergostat.yaml")
    return [x for x in got if x.level == "error"]


# ---- declared


def test_compile_example_and_kind_only_when_declared(tmp_path, monkeypatch):
    assert problems(tmp_path, EXAMPLE) == []
    s = mdl.load(tmp_path).spec
    assert KIND in s.items and s.items[KIND].states == ["entered", "left"]
    assert (s.operating["incident"].rank, s.operating["maintenance"].pool, s.operating["freeze"].trips) == (3, 1, {"room": None})
    plain = tmp_path / "plain"
    plain.mkdir()
    p, e, _ = setup(plain, "", n=2)
    assert KIND not in p.model.spec.items and not p.model.spec.operating

    def boom(*a, **k):
        raise AssertionError("in_force read for a model without operating:")
    monkeypatch.setattr(op_fold, "in_force", boom)
    monkeypatch.setattr(trips, "check", boom)
    e.dispatch.tick()
    assert held_n(p) == 2, "leases are still taken, and nothing about operating states was read"
    release(plain, p, e)


@pytest.mark.parametrize("ops, code", [
    ("operating:\n  Freeze: {rank: 1}\n", "bad-name"),
    ("operating:\n  freeze: {rank: 0}\n", "bad-number"),
    ("operating:\n  freeze: {rank: 1, pool: -1}\n", "bad-number"),
    ("operating:\n  freeze: {rank: 1}\n  incident: {rank: 1}\n", "rank-taken"),
    ("operating:\n  freeze: {rank: 1, trips: {nogoal: {}}}\n", "unknown-ref"),
    ("operating:\n  freeze: {rank: 1, trips: {room: {unknown-after: soon}}}\n", "bad-duration"),
    ("operating:\n  freeze: {rank: 1, colour: red}\n", "unknown-key"),
    ("operating:\n  freeze: {rank: 1, trips: {room: {after: 1m}}}\n", "unknown-key"),
])
def test_compile_refuses_bad_states(tmp_path, ops, code):
    got = problems(tmp_path, ops)
    assert [x.code for x in got] == [code], got


def test_compile_refuses_unknown_after_on_an_unmeasured_goal(tmp_path):
    base = BASE.replace("    sensors:\n      a: {run: \"echo SENSE\", every: 1h}\n      b: {run: \"echo SENSE\", every: 1h}\n", "")
    base = base.replace("goals:\n", "auxiliaries:\n  x: {unit: n}\ngoals:\n  bare: {auxiliary: x, hold: '<= 1'}\n")
    write(tmp_path, "operating:\n  freeze: {rank: 1, trips: {bare: {unknown-after: 1m}}}\n", base=base)
    _, got = read(tmp_path / "ergostat.yaml")
    assert [x.code for x in got if x.level == "error"] == ["unknown-after-unmeasured"]


def test_pool_rises_with_rank_refused(tmp_path):
    bad = "operating:\n  maintenance: {rank: 3, pool: 1}\n  freeze: {rank: 2, pool: 0}\n"
    assert [x.code for x in problems(tmp_path, bad)] == ["pool-rises-with-rank"]
    uncapped = "operating:\n  open: {rank: 2}\n  freeze: {rank: 1, pool: 0}\n"     # no cap counts as infinite
    assert [x.code for x in problems(tmp_path, uncapped)] == ["pool-rises-with-rank"]
    for good in ("operating:\n  a: {rank: 2, pool: 1}\n  b: {rank: 1, pool: 1}\n",
                 "operating:\n  a: {rank: 2, pool: 0}\n  b: {rank: 1, pool: 1}\n  c: {rank: 0}\n".replace("rank: 0", "rank: 5, pool: 0"),
                 "operating:\n  a: {rank: 2, pool: 0}\n  b: {rank: 1}\n"):
        assert problems(tmp_path, good) == [], good


# ---- scheduling the pool


def test_state_caps_block_pool(tmp_path):
    p, e, _ = setup(tmp_path, "operating:\n  careful: {rank: 1, pool: 1}\n")
    acts.enter(p, e.spec, "careful", "slowly", env=OWNER)
    e.dispatch.tick()
    assert held_n(p) == 1, "careful's pool 1 over the block's 3"
    e.dispatch.tick()
    assert held_n(p) == 1
    acts.leave(p, e.spec, "careful", "done", env=OWNER)
    e.dispatch.tick()
    assert held_n(p) == 3, "left: the block's own pool"
    release(tmp_path, p, e)
    wide = tmp_path / "wide"
    wide.mkdir()
    p, e, _ = setup(wide, "operating:\n  loose: {rank: 1, pool: 5}\n", pool=2)
    acts.enter(p, e.spec, "loose", "wide open", env=OWNER)
    e.dispatch.tick()
    e.dispatch.tick()
    assert held_n(p) == 2, "a state's pool never raises a block's (lesson-4)"
    release(wide, p, e)


def test_pool_zero_takes_nothing_running_work_finishes(tmp_path):
    p, e, _ = setup(tmp_path)
    e.dispatch.tick()
    assert held_n(p) == 3
    assert wait_for(lambda: len(list(tmp_path.glob("ran-*"))) == 3), "the three runs started"
    acts.enter(p, e.spec, "freeze", "mainline red", env=OWNER)
    (tmp_path / "go").touch()
    assert wait_for(lambda: len(p.events.query(n=None, type=ENDED)) == 3), "running work finishes"
    for _ in range(3):
        e.dispatch.tick()
    assert all(x["data"]["how"] == "ack" for x in p.events.query(n=None, type=ENDED)), "not killed: each ended ack"
    assert len(p.events.query(n=None, type=TAKEN)) == 3, "nothing new starts under freeze"
    e.close()


def test_freeze_and_maintenance_both_entered_take_nothing(tmp_path):
    p, e, _ = setup(tmp_path)
    acts.enter(p, e.spec, "freeze", "red", env=OWNER)
    acts.enter(p, e.spec, "maintenance", "owner at work", env=OWNER)       # the latest entered has pool 1
    assert op_fold.in_force(p, e.spec)[:2] == ("freeze", 0)
    e.dispatch.tick()
    assert held_n(p) == 0 and not p.events.query(n=None, type=TAKEN)
    e.close()


def test_pool_is_smallest_among_entered(tmp_path):
    p, e, _ = setup(tmp_path, "operating:\n  high: {rank: 2, pool: 0}\n  low: {rank: 1, pool: 2}\n")
    e.spec.operating["high"].pool, e.spec.operating["low"].pool = 2, 0     # (the compiler's check bypassed)
    acts.enter(p, e.spec, "high", "x", env=OWNER)
    acts.enter(p, e.spec, "low", "y", env=OWNER)
    assert op_fold.in_force(p, e.spec)[:2] == ("high", 0), "the top state is high, the pool the least entered"
    e.dispatch.tick()
    assert held_n(p) == 0
    e.close()


def test_unreadable_fold_is_worst_case(tmp_path, monkeypatch):
    p, e, _ = setup(tmp_path, "operating:\n  careful: {rank: 1, pool: 1}\n", pool=2)
    acts.enter(p, e.spec, "careful", "slowly", env=OWNER)

    def boom(*a, **k):
        raise OSError("disk gone")
    with monkeypatch.context() as m:
        m.setattr(op_fold, "entered", boom)
        top, pool, why = op_fold.in_force(p, e.spec)
        assert pool == 0 and "could not be read" in why and "disk gone" in why
        e.dispatch.tick()
        assert held_n(p) == 0, "neither careful's 1 nor the block's 2"
    e.dispatch.tick()
    assert held_n(p) == 1, "readable again: careful's pool 1"
    release(tmp_path, p, e)


def test_undeclared_entered_state_counts_as_pool_zero(tmp_path, capsys):
    p, e, _ = setup(tmp_path)
    acts.enter(p, e.spec, "freeze", "red", env=OWNER)
    write(tmp_path, EXAMPLE.replace("  freeze:\n    rank: 2\n    pool: 0\n    description: the mainline is red; running work "
                                    "finishes, nothing new starts\n    trips:\n      room: {}\n", ""))
    e.swap(mdl.load(tmp_path))
    assert "freeze" not in e.spec.operating
    assert op_fold.in_force(p, e.spec)[1] == 0
    e.dispatch.tick()
    assert held_n(p) == 0, "an entered state the model no longer declares holds pool 0"
    assert main(["-C", str(tmp_path), "operating", "--json"]) == 0
    listed = {x["state"]: x for x in json.loads(capsys.readouterr().out)["declared"]}
    assert listed["freeze"]["now"] == "entered" and listed["freeze"]["declared"] is False
    assert main(["-C", str(tmp_path), "operating", "leave", "freeze", "--why", "fixed"]) == 0
    e.dispatch.tick()
    assert held_n(p) == 3, "left: leases resume"
    release(tmp_path, p, e)


def test_removing_the_whole_section_lifts_every_state_and_restoring_it_restores_them(tmp_path):
    """The chosen answer to the plan review: a model without ``operating:`` reads nothing (invariant 12), so removing
    the section lifts every state, as documented; the record keeps the entry, so putting the section back holds again."""
    p, e, _ = setup(tmp_path, n=6)
    acts.enter(p, e.spec, "freeze", "red", env=OWNER)
    write(tmp_path, "")
    e.swap(mdl.load(tmp_path))
    e.dispatch.tick()
    assert held_n(p) == 3, "no operating: read: the block's own pool"
    write(tmp_path, EXAMPLE)
    e.swap(mdl.load(tmp_path))
    (tmp_path / "go").touch()
    assert wait_for(lambda: held_n(p) == 0 and not e.running)
    e.dispatch.tick()
    assert len(p.events.query(n=None, type=TAKEN)) == 3, "freeze is entered again, from the record"
    e.close()


def test_state_entered_between_check_and_take_gives_back(tmp_path, monkeypatch):
    p, e, said = setup(tmp_path, n=1)
    real = dispatch_mod.terms

    def owner_freezes(spec, b):                   # the step between tick's room and the TAKEN write
        if not p.events.query(n=None, type=ENTERED):
            acts.enter(p, e.spec, "freeze", "red", env=OWNER)
        return real(spec, b)
    monkeypatch.setattr(dispatch_mod, "terms", owner_freezes)
    e.dispatch.tick()
    taken = p.events.query(n=None, type=TAKEN)
    ended = p.events.query(n=None, type=ENDED)
    assert len(taken) == 1 and len(ended) == 1
    d = ended[0]["data"]
    assert d["how"] == "nack" and d["count"] is False and "freeze" in d["why"] and ended[0]["seq"] > taken[0]["seq"]
    it = its.one(p.events, e.spec, "ticket/0")
    assert it.state == "ready" and it.fields["lease"]["attempts"] == 0 and not held(it.fields)
    assert not e.dispatch.going.get("worker") and not e.running, "no run started"
    assert not list(tmp_path.glob("ran-*")), "the block's program never ran"
    e.close()
    assert not list(tmp_path.glob("ran-*"))


def test_a_recheck_that_raises_after_taken_leaves_nothing_running(tmp_path, monkeypatch):
    p, e, _ = setup(tmp_path, n=1)
    acts.enter(p, e.spec, "maintenance", "one at a time", env=OWNER)

    def unreadable(*a, **k):                      # the re-read after TAKEN (its flying() read or its ENDED write)
        raise OSError("record unreadable")
    monkeypatch.setattr(e.dispatch, "entered_meanwhile", unreadable)
    it = its.one(p.events, e.spec, "ticket/0")
    with pytest.raises(OSError):
        e.dispatch.take(e.spec.blocks["worker"], it)
    assert len(p.events.query(n=None, type=TAKEN)) == 1
    assert not e.running and not e.dispatch.going.get("worker"), "the key is not left running"
    assert not list(tmp_path.glob("ran-*")), "no run started"
    e.close()


def test_now_refused_under_pool_zero(tmp_path):
    p, e, said = setup(tmp_path)
    b = e.spec.blocks["worker"]
    acts.enter(p, e.spec, "freeze", "red", env=OWNER)
    assert e.dispatch.once(b, "by hand") == []
    assert any("freeze" in s and "not run" in s for s in said)
    assert not p.events.query(n=None, type=TAKEN) and not list(tmp_path.glob("ran-*"))
    e.close()


def test_now_under_pool_one_with_a_run_in_flight_still_runs(tmp_path):
    p, e, _ = setup(tmp_path)
    b = e.spec.blocks["worker"]
    acts.enter(p, e.spec, "maintenance", "one at a time", env=OWNER)
    e.dispatch.tick()
    assert held_n(p) == 1                                       # ticket/0 in flight
    (tmp_path / "go-ticket-1").touch()
    e.dispatch.once(b, "by hand")                               # --now ignores the block's pool, and so the state's
    ends = p.events.query(n=None, type=ENDED, item="ticket/1")
    assert [x["data"]["how"] for x in ends] == ["ack"], "not given back for the run in flight"
    release(tmp_path, p, e)


# ---- entered and left


def test_owner_enter_leave_cli(tmp_path, capsys, monkeypatch):
    p, e, _ = setup(tmp_path, n=0)
    e.close()
    d = str(tmp_path)
    assert main(["-C", d, "operating", "enter", "freeze", "--why", "mainline red"]) == 0
    assert main(["-C", d, "operating", "enter", "nosuch", "--why", "x"]) == 1
    assert main(["-C", d, "operating", "enter", "freeze"]) == 2, "--why is required"
    capsys.readouterr()
    assert main(["-C", d, "operating", "--json"]) == 0
    got = {x["state"]: x for x in json.loads(capsys.readouterr().out)["declared"]}
    assert got["freeze"]["now"] == "entered" and got["freeze"]["by"] == "owner" and got["freeze"]["why"] == "mainline red"
    assert got["incident"]["now"] == "left" and got["maintenance"]["pool"] == 1
    assert main(["-C", d, "operating"]) == 0 and "freeze" in capsys.readouterr().out
    monkeypatch.setenv("ERGOSTAT_RUN", "run-123")
    assert main(["-C", d, "operating", "leave", "freeze", "--why", "a run tries"]) == 1
    assert "only the owner" in capsys.readouterr().err
    assert main(["-C", d, "operating", "enter", "incident", "--why", "a run saw harm"]) == 0
    ev = p.events.query(n=None, type=ENTERED, item=item_of("incident"))[-1]
    assert ev["data"]["by"] == "run" and ev["causedby"] == "run-123"
    monkeypatch.delenv("ERGOSTAT_RUN")
    assert main(["-C", d, "operating", "leave", "freeze", "--why", "green again"]) == 0
    assert main(["-C", d, "operating", "leave", "freeze", "--why", "again"]) == 1, "not entered"
    bad = p.events.add(LEFT, item=item_of("incident"), source="x", causedby="run-123", data={"by": "owner", "why": "sneaky"})
    it = its.one(p.events, p.model.spec, item_of("incident"))
    assert it.state == "entered" and it.refused[-1]["event"] == bad["id"] and "only the owner" in it.refused[-1]["why"]


def test_reentered_state_clears_old_fields(tmp_path):
    p, e, _ = setup(tmp_path, n=0)
    e.close()
    s = p.model.spec
    p.events.add(ENTERED, item=item_of("freeze"), source="ergostat", data={"by": "trip", "why": "room off", "goal": "room",
                                                                           "spell": "off:x"})
    it = its.one(p.events, s, item_of("freeze"))
    assert it.fields["by"] == "trip" and it.fields["trips"] == [{"goal": "room", "spell": "off:x", "event": it.moves[0]["event"]}]
    acts.leave(p, s, "freeze", "fixed", env=OWNER)
    acts.enter(p, s, "freeze", "by hand, for the release", env=OWNER)
    it = its.one(p.events, s, item_of("freeze"))
    assert it.state == "entered" and it.fields["by"] == "owner" and it.fields["why"] == "by hand, for the release"
    assert it.fields["trips"] == []


# ---- trips


def entries(p, state="freeze") -> list:
    return p.events.query(n=None, type=ENTERED, item=item_of(state))


def state_of(p, state="freeze"):
    return its.one(p.events, p.model.spec, item_of(state))


def test_crossing_trips_once_per_crossing(tmp_path):
    p, e, _ = setup(tmp_path, n=0)
    s = e.spec
    off = p.events.add("loop.off", item="room", source="ergostat")
    assert trips.check(p, s) is None
    got = entries(p)
    assert len(got) == 1 and got[0]["data"]["spell"] == f"off:{off['id']}" and got[0]["causedby"] == off["id"]
    assert state_of(p).fields["by"] == "trip"
    acts.leave(p, s, "freeze", "looked at it", env=OWNER)
    for _ in range(3):
        trips.check(p, s)
    assert len(entries(p)) == 1 and state_of(p).state == "left", "the owner's leave holds for the same crossing"
    p.events.add("loop.holding", item="room", source="ergostat")
    trips.check(p, s)
    assert len(entries(p)) == 1
    again = p.events.add("loop.off", item="room", source="ergostat")
    trips.check(p, s)
    assert [x["data"]["spell"] for x in entries(p)][-1] == f"off:{again['id']}" and state_of(p).state == "entered"
    e.close()


def test_owner_leave_in_trip_gap(tmp_path, monkeypatch):
    """Guards against check skipping its write because a read showed the state entered: the owner's leave lands
    between the read and the write, and the trip must still enter it."""
    p, e, _ = setup(tmp_path, n=0)
    s = e.spec
    acts.enter(p, s, "freeze", "by hand", env=OWNER)
    p.events.add("loop.off", item="room", source="ergostat")
    real = trips._record

    def owner_leaves_first(*a, **k):
        if state_of(p).state == "entered":
            acts.leave(p, s, "freeze", "done by hand", env=OWNER)
        return real(*a, **k)
    monkeypatch.setattr(trips, "_record", owner_leaves_first)
    trips.check(p, s)
    st = state_of(p)
    assert st.state == "entered" and st.fields["by"] == "trip"
    assert len(entries(p)) == 2
    monkeypatch.setattr(trips, "_record", real)
    trips.check(p, s)
    assert len(entries(p)) == 2, "no second entry for the same spell"
    e.close()


UNREAD = EXAMPLE.replace("      room: {}", "      room: {unknown-after: 60s}")


def test_unknown_after_trips_on_record_clock(tmp_path):
    p, e, _ = setup(tmp_path, UNREAD, n=0)
    s = e.spec
    t0 = time.time() - 5000
    for x in ("a", "b"):
        p.measurements.add(f"sensor/disk.{x}", 1, at=t0)
    trips.check(p, s, now=t0 + 59)
    assert not entries(p)
    trips.check(p, s, now=t0 + 61)
    assert [x["data"]["spell"] for x in entries(p)] == [f"unread:a:{t0!r}", f"unread:b:{t0!r}"], "one spell per sensor"
    acts.leave(p, s, "freeze", "seen", env=OWNER)
    t1 = t0 + 100
    for x in ("a", "b"):
        p.measurements.add(f"sensor/disk.{x}", 1, at=t1)
    trips.check(p, s, now=t1 + 10)
    assert len(entries(p)) == 2, "read again: no trip"
    trips.check(p, s, now=t1 + 61)
    assert [x["data"]["spell"] for x in entries(p)][-2:] == [f"unread:a:{t1!r}", f"unread:b:{t1!r}"], "a new spell"
    acts.leave(p, s, "freeze", "seen", env=OWNER)
    t3 = t1 + 1000                                               # b goes silent; a keeps reading
    for x in ("a", "b"):
        p.measurements.add(f"sensor/disk.{x}", 1, at=t3)
    for k in (30, 60, 100):
        p.measurements.add("sensor/disk.a", 1, at=t3 + k)
    trips.check(p, s, now=t3 + 101)
    assert [x["data"]["spell"] for x in entries(p)][-1] == f"unread:b:{t3!r}", "one live sensor never hides a dead one"
    e.close()


def test_a_sensor_left_silent_never_hides_another_going_silent(tmp_path):
    """The order the dead sensor is already the oldest does not cover: a goes silent and the owner leaves its spell;
    then b, still reading, goes silent too. a is still the oldest, yet b's silence is a spell of its own and trips."""
    p, e, _ = setup(tmp_path, UNREAD, n=0)
    s = e.spec
    t0 = time.time() - 5000
    p.measurements.add("sensor/disk.a", 1, at=t0)
    for k in range(0, 200, 30):
        p.measurements.add("sensor/disk.b", 1, at=t0 + k)
    trips.check(p, s, now=t0 + 190)
    assert [x["data"]["spell"] for x in entries(p)] == [f"unread:a:{t0!r}"]
    acts.leave(p, s, "freeze", "a is known to be dead", env=OWNER)
    trips.check(p, s, now=t0 + 200)
    assert len(entries(p)) == 1 and state_of(p).state == "left"
    trips.check(p, s, now=t0 + 180 + 61)                        # b's newest reading is t0+180
    assert [x["data"]["spell"] for x in entries(p)][-1] == f"unread:b:{t0 + 180!r}" and state_of(p).state == "entered"
    e.close()
    # a never read, its unread:a:never left: b's later silence still trips
    other = tmp_path / "n"
    other.mkdir()
    write(other, UNREAD)
    p = Project(mdl.load(other))
    e = Engine(p, say=lambda s: None)
    t = time.time() - 5000
    trips.check(p, e.spec, now=t)                               # (the watching event: a's clock)
    p.measurements.add("sensor/disk.b", 1, at=t + 50)
    trips.check(p, e.spec, now=t + 61)
    assert [x["data"]["spell"] for x in entries(p)] == ["unread:a:never"]
    acts.leave(p, e.spec, "freeze", "a is not wired yet", env=OWNER)
    trips.check(p, e.spec, now=t + 50 + 61)
    assert [x["data"]["spell"] for x in entries(p)][-1] == f"unread:b:{t + 50!r}"
    e.close()


@pytest.mark.parametrize("events", ["segments", "sqlite"])
def test_rolled_up_and_pruned_record_still_answers_its_spells(tmp_path, events):
    """The engine's upkeep rolls an item's events older than 7 days into a snapshot, and forgets what is older than
    keep (30 days). Neither may take a trip's entry, the owner's leave or a watching event: a sensor still silent,
    or one never read, must not trip again, and the never-read clock must not restart."""
    from ergostat import rollup
    write(tmp_path, UNREAD.replace("      room: {unknown-after: 60s}", "      room: {unknown-after: 60s}\n"
                                   "  maintenance-2:\n    rank: 4\n    pool: 0\n    description: x\n"
                                   "    trips:\n      room: {unknown-after: 60s}")
          + f"storage: {{events: {events}}}\n")
    p = Project(mdl.load(tmp_path))
    s = p.model.spec
    t0 = time.time() - 100
    p.measurements.add("sensor/disk.a", 1, at=t0)                # b never read
    trips.check(p, s, now=t0)
    assert len(p.events.query(n=None, type=WATCHING)) == 2      # two states trip on room: two on goal.room
    trips.check(p, s, now=t0 + 61)
    for st in ("freeze", "maintenance-2"):
        assert {x["data"]["spell"] for x in entries(p, st)} == {f"unread:a:{t0!r}", "unread:b:never"}
        acts.leave(p, s, st, "seen", env=OWNER)
    for days in (8, 40):                                         # rolled up past 7 days; then all of it past keep
        now = time.time() + days * 86400
        rollup.compact(p, now=now)
        p.events.prune(now - (86400 if days > 8 else 30 * 86400))
        for st in ("freeze", "maintenance-2"):
            assert len(entries(p, st)) == 2 and state_of(p, st).state == "left", "the answered spells kept"
        assert len(p.events.query(n=None, type=WATCHING)) == 2
        trips.check(p, s, now=now)
        for st in ("freeze", "maintenance-2"):
            assert state_of(p, st).state == "left", "the owner's leave not undone by the same silence"
            assert len(entries(p, st)) == 2, "no second entry for a spell the owner left"
        assert len(p.events.query(n=None, type=WATCHING)) == 2, "the never-read clock not restarted"


def test_restart_neither_reenters_nor_resets_clock(tmp_path):
    # (a) a crossing, entered by its trip and left by the owner: a restarted engine records no new loop.off nor entry
    p, e, _ = setup(tmp_path, n=0, sense=9)                       # the sensors read 9: room (<= 5) is off
    e.start_all()
    try:
        assert wait_for(lambda: entries(p), 20), "the engine's crossing tripped freeze"
    finally:
        e.close()
    offs = len(p.events.query(n=None, type="loop.off", item="room"))
    acts.leave(p, p.model.spec, "freeze", "seen", env=OWNER)
    reads = p.measurements.count("sensor/disk.a")
    e2 = Engine(Project(mdl.load(tmp_path)), say=lambda s: None)
    e2.start_all()
    try:
        assert wait_for(lambda: p.measurements.count("sensor/disk.a") > reads, 20), "the restarted engine read room again"
        assert wait_for(lambda: e2.status.get("room") == "off", 5)
        e2.dispatch.trip()
    finally:
        e2.close()
    assert len(p.events.query(n=None, type="loop.off", item="room")) == offs, "status restored from the record"
    assert len(entries(p)) == 1 and state_of(p).state == "left"
    # (b) read at t0, the engine restarted at t0+50, unknown-after 60s: it trips at t0+61, not t0+110
    other = tmp_path / "b"
    other.mkdir()
    t0 = time.time() - 50
    write(other, UNREAD)
    p = Project(mdl.load(other))
    for x in ("a", "b"):
        p.measurements.add(f"sensor/disk.{x}", 1, at=t0)
    e3 = Engine(p, say=lambda s: None)                           # (now: t0 + 50)
    e3.dispatch.trip(now=t0 + 61)
    assert [x["data"]["spell"] for x in entries(p)] == [f"unread:a:{t0!r}", f"unread:b:{t0!r}"]
    e3.close()
    # (c) left by the owner: no restart nor later check enters it again for that spell
    acts.leave(p, p.model.spec, "freeze", "seen", env=OWNER)
    for k in (61, 200, 4000):
        e4 = Engine(Project(mdl.load(other)), say=lambda s: None)
        e4.dispatch.trip(now=t0 + k)
        e4.close()
    assert len(entries(p)) == 2 and state_of(p).state == "left"


def test_never_read_clock_starts_at_watching_event(tmp_path):
    p, e, _ = setup(tmp_path, UNREAD, n=0)
    t = time.time()
    e.dispatch.trip(now=t)
    w = p.events.query(n=None, type=WATCHING)
    assert len(w) == 1 and w[0]["item"] == "goal.room" and w[0]["data"] == {"state": "freeze"} and w[0]["time"] == t
    e.close()
    e2 = Engine(Project(mdl.load(tmp_path)), say=lambda s: None)
    e2.dispatch.trip(now=t + 30)
    e2.dispatch.trip(now=t + 60)
    assert len(p.events.query(n=None, type=WATCHING)) == 1, "a restart finds it and writes none"
    assert not entries(p)
    e2.dispatch.trip(now=t + 61)
    assert [x["data"]["spell"] for x in entries(p)] == ["unread:a:never", "unread:b:never"]
    e2.close()


def test_unreadable_trip_inputs_hold_dispatch(tmp_path, monkeypatch):
    p, e, said = setup(tmp_path, UNREAD, n=2)
    for x in ("a", "b"):
        p.measurements.add(f"sensor/disk.{x}", 1)
    before = p.events.last_seq()

    def boom(*a, **k):
        raise OSError("measurements unreadable")
    with monkeypatch.context() as m:
        m.setattr(p.measurements, "latest", boom)
        e.dispatch.trip()
        assert p.events.last_seq() == before, "nothing recorded"
        assert any("could not be read" in s for s in said)
        e.dispatch.tick()
        e.dispatch.tick()
        assert held_n(p) == 0, "pool 0 until a trip check reads cleanly"
    e.dispatch.trip()
    e.dispatch.tick()
    assert held_n(p) == 2
    release(tmp_path, p, e)


def test_a_trip_write_that_raises_holds_dispatch(tmp_path, monkeypatch):
    """The trip's read succeeds but its write (the watching event) raises: that look holds at pool 0 as well, rather
    than dispatching on the previous hold (review operating-states-4)."""
    p, e, _ = setup(tmp_path, UNREAD, n=2)
    real = p.events.add

    def boom(type_, *a, **k):
        if type_.startswith("ergostat.operating."):
            raise OSError("record not writable")
        return real(type_, *a, **k)
    with monkeypatch.context() as m:
        m.setattr(p.events, "add", boom)
        e.dispatch.trip()
        assert e.dispatch.hold and "could not be checked" in e.dispatch.hold
        e.dispatch.tick()
        assert held_n(p) == 0, "pool 0 after a trip write raised"
    release(tmp_path, p, e)


@pytest.mark.parametrize("lead", [True, False])
def test_trips_are_checked_by_the_lead_alone(tmp_path, monkeypatch, lead):
    """With shards every engine runs a dispatcher; only the lead's checks the trips, so a spell is entered once and an
    owner's leave is not undone by another shard's look (review operating-states-11, lesson-1)."""
    p, e, _ = setup(tmp_path, UNREAD, n=0)
    looked: list[bool] = []
    monkeypatch.setattr(dispatch_mod, "LOOK", 0.0)
    monkeypatch.setattr(e, "leads", lambda: lead)
    monkeypatch.setattr(e.dispatch, "trip", lambda now=None: looked.append(True))
    monkeypatch.setattr(e.dispatch, "tick", lambda *a, **k: e.stop.set())
    try:
        e.dispatch.run()                                       # one look: its tick stops the loop
    finally:
        e.close()
    assert looked == ([True] if lead else [])


def test_declared_states_beside_the_operating_state_of_12k(tmp_path, capsys):
    """Main's ``operating: {away-after:}`` and its states (SPEC §12k) share the section, the event prefix and the topic
    with the declared states: away-after is no state, a declared state's events never read as incident there, and
    one ``ergostat operating`` serves both."""
    from ergostat.actions import operating as ops
    assert problems(tmp_path, EXAMPLE + "  away-after: 1h\n") == []
    p, e, _ = setup(tmp_path, EXAMPLE + "  away-after: 1h\n", n=0)
    e.close()
    assert set(p.model.spec.operating) == {"incident", "freeze", "maintenance"} and p.model.spec.away_after == 3600
    d = str(tmp_path)
    assert main(["-C", d, "operating", "enter", "freeze", "--why", "red"]) == 0
    trips.check(p, p.model.spec, time.time())                  # (may write a watching event: also not 12k's)
    assert ops.read(p).state == "normal", "a declared state's events are not the §12k state's"
    assert main(["-C", d, "operating", "incident", "--note", "outage"]) == 0
    assert ops.read(p).state == "incident" and op_fold.in_force(p, p.model.spec)[0] == "freeze"
    capsys.readouterr()
    assert main(["-C", d, "operating", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["state"] == "incident" and {x["state"]: x["now"] for x in got["declared"]}["freeze"] == "entered"
    assert main(["-C", d, "operating", "freeze", "--why", "x"]) == 2, "--why belongs to enter and leave"
    assert main(["-C", d, "operating", "enter", "freeze", "--note", "x", "--why", "y"]) == 2
    (tmp_path / "ergostat.yaml").write_text("name: t\noperating: {away-after: 1h}\n")
    _, got = read(tmp_path / "ergostat.yaml")
    q = Project(mdl.load(tmp_path))
    assert not [x for x in got if x.level == "error"] and KIND not in q.model.spec.items, "away-after alone: no kind"
