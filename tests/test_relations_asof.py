"""The Items page's Graph and Timeline at a moment travelled to (SPEC §5a, *Relations*; ``spec/asof.py``): items,
their states, segments and links as they stood then, read per item while few changed since, else from the whole
record folded to then; and what each kind's stays were by then."""

from __future__ import annotations

import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import precedence as pr
from ergostat.spec import asof
from ergostat.spec import items as its
from ergostat.spec.itemindex import Index, index_for
from ergostat.store import Project

T0 = 1_700_000_000.0
U = T0 + 1000.0                       # the moment travelled to

MODEL = """
items:
  epic:
    id: epic/*
    states: [planned, underway, shipped]
    on: {epic.started: underway, epic.shipped: shipped}
    relations:
      after: epic
  ticket:
    id: ticket/*
    states: [todo, doing, done]
    on: {ticket.started: doing, ticket.done: done}
    relations:
      blocked_by: ticket
      parent: epic
messages:
  done: {ticket: [done], epic: [shipped]}
"""
OPEN = ["todo", "doing"]


def project(tmp_path) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def by_id(g) -> dict:
    return {x["id"]: x for x in g["items"]}


def views(monkeypatch) -> list:
    """Every ``AsOf`` a build makes, kept to look at."""
    got, real = [], asof.AsOf.__init__

    def init(self, *a, **k):
        real(self, *a, **k)
        got.append(self)
    monkeypatch.setattr(asof.AsOf, "__init__", init)
    return got


def seed_before(ev) -> None:
    ev.add("epic.planned", item="epic/e", at=T0)
    ev.add("ticket.planned", item="ticket/a", at=T0 + 1)
    ev.add("ticket.planned", item="ticket/b", data={"blocked_by": "ticket/a", "parent": "epic/e"}, at=T0 + 2)
    ev.add("ticket.planned", item="ticket/x", data={"title": "x as it was"}, at=T0 + 3)
    ev.add("ticket.started", item="ticket/a", at=U)                       # exactly at the moment: it counts


def test_the_graph_at_a_moment_shows_items_and_links_as_they_stood(tmp_path):
    p = project(tmp_path)
    ev, spec = p.events, p.model.spec
    seed_before(ev)
    ev.add("ticket.planned", item="ticket/y", data={"blocked_by": "ticket/b"}, at=U)   # made at U, nothing since: a row
    ev.add("ticket.relinked", item="ticket/b", data={"blocked_by": {"set": ["ticket/c"]}}, at=U + 5)
    ev.add("ticket.planned", item="ticket/c", at=U + 6)
    ev.add("ticket.done", item="ticket/a", at=U + 7)
    ev.add("ticket.planned", item="ticket/d", data={"blocked_by": "ticket/a"}, at=U + 8)
    ev.add("ticket.planned", item="ticket/x", set={"title": "x made again", "blocked_by": ["ticket/d"]}, at=U + 9)
    g = pr.build(ev, spec, ["ticket", "epic"], U, T0 - 10, until=U)
    by = by_id(g)
    assert set(by) == {"ticket/a", "ticket/b", "ticket/x", "ticket/y", "epic/e"}    # no c, no d: made after
    assert (by["ticket/a"]["state"], by["ticket/a"]["status"]) == ("doing", "active")
    assert by["ticket/b"]["status"] == "blocked" and by["ticket/b"]["waiting"] == ["ticket/a"]
    assert by["ticket/b"]["links"] == {"blocked_by": ["ticket/a"], "parent": ["epic/e"]}
    assert by["ticket/b"]["inverse"] == {"blocks": ["ticket/y"]} and by["ticket/y"]["status"] == "blocked"
    assert by["ticket/a"]["inverse"] == {"blocks": ["ticket/b"]}
    assert by["epic/e"]["inverse"] == {"children": ["ticket/b"]}
    assert by["ticket/x"]["title"] == "x as it was" and by["ticket/x"]["links"] == {}     # its earlier self
    assert all(s[2] <= U for x in g["items"] for s in x["segments"])
    assert by["ticket/a"]["segments"] == [["todo", T0 + 1, U]]                # into doing at U: no time there yet
    assert by["ticket/b"]["segments"] == [["todo", T0 + 2, U]]
    # the count, as of then: a, b, x and y open (a doing at U); now b, c, d, x (remade) and y
    ix = index_for(ev, spec, False)
    with ix.lock:
        view = asof.AsOf(ix, ev, spec, U)
        assert view.count("ticket", OPEN) == 4 and view.count("ticket", ["done"]) == 0
        assert ix.count("ticket", OPEN) == 5
        assert {i.id for i in view.items("ticket", ["doing"])} == {"ticket/a"}
    # the same through the page's answer
    from ergostat.web.relations_api import graph
    w = graph(p, p.model, {"at": U, "window": U - T0 + 10}, {"kinds": ["ticket,epic"]})
    wb = by_id(w)
    assert set(wb) == set(by) and wb["ticket/b"]["links"] == by["ticket/b"]["links"]
    assert wb["ticket/a"]["state"] == "doing" and wb["ticket/x"]["title"] == "x as it was"
    # and now, which differs
    n = by_id(pr.build(ev, spec, ["ticket", "epic"], U + 100, T0 - 10))
    assert n["ticket/b"]["links"]["blocked_by"] == ["ticket/c"] and n["ticket/a"]["status"] == "done"
    assert "ticket/d" in n and n["ticket/x"]["title"] == "x made again"


@pytest.mark.parametrize("op", ["items", "links_from", "links_to"])
def test_a_change_in_the_gap_between_the_index_read_and_the_late_read_is_seen(tmp_path, monkeypatch, op):
    p = project(tmp_path)
    ev, spec = p.events, p.model.spec
    seed_before(ev)
    ix = index_for(ev, spec, False)
    other = Index(ix.path, spec, False)               # another process's index on the same file
    fired, answered = [], []

    def between(self, at):
        if at == op and not fired:
            fired.append(at)
            ev.add("ticket.relinked", item="ticket/b", data={"blocked_by": {"set": ["ticket/c"]}}, at=U + 10)
            other.catch_up(ev)
            assert "ticket/b" in ix.late(U)            # the file this build reads holds it, changed after U
    monkeypatch.setattr(asof.AsOf, "_between", between)
    real = getattr(asof.AsOf, op)

    def read(self, *a, **k):                           # the answer of the read the write fell into
        got = real(self, *a, **k)
        if fired and not answered:
            answered.append((a, got))
        return got
    monkeypatch.setattr(asof.AsOf, op, read)
    try:
        g = pr.build(ev, spec, ["ticket"], U, T0 - 10, until=U)
    finally:
        other.close()
    assert fired == [op] and answered
    _, got = answered[0]
    if op == "items":
        assert [(i.state, i.fields.get("blocked_by")) for i in got if i.id == "ticket/b"] == [("todo", ["ticket/a"])]
    else:
        assert ("ticket/b", "blocked_by", "ticket/a") in got and ("ticket/b", "blocked_by", "ticket/c") not in got
    by = by_id(g)
    assert by["ticket/b"]["state"] == "todo" and by["ticket/b"]["links"]["blocked_by"] == ["ticket/a"]
    assert by["ticket/a"]["inverse"]["blocks"] == ["ticket/b"]


def _same(g) -> dict:
    """An answer with its lists in one order (the order links are read in is the index's or the fold's)."""
    out = {k: v for k, v in g.items() if k not in ("items", "edges")}
    out["edges"] = sorted(g["edges"], key=lambda e: (e["from"], e["to"], e["rel"]))
    out["items"] = sorted(({**x, "links": {r: sorted(v) for r, v in x["links"].items()},
                            "inverse": {r: sorted(v) for r, v in x["inverse"].items()}} for x in g["items"]),
                          key=lambda x: x["id"])
    return out


def seed_busy(ev) -> None:
    """A chain under an epic, half of it changed after U: moved on, relinked, finished; one made after."""
    ev.add("epic.planned", item="epic/e", at=T0)
    for i in range(6):
        ev.add("ticket.planned", item=f"ticket/{i}", data={"parent": "epic/e", **({"blocked_by": f"ticket/{i - 1}"} if i else {})},
               at=T0 + 10 + i)
    for i in range(3):
        ev.add("ticket.started", item=f"ticket/{i}", at=T0 + 100 + i * 100)
        ev.add("ticket.done", item=f"ticket/{i}", at=T0 + 150 + i * 100)
    ev.add("ticket.started", item="ticket/3", at=T0 + 500)
    ev.add("ticket.done", item="ticket/3", at=U + 10)
    ev.add("ticket.started", item="ticket/4", at=U + 20)
    ev.add("ticket.relinked", item="ticket/5", data={"blocked_by": {"set": ["ticket/9"]}}, at=U + 30)
    ev.add("ticket.planned", item="ticket/9", data={"parent": "epic/e"}, at=U + 40)
    ev.add("epic.started", item="epic/e", at=U + 50)


def test_the_whole_fold_when_most_items_changed_agrees_with_the_per_item_read(tmp_path, monkeypatch):
    p = project(tmp_path)
    ev, spec = p.events, p.model.spec
    seed_busy(ev)
    made = views(monkeypatch)
    monkeypatch.setattr(its, "late_cap", lambda ix, kind=None: 10**6)
    one = pr.build(ev, spec, ["ticket", "epic"], U, T0 - 10, until=U)
    (v1,) = made
    one_up = pr.build(ev, spec, ["epic"], U, T0 - 10, until=U)      # the tickets reached from the epic (links_to)
    assert v1.whole is None and {"ticket/3", "ticket/4", "ticket/5", "epic/e"} <= set(v1.folded)
    assert "ticket/9" in v1.late_ids and "ticket/9" not in v1.folded          # late, and not there at U
    ix = index_for(ev, spec, False)
    with ix.lock:
        n1 = asof.AsOf(ix, ev, spec, U).count("ticket", OPEN)
    # the whole mode: past the cap at once, and the index's rows never read after the first late read
    monkeypatch.setattr(its, "late_cap", lambda ix, kind=None: 0)
    late_read, real_late = [], Index.late
    monkeypatch.setattr(Index, "late", lambda self, *a, **k: late_read.append(1) or real_late(self, *a, **k))
    for name in ("items", "count", "links_from", "links_to"):
        real = getattr(Index, name)

        def guard(self, *a, _real=real, _name=name, **k):
            if late_read:
                raise AssertionError(f"Index.{_name} read in the whole mode")
            return _real(self, *a, **k)
        monkeypatch.setattr(Index, name, guard)
    two = pr.build(ev, spec, ["ticket", "epic"], U, T0 - 10, until=U)
    v2 = made[-1]
    assert v2 is not v1 and v2.whole is not None and "ticket/9" not in v2.whole
    two_up = pr.build(ev, spec, ["epic"], U, T0 - 10, until=U)
    with ix.lock:
        n2 = asof.AsOf(ix, ev, spec, U).count("ticket", OPEN)
    assert _same(one) == _same(two)
    assert _same(one_up) == _same(two_up) and len(one_up["items"]) == 7       # the epic and its six tickets
    assert n1 == n2 == 3                                     # 3, 4 and 5 open at U
    by = by_id(two)
    assert by["ticket/3"]["state"] == "doing" and by["ticket/5"]["links"]["blocked_by"] == ["ticket/4"]
    assert by["epic/e"]["state"] == "planned" and "ticket/9" not in by


@pytest.mark.parametrize("mode", ["per_item", "whole"])
def test_an_item_of_no_kind_changed_since_has_no_links_and_the_rest_answers(tmp_path, monkeypatch, mode):
    p = project(tmp_path)
    ev, spec = p.events, p.model.spec
    ev.add("misc.made", item="misc/1", data={"blocked_by": "ticket/a"}, at=T0)
    ev.add("ticket.planned", item="ticket/a", data={"blocked_by": "misc/1"}, at=T0 + 1)
    ev.add("ticket.planned", item="ticket/z", at=T0 + 2)
    ev.add("misc.changed", item="misc/1", data={"blocked_by": "ticket/z"}, at=U + 5)
    made = views(monkeypatch)
    if mode == "whole":
        monkeypatch.setattr(its, "late_cap", lambda ix, kind=None: 0)
    g = pr.build(ev, spec, ["ticket"], U, T0 - 10, until=U)
    assert (made[0].whole is not None) == (mode == "whole")
    assert mode == "whole" or "misc/1" in made[0].folded
    by = by_id(g)
    m = by["misc/1"]
    assert m["kind"] is None and m["links"] == {} and m["status"] == "ready"
    assert by["ticket/a"]["links"] == {"blocked_by": ["misc/1"]} and by["ticket/a"]["inverse"] == {}
    assert by["ticket/a"]["status"] == "blocked" and by["ticket/a"]["waiting"] == ["misc/1"]
    assert by["ticket/z"]["status"] == "ready" and by["ticket/z"]["inverse"] == {}
    view = made[0]                                          # and the view itself gives it none, either way
    with view.lock:
        assert view.links_from(["misc/1"]) == [] and view.links_to(["ticket/a"]) == []
        assert view.links_from(["ticket/a"]) == [("ticket/a", "blocked_by", "misc/1")]


def test_stays_at_a_moment_count_only_the_moves_by_then(tmp_path):
    p = project(tmp_path)
    ev, spec = p.events, p.model.spec
    for i in range(4):                                   # before: 100 s doing
        ev.add("ticket.planned", item=f"ticket/s{i}", at=T0 + i)
        ev.add("ticket.started", item=f"ticket/s{i}", at=T0 + 10 + i)
        ev.add("ticket.done", item=f"ticket/s{i}", at=T0 + 110 + i)
    for i in range(4):                                   # after: 1000 s doing
        ev.add("ticket.planned", item=f"ticket/l{i}", at=U + 1 + i)
        ev.add("ticket.started", item=f"ticket/l{i}", at=U + 10 + i)
        ev.add("ticket.done", item=f"ticket/l{i}", at=U + 1010 + i)
    ev.add("ticket.planned", item="ticket/w", at=T0 + 50)       # still doing at U, done since
    ev.add("ticket.started", item="ticket/w", at=T0 + 60)
    ev.add("ticket.done", item="ticket/w", at=U + 500)
    ev.add("ticket.planned", item="ticket/u", at=U - 30)        # its move at U counts: its todo ended then
    ev.add("ticket.started", item="ticket/u", at=U)
    ix = index_for(ev, spec, False)
    stays, visits, n = ix.stays("ticket", finished=["done"], until=U)
    assert stays["doing"] == [100.0] * 4
    assert sorted(stays["todo"]) == [10.0] * 5 + [30.0]
    assert n == 4 and visits == {"todo": 4, "doing": 4}         # w was not finished then; nor u
    now_stays, now_visits, now_n = ix.stays("ticket", finished=["done"])
    assert sorted(now_stays["doing"]) == [100.0] * 4 + [1000.0] * 4 + [U + 500 - T0 - 60]
    assert now_n == 9 and now_visits["doing"] == 9
    few = ix.stays("ticket", most=2, finished=["done"], until=U)      # the latest moves by then: u's, s3's
    assert sorted(few[0]["todo"]) == [10.0, 30.0] and few[0]["doing"] == [100.0] and few[2] == 1


def test_the_graph_now_does_not_build_a_view(tmp_path, monkeypatch):
    p = project(tmp_path)
    ev, spec = p.events, p.model.spec
    t = time.time()
    ev.add("ticket.planned", item="ticket/a", at=t - 20)
    ev.add("ticket.planned", item="ticket/b", data={"blocked_by": "ticket/a"}, at=t - 10)
    before = pr.build(ev, spec, ["ticket"], t, t - 3600)

    def refuse(self, *a, **k):
        raise AssertionError("a view built for now")
    monkeypatch.setattr(asof.AsOf, "__init__", refuse)
    from ergostat.web.relations_api import graph
    w = graph(p, p.model, {"at": time.time(), "window": 3600}, {"kinds": ["ticket"]})
    assert by_id(w)["ticket/b"]["status"] == "blocked" and by_id(w)["ticket/b"]["links"] == {"blocked_by": ["ticket/a"]}
    assert pr.build(ev, spec, ["ticket"], t, t - 3600, until=None) == before
    with pytest.raises(AssertionError):                    # (the guard is live: a moment does build one)
        pr.build(ev, spec, ["ticket"], t, t - 3600, until=t - 15)
