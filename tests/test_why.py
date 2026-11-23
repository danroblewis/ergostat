"""Why an item is not done (SPEC §5a, *Why it is not done*; ergostat/why/): each kind of root, from what the model
declares, with its owner and next step; this factory's stalls of 2026-11-22 replayed; a cycle, a missing dependency
and an unreadable field answered, not raised; and an answer read from the item index, quickly."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.leases import TAKEN
from ergostat.store import Project
from ergostat.why import answer

NOW = time.time()
UP = {"running": True, "pid": os.getpid(), "beat": NOW, "said": f"pid {os.getpid()}"}
DOWN = {"running": False, "pid": None, "beat": NOW - 3600, "said": "no engine holds the run lock"}

MODEL = """
stocks:
  open:
    unit: switch
    sensor: {manual: true}
  spend:
    unit: usd
    sensor: {manual: true}
  intake:
    unit: notes
    sensor: {items: note, state: open, every: 1m}
goals:
  spend-low:
    stock: spend
    hold: "<= 5"
items:
  ticket:
    id: ticket/*
    states: [todo, doing, review, done, held]
    on: {ticket.opened: todo, ticket.started: doing, ticket.reviewed: review, ticket.done: done, ticket.held: held}
    relations:
      blocked_by: ticket
  note:
    id: note/*
    states: [open, shut]
    on: {note.opened: open, note.shut: shut}
messages:
  done: {ticket: [done], note: [shut]}
  paused: {ticket: [held]}
budget: {daily: 5, max-cost: 1}
blocks:
  gate:
    type: expr
    in: {o: stock.open, i: stock.intake, over: goal.spend-low.off}
    expr: o * i * (1 - over)
  worker:
    type: program
    run: "true"
    takes: {kind: ticket, at: todo, to: [review]}
    pool: 1
    in: block.gate
  reviewer:
    type: ai
    prompt: review it
    takes: {kind: ticket, at: review}
    actions: [publish]
actions:
  publish:
    run: "true"
    gate: approve
"""


def project(tmp_path, text=MODEL) -> Project:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def take(p, item, block, run="r1", pid=None, ttl=600.0, at=None, fence=1):
    p.events.add(TAKEN, item=item, source="ergostat", at=at or NOW - 60,
                 data={"run": run, "block": block, "fence": fence, "ttl": ttl, "max": 2, "pid": pid or os.getpid()})


def gate_open(p, value=1.0):
    p.measurements.add("block/gate", value, at=NOW - 120)


def why(p, item, engine=UP):
    return answer(p, item, now=NOW, engine=engine)


# ---- each kind of root: the right root, owner and next step

def test_work_a_run_holds_it(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    take(p, "ticket/1", "worker")
    a = why(p, "ticket/1")
    assert a["root"]["kind"] == "work" and "worker" in a["root"]["owner"] and "being worked" in a["root"]["says"]
    assert a["next"]["command"] == "ergostat lease ticket/1"
    assert a["now"]["state"] == "leased" and a["summary"].startswith("ticket/1 has been in leased for")


def series(p, stock) -> str:
    return next(iter(p.model.spec.stocks[stock].sensors.values())).series


def readings(p, o=1.0, i=1.0, off=False):
    p.measurements.add(series(p, "open"), o, at=NOW - 200)
    p.measurements.add(series(p, "intake"), i, at=NOW - 200)
    p.events.add("loop.off" if off else "loop.holding", item="spend-low", source="ergostat", at=NOW - 150, data={})
    gate_open(p, 0.0 if not (o and i and not off) else 1.0)


def test_person_a_gate_read_by_hand(tmp_path):
    p = project(tmp_path)
    readings(p, o=0.0)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "person" and r["who"].startswith("a person, reading open.") and "o is 0" in r["says"], r
    assert r["command"].startswith("ergostat sensor open.") and r["command"].endswith("--read V")


def test_person_the_owner_asked_for_a_gated_action(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 500)
    p.events.add("ticket.reviewed", item="ticket/1", at=NOW - 400)
    take(p, "ticket/1", "reviewer", at=NOW - 300)
    p.events.add("ergostat.action.requested", item="ergostat.action/abc123", source="reviewer", at=NOW - 200,
                 data={"action": "publish", "item": "ticket/1", "block": "reviewer", "gate": "approve"})
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "person" and r["who"] == "the owner" and r["since"] == pytest.approx(NOW - 200)
    assert r["command"] == "ergostat inbox action/abc123 --approve | --deny"


def test_full_pool_names_what_holds_it(tmp_path):
    p = project(tmp_path)
    gate_open(p)
    for i in (1, 2):
        p.events.add("ticket.opened", item=f"ticket/{i}", at=NOW - 100 + i)
    take(p, "ticket/1", "worker")
    r = why(p, "ticket/2")["root"]
    assert r["kind"] == "pool-full" and r["owner"] == "worker" and "1 of 1" in r["says"] and "ticket/1" in r["says"]


def test_budget_refusing_runs(tmp_path):
    p = project(tmp_path)
    gate_open(p)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    p.events.add("budget.refused", item="worker", source="ergostat", at=NOW - 30,
                 data={"why": "4.50 spent and 0.00 reserved of 5 today; this run reserves 1"})
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "gate" and r["gate"] == "budget" and "4.50 spent" in r["says"] and r["owner"] == "the owner"
    assert r["evidence"][0]["link"].startswith("/api/events/")


def test_old_budget_refusal_followed_by_a_start_is_not_the_cause(tmp_path):
    p = project(tmp_path)
    gate_open(p)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    p.events.add("budget.refused", item="worker", source="ergostat", at=NOW - 60, data={"why": "over"})
    p.events.add("agent.started", item="worker", source="ergostat", at=NOW - 30, data={})
    assert why(p, "ticket/1")["root"]["kind"] != "gate"


def test_gate_refusing_because_a_limit_goal_is_off(tmp_path):
    p = project(tmp_path)
    readings(p, off=True)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "gate" and r["gate"] == "gate" and "1 - over is 0" in r["says"], r["says"]
    assert "goal.spend-low.off" in r["owner"] and "o is 0" not in r["says"]


def test_closed_intake(tmp_path):
    p = project(tmp_path)
    readings(p, i=0.0)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "closed" and "i is 0" in r["says"] and r["owner"] == "whatever sets stock.intake", r


def test_gate_with_no_reading_is_said_not_guessed(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    a = why(p, "ticket/1")
    assert a["root"]["kind"] == "unknown" and "no reading" in a["root"]["says"] and a["missing"]
    p.measurements.add(series(p, "open"), 1.0, at=NOW - 200)
    p.events.add("loop.holding", item="spend-low", source="ergostat", at=NOW - 150, data={})
    gate_open(p, 0.0)                                   # 0, and the input that would say why has no reading
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "unknown" and "i cannot be worked out (i: stock.intake: no reading)" in r["says"], r["says"]


def test_dead_lease_its_process_gone(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    take(p, "ticket/1", "worker", pid=dead_pid())
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "lease" and "is gone" in r["says"] and r["command"] == "ergostat run"


def test_stale_lease_past_its_expiry(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 2000)
    take(p, "ticket/1", "worker", ttl=60, at=NOW - 1000)
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "lease" and "expired" in r["says"] and "watchdog" in r["owner"]


def test_block_failing(tmp_path):
    p = project(tmp_path)
    gate_open(p)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    for i in range(3):
        p.events.add("agent.failed", item="worker", source="ergostat", at=NOW - 50 + i, data={"note": f"exited {i + 1}"})
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "block" and "last 3 runs failed" in r["says"] and "exited 3" in r["says"]
    assert r["command"] == "ergostat agent worker"


def test_block_not_running(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    r = why(p, "ticket/1", DOWN)["root"]
    assert r["kind"] == "block" and "no engine is running" in r["says"] and r["command"] == "ergostat run"


def test_engine_read_from_the_run_lock_and_heartbeat(tmp_path):
    from ergostat.why.blocks import engine_now
    p = project(tmp_path)
    assert engine_now(p, time.time())["running"] is False, "no lock held: not running"
    with open(p.dir / "run.pid", "w") as f:
        f.write(str(os.getpid()))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_EX)
        (p.dir / "heartbeat.json").write_text(json.dumps({"written": time.time(), "pid": os.getpid()}))
        assert engine_now(p, time.time())["running"] is True
        (p.dir / "heartbeat.json").write_text(json.dumps({"written": time.time() - 7200, "pid": os.getpid()}))
        got = engine_now(p, time.time())
        assert got["running"] is False and "has not passed since" in got["said"], "held, but its passes stopped"


def test_parked_and_dead_dependencies(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/b", at=NOW - 300)
    p.events.add("ticket.held", item="ticket/b", at=NOW - 200)
    p.events.add("ticket.opened", item="ticket/a", at=NOW - 100, data={"blocked_by": "ticket/b"})
    a = why(p, "ticket/a")
    assert a["root"]["kind"] == "parked" and a["root"]["item"] == "ticket/b" and a["root"]["path"] == ["ticket/a", "ticket/b"]
    assert [c["item"] for c in a["chain"]] == ["ticket/a", "ticket/b"] and "It waits on ticket/b" in a["summary"]
    p.events.add("ticket.opened", item="ticket/d", at=NOW - 90)
    for f in (1, 2):
        take(p, "ticket/d", "worker", run=f"r{f}", fence=f, at=NOW - 80 + f)
        p.events.add("ergostat.lease.expired", item="ticket/d", source="ergostat", at=NOW - 70 + f,
                     data={"run": f"r{f}", "fence": f})
    p.events.add("ticket.opened", item="ticket/c", at=NOW - 60, data={"blocked_by": "ticket/d"})
    r = why(p, "ticket/c")["root"]
    assert r["kind"] == "parked" and "dead letter" in r["says"] and r["command"] == "ergostat lease ticket/d --redrive"


def test_nothing_takes_its_state(tmp_path):
    p = project(tmp_path)
    p.events.add("note.opened", item="note/1", at=NOW - 100)
    r = why(p, "note/1")["root"]
    assert r["kind"] == "nothing" and "nothing takes note items from open" in r["says"] and r["owner"] == "the owner"


def test_a_where_that_does_not_match_its_fields(tmp_path):
    p = project(tmp_path, MODEL.replace("takes: {kind: ticket, at: todo, to: [review]}",
                                        "takes: {kind: ticket, at: todo, to: [review], where: {team: a}}"))
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100, data={"team": "b"})
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "nothing" and "team is 'b' (it takes 'a')" in r["says"] and r["owner"] == "whatever sets team"


def test_given_back_and_put_off(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 300)
    take(p, "ticket/1", "worker", at=NOW - 200)
    p.events.add("ergostat.lease.ended", item="ticket/1", source="ergostat", at=NOW - 100,
                 data={"run": "r1", "fence": 1, "how": "nack", "why": "tests failed", "after": 3600})
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "lease" and "given back by its last run (nack: tests failed)" in r["says"], r["says"]


def test_unfinished_work_outside_ergostat(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    p.events.add("ticket.started", item="ticket/1", at=NOW - 50)
    r = why(p, "ticket/1")["root"]
    assert r["kind"] == "work" and "outside ergostat" in r["says"]


def test_done_and_unknown_items(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=NOW - 100)
    p.events.add("ticket.done", item="ticket/1", at=NOW - 50)
    a = why(p, "ticket/1")
    assert a["done"] is True and a["root"] is None and "it is done" in a["summary"]
    a = why(p, "ticket/nope")
    assert a["known"] is False and "nothing is recorded about ticket/nope" in a["missing"]


def test_time_in_state_against_its_kinds_stays(tmp_path):
    p = project(tmp_path)
    for i in range(10):
        p.events.add("ticket.opened", item=f"ticket/o{i}", at=NOW - 10000 + i)
        p.events.add("ticket.started", item=f"ticket/o{i}", at=NOW - 10000 + i + 60)
    p.events.add("ticket.opened", item="ticket/slow", at=NOW - 5000)
    n = why(p, "ticket/slow")["now"]
    assert n["unusual"] is True and n["usual"]["stays"] == 10 and "longer than 100%" in n["said"]
    p.events.add("ticket.opened", item="ticket/new", at=NOW - 30)
    assert why(p, "ticket/new")["now"]["unusual"] is False
    q = project(tmp_path / "few")
    q.events.add("ticket.opened", item="ticket/1", at=NOW - 30)
    n = why(q, "ticket/1")["now"]
    assert n["unusual"] is None and "too few" in n["said"], "never guessed"


# ---- a cycle, a missing dependency, an unreadable field: answers, not errors

def test_cycle_is_an_answer(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/a", at=NOW - 100, data={"blocked_by": "ticket/b"})
    p.events.add("ticket.opened", item="ticket/b", at=NOW - 90, data={"blocked_by": "ticket/a"})
    r = why(p, "ticket/a")["root"]
    assert r["kind"] == "cycle" and "ticket/a → ticket/b → ticket/a" in r["says"] and r["owner"] == "the owner"


def test_missing_dependency_is_an_answer(tmp_path):
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/a", at=NOW - 100, data={"blocked_by": "ticket/never"})
    r = why(p, "ticket/a")["root"]
    assert r["kind"] == "missing" and r["item"] == "ticket/never" and "not known to be finished" in r["says"]


def test_unreadable_field_is_an_answer(tmp_path, monkeypatch):
    from ergostat import why as w
    p = project(tmp_path)
    p.events.add("ticket.opened", item="ticket/a", at=NOW - 100)
    take(p, "ticket/a", "worker")
    real = w.Ctx.items

    def odd(self, ids):                    # its lease as an index row might hold it: a time that is not a number
        got = real(self, ids)
        if "ticket/a" in got:
            got["ticket/a"].fields["lease"] = {"holder": "r1", "block": "worker", "taken": "yesterday"}
        return got
    monkeypatch.setattr(w.Ctx, "items", odd)
    a = why(p, "ticket/a")
    assert a["root"]["kind"] == "unknown" and "could not be read" in a["root"]["says"] and a["missing"]


# ---- this factory's stalls of 2026-11-22, replayed

FACTORY = """
items:
  gap:
    id: gap/*
    states: [open, ready, fix, building, built, in-review, approved, queued, merged, parked, closed]
    on: {gap.found: open, gap.defined: ready, gap.started: building, gap.built: built, gap.review-started: in-review,
         gap.approved: approved, gap.sent-back: fix, gap.queued: queued, gap.merged: merged, gap.parked: parked,
         gap.closed: closed}
    relations:
      depends_on: gap
messages:
  done: {gap: [merged, closed]}
  paused: {gap: [parked]}
budget: {daily: 40, max-cost: 4}
blocks:
  implementor:
    type: ai
    prompt: build it
    takes: {kind: gap, at: [fix, ready], to: [built], unblocked: true}
    pool: 9
  queue:
    type: program
    run: "true"
    takes: {kind: gap, at: [approved], to: [merged, fix]}
    pool: 1
"""


def gap(p, name, *moves, at=NOW - 3600, **data):
    p.events.add("gap.found", item=f"gap/{name}", at=at, data=data or None)
    for i, m in enumerate(moves):
        p.events.add(f"gap.{m}", item=f"gap/{name}", at=at + 60 * (i + 1))


def test_stall_dependency_chain(tmp_path):
    p = project(tmp_path, FACTORY)
    gap(p, "a", "defined", "started")
    take(p, "gap/a", "implementor")
    gap(p, "b", "defined", depends_on="gap/a")
    gap(p, "c", "defined", depends_on="gap/b")
    a = why(p, "gap/c")
    assert a["root"]["kind"] == "work" and a["root"]["item"] == "gap/a" and a["root"]["path"] == ["gap/c", "gap/b", "gap/a"]
    assert "implementor" in a["root"]["owner"] and "It waits on gap/b, which waits on gap/a" in a["summary"]


def test_stall_queue_held_by_a_lease_whose_process_died(tmp_path):
    p = project(tmp_path, FACTORY)
    gap(p, "q", "defined", "started", "built", "approved")
    take(p, "gap/q", "queue", pid=dead_pid())
    gap(p, "r", "defined", "started", "built", "approved", at=NOW - 1800)
    r = why(p, "gap/r")["root"]
    assert r["kind"] == "lease" and r["item"] == "gap/q" and r.get("via") == "queue"
    assert "pool is full" in r["says"] and "is gone" in r["says"] and r["command"] == "ergostat run"


def test_stall_every_build_refused_by_the_budget(tmp_path):
    p = project(tmp_path, FACTORY)
    for n in ("x", "y"):
        gap(p, n, "defined")
    for i in range(5):
        p.events.add("budget.refused", item="implementor", source="ergostat", at=NOW - 300 + 60 * i,
                     data={"why": "38.00 spent and 4.00 reserved of 40 today; this run reserves 4"})
    for n in ("x", "y"):
        r = why(p, f"gap/{n}")["root"]
        assert r["kind"] == "gate" and r["gate"] == "budget" and "38.00 spent" in r["says"]


def test_stall_gap_waiting_on_a_parked_gap(tmp_path):
    p = project(tmp_path, FACTORY)
    gap(p, "z", "defined", "started", "parked")
    gap(p, "y", "defined", depends_on="gap/z")
    a = why(p, "gap/y")
    assert a["root"]["kind"] == "parked" and a["root"]["item"] == "gap/z" and "paused in parked" in a["root"]["says"]


# ---- the CLI, the API and MCP answer the same

def test_cli_json_and_mcp_agree(tmp_path, capsys):
    from ergostat.cli import main
    from ergostat.mcp import Server
    p = project(tmp_path)
    p.events.add("note.opened", item="note/1")
    assert main(["-C", str(tmp_path), "why", "note/1", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["root"]["kind"] == "nothing"
    via = json.loads(Server(tmp_path).call("why", {"item": "note/1"})["content"][0]["text"])
    assert via["root"] == got["root"] and via["next"] == got["next"]
    assert main(["-C", str(tmp_path), "why", "note/1"]) == 0
    assert "The cause, nothing takes it" in capsys.readouterr().out
    assert main(["-C", str(tmp_path), "why", "note/none"]) == 2


# ---- quick, and from the index

@pytest.mark.serial
def test_factory_size_answer_under_100_ms_without_reading_an_items_events(tmp_path, monkeypatch):
    p = project(tmp_path, FACTORY)
    rows = []
    for i in range(3000):
        moves = ["gap.found", "gap.defined", "gap.started", "gap.built", "gap.approved", "gap.merged"][: 2 + i % 5]
        rows += [{"type": t, "item": f"gap/g{i}", "at": NOW - 86400 + i * 20 + k * 3, "source": "t",
                  "data": {"depends_on": f"gap/g{i - 1}"} if k == 0 and i % 7 else {}} for k, t in enumerate(moves)]
    p.events.add_many(rows)
    for i in range(20):                                  # a chain at the end, its root a parked gap
        gap(p, f"c{i}", "defined", depends_on=f"gap/c{i - 1}" if i else "gap/g2999")
    p.events.add("gap.parked", item="gap/g2999", at=NOW - 10)
    first = why(p, "gap/c19")                                     # (the index built and caught up)
    assert (first["root"] or {}).get("item") == "gap/g2999", first
    from ergostat.spec import items as its
    calls = []
    real = p.events.query
    monkeypatch.setattr(its, "one", lambda *a, **k: pytest.fail("an item folded from its events"))
    monkeypatch.setattr(p.events, "query", lambda **k: calls.append(k) or real(**k))
    best = min(_timed(lambda: why(p, "gap/c19")) for _ in range(5))
    assert best < 0.100, f"{best * 1000:.0f} ms"
    assert all(k.get("n") is not None for k in calls), f"a whole read of the record: {calls}"


def _timed(f) -> float:
    t = time.perf_counter()
    f()
    return time.perf_counter() - t
