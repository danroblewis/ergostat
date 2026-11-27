"""An item's numeric fields in the item index (spec/itemnumbers.py): what counts as a value, the table against a full
refold of the record for any way the events arrive, roll-ups, rebuilding, and reading a field without the record."""

from __future__ import annotations

import random
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.rollup import compact
from ergostat.spec import codec, itemindex, itemnumbers, numberreads
from ergostat.spec import items as its
from ergostat.store import Project

T0 = 1_790_000_000.0
KIND = """
    projections:
      ticket:
        query: key.startswith('ticket/')
        fields:
          state:
            type: one of [open, doing, done]
          ai_cost_usd: {fold: add}
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
    storage:
      events: segments
"""


def _project(tmp_path, extra=""):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(KIND) + extra)
    return Project(mdl.load(tmp_path))


def _events(r: random.Random, n: int) -> list[dict]:
    out, t = [], T0
    for i in range(n):
        t += r.choice((0.0, 1.0, 30.0))
        data = {}
        if r.random() < 0.6:
            data["ai_cost_usd"] = r.choice((0.5, 1.25, 2.0))
        if r.random() < 0.4:
            data["attempts"] = r.choice((1, 2, 3, "many", True))
        out.append({"id": f"e{i}", "at": t, "type": r.choice(("ticket.note", "ticket.started", "ticket.done")),
                    "item": f"ticket/{r.randrange(6)}", "source": "test", "causedby": None, "data": data})
    return out


def _table(ix) -> tuple[set, set]:
    with ix.lock:
        log = {(ix.name(k), ix.name(f), t, id, v, d) for k, f, t, id, v, d in ix.db.execute(
            "select n.kind, n.field, n.t, i.id, n.value, n.delta from number_log n join items i on i.rid = n.rid")}
        now = {(id, ix.name(f), v) for id, f, v in ix.db.execute(
            "select i.id, n.field, n.value from numbers n join items i on i.rid = n.rid")}
    return log, now


def _refold(p) -> tuple[set, set]:
    spec, by = p.model.spec, {}
    for e in p.events.of_items(None, skip=(its.TRANSCRIPT_TYPES,)):
        by.setdefault(e["item"], []).append(e)
    log, now = set(), set()
    for id, evs in by.items():
        for k in its.projections_of(spec, id):
            log |= {(k.name, f, t, id, v, d) for f, t, v, d in itemnumbers.history_of(id, evs, k, False)}
            now |= {(id, f, v) for f, v in itemnumbers.values(its.fold(id, evs, k, transcript=False).fields).items()}
    return log, now


@pytest.mark.parametrize("name,v,want", [
    ("ai_cost_usd", 1.5, True), ("attempts", 3, True), ("flag", True, False), ("attempts", "3", False),
    ("session_id", 42, False), ("loop_ended", T0, False), ("started_at", 12.0, False), ("anything", T0, False),
    ("nan", float("nan"), False), ("budget", 0, True)])
def test_what_is_a_value(name, v, want):
    assert itemnumbers.is_value(name, v) is want


def test_a_field_says_its_unit():
    assert [itemnumbers.unit_of(f) for f in ("ai_cost_usd", "loop_hours", "net_lines", "attempts")] == \
        ["usd", "hours", "lines", "count"]


@pytest.mark.parametrize("seed", range(12))
def test_the_table_is_a_full_refold_however_the_events_arrive(tmp_path, seed):
    r = random.Random(seed)
    p = _project(tmp_path)
    evs = _events(r, 120)
    at = 0
    while at < len(evs):                                      # in chunks of any size, read between them
        step = r.randint(1, 40)
        p.events.add_many(evs[at:at + step])
        at += step
        ix = itemindex.index_for(p.events, p.model.spec, False)
        assert _table(ix) == _refold(p)
    itemindex.reindex(p.events, p.model.spec)
    assert _table(itemindex.index_for(p.events, p.model.spec, False)) == _refold(p)


@pytest.mark.parametrize("seed", range(4))
def test_a_rolled_up_record_folds_to_the_same_numbers(tmp_path, seed):
    p = _project(tmp_path)
    evs = _events(random.Random(seed), 200)
    p.events.add_many(evs)
    before = _table(itemindex.index_for(p.events, p.model.spec, False))
    end = evs[-1]["at"]
    for frac in (0.4, 0.8):                                   # twice: a snapshot of a snapshot keeps them too
        compact(p, now=T0 + (end - T0) * frac + p.storage.rollup_after)
        assert _table(itemindex.index_for(p.events, p.model.spec, False)) == before
    itemindex.reindex(p.events, p.model.spec)
    assert _table(itemindex.index_for(p.events, p.model.spec, False)) == before


def test_a_cost_summed_by_its_fold_moves_by_each_amount(tmp_path):
    p = _project(tmp_path)
    for i, c in enumerate((1.0, 2.5, 0.5)):
        p.events.add("ticket.note", item="ticket/1", data={"ai_cost_usd": c}, at=T0 + i)
    ix = itemindex.index_for(p.events, p.model.spec, False)
    got = numberreads.changes(ix, "ticket", "ai_cost_usd", T0, T0 + 9)
    assert [(v, d) for _, _, v, d in got] == [(1.0, 1.0), (3.5, 2.5), (4.0, 0.5)]
    assert numberreads.fields_of(ix)["ticket"] == [{"field": "ai_cost_usd", "unit": "usd", "items": 1}]


def test_a_field_that_stops_being_a_number_leaves_the_current_values(tmp_path):
    p = _project(tmp_path)
    p.events.add("ticket.note", item="ticket/1", data={"attempts": 2}, at=T0)
    p.events.add("ticket.note", item="ticket/1", data={"attempts": "two"}, at=T0 + 1)
    ix = itemindex.index_for(p.events, p.model.spec, False)
    log, now = _table(ix)
    assert now == set() and ("ticket", "attempts", T0 + 1, "ticket/1", None, -2.0) in log


def test_an_item_of_no_kind_is_folded_and_keeps_no_numbers(tmp_path):
    p = _project(tmp_path)
    p.events.add("other.note", item="other/1", data={"attempts": 2}, at=T0)
    ix = itemindex.index_for(p.events, p.model.spec, False)
    assert ix.total() == 1 and _table(ix) == (set(), set())


def test_a_crash_part_way_resumes_to_the_same_table(tmp_path, monkeypatch):
    p = _project(tmp_path)
    evs = _events(random.Random(9), 150)
    p.events.add_many(evs[:60])
    ix = itemindex.index_for(p.events, p.model.spec, False)
    p.events.add_many(evs[60:])
    real, calls = itemindex.Index._keep_numbers, []

    def dies(self, *a):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("the process stopped here")
        return real(self, *a)
    monkeypatch.setattr(itemindex.Index, "_keep_numbers", dies)
    with pytest.raises(RuntimeError):
        ix.catch_up(p.events)
    monkeypatch.setattr(itemindex.Index, "_keep_numbers", real)
    ix.catch_up(p.events)
    assert _table(ix) == _refold(p)


def test_an_index_of_an_older_layout_is_rebuilt_with_its_numbers(tmp_path):
    p = _project(tmp_path)
    p.events.add_many(_events(random.Random(3), 60))
    ix = itemindex.index_for(p.events, p.model.spec, False)
    with ix.lock:
        ix.db.execute("delete from number_log")
        ix.db.execute("delete from numbers")
        ix.db.execute("update meta set value = 5 where key = 'version'")
    ix.seq = -1
    p.events.add("ticket.note", item="ticket/1", data={"attempts": 7}, at=T0 + 9999)
    ix.catch_up(p.events)
    assert _table(ix) == _refold(p)


def _sized(tmp_path, n: int, items: int, note: int):
    p = _project(tmp_path)
    r = random.Random(1)
    p.events.add_many([{"id": f"e{i}", "at": T0 + i * 20.0, "type": "ticket.note", "item": f"ticket/{r.randrange(items)}",
                        "source": "t", "causedby": None, "data": {"ai_cost_usd": 0.25, "note": "x" * note}}
                       for i in range(n)], new=True)
    return p, itemindex.index_for(p.events, p.model.spec, False)


@pytest.mark.serial
def test_a_field_over_a_window_reads_neither_the_record_nor_a_document(tmp_path, monkeypatch):
    p, ix = _sized(tmp_path, 40_000, 4000, 20)

    def no(*a, **k):
        raise AssertionError("a chart's read touched the record or a document")
    monkeypatch.setattr(codec, "unpack", no)
    monkeypatch.setattr(p.events, "of_items", no)
    monkeypatch.setattr(p.events, "query", no)
    took, n = min(_timed(lambda: numberreads.changes(ix, "ticket", "ai_cost_usd", T0 + 200_000, T0 + 286_400)) for _ in range(5))
    assert n == 4321 and took < 0.020


def test_the_numbers_add_at_most_half_to_the_index(tmp_path):
    _, ix = _sized(tmp_path, 3000, 400, 4000)              # (the factory: about 4 KB a document, 9 changes an item)
    with ix.lock:
        ix.db.execute("pragma wal_checkpoint(truncate)")
        ix.db.execute("vacuum")
        whole = _pages(ix)
        ix.db.execute("drop table number_log")
        ix.db.execute("drop table numbers")
        ix.db.execute("vacuum")
        assert whole <= _pages(ix) * 1.5


def _timed(f) -> tuple[float, int]:
    t = time.perf_counter()
    got = f()
    return time.perf_counter() - t, len(got)


def _pages(ix) -> int:
    return ix.db.execute("pragma page_count").fetchone()[0]
