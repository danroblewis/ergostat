"""Leases on items (SPEC §9.5): a block that takes items runs once per item, each run holding a lease that its own
events renew, that ends on ack or nack, or expires when it is silent past its TTL; after its attempts an item is a
dead letter; a run whose lease ended is refused (fencing); the fold is the truth, across a restart."""

import json
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.leases import ENDED, EXPIRED, REDRIVEN, RENEWED, TAKEN
from ergostat.leases.terms import terms
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

KIND = """
name: t
items:
  ticket:
    id: ticket/*
    states: [ready, doing, done]
    on: {ticket.started: doing, ticket.done: done}
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
    takes: {kind: ticket, at: ready}
  bot:
    type: program
    run: "true"
    takes: {kind: ticket, at: ready}
  dev2:
    type: program
    agent: claude
    run: "true"
    takes: {kind: ticket, at: ready}
    lease: {ttl: 90s}
  person-ish:
    type: ai
    prompt: do it
    takes: {kind: ticket, at: doing}
    lease: {ttl: 3h, attempts: 1}
""")
    s = p.model.spec
    assert s.items["ticket"].states == ["ready", "leased", "doing", "done", "dead"], "a kind taken gains the lease's states"
    dev, bot, dev2, slow = (terms(s, s.blocks[n]) for n in ("dev", "bot", "dev2", "person-ish"))
    assert dev["tier"] == "ai" and dev["ttl"] == 40 * 60 and dev["attempts"] == 5 and dev["from"] == {"ttl": "default", "attempts": "kind"}
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
    takes: {kind: tickets, at: ready}
  b:
    type: program
    run: "true"
    takes: {kind: ticket, at: nowhere}
    every: 5s
  c:
    type: program
    run: "true"
    pool: 3
"""))
    _, problems = read(tmp_path / "ergostat.yaml")
    said = "\n".join(x.message for x in problems if x.level == "error")
    assert "'tickets' is not a kind of item" in said
    assert "'nowhere' is not a state of ticket" in said
    assert "started by them" in said
    assert "only a block that takes items runs more than once" in said
    assert "leases.robot: a tier of the ladder" in said


# ---- the engine: dispatch, the watchdog, fencing


WORKER = KIND + """
blocks:
  worker:
    type: program
    takes: {kind: ticket, at: ready}
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
    sensor: {items: ticket, state: ready, every: 0.2s}
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
    first.dispatch.finish = lambda *a, **k: None             # it dies: no lease is ended
    first.stop.set()
    from ergostat import runner as old
    old.kill_all()
    held = item(p, "ticket/1").fields["lease"]
    second = start(Project(mdl.load(tmp_path)))
    try:
        time.sleep(0.6)
        assert item(p, "ticket/1").fields["lease"]["holder"] == held["holder"], "the new engine reads the lease, and keeps it"
        assert item(p, "ticket/2").state == "ready", "the pool is full: the lease held counts"
        assert wait_for(lambda: item(p, "ticket/1").fields["lease"]["history"][0].get("how") == "expired", 5), \
            "expired on its TTL"
        assert wait_for(lambda: item(p, "ticket/2").state == "leased" or item(p, "ticket/1").state == "leased", 5)
    finally:
        second.close()
        old.STOPPING.clear()
    for i in (1, 2):                                         # stopped with ergostat: given back, not counted
        lease = item(p, f"ticket/{i}").fields["lease"]
        assert lease["holder"] is None
    assert any(h.get("why") == "stopped with ergostat" and h["counted"] is False
               for i in (1, 2) for h in item(p, f"ticket/{i}").fields["lease"]["history"])


def test_a_run_started_as_ergostat_stops_is_killed_and_gives_its_lease_back(tmp_path, monkeypatch):
    """The stop lands between a run's process starting and its being counted among those ``kill_all`` kills: the run
    still ends at once, its lease given back, not counted (it once ran on, its lease held past the engine's close)."""
    from ergostat import runner as old
    from ergostat.spec import engine as eng
    p = project(tmp_path, model("sleep 30").replace("pool: 2", "pool: 1"))
    e = Engine(p, say=lambda s: None)
    real = eng.Measured

    def spawned_as_close_begins(*a, **k):
        e.stop.set()                                         # what close does first: stop, and kill what is live
        old.kill_all()
        return real(*a, **k)
    monkeypatch.setattr(eng, "Measured", spawned_as_close_begins)
    opened(p, 1)
    e.start_all()
    try:
        assert wait_for(lambda: item(p, "ticket/0").fields.get("lease"), 5), "taken"
        assert wait_for(lambda: item(p, "ticket/0").fields["lease"]["holder"] is None, 8), "it ended, not ran on for 30s"
        lease = item(p, "ticket/0").fields["lease"]
        assert lease["history"][-1]["why"] == "stopped with ergostat" and lease["history"][-1]["counted"] is False
    finally:
        e.close()
        old.STOPPING.clear()


def test_nothing_is_taken_once_ergostat_is_stopping(tmp_path):
    p = project(tmp_path, model("sleep 30"))
    opened(p, 1)
    e = Engine(p, say=lambda s: None)
    e.stop.set()                                             # close began between the look and the take
    assert e.dispatch.take(p.model.spec.blocks["worker"], item(p, "ticket/0")) is None
    assert not p.events.query(n=None, type=TAKEN), "no lease taken after the stop: close would not wait for it"
    assert not e.running


# ---- measures, attention, the command line


TAKER = KIND + """
blocks:
  worker:
    type: program
    run: "true"
    takes: {kind: ticket, at: ready}
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
