"""The item index (spec/itemindex.py): every item's fold kept on disk and followed as events arrive.
It must always equal a fresh fold of the record: for every example's kinds, with and without a
transcript's lines, as events arrive, after roll-ups and prunes, and when built again from the
record. Counting, paging and a flow's moves read it, and give what a fold of every item gives."""

from __future__ import annotations

import random
import textwrap

import pytest

from ergostat import model as mdl
from ergostat.rollup import compact, upkeep
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.store import Project
from tests.test_rollup import BACKENDS, EXAMPLES, T0, _fresh, _project, _record, _seen


def _indexed(p, transcript: bool) -> dict:
    return {i.id: _seen(i) for i in its.project(p.events, p.model.spec, transcript=transcript)}


def _cold(p) -> None:
    """As a process that starts: nothing of the index in memory."""
    for ix in list(itemindex._OPEN.values()):
        ix.close()
    itemindex._OPEN.clear()


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("example", [e for e in EXAMPLES if mdl.load(e).spec and mdl.load(e).spec.items], ids=lambda p: p.name)
def test_the_index_is_a_fresh_fold_as_events_arrive_and_after_rollups(tmp_path, example, backend):
    p = _project(tmp_path, example, backend)
    r = random.Random(example.name + "index")
    evs = _record(p.model.spec, r)
    half = len(evs) // 2
    p.events.add_many(evs[:half])
    for tr in (False, True):
        assert _indexed(p, tr) == _fresh(p, tr), tr           # built from the record
    p.events.add_many(evs[half:])
    for tr in (False, True):
        assert _indexed(p, tr) == _fresh(p, tr), tr           # followed: only what is new folded
    end = max(e["time"] for e in p.events.query(n=None))
    for frac in (0.3, 0.7, 1.01):                            # rolled up three times: the index stays as it was
        compact(p, now=T0 + (end - T0) * frac + p.storage.rollup_after)
        for tr in (False, True):
            assert _indexed(p, tr) == _fresh(p, tr), (frac, tr)
    _cold(p)
    for tr in (False, True):                                 # read again from disk by a process that starts
        assert _indexed(p, tr) == _fresh(p, tr), tr
    itemindex.reindex(p.events, p.model.spec)                # and built again from the record
    for tr in (False, True):
        assert _indexed(p, tr) == _fresh(p, tr), tr
    from tests.test_index_projections import _check
    _check(p, r)                                             # and what the status reads, beside the items


def _ticket(tmp_path, backend="segments", extra=""):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(f"""
        items:
          ticket:
            id: ticket/*
            states: [open, doing, done]
            on: {{ticket.started: doing, ticket.done: done}}
            fold: {{spent: sum}}
        storage:
          events: {backend}
        """) + extra)
    return Project(mdl.load(tmp_path))


def test_a_process_that_starts_reads_the_index_and_folds_only_what_is_new(tmp_path):
    p = _ticket(tmp_path)
    for i in range(200):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"spent": i}, at=T0 + i)
    assert len(its.project(p.events, p.model.spec)) == 200
    _cold(p)
    p = Project(mdl.load(tmp_path))
    read = []
    real = p.events.of_items

    def counting(*a, **k):
        got = real(*a, **k)
        read.extend(got)
        return got
    p.events.of_items = counting
    p.events.add("ticket.done", item="ticket/3", at=T0 + 500)
    got = {i.id: i for i in its.project(p.events, p.model.spec)}
    assert len(got) == 200 and got["ticket/3"].state == "done" and got["ticket/3"].fields == {"spent": 3}
    assert [e["type"] for e in read] == ["ticket.done"]        # the rest came from the index


def test_two_processes_share_one_index_and_neither_keeps_a_stale_item(tmp_path):
    p = _ticket(tmp_path)
    spec = p.model.spec
    p.events.add("ticket.opened", item="ticket/1", data={"spent": 1}, at=T0)
    a = itemindex.index_for(p.events, spec, False)
    path = a.path
    b = itemindex.Index(path, spec, False)                     # another process's, on the same file
    p.events.add("ticket.worked", item="ticket/1", data={"spent": 2}, at=T0 + 1)
    b.catch_up(p.events)                                     # b folds it
    p.events.add("ticket.worked", item="ticket/1", data={"spent": 4}, at=T0 + 2)
    a.catch_up(p.events)                                     # a's kept fold of ticket/1 is older than the index's
    with a.lock:
        assert a.items("ticket")[0].fields == {"spent": 7}
    b.close()


def test_only_open_items_are_kept_folded_in_memory(tmp_path):
    p = _ticket(tmp_path, extra="  items: {idle: 1h}\n")
    import time
    now = time.time()
    p.events.add("ticket.opened", item="ticket/open", at=now)
    p.events.add("ticket.opened", item="ticket/done", at=now)
    p.events.add("ticket.done", item="ticket/done", at=now)
    p.events.add("ticket.opened", item="ticket/idle", at=now - 7200)
    ix = itemindex.index_for(p.events, p.model.spec, False)
    assert set(ix.cache) == {"ticket/open"}
    assert {i.id: i.state for i in its.project(p.events, p.model.spec)} == {"ticket/open": "open", "ticket/done": "done",
                                                                            "ticket/idle": "open"}
    p.events.add("ticket.worked", item="ticket/done", data={"spent": 2}, at=now)   # read from disk to fold it further
    assert {i.id: i.fields for i in its.project(p.events, p.model.spec)}["ticket/done"] == {"spent": 2}


def test_what_counts_as_finished_is_declared_or_what_no_item_has_left(tmp_path):
    p = _ticket(tmp_path, extra="messages:\n  done: {ticket: [doing, done]}\n")
    k = p.model.spec.items["ticket"]
    assert itemindex.done_states(k, set()) == ["doing", "done"]
    assert itemindex.done_states(k, {"doing"}) == ["done"]
    assert itemindex.done_states(k, {"doing", "done"}) == ["done"]
    assert itemindex.done_states(k, set(), p.model.spec.messages.done) == ["doing", "done"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_counts_pages_and_moves_read_from_the_index_are_a_folds(tmp_path, backend):
    p = _ticket(tmp_path, backend)
    spec = p.model.spec
    r = random.Random(7)
    for i in range(300):
        t = T0 + i * 10
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"spent": i % 3, "team": r.choice(["a", "b"])}, at=t)
        if r.random() < 0.7:
            p.events.add("ticket.started", item=f"ticket/{i}", at=t + r.random() * 2000)
        if r.random() < 0.4:
            p.events.add("ticket.done", item=f"ticket/{i}", at=t + 2000 + r.random() * 2000)
    p.events.add("x.y", item="loose/1", at=T0)                # an item of no kind
    every = list(_fresh(p, False).values())
    until = T0 + 2500
    past = {i["id"]: its.fold(i["id"], evs, its.kind_of(spec, i["id"])) for i in every
            if (evs := p.events.query(n=None, item=i["id"], until=until))}       # each item as it stood, from the record
    assert any(i["last"] > until for i in every)

    def fresh_moves(key, state, lo, hi, where=None, at=None):
        src = past.values() if at is not None else [its.fold(i["id"], p.events.query(n=None, item=i["id"]),
                                                             its.kind_of(spec, i["id"])) for i in every]
        return sorted(m["time"] for i in src if i.kind == "ticket" and its.matches(i, where or {})
                      for m in i.moves if m[key] == state and lo <= m["time"] <= hi)
    for key, state in (("to", "doing"), ("from", "doing"), ("to", "done"), ("to", "open")):
        assert its.moved(p.events, spec, "ticket", key, state, T0 + 500, T0 + 3000) == fresh_moves(key, state, T0 + 500, T0 + 3000)
        assert its.moved(p.events, spec, "ticket", key, state, T0 + 500, T0 + 3000, {"team": "a"}, at=until) == \
            fresh_moves(key, state, T0 + 500, T0 + 3000, {"team": "a"}, at=until)
    n, entered, _ = its.in_states(p.events, spec, "ticket", ["doing"], until=until)
    want = [i for i in past.values() if i.kind == "ticket" and i.state == "doing"]
    assert n == len(want) and entered == min(i.entered for i in want)
    n, _, got = its.in_states(p.events, spec, "ticket", ["open", "doing"], {"team": "b"}, until=until)
    assert sorted(i.id for i in got) == sorted(i.id for i in past.values() if i.kind == "ticket" and i.state in ("open", "doing")
                                               and i.fields["team"] == "b")
    now = its.listing(p.events, spec, n=50, offset=20)
    assert now["total"] == len(every) and now["unkinded"] == 1
    assert [i["id"] for i in now["items"]] == [i["id"] for i in sorted(every, key=lambda i: -i["last"])][20:70]
    counts = {}
    for i in every:
        if i["kind"]:
            counts[i["state"]] = counts.get(i["state"], 0) + 1
    assert next(k for k in now["kinds"] if k["name"] == "ticket")["counts"] == counts
    doing = its.listing(p.events, spec, kind="ticket", state="doing", until=until)
    assert doing["total"] == len(want) and {i["id"] for i in doing["items"]} == {i.id for i in want}
    assert its.listing(p.events, spec, kind="", n=5)["items"][0]["id"] == "loose/1"


def test_items_flow_from_the_index_is_the_fold_of_every_item(tmp_path):
    from ergostat import series
    p = _ticket(tmp_path)
    r = random.Random(3)
    for i in range(120):
        t = T0 + i * 30
        p.events.add("ticket.opened", item=f"ticket/{i}", at=t)
        if r.random() < 0.8:
            p.events.add("ticket.started", item=f"ticket/{i}", at=t + 100 + r.random() * 600)
            if r.random() < 0.6:
                p.events.add("ticket.done", item=f"ticket/{i}", at=t + 800 + r.random() * 900)
    spec = p.model.spec
    k = spec.items["ticket"]
    for since, until in ((T0 + 600, T0 + 6000), (T0 - 100, T0 + 6000), (T0 + 2000, T0 + 5200)):   # the last: a few changed after
        ts = series.times(since, until, 40)
        got = series._flow_indexed(p, spec, k, since, until, ts)
        assert got is not None
        want = series._flow_folded(p, spec, k, since, until, ts)
        assert got[0] == want[0] and got[1] == want[1] and got[2] == want[2]
        assert sorted(f["id"] for f in got[3]) == sorted(f["id"] for f in want[3])


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_prune_takes_out_whole_items_and_a_fresh_record_is_folded_again(tmp_path, backend):
    p = _ticket(tmp_path, backend, extra="keep: 1d\n")
    now = T0 + 10 * 86400
    p.events.add("ticket.opened", item="ticket/old", at=T0)
    p.events.add("ticket.opened", item="ticket/live", at=T0)
    p.events.add("ticket.done", item="ticket/live", at=now - 10)
    assert len(its.project(p.events, p.model.spec)) == 2
    upkeep(p, now=now)
    assert [i.id for i in its.project(p.events, p.model.spec)] == ["ticket/live"]
    import shutil
    for d in ("events", "events.db", "events.db-wal", "events.db-shm"):        # the record started again
        x = p.dir / d
        if x.is_dir():
            shutil.rmtree(x)
        else:
            x.unlink(missing_ok=True)
    p = Project(mdl.load(tmp_path))
    p.events.add("ticket.opened", item="ticket/new", at=now)
    assert [i.id for i in its.project(p.events, p.model.spec)] == ["ticket/new"]


def test_a_rolled_up_item_is_not_read_again_until_more_of_it_is_due(tmp_path):
    from ergostat import rollup
    p = _ticket(tmp_path, extra="  rollup: {after: 1h}\n")
    for i in range(20):
        p.events.add("ticket.opened", item=f"ticket/{i}", at=T0 + i)
        p.events.add("ticket.started", item=f"ticket/{i}", at=T0 + 100 + i)
    assert compact(p, now=T0 + 7200)["items"] == 20
    assert rollup.candidates(p, T0 + 7200, None) == []
    p.events.add("ticket.done", item="ticket/4", at=T0 + 7300)
    assert rollup.candidates(p, T0 + 7300 + 3600 + 1, None) == ["ticket/4"]


def test_compact_reindex_folds_it_again(tmp_path, capsys):
    from ergostat.cli import main
    p = _ticket(tmp_path)
    p.events.add("ticket.opened", item="ticket/1", at=T0)
    assert main(["-C", str(tmp_path), "compact", "--reindex"]) == 0
    assert "1 items folded" in capsys.readouterr().out


def test_storage_items_idle_is_read_and_checked():
    from ergostat.storage import parse
    problems: list[str] = []
    assert parse({"items": {"idle": "2h"}}, problems).item_idle == 7200 and not problems
    parse({"items": {"kept": 1}}, problems)
    assert problems and "unknown key" in problems[0]


class _Watched:
    """The index's connection, noting each statement run on it by a thread that did not hold the index's lock."""

    def __init__(self, c, lock):
        self.c, self.lock, self.unlocked = c, lock, []

    def execute(self, sql, *a):
        if not self.lock._is_owned():
            self.unlocked.append(sql.split()[:4])
        return self.c.execute(sql, *a)

    def __getattr__(self, name):
        return getattr(self.c, name)


def test_every_read_of_the_index_holds_its_lock(tmp_path):
    """The index's one connection is shared by the process's threads (the page's requests, the engine, the
    estimates); two stepping it at once break each other's reads (the same query twice at once shares SQLite's
    prepared statement: the page's items-graph was handed a row of nothing, ``not enough values to unpack``, a 500).
    Each query takes the lock itself, whoever calls it."""
    p = _ticket(tmp_path)
    spec = p.model.spec
    for i in range(20):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"spent": i}, at=T0 + i)
        p.events.add("ticket.started", item=f"ticket/{i}", at=T0 + 100 + i)
        if i % 2:
            p.events.add("ticket.done", item=f"ticket/{i}", at=T0 + 200 + i)
    ix = itemindex.index_for(p.events, spec, False)
    w = ix._db = _Watched(ix.db, ix.lock)
    ix._forget()                                              # names read again: inside each query below
    ix.catch_up(p.events)
    ix.known("ticket")
    ix.name(1)
    ix.left("ticket")
    ix.reached("ticket")
    ix.changed_after(T0)
    ix.late(T0, "ticket")
    ix.total("ticket")
    ix.counts(T0 + 150)
    ix.count("ticket", ["doing"], T0 + 150)
    ix.items("ticket", n=5)
    ix.items("ticket", ids=["ticket/1", "ticket/2"])
    ix.moves_of([1, 2, 3])
    ix.moved("ticket", "to", "doing", T0, T0 + 300, T0 + 150)
    ix.transitions("ticket")
    ix.tally("ticket", "done", "to", T0 + 300, T0 + 150)
    ix.finished("ticket", ["done"], T0, T0 + 300, T0 + 150)
    ix.links_from(["ticket/1"])
    ix.links_to(["ticket/1"])
    ix.links()
    ix.stays("ticket", finished=["done"])
    ix.candidates()
    ix.guard(lambda: ix.db.execute("select count(*) from items").fetchone())
    assert w.unlocked == []
