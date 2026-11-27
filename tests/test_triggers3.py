"""Blocks started by events, the follow-up (SPEC §9.3): a run's block is read from its own record, never from what it
says of itself; the depth budget is per line of causes; a run never answers for its own block."""

import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.spec import triggers as tr
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: t
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [open, done]
    events:
      ticket-reopened:
        when: type == 'ticket.reopened'
        '...': data
        state: set('open')
      ticket-closed:
        when: type == 'ticket.closed'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
blocks:
  triage:
    type: program
    on: {event: ticket.opened, emits: [note.added]}
    run: sh run.sh
    out: flow.f
  other:
    type: program
    on: {event: other.go, emits: [ticket.opened, note.added]}
    run: "true"
    out: flow.g
stocks:
  s: {}
flows:
  f: {to: s}
  g: {to: s}
"""


def wait_for(cond, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


@pytest.fixture
def engine(tmp_path):
    made = []

    def go(text, script=""):
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
        (tmp_path / "run.sh").write_text(script)
        p = Project(mdl.load(tmp_path))
        e = Engine(p, say=lambda s: None)
        e.start_all()
        made.append(e)
        time.sleep(0.3)
        return p, e
    yield go
    for e in made:
        e.close()


def ran(p, block):
    return p.events.query(n=None, item=block, type="agent.ran")


def test_a_run_cannot_claim_another_blocks_emits(tmp_path, engine):
    """triage may not say ticket.opened; naming itself as another block (ERGOSTAT_BLOCK=other, which may) changes
    nothing, through the engine's socket or without it: its block is read from its run's own record."""
    script = ("ERGOSTAT_BLOCK=other $ERGOSTAT_CMD event --add ticket.opened --item ticket/b || echo refused-socket >> out\n"
              "ERGOSTAT_BLOCK=other ERGOSTAT_NO_SOCKET=1 $ERGOSTAT_CMD event --add ticket.opened --item ticket/c"
              " || echo refused-direct >> out\n"
              "ERGOSTAT_BLOCK=other $ERGOSTAT_CMD event --add note.added --item note/a\n")
    p, e = engine(MODEL, script)
    p.events.add("ticket.opened", item="ticket/1", source="hook")
    assert wait_for(lambda: ran(p, "triage"))
    assert (tmp_path / "out").read_text().split() == ["refused-socket", "refused-direct"]
    assert not p.events.query(n=None, item="ticket/b") and not p.events.query(n=None, item="ticket/c")
    assert p.events.query(n=None, item="note/a"), "what it does emit is recorded"
    run = p.events.query(n=None, item="triage", type="agent.started")[0]["id"]
    from ergostat.calls import ops
    with pytest.raises(ops.Refused, match="not among what triage emits"):
        ops.event(e, {"events": [{"event": "ticket.opened", "item": "ticket/d"}], "causedby": run, "block": "other"})
    assert tr.block_of(p.events, run) == "triage" and tr.block_of(p.events, run[:8]) is None, "its exact id only"


FANNED = """
name: fanned
projections:
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        type: one of [open, done]
    events:
      ticket-reopened:
        when: type == 'ticket.reopened'
        '...': data
        state: set('open')
      ticket-closed:
        when: type == 'ticket.closed'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
blocks:
  poke:
    type: program
    on: {event: ticket.poked, emits: [ticket.reopened]}
    run: python3 poke.py
    out: flow.f
  relay:
    type: program
    takes: {projection: ticket, at: open}
    run: python3 relay.py
    out: flow.r
stocks:
  s: {}
flows:
  f: {to: s}
  r: {to: s}
"""


def test_each_line_of_causes_has_its_own_budget(tmp_path, engine):
    """Two events, two lines of causes (each its own ticket, relayed back by a block that takes it): each line runs 8
    triggered runs in a row and is stopped once, so the block runs twice 8 times, no run deeper than 8."""
    (tmp_path / "poke.py").write_text("import json, sys\ne = json.load(sys.stdin)['event']\n"
                                      "print(json.dumps({'event': 'ticket.reopened', 'item': e['data']['t']}), flush=True)\n")
    (tmp_path / "relay.py").write_text("import json, os\nit = os.environ['ERGOSTAT_ITEM']\n"
                                       "print(json.dumps({'event': 'ticket.closed', 'item': it}), flush=True)\n"
                                       "print(json.dumps({'event': 'ticket.poked', 'data': {'t': it}}), flush=True)\n")
    p, _ = engine(FANNED)
    for t in ("ticket/1", "ticket/2"):
        p.events.add("ticket.poked", source="hook", data={"t": t})
    assert wait_for(lambda: len(p.events.query(n=None, type="trigger.stopped")) == 2, 60.0)
    time.sleep(1.0)
    depths = sorted(s["data"]["depth"] for s in p.events.query(n=None, item="poke", type="agent.started"))
    assert depths == sorted(list(range(1, tr.DEPTH + 1)) * 2), "8 in a row on each line, no more"
    assert all(s["data"]["depth"] == tr.DEPTH for s in p.events.query(n=None, type="trigger.stopped"))


def test_a_run_never_answers_for_its_own_block(tmp_path, engine):
    """From inside a run of triage: block triage --reset and --approve are refused (its block read from its run's
    record); the owner, outside any run, resets it."""
    script = ("$ERGOSTAT_CMD block triage --reset 2>> err || echo refused-reset >> out\n"
              "$ERGOSTAT_CMD block triage --approve 2>> err || echo refused-approve >> out\n"
              "ERGOSTAT_BLOCK=other $ERGOSTAT_CMD block triage --reset 2>> err || echo refused-named >> out\n")
    p, _ = engine(MODEL.replace("    run: sh run.sh", "    mode: advise\n    run: sh run.sh"), script)
    p.events.add("ticket.opened", item="ticket/1", source="hook")
    asked = wait_for(lambda: p.events.query(n=None, item="triage", type="block.advised"))
    p.events.add("block.approved", item="triage", source="person", data={"ask": asked[0]["seq"]})
    assert wait_for(lambda: ran(p, "triage"))
    assert (tmp_path / "out").read_text().split() == ["refused-reset", "refused-approve", "refused-named"]
    assert (tmp_path / "err").read_text().count("answers for it to no one") == 3
    assert not p.events.query(n=None, type="trigger.reset")
    assert len(p.events.query(n=None, item="triage", type="block.approved")) == 1
    got = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "block", "triage", "--reset"],
                         capture_output=True, text=True, env={k: v for k, v in __import__("os").environ.items()
                                                              if k != "ERGOSTAT_RUN"})
    assert got.returncode == 0 and p.events.query(n=None, type="trigger.reset"), got.stderr
