"""Projections overlap (SPEC §5a): an event has no projection; a projection is a way of looking at a set of events.
Every projection whose glob matches an id folds that id's events, by its own rules, into its own table of the item
index: two identical definitions under two names, a copy with one more field, two projections reading different
fields of the same events differently. Each is counted, measured, queried and shown as its own."""

from __future__ import annotations

import random
import sqlite3
import textwrap

import pytest

from ergostat import model as mdl
from ergostat.leases import TAKEN
from ergostat.rollup import compact
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.store import Project
from ergostat.web.server import Live, api
from tests.test_sql_source import raw, rows

T0 = 1_700_000_000.0

MODEL = """
    name: overlap
    projections:
      ticket:                         # the first
        match:
          key: ticket/*
        states: [open, doing, done]
        events:
          ticket.started:
            state: set('doing')
          ticket.done:
            state: set('done')
        otherwise: rest
        show: [title, hours]
      twin:                           # the same, under another name
        match:
          key: ticket/*
        states: [open, doing, done]
        events:
          ticket.started:
            state: set('doing')
          ticket.done:
            state: set('done')
        otherwise: rest
        show: [title, hours]
      summed:                         # a copy with one more field: hours summed, not replaced
        match:
          key: ticket/*
        states: [open, doing, done]
        events:
          "*":
            hours: add(data.hours)
          ticket.started:
            state: set('doing')
          ticket.done:
            state: set('done')
        otherwise: rest
        show: [title, hours]
      effort:                         # the same events read otherwise: other fields, other rules, other states
        match:
          key: ticket/*
        states: [unworked, worked]
        events:
          "*":
            hours: max(data.hours)
            titles: append(data.titles)
          ticket.started:
            state: set('worked')
        otherwise: rest
        show: [hours, titles]
    stocks:
      open-tickets: {unit: tickets, sensor: {projection: ticket, state: open, every: 1m}}
      worked: {unit: tickets, sensor: {projection: effort, state: worked, every: 1m}}
"""


def project(tmp_path, text: str = MODEL) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(text))
    m = mdl.load(tmp_path)
    assert m.spec is not None, [str(x) for x in getattr(m, "problems", [])]
    return Project(m)


def seed(p) -> None:
    ev = p.events
    ev.add("ticket.opened", item="ticket/1", data={"title": "one", "hours": 2, "titles": "one"}, at=T0)
    ev.add("ticket.logged", item="ticket/1", data={"hours": 3, "titles": "uno"}, at=T0 + 10)
    ev.add("ticket.started", item="ticket/1", at=T0 + 20)
    ev.add("ticket.opened", item="ticket/2", data={"title": "two", "hours": 5}, at=T0 + 30)
    ev.add("ticket.opened", item="ticket/3", data={"title": "three", "hours": 1}, at=T0 + 40)
    ev.add("ticket.started", item="ticket/3", at=T0 + 50)
    ev.add("ticket.done", item="ticket/3", at=T0 + 60)
    ev.add("note.made", item="note/1", data={"title": "seen by none"}, at=T0 + 70)


def by(items) -> dict[tuple, its.Item]:
    return {(i.kind, i.id): i for i in items}


@pytest.fixture
def p(tmp_path):
    p = project(tmp_path)
    seed(p)
    return p


def test_every_projection_that_matches_an_id_has_an_item_of_it(p):
    spec = p.model.spec
    assert [k.name for k in its.projections_of(spec, "ticket/1")] == ["ticket", "twin", "summed", "effort"]
    got = by(its.project(p.events, spec))
    for k in ("ticket", "twin", "summed", "effort"):
        assert {i for kk, i in got if kk == k} == {"ticket/1", "ticket/2", "ticket/3"}, k
    assert (None, "note/1") in got                                   # an id no projection matches: of none
    one, twin = got[("ticket", "ticket/1")], got[("twin", "ticket/1")]
    assert (one.state, one.fields, one.n) == (twin.state, twin.fields, twin.n) == ("doing", one.fields, 3)
    assert one.fields == {"title": "one", "hours": 3, "titles": "uno"}
    assert got[("summed", "ticket/1")].fields["hours"] == 5           # one more field's rule: the same events, summed
    e = got[("effort", "ticket/1")]
    assert (e.state, e.fields["hours"], e.fields["titles"]) == ("worked", 3, ["one", "uno"])
    assert got[("effort", "ticket/3")].state == "worked"             # done is no state of effort's: it stays worked
    assert got[("ticket", "ticket/3")].state == "done"


def test_each_projection_is_counted_and_listed_as_its_own(p):
    spec = p.model.spec
    got = its.listing(p.events, spec)
    counts = {k["name"]: k["counts"] for k in got["projections"]}
    assert counts["ticket"] == counts["twin"] == counts["summed"] == {"open": 1, "doing": 1, "done": 1}
    assert counts["effort"] == {"unworked": 1, "worked": 2}
    assert got["unprojected"] == 1
    assert sorted((i["projection"], i["id"]) for i in got["items"] if i["id"] == "ticket/1") == [
        ("effort", "ticket/1"), ("summed", "ticket/1"), ("ticket", "ticket/1"), ("twin", "ticket/1")]
    assert its.in_states(p.events, spec, "twin", ["open"])[0] == 1
    assert its.in_states(p.events, spec, "effort", ["worked"])[0] == 2
    page = its.kind_page(p.events, spec, "summed", sort="-hours")
    assert [(i.id, i.fields["hours"]) for i in page["items"]] == [("ticket/2", 5), ("ticket/1", 5), ("ticket/3", 1)]


def test_a_sensor_counts_its_own_projection(p):
    spec = p.model.spec
    now = T0 + 100
    (s,) = spec.stocks["open-tickets"].sensors.values()
    (w,) = spec.stocks["worked"].sensors.values()
    assert its.measure(p.events, spec, s, now=now)[0] == 1.0          # ticket/2, open as ticket's
    assert its.measure(p.events, spec, w, now=now)[0] == 2.0          # ticket/1 and ticket/3, worked as effort's


def test_each_projection_has_its_own_table_and_view(p):
    ix = itemindex.index_for(p.events, p.model.spec, False)
    with sqlite3.connect(ix.path) as c:
        tables = {r[0] for r in c.execute("select name from sqlite_master where type = 'table'")}
        assert {"items/ticket", "items/twin", "items/summed", "items/effort", "unprojected"} <= tables
        assert c.execute('select count(*) from "items/summed"').fetchone()[0] == 3
        assert c.execute("select count(*) from unprojected").fetchone()[0] == 1
        assert c.execute("select count(*) from items").fetchone()[0] == 13      # the view of them all: 4 × 3 and 1
    assert rows(p, "select id, hours from summed order by id") == [["ticket/1", 5], ["ticket/2", 5], ["ticket/3", 1]]
    assert rows(p, "select id, hours from ticket order by id") == [["ticket/1", 3], ["ticket/2", 5], ["ticket/3", 1]]
    assert raw(p, "select id, state from effort order by id")[1] == [
        ("ticket/1", "worked"), ("ticket/2", "unworked"), ("ticket/3", "worked")]
    assert rows(p, "select projection, count(*) from item_list where id = 'ticket/1' group by 1 order by 1") == [
        ["effort", 1], ["summed", 1], ["ticket", 1], ["twin", 1]]
    _, got = raw(p, "select projection, value from item_fields where id = 'ticket/1' and field = 'hours' order by 1")
    assert got == [("effort", 3), ("summed", 5), ("ticket", 3), ("twin", 3)]
    _, moved = raw(p, "select projection, to_state from transitions where id = 'ticket/3' order by projection, at")
    assert moved == [("effort", "unworked"), ("effort", "worked"), ("summed", "open"), ("summed", "doing"),
                     ("summed", "done"), ("ticket", "open"), ("ticket", "doing"), ("ticket", "done"),
                     ("twin", "open"), ("twin", "doing"), ("twin", "done")]


def test_an_items_page_is_one_projections_and_the_id_alone_lists_them(p):
    live = Live(p)
    d = api(live, "items/ticket%2F1", {"projection": ["summed"]})
    assert d["projection"] == "summed" and d["fields"]["hours"] == 5
    assert d["projections"] == ["ticket", "twin", "summed", "effort"]
    e = api(live, "items/ticket%2F1", {"projection": ["effort"]})
    assert e["state"] == "worked" and e["projection_of"]["name"] == "effort"
    first = api(live, "items/ticket%2F1", {})                           # the id alone: the first, and all it is seen by
    assert first["projection"] == "ticket" and len(first["projections"]) == 4
    assert its.detail(p.events, p.model.spec, "ticket/1", kind="nope") is None     # a projection that does not see it
    assert its.one(p.events, p.model.spec, "ticket/1", "summed").fields["hours"] == 5


def test_a_lease_is_on_one_projections_item(p):
    spec = p.model.spec
    p.events.add(TAKEN, item="ticket/2", source="ergostat",
                 data={"projection": "twin", "run": "r1", "block": "b", "fence": 1, "ttl": 600, "back": "open"}, at=T0 + 80)
    got = by(its.project(p.events, spec))
    assert got[("twin", "ticket/2")].state == "leased" and got[("twin", "ticket/2")].fields["lease"]["holder"] == "r1"
    assert got[("ticket", "ticket/2")].state == "open" and "lease" not in got[("ticket", "ticket/2")].fields


def test_the_index_followed_is_a_fold_of_the_record_rebuilt_and_rolled_up(tmp_path):
    p = project(tmp_path)
    r = random.Random(11)
    evs = []
    for i in range(120):
        t = T0 + i * 30
        item = f"ticket/{r.randrange(25)}"
        typ = r.choice(["ticket.opened", "ticket.logged", "ticket.started", "ticket.done"])
        evs.append({"id": f"e{i}", "type": typ, "item": item, "at": t, "source": "test",
                    "data": {"hours": r.randrange(1, 9), "titles": r.choice("abc")}})
    fresh = lambda: by(its.fold_all(p.events, p.model.spec, None, None, False))   # noqa: E731
    seen = lambda: {k: i.as_dict(moves=True) for k, i in by(its.project(p.events, p.model.spec)).items()}  # noqa: E731
    want = lambda: {k: i.as_dict(moves=True) for k, i in fresh().items()}  # noqa: E731
    p.events.add_many(evs[:60])
    assert seen() == want()                                           # built from the record
    p.events.add_many(evs[60:])
    assert seen() == want()                                           # followed: only what is new folded
    before = want()
    assert len({k for k, _ in before}) == 4
    itemindex.reindex(p.events, p.model.spec)
    assert seen() == before                                           # built again from the record
    compact(p, now=T0 + 120 * 30 + p.storage.rollup_after + 1)        # every id rolled up: a snapshot per projection
    snaps = [e for e in p.events.query(n=None, type=its.SNAPSHOT) if e["item"].startswith("ticket/")]
    assert snaps and all(set(e["data"]["rollup"]["projections"]) == {"twin", "summed", "effort"} for e in snaps)
    assert want() == before and seen() == before


def test_a_join_and_a_reopening_naming_a_projection_move_only_its_item(p):
    spec = p.model.spec
    p.events.add(its.REOPENED, item="ticket/3", source="owner", data={"reopened": {"projection": "summed", "to": "open"}},
                 at=T0 + 90)
    got = by(its.project(p.events, spec))
    assert got[("summed", "ticket/3")].state == "open" and got[("ticket", "ticket/3")].state == "done"
    p.events.add(its.REOPENED, item="ticket/3", source="owner", data={"reopened": {"to": "open"}}, at=T0 + 95)
    got = by(its.project(p.events, spec))                             # naming none: each projection that sees it
    assert got[("ticket", "ticket/3")].state == got[("twin", "ticket/3")].state == "open"


def test_a_recorded_event_a_projection_refused_says_which(p):
    spec = p.model.spec
    ev = p.events.add("ticket.logged", item="ticket/2", data={"hours": "many"}, at=T0 + 99)
    why = its.refused_by(p.events, spec, ev)
    assert why is not None and why.startswith("summed: ")             # sum takes a number; replace took it
    assert its.one(p.events, spec, "ticket/2", "ticket").fields["hours"] == "many"

