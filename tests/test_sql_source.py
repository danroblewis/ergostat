"""Acceptance (sql-source-over-item-views): the ``sql`` data source answers SELECTs over the stable, read-only item views
(ergostat/datasources/sql.py, _itemviews.py), through the real query API, on a hand-worked record of five tickets.

Done 1: writes, ATTACH, PRAGMA and the index's own tables are refused. Done 2: a runaway query is stopped at its time
limit (and the row, byte, value and median bounds hold). Done 3: the views answer the same after the index's layout
changes. Done 4: exact medians and percentiles match the record worked by hand below."""

from __future__ import annotations

import base64
import json
import sqlite3
import textwrap
import time

import pytest

from ergostat import datasources
from ergostat import model as mdl
from ergostat.datasources import _itemviews, sql
from ergostat.spec import itemindex
from ergostat.store import Project
from ergostat.web.server import Live, api

T = 1_795_400_400.0

# The record, worked by hand (each ticket: when it arrived, then its moves, seconds after T):
#   ticket/1  open 0,  doing 10,                       done 40     doing 30
#   ticket/2  open 0,  doing 20, open 30, doing 50,    done 120    doing 10 (entry 1) and 70 (entry 2)
#   ticket/3  open 5,  doing 15,                       done 65     doing 50
#   ticket/4  open 5,  doing 25,                       dropped 45  doing 20
#   ticket/5  open 10, doing 100                       (still doing: its span is open, its reason null)
# Closed doing spans: 10 20 30 50 70, so their median is 30, and their 90th percentile, at 0.9 * 4 = 3.6 of the way
# through them, is 50 + 0.6 * (70 - 50) = 62. First entries only: 10 20 30 50, an even count, so the median is
# (20 + 30) / 2 = 25. Doing time per finished item: 30, 80, 50, 20, median (30 + 50) / 2 = 40. Arrival to done (the
# reason done): 40, 120, 60, median 60.
EVENTS = [
    ("ticket/1", "ticket.opened", 0, {"owner": "ana", "size": 3}), ("ticket/1", "ticket.started", 10, {}),
    ("ticket/1", "ticket.done", 40, {}),
    ("ticket/2", "ticket.opened", 0, {"owner": "bo", "size": 5}), ("ticket/2", "ticket.started", 20, {}),
    ("ticket/2", "ticket.back", 30, {}), ("ticket/2", "ticket.started", 50, {}), ("ticket/2", "ticket.done", 120, {}),
    ("ticket/3", "ticket.opened", 5, {"owner": "ana", "size": 1}), ("ticket/3", "ticket.started", 15, {}),
    ("ticket/3", "ticket.done", 65, {}),
    ("ticket/4", "ticket.opened", 5, {"owner": "cy", "size": 2}), ("ticket/4", "ticket.started", 25, {}),
    ("ticket/4", "ticket.dropped", 45, {}),
    ("ticket/5", "ticket.opened", 10, {"owner": "bo", "size": 8}), ("ticket/5", "ticket.started", 100, {}),
]
SPANS = [                                   # item_spans, as worked by hand: (id, state, entered, left, entry, reason)
    ("ticket/1", "open", 0, 10, 1, "done"), ("ticket/1", "doing", 10, 40, 1, "done"),
    ("ticket/1", "done", 40, None, 1, "done"),
    ("ticket/2", "open", 0, 20, 1, "done"), ("ticket/2", "doing", 20, 30, 1, "done"), ("ticket/2", "open", 30, 50, 2, "done"),
    ("ticket/2", "doing", 50, 120, 2, "done"), ("ticket/2", "done", 120, None, 1, "done"),
    ("ticket/3", "open", 5, 15, 1, "done"), ("ticket/3", "doing", 15, 65, 1, "done"), ("ticket/3", "done", 65, None, 1, "done"),
    ("ticket/4", "open", 5, 25, 1, "dropped"), ("ticket/4", "doing", 25, 45, 1, "dropped"),
    ("ticket/4", "dropped", 45, None, 1, "dropped"),
    ("ticket/5", "open", 10, 100, 1, None), ("ticket/5", "doing", 100, None, 1, None),
]


@pytest.fixture
def p(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: sq
        stocks:
          queue: {unit: tickets}
        items:
          ticket:
            id: ticket/*
            states: [open, doing, done, dropped]
            on: {ticket.started: doing, ticket.back: open, ticket.done: done, ticket.dropped: dropped}
            show: [owner, size]
        sources:
          record: {type: sql}
        """))
    p = Project(mdl.load(tmp_path))
    for item, type_, at, data in EVENTS:
        p.events.add(type_, item=item, data=data, at=T + at)
    return p


def ask(p, text: str) -> dict:
    body = {"since": 3600.0, "until": T + 3600, "points": 4, "queries": [{"id": "a", "source": "record", "text": text}]}
    q = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    [r] = api(Live(p), "query", {"q": [q]})["results"]
    return r


def rows(p, text: str) -> list[list]:
    r = ask(p, text)
    assert "error" not in r, r
    assert r["shape"] == "table", r
    return r["rows"]


def index_file(p):
    return itemindex.index_for(p.events, p.model.spec, False).path


def test_writes_attach_pragma_and_the_index_s_own_tables_are_refused(p):
    assert rows(p, "select kind, count(*) as n from transitions group by kind") == [["ticket", 16]]
    before = sqlite3.connect(index_file(p)).execute("select count(*) from moves").fetchone()
    for text in [
        "insert into transitions(id) values ('x')", "delete from item_spans", "update item_fields set value = 1",
        "replace into transitions(id) values ('x')", "create table x(a)", "create temp view v as select 1 as n",
        "drop view transitions", "alter table transitions rename to t", "attach database ':memory:' as x",
        "detach database temp", "pragma table_info(items)", "pragma query_only = 0", "pragma writable_schema = 1",
        "vacuum", "begin", "analyze", "reindex", "savepoint s",
        "select * from items", "select count(*) from main.items", "select * from moves", "select rid from main.moves",
        "select * from names", "select * from links", "select * from meta", "select * from numbers",
        "select * from sqlite_master", "select * from sqlite_temp_master", "select * from temp.sqlite_master",
        "select * from pragma_table_info('items')", "select name, 1 as n from pragma_table_list",
        "with x as (select * from main.items) select count(*) as n from x",
        "select count(*) as n from transitions where id in (select id from main.items)",
        "select _fields(body), 1 as n from main.items", "select load_extension('x') as n", "select 1 as n; delete from moves",
    ]:
        r = ask(p, text)
        assert r.get("error_kind") == "refused", (text, r)
    assert sqlite3.connect(index_file(p)).execute("select count(*) from moves").fetchone() == before


def test_a_runaway_query_is_stopped_at_its_time_limit(p, monkeypatch):
    monkeypatch.setattr(datasources, "MOST_SECONDS", 1.0)
    for text in ["with recursive r(n) as (select 1 union all select n + 1 from r) select count(*) as n from r",
                 "select count(*) as n from transitions a, transitions b, transitions c, transitions d, transitions e, "
                 "transitions f, transitions g"]:
        t0 = time.monotonic()
        r = ask(p, text)
        took = time.monotonic() - t0
        assert r.get("error_kind") == "limit" and "ran past 1 s" in r["error"], r
        assert took < 3.0, took


def test_rows_bytes_values_and_a_median_s_numbers_are_bounded(p, monkeypatch):
    r = ask(p, "with recursive r(n) as (select 1 union all select n + 1 from r limit 5001) select n, n * 2 as m from r")
    assert r.get("error_kind") == "limit" and "5000 rows" in r["error"], r
    assert len(rows(p, "with recursive r(n) as (select 1 union all select n + 1 from r limit 5000) select n, n as m from r")) == 5000
    r = ask(p, "with recursive s(n, x) as (select 1, 'x' union all select n + 1, x || x from s where n < 21), "
               "r(n) as (select 1 union all select n + 1 from r where n < 50) "
               "select (select x from s where n = 21) || r.n as s, r.n from r")
    assert r.get("error_kind") == "limit" and "8 MB" in r["error"], r
    r = ask(p, "with recursive r(n, s) as (select 1, 'x' union all select n + 1, s || s from r where n < 30) "
               "select max(length(s)) as n from r")
    assert r.get("error_kind") == "limit" and "16 MB" in r["error"], r
    monkeypatch.setattr(_itemviews, "MOST_VALUES", 10)
    r = ask(p, "with recursive r(n) as (select 1 union all select n + 1 from r limit 11) select median(n) as m from r")
    assert r.get("error_kind") == "limit" and "at most 10 numbers" in r["error"], r


def raw(p, text: str) -> tuple[list[str], list[tuple]]:
    """A query's columns and rows as SQLite answers them, on the views as a query sees them (no frame made)."""
    ix = sql._index(p, p.model.spec)
    with _itemviews.opened(ix, p.model.spec, time.monotonic() + 10) as (c, why):
        try:
            cur = c.execute(text)
        except sqlite3.Error as e:
            raise AssertionError((text, e, why)) from None
        return [d[0] for d in cur.description], cur.fetchall()


def test_a_query_s_connection_holds_its_memory_and_attaches_nothing(p):
    ix = sql._index(p, p.model.spec)
    with _itemviews.opened(ix, p.model.spec, time.monotonic() + 10) as (c, _):
        assert c.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) == 16 * 2**20 and c.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED) == 0
        c.set_authorizer(None)                                     # (only to read what was set)
        got = [c.execute(f"pragma {q}").fetchone()[0] for q in ("cache_size", "temp.cache_size", "temp_store",
                                                                "query_only")]
        assert got == [-8000, -8000, 1, 1]


def view_answers(p) -> dict:
    return {v: raw(p, f"select * from {v} order by " + ", ".join(f'"{c}"' for c in cols))
            for v, cols in _itemviews.views(p.model.spec).items()}


def test_the_views_answer_as_the_record_was_worked_by_hand(p):
    cols, got = raw(p, f'select id, state, entered - {T} as entered, "left" - {T} as "left", entry, reason '
                       "from item_spans order by id, entered, entry")
    assert got == [(i, s, float(e), None if lf is None else float(lf), n, why) for i, s, e, lf, n, why in SPANS]
    assert raw(p, "select * from item_spans")[0] == list(_itemviews.STABLE["item_spans"])
    assert raw(p, "select id, owner, size, state, events from ticket order by id")[1] == [
        ("ticket/1", "ana", 3, "done", 3), ("ticket/2", "bo", 5, "done", 5), ("ticket/3", "ana", 1, "done", 3),
        ("ticket/4", "cy", 2, "dropped", 3), ("ticket/5", "bo", 8, "doing", 2)]
    assert raw(p, "select field, value from item_fields where id = 'ticket/2' order by field")[1] == [
        ("owner", "bo"), ("size", 5)]
    assert rows(p, "select id, owner, state, size, events from ticket where state = 'done' order by id") == [
        ["ticket/1", "ana", "done", 3, 3], ["ticket/2", "bo", "done", 5, 5], ["ticket/3", "ana", "done", 1, 3]]
    assert rows(p, "select from_state, to_state, count(*) as n from transitions group by 1, 2 order by 1, 2") == [
        ["", "open", 5], ["doing", "done", 3], ["doing", "dropped", 1], ["doing", "open", 1], ["open", "doing", 6]]


def test_the_views_survive_an_index_layout_change(p, monkeypatch):
    before = view_answers(p)
    assert set(before) == {"transitions", "item_fields", "item_spans", "ticket"}
    assert {v: cols for v, (cols, _) in before.items()} == {
        "transitions": ["id", "kind", "at", "from_state", "to_state", "event", "type"],
        "item_fields": ["id", "kind", "field", "value"],
        "item_spans": ["id", "kind", "state", "entered", "left", "entry", "reason"],
        "ticket": ["id", "state", "first", "last", "entered", "events", "owner", "size"]}
    assert len(before["item_spans"][1]) == len(SPANS) and len(before["item_fields"][1]) == 10
    path = index_file(p)
    c = sqlite3.connect(path, isolation_level=None)               # another layout: columns reordered and added, a table
    c.executescript("""
        begin;
        create table items2 (body blob, extra text, text text, id text unique not null, raw_first real, raw integer,
            arrived real, latest integer, n integer, entered real, newest real, last real, first real, state integer,
            kind integer, rid integer primary key);
        insert into items2 (body, text, id, raw_first, raw, arrived, latest, n, entered, newest, last, first, state, kind,
            rid) select body, text, id, raw_first, raw, arrived, latest, n, entered, newest, last, first, state, kind, rid
            from items;
        drop table items;
        alter table items2 rename to items;
        alter table moves add column weight real;
        create table spans (rid integer, t real);
        commit;
        """)
    c.close()
    assert view_answers(p) == before
    monkeypatch.setattr(itemindex, "VERSION", itemindex.VERSION + 100)   # a new layout's file, built again from the record
    assert index_file(p) != path
    assert view_answers(p) == before


def test_a_query_joining_views_reads_one_state_of_the_index_while_it_is_caught_up_between_copies(p, monkeypatch):
    """A catch-up committed between two views' copies (another request's, or another process's) is seen by none."""
    definitions = _itemviews._definitions

    class Between(dict):
        def items(self):
            for view, select in super().items():
                if view == "ticket":                    # item_spans is copied; ticket/5 is done before ticket is
                    p.events.add("ticket.done", item="ticket/5", data={}, at=T + 200)
                    itemindex.index_for(p.events, p.model.spec, False)
                yield view, select

    monkeypatch.setattr(_itemviews, "_definitions", lambda spec, finished: Between(definitions(spec, finished)))
    got = rows(p, "select t.id, t.state, s.state as now, s.reason, count(*) as n from ticket t join item_spans s "
                  "on s.id = t.id and s.\"left\" is null where t.id = 'ticket/5' group by 1, 2, 3, 4")
    assert got == [["ticket/5", "doing", "doing", None, 1]]           # (a reason all null reads as a measure)
    monkeypatch.setattr(_itemviews, "_definitions", definitions)
    assert rows(p, "select t.id, t.state, s.state as now, s.reason, count(*) as n from ticket t join item_spans s "
                   "on s.id = t.id and s.\"left\" is null where t.id = 'ticket/5' group by 1, 2, 3, 4") == [
        ["ticket/5", "done", "done", "done", 1]]


def test_exact_medians_and_percentiles_match_the_hand_worked_record(p):
    closed = "from item_spans where state = 'doing' and \"left\" is not null"
    assert rows(p, f'select median("left" - entered) as m, percentile("left" - entered, 90) as p90, '
                   f'percentile_cont("left" - entered, 0.5) as c {closed}') == [["1", 30.0, 62.0, 30.0]]
    assert rows(p, f'select median("left" - entered) as m {closed} and entry = 1') == [["1", 25.0]]
    assert rows(p, 'select median(t) as m from (select id, sum("left" - entered) as t from item_spans '
                   "where state = 'doing' and reason is not null group by id)") == [["1", 40.0]]
    assert rows(p, "select reason, median(t) as m from (select id, reason, max(entered) - min(entered) as t "
                   "from item_spans where reason = 'done' group by id) group by reason") == [["done", 60.0]]
    assert rows(p, "select median(x) as m from (select 1 as x union all select null union all select 4)") == [["1", 2.5]]
    assert rows(p, "select median(x) as m from (select null as x)") == [["1", None]]
    r = ask(p, "select median(id) as m from item_spans")
    assert r.get("error_kind") == "refused" and "takes numbers" in r["error"], r
    r = ask(p, "select percentile(entry, 101) as m from item_spans")
    assert r.get("error_kind") == "refused" and "0 to 100" in r["error"], r


def test_an_answer_with_a_time_column_is_series_and_the_editor_is_offered_views_and_columns(p):
    r = ask(p, "select :until - :step as time, 1 as one")
    assert r["shape"] == "series" and r["series"][0]["name"] == "one" and 1.0 in r["series"][0]["values"], r
    r = ask(p, "select id, state from ticket")
    assert r.get("error_kind") == "refused" and "column of numbers" in r["error"], r
    got = datasources.suggest(p.model.spec, "record", "metrics", project=p)
    assert got == {"suggestions": ["item_fields", "item_spans", "ticket", "transitions"], "more": False}
    got = datasources.suggest(p.model.spec, "record", "labels", "", "item_spans", project=p)
    assert got["suggestions"] == sorted(_itemviews.STABLE["item_spans"])
    assert sql.LANGUAGE == "SQL" and datasources.types()["sql"] is sql
