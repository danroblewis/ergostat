"""A narrow AI's specification and a decision's means, read from what is declared and from the record
(docs/proposals/agent-means.md, dev/records/agent-page-narrow-ai-and-decision.md): an approver on the decision rung
held against its ``takes.to``, a controller decision's words and its commands acted on, and the rung's spans."""

import textwrap

import pytest

from ergostat import model as mdl
from ergostat.leases import ENDED, EXPIRED, TAKEN
from ergostat.store import Project
from ergostat.web.server import Live, api

MODEL = """
name: t
stocks:
  todo: {sensor: {manual: true}}
  aside: {sensor: {manual: true}}
  inner: {sensor: {manual: true}}
flows:
  done: {from: todo}
  picked: {from: aside}
  written: {from: todo}
  solo-done: {from: todo}
  classed: {from: todo}
goals:
  todo-low: {stock: todo, hold: "<= 0"}
  aside-low: {stock: aside, hold: "<= 0"}
  inner-low: {stock: inner, hold: "<= 5"}
projections:
  request:
    query: key.startswith('request/')
    fields:
      state:
        type: one of [new, approved, denied, deferred]
agents:
  approver: {kind: decision}
  picker: {kind: decision}
  small: {kind: narrow-ai, model: haiku}
blocks:
  approve:
    type: program
    agent: approver
    run: python3 bin/x.py
    goal: todo-low
    takes: {projection: request, at: new, to: [approved, denied, deferred]}
    out: flow.done
  pick:
    type: program
    agent: picker
    run: python3 bin/x.py
    every: 1h
    in: [goal.aside-low.error, goal.todo-low.error]
    out: {write: block.writer, solo: block.solo, move: flow.picked, set: goal.inner-low}
  other:
    type: program
    run: python3 bin/x.py
    every: 1h
    out: block.writer
  writer: {type: program, run: python3 bin/x.py, out: flow.written}
  solo: {type: program, run: python3 bin/x.py, out: flow.solo-done}
  classify:
    type: ai
    agent: small
    prompt: Classify the request as one of approved, denied or deferred.
    run: python3 bin/x.py
    every: 1h
    timeout: 2m
    parse: json
    out: flow.classed
"""


def project(tmp_path) -> Project:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "x.py").write_text("print('x')\n")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    errors = [x for x in m.problems if x.level == "error"]
    assert not errors, errors
    return Project(m)


def means(p, name):
    return api(Live(p), f"agents/{name}", {})["spec"]["means"]


def lease(p, item, run, block="approve"):
    p.events.add(TAKEN, item=item, source="ergostat", data={"item": item, "run": run, "block": block, "fence": 1})


def end(p, item, run, how, state):
    p.events.add(ENDED, item=item, source="ergostat", causedby=run, data={"run": run, "how": how, "state": state})


def seed_approver(p):
    lease(p, "request/1", "r1")
    end(p, "request/1", "r1", "ack", "approved")
    lease(p, "request/2", "r2")
    end(p, "request/2", "r2", "ack", "approved")
    lease(p, "request/3", "r3")
    end(p, "request/3", "r3", "ack", "denied")
    lease(p, "request/4", "r4")
    end(p, "request/4", "r4", "nack", "new")                    # given back
    lease(p, "request/5", "r5")
    end(p, "request/5", "r5", "nack", "dead")                   # a dead letter
    end(p, "request/6", "lost", "ack", "approved")              # its take not in the record
    lease(p, "request/7", "r7", block="someone-else")
    end(p, "request/7", "r7", "ack", "approved")                # another block's: not counted here
    p.events.add(EXPIRED, item="request/8", source="ergostat", data={"run": "r8", "block": "approve", "state": "new"})


def test_the_approver_is_held_against_its_declared_answers(tmp_path):
    p = project(tmp_path)
    seed_approver(p)
    m = means(p, "approve")
    assert m["work"] == "items" and m["spec"] is None and len(m["spans"]) == 1
    c = m["spans"][-1]["counts"]
    assert c["to"] == [["approved", 2], ["denied", 1], ["deferred", 0]]       # never reached: 0, not missing
    assert dict(c["other"]) == {"given back to new": 1, "a dead letter": 1, "expired": 1}
    assert c["unattributed"] == 1


def test_a_take_older_than_the_lookback_is_found_by_its_item(tmp_path):
    p = project(tmp_path)
    p.events.add(TAKEN, item="request/9", source="ergostat", at=1_000.0,
                 data={"item": "request/9", "run": "old", "block": "approve"})
    end(p, "request/9", "old", "ack", "deferred")
    c = means(p, "approve")["spans"][-1]["counts"]
    assert c["to"][2] == ["deferred", 1] and c["unattributed"] == 0


def test_a_ladder_move_splits_the_counts_by_span_and_a_remake_keeps_the_gap(tmp_path):
    p = project(tmp_path)
    v = lambda n, rungs: p.events.add("model.changed", item="t", source="ergostat",          # noqa: E731
                                      data={"version": n, "parts": {}, "rungs": rungs})
    v("v-a", {"approve": "ai"})
    lease(p, "request/1", "r1")
    end(p, "request/1", "r1", "ack", "approved")
    v("v-b", {})                                                 # removed
    v("v-c", {"approve": "decision"})                            # made again under its name
    v("v-d", {"approve": "decision"})
    lease(p, "request/2", "r2")
    end(p, "request/2", "r2", "ack", "denied")
    sp = means(p, "approve")["spans"]                             # (the model loaded now: decision, as v-d was)
    assert [(s["rung"], s["first"], s["last"]) for s in sp] == [("ai", 1, 1), (None, 2, 2), ("decision", 3, 4)]
    assert sp[0]["counts"]["to"][:2] == [["approved", 1], ["denied", 0]]
    assert sp[2]["counts"]["to"][:2] == [["approved", 0], ["denied", 1]]       # the old record never merged in
    v("v-e", {"approve": "ai"})                                  # a move back up, ordered by seq, not by time
    p.model.agents["approve"].kind = "program"                   # and the model loaded now, not recorded yet
    sp = means(p, "approve")["spans"]
    assert [(s["rung"], s["first"]) for s in sp[2:]] == [("decision", 3), ("ai", 5), ("program", None)]
    assert sp[-1]["counts"]["to"][1] == ["denied", 0] and sp[2]["counts"]["to"][1] == ["denied", 1]


def seed_before_rungs(p):
    """A record from before rungs were kept: two versions with no ``rungs``, the approver's ends under them, then the
    model loaded now recorded (with its rungs) and one end after it."""
    from ergostat import history
    for i, n in enumerate(("old-1", "old-2")):                    # as history.note wrote them, but for rungs
        p.events.add("model.changed", item="t", source="ergostat",
                     data={"added": [], "removed": [], "changed": [], "parts": {}, "version": n, "first": not i})
    seed_approver(p)
    history.note(p)
    lease(p, "request/9", "r9")
    end(p, "request/9", "r9", "ack", "deferred")


def test_versions_recorded_before_rungs_keep_their_counts_in_a_span_of_their_own(tmp_path):
    p = project(tmp_path)
    seed_before_rungs(p)
    sp = means(p, "approve")["spans"]
    assert [(s["rung"], s["first"], s["last"]) for s in sp] == [("not recorded", 1, 2), ("decision", 3, 3)]
    old, now = sp[0]["counts"], sp[1]["counts"]
    assert old["to"] == [["approved", 2], ["denied", 1], ["deferred", 0]] and old["unattributed"] == 1   # not dropped
    assert dict(old["other"]) == {"given back to new": 1, "a dead letter": 1, "expired": 1}
    assert now["to"] == [["approved", 0], ["denied", 0], ["deferred", 1]] and not now["other"]       # never merged in


def test_no_key_declares_answers_a_decisions_are_its_takes_to(tmp_path):
    """The compile test for the key: the proposal declares none, so ``answers:`` is refused as any unknown key is, and a
    decision's answers are its ``takes.to``, which check already holds to its kind's states (``bad-states``)."""
    from ergostat.spec.compile import TYPE_KEYS
    assert not any("answers" in keys or "examples" in keys or "answer-schema" in keys for keys in TYPE_KEYS.values())
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL).replace(
        "    takes: {projection: request, at: new, to: [approved, denied, deferred]}",
        "    answers: [approved, denied]\n    takes: {projection: request, at: new, to: [approved, denied, maybe]}"))
    (tmp_path / "bin").mkdir()
    with pytest.raises(mdl.ModelError) as e:
        mdl.load(tmp_path)
    assert "answers" in str(e.value) and "maybe" in str(e.value), str(e.value)


def test_each_recorded_version_keeps_each_blocks_rung(tmp_path):
    from ergostat import history
    p = project(tmp_path)
    e = history.note(p)
    assert e["data"]["rungs"]["approve"] == "decision" and e["data"]["rungs"]["classify"] == "narrow-ai"
    sp = means(p, "classify")["spans"]
    assert [(s["rung"], s["first"], s["last"], s["seq"]) for s in sp] == [("narrow-ai", 1, 1, 0)]


def test_a_controller_says_once_per_run_and_its_commands_are_counted_per_port(tmp_path):
    p = project(tmp_path)
    for g in ("aside-low", "todo-low"):                           # one line, filed under each goal it serves
        p.events.add("controller.decided", item=g, source="pick", causedby="run1", data={"decision": "rewrite 3"})
        p.events.add("controller.decided", item=g, source="pick", causedby="run2", data={"decision": "rewrite 1"})
        p.events.add("controller.decided", item=g, source="pick", causedby="run3", data={"decision": "wait"})
    p.events.add("block.commanded", item="solo", source="ergostat", data={"amount": 2, "from": "pick"})
    p.events.add("block.commanded", item="writer", source="ergostat", data={"amount": 2, "from": "pick"})
    p.events.add("valve.opened", item="pick", source="pick", data={"amount": 1, "flow": "picked"})
    m = means(p, "pick")
    c = m["spans"][-1]["counts"]
    assert m["work"] == "controller" and dict(c["said"]) == {"rewrite #": 2, "wait": 1}
    by = {r["port"]: r for r in c["carried"]}
    assert by["solo: block.solo"]["n"] == 1 and by["move: flow.picked"]["n"] == 1
    assert by["write: block.writer"] == {"port": "write: block.writer", "n": None, "note": "shared with other"}
    assert by["set: goal.inner-low"] == {"port": "set: goal.inner-low", "n": None, "note": "not recorded"}
    assert "to" not in c                                         # no answer set, no 0 rows, no "other"


def test_a_narrow_ais_specification_is_its_block_as_declared(tmp_path):
    p = project(tmp_path)
    p.events.add("classified", item="request/1", source="classify", data={})
    rows = {shown: dict(kv) for shown, kv in means(p, "classify")["spec"]}
    assert rows["what it may move"]["out"] == {"out": ["flow.classed"]}
    assert rows["what it costs and how long"] == {"model": "haiku", "timeout": 120.0}
    assert rows["how it is answered"] == {"parse": "json"}
    assert rows["what its runs wrote (from the record)"] == {"classified": 1}
    assert means(p, "pick")["spec"] is None
