"""A model edited while it runs (SPEC §9.1): every root cause found when an agent's edits left
``ergostat run`` with no items, no diagrams and every sensor timing out, each with its own test."""

import textwrap
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.spec import chains
from ergostat.spec.itemindex import index_for
from ergostat.store import Project

KINDS = """
name: rs
items:
  job:
    id: job/*
    states: [new, doing, done]
    on:
      job.start: doing
      job.end: done
stocks:
  waiting: {unit: jobs, sensor: {items: job, state: new, every: 1s}}
  doing: {unit: jobs, sensor: {items: job, state: doing, every: 1s}}
  done: {unit: jobs, sensor: {items: job, state: done, every: 1s}}
flows:
  starting: {from: waiting, to: doing, sensor: {items: job, entering: doing, over: 1h}}
  ending: {from: doing, to: done, sensor: {items: job, entering: done, over: 1h}}
"""


@pytest.fixture(autouse=True)
def _stopping_cleared():
    yield
    runner.STOPPING.clear()


def _project(tmp_path, text: str = KINDS, jobs: int = 300) -> Project:
    d = tmp_path / "rs"
    d.mkdir(exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))
    p = Project(mdl.load(d))
    evs = []
    for i in range(jobs):
        evs += [{"type": "job.made", "item": f"job/{i}"}, {"type": "job.start", "item": f"job/{i}"},
                {"type": "job.end", "item": f"job/{i}"}]
    p.events.add_many(evs, new=True)
    return p


class _Watched:
    """The index's connection, each statement checked: run by the thread that holds the index's lock."""

    def __init__(self, conn, lock, wrong: list):
        self.conn, self.lock, self.wrong = conn, lock, wrong

    def execute(self, *a, **kw):
        if not self.lock._is_owned():
            self.wrong.append((threading.current_thread().name, str(a[0])[:60]))
        return self.conn.execute(*a, **kw)

    def __getattr__(self, name):
        return getattr(self.conn, name)


def test_loading_a_model_reads_the_item_index_only_under_its_lock(tmp_path):
    """Root cause 1: a model's findings read the record's moves (``chains.recorded``) on the process's shared item index
    connection without its lock, while the engine's loop, its dispatcher and the page used it under the lock. An agent's
    edits made every page request load the model at once: a dozen threads stepping one SQLite connection together
    stalled for minutes, and the errors it gave ("another row available", "database is locked") broke the counts."""
    p = _project(tmp_path)
    ix = index_for(p.events, p.model.spec, False)
    wrong: list = []
    with ix.lock:
        ix._db = _Watched(ix.db, ix.lock, wrong)
    chains._CACHE.clear()
    got = chains.recorded(p.model.spec)
    assert got["job"][("doing", "done")] == 300
    assert wrong == []


def test_many_threads_loading_the_model_at_once_read_the_record_once(tmp_path, monkeypatch):
    """The same model loaded by many threads at once (every page request after an edit) reads the record's moves once."""
    p = _project(tmp_path)
    ix = index_for(p.events, p.model.spec, False)
    calls = []
    real = type(ix).transitions

    def counted(self, kind):
        calls.append(kind)
        time.sleep(0.05)
        return real(self, kind)
    monkeypatch.setattr(type(ix), "transitions", counted)
    chains._CACHE.clear()
    ts = [threading.Thread(target=chains.recorded, args=(p.model.spec,)) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert not any(t.is_alive() for t in ts)
    assert calls == ["job"]
