"""A machine block's output lines take effect as they arrive (SPEC §9.1): an event line is recorded and folded into its
item while the run goes on, renews the lease its run holds, and is refused at once when that lease has ended
(fencing); a run stopped part way keeps what it printed; a bare number is still the output of a run that finished
well; a burst of thousands of lines neither deadlocks nor starves the engine."""

import json
import shlex
import sys
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.leases import EXPIRED
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = shlex.quote(sys.executable)

FINDINGS = """
name: s
projections:
  finding:
    query: key.startswith('finding/')
    fields:
      state:
        values: [new, kept]
    events:
      finding-found:
        when: type == 'finding.found'
        '...': data
        state: set('new')
      finding-kept:
        when: type == 'finding.kept'
        '...': data
        state: set('kept')
      other:
        when: true
        '...': data
stocks:
  found:
    unit: findings
flows:
  noted:
    to: found
blocks:
  researcher:
    type: {type}
{extra}    run: {run}
    out: flow.noted
"""


@pytest.fixture(autouse=True)
def _stopping_cleared():
    yield
    runner.STOPPING.clear()


def project(tmp_path, text: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def findings(tmp_path, script: str, type: str = "program", extra: str = "") -> Project:
    (tmp_path / "research.py").write_text(textwrap.dedent(script))
    text = FINDINGS.replace("{type}", type).replace("{extra}", extra).replace("{run}", json.dumps(f"{PY} research.py"))
    return project(tmp_path, text)


def wait_for(cond, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def in_background(e: Engine, name: str) -> threading.Thread:
    t = threading.Thread(target=e.run_block, args=(e.spec.blocks[name], "test"), daemon=True)
    t.start()
    return t


def ended(p) -> list[dict]:
    return p.events.query(n=None, type="agent.ran,agent.failed", item="researcher")


SLOW = """
    import json, sys, time
    sys.stdin.read()
    for i in range(1, 4):
        print(json.dumps({"event": "finding.found", "item": f"finding/{i}", "data": {"n": i}}), flush=True)
        time.sleep(1)
"""


@pytest.mark.parametrize("type,extra", [("program", ""), ("ai", "    prompt: Look for findings.\n")])
def test_each_event_is_recorded_and_folded_while_the_run_goes_on(tmp_path, type, extra):
    """A slow program printing a finding every second: each is in the record, and folded into its item, before the run
    ends; an ``ai`` block with ``run:`` is read the same way."""
    p = findings(tmp_path, SLOW, type, extra)
    e = Engine(p, say=lambda s: None)
    t = in_background(e, "researcher")
    started = wait_for(lambda: p.events.query(n=1, type="agent.started", item="researcher"))
    assert started
    run = started[0]["id"]
    for i in range(1, 4):
        it = wait_for(lambda i=i: its.one(p.events, p.model.spec, f"finding/{i}"), 5)
        assert it and it.state == "new" and it.fields["n"] == i
        if i < 3:
            assert t.is_alive() and not ended(p), f"finding/{i} landed before the run ended"
    got = p.events.query(n=None, type="finding.found")
    assert [x["item"] for x in got] == ["finding/1", "finding/2", "finding/3"], "in the order printed"
    assert all(x["causedby"] == run and x["source"] == "researcher" for x in got), "caused by the run"
    assert got[1]["time"] - got[0]["time"] > 0.7, "each recorded when it was printed, not all at the end"
    t.join(10)
    ran = ended(p)
    assert ran and ran[0]["type"] == "agent.ran" and ran[0]["data"]["events"] == 3
    assert ran[0]["time"] - got[0]["time"] > 1.7


def test_lines_keep_their_order_and_a_partial_line_waits_for_the_rest(tmp_path):
    """An event, a bad line, an event: recorded in that order. Half a line printed, then the rest a moment later, is one
    line."""
    p = findings(tmp_path, """
        import sys, time
        sys.stdin.read()
        out = sys.stdout
        out.write('{"event": "finding.found", "item": "finding/1"}\\n')
        out.write('{"event": "Not A Type"}\\n')
        out.write('{"event": "finding.found", ')
        out.flush()
        time.sleep(0.6)
        out.write('"item": "finding/2"}\\nnot json, for the log\\n')
        out.flush()
    """)
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks["researcher"], "test")
    recorded = [x for x in p.events.query(n=None) if x["type"] in ("finding.found", "agent.refused")]
    assert [(x["type"], x["item"]) for x in recorded] == [("finding.found", "finding/1"), ("agent.refused", "researcher"),
                                                         ("finding.found", "finding/2")]
    assert its.one(p.events, p.model.spec, "finding/2").state == "new"
    log = (p.dir / "logs" / "researcher.log").read_text()
    assert "not json, for the log" in log and "finding.found" not in log


def test_a_run_stopped_part_way_keeps_what_it_printed(tmp_path):
    """Its timeout kills it, and so does the owner's stop: what it said before stands."""
    p = findings(tmp_path, """
        import json, sys, time
        sys.stdin.read()
        for i in (1, 2):
            print(json.dumps({"event": "finding.found", "item": f"finding/{i}"}), flush=True)
        print(json.dumps({"out": "flow.noted", "moved": 2}), flush=True)
        time.sleep(60)
        print(json.dumps({"event": "finding.found", "item": "finding/3"}), flush=True)
    """, extra="    timeout: 1.5s\n")
    e = Engine(p, say=lambda s: None)
    t0 = time.monotonic()
    moved = e.run_block(p.model.spec.blocks["researcher"], "test")
    assert time.monotonic() - t0 < 10
    assert moved == ["noted"], "what it moved counts, though it was stopped"
    assert {x["item"] for x in p.events.query(n=None, type="finding.found")} == {"finding/1", "finding/2"}
    failed = ended(p)[0]
    assert failed["type"] == "agent.failed" and "timeout" in failed["data"]["note"] and failed["data"]["events"] == 2
    # the owner stops the next one
    p.events.add("finding.kept", item="finding/1", source="t")
    e2 = Engine(project(tmp_path, (tmp_path / "ergostat.yaml").read_text().replace("    timeout: 1.5s\n", "")),
                say=lambda s: None)
    t = in_background(e2, "researcher")
    assert wait_for(lambda: len(p.events.query(n=None, type="finding.found")) == 4, 10)
    assert e2.stop_run("researcher")
    t.join(10)
    assert not t.is_alive()
    last = ended(p)[-1]
    assert last["type"] == "agent.ran" and last["data"]["note"] == "stopped as the owner asked"
    assert last["data"]["events"] == 2


def test_a_bare_number_is_still_the_output_of_a_run_that_finished_well(tmp_path):
    p = findings(tmp_path, """
        import sys
        sys.stdin.read()
        print("working")
        sys.stdout.write("7")           # its last line, without an end
    """)
    e = Engine(p, say=lambda s: None)
    assert e.run_block(p.model.spec.blocks["researcher"], "test") == ["noted"]
    assert [x["data"]["amount"] for x in p.events.query(n=None, type="valve.opened")] == [7.0]
    (tmp_path / "research.py").write_text("import sys\nsys.stdin.read()\nprint(5)\nsys.exit(2)\n")
    assert e.run_block(p.model.spec.blocks["researcher"], "test") == [], "not from a run that failed"
    assert len(p.events.query(n=None, type="valve.opened")) == 1


def test_a_burst_of_ten_thousand_lines_from_a_program_that_never_reads_its_input(tmp_path):
    """No deadlock: it prints 10,000 event lines (and some for its log) without reading its input; all are recorded,
    in order, in a few writes, and the engine's own thread is not starved."""
    p = findings(tmp_path, """
        import json, sys
        out = []
        for i in range(10000):
            out.append(json.dumps({"event": "finding.found", "item": f"finding/{i % 50}", "data": {"n": i}}))
            if i % 1000 == 0:
                out.append(f"progress {i}")
        print("\\n".join(out))
    """)
    e = Engine(p, say=lambda s: None)
    ticks, stop = [], threading.Event()

    def other_work():                                   # what else the engine does meanwhile: it keeps its pace
        while not stop.is_set():
            t0 = time.monotonic()
            p.events.query(n=1, type="agent.started")
            ticks.append(time.monotonic() - t0)
            time.sleep(0.05)
    threading.Thread(target=other_work, daemon=True).start()
    t0 = time.monotonic()
    e.run_block(p.model.spec.blocks["researcher"], "test")
    took = time.monotonic() - t0
    stop.set()
    got = p.events.query(n=None, type="finding.found")
    assert len(got) == 10000 and [x["data"]["n"] for x in got] == list(range(10000))
    assert ended(p)[0]["data"]["events"] == 10000
    print(f"\n10,000 event lines streamed and recorded in {took:.2f}s ({10000 / took:,.0f} lines/s); "
          f"the slowest other read meanwhile {max(ticks) * 1000:.0f} ms")
    assert took < 30, took
    assert max(ticks) < 2.0, "the engine's other work was not starved"
    assert its.one(p.events, p.model.spec, "finding/49").fields["n"] == 9999


# ---- leases: a streamed event renews the lease, and a fenced run's lines are refused at once

LEASED = """
name: t
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        values: [ready, doing, done]
    events:
      ticket-started:
        when: type == 'ticket.started'
        '...': data
        state: set('doing')
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready}
    pool: 1
    run: {run}
    lease: {lease}
"""


def leased(tmp_path, script: str, lease: str) -> Project:
    (tmp_path / "work.py").write_text(textwrap.dedent(script))
    return project(tmp_path, LEASED.replace("{run}", json.dumps(f"{PY} work.py")).replace("{lease}", lease))


def test_printed_events_renew_the_lease_as_they_arrive(tmp_path):
    """A run with a TTL of 1s that prints a progress event every 0.4s for 2.4s keeps its lease past its TTL: no
    command, only its printed lines (which, read at the end, would have come too late)."""
    p = leased(tmp_path, """
        import json, os, sys, time
        sys.stdin.read()
        for i in range(6):
            print(json.dumps({"event": "ticket.progress", "data": {"step": i}}), flush=True)
            time.sleep(0.4)
        print(json.dumps({"event": "ticket.done"}), flush=True)
    """, "{ttl: 1s, attempts: 1}")
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        assert wait_for(lambda: its.one(p.events, p.model.spec, "ticket/1").state == "done", 15)
        renewed = [its.one(p.events, p.model.spec, "ticket/1").fields["lease"]]
        assert wait_for(lambda: its.one(p.events, p.model.spec, "ticket/1").fields["lease"]["holder"] is None, 5)
    finally:
        e.close()
    lease = its.one(p.events, p.model.spec, "ticket/1").fields["lease"]
    assert [h["how"] for h in lease["history"]] == ["ack"], "never expired"
    assert lease["history"][0]["ended"] - lease["history"][0]["taken"] > 2.0, "held well past its TTL"
    assert renewed[0]["renewed"] - lease["history"][0]["taken"] > 1.5, "renewed by the lines as they came"
    assert not p.events.query(n=None, type=EXPIRED)


def test_a_fenced_runs_later_lines_are_refused_at_once(tmp_path, monkeypatch):
    """Its lease expires while it is silent; the line it prints after is refused when it prints it, before the run
    ends, and changes nothing; what it printed while it held the lease stands. (An expired run is killed: this one
    ignores SIGTERM, and the grace before SIGKILL outlasts it, so it prints its late line while being stopped.)"""
    from ergostat.leases import kill
    monkeypatch.setattr(kill, "GRACE", 30.0)
    p = leased(tmp_path, """
        import json, signal, sys, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        sys.stdin.read()
        print(json.dumps({"event": "ticket.started", "data": {"by": "first"}}), flush=True)
        time.sleep(3)
        print(json.dumps({"event": "ticket.done", "data": {"late": True}}), flush=True)
        time.sleep(2)
    """, "{ttl: 1s, attempts: 1}")
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        refused = wait_for(lambda: p.events.query(n=None, type="agent.refused", item="worker"), 10)
        assert refused and "fencing" in refused[0]["data"]["why"]
        assert not p.events.query(n=None, type="agent.ran,agent.failed", item="worker"), "refused before the run ended"
        assert wait_for(lambda: p.events.query(n=None, type="agent.ran,agent.failed", item="worker"), 8)
    finally:
        e.close()
    it = its.one(p.events, p.model.spec, "ticket/1")
    assert it.fields["by"] == "first" and "late" not in it.fields, "the line before stands; the late one changed nothing"
    assert it.state == "dead" and [h["how"] for h in it.fields["lease"]["history"]] == ["expired"]
    assert not p.events.query(n=None, type="ticket.done")


def test_a_burst_about_its_leased_item_is_fenced_cheaply(tmp_path):
    """10,000 progress events about the item a run holds, printed as fast as it can: each looked at for fencing, the
    item folded again only when its lease changed, so the burst stays fast."""
    p = leased(tmp_path, """
        import json, sys
        sys.stdin.read()
        for i in range(10000):
            print(json.dumps({"event": "ticket.progress", "data": {"step": i}}))
            if i % 2000 == 0:
                sys.stdout.flush()
        print(json.dumps({"event": "ticket.done"}))
    """, "{ttl: 1m, attempts: 1}")
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = Engine(p, say=lambda s: None)
    t0 = time.monotonic()
    e.start_all()
    try:
        assert wait_for(lambda: p.events.query(n=None, type="agent.ran,agent.failed", item="worker"), 60)
        took = time.monotonic() - t0
    finally:
        e.close()
    it = its.one(p.events, p.model.spec, "ticket/1")
    assert it.state == "done" and it.fields["step"] == 9999
    assert len(p.events.query(n=None, type="ticket.progress")) == 10000
    assert not p.events.query(n=None, type="agent.refused")
    print(f"\n10,001 event lines about a leased item, from the item's arrival to the run's end, in {took:.2f}s")
    assert took < 30, took


def test_a_run_stopped_after_its_lines_moved_its_item_on_is_an_ack(tmp_path):
    """Its event moved the item on while it ran; ergostat stops before the run ends: the work stands (ack), the item is
    not given back."""
    p = leased(tmp_path, """
        import json, sys, time
        sys.stdin.read()
        print(json.dumps({"event": "ticket.done"}), flush=True)
        time.sleep(30)
    """, "{ttl: 1m, attempts: 2}")
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        assert wait_for(lambda: its.one(p.events, p.model.spec, "ticket/1").state == "done", 10)
    finally:
        e.close()
    assert wait_for(lambda: its.one(p.events, p.model.spec, "ticket/1").fields["lease"]["holder"] is None, 5)
    it = its.one(p.events, p.model.spec, "ticket/1")
    assert it.state == "done" and [h["how"] for h in it.fields["lease"]["history"]] == ["ack"]
