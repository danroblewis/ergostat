"""Relations between items (SPEC §5a, *Relations*; spec/relations.py, precedence.py): declared on a kind, folded as
sets with their history, kept both ways in the item index, cross-kind; each item's status, the critical path and
slack, the projected schedule, cycles as a finding, and a block that takes only unblocked items."""

from __future__ import annotations

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.spec import items as its
from ergostat.spec.changes import fold_event
from ergostat.spec.itemindex import index_for
from ergostat.store import Project

T0 = 1_700_000_000.0

MODEL = """
projections:
  epic:
    query: key.startswith('epic/')
    fields:
      state:
        values: [planned, underway, shipped]
    events:
      epic-started:
        when: type == 'epic.started'
        '...': data
        state: set('underway')
      epic-shipped:
        when: type == 'epic.shipped'
        '...': data
        state: set('shipped')
      other:
        when: true
        '...': data
    relations:
      after: epic
  ticket:
    query: key.startswith('ticket/')
    fields:
      state:
        values: [todo, doing, done]
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
    relations:
      blocked_by: ticket
      parent: epic
      duplicates: {projection: [ticket, epic], inverse: duplicated_by}
messages:
  done: {ticket: [done], epic: [shipped]}
"""


def project(tmp_path, text=MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def problems(tmp_path, text) -> list[str]:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    from ergostat.spec import read
    _, got = read(tmp_path / "ergostat.yaml")
    return [f"{p.code}: {p.message}" for p in got if p.level == "error"]


# ---- the declaration


def test_a_kind_declares_relations_with_their_defaults(tmp_path):
    p = project(tmp_path)
    t = p.model.spec.items["ticket"]
    b, parent, dup = t.relations["blocked_by"], t.relations["parent"], t.relations["duplicates"]
    assert (b.kinds, b.precedence, b.inverse, b.group) == (["ticket"], True, "blocks", False)
    assert (parent.kinds, parent.precedence, parent.inverse, parent.group) == (["epic"], False, "children", True)
    assert (dup.kinds, dup.precedence, dup.inverse) == (["ticket", "epic"], False, "duplicated_by")
    assert p.model.spec.items["epic"].relations["after"].precedence
    assert t.fold["blocked_by"] == "relation"                 # folded as a set of ids, unless fold: says otherwise


@pytest.mark.parametrize("rel,says", [
    ("blocked_by: story", "'story' is not a projection"),
    ("Blocked: ticket", "is not a relation's name"),
    ("blocked_by: {projection: ticket, precedence: maybe}", "precedence: and group: are true or false"),
    ("blocked_by: {projection: ticket, inverse: blocked_by}", "the other direction's name"),
    ("blocked_by: {projection: ticket, colour: red}", "colour"),
])
def test_a_relation_that_is_not_one_is_an_error(tmp_path, rel, says):
    got = problems(tmp_path, f"""
        projections:
          ticket:
            match:
              key: ticket/*
            states: [todo, done]
            relations:
              {rel}
        """)
    assert any(says in g for g in got), got


STARTS = """
    projections:
      ticket:
        query: key.startswith('ticket/')
        fields:
          state:
            values: [todo, review, done, on-hold]
        relations:
          {rel}
    messages:
      done: {{ticket: [done]}}
      paused: {{ticket: [on-hold]}}
"""


def test_starts_at_naming_an_unknown_state_is_refused(tmp_path):
    got = problems(tmp_path, STARTS.format(rel="blocked_by: {projection: ticket, starts_at: [reveiw]}"))
    assert [g.split(":")[0] for g in got] == ["starts-at-unknown-state"], got
    assert "did you mean review" in got[0]
    assert problems(tmp_path, STARTS.format(rel="blocked_by: {projection: ticket, starts_at: [review]}")) == []


def test_starts_at_on_a_group_relation_is_refused(tmp_path):
    got = problems(tmp_path, STARTS.format(rel="parent: {projection: ticket, starts_at: [review]}"))
    assert [g.split(":")[0] for g in got] == ["starts-at-not-precedence"], got
    got = problems(tmp_path, STARTS.format(rel="relates_to: {projection: ticket, starts_at: [review]}"))
    assert [g.split(":")[0] for g in got] == ["starts-at-not-precedence"], got


@pytest.mark.parametrize("state", ["done", "on-hold"])
def test_starts_at_naming_a_finished_or_paused_state_is_refused(tmp_path, state):
    got = problems(tmp_path, STARTS.format(rel=f"blocked_by: {{projection: ticket, starts_at: [{state}]}}"))
    assert [g.split(":")[0] for g in got] == ["starts-at-finished"], got


TAKEN = """
    projections:
      gap:
        query: key.startswith('gap/')
        fields:
          state:
            values: [todo, approved, merged]
        relations:
          depends_on: {{projection: gap, starts_at: [{state}]}}
    blocks:
      dev:
        type: program
        run: "true"
        takes: {{projection: gap, at: todo, unblocked: true}}
"""


@pytest.mark.parametrize("state,code", [("merged", "starts-at-finished"), ("dead", "starts-at-finished"),
                                        ("leased", "starts-at-leased"), ("approved", None)])
def test_starts_at_on_a_taken_kind_with_no_done_reads_its_own_last_state(tmp_path, state, code):
    # a block takes the kind, so it gains leased and dead: the last state is still merged, not dead
    got = problems(tmp_path, TAKEN.format(state=state))
    assert [g.split(":")[0] for g in got] == ([code] if code else []), got


def test_takes_unblocked_needs_a_precedence_relation(tmp_path):
    got = problems(tmp_path, """
        projections:
          ticket:
            query: key.startswith('ticket/')
            fields:
              state:
                values: [todo, done]
            relations: {parent: ticket}
        blocks:
          dev:
            type: program
            run: "true"
            takes: {projection: ticket, at: todo, unblocked: true}
""")
    assert any("no precedence relation" in g for g in got), got


# ---- folding: added and removed like fields, with history


def test_relation_folding_adds_removes_and_sets():
    doc: dict = {}
    rules = {"blocked_by": "relation"}
    for data in ({"blocked_by": "ticket/2"}, {"blocked_by": ["ticket/3", "ticket/2"]}):
        assert fold_event(doc, {"data": data}, rules)[1] is None
    assert doc["blocked_by"] == ["ticket/2", "ticket/3"]
    assert fold_event(doc, {"data": {"blocked_by": {"add": "ticket/9", "remove": ["ticket/2"]}}}, rules)[1] is None
    assert doc["blocked_by"] == ["ticket/3", "ticket/9"]
    assert fold_event(doc, {"data": {"blocked_by": {"set": ["ticket/7"]}}}, rules)[1] is None    # a mirror says it whole
    assert doc["blocked_by"] == ["ticket/7"]
    done, why = fold_event(doc, {"data": {"blocked_by": "ticket/7"}}, rules)
    assert why is None and done == []                        # nothing new: no change
    for bad in ({"blocked_by": 3}, {"blocked_by": {"drop": "x"}}):
        before = list(doc["blocked_by"])
        assert fold_event(doc, {"data": bad}, rules)[1] is not None and doc["blocked_by"] == before   # refused whole
    assert fold_event(doc, {"patch": [{"op": "remove", "path": "/blocked_by/0"}]}, rules)[1] is None   # or patch it
    assert doc["blocked_by"] == []


def test_relations_are_kept_with_their_history_and_both_ways_in_the_index(tmp_path):
    p = project(tmp_path)
    ev = p.events
    ev.add("epic.planned", item="epic/a", at=T0)
    ev.add("ticket.planned", item="ticket/1", data={"parent": "epic/a"}, at=T0 + 1)
    ev.add("ticket.planned", item="ticket/2", data={"parent": "epic/a", "blocked_by": "ticket/1"}, at=T0 + 2)
    ev.add("ticket.linked", item="ticket/2", data={"blocked_by": {"add": "ticket/3"}}, at=T0 + 3)
    ev.add("ticket.planned", item="ticket/3", data={"duplicates": "epic/a"}, at=T0 + 4)     # cross-kind
    ix = index_for(ev, p.model.spec, False)
    assert sorted(ix.links_from(["ticket/2"])) == [("ticket/2", "blocked_by", "ticket/1"), ("ticket/2", "blocked_by", "ticket/3"),
                                                   ("ticket/2", "parent", "epic/a")]
    assert sorted(a for a, _, _ in ix.links_to(["epic/a"])) == ["ticket/1", "ticket/2", "ticket/3"]
    ev.add("ticket.unlinked", item="ticket/2", data={"blocked_by": {"remove": "ticket/1"}}, at=T0 + 5)
    ix = index_for(ev, p.model.spec, False)
    assert ("ticket/2", "blocked_by", "ticket/1") not in ix.links_from(["ticket/2"])       # taken away, followed
    d = its.detail(ev, p.model.spec, "ticket/2")
    assert [c["after"] for c in d["history"]["blocked_by"]] == [["ticket/1"], ["ticket/1", "ticket/3"], ["ticket/3"]]
    assert d["history"]["blocked_by"][0]["rule"] == "relation"
    r = its.detail(ev, p.model.spec, "epic/a")["relations"]
    assert sorted(r["in"]["children"]) == ["ticket/1", "ticket/2"] and r["in"]["duplicated_by"] == ["ticket/3"]
    r = its.detail(ev, p.model.spec, "ticket/2")["relations"]
    assert r["out"] == {"blocked_by": ["ticket/3"], "parent": ["epic/a"]} and r["waiting"] == ["ticket/3"]


# ---- what the relations say: status, the critical path, the schedule


def _seed_history(ev, n=4):
    """Finished tickets: each 100 s in todo, 600 s doing."""
    for i in range(n):
        ev.add("ticket.planned", item=f"ticket/old{i}", at=T0 + i)
        ev.add("ticket.started", item=f"ticket/old{i}", at=T0 + 100 + i)
        ev.add("ticket.done", item=f"ticket/old{i}", at=T0 + 700 + i)


def test_each_item_is_done_active_ready_or_blocked(tmp_path):
    p = project(tmp_path)
    ev = p.events
    ev.add("ticket.planned", item="ticket/a", at=T0)
    ev.add("ticket.planned", item="ticket/b", data={"blocked_by": "ticket/a"}, at=T0)
    ev.add("ticket.planned", item="ticket/c", data={"blocked_by": ["ticket/a", "ticket/nowhere"]}, at=T0)
    ev.add("ticket.planned", item="ticket/d", at=T0)
    ev.add("ticket.started", item="ticket/d", at=T0 + 5)
    g = pr.build(ev, p.model.spec, ["ticket"], T0 + 10, T0 - 10)
    st = {x["id"]: x["status"] for x in g["items"]}
    assert st == {"ticket/a": "unblocked", "ticket/b": "blocked", "ticket/c": "blocked", "ticket/d": "active"}
    waits = {x["id"]: x["waiting"] for x in g["items"]}
    assert waits["ticket/c"] == ["ticket/a", "ticket/nowhere"]      # an item never seen is not known to be finished
    ev.add("ticket.started", item="ticket/a", at=T0 + 20)
    ev.add("ticket.done", item="ticket/a", at=T0 + 30)
    g = pr.build(ev, p.model.spec, ["ticket"], T0 + 40, T0 - 10)
    st = {x["id"]: x["status"] for x in g["items"]}
    assert st["ticket/a"] == "done" and st["ticket/b"] == "unblocked" and st["ticket/c"] == "blocked"


def test_the_critical_path_method_on_a_textbook_network():
    # A(3) -> B(4) -> D(2); A -> C(2) -> D; C -> E(5): the longest path A, C, E (10); B and D have slack
    d = {"A": 3, "B": 4, "C": 2, "D": 2, "E": 5}
    plan = pr.cpm(d, [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("C", "E")])
    assert {n for n, x in plan.items() if x["critical"]} == {"A", "C", "E"}
    assert plan["E"]["ef"] == 10 and plan["A"]["end"] == 10
    assert (plan["B"]["es"], plan["B"]["slack"]) == (3, 1) and (plan["D"]["es"], plan["D"]["slack"]) == (7, 1)
    assert plan["C"]["slack"] == 0 and plan["E"]["ls"] == 5
    started = pr.cpm(d, [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("C", "E")], started=["C"])
    assert started["C"]["es"] == 0 and started["E"]["ef"] == 7      # C already going: it does not wait on A


def test_cycles_are_found():
    assert pr.cycles("abcd", [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")]) == [["a", "b", "c"]]
    assert pr.cycles("ab", [("a", "a"), ("a", "b")]) == [["a"]]
    assert pr.cycles("abc", [("a", "b"), ("b", "c")]) == []


def test_a_cycle_is_a_finding_and_left_out_of_the_projection(tmp_path):
    p = project(tmp_path)
    ev = p.events
    ev.add("ticket.planned", item="ticket/x", data={"blocked_by": "ticket/y"}, at=T0)
    ev.add("ticket.planned", item="ticket/y", data={"blocked_by": "ticket/x"}, at=T0)
    ev.add("ticket.planned", item="ticket/z", data={"blocked_by": "ticket/y"}, at=T0)
    g = pr.build(ev, p.model.spec, ["ticket"], T0 + 1, T0)
    assert g["cycles"] == [["ticket/x", "ticket/y"]]
    by = {x["id"]: x for x in g["items"]}
    assert by["ticket/x"]["cycle"] and "es" not in by["ticket/x"] and by["ticket/z"]["status"] == "blocked"
    assert pr.relation_cycles(ev, p.model.spec) == [["ticket/x", "ticket/y"]]
    from ergostat import state as st
    att = st.attention({"loops": {}, "agents": {}, "residuals": {}, "cycles": st.relation_cycles(p)})
    assert any("cycle of precedence" in a["says"] and a["level"] == "warn" for a in att), att


def test_durations_slack_and_the_projected_schedule(tmp_path):
    p = project(tmp_path)
    ev = p.events
    _seed_history(ev)
    t = T0 + 2000
    # a fan-out and a join: a -> (b, c) -> d; b is longer (it is already going, with 100 s of its 600 done)
    ev.add("ticket.planned", item="ticket/a", at=t)
    ev.add("ticket.planned", item="ticket/b", data={"blocked_by": "ticket/a"}, at=t)
    ev.add("ticket.planned", item="ticket/c", data={"blocked_by": "ticket/a"}, at=t)
    ev.add("ticket.planned", item="ticket/d", data={"blocked_by": ["ticket/b", "ticket/c"]}, at=t)
    ev.add("ticket.started", item="ticket/a", at=t + 10)
    now = t + 110
    g = pr.build(ev, p.model.spec, ["ticket"], now, now)
    by = {x["id"]: x for x in g["items"]}
    assert by["ticket/a"]["duration"] == pytest.approx(500)     # 600 s doing, 100 s of it gone
    assert by["ticket/b"]["duration"] == pytest.approx(600) and by["ticket/b"]["known"]
    assert by["ticket/b"]["es"] == pytest.approx(now + 500) and by["ticket/d"]["es"] == pytest.approx(now + 1100)
    assert g["end"] == pytest.approx(now + 1700)
    assert g["critical"][0] == "ticket/a" and g["critical"][-1] == "ticket/d"
    assert by["ticket/b"]["slack"] == 0 and by["ticket/c"]["slack"] == 0      # equal lengths: both critical
    # the Gantt projection: in the order they would start, each after what it waits on, state by state
    order = [x["id"] for x in g["items"] if "es" in x]
    assert order == ["ticket/a", "ticket/b", "ticket/c", "ticket/d"]
    for e in g["edges"]:
        if e["kind"] == "precedence":
            assert by[e["from"]]["projected"][-1][2] <= by[e["to"]]["projected"][0][1] + 1e-6, e
    assert by["ticket/d"]["projected"] == [["doing", pytest.approx(now + 1100), pytest.approx(now + 1700)]]
    assert by["ticket/a"]["segments"][0][0] == "todo" and by["ticket/a"]["segments"][-1][0] == "doing"   # actual


def test_a_parent_is_a_summary_of_its_children_and_follows_what_it_follows(tmp_path):
    p = project(tmp_path)
    ev = p.events
    _seed_history(ev)
    t = T0 + 2000
    ev.add("epic.planned", item="epic/one", at=t)
    ev.add("epic.planned", item="epic/two", data={"after": "epic/one"}, at=t)
    ev.add("ticket.planned", item="ticket/1", data={"parent": "epic/one"}, at=t)
    ev.add("ticket.planned", item="ticket/2", data={"parent": "epic/one", "blocked_by": "ticket/1"}, at=t)
    ev.add("ticket.planned", item="ticket/3", data={"parent": "epic/two"}, at=t)
    g = pr.build(ev, p.model.spec, ["ticket", "epic"], t, t)
    by = {x["id"]: x for x in g["items"]}
    assert by["epic/one"]["summary"] and by["epic/one"]["children"] == {"total": 2, "done": 0}
    assert by["epic/one"]["ef"] == pytest.approx(t + 1200)
    assert by["ticket/3"]["es"] == pytest.approx(t + 1200)     # its epic comes after the first: so does it
    assert by["epic/two"]["ef"] == pytest.approx(t + 1800)


def test_a_block_that_takes_unblocked_items_takes_the_critical_first(tmp_path):
    p = project(tmp_path)
    ev = p.events
    _seed_history(ev)
    t = T0 + 2000
    # short: s (alone); long chain: x -> y -> z; and w, blocked by x
    for i in ("s", "x", "y", "z", "w"):
        ev.add("ticket.planned", item=f"ticket/{i}", at=t + {"s": 0, "x": 1, "y": 2, "z": 3, "w": 4}[i])
    ev.add("ticket.linked", item="ticket/y", data={"blocked_by": "ticket/x"}, at=t + 5)
    ev.add("ticket.linked", item="ticket/z", data={"blocked_by": "ticket/y"}, at=t + 5)
    ev.add("ticket.linked", item="ticket/w", data={"blocked_by": "ticket/x"}, at=t + 5)
    spec = p.model.spec
    todo = sorted(its.project(ev, spec, "ticket"), key=lambda i: i.first)
    todo = [i for i in todo if i.state == "todo"]
    got = pr.order_ready(ev, spec, "ticket", todo, t + 10)
    assert [i.id for i in got] == ["ticket/x", "ticket/s"]      # only the unblocked; the one on the long chain first
    from types import SimpleNamespace

    from ergostat.leases.ready import unblocked
    d = SimpleNamespace(p=p, spec=spec)
    plain = SimpleNamespace(takes=SimpleNamespace(unblocked=False, kind="ticket"))
    assert unblocked(d, plain, todo) == todo                     # any other block's order, as it was
    ask = SimpleNamespace(takes=SimpleNamespace(unblocked=True, kind="ticket"))
    assert [i.id for i in unblocked(d, ask, todo)] == ["ticket/x", "ticket/s"]


def test_the_items_graph_answer_is_kept_until_the_record_changes(tmp_path):
    from ergostat.web.relations_api import graph
    p = project(tmp_path)
    p.events.add("ticket.planned", item="ticket/a", at=time.time())
    snap = {"at": time.time(), "window": 3600}
    one = graph(p, p.model, snap, {"kinds": ["ticket"]})
    two = graph(p, p.model, {**snap, "at": snap["at"] + 3}, {"kinds": ["ticket"]})
    assert one is two                                             # nothing new: the same answer, nothing redrawn
    p.events.add("ticket.planned", item="ticket/b", data={"blocked_by": "ticket/a"})
    three = graph(p, p.model, snap, {"kinds": ["ticket"]})
    assert three is not one and len(three["items"]) == 2


# ---- a system's Graph: its own kinds' dependency network, another system's items stubs at its edge

FACTORY = """
systems:
  knowledge: {description: what is known}
  building: {description: the gaps}
  support: {description: the tickets}
projections:
  gap:
    query: key.startswith('gap/')
    system: building
    fields:
      state:
        values: [ready, building, done]
    events:
      gap-started:
        when: type == 'gap.started'
        '...': data
        state: set('building')
      gap-done:
        when: type == 'gap.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
    relations: {depends_on: gap}
  session:
    query: key.startswith('session/')
    system: building
    fields:
      state:
        values: [running, ended]
    events:
      session-ended:
        when: type == 'session.ended'
        '...': data
        state: set('ended')
      other:
        when: true
        '...': data
    relations: {gap: gap}
  review:
    query: key.startswith('review/')
    system: knowledge
    fields:
      state:
        values: [open, judged]
    events:
      review-judged:
        when: type == 'review.judged'
        '...': data
        state: set('judged')
      other:
        when: true
        '...': data
    relations: {gap: gap}
  ticket:
    query: key.startswith('ticket/')
    system: support
    fields:
      state:
        values: [todo, done]
    events:
      ticket-done:
        when: type == 'ticket.done'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
    relations: {blocked_by: gap}
messages:
  done: {gap: [done], session: [ended], review: [judged], ticket: [done]}
"""


def factory(tmp_path, ticket: bool = True) -> Project:
    """gap/a, then gap/b depending on it, then gap/c on gap/b; a session about each; a review about gap/c; a ticket
    blocked by gap/c (unfinished)."""
    p = project(tmp_path, FACTORY)
    ev = p.events
    ev.add("gap.opened", item="gap/a", at=T0)
    ev.add("gap.opened", item="gap/b", data={"depends_on": "gap/a"}, at=T0 + 1)
    ev.add("gap.opened", item="gap/c", data={"depends_on": "gap/b"}, at=T0 + 2)
    ev.add("gap.started", item="gap/c", at=T0 + 3)
    for g in "abc":
        ev.add("session.opened", item=f"session/{g}", data={"gap": f"gap/{g}"}, at=T0 + 4)
    ev.add("review.opened", item="review/1", data={"gap": "gap/c"}, at=T0 + 5)
    if ticket:
        ev.add("ticket.opened", item="ticket/1", data={"blocked_by": "gap/c"}, at=T0 + 6)
    return p


def test_a_systems_graph_draws_no_other_systems_items_and_says_where_they_are(tmp_path):
    from ergostat.web.relations_api import graph
    p = factory(tmp_path)
    before = pr.build(p.events, p.model.spec, ["review"], T0 + 10, T0 - 10)     # no system: every relation, any kind
    assert {"gap/a", "gap/b", "gap/c", "session/c"} <= {x["id"] for x in before["items"]}
    ans = graph(p, p.model, {"at": T0 + 10, "window": 3600}, {"kinds": ["review"], "system": ["knowledge"]})
    assert [x["id"] for x in ans["items"]] == ["review/1"]                  # no gap, no session: not even a stub
    assert ans["outside"] == [] and ans["edges"] == [] and ans["waits"] is False
    assert ans["about"] == [{"projection": "review", "rel": "gap", "to": "gap", "system": "building"}]
    assert ans["items"][0]["links"] == {"gap": ["gap/c"]}                  # listed on its card, not drawn


def test_an_item_blocked_by_another_systems_item_is_waiting_with_one_stub(tmp_path):
    p = factory(tmp_path)
    spec = p.model.spec
    g = pr.build(p.events, spec, ["ticket"], T0 + 10, T0 - 10, own=["ticket"])
    assert [x["id"] for x in g["items"]] == ["ticket/1"]
    assert [(x["id"], x["system"], x["status"], x["outside"]) for x in g["outside"]] == [("gap/c", "building", "active", True)]
    assert g["edges"] == [{"from": "gap/c", "to": "ticket/1", "rel": "blocked_by", "kind": "outside", "critical": False}]
    assert g["items"][0]["status"] == "blocked" and g["items"][0]["waiting"] == ["gap/c"]
    p.events.add("gap.done", item="gap/c", at=T0 + 20)
    g = pr.build(p.events, spec, ["ticket"], T0 + 30, T0 - 10, own=["ticket"])
    assert g["items"][0]["status"] == "unblocked" and g["outside"][0]["status"] == "done"


def test_an_item_waiting_on_another_systems_item_is_projected_after_it(tmp_path):
    p = factory(tmp_path)
    spec = p.model.spec
    plain = pr.build(p.events, spec, ["ticket"], T0 + 10, T0 - 10)            # gap/c pulled as a card
    mine = pr.build(p.events, spec, ["ticket"], T0 + 10, T0 - 10, own=["ticket"])
    by = lambda g: {x["id"]: x for x in g["items"]}                         # noqa: E731
    gap_c, t, t0 = by(plain)["gap/c"], by(mine)["ticket/1"], by(plain)["ticket/1"]
    assert gap_c["ef"] > T0 + 10 and t["es"] >= gap_c["ef"]                # not started now: after gap/c's end
    assert {k: t[k] for k in ("es", "ef", "slack", "critical")} == {k: t0[k] for k in ("es", "ef", "slack", "critical")}
    assert mine["end"] == plain["end"] and mine["critical"] == [x for x in plain["critical"] if x.startswith("ticket/")]
    assert "ticket/1" in mine["critical"] and [x["id"] for x in mine["items"]] == ["ticket/1"]


RELATED = """
systems: {planning: {description: planned}, delivery: {description: built}}
projections:
  epic:
    query: key.startswith('epic/')
    system: planning
    fields:
      state:
        values: [planned, shipped]
    relations: {after: epic}
  ticket:
    query: key.startswith('ticket/')
    system: delivery
    fields:
      state:
        values: [todo, doing, done]
    events:
      ticket-started:
        when: type == 'ticket.started'
        '...': data
        state: set('doing')
      other:
        when: true
        '...': data
    relations: {parent: epic}
messages:
  done: {ticket: [done], epic: [shipped]}
"""


def test_a_child_of_another_systems_parent_still_waits_for_what_that_parent_waits_on(tmp_path):
    p = project(tmp_path, RELATED)
    ev = p.events
    ev.add("epic.planned", item="epic/e1", at=T0)
    ev.add("epic.planned", item="epic/e2", data={"after": "epic/e1"}, at=T0 + 1)
    ev.add("ticket.planned", item="ticket/a", data={"parent": "epic/e1"}, at=T0 + 2)
    ev.add("ticket.started", item="ticket/a", at=T0 + 3)
    ev.add("ticket.planned", item="ticket/c", data={"parent": "epic/e2"}, at=T0 + 4)
    spec = p.model.spec
    plain = pr.build(ev, spec, ["ticket"], T0 + 10, T0 - 10)
    mine = pr.build(ev, spec, ["ticket"], T0 + 10, T0 - 10, own=["ticket"])
    by = lambda g: {x["id"]: x for x in g["items"]}                         # noqa: E731
    assert sorted(by(mine)) == ["ticket/a", "ticket/c"] and sorted(x["id"] for x in mine["outside"]) == ["epic/e1", "epic/e2"]
    a, c = by(mine)["ticket/a"], by(mine)["ticket/c"]
    assert c["es"] >= a["ef"] > T0 + 10                                    # e2 after e1: its child after e1's
    assert {k: c[k] for k in ("es", "ef", "critical")} == {k: by(plain)["ticket/c"][k] for k in ("es", "ef", "critical")}


def test_the_gaps_own_system_keeps_its_chain_and_critical_path(tmp_path):
    p = factory(tmp_path, ticket=False)          # (another system's ticket waiting on a gap: no longer on its path)
    spec = p.model.spec
    plain = pr.build(p.events, spec, ["gap"], T0 + 10, T0 - 10)
    mine = pr.build(p.events, spec, ["gap"], T0 + 10, T0 - 10, own=["gap", "session"])
    gaps = lambda g: [x["id"] for x in g["items"] if x["projection"] == "gap"]   # noqa: E731
    assert gaps(plain) == gaps(mine) and {"gap/a", "gap/b", "gap/c"} == set(gaps(plain))   # the depends_on chain
    assert plain["critical"] == mine["critical"] and plain["end"] == mine["end"]
    prec = lambda g: sorted((e["from"], e["to"]) for e in g["edges"] if e["kind"] == "precedence")   # noqa: E731
    assert prec(plain) == prec(mine) == [("gap/a", "gap/b"), ("gap/b", "gap/c")]
    assert mine["outside"] == [] and not any(x["projection"] == "session" for x in mine["items"])   # about a gap: not pulled


