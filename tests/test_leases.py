"""Leases on items (SPEC §9.5): a block that takes items runs once per item, each run holding a lease that its own
events renew, that ends on ack or nack, or expires when it is silent past its TTL; after its attempts an item is a
dead letter; a run whose lease ended is refused (fencing); the fold is the truth, across a restart."""

import json
import os
import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import runner as old
from ergostat.leases import ENDED, EXPIRED, REDRIVEN, RENEWED, TAKEN, gone
from ergostat.leases.terms import terms
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

KIND = """
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
"""


def project(tmp_path, text: str) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return Project(mdl.load(tmp_path))


def item(p, id):
    return its.one(p.events, p.model.spec, id)


def wait_for(cond, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.05)
    return cond()


def start(p) -> Engine:
    e = Engine(p, say=lambda s: None)
    e.start_all()
    return e


# ---- the fold: leases are folded like everything else


def take(p, id, run, fence, ttl=60.0, max_=3, at=None):
    return p.events.add(TAKEN, item=id, source="ergostat", at=at,
                        data={"run": run, "block": "w", "fence": fence, "ttl": ttl, "max": max_, "back": "ready"})


def test_a_lease_folds_onto_its_item(tmp_path):
    p = project(tmp_path, KIND)
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"title": "one"})
    take(p, "ticket/1", "r1", 1, ttl=60, at=time.time())
    it = item(p, "ticket/1")
    lease = it.fields["lease"]
    assert it.state == "leased"
    assert lease["holder"] == "r1" and lease["fence"] == 1 and lease["attempts"] == 0
    assert lease["expires"] == pytest.approx(lease["taken"] + 60)
    assert [h["run"] for h in lease["history"]] == ["r1"]
    # one lease at a time: a second taken is refused, and so is a fence that is not the next one
    take(p, "ticket/1", "r2", 2)
    it = item(p, "ticket/1")
    assert it.fields["lease"]["holder"] == "r1" and "already leased" in it.refused[-1]["why"]


def test_renewed_by_any_event_its_holder_causes(tmp_path):
    p = project(tmp_path, KIND)
    t0 = time.time() - 100
    p.events.add("ticket.opened", item="ticket/1", source="t", at=t0)
    take(p, "ticket/1", "r1", 1, ttl=30, at=t0)
    p.events.add("ticket.note", item="ticket/1", source="someone", data={"x": 1}, at=t0 + 20)   # not the holder's
    assert item(p, "ticket/1").fields["lease"]["expires"] == pytest.approx(t0 + 30)
    p.events.add("ticket.started", item="ticket/1", source="w", causedby="r1", at=t0 + 25)
    it = item(p, "ticket/1")
    assert it.state == "doing", "the work moves it on while it holds the lease"
    assert it.fields["lease"]["holder"] == "r1" and it.fields["lease"]["expires"] == pytest.approx(t0 + 55)
    p.events.add(RENEWED, item="ticket/1", source="ergostat", data={"run": "r1", "fence": 1}, at=t0 + 50)
    assert item(p, "ticket/1").fields["lease"]["expires"] == pytest.approx(t0 + 80)
    p.events.add("claude.message", item="ticket/1", source="w", data={"messages": []}, at=t0 + 70)   # its transcript
    assert item(p, "ticket/1").fields["lease"]["expires"] == pytest.approx(t0 + 100)


def test_ack_nack_expiry_and_the_dead_letter(tmp_path):
    p = project(tmp_path, KIND)
    p.events.add("ticket.opened", item="ticket/1", source="t")
    take(p, "ticket/1", "r1", 1, max_=3)
    p.events.add(EXPIRED, item="ticket/1", source="ergostat", data={"run": "r1", "fence": 1, "silent": 61})
    it = item(p, "ticket/1")
    assert it.state == "ready" and it.fields["lease"]["attempts"] == 1 and it.fields["lease"]["holder"] is None
    take(p, "ticket/1", "r2", 2, max_=3)
    p.events.add(ENDED, item="ticket/1", source="ergostat", data={"run": "r2", "fence": 2, "how": "nack", "why": "flaky",
                                                                  "after": 30, "count": False})
    it = item(p, "ticket/1")
    assert it.state == "ready" and it.fields["lease"]["attempts"] == 1, "a nack that does not count"
    assert it.fields["lease"]["not_before"] > time.time() + 20
    take(p, "ticket/1", "r3", 3, max_=3)
    p.events.add(ENDED, item="ticket/1", source="ergostat", data={"run": "r3", "fence": 3, "how": "nack", "why": "no"})
    take(p, "ticket/1", "r4", 4, max_=3)
    p.events.add(EXPIRED, item="ticket/1", source="ergostat", data={"run": "r4", "fence": 4, "silent": 70})
    it = item(p, "ticket/1")
    lease = it.fields["lease"]
    assert it.state == "dead" and lease["attempts"] == 3 and lease["dead"]
    assert [(h["run"], h["how"], h["counted"]) for h in lease["history"]] == [
        ("r1", "expired", True), ("r2", "nack", False), ("r3", "nack", True), ("r4", "expired", True)], "each attempt's evidence"
    assert lease["history"][-1]["silent"] == 70 and lease["history"][1]["why"] == "flaky"
    take(p, "ticket/1", "r5", 5)
    assert item(p, "ticket/1").state == "dead", "a dead letter is not taken"
    p.events.add(REDRIVEN, item="ticket/1", source="owner", data={"why": "fixed the flake"})
    it = item(p, "ticket/1")
    assert it.state == "ready" and it.fields["lease"]["attempts"] == 0
    take(p, "ticket/1", "r5", 5)
    p.events.add("ticket.done", item="ticket/1", source="w", causedby="r5")
    p.events.add(ENDED, item="ticket/1", source="ergostat", data={"run": "r5", "fence": 5, "how": "ack"})
    it = item(p, "ticket/1")
    assert it.state == "done" and it.fields["lease"]["holder"] is None and it.fields["lease"]["attempts"] == 0


def test_a_late_runs_output_is_refused_by_fencing(tmp_path):
    p = project(tmp_path, KIND)
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"title": "one"})
    take(p, "ticket/1", "r1", 1)
    p.events.add(EXPIRED, item="ticket/1", source="ergostat", data={"run": "r1", "fence": 1})
    take(p, "ticket/1", "r2", 2)
    late = p.events.add("ticket.done", item="ticket/1", source="w", causedby="r1", data={"title": "late"})
    it = item(p, "ticket/1")
    assert it.state == "leased" and it.fields["title"] == "one", "refused, not applied"
    assert it.refused[-1]["event"] == late["id"] and "fencing" in it.refused[-1]["why"]
    assert p.events.get(late["id"]), "recorded as it was said"
    p.events.add(ENDED, item="ticket/1", source="ergostat", data={"run": "r1", "fence": 1, "how": "ack"})
    assert item(p, "ticket/1").fields["lease"]["holder"] == "r2", "an old lease cannot be ended"
    p.events.add("ticket.done", item="ticket/1", source="w", causedby="r2")
    assert item(p, "ticket/1").state == "done"


def test_a_set_never_takes_the_lease_away(tmp_path):
    p = project(tmp_path, KIND)
    p.events.add("ticket.opened", item="ticket/1", source="t")
    take(p, "ticket/1", "r1", 1)
    p.events.add("ticket.rewritten", item="ticket/1", source="t", set={"title": "new"})
    p.events.add("ticket.noted", item="ticket/1", source="t", data={"lease": "mine"})
    it = item(p, "ticket/1")
    assert it.fields["title"] == "new" and it.fields["lease"]["holder"] == "r1"


# ---- the terms: per tier, kind and block


def test_lease_terms_by_tier_kind_and_block(tmp_path):
    p = project(tmp_path, KIND + """
    lease: {attempts: 5}
leases:
  program: {ttl: 2m}
agents:
  claude:
    kind: ai
blocks:
  dev:
    type: ai
    prompt: do it
    takes: {projection: ticket, at: ready}
  bot:
    type: program
    run: "true"
    takes: {projection: ticket, at: ready}
  dev2:
    type: program
    agent: claude
    run: "true"
    takes: {projection: ticket, at: ready}
    lease: {ttl: 90s}
  person-ish:
    type: ai
    prompt: do it
    takes: {projection: ticket, at: doing}
    lease: {ttl: 3h, attempts: 1}
""")
    s = p.model.spec
    assert s.items["ticket"].states == ["ready", "leased", "doing", "done", "dead"], "a kind taken gains the lease's states"
    dev, bot, dev2, slow = (terms(s, s.blocks[n]) for n in ("dev", "bot", "dev2", "person-ish"))
    assert dev["tier"] == "ai" and dev["ttl"] == 40 * 60 and dev["attempts"] == 5 and dev["from"] == {"ttl": "default", "attempts": "projection"}
    assert bot["tier"] == "program" and bot["ttl"] == 120 and bot["from"]["ttl"] == "leases"
    assert dev2["tier"] == "ai" and dev2["ttl"] == 90, "its agent's kind is its tier; the block's own TTL first"
    assert slow["ttl"] == 3 * 3600 and slow["attempts"] == 1


def test_takes_is_checked(tmp_path):
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(KIND + """
leases:
  robot: {ttl: 1m}
blocks:
  a:
    type: program
    run: "true"
    takes: {projection: tickets, at: ready}
  b:
    type: program
    run: "true"
    takes: {projection: ticket, at: nowhere}
    every: 5s
  c:
    type: program
    run: "true"
    pool: 3
"""))
    _, problems = read(tmp_path / "ergostat.yaml")
    said = "\n".join(x.message for x in problems if x.level == "error")
    assert "'tickets' is not a projection" in said
    assert "'nowhere' is not a state of ticket" in said
    assert "started by them" in said
    assert "only a block that takes items runs more than once" in said
    assert "leases.robot: a tier of the ladder" in said


def read_model(tmp_path, text: str):
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    return read(tmp_path / "ergostat.yaml")


def test_mode_advise_on_a_block_that_takes_is_refused(tmp_path):
    """advise asks before a command or an event, never per item: with takes: it is refused, before the kind is checked
    (a mistyped kind would otherwise drop takes: and hide it)."""
    spec, problems = read_model(tmp_path, KIND + """
blocks:
  bot:
    type: program
    run: "true"
    takes: {projection: ticket, at: ready}
    mode: advise
  dev:
    type: ai
    prompt: do it
    takes: {projection: ticket, at: ready}
    mode: advise
  typo:
    type: program
    run: "true"
    takes: {projection: tickets, at: ready}
    mode: advise
""")
    for name in ("bot", "dev", "typo"):
        got = [x for x in problems if x.code == "advise-with-takes" and f"block {name}." in x.message]
        assert len(got) == 1, (name, [str(x) for x in problems])
        assert got[0].level == "error" and got[0].where == spec.blocks[name].where
        assert "in: block." in got[0].message and "manual: true" in got[0].message, "it says to gate it instead"
    assert len([x for x in problems if x.code == "advise-with-takes"]) == 3
    assert [x for x in problems if x.code == "unknown-ref" and "block typo." in x.message], "its own error as well"


def test_mode_advise_without_takes_and_takes_without_advise_compile(tmp_path):
    from .test_triggers2 import MODEL as EVENTS
    takers = KIND + """
blocks:
  plain:
    type: program
    run: "true"
    takes: {projection: ticket, at: ready}
  auto:
    type: ai
    prompt: do it
    takes: {projection: ticket, at: ready}
    mode: auto
  c:
    type: expr
    in: {n: parameter.n}
    expr: n
  asked:
    type: program
    run: "true"
    mode: advise
    in: block.c
parameters:
  n: {value: 1}
"""
    advised = EVENTS.replace("    run: python3 triage.py", "    mode: advise\n    run: python3 triage.py")
    assert "mode: advise" in advised
    for i, text in enumerate((takers, advised)):
        d = tmp_path / str(i)
        d.mkdir()
        spec, problems = read_model(d, text)
        assert not [str(x) for x in problems if x.code == "advise-with-takes"]
        assert spec.blocks["triage" if i else "asked"].mode == "advise", "what it would refuse is in the model"


def test_a_block_that_takes_waits_while_what_commands_it_is_off(tmp_path):
    """The gate the refusal points to: in: block.X from a block that is off, and its items wait (dispatch.py)."""
    text = model('echo "{\\"event\\": \\"ticket.done\\"}"', extra="""
  gate:
    type: expr
    in: {w: stock.waiting}
    expr: "w >= 3"
stocks:
  waiting:
    sensor: {projection: ticket, state: ready, every: 0.2s}
""").replace("    lease: {ttl: 1m}\n", "    lease: {ttl: 1m}\n    in: block.gate\n")
    p = project(tmp_path, text)
    opened(p, 2)
    e = start(p)
    try:
        time.sleep(2)
        assert all(item(p, f"ticket/{i}").state == "ready" for i in range(2)), "off: its items wait"
        for i in range(2, 4):
            p.events.add("ticket.opened", item=f"ticket/{i}", source="t")
        assert wait_for(lambda: any(item(p, f"ticket/{i}").state == "done" for i in range(4)), 10), "on: it takes"
    finally:
        e.close()


GATE = """
  gate:
    type: expr
    in: {o: stock.open}
    expr: o
stocks:
  open:
    unit: switch
    sensor: {manual: true}
"""


def gated(run: str, by: str, extra: str) -> str:
    return model(run, extra=extra).replace("    lease: {ttl: 1m}\n", f"    lease: {{ttl: 1m}}\n    in: block.{by}\n")


def test_the_documented_gate_opens_for_items(tmp_path):
    """The form the advise-with-takes error and SPEC §9.5 name: an expr block reading a manual sensor, which a person
    reads as 1 (`ergostat sensor open --read 1`) to let every item through at once, not one by one."""
    from ergostat.cli.spec_cmds import read_manual
    (tmp_path / "advised").mkdir()
    _, problems = read_model(tmp_path / "advised", KIND + """
blocks:
  bot: {type: program, run: "true", takes: {projection: ticket, at: ready}, mode: advise}
""")
    said = next(x.message for x in problems if x.code == "advise-with-takes")
    assert "expr block reading a sensor: {manual: true}" in said and "--read 1" in said and "not per item" in said
    text = gated('echo "{\\"event\\": \\"ticket.done\\"}"', "gate", GATE)
    _, problems = read_model(tmp_path, text)
    assert not [str(x) for x in problems if x.level == "error"], "the documented form compiles"
    p = project(tmp_path, text)
    opened(p, 3)
    e = start(p)
    try:
        time.sleep(2)
        assert all(item(p, f"ticket/{i}").state == "ready" for i in range(3)), "no reading yet: its items wait"
        assert read_manual(p, "open", 1) == 0
        assert wait_for(lambda: all(item(p, f"ticket/{i}").state == "done" for i in range(3)), 10), "open: all of them"
    finally:
        e.close()


PERSON = """
  ok:
    type: person
    ask: let them through
"""


def test_check_refuses_a_person_block_as_a_gate(tmp_path):
    """A person's --done records work and never sets a command: a person block gating a block that takes would leave
    its items waiting forever, so check refuses it, whichever end the wire is written on."""
    for i, text in enumerate((gated('"true"', "ok", PERSON), model('"true"', extra=PERSON + "    out: block.worker\n"))):
        d = tmp_path / str(i)
        d.mkdir()
        _, problems = read_model(d, text)
        got = [x for x in problems if x.code == "person-gate"]
        assert len(got) == 1 and got[0].level == "error" and "block worker" in got[0].message, [str(x) for x in problems]
        assert "manual: true" in got[0].message, "it names the form that works"
    _, problems = read_model(tmp_path, gated('"true"', "gate", GATE))
    assert not [str(x) for x in problems if x.level == "error"], "an expr gate is not refused"


# ---- the engine: dispatch, the watchdog, fencing


WORKER = KIND + """
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready}
    pool: 2
    run: {run}
    lease: {lease}
"""


def model(run: str, lease: str = "{ttl: 1m}", extra: str = "") -> str:
    return WORKER.replace("{run}", json.dumps(run)).replace("{lease}", lease) + extra


def opened(p, n: int, at: float | None = None):
    for i in range(n):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data={"title": f"t{i}"}, at=at)


def test_one_run_per_item_bounded_by_the_pool(tmp_path):
    run = ('echo "$ERGOSTAT_ITEM $ERGOSTAT_LEASE $(date +%s.%N)" >> runs.log; sleep 0.8; '
           'echo "{\\"event\\": \\"ticket.done\\"}"; echo "$ERGOSTAT_ITEM done $(date +%s.%N)" >> runs.log')
    p = project(tmp_path, model(run))
    opened(p, 5)
    e = start(p)
    try:
        assert wait_for(lambda: all(item(p, f"ticket/{i}").state == "done" for i in range(5)), 15)
    finally:
        e.close()
    lines = (tmp_path / "runs.log").read_text().splitlines()
    starts = [x.split() for x in lines if " done " not in x]
    assert sorted(s[0] for s in starts) == [f"ticket/{i}" for i in range(5)], "one run per item, each once"
    assert all(s[1] == "1" for s in starts), "each run given its item and its lease (ERGOSTAT_ITEM, ERGOSTAT_LEASE)"
    going, most = 0, 0                                   # never more than the pool at once
    for x in lines:
        going += -1 if " done " in x else 1
        most = max(most, going)
    assert most == 2
    for i in range(5):
        lease = item(p, f"ticket/{i}").fields["lease"]
        assert lease["holder"] is None and lease["history"][-1]["how"] == "ack"
    runs = p.events.query(n=None, type="agent.started", item="worker")
    assert {r["data"]["item"] for r in runs} == {f"ticket/{i}" for i in range(5)}
    taken = p.events.query(n=None, type=TAKEN)
    assert {r["id"] for r in taken} == {r["causedby"] for r in runs}, "each run caused by its lease"
    assert {t["data"]["run"] for t in taken} == {r["id"] for r in runs}, "the lease names its holder, the run"
    for e in p.events.query(n=None, type=ENDED):          # the hook: what each end leaves the item as
        assert e["data"]["item"] == e["item"] and e["data"]["state"] == "done" and e["data"]["terminal"] is True
    assert all(t["data"]["item"] == t["item"] for t in taken)


def test_a_run_starts_on_the_item_event(tmp_path):
    p = project(tmp_path, model('echo "{\\"event\\": \\"ticket.done\\"}"'))
    e = start(p)
    try:
        time.sleep(0.5)
        ev = p.events.add("ticket.opened", item="ticket/9", source="t")
        t0 = time.time()
        got = wait_for(lambda: p.events.query(n=None, type=TAKEN, item="ticket/9"), 5)
        assert got and got[0]["time"] - t0 < 0.9, "leased as soon as it arrived, not on a slow clock"
        assert got[0]["causedby"] == ev["id"], "caused by the event that brought it to ready"
        assert wait_for(lambda: item(p, "ticket/9").state == "done", 5)
    finally:
        e.close()


def test_a_run_given_its_item_and_its_lines_about_it(tmp_path):
    run = ('cat > input.json; echo "{\\"event\\": \\"ticket.started\\", \\"data\\": {\\"by\\": \\"$ERGOSTAT_RUN\\"}}"; '
           'echo "{\\"event\\": \\"ticket.done\\"}"')
    p = project(tmp_path, model(run))
    p.events.add("ticket.opened", item="ticket/1", source="t", data={"title": "the one"})
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 8)
    finally:
        e.close()
    given = json.loads((tmp_path / "input.json").read_text())
    assert given["item"]["id"] == "ticket/1" and given["item"]["fields"]["title"] == "the one" and given["trigger"] == "item"
    assert given["lease"]["fence"] == 1 and given["lease"]["ttl"] == 60 and given["lease"]["tier"] == "program"
    it = item(p, "ticket/1")
    assert it.fields["by"] == it.fields["lease"]["history"][0]["run"]


def test_a_run_that_does_not_move_it_gives_it_back_and_a_dead_letter_after_its_attempts(tmp_path):
    p = project(tmp_path, model("exit 3", "{ttl: 1m, attempts: 2}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "dead", 10)
    finally:
        e.close()
    lease = item(p, "ticket/1").fields["lease"]
    assert [h["how"] for h in lease["history"]] == ["nack", "nack"] and all(h["exit"] == 3 for h in lease["history"])
    assert lease["history"][0]["why"] == "exited 3"
    ends = p.events.query(n=None, type=ENDED, item="ticket/1")
    assert [(e["data"]["state"], e["data"]["terminal"]) for e in ends] == [("ready", False), ("dead", True)]
    assert len(p.events.query(n=None, type="agent.started", item="worker")) == 2, "nothing taken once dead"


def test_a_nack_line_puts_it_off(tmp_path):
    p = project(tmp_path, model('echo "{\\"nack\\": {\\"why\\": \\"can wait\\", \\"after\\": \\"1h\\", \\"count\\": false}}"'))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: (item(p, "ticket/1").fields.get("lease") or {}).get("not_before"), 8)
        time.sleep(1.5)
    finally:
        e.close()
    it = item(p, "ticket/1")
    assert it.state == "ready" and it.fields["lease"]["attempts"] == 0 and it.fields["lease"]["history"][0]["why"] == "can wait"
    assert len(p.events.query(n=None, type=TAKEN)) == 1, "not taken again before its time"


def test_renewed_by_events_and_expired_when_silent_then_retried(tmp_path):
    """A run that writes about its item keeps its lease past its TTL; one that goes silent loses it: the item goes back
    to ready, its attempt counted, and is taken again. The silent run is killed (test_lease_kill.py): it says nothing late."""
    run = ('if [ ! -f first ]; then touch first; sleep 3; echo "{\\"event\\": \\"ticket.done\\"}"; exit 0; fi; '   # silent
           'for i in 1 2 3 4; do $ERGOSTAT_CMD event --add ticket.progress --item $ERGOSTAT_ITEM --data "{\\"step\\": $i}"; '
           'sleep 0.4; done; echo "{\\"event\\": \\"ticket.done\\", \\"data\\": {\\"by\\": \\"second\\"}}"')
    p = project(tmp_path, model(run, "{ttl: 1s, attempts: 3}").replace("pool: 2", "pool: 1"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 15)
    finally:
        e.close()
    it = item(p, "ticket/1")
    lease = it.fields["lease"]
    assert [h["how"] for h in lease["history"]] == ["expired", "ack"]
    assert lease["history"][1]["taken"] - lease["history"][0]["taken"] >= 1.0
    assert lease["history"][1]["ended"] - lease["history"][1]["taken"] > 1.2, "kept past its TTL by its own events"
    assert it.fields["by"] == "second"
    assert p.events.query(n=None, type="ergostat.run.killed"), "the silent run killed, not left to finish late"
    assert not p.events.query(n=None, type="agent.refused", item="worker"), "so it never said its late line"
    expired = p.events.query(n=None, type=EXPIRED)[0]["data"]
    assert expired["silent"] >= 1.0 and expired["item"] == "ticket/1" and expired["state"] == "ready" and not expired["terminal"]


def test_the_watchdog_renews_from_what_the_holder_does_elsewhere(tmp_path):
    """A run working in a session of its own (another item) keeps its lease on its item."""
    run = ('for i in 1 2 3 4 5; do $ERGOSTAT_CMD event --add session.said --item session/$ERGOSTAT_LEASE '
           '--data "{\\"n\\": $i}"; sleep 0.4; done; echo "{\\"event\\": \\"ticket.done\\"}"')
    p = project(tmp_path, model(run, "{ttl: 1s}"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 15)
    finally:
        e.close()
    lease = item(p, "ticket/1").fields["lease"]
    assert [h["how"] for h in lease["history"]] == ["ack"]
    assert p.events.query(n=None, type=RENEWED, item="ticket/1"), "renewed by the watchdog, from the session's events"


def test_a_goal_gates_what_a_block_takes(tmp_path):
    text = model('sleep 0.6; echo "{\\"event\\": \\"ticket.done\\"}"', extra="""
stocks:
  waiting:
    sensor: {projection: ticket, state: ready, every: 0.2s}
flows:
  done:
    from: waiting
goals:
  short:
    stock: waiting
    hold: "<= 2"
""").replace("    lease: {ttl: 1m}\n", "    lease: {ttl: 1m}\n    goal: short\n    out: flow.done\n").replace("pool: 2", "pool: 1")
    p = project(tmp_path, text)
    opened(p, 5)
    e = start(p)
    try:
        assert wait_for(lambda: sum(1 for i in range(5) if item(p, f"ticket/{i}").state == "done") >= 3, 10)
        time.sleep(2)
    finally:
        e.close()
    done = sum(1 for i in range(5) if item(p, f"ticket/{i}").state == "done")
    assert 3 <= done <= 4, "it takes while its goal is off, and stops once it holds"


def test_leases_survive_a_restart_the_fold_is_the_truth(tmp_path):
    p = project(tmp_path, model('sleep 30', "{ttl: 1.5s, attempts: 2}").replace("pool: 2", "pool: 1"))
    p.events.add("ticket.opened", item="ticket/1", source="t")
    p.events.add("ticket.opened", item="ticket/2", source="t")
    first = Engine(p, say=lambda s: None)
    first.start_all()
    assert wait_for(lambda: item(p, "ticket/1").state == "leased", 5)
    first.dispatch.finish = lambda *a, **k: None             # it dies: no lease is ended (nor given back: no close)
    first.stop.set()
    old.kill_all()
    gone.closed(first.dispatch)                              # (as its process ending would: its id no live engine's)
    held = item(p, "ticket/1").fields["lease"]
    second = start(Project(mdl.load(tmp_path)))
    try:                     # (no fixed sleep: what the record says, in its order, holds however late a look comes)
        assert wait_for(lambda: ends(p, "ticket/1"), 10), "ended: its run no longer exists (leases/gone.py)"
        assert wait_for(lambda: len(p.events.query(n=None, type=TAKEN)) >= 2, 5), "then the next is taken"
        expired = ends(p, "ticket/1")[0]
    finally:
        second.close()
        old.STOPPING.clear()
    ended = item(p, "ticket/1").fields["lease"]["history"][0]
    assert ended.get("run") == held["holder"] and ended.get("how") == "nack" and ended["counted"] is False, \
        "the new engine reads the lease, and ends it uncounted: its run was killed with the engine that held it"
    assert expired["data"]["run"] == held["holder"] and expired["data"]["count"] is False   # (its record left or not)
    assert "no longer exists" in expired["data"]["why"] or "process is gone" in expired["data"]["why"]
    # A take that ignored the lease held would come before its end in the record.
    taken = [ev["seq"] for ev in p.events.query(n=None, type=TAKEN) if ev["data"]["run"] != held["holder"]]
    assert taken and min(taken) > expired["seq"], "the pool is full: the lease held counts, till it ended"
    for i in (1, 2):                                         # stopped with ergostat: given back, not counted
        lease = item(p, f"ticket/{i}").fields["lease"]
        assert lease["holder"] is None
    assert any(h.get("why") == "stopped with ergostat" and h["counted"] is False
               for i in (1, 2) for h in item(p, f"ticket/{i}").fields["lease"]["history"])


# ---- the engine closing: no lease taken, and no run left, after its stop (SPEC §9.5)


def ends(p, id):
    return [x for x in p.events.query(n=None, type=ENDED) if x["item"] == id]


def stopped_at(p) -> int:
    return p.events.query(n=None, type="ergostat.stopped")[-1]["seq"]


def given_back_once(p, id):
    """The item's lease ended once, uncounted, stopped with ergostat, before the engine recorded its stop (by seq)."""
    got = ends(p, id)
    assert len(got) == 1, got
    assert got[0]["data"]["how"] == "nack" and got[0]["data"]["why"] == "stopped with ergostat"
    assert got[0]["data"]["count"] is False and got[0]["seq"] < stopped_at(p)
    lease = item(p, id).fields["lease"]
    assert lease["holder"] is None and lease["history"][-1]["counted"] is False


def alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def test_no_lease_is_taken_once_close_has_begun(tmp_path, monkeypatch):
    p = project(tmp_path, model("sleep 30"))
    opened(p, 1)
    e = Engine(p, say=lambda s: None)
    real = e.command_of
    monkeypatch.setattr(e, "command_of", lambda b: (e.close(), real(b))[1])   # (past the look's own stop check)
    try:
        e.dispatch.tick()
        assert not p.events.query(n=None, type=TAKEN), "nothing taken once close() set the stop"
        assert item(p, "ticket/0").state == "ready" and not e.running
    finally:
        old.kill_all()
        old.STOPPING.clear()


def test_a_take_racing_close_s_stop_is_given_back_before_it_is_recorded(tmp_path, monkeypatch):
    p = project(tmp_path, model("sleep 30"))
    opened(p, 1)
    e = Engine(p, say=lambda s: None)
    real = p.events.add

    def add(type, *a, **k):                                  # close()'s stop, inside the take's write
        if type == TAKEN:
            with e.lock:
                e.stop.set()
            old.kill_all()
        return real(type, *a, **k)
    monkeypatch.setattr(p.events, "add", add)
    try:
        e.dispatch.tick()
        e.close()
    finally:
        old.STOPPING.clear()
    assert len(p.events.query(n=None, type=TAKEN)) == 1
    given_back_once(p, "ticket/0")
    assert not p.events.query(n=None, type="agent.started"), "no run started"
    assert not e.running


def spawning(monkeypatch, then):
    """The spawn in ``run_block``, with ``then`` done just after each process starts; the processes started."""
    from ergostat.spec import engine as em
    procs, real = [], em.Measured

    def spawn(*a, **k):
        procs.append(real(*a, **k))
        then()
        return procs[-1]
    monkeypatch.setattr(em, "Measured", spawn)
    return procs


def test_a_run_spawned_after_kill_all_is_killed(tmp_path, monkeypatch):
    p = project(tmp_path, model("sleep 30"))
    opened(p, 1)
    e = Engine(p, say=lambda s: None)

    def stop():                                              # close()'s stop and kill_all, before it is in LIVE
        with e.lock:
            e.stop.set()
        old.kill_all()
    procs = spawning(monkeypatch, stop)
    e.start_all()
    try:
        assert wait_for(lambda: procs, 10)
        assert wait_for(lambda: not alive(procs[0].pid), 5), "its process group is killed, not left to run"
    finally:
        e.close()
        old.STOPPING.clear()
    given_back_once(p, "ticket/0")


def test_one_engine_closing_does_not_kill_another_engines_run(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    pa, pb = project(tmp_path / "a", KIND), project(tmp_path / "b", model("sleep 30"))
    a = start(pa)
    opened(pb, 1)
    procs = spawning(monkeypatch, a.close)                  # (STOPPING set by the first engine's kill_all)
    b = start(pb)
    try:
        assert wait_for(lambda: b.live, 10)
        assert old.STOPPING.is_set() and a.stop.is_set() and not b.stop.is_set()
        assert not wait_for(lambda: procs[0].poll() is not None, 1.0), "the other engine's run goes on"
        assert alive(procs[0].pid) and item(pb, "ticket/0").fields["lease"]["holder"]
    finally:
        b.close()
        old.STOPPING.clear()


def stuck(tmp_path):
    """An engine whose run ended but whose own end of the lease failed (so the lease stays held), and the calls made
    to its ``finish``."""
    p = project(tmp_path, model("true"))
    opened(p, 1)
    e = Engine(p, say=lambda s: None)
    real, calls = e.dispatch.finish, []

    def finish(*a):
        calls.append(a)
        if len(calls) == 1:
            raise OSError("the record was busy")
        return real(*a)
    e.dispatch.finish = finish
    e.start_all()
    assert wait_for(lambda: calls and not e.running, 10)
    assert item(p, "ticket/0").fields["lease"]["holder"] == calls[0][3]
    return p, e, calls


def test_close_gives_back_every_lease_still_going(tmp_path):
    p, e, _ = stuck(tmp_path)
    try:
        e.close()
    finally:
        old.STOPPING.clear()
    given_back_once(p, "ticket/0")


def test_a_runs_own_end_inside_close_s_give_back_ends_it_once(tmp_path):
    p, e, calls = stuck(tmp_path)
    real, late = e.dispatch.after, []

    def after(*a, **k):                                      # between the give-back's read and its write
        if not late:
            late.append(threading.Thread(target=e.dispatch.finish, args=(*calls[0][:4], {})))
            late[0].start()
            late[0].join(0.5)
        return real(*a, **k)
    e.dispatch.after = after
    try:
        e.close()
        late[0].join(5)
    finally:
        old.STOPPING.clear()
    given_back_once(p, "ticket/0")


def test_no_lease_is_taken_once_the_engine_is_stopping(tmp_path):
    p = project(tmp_path, model('sleep 30'))
    opened(p, 2)
    e = Engine(p, say=lambda s: None)
    ready = e.dispatch.ready

    def stopping_now(*a, **k):                     # the stop lands after the look began, before it takes
        got = ready(*a, **k)
        e.stop.set()
        return got
    e.dispatch.ready = stopping_now
    try:
        e.dispatch.tick()
    finally:
        e.close()
    assert not p.events.query(n=None, type=TAKEN), "nothing is taken once the engine is stopping"
    assert not p.events.query(n=None, type="agent.started") and not e.running
    assert all(item(p, f"ticket/{i}").state == "ready" for i in range(2))


def test_a_take_racing_the_stop_is_given_back_uncounted(tmp_path):
    p = project(tmp_path, model('sleep 30').replace("pool: 2", "pool: 1"))
    opened(p, 2)
    e = Engine(p, say=lambda s: None)
    add = p.events.add

    def racing(type_, *a, **k):                    # the stop lands between the take's look and its write
        if type_ == TAKEN:
            e.stop.set()
        return add(type_, *a, **k)
    p.events.add = racing
    try:
        e.dispatch.tick()
    finally:
        p.events.add = add
    assert p.events.query(n=None, type=TAKEN, item="ticket/0"), "the take was written: it raced the stop"
    it = item(p, "ticket/0")
    lease = it.fields["lease"]
    assert it.state == "ready" and lease["holder"] is None and lease["attempts"] == 0
    assert [(h["how"], h["why"], h["counted"]) for h in lease["history"]] == [("nack", "stopped with ergostat", False)]
    assert not p.events.query(n=None, type="agent.started"), "its run never started"
    assert not e.running and not e.dispatch.going_items()
    # a run still going when the engine has waited its last: its lease is given back as it exits, not counted
    e.stop.clear()
    e.dispatch._work = lambda *a, **k: None        # (a run that never ends)
    e.dispatch.tick()
    (going,) = e.dispatch.going_items()
    assert item(p, going).state == "leased"
    e.running.clear()                              # (not waited for: close's five seconds)
    e.close()
    lease = item(p, going).fields["lease"]
    assert lease["holder"] is None and lease["attempts"] == 0 and lease["history"][-1]["counted"] is False


def test_a_run_whose_process_starts_as_the_engine_stops_is_killed_and_given_back(tmp_path, monkeypatch):
    """The stop lands between a run's process starting and its joining LIVE (close's kill_all missed it): killed at once."""
    from ergostat.spec import engine as eng
    p = project(tmp_path, model('sleep 30'))
    opened(p, 1)
    e = Engine(p, say=lambda s: None)

    class StopsAsItStarts(eng.Measured):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            e.stop.set()
    monkeypatch.setattr(eng, "Measured", StopsAsItStarts)
    try:
        e.dispatch.tick()
        assert wait_for(lambda: item(p, "ticket/0").state == "ready", 8), "killed at once, not left to sleep 30s"
    finally:
        e.close()
    assert p.events.query(n=None, type="agent.started"), "its process started"
    (h,) = item(p, "ticket/0").fields["lease"]["history"]
    assert (h["how"], h["why"], h["counted"]) == ("nack", "stopped with ergostat", False)


def test_a_run_whose_thread_starts_after_the_stop_is_not_started(tmp_path):
    p = project(tmp_path, model('sleep 30'))
    opened(p, 1)
    e = Engine(p, say=lambda s: e.stop.set() if "took" in s else None)      # the stop lands after the take, before its run
    try:
        e.dispatch.tick()
        assert wait_for(lambda: item(p, "ticket/0").state == "ready", 8)
    finally:
        e.close()
    assert not p.events.query(n=None, type="agent.started"), "its run never started"
    (h,) = item(p, "ticket/0").fields["lease"]["history"]
    assert (h["how"], h["why"], h["counted"]) == ("nack", "stopped with ergostat", False)


def test_close_returns_when_its_locks_are_held_for_good(tmp_path):
    """A pass or a look wedged with the engine's or the dispatcher's lock held (the watchdog's case): close still stops
    and returns, at most its wait for each lock later, and nothing is taken after."""
    import threading
    p = project(tmp_path, model('sleep 30'))
    opened(p, 1)
    e = Engine(p, say=lambda s: None)
    e.lock_wait = 0.3
    held, done = threading.Event(), threading.Event()

    def wedged():
        with e.lock, e.dispatch.lock:
            held.set()
            done.wait(30)
    threading.Thread(target=wedged, daemon=True).start()
    assert held.wait(5)
    closing = threading.Thread(target=e.close, daemon=True)
    closing.start()
    closing.join(10)
    try:
        assert not closing.is_alive(), "close waited for good on a lock held by something wedged"
        assert e.stop.is_set() and p.events.query(n=None, type="ergostat.stopped")
    finally:
        done.set()
    e.dispatch.tick()                               # the wedge let go: what was waiting for the lock sees the stop
    assert not p.events.query(n=None, type=TAKEN)


def test_another_engines_run_survives_this_engines_close(tmp_path):
    """One engine's stop is its own: an engine closing (runner.STOPPING set, process-wide) kills no run another engine
    starts afterwards."""
    from ergostat import runner as old
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    b = project(tmp_path / "b", model('sleep 0.3; echo "{\\"event\\": \\"ticket.done\\"}"'))
    other = start(b)
    try:
        Engine(project(tmp_path / "a", model("true")), say=lambda s: None).close()
        assert old.STOPPING.is_set()
        opened(b, 1)
        assert wait_for(lambda: item(b, "ticket/0").state == "done", 10), "its run went to its end"
    finally:
        other.close()
        old.STOPPING.clear()
    assert [h["how"] for h in item(b, "ticket/0").fields["lease"]["history"]] == ["ack"]


# ---- measures, attention, the command line


TAKER = KIND + """
blocks:
  worker:
    type: program
    run: "true"
    takes: {projection: ticket, at: ready}
    pool: 3
"""


def test_measures_and_what_needs_attention(tmp_path):
    from ergostat import state
    from ergostat.leases import measures
    from ergostat.numbers.measures import measure
    p = project(tmp_path, TAKER)
    now = time.time()
    for i in range(4):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", at=now - 100)
    take(p, "ticket/0", "r0", 1, ttl=600, at=now - 50)                     # held
    take(p, "ticket/1", "r1", 1, ttl=10, at=now - 50)                      # held, past its expiry: overdue
    take(p, "ticket/2", "r2", 1, ttl=10, max_=1, at=now - 50)              # expired: a dead letter
    p.events.add(EXPIRED, item="ticket/2", source="ergostat", data={"run": "r2", "fence": 1, "block": "w", "silent": 40})
    take(p, "ticket/3", "r3", 1, ttl=10, max_=3, at=now - 50)              # expired, back to ready
    p.events.add(EXPIRED, item="ticket/3", source="ergostat", data={"run": "r3", "fence": 1, "block": "w", "silent": 40})
    assert measures.counts(p, p.model.spec) == {"held": 2, "dead": 1, "overdue": 1, "expired": 2}
    assert measure(p, "ergostat.leases.dead") == 1 and measure(p, "leases.held@ticket") == 2
    assert measure(p, "ergostat.leases.expired@ticket") == 2 and measure(p, "ergostat.leases.held@worker") == 0
    att = state.attention(state.snapshot(p), running=False, model=p.model)
    said = {a["what"]: a for a in att if a["what"].startswith("item ")}
    assert said["item ticket/2"]["level"] == "bad" and "dead letter" in said["item ticket/2"]["says"]
    assert said["item ticket/3"]["level"] == "warn" and "expired" in said["item ticket/3"]["says"]
    from ergostat.spec import read
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(TAKER + """
stocks:
  stalled:
    sensor: {builtin: ergostat.leases.expired@worker, every: 1m}
goals:
  none-stalled:
    stock: stalled
    hold: "<= 0"
"""))
    _, problems = read(tmp_path / "ergostat.yaml")
    assert not [x for x in problems if x.level == "error"], [x.message for x in problems if x.level == "error"]


def test_the_command_line_renews_gives_back_and_redrives(tmp_path):
    from ergostat.cli import main
    p = project(tmp_path, TAKER)
    p.events.add("ticket.opened", item="ticket/1", source="t")
    take(p, "ticket/1", "r1", 1, ttl=30, max_=1)
    env = {"ERGOSTAT_ITEM": "ticket/1", "ERGOSTAT_LEASE": "1", "ERGOSTAT_RUN": "r1"}
    import os
    from unittest import mock
    with mock.patch.dict(os.environ, env):
        before = item(p, "ticket/1").fields["lease"]["expires"]
        time.sleep(0.05)
        assert main(["-C", str(tmp_path), "lease", "--renew"]) == 0
        assert item(p, "ticket/1").fields["lease"]["expires"] > before
        assert main(["-C", str(tmp_path), "lease", "--nack", "cannot build it"]) == 0
    it = item(p, "ticket/1")
    assert it.state == "dead" and it.fields["lease"]["history"][0]["why"] == "cannot build it"
    with mock.patch.dict(os.environ, env):
        assert main(["-C", str(tmp_path), "lease", "--renew"]) == 1, "a lease that ended is not renewed"
    assert main(["-C", str(tmp_path), "lease", "ticket/1", "--redrive", "--why", "fixed"]) == 0
    assert item(p, "ticket/1").state == "ready"
    assert main(["-C", str(tmp_path), "lease", "ticket/1", "--redrive"]) == 1, "only a dead letter"
    assert main(["-C", str(tmp_path), "lease"]) == 0 and main(["-C", str(tmp_path), "lease", "ticket/1"]) == 0


@pytest.mark.slow
def test_a_lease_held_by_a_run_survives_a_model_edit(tmp_path):
    """A model swapped in place (SPEC §9.1) while a run holds a lease: the run keeps its lease, what it records still
    renews it, its fencing number stands, and it ends the lease when it finishes; the next item is taken under the new
    model's terms.

    Sized for a loaded machine: each renewal is a CLI call (a Python start, a second or more under load), so the TTL
    is 3 s rather than 1 s, and the run lasts several TTLs (checked below, so the renewals are what kept it); the
    waits are for conditions, long enough for a slow machine, and end as soon as each holds."""
    run = ('for i in 1 2 3 4 5 6 7 8 9 10; do $ERGOSTAT_CMD event --add ticket.progress --item $ERGOSTAT_ITEM '
           '--data "{\\"step\\": $i}"; sleep 0.5; done; '
           'echo "{\\"event\\": \\"ticket.done\\", \\"data\\": {\\"fence\\": $ERGOSTAT_LEASE}}"')
    text = model(run, "{ttl: 3s}").replace("pool: 2", "pool: 1")
    p = project(tmp_path, text)
    p.events.add("ticket.opened", item="ticket/1", source="t")
    e = start(p)
    try:
        assert wait_for(lambda: item(p, "ticket/1").state == "leased", 60)
        held = item(p, "ticket/1").fields["lease"]
        (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text.replace("{ttl: 3s}", "{ttl: 9s}")))
        said = e.swap(mdl.load(tmp_path))
        assert said["runs"] == ["worker ticket/1"], "the leased run carried over"
        p.events.add("ticket.opened", item="ticket/2", source="t")
        assert wait_for(lambda: item(p, "ticket/1").state == "done", 120)
        assert wait_for(lambda: item(p, "ticket/2").state == "done", 120)
    finally:
        e.close()
    one = item(p, "ticket/1")
    lease = one.fields["lease"]
    assert [h["how"] for h in lease["history"]] == ["ack"], "kept across the edit: renewed by its events, not expired"
    assert lease["history"][0]["run"] == held["holder"] and one.fields["fence"] == 1
    taken = p.events.query(n=None, type=TAKEN, item="ticket/1")[0]
    ended = max(m["time"] for m in one.moves if m["to"] == "done")
    assert ended - taken["time"] > 3, "the run outlived its TTL: only its renewals kept the lease"
    assert item(p, "ticket/2").fields["lease"]["history"][0]["how"] == "ack"
    assert p.events.query(n=None, type=TAKEN, item="ticket/2")[0]["data"]["ttl"] == 9, "the next lease on the new terms"


def test_given_back_to_wait_for_news_it_is_ready_at_the_first_news_of_it(tmp_path):
    p = project(tmp_path, KIND)
    p.events.add("ticket.opened", item="ticket/1", source="t")
    take(p, "ticket/1", "r1", 1)
    p.events.add("ticket.noted", item="ticket/1", source="w", causedby="r1", data={"waiting": "review"})
    p.events.add(ENDED, item="ticket/1", source="ergostat", data={"run": "r1", "fence": 1, "how": "nack", "why": "review",
                                                                  "after": 300, "count": False, "news": True})
    assert item(p, "ticket/1").fields["lease"]["not_before"] > time.time() + 200
    p.events.add("ticket.noted", item="ticket/1", source="w", causedby="r1", data={"late": True})   # its own run's: not news
    p.events.add("ergostat.workspace.held", item="ticket/1", source="ergostat")                     # ergostat's: not news
    assert item(p, "ticket/1").fields["lease"].get("not_before")
    p.events.add("ticket.reviewed", item="ticket/1", source="github", data={"state": "approved"})   # a webhook's: news
    lease = item(p, "ticket/1").fields["lease"]
    assert "not_before" not in lease and lease["woken"] > 0
    take(p, "ticket/1", "r2", 2)                                       # taken again at once, and put off plainly after
    p.events.add(ENDED, item="ticket/1", source="ergostat", data={"run": "r2", "fence": 2, "how": "nack", "why": "x",
                                                                  "after": 300, "count": False})
    p.events.add("ticket.reviewed", item="ticket/1", source="github")
    assert item(p, "ticket/1").fields["lease"]["not_before"] > time.time() + 200
