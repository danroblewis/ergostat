"""Acceptance (a-read-only-sql-data-source): the ``sql`` source's views are real temp views over the item index, and a
query's text is checked first on an empty stand-in of the index (ergostat/datasources/_itemviews.py, ``check``); only a
text that passed there is run on the index, and the index's own authorizer still refuses reads outside the views'."""

from __future__ import annotations

import contextlib
import sqlite3
import time

import pytest

from ergostat import datasources
from ergostat.datasources import _itemviews
from tests import test_sql_source as base
from tests.test_sql_source import SPANS, T, ask, index_file, rows

p = base.p                                                          # (the record of five tickets, worked by hand)


@pytest.fixture
def spy(monkeypatch):
    """Each run on the index: its text, and what its connection's temp schema held after it."""
    real, ran = _itemviews.opened, []

    @contextlib.contextmanager
    def opened(*a):
        ran.append([a[3]])
        with real(*a) as (c, w):
            yield c, w
            c.set_authorizer(None)
            ran[-1].append(c.execute("select type, name from sqlite_temp_master").fetchall())
    monkeypatch.setattr(_itemviews, "opened", opened)
    return ran


def test_a_query_reads_real_views_and_copies_nothing(p, spy):
    got = rows(p, f'select id, state, cast(entry as text) as entry, reason, entered - {T} as entered, "left" - {T} '
                  'as "left" from item_spans order by id, entered, entry')
    assert got == [[i, s, str(n), why or "", e, lf] for i, s, e, lf, n, why in SPANS]
    [(text, temp)] = spy
    assert "item_spans" in text
    assert {t for t, _ in temp} == {"view"}, temp
    assert {n for _, n in temp} == {"transitions", "item_fields", "item_spans", "ticket"}


def test_a_name_only_the_index_has_is_refused_before_the_text_reaches_the_index(p, spy):
    texts = [f"select count(*) as n from {q}{name}" for q in ("", "main.")
             for name in ("items", "moves", "names", '"left"', "x", "sqlite_master", "pragma_table_info('items')",
                          "json_each('[1]')")]
    texts += ["select count(*) as n from main.transitions", "select count(*) as n from sqlite_temp_master",
              "select count(*) as n from temp.sqlite_master", "select count(*) as n from temp.sqlite_temp_master",
              "select _fields(body), 1 as n from items",
              "select _fields(x'00') as f, 1 as n", "select count(*) as n from transitions where id in (select id from items)"]
    for text in texts:
        r = ask(p, text)
        assert r.get("error_kind") == "refused", (text, r)
    assert spy == []                                                # (the index never ran any)
    assert rows(p, "select count(*) as n from temp.transitions") == [["1", 16]]
    assert rows(p, "with items as (select id from transitions) select count(*) as n from items") == [["1", 16]]
    assert len(spy) == 2


def test_a_check_that_fails_or_runs_out_of_time_does_not_run_the_query(p, spy, monkeypatch):
    def broken(spec):
        raise KeyError("broken")
    with monkeypatch.context() as m:
        m.setattr(_itemviews, "views", broken)
        r = ask(p, "select count(*) as n from transitions")
    assert r.get("error_kind") == "refused" and "could not be checked" in r["error"], r
    monkeypatch.setattr(datasources, "MOST_SECONDS", 1.0)
    monkeypatch.setattr(_itemviews, "_prepared", lambda deadline: lambda: int(time.monotonic() > deadline))
    t0 = time.monotonic()                                           # (the check run to the end, not only prepared)
    r = ask(p, "with recursive r(n) as (select 1 union all select n + 1 from r) select count(*) as n from r")
    assert r.get("error_kind") == "limit" and "ran past 1 s" in r["error"], r
    assert time.monotonic() - t0 < 3.0
    assert spy == []


def test_the_index_connection_refuses_a_read_outside_the_view_tables(p, spy, monkeypatch):
    c = sqlite3.connect(index_file(p))
    c.executescript("create table extra (a); insert into extra values (1);")
    c.close()
    monkeypatch.setattr(_itemviews, "check", lambda *a: None)       # (the check passed by force)
    for text in ["select count(*) as n from sqlite_master", "select count(*) as n from temp.sqlite_master",
                 "select count(*) as n from extra", "select count(*) as n from meta", "select count(*) as n from links",
                 "select count(*) as n from numbers", 'select count(*) as n from "left"', "select load_extension('x')"]:
        r = ask(p, text)
        assert r.get("error_kind") == "refused" and "only a SELECT of the views" in r["error"], (text, r)
    assert [len(r) for r in spy] == [1] * 8                         # (each was run on the index, and refused there)
    # What the check is for: the tables the views read are readable here, so on the index alone they would answer.
    assert rows(p, "select count(*) as n from main.items") == [["1", 5]]
