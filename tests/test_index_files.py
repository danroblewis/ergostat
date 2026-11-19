"""The item index's files across processes (spec/itemindex.py): no process deletes an index file another
has open (a SQLite file, WAL or shared memory unlinked while in use is corrupted), and an index that cannot
be read is built again from the record where it is found. The record itself is never rebuilt."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import random
import sqlite3
import textwrap
import time
import traceback
from collections import Counter
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.spec import itemindex
from ergostat.spec import items as its
from ergostat.store import Events, Project, RecordDamaged

CTX = mp.get_context("spawn")
YAML = """
items:
  ticket:
    id: ticket/*
    states: [{states}]
    on: {{ticket.started: doing, ticket.done: done}}
storage:
  events: sqlite
"""
STATES = "open, doing, done"


def _project(root: Path, states: str = STATES) -> Project:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ergostat.yaml").write_text(textwrap.dedent(YAML.format(states=states)))
    return Project(mdl.load(root))


def _cold() -> None:
    for ix in list(itemindex._OPEN.values()):
        ix.close()
    itemindex._OPEN.clear()


def _heals() -> list[str]:
    """The warnings healing logs, kept in a list (in whichever process calls it)."""
    got: list[str] = []

    class Keep(logging.Handler):
        def emit(self, r):
            got.append(r.getMessage())
    logging.getLogger("ergostat").addHandler(Keep())
    return got


# ---- a process that writes and reads the index (spawned: a process of its own, as the engine, the page and the CLI are)

def _writer(root: str, path: str, hold: int, stop, out) -> None:
    """Opens the index file ``path``, folds what it adds to the record, reads, and closes again after ``hold``
    rounds; counts every error it meets."""
    heals = _heals()
    errs: Counter = Counter()
    n = 0
    try:
        p = _project(Path(root))
        r = random.Random(os.getpid())
        ix, used = None, 0
        while not stop.is_set():
            try:
                if ix is None:
                    ix, used = itemindex.Index(Path(path), p.model.spec, False), 0
                for _ in range(r.randint(1, 30)):
                    p.events.add("ticket.opened", item=f"ticket/{os.getpid()}-{n}-{r.random()}", data={"x": "y" * r.randint(10, 2000)})
                ix.catch_up(p.events)
                with ix.lock:
                    ix.count("ticket")
                    ix.items("ticket", n=20)
                n, used = n + 1, used + 1
                if used >= hold:
                    ix.close()
                    ix = None
            except sqlite3.DatabaseError as e:
                errs[f"{type(e).__name__}: {e}"] += 1
                if ix is not None:
                    ix.close()
                ix = None
        if ix is not None:
            ix.close()
    except BaseException:
        errs[traceback.format_exc()] += 1
    out.put((n, dict(errs), len(heals)))


def _tidier(d: str, stop, out) -> None:
    """``_tidy`` again and again, told to keep nothing however recently changed."""
    itemindex.KEPT_FILES, itemindex.TIDY_AGE = 1, 0.0
    n = 0
    while not stop.is_set():
        time.sleep(random.random() * 0.2)
        itemindex._tidy(Path(d))
        n += 1
    out.put(n)


def test_two_processes_one_tidying_never_corrupt_an_index_another_has_open(tmp_path):
    """The reproduction: processes holding the index open and writing while another tidies the directory (as a
    process with other kinds does). Before the locks, the tidy unlinked the file, its WAL and its shared memory
    under them: disk I/O errors, then "database disk image is malformed" / "file is not a database"."""
    root = tmp_path / "proj"
    p = _project(root)
    p.events.add("ticket.opened", item="ticket/0")
    path = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    stop, out = CTX.Event(), CTX.Queue()
    holds = [1, 3, 10, 50, 10_000]
    ws = [CTX.Process(target=_writer, args=(str(root), str(path), h, stop, out)) for h in holds]
    ts = [CTX.Process(target=_tidier, args=(str(path.parent), stop, out)) for _ in range(2)]
    for x in ws + ts:
        x.start()
    time.sleep(8)
    stop.set()
    got = [out.get(timeout=60) for _ in ws + ts]
    for x in ws + ts:
        x.join(30)
    runs = [g for g in got if isinstance(g, tuple)]
    assert sum(n for n, _, _ in runs) > 50                      # they did work
    assert all(not errs for _, errs, _ in runs), runs           # no process met an error
    assert all(heals == 0 for _, _, heals in runs), runs        # nor needed healing: nothing was deleted under them
    if path.exists():                                           # (tidied once the last closed it, or not)
        c = sqlite3.connect(path)
        assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
        c.close()
    _cold()
    p = Project(mdl.load(root))
    assert len(its.project(p.events, p.model.spec)) == p.events.count()


def test_a_corrupt_index_is_built_again_from_the_record_on_next_use(tmp_path):
    p = _project(tmp_path / "proj")
    for i in range(50):
        p.events.add("ticket.opened", item=f"ticket/{i}")
    p.events.add("ticket.done", item="ticket/3")
    path = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    path.write_bytes(os.urandom(64 * 1024))                    # garbage where the index was
    for suf in ("-wal", "-shm"):
        Path(str(path) + suf).unlink(missing_ok=True)
    heals = _heals()
    got = {i.id: i.state for i in its.project(p.events, p.model.spec)}
    assert len(got) == 50 and got["ticket/3"] == "done"
    assert len(heals) == 1 and "could not be read" in heals[0]
    assert itemindex._OPEN and next(iter(itemindex._OPEN.values())).path == path   # the same file, made again
    c = sqlite3.connect(path)
    assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
    c.close()


def test_a_corrupt_index_another_process_has_open_is_retired_and_the_next_name_built(tmp_path):
    p = _project(tmp_path / "proj")
    for i in range(20):
        p.events.add("ticket.opened", item=f"ticket/{i}")
    path = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    w = _Held(tmp_path / "proj", path)                        # another process has it open
    try:
        with open(path, "r+b") as f:
            f.write(os.urandom(4096))                          # its first page: not a database any more
        heals = _heals()
        assert len(its.project(p.events, p.model.spec)) == 20
        assert len(heals) == 1
        assert path.exists() and path.with_suffix(".retired").exists()     # not deleted under the other process
        now = next(iter(itemindex._OPEN.values())).path
        assert now.name == path.name.replace(".db", ".1.db") and now.exists()
    finally:
        w.stop()
    itemindex._tidy(path.parent)                               # nobody has it open now: the retired file goes
    assert not path.exists() and now.exists()


class _Held:
    """Another process with an index file open (and its shared lock held) until ``stop``."""

    def __init__(self, root: Path, path: Path):
        self.go, self.out = CTX.Event(), CTX.Queue()
        self.p = CTX.Process(target=_hold, args=(str(root), str(path), self.go, self.out))
        self.p.start()
        assert self.out.get(timeout=60) == "open"

    def stop(self):
        self.go.set()
        self.p.join(30)


def _hold(root: str, path: str, go, out) -> None:
    p = Project(mdl.load(Path(root)))
    ix = itemindex.Index(Path(path), p.model.spec, False)
    ix.total()                                                # opened: the shared lock taken
    out.put("open")
    go.wait()
    ix.close()


def test_tidy_skips_an_index_another_process_has_open(tmp_path, monkeypatch):
    p = _project(tmp_path / "proj")
    p.events.add("ticket.opened", item="ticket/1")
    held = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    monkeypatch.setattr(itemindex, "KEPT_FILES", 1)
    old = time.time() - 2 * itemindex.TIDY_AGE
    w = _Held(tmp_path / "proj", held)
    try:
        for suf in ("", "-wal", "-shm"):
            if Path(str(held) + suf).exists():
                os.utime(str(held) + suf, (old, old))          # unchanged for two hours: tidied, unless open
        other = _project(tmp_path / "alt", f"{STATES}, more").model.spec
        itemindex.index_for(p.events, other, False)            # a new fold: the tidy runs
        assert held.exists() and held.with_suffix(".lock").exists()
    finally:
        w.stop()
    _cold()
    itemindex._tidy(held.parent)                               # closed now: it goes, with its WAL, shm and lock
    assert not any(held.parent.glob(held.name.split(".")[0] + "*"))


def test_tidy_leaves_an_index_changed_within_the_hour(tmp_path, monkeypatch):
    p = _project(tmp_path / "proj")
    p.events.add("ticket.opened", item="ticket/1")
    recent = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    monkeypatch.setattr(itemindex, "KEPT_FILES", 1)
    itemindex._tidy(recent.parent)
    assert recent.exists()


def test_reindex_while_another_process_has_the_index_open(tmp_path):
    p = _project(tmp_path / "proj")
    for i in range(30):
        p.events.add("ticket.opened", item=f"ticket/{i}")
    path = itemindex.index_for(p.events, p.model.spec, False).path
    _cold()
    w = _Held(tmp_path / "proj", path)
    try:
        got = itemindex.reindex(p.events, p.model.spec)
        assert got["items"]["items"] == 30
        assert path.exists() and path.with_suffix(".retired").exists()     # the other process's file left alone
        built = next(ix.path for ix in itemindex._OPEN.values() if not ix.transcript)
        assert built != path and built.exists()
    finally:
        w.stop()
    _cold()
    p.events.add("ticket.done", item="ticket/1")
    assert {i.id: i.state for i in its.project(p.events, p.model.spec)}["ticket/1"] == "done"
    assert next(iter(itemindex._OPEN.values())).path == built                  # the retired name is not used again
    itemindex.reindex(p.events, p.model.spec)                                   # nobody holds any: all deleted, built afresh
    assert not built.exists() and not path.with_suffix(".retired").exists()
    assert next(ix.path for ix in itemindex._OPEN.values() if not ix.transcript) == path


def test_a_process_whose_index_was_retired_moves_to_the_new_one(tmp_path):
    p = _project(tmp_path / "proj")
    p.events.add("ticket.opened", item="ticket/1")
    ix = itemindex.index_for(p.events, p.model.spec, False)
    first = ix.path
    first.with_suffix(".retired").touch()                     # as another process's reindex leaves it
    p.events.add("ticket.done", item="ticket/1")
    again = itemindex.index_for(p.events, p.model.spec, False)
    assert again is ix and ix.path != first
    with ix.lock:
        assert ix.items("ticket")[0].state == "done"


def test_a_damaged_record_is_never_rebuilt_and_says_how_to_restore_it(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    (d / "events.db").write_bytes(os.urandom(64 * 1024))
    with pytest.raises(RecordDamaged) as e:
        Events(d)
    msg = str(e.value)
    assert str(d / "events.db") in msg and ".recover" in msg and "ergostat run --stop" in msg
    assert (d / "events.db").stat().st_size == 64 * 1024     # left as it is
