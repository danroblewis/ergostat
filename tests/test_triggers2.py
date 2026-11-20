"""Blocks started by an event type (SPEC §9.3, *Started by an event*): a run per matching event, in the record's order,
woken by the write and caused by it; loops refused when the model is read (any length), and stopped at run time by a
budget carried on the record; mode: advise asked before each run; a hop's cost independent of the record's size."""

import json
import sqlite3
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.spec import read
from ergostat.spec import triggers as tr
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: t
items:
  ticket:
    id: ticket/*
    states: [open, triaged]
    on: {ticket.triaged: triaged}
  note:
    id: note/*
blocks:
  triage:
    type: program
    on: {event: ticket.opened, where: {team: core}, emits: [ticket.triaged, note.*]}
    run: python3 triage.py
    out: flow.triaged
stocks:
  open:
    sensor: {items: ticket, state: open, every: 1m}
flows:
  triaged:
    from: open
    sensor: {items: ticket, entering: triaged, over: 1h}
"""

TRIAGE = """
import json, os, sys
got = json.load(sys.stdin)
ev = got["event"]
assert got["trigger"] in ("event", "approved") and os.environ["ERGOSTAT_EVENT"] == ev["id"]
print(json.dumps({"event": "ticket.triaged", "item": ev["item"]}), flush=True)
print(json.dumps({"event": "note.written", "item": "note/" + ev["item"].split("/")[1]}), flush=True)
# a type it did not declare (emits:) is refused: what it says never starts it again
print(json.dumps({"event": "ticket.opened", "item": "ticket/echo", "data": {"team": "core"}}), flush=True)
"""


def project(tmp_path, text=MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    (tmp_path / "triage.py").write_text(TRIAGE)
    return Project(mdl.load(tmp_path))


def wait_for(cond, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.02)
    return cond()


def of(p, type, item="triage"):
    return p.events.query(n=None, item=item, type=type)


def opened(p, n, team="core"):
    return p.events.add("ticket.opened", item=f"ticket/{n}", source="hook", data={"team": team})


@pytest.fixture
def running(tmp_path):
    engines = []

    def go(text=MODEL):
        p = project(tmp_path, text)
        e = Engine(p, say=lambda s: None)
        e.start_all()
        engines.append(e)
        time.sleep(0.3)
        return p, e
    yield go
    for e in engines:
        e.close()


def test_a_block_on_an_event_type_runs_once_per_matching_event(running):
    p, _ = running()
    t0 = time.time()
    opened(p, 1)
    assert wait_for(lambda: of(p, "agent.started")), "the write starts it"
    assert of(p, "agent.started")[0]["time"] - t0 < 1.0, "woken by the write, not by a clock"
    opened(p, 2)
    opened(p, 3)
    assert wait_for(lambda: len(of(p, "agent.ran")) == 3)
    time.sleep(0.5)
    assert len(of(p, "agent.ran")) == 3, "once for each event"
    starts, ends = of(p, "agent.started"), of(p, "agent.ran")
    assert [s["data"]["trigger"] for s in starts] == ["event"] * 3
    assert starts[1]["time"] >= ends[0]["time"] and starts[2]["time"] >= ends[1]["time"], "one at a time, in order"


def test_its_run_and_what_it_says_are_caused_by_the_event(running):
    p, _ = running()
    ev = opened(p, 7)
    assert wait_for(lambda: of(p, "agent.ran"))
    run = of(p, "agent.started")[0]
    assert run["causedby"] == ev["id"] and run["data"]["event_seq"] == ev["seq"] and run["data"]["chain"] == ["triage"]
    said = p.events.query(n=None, item="ticket/7", type="ticket.triaged")
    assert said and said[0]["causedby"] == run["id"], "its lines are caused by the run, the run by the event"
    assert p.events.query(n=None, item="note/7")[0]["causedby"] == run["id"]


def test_where_narrows_and_undeclared_lines_are_refused(running):
    p, _ = running()
    opened(p, 1, team="web")
    two = opened(p, 2)
    assert wait_for(lambda: of(p, "agent.ran"))
    time.sleep(0.6)
    assert len(of(p, "agent.ran")) == 1, "the web team's ticket is not its"
    assert of(p, "agent.started")[0]["causedby"] == two["id"]
    refused = of(p, "agent.refused")
    assert len(refused) == 1 and "ticket.opened is not among what triage emits" in refused[0]["data"]["why"]
    assert not p.events.query(n=None, item="ticket/echo"), "an undeclared line is never recorded"


def check(tmp_path, text) -> list:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return [x for x in read(tmp_path / "ergostat.yaml")[1] if x.level == "error"]


def test_on_is_refused_beside_every_cron_or_takes_and_on_ergostats_own_types(tmp_path):
    assert not check(tmp_path, MODEL)
    for extra in ("every: 1m", "takes: {kind: ticket, at: open}", "cron: '0 3 * * *'"):
        text = textwrap.dedent(MODEL).replace("out: flow.triaged\n", f"out: flow.triaged\n    {extra}\n", 1)
        assert any(x.code == "bad-trigger" for x in check(tmp_path, text)), extra
    for own in ("agent.ran", "block.*", "trigger.stopped", "ergostat.item.joined", "loop.*"):
        text = MODEL.replace("event: ticket.opened,", f"event: [ticket.opened, {own}],")
        assert any(x.code == "bad-trigger" and "ergostat's own" in x.message for x in check(tmp_path, text)), own
    text = MODEL.replace("type: program\n    on:", "type: person\n    ask: look\n    on:")
    assert any(x.code == "bad-trigger" for x in check(tmp_path, text))


def ring(n: int, emits: bool, run: str = "true") -> str:
    """``n`` blocks, each on its own type, the last one's type the first one's: a loop of n."""
    blocks = "".join(f"""
  b{i}:
    type: program
    on: {{event: s.e{i}{f', emits: [s.e{(i + 1) % n}]' if emits else ''}}}
    run: {run.format(nxt=f's.e{(i + 1) % n}')}
    out: flow.f{i}""" for i in range(n))
    flows = "".join(f"\n  f{i}: {{to: s}}" for i in range(n))
    return f"""
name: ring
blocks:{blocks}
stocks:
  s: {{}}
flows:{flows}
"""


@pytest.mark.parametrize("n", [2, 5, 9])
def test_a_declared_loop_is_refused_by_check(tmp_path, n):
    errs = [x for x in check(tmp_path, ring(n, emits=True)) if x.code == "trigger-loop"]
    assert len(errs) == 1, [x.message for x in errs]
    assert " → ".join(f"b{i}" for i in range(n)) + " → b0" in errs[0].message
    chain = ring(n, emits=True).replace("emits: [s.e0]", "emits: [s.done]")
    assert not [x for x in check(tmp_path, chain) if x.code == "trigger-loop"], "a chain that ends is not a loop"


def test_a_prefix_or_a_self_loop_is_a_loop_and_where_is_not_read(tmp_path):
    one = MODEL.replace("emits: [ticket.triaged, note.*]", "emits: [ticket.*]")
    errs = [x for x in check(tmp_path, one) if x.code == "trigger-loop"]
    assert errs and "triage → triage" in errs[0].message


@pytest.mark.slow
@pytest.mark.parametrize("n", [2, 5, 9])
def test_an_undeclared_loop_stops_at_the_depth_budget(running, n):
    """Relayed by ``event --add`` from the run (which the trigger graph cannot see): at most DEPTH runs in a row, then
    the one event that would have gone on is recorded, with the chain, and nothing more runs."""
    p, _ = running(ring(n, emits=False, run="$ERGOSTAT_CMD event --add {nxt} --data '{{}}' > /dev/null"))
    p.events.add("s.e0", source="hook")
    stop = wait_for(lambda: p.events.query(n=None, type="trigger.stopped"), 60.0)
    assert stop and len(stop) == 1
    starts = p.events.query(n=None, type="agent.started")
    assert len(starts) == tr.DEPTH
    assert [len(s["data"]["chain"]) for s in starts] == list(range(1, tr.DEPTH + 1)), "carried, one more each hop"
    assert stop[0]["data"]["chain"] == [f"b{i % n}" for i in range(tr.DEPTH)]
    time.sleep(1.0)
    assert len(p.events.query(n=None, type="agent.started")) == tr.DEPTH, "nothing runs after it"


def test_advise_asks_before_each_triggered_run(running):
    p, e = running(MODEL.replace("    run: python3 triage.py", "    mode: advise\n    run: python3 triage.py"))
    one = opened(p, 1)
    asked = wait_for(lambda: of(p, "block.advised"))
    assert asked and asked[0]["causedby"] == one["id"] and asked[0]["data"]["event"] == one["id"]
    opened(p, 2)
    time.sleep(0.6)
    assert not of(p, "agent.started"), "nothing runs before it is approved"
    assert len(of(p, "block.advised")) == 1, "one ask at a time; the next event waits behind it"
    from ergostat.inbox import entries
    waiting = [x for x in entries.entries(p, e.spec) if x.get("block") == "triage"]
    assert waiting and "run on ticket.opened" in waiting[0]["summary"]
    p.events.add("block.approved", item="triage", source="person", data={})
    assert wait_for(lambda: of(p, "agent.ran"))
    assert of(p, "agent.started")[0]["causedby"] == one["id"], "approved, it runs on the event it asked about"
    asked = wait_for(lambda: len(of(p, "block.advised")) == 2 and of(p, "block.advised"))
    assert asked[1]["data"]["event_type"] == "ticket.opened" and asked[1]["data"]["event_seq"] > one["seq"]
    p.events.add("block.denied", item="triage", source="person", data={})
    time.sleep(0.8)
    assert len(of(p, "agent.started")) == 1, "denied: that event never runs"
    assert len(of(p, "block.advised")) == 2, "and nothing more waits"


@pytest.mark.parametrize("backend", ["segments", "sqlite"])
def test_a_hop_costs_the_same_at_10k_events(tmp_path, backend):
    """One look at a new event, deep in a chain, behind 10k others: a fixed number of reads of the record (one query,
    at most HOPS lookups by id), in SQLite each served by an index (no scan of the events table)."""
    from ergostat.store import Events
    p = project(tmp_path)
    if backend == "sqlite":
        (tmp_path / "sq").mkdir()
        p.events = Events(tmp_path / "sq")
    p.events.add_many([{"type": f"noise.k{i % 50}", "item": f"ticket/{i}", "data": {"i": i}} for i in range(10000)])
    cause = None
    for i in range(tr.DEPTH - 1):                         # a chain of triggered runs, as the engine writes them
        run = p.events.add("agent.started", item="triage", source="ergostat", causedby=cause,
                           data={"chain": ["triage"] * (i + 1)})
        cause = p.events.add("note.written", item=f"note/{i}", source="triage", causedby=run["id"])["id"]
    e = Engine(p, say=lambda s: None)
    started: list = []
    e.start = lambda b, why, extra=None, cause=None: started.append(extra) or True
    e.triggers.at["triage"] = p.events.last_seq()
    ev = p.events.add("ticket.opened", item="ticket/x", source="triage", causedby=cause, data={"team": "core"})
    reads, sql = {"get": 0, "query": 0}, []
    for name in reads:
        real = getattr(p.events, name)
        setattr(p.events, name, lambda *a, _r=real, _n=name, **k: reads.__setitem__(_n, reads[_n] + 1) or _r(*a, **k))
    try:
        if backend == "sqlite":
            with p.events._c() as c:
                c.set_trace_callback(sql.append)
                e.triggers.look()
                c.set_trace_callback(None)
        else:
            e.triggers.look()
        assert started and started[0]["chain"] == ["triage"] * tr.DEPTH and started[0]["event"]["id"] == ev["id"]
        assert reads["query"] == 1 and reads["get"] <= tr.HOPS, reads
        e.triggers.at["triage"], e.triggers.top = p.events.last_seq() - 1, -1
        t0 = time.perf_counter()
        e.triggers.look()                                 # once more, its causes remembered: no lookup at all
        assert time.perf_counter() - t0 < 0.25 and reads["get"] <= tr.HOPS
    finally:
        e.close()
    if backend == "sqlite":
        con = sqlite3.connect(p.events.path)
        selects = [q for q in sql if q.lstrip().lower().startswith("select")]
        assert selects
        for q in selects + ["select * from events where id >= 'ab' and id < 'ac' order by id limit 1"]:
            plan = " ".join(r[3] for r in con.execute("explain query plan " + q))
            assert "SCAN" not in plan, (q, plan)
        con.close()


def test_started_again_it_resumes_after_its_last_event(tmp_path, running):
    p, e = running()
    opened(p, 1)
    assert wait_for(lambda: of(p, "agent.ran"))
    e.close()
    four = opened(p, 4)                                    # written while it was stopped: it runs when started again
    p2 = Project(mdl.load(tmp_path))
    e2 = Engine(p2, say=lambda s: None)
    e2.start_all()
    try:
        assert wait_for(lambda: len(of(p2, "agent.ran")) == 2)
        time.sleep(0.5)
        assert len(of(p2, "agent.ran")) == 2, "nothing twice"
        assert json.dumps(of(p2, "agent.started")[-1]["causedby"]) == json.dumps(four["id"])
    finally:
        e2.close()
