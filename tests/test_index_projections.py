"""What the status reads from the record, kept as tables of the item index (spec/projections.py). For randomized
event sequences, on both event stores, each table's answer equals a fresh read of the record (the modules' own
``stored()``, ``events.query``, ``inbox.entries.asks``): as events arrive, a chunk at a time, read cold, built again,
after a roll-up, a prune and a fresh record; an older index is rebuilt; a crash part way resumes; another process
reads what was committed while one follows."""

from __future__ import annotations

import random
import shutil
import textwrap
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat.actions import record as actions
from ergostat.inbox import entries, interventions
from ergostat.messages import record as messages
from ergostat.numbers import proposals, requests
from ergostat.reports import record as reports
from ergostat.rollup import compact, upkeep
from ergostat.spec import itemindex, projections
from ergostat.store import Project
from tests import status_before as old
from tests.test_item_index import _cold

T0 = 1_700_000_000.0
BACKENDS = ("sqlite", "segments")
BLOCKS = ("asker", "advisor")
LOOPS = ("lp-a", "lp-b")


def _project(tmp_path, backend: str, extra: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(f"""
        items:
          ticket:
            id: ticket/*
            states: [open, done]
            on: {{ticket.done: done}}
        storage:
          events: {backend}
        """) + extra)
    return Project(mdl.load(tmp_path))


def _events(r: random.Random, n: int, t0: float) -> list[tuple]:
    """(type, item, data, source) of a random history: ergostat's own items, the marks and the asks, a few tickets."""
    out, ids = [], []
    for _ in range(n):
        pick = r.random()
        if pick < 0.5:
            fam = r.choice(list(projections.FAMILIES))
            pre = projections.FAMILIES[fam][0]
            kind = projections._kind(fam)
            item = f"{pre}/{r.randrange(6)}"
            ty = r.choice([*kind.on, f"{pre}.noted"])
            data = {k: r.choice(["a", "b", "c"]) for k in r.sample(["class", "action", "kind", "code", "note", "text"],
                                                                     r.randrange(3))}
            out.append((ty, item, data, r.choice(["owner", "ergostat", "gate"])))
        elif pick < 0.75:
            ty = r.choice(["loop.off", "loop.on", "trigger.tripped", "trigger.reset", "steptest.offered",
                           "steptest.approved", "ergostat.daemon.failed", "ergostat.daemon.started", "loop.held"])
            data = {"id": f"s{r.randrange(3)}"} if ty.startswith("steptest") else {"users": ["x"]}
            out.append((ty, r.choice(LOOPS + BLOCKS), data, "ergostat"))
        elif pick < 0.8:
            out.append((projections.EXPIRED, f"ticket/{r.randrange(4)}", {"block": "b"}, "ergostat"))
        elif pick < 0.83 and ids:
            out.append((projections.FORGOTTEN, "part", {"voids": r.sample(ids, min(len(ids), 2))}, "ergostat"))
        elif pick < 0.97:
            ty = r.choice(list(projections.CHAINS))
            out.append((ty, r.choice(BLOCKS), {"note": r.choice(["", "fine"]), "command": 1}, r.choice(["owner", "x"])))
        else:
            out.append(("ticket.done" if r.random() < 0.3 else "ticket.opened", f"ticket/{r.randrange(4)}", {}, "x"))
        ids.append(None)
    return out


def _add(p, evs: list[tuple], t0: float, r: random.Random) -> list[str]:
    t, got = t0, []
    known: list[str] = []
    for ty, item, data, src in evs:
        t += r.choice([0.0, 0.5, 10.0, 600.0])                # times follow the record's order (each added now)
        if ty == projections.FORGOTTEN:
            data = {"voids": r.sample(known, min(len(known), 2))}
        e = p.events.add(ty, item=item, data=data, source=src, at=t)
        if ty.startswith("loop."):
            known.append(e["id"])
        got.append(e["id"])
    return got


def _fresh_records(p) -> dict:
    """The record folded by the old code (tests/status_before.py): the modules read the tables now."""
    return {"action": old.actions(p), "message": old.messages(p), "report": old.reports(p),
            "change": old.changes(p), "request": old.requests(p), "model-request": old.requests_now(p)}


def _modules(p) -> dict:
    return {"action": actions.stored(p), "message": messages.stored(p), "report": reports.stored(p),
            "change": proposals.changes(p), "request": requests.stored(p), "model-request": interventions.requests_now(p)}


def _check(p, r: random.Random) -> None:
    """Every table's answer equals a fresh read of the record, for random questions."""
    for tr in (False, True):
        ix = itemindex.index_for(p.events, p.model.spec, tr)
        want = _fresh_records(p)
        assert _modules(p) == want                         # what the modules answer, from the tables
        real = projections.index_of                        # and with no index (a record kept nowhere on disk): the
        projections.index_of = lambda p: None              # same fold, of the record's events, in memory
        try:
            assert _modules(p) == want
            for name in BLOCKS:
                assert projections.asks(p, name, True) == old.asks(p, name, True)
                assert projections.asks(p, name, False) == old.asks(p, name, False)
        finally:
            projections.index_of = real
        for fam, got in want.items():
            mine = ix.records(fam)
            for k in set(mine) | set(got):                 # (one entry at a time: a difference says which)
                assert mine.get(k) == got.get(k), (fam, k, mine.get(k), got.get(k),
                                                   [(e["seq"], e["type"]) for e in p.events.query(n=None, item=k)])
            for st in projections._kind(fam).states if fam != "model-request" else ():   # (keyed by class: two of one
                #                                                       class in different states are one entry there)
                assert ix.records(fam, states=[st]) == {k: v for k, v in got.items()
                                                        if (v[0] if fam == "change" else v["state"]) == st}, (fam, st)
        cls = {a.get("class") or a.get("action") for a in want["action"].values()}
        for c in cls:
            assert ix.records("action", cls=c) == {k: v for k, v in want["action"].items()
                                                   if (v.get("class") or v.get("action")) == c}
        assert ix.records("action", states=["requested"], cls="a") == {
            k: v for k, v in want["action"].items() if v["state"] == "requested" and (v.get("class") or v.get("action")) == "a"}
        span = [e["time"] for e in p.events.query(n=None)] or [T0]
        for _ in range(12):
            a, b = sorted(r.uniform(min(span) - 1, max(span) + 1) for _ in range(2))
            q = {"type": r.choice(["loop.*", "trigger.tripped,trigger.reset", "steptest.offered", "ergostat.daemon.*",
                                   projections.EXPIRED, f"{projections.MODEL_CHANGE}.*",
                                   f"{projections.MODELLING_REQUEST}.*,loop.off", projections.FORGOTTEN]),
                 "item": r.choice([None, *LOOPS, *BLOCKS, "ticket/1"]), "since": r.choice([None, a]),
                 "until": r.choice([None, b]), "n": r.choice([None, 1, 3, 50]), "unvoided": r.random() < 0.5}
            assert ix.marked(**q) == p.events.query(**q) == projections.query(p, **q), q
            assert ix.records("action", since=a) == actions.stored(p, since=a) == old.actions(p, since=a)
            assert ix.records("message", since=a) == messages.stored(p, since=a) == old.messages(p, since=a)
            # as of a moment: the table when no item of the family has an event after it, else folded up to then
            assert actions.stored(p, since=a, until=b) == old.actions(p, since=a, until=b), (a, b)
            assert reports.stored(p, until=b) == old.reports(p, until=b), b
            for name in BLOCKS:
                for person in (True, False):
                    blk = SimpleNamespace(name=name, type="person" if person else "ai")
                    w = (r.choice([None, a]), r.choice([None, b]))
                    assert ix.asked(name, person, *w) == entries.asks(p, blk, *w) == old.asks(p, name, person, *w), \
                        (name, person, w)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("seed", range(3))
def test_each_table_is_a_fresh_read_of_the_record(tmp_path, backend, seed, monkeypatch):
    p = _project(tmp_path, backend)
    r = random.Random(f"{backend}{seed}")
    evs = _events(r, 300, T0)
    _add(p, evs[:120], T0, r)
    _check(p, r)                                           # built from the record
    _add(p, evs[120:], T0 + 1e6, r)
    _check(p, r)                                           # followed: only what is new folded
    _cold(p)
    _check(p, r)                                           # read again from disk by a process that starts
    monkeypatch.setattr(itemindex, "CHUNK", 7)             # built again, a few events per transaction
    itemindex.reindex(p.events, p.model.spec)
    _check(p, r)
    _add(p, _events(r, 60, T0), T0 + 2e6, r)               # followed a chunk at a time
    _check(p, r)


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_rollup_a_prune_and_a_fresh_record_leave_the_tables_right(tmp_path, backend):
    p = _project(tmp_path, backend, "  rollup: {after: 1h}\nkeep: 2d\n")
    r = random.Random(backend + "rollup")
    _add(p, _events(r, 400, T0), T0, r)
    _check(p, r)
    end = max(e["time"] for e in p.events.query(n=None))
    compact(p, now=end + 7200)                             # rolled up: ergostat's own items among them
    assert p.events.query(n=1, type="ergostat.item.snapshot")
    _check(p, r)
    _add(p, _events(r, 80, T0), end + 10 * 86400, r)
    upkeep(p, now=end + 10 * 86400 + 3 * 3600)             # pruned: the old ones forgotten
    _check(p, r)
    for d in ("events", "events.db", "events.db-wal", "events.db-shm"):     # the record started again
        x = p.dir / d
        if x.is_dir():
            shutil.rmtree(x)
        else:
            x.unlink(missing_ok=True)
    p = Project(mdl.load(tmp_path))
    _add(p, _events(r, 50, T0), T0 + 5e6, r)
    _check(p, r)


def test_an_index_of_an_older_layout_is_rebuilt(tmp_path, monkeypatch):
    p = _project(tmp_path, "sqlite")
    r = random.Random("older")
    _add(p, _events(r, 150, T0), T0, r)
    ix = itemindex.index_for(p.events, p.model.spec, False)
    for t in projections.TABLES:                           # as an index of version 5 left it: none of the tables
        ix.db.execute(f"delete from {t}")
    ix.db.execute("update meta set value = 5 where key = 'version'")
    _cold(p)
    _check(p, r)
    with monkeypatch.context() as m:                       # a file named for version 5 is not read: a new one is built
        m.setattr(itemindex, "VERSION", 5)
        _cold(p)
        old = itemindex.index_for(p.events, p.model.spec, False).path
    _cold(p)
    assert itemindex.index_for(p.events, p.model.spec, False).path != old
    _check(p, r)


def test_a_crash_part_way_resumes_from_what_was_committed(tmp_path, monkeypatch):
    p = _project(tmp_path, "segments")
    r = random.Random("crash")
    _add(p, _events(r, 200, T0), T0, r)
    monkeypatch.setattr(itemindex, "CHUNK", 9)
    real, calls = projections.follow, []

    def dies(ix, evs, asks=True):
        calls.append(1)
        real(ix, evs, asks)
        if len(calls) == 4:
            raise KeyboardInterrupt                        # killed inside the fourth chunk's transaction
    monkeypatch.setattr(projections, "follow", dies)
    _cold(p)
    with pytest.raises(KeyboardInterrupt):
        itemindex.index_for(p.events, p.model.spec, False)
    ix = itemindex._OPEN[next(iter(itemindex._OPEN))]
    with ix.lock:
        assert 0 < int(ix._meta("seq")) < p.events.last_seq()      # three chunks committed, the fourth rolled back
    monkeypatch.setattr(projections, "follow", real)
    _cold(p)
    _check(p, r)                                           # a process that starts again resumes from there


def test_another_process_reads_what_was_committed_while_one_follows(tmp_path, monkeypatch):
    p = _project(tmp_path, "sqlite")
    r = random.Random("readers")
    _add(p, _events(r, 150, T0), T0, r)
    a = itemindex.index_for(p.events, p.model.spec, False)
    b = itemindex.Index(a.path, p.model.spec, False)       # another process's, on the same file
    b.catch_up(p.events)
    before = (b.records("action"), b.marked("loop.*", n=None), b.asked("asker", True))
    _add(p, _events(r, 150, T0), T0 + 1e6, r)
    seen, real = [], projections.follow

    def reading(ix, evs, asks=True):
        real(ix, evs, asks)
        if ix is a:                                        # a holds the write lock, its chunk not yet committed
            seen.append((b.records("action"), b.marked("loop.*", n=None), b.asked("asker", True)))
    monkeypatch.setattr(projections, "follow", reading)
    a.catch_up(p.events)
    assert seen and seen[0] == before                      # b read at once, what was committed before
    monkeypatch.setattr(projections, "follow", real)
    b.catch_up(p.events)
    assert (b.records("action"), b.marked("loop.*", n=None), b.asked("asker", True)) == (
        old.actions(p), p.events.query(n=None, type="loop.*"), old.asks(p, "asker", True))
    b.close()
