"""The built-in join (SPEC §5a, *Join*): a parent moved on once all (or any) of its children reach a state, a rule on
its kind over the relation they name it by; fired by each child's move, from the item index; caused by that move;
never backwards; counted like any other move; checked."""

import textwrap
import time

from ergostat import model as mdl
from ergostat.spec import items as its
from ergostat.spec import read
from ergostat.spec.engine import Engine
from ergostat.spec.items import JOINED
from ergostat.store import Project

MODEL = """
name: t
items:
  epic:
    id: epic/*
    states: [planned, underway, shipped]
    join:
      - {children: parent, any: [doing, done], to: underway}
      - {children: parent, all: done, to: shipped}
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.started: doing, ticket.done: done, ticket.reopened: todo}
    relations: {parent: epic}
stocks:
  underway:
    sensor: {items: epic, state: underway, every: 1h}
flows:
  shipped:
    from: underway
    sensor: {items: epic, entering: shipped, over: 1h}
"""


def project(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    return Project(mdl.load(tmp_path))


def wait_for(cond, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(0.02)
    return cond()


def state(p, id):
    it = its.one(p.events, p.model.spec, id)
    return it.state if it else None


def seed(p):
    p.events.add("epic.planned", item="epic/1", source="t")
    for i in (1, 2, 3):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", data={"parent": "epic/1"})


def running(p):
    e = Engine(p, say=lambda s: None)
    e.start_all()
    return e


def test_a_parent_moves_once_all_its_children_reach_the_state(tmp_path):
    p = project(tmp_path)
    seed(p)
    e = running(p)
    try:
        for i in (1, 2):
            p.events.add("ticket.started", item=f"ticket/{i}", source="t")
            p.events.add("ticket.done", item=f"ticket/{i}", source="t")
        assert wait_for(lambda: state(p, "epic/1") == "underway")
        time.sleep(0.4)
        assert state(p, "epic/1") == "underway", "two of three done is not all"
        p.events.add("ticket.started", item="ticket/3", source="t")
        last = p.events.add("ticket.done", item="ticket/3", source="t")
        assert wait_for(lambda: state(p, "epic/1") == "shipped"), "the last child's move ships it"
        shipped = p.events.query(n=1, item="epic/1", type=JOINED)[-1]
        assert shipped["causedby"] == last["id"], "caused by the move that completed it"
        assert shipped["data"]["joined"] == {"to": "shipped", "children": "parent", "all": ["done"], "n": 3}
    finally:
        e.close()


def test_any_moves_it_on_the_first_child_and_never_back(tmp_path):
    p = project(tmp_path)
    seed(p)
    p.events.add("epic.planned", item="epic/2", source="t")              # no children: never joined
    e = running(p)
    try:
        first = p.events.add("ticket.started", item="ticket/2", source="t")
        assert wait_for(lambda: state(p, "epic/1") == "underway")
        assert p.events.query(n=1, item="epic/1", type=JOINED)[-1]["causedby"] == first["id"]
        p.events.add("ticket.reopened", item="ticket/2", source="t")       # back to todo: the epic stays underway
        time.sleep(0.4)
        assert state(p, "epic/1") == "underway" and state(p, "epic/2") == "planned"
        assert len(p.events.query(n=None, type=JOINED)) == 1
    finally:
        e.close()
    # what moved while ergostat was stopped is joined when it starts
    for i in (1, 2, 3):
        p.events.add("ticket.done", item=f"ticket/{i}", source="t")
    e = running(Project(mdl.load(tmp_path)))
    try:
        assert wait_for(lambda: state(p, "epic/1") == "shipped")
    finally:
        e.close()


def test_the_parents_move_is_counted_entering(tmp_path):
    from ergostat.spec.engine import read_sensor
    p = project(tmp_path)
    seed(p)
    e = running(p)
    try:
        for i in (1, 2, 3):
            p.events.add("ticket.done", item=f"ticket/{i}", source="t")
        assert wait_for(lambda: state(p, "epic/1") == "shipped")
        spec = p.model.spec
        it = its.one(p.events, spec, "epic/1")
        assert [m["to"] for m in it.moves] == ["planned", "underway", "shipped"]
        flow = spec.flows["shipped"].sensors["main"]
        assert read_sensor(spec, flow, p.events)[0] == 1.0, "one epic entered shipped in the hour"
    finally:
        e.close()


def test_a_join_is_checked(tmp_path):
    bad = MODEL.replace("{children: parent, all: done, to: shipped}", "{children: parent, all: closed, to: gone}") \
        .replace("{children: parent, any: [doing, done], to: underway}", "{children: epic_of, any: doing, to: underway}")
    bad = bad.replace("  ticket:\n", "  other:\n    id: other/*\n    states: [a]\n    join: {children: parent, all: done}\n  ticket:\n")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(bad))
    _, problems = read(tmp_path / "ergostat.yaml")
    said = "\n".join(x.message for x in problems if x.level == "error")
    assert "no kind names epic by a relation 'epic_of'" in said
    assert "'gone' is not a state of epic" in said
    assert "children: (a relation), all: or any:" in said
