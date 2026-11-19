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

    def counted(self, kind, **kw):
        calls.append(kind)
        time.sleep(0.05)
        return real(self, kind, **kw)
    monkeypatch.setattr(type(ix), "transitions", counted)
    chains._CACHE.clear()
    ts = [threading.Thread(target=chains.recorded, args=(p.model.spec,)) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert not any(t.is_alive() for t in ts)
    assert calls == ["job"]


# ---- settled, checked, atomic: what an editing agent leaves half done is never taken

SMALL = """
name: rs
stocks:
  done:
    unit: things
    sensor:
      run: echo 10
      every: 0.3s
goals:
  enough:
    stock: done
    hold: "<= 20"
"""


def _write(d, text: str) -> None:
    import os
    f = d / "ergostat.yaml"
    before = f.stat().st_mtime_ns if f.exists() else 0
    f.write_text(textwrap.dedent(text))
    if f.stat().st_mtime_ns == before:                   # a clock too coarse to see the edit: move it on
        os.utime(f, ns=(before + 1_000_000, before + 1_000_000))


def _until(cond, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_a_burst_of_writes_is_taken_once_the_files_settle(tmp_path):
    from ergostat.reload import Settled
    _write(tmp_path, SMALL)
    w = Settled(mdl.load(tmp_path), settle=0.4)
    assert w.due() is None
    for i in range(5):                                   # written in pieces, and again
        _write(tmp_path, SMALL.replace('"<= 20"', f'"<= {21 + i}"'))
        assert w.due() is None
        time.sleep(0.1)
    assert w.due() is None                               # not settled yet
    time.sleep(0.6)
    due = w.due()
    assert due is not None and w.due() == due            # due until taken
    w.refused(due)
    assert w.due() is None                               # the same files are not read again


def test_an_empty_truncated_or_broken_file_is_refused_with_where_it_is_wrong(tmp_path):
    from ergostat.reload import banner, load_checked
    _write(tmp_path, SMALL)
    m = mdl.load(tmp_path)
    (tmp_path / "ergostat.yaml").write_text("")          # truncated, not yet written: it would load as an empty model
    got, errors = load_checked(m)
    assert got is None and errors == ["ergostat.yaml:1: the file is empty"]
    text = textwrap.dedent(SMALL)
    (tmp_path / "ergostat.yaml").write_text(text[:text.index("<=")])   # cut off in a quoted string
    assert load_checked(m)[0] is None
    _write(tmp_path, SMALL.replace("stock: done", "stock: gone"))
    got, errors = load_checked(m)
    assert got is None and errors and errors[0].startswith("ergostat.yaml:")
    assert banner(errors).startswith("the edited model has errors (ergostat.yaml:")
    assert banner(errors).endswith("; still running the last good version")
    _write(tmp_path, SMALL)
    assert load_checked(m)[0] is not None


def test_the_page_reads_a_changed_model_once_however_many_ask_and_keeps_the_last_good_one(tmp_path, monkeypatch):
    """Root cause 2: the page's ``Live.get`` read the model again in every request while the files differed from the
    model it had, all at once, and again in every request while they had errors."""
    from ergostat import reload as rl
    from ergostat.web.server import Live, api
    monkeypatch.setattr(rl, "SETTLE", 0.2)
    _write(tmp_path, SMALL)
    live = Live(Project(mdl.load(tmp_path)))
    loads = []
    real = rl.mdl.load

    def slow(*a, **kw):
        loads.append(1)
        time.sleep(0.3)
        return real(*a, **kw)
    monkeypatch.setattr(rl.mdl, "load", slow)
    _write(tmp_path, SMALL.replace('"<= 20"', '"<= 30"'))
    time.sleep(0.3)
    ts = [threading.Thread(target=live.get) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert len(loads) == 1
    assert "30" in str(live.get().model.spec.goals["enough"].hold)
    _write(tmp_path, SMALL.replace("stock: done", "stock: gone"))
    time.sleep(0.3)
    for _ in range(20):
        live.get()
    assert len(loads) == 2 and live.errors                 # read once, refused once
    assert "30" in str(live.get().model.spec.goals["enough"].hold)       # the last good one, still
    got = api(live, "status", {})
    assert got["edited"]["banner"].startswith("the edited model has errors (ergostat.yaml:")
    assert got["attention"][0]["says"] == got["edited"]["banner"]
    _write(tmp_path, SMALL)
    time.sleep(0.3)
    live.get()
    assert not live.errors and "edited" not in api(live, "status", {})


def test_a_change_that_cannot_be_taken_leaves_the_last_model_running_untouched(tmp_path, monkeypatch):
    from ergostat.spec import blocks as bl
    from ergostat.spec.engine import Engine
    text = SMALL + """
blocks:
  hold:
    type: onoff
    goal: enough
"""
    _write(tmp_path, text)
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)
    spec, version, builtins = e.spec, e.version, dict(e.builtins)
    kept = builtins["hold"]
    _write(tmp_path, text.replace('"<= 20"', '"<= 25"') + "  other:\n    type: onoff\n    goal: enough\n")
    fresh = mdl.load(tmp_path)
    real = bl.make

    def refuse(b, s):
        if b.name == "other":
            raise RuntimeError("cannot make it")
        return real(b, s)
    monkeypatch.setattr(bl, "make", refuse)
    with pytest.raises(RuntimeError):
        e.swap(fresh)
    assert e.spec is spec and e.version == version and e.builtins == builtins and p.model.spec is spec
    assert kept.spec is spec                              # a built-in kept is not half moved to the new model


def test_a_reading_is_never_left_under_way_when_writing_it_fails(tmp_path, monkeypatch):
    """A reading whose result could not be written (the store busy) stayed marked under way, and was never read
    again."""
    from ergostat.spec.engine import Engine
    _write(tmp_path, SMALL)
    p = Project(mdl.load(tmp_path))
    e = Engine(p, say=lambda s: None)
    e.looping = True
    s = next(iter(e.spec.sensors()))
    e.read_soon(s)
    assert s.series in e.reading

    def busy(rows):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(p.measurements, "add_many", busy)
    e._readings(False)                                   # handed to the pool
    assert _until(lambda: not e.results.empty())
    with pytest.raises(RuntimeError):
        e._readings(False)
    assert s.series not in e.reading
    e.read_soon(s)                                        # asked again: it is
    assert s.series in e.wanted
    e.pool.shutdown(wait=False)
