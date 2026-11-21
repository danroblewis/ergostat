"""The day's AI budget, the permissive P3 (SPEC §9.9): docs/roadmap/overnight/run-budget-reserve.md."""

import ast
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.costs import budget
from ergostat.leases import TAKEN
from ergostat.numbers import measures
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: t
{budget}
agents:
  bot: {{kind: program}}
  anon: {{}}
items:
  ticket:
    id: ticket/*
    states: [ready, doing, done]
    on: {{ticket.started: doing, ticket.done: done}}
blocks:
  worker:
    type: program
    takes: {{kind: ticket, at: ready}}
    pool: 1
    run: "true"
  solo:
    type: program
    run: "true"
  solo2:
    type: program
    run: "true"
  free:
    type: program
    agent: bot
    run: "true"
  nameless:
    type: program
    agent: anon
    run: "true"
"""
BUDGET = "budget: {daily: 1.5, max-cost: 1}"


def project(tmp_path, bud: str = BUDGET) -> Project:
    (tmp_path / "ergostat.yaml").write_text(MODEL.format(budget=bud))
    return Project(mdl.load(tmp_path))


def engine(p) -> Engine:
    return Engine(p, say=lambda s: None)


def evs(p, type: str) -> list[dict]:
    return p.events.query(n=None, type=type)


def reserving(p) -> list[dict]:
    return [e for e in evs(p, f"{TAKEN},agent.started") if "reserve" in (e.get("data") or {})]


def spend(p, cost: float = 2.0, at: float | None = None) -> None:
    """An end of no reserving run, priced: it counts its cost (here, the whole day's budget)."""
    p.events.add("agent.ran", item="elsewhere", source="ergostat", at=at, data={"ai": {"cost_usd": cost}})


def started(p, run: str, reserve: float = 1.0, pid: int | None = None, at: float | None = None, block: str = "solo"):
    return p.events.add("agent.started", item=block, source="ergostat", id=run, at=at,
                        data={"reserve": reserve, "pid": os.getpid() if pid is None else pid})


def ended(p, run: str, data: dict | None = None, at: float | None = None, block: str = "solo"):
    return p.events.add("agent.ran", item=block, source="ergostat", causedby=run, at=at, data=data or {})


def item(p, id):
    return its.one(p.events, p.model.spec, id)


def wait_for(cond, seconds=15.0):
    end = time.time() + seconds
    while time.time() < end:
        if got := cond():
            return got
        time.sleep(0.05)
    return cond()


def errors(tmp_path, bud: str, local: str | None = None) -> list[str]:
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(MODEL.format(budget=bud))
    if local is not None:
        (tmp_path / "ergostat.local.yaml").write_text(local)
    return [x.message for x in read(tmp_path / "ergostat.yaml")[1] if x.level == "error"]


# ---- config and limits


def test_check_budget_keys(tmp_path):
    cases = {"daily: 20000, max-cost: 1": "above the ceiling", "daily: 0, max-cost: 1": "daily: out of bounds: 0 is not",
             "daily: -1, max-cost: 1": "daily: out of bounds: -1 is not", "daily: 5, max-cost: 0": "max-cost: out of bounds: 0",
             "daily: 5, max-cost: -2": "max-cost: out of bounds: -2", "daily: 5, max-cost: 6": "above budget.daily",
             "daily: 5": "missing max-cost", "max-cost: 1": "missing daily", "daily: 5, max-cost: 1, per-run: 2": "unknown key",
             "daily: lots, max-cost: 1": "a number of dollars"}
    seen = set()
    for body, says in cases.items():
        got = [m for m in errors(tmp_path, f"budget: {{{body}}}") if "budget" in m]
        assert len(got) == 1 and says in got[0], (body, got)
        seen.add(got[0])
    assert len(seen) == len(cases), "each its own message"
    assert not errors(tmp_path, BUDGET)
    assert project(tmp_path).model.spec.budget.daily == 1.5
    got = errors(tmp_path, "", local="budget: {daily: 5, max-cost: 1}\n")
    assert any("not a per-machine setting" in m for m in got), got


def test_permit_refuses_out_of_bounds_at_run_time(tmp_path):
    p = project(tmp_path)
    e, spec = engine(p), p.model.spec
    for k, v in (("daily", 20000.0), ("max_cost", 0.0), ("max_cost", 2.0)):
        spec.budget.daily, spec.budget.max_cost = 1.5, 1.0
        setattr(spec.budget, k, v)
        budget._said.clear()
        out: dict = {}
        assert e.run_block(spec.blocks["solo"], "test", outcome=out) == []
        assert e.run_block(spec.blocks["free"], "test") == []          # (a free run too: the budget itself is wrong)
        assert not evs(p, "agent.started"), k
        assert "out of bounds" in out["refused"]
        assert "out of bounds" in evs(p, "budget.refused")[-1]["data"]["why"]


def test_no_budget_changes_nothing(tmp_path):
    p = project(tmp_path, bud="")
    e = engine(p)
    spend(p, 50.0)
    e.run_block(p.model.spec.blocks["solo"], "test")
    p.events.add("ticket.opened", item="ticket/0", source="t")
    assert e.dispatch.take(p.model.spec.blocks["worker"], item(p, "ticket/0"), inline=True)
    assert len(evs(p, "agent.started")) == 1 and len(evs(p, "agent.ran")) == 2 and len(evs(p, TAKEN)) == 1
    assert not reserving(p) and not evs(p, "budget.*")


# ---- concurrency


def race(monkeypatch, first, competitor):
    """``first`` runs; at its ``_between`` it starts ``competitor`` in a thread and waits up to 1 s for the
    competitor's own ``_between`` (it fires only if the competitor read the record in the gap)."""
    fired, calls, ts = threading.Event(), [], []

    def hook():
        calls.append(1)
        if len(calls) == 1:
            ts.append(threading.Thread(target=competitor, daemon=True))
            ts[0].start()
            fired.wait(1.0)                                    # (the one timed wait: expected when the lock works)
        else:
            fired.set()
    monkeypatch.setattr(budget, "_between", hook)
    first()
    ts[0].join(30)
    assert not ts[0].is_alive()


def test_permit_lock_spans_write_run_block_then_take(tmp_path, monkeypatch):
    p = project(tmp_path)
    e, spec = engine(p), p.model.spec
    p.events.add("ticket.opened", item="ticket/0", source="t")
    it = item(p, "ticket/0")
    race(monkeypatch, lambda: e.run_block(spec.blocks["solo"], "test"),
         lambda: e.dispatch.take(spec.blocks["worker"], it, inline=True))
    assert len(reserving(p)) == 1 and reserving(p)[0]["type"] == "agent.started"
    assert len(evs(p, "budget.refused")) == 1 and item(p, "ticket/0").state == "ready"


def test_permit_lock_spans_write_take_then_run_block(tmp_path, monkeypatch):
    p = project(tmp_path)
    e, spec = engine(p), p.model.spec
    p.events.add("ticket.opened", item="ticket/0", source="t")
    it = item(p, "ticket/0")
    race(monkeypatch, lambda: e.dispatch.take(spec.blocks["worker"], it, inline=True),
         lambda: e.run_block(spec.blocks["solo"], "test"))
    assert len(reserving(p)) == 1 and reserving(p)[0]["type"] == TAKEN
    assert len(evs(p, "budget.refused")) == 1 and not evs(p, "agent.started")


COMPETITOR = """
import sys, uuid
from pathlib import Path
from ergostat import model as mdl
from ergostat.costs import budget
from ergostat.store import Project
d = Path(sys.argv[1])
p = Project(mdl.load(d))
budget._between = lambda: (d / "read").write_text("x")
run = uuid.uuid4().hex
(d / "asking").write_text("x")
got, why = budget.permit(p, p.model.spec, p.model.spec.blocks["solo2"], lambda more: p.events.add(
    "agent.started", item="solo2", source="ergostat", id=run, data=more), run)
print("refused" if got is None else "permitted")
"""


def test_permit_lock_across_processes(tmp_path, monkeypatch):
    p = project(tmp_path)
    e, spec = engine(p), p.model.spec
    procs = []

    def hook():
        procs.append(subprocess.Popen([sys.executable, "-c", COMPETITOR, str(tmp_path)], stdout=subprocess.PIPE, text=True))
        assert wait_for(lambda: (tmp_path / "asking").exists() or procs[0].poll() is not None, 60)
        end = time.time() + 1.0                                  # (the one timed wait: expected when the lock works)
        while time.time() < end and not (tmp_path / "read").exists():
            time.sleep(0.01)
    monkeypatch.setattr(budget, "_between", hook)
    e.run_block(spec.blocks["solo"], "test")
    out, _ = procs[0].communicate(timeout=60)
    assert out.strip() == "refused" and not (tmp_path / "read").exists()
    assert len(reserving(p)) == 1 and len(evs(p, "budget.refused")) == 1


# ---- refusal on every start path


def test_refused_engine_loop(tmp_path):
    p = project(tmp_path)
    spend(p)
    e = engine(p)
    assert e.start(p.model.spec.blocks["solo"], "test")
    assert wait_for(lambda: evs(p, "budget.refused") and "solo" not in e.running)
    assert not evs(p, "agent.started") and "solo" not in e.last_run


def test_refused_dispatch_loop(tmp_path):
    p = project(tmp_path)
    spend(p)
    p.events.add("ticket.opened", item="ticket/0", source="t")
    e = engine(p)
    e.start_all()
    try:
        assert wait_for(lambda: evs(p, "budget.refused"))
        assert not evs(p, TAKEN) and item(p, "ticket/0").state == "ready" and not e.dispatch.going_items()
        assert not [k for k in e.running if k.startswith("worker")]
    finally:
        e.close()


def test_refused_block_now_unleased(tmp_path, capsys):
    p = project(tmp_path)
    ended(p, "earlier", {"note": "an earlier run"})
    spend(p)
    assert main(["-C", str(tmp_path), "block", "solo", "--now"]) == 1
    out = capsys.readouterr().out
    assert "refused: budget" in out and "ran in" not in out and "earlier run" not in out
    assert not evs(p, "agent.started")


def test_refused_block_now_leased(tmp_path, capsys):
    p = project(tmp_path)
    ended(p, "earlier", {"note": "an earlier run"}, block="worker")
    spend(p)
    p.events.add("ticket.opened", item="ticket/0", source="t")
    assert main(["-C", str(tmp_path), "block", "worker", "--now"]) == 1
    out = capsys.readouterr().out
    assert "refused: budget" in out and "ran in" not in out and "earlier run" not in out
    assert not evs(p, TAKEN) and not evs(p, "agent.started") and item(p, "ticket/0").state == "ready"


def test_only_known_start_paths():
    root = Path(__file__).resolve().parent.parent / "ergostat"
    found: dict[str, set[str]] = {"agent.started": set(), "lease.taken": set()}

    def scan(node, where):
        for ch in ast.iter_child_nodes(node):
            here = [*where, ch.name] if isinstance(ch, ast.FunctionDef | ast.ClassDef) else where
            if isinstance(ch, ast.Call) and isinstance(ch.func, ast.Attribute) and ch.func.attr == "add" and ch.args:
                a = ch.args[0]
                name = a.value if isinstance(a, ast.Constant) else getattr(a, "id", getattr(a, "attr", None))
                key = {"agent.started": "agent.started", "TAKEN": "lease.taken", "ergostat.lease.taken": "lease.taken"}.get(name)
                if key:
                    found[key].add(f"{rel}:{'.'.join(where[:2])}")
            scan(ch, here)
    for f in sorted(root.rglob("*.py")):
        rel = f.relative_to(root).as_posix()
        scan(ast.parse(f.read_text()), [])
    assert found == {"agent.started": {"spec/engine.py:Engine.run_block", "spec/engine.py:Engine.judge", "runner.py:run_agent"},
                     "lease.taken": {"leases/dispatch.py:Dispatcher.take"}}


def test_free_run_not_reserved(tmp_path):
    p = project(tmp_path)
    spend(p)
    e, b = engine(p), p.model.spec.blocks
    e.run_block(b["free"], "test")
    got = evs(p, "agent.started")
    assert len(got) == 1 and got[0]["data"]["reserve"] == 0 and evs(p, "agent.ran")[-1]["causedby"] == got[0]["id"]
    for name in ("solo", "nameless"):                            # no agent, an agent of no kind: charged
        out: dict = {}
        e.run_block(b[name], "test", outcome=out)
        assert out.get("refused"), name
    assert len(evs(p, "agent.started")) == 1


def test_refusal_recorded_once_a_minute(tmp_path):
    p = project(tmp_path)
    spend(p)
    e, b = engine(p), p.model.spec.blocks
    for _ in range(3):
        e.run_block(b["solo"], "test")
        e.run_block(b["solo2"], "test")
    assert sorted(x["item"] for x in evs(p, "budget.refused")) == ["solo", "solo2"]
    d = evs(p, "budget.refused")[0]["data"]
    assert d["spent"] == 2.0 and d["reserved"] == 0 and d["daily"] == 1.5 and d["reserve"] == 1.0 and d["why"]


# ---- fail-closed accounting


def test_reserve_held_until_end_with_cost(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    p.events.add("ticket.opened", item="ticket/0", source="t")
    e = engine(p)
    b, item0 = spec.blocks["worker"], item(p, "ticket/0")
    _, _, given, run, _ = e.dispatch.take(b, item0, inline=True)
    budget.OPEN.discard(run)
    assert budget.fold(p, spec) == (0.0, 1.0)
    e.dispatch.finish(b, "ticket/0", given["fence"], run, {"stopped": True})     # given back, no end
    p.events.add("ergostat.lease.expired", item="ticket/0", source="ergostat", data={"run": run, "fence": given["fence"]})
    assert item(p, "ticket/0").state == "ready" and budget.fold(p, spec) == (0.0, 1.0), "still charged its reserve"
    ended(p, run, {"ai": {"cost_usd": 0.1}}, block="worker")
    assert budget.fold(p, spec) == (0.1, 0.0)


def test_end_without_cost_charges_reserve(tmp_path):
    p = project(tmp_path, bud="budget: {daily: 10, max-cost: 1}")
    spec = p.model.spec
    started(p, "a", reserve=0.5)
    ended(p, "a")                                                # no cost: its reserve
    assert budget.fold(p, spec) == (0.5, 0.0)
    started(p, "b", reserve=0.5)
    ended(p, "b", {"ai": {"cost_usd": None, "cost": "unpriced", "tokens": {"total": 9}}})   # AI, no price: max-cost
    assert budget.fold(p, spec) == (1.5, 0.0)
    started(p, "c", reserve=0.0, block="free")
    ended(p, "c", {"ai": {"cost_usd": None, "cost": "unpriced"}}, block="free")   # a free run, AI unpriced: max-cost
    started(p, "d", reserve=0.0, block="free")
    ended(p, "d", block="free")                                  # a free run, no AI: 0
    assert budget.fold(p, spec) == (2.5, 0.0)
    started(p, "e", reserve=0.5)
    ended(p, "e", {"ai": {"cost_usd": 0.2}})
    p.events.add("budget.closed", item="solo", source="ergostat", causedby="e", data={"run": "e", "cost_usd": None})
    assert budget.fold(p, spec) == (3.0, 0.0), "two ends: the larger charge"


@pytest.mark.parametrize("bad", [float("nan"), -5.0, float("inf"), float("-inf")])
def test_malformed_cost_counts_unknown(tmp_path, bad):
    """Guards budget._known in _charge: a cost from a run's own output that is NaN, infinite or negative is unknown,
    charged its reserve (max-cost for a run with none), so the permit still refuses."""
    p = project(tmp_path)                                        # daily 1.5, max-cost 1
    spec = p.model.spec
    started(p, "a", reserve=1.0)
    ended(p, "a", {"ai": {"cost_usd": bad, "cost": "reported"}})
    assert budget.fold(p, spec) == (1.0, 0.0)
    run = uuid.uuid4().hex
    got, why = budget.permit(p, spec, spec.blocks["solo"], lambda more: started(p, run, pid=more["pid"]), run)
    assert got is None and "spent" in why and not [e for e in reserving(p) if e["id"] == run]
    for i, (end, data) in enumerate([("agent.ran", {"cost_usd": bad}), ("budget.closed", {"cost_usd": bad})]):
        r = f"free{i}"
        started(p, r, reserve=0.0, block="free")
        p.events.add(end, item="free", source="ergostat", causedby=r, data={"run": r, **data})
    assert budget.fold(p, spec) == (3.0, 0.0), "a free run's malformed cost: max-cost"


def test_unended_reserve_does_not_age_out(tmp_path):
    p = project(tmp_path, bud="budget: {daily: 10, max-cost: 1}")
    spec, now = p.model.spec, time.time()
    started(p, "old", at=now - 2 * 86400)
    budget.OPEN.add("old")
    try:
        assert budget.recover(p, spec, every=0) == []
        assert budget.fold(p, spec) == (0.0, 1.0)
    finally:
        budget.OPEN.discard("old")
    started(p, "done", at=now - 3 * 86400, pid=1 << 22)
    ended(p, "done", {"ai": {"cost_usd": 0.5}}, at=now - 2 * 86400)
    assert budget.fold(p, spec) == (0.0, 1.0), "ended over a day ago: not counted, and not reserved"
    assert budget.recover(p, spec, every=0) == ["old"] and not [x for x in evs(p, "budget.closed") if x["causedby"] == "done"]
    started(p, "ancient", at=now - 8 * 86400, pid=1 << 22)
    ended(p, "ancient", {"ai": {"cost_usd": 0.3}}, at=now - 3600)
    assert budget.fold(p, spec) == pytest.approx((1.3, 0.0)), "a start past 7 days, priced: its real cost"


def test_orphan_closed_by_recovery(tmp_path):
    p = project(tmp_path, bud="budget: {daily: 10, max-cost: 1}")
    spec = p.model.spec
    child = subprocess.Popen(["true"])
    child.wait()
    started(p, "orphan", pid=child.pid)
    started(p, "mine")
    started(p, "lost")                                           # this process's pid, not open here
    started(p, "theirs", pid=os.getppid())                       # a live process of another's
    budget.OPEN.add("mine")
    e = engine(p)
    stop = threading.Event()

    def holder():                                                # the dispatcher's and engine's locks held elsewhere
        with e.dispatch.lock, e.lock:
            got.set()
            stop.wait(10)
    got = threading.Event()
    threading.Thread(target=holder, daemon=True).start()
    got.wait(5)
    try:
        t = threading.Thread(target=lambda: closed.extend(budget.recover(p, spec, every=0)), daemon=True)
        closed: list = []
        t.start()
        t.join(10)
        assert not t.is_alive(), "recovery takes no lock but its own"
    finally:
        stop.set()
        budget.OPEN.discard("mine")
    assert sorted(closed) == ["lost", "orphan"]
    assert all(x["data"]["cost_usd"] is None for x in evs(p, "budget.closed"))
    assert budget.fold(p, spec) == (2.0, 2.0)
    assert budget.fold(p, spec, now=time.time() + 86400 + 60) == (0.0, 2.0), "the close drops out a day after"


def test_permit_lists_the_run_under_the_lock(tmp_path):
    p = project(tmp_path)
    spec, done = p.model.spec, []
    run = uuid.uuid4().hex

    def write(more):
        assert run in budget.OPEN
        t = threading.Thread(target=lambda: done.append(budget.recover(p, spec, every=0)), daemon=True)
        t.start()
        t.join(0.3)
        assert not done, "recovery waits for the flock"
        ts.append(t)
        return started(p, run, pid=more["pid"])
    ts: list = []
    got, why = budget.permit(p, spec, spec.blocks["solo"], write, run)
    ts[0].join(10)
    budget.OPEN.discard(run)
    assert got and done == [[]], "the run was open when recovery read it"


def test_recover_copies_open_before_reading(tmp_path, monkeypatch):
    """Guards the order in budget.recover: OPEN is copied before the record is read, so a run of this process that
    writes its end and leaves OPEN in between is seen ended, not closed at its reserve."""
    p = project(tmp_path, bud="budget: {daily: 10, max-cost: 1}")
    spec = p.model.spec
    started(p, "r")
    budget.OPEN.add("r")

    def read_then_end(*a, real=budget.read):                     # the run ends right after the read, as engine._ran
        got = real(*a)                                           # does it: its end, then out of OPEN
        ended(p, "r", {"ai": {"cost_usd": 0.1}})
        budget.OPEN.discard("r")
        return got
    monkeypatch.setattr(budget, "read", read_then_end)
    try:
        assert budget.recover(p, spec, every=0) == []
    finally:
        budget.OPEN.discard("r")
        monkeypatch.undo()
    assert not evs(p, "budget.closed") and budget.fold(p, spec) == pytest.approx((0.1, 0.0))


def test_run_block_crash_closes_reserve(tmp_path, monkeypatch):
    p = project(tmp_path)
    e, spec = engine(p), p.model.spec

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(Engine, "program", boom)
    with pytest.raises(RuntimeError):
        e.run_block(spec.blocks["solo"], "test")
    run = evs(p, "agent.started")[0]["id"]
    closed = evs(p, "budget.closed")
    assert [x["data"]["run"] for x in closed] == [run] and closed[0]["data"]["cost_usd"] is None
    assert budget.fold(p, spec) == (1.0, 0.0) and run not in budget.OPEN


def test_lost_take_releases_reserve(tmp_path):
    p = project(tmp_path)
    spec, e = p.model.spec, engine(p)
    p.events.add("ticket.opened", item="ticket/0", source="t")
    it = item(p, "ticket/0")
    p.events.add(TAKEN, item="ticket/0", source="ergostat", data={"item": "ticket/0", "run": "other", "block": "worker",
                                                                     "fence": 1, "ttl": 60, "max": 3, "back": "ready"})
    assert e.dispatch.take(spec.blocks["worker"], it, inline=True) is None
    mine = [x for x in reserving(p)]
    closed = evs(p, "budget.closed")
    assert len(mine) == 1 and [(x["data"]["run"], x["data"]["cost_usd"]) for x in closed] == [(mine[0]["data"]["run"], 0.0)]
    assert budget.fold(p, spec) == (0.0, 0.0)


def test_retaken_item_keeps_old_reserve(tmp_path):
    p = project(tmp_path, bud="budget: {daily: 10, max-cost: 1}")
    spec, e = p.model.spec, engine(p)
    b = spec.blocks["worker"]
    p.events.add("ticket.opened", item="ticket/0", source="t")
    runs = []
    for _ in range(2):
        _, _, given, run, _ = e.dispatch.take(b, item(p, "ticket/0"), inline=True)
        runs.append(run)
        e.dispatch.finish(b, "ticket/0", given["fence"], run, {"stopped": True})
    assert runs[0] != runs[1] and sorted(x["data"]["run"] for x in reserving(p)) == sorted(runs)
    assert budget.fold(p, spec) == (0.0, 2.0)
    ended(p, runs[1], {"ai": {"cost_usd": 0.1}}, block="worker")
    assert budget.fold(p, spec) == (0.1, 1.0), "the new run's end leaves the old run's reserve"


def test_leased_run_block_reserves_once(tmp_path):
    p = project(tmp_path, bud="budget: {daily: 10, max-cost: 1}")
    spec, e = p.model.spec, engine(p)
    p.events.add("ticket.opened", item="ticket/0", source="t")
    e.dispatch.once(spec.blocks["worker"], "test")
    start = evs(p, "agent.started")
    assert len(start) == 1 and "reserve" not in start[0]["data"]
    assert start[0]["id"] == evs(p, TAKEN)[0]["data"]["run"] and len(reserving(p)) == 1
    assert budget.fold(p, spec) == (1.0, 0.0), "charged once: its end has no cost, so its reserve"


def test_budget_events_trip_no_coherence_or_graph(tmp_path):
    from ergostat import coherence, graph, state
    p = project(tmp_path)

    def look():
        snap = state.snapshot(p, state.WINDOW, None)
        w = graph.wiring(p.model, p, snap, graph.select(p.model))
        got = coherence.of_project(p, p.model.spec)
        nodes = [n for n in w.get("nodes") or [] if n["id"] != "agent:ergostat"]   # (its own bookkeeping, as a lease's)
        return {k: v for k, v in got.items() if k not in ("since", "until")}, w.get("edges"), nodes
    before = look()
    p.events.add("budget.refused", item="solo", source="ergostat", data={"reserve": 1, "why": "x"})
    p.events.add("budget.closed", item="solo", source="ergostat", causedby="r", data={"run": "r", "cost_usd": None})
    assert look() == before


# ---- the measure


def test_budget_left_value(tmp_path):
    p = project(tmp_path, bud="budget: {daily: 10, max-cost: 1}")
    started(p, "a")
    budget.OPEN.add("a")
    started(p, "b")
    ended(p, "b", {"ai": {"cost_usd": 0.25}})
    spend(p, 0.5)
    try:
        assert measures.measure(p, "ergostat.budget.left") == pytest.approx(8.25)
        assert measures.measure(p, "budget.left") == pytest.approx(8.25)
    finally:
        budget.OPEN.discard("a")


def test_budget_left_fails_closed(tmp_path, monkeypatch):
    p = project(tmp_path, bud="")
    with pytest.raises(measures.MeasureError):
        measures.measure(p, "ergostat.budget.left")
    p = project(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path)
    e = engine(p)

    def broken(*a, **k):
        raise OSError("the record is gone")
    monkeypatch.setattr(p.events, "query", broken)
    with pytest.raises(measures.MeasureError):
        measures.measure(p, "ergostat.budget.left")
    got = measures.all_of(p)
    assert got["ergostat.budget.left"] is None and "record is gone" in got["ergostat.budget.left_error"]
    out: dict = {}
    e.run_block(p.model.spec.blocks["solo"], "test", outcome=out)
    monkeypatch.undo()
    assert "could not be read" in out["refused"] and not evs(p, "agent.started")
