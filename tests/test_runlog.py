"""Each run's own log (SPEC §4b, §12r): ``logs/runs/<block>/<seq>-<id12>.log`` holds that run's standard error and
nothing of another's, triage reads only it, the block's log gets each run whole in one locked append, and the oldest
run files are pruned by start seq, never one a run still holds."""

import fcntl
import os
import re
import textwrap
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat import runlog
from ergostat.repair import FAILURE
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

DEADLINE = 30.0                     # (only so a hung test fails rather than hangs: every wait is on a barrier)

KIND = """
name: t
items:
  ticket:
    id: ticket/*
    states: [ready, doing, done]
    on: {ticket.started: doing, ticket.done: done}
"""
REPAIR = """
uses:
  repair:
    use: repair
    with: {count-every: 1h, approver: person}
"""
# Each run writes its marker, waits until the other has started, writes it again after the other has written its
# first: so each run's lines and the other's are written while both are running. ticket/1's run fails.
BARRIER = r'''
import os, pathlib, sys, time
sys.stdin.read()
me = os.environ["ERGOSTAT_ITEM"].split("/")[1]
other = "2" if me == "1" else "1"
def wait(name):
    end = time.time() + 30
    while not pathlib.Path(name).exists():
        if time.time() > end:
            sys.exit(9)
        time.sleep(0.01)
sys.stderr.write(f"MARK-{me} first\n"); sys.stderr.flush()
print(f"MARK-{me} printed", flush=True)
pathlib.Path(f"at-{me}").write_text("x")
wait(f"at-{other}")
sys.stderr.write(f"MARK-{me} second\n"); sys.stderr.flush()
pathlib.Path(f"wrote-{me}").write_text("x")
wait(f"wrote-{other}")
sys.stderr.write(f"MARK-{me} last\n"); sys.stderr.flush()
sys.exit(1 if me == "1" else 0)
'''
# A daemon that holds both its runs until it has been handed two, then writes each one's line to its standard error
# and answers: ticket/1's run fails.
DAEMON = r'''
import json, sys, threading, time
out = threading.Lock()
def say(**o):
    with out:
        sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
def beat():
    while True:
        say(heartbeat=True); time.sleep(0.2)
threading.Thread(target=beat, daemon=True).start()
held = []
for line in sys.stdin:
    m = json.loads(line)
    if m["op"] == "item":
        held.append(m)
        if len(held) == 2:
            for h in held:
                sys.stderr.write(f"DSTDERR-{h['run']}\n"); sys.stderr.flush()
            for h in held:
                say(done=1 if h["item"] == "ticket/1" else 0, run=h["run"])
    elif m["op"] == "stop":
        break
'''


def project(tmp_path, blocks: str, repair: bool = True) -> Project:
    from ergostat import runner
    runner.STOPPING.clear()                                  # (an engine closed before stops every run: not this one's)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(KIND) + textwrap.dedent(blocks) + (REPAIR if repair else ""))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    return Project(m)


def ended(p, block: str) -> list[dict]:
    return [x for x in p.events.query(n=None) if x["type"] in ("agent.ran", "agent.failed") and x["item"] == block]


def wait_for(cond, seconds=DEADLINE):
    end = time.time() + seconds
    while time.time() < end:
        if got := cond():
            return got
        time.sleep(0.02)
    return cond()


def entries(text: str) -> list[tuple[str, list[str]]]:
    """The block log as (its header's run id8, its lines)."""
    out: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if m := re.match(r"^--- \d{4}-\d\d-\d\d \d\d:\d\d:\d\d run ([0-9a-f]{8}) \(", line):
            out.append((m[1], []))
        else:
            assert out, f"a line before any header: {line!r}"
            out[-1][1].append(line)
    return out


@pytest.fixture
def overlapped(tmp_path):
    """Two runs of one block that takes items, overlapping through barrier files; ticket/1's fails."""
    (tmp_path / "w.py").write_text(BARRIER)
    p = project(tmp_path, """
        blocks:
          worker:
            type: program
            takes: {kind: ticket, at: ready}
            pool: 2
            lease: {ttl: 1m, attempts: 1}
            run: python3 w.py
        """)
    for i in (1, 2):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t")
    e = Engine(p, say=lambda s: None)
    b = p.model.spec.blocks["worker"]
    ts = [threading.Thread(target=e.run_block, args=(b, "test")) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(DEADLINE)
    assert not any(t.is_alive() for t in ts)
    runs = {x["data"]["item"]: x for x in ended(p, "worker")}
    assert sorted(runs) == ["ticket/1", "ticket/2"]
    assert runs["ticket/1"]["type"] == "agent.failed" and runs["ticket/2"]["type"] == "agent.ran"
    return p, runs


def test_two_overlapping_runs_of_one_block_each_have_their_own_file_and_failure(overlapped):
    p, runs = overlapped
    logs = {i: r["data"]["log"] for i, r in runs.items()}
    assert len(set(logs.values())) == 2
    for i, other in (("1", "2"), ("2", "1")):
        log = logs[f"ticket/{i}"]
        assert re.fullmatch(r"logs/runs/worker/\d+-[0-9a-f]{12}\.log", log)
        text = (p.dir / log).read_text()
        assert all(f"MARK-{i} {w}" in text for w in ("first", "printed", "second", "last")), text
        assert f"MARK-{other}" not in text, text
    failed = p.events.query(n=None, type="ergostat.run.failed")
    assert len(failed) == 1
    d = failed[0]["data"]
    assert d["run"] == runs["ticket/1"]["causedby"] and d["log"] == logs["ticket/1"]
    assert "MARK-1 first" in d["stderr"] and "MARK-1 last" in d["stderr"] and "MARK-2" not in d["stderr"]


def test_the_block_log_holds_each_run_whole_with_its_header(overlapped):
    p, runs = overlapped
    got = entries((p.dir / "logs" / "worker.log").read_text())
    assert len(got) == 2
    item_of = {r["causedby"][:8]: r["data"]["item"].split("/")[1] for r in runs.values()}
    assert sorted(i for i, _ in got) == sorted(item_of)
    for id8, lines in got:
        me = item_of[id8]
        assert lines and all(line.startswith(f"MARK-{me} ") for line in lines), (id8, lines)


def test_finish_writes_header_and_body_in_one_locked_append(tmp_path, monkeypatch):
    p = SimpleNamespace(dir=tmp_path)
    a = runlog.open_run(p, "b", 1, "a" * 32)
    b = runlog.open_run(p, "b", 2, "b" * 32)
    a.file.write("ONE\n" * 50)
    b.file.write("TWO\n" * 50)
    paused, tried = threading.Event(), threading.Event()
    outside: list[str] = []
    real_lock, real_append, real_trim = runlog._lock, runlog._append, runlog.trim

    def lock(fd, how):
        if threading.current_thread().name == "B":
            tried.set()                                      # (B is trying the block log's lock)
        real_lock(fd, how)

    def trim(path, most):
        probe = os.open(tmp_path / "logs" / "b.log.lock", os.O_RDWR | os.O_CREAT)
        try:                                                 # held by this call, or no one: trim outside the lock
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            outside.append(threading.current_thread().name)
        except OSError:
            pass
        finally:
            os.close(probe)
        if threading.current_thread().name == "B":
            tried.set()
        real_trim(path, most)

    def append(fd, data):
        if threading.current_thread().name == "A":           # A stops between its header and its body
            head, _, body = data.partition(b"\n")
            real_append(fd, head + b"\n")
            paused.set()
            assert tried.wait(DEADLINE)
            real_append(fd, body)
        else:
            tried.set()
            real_append(fd, data)

    monkeypatch.setattr(runlog, "_lock", lock)
    monkeypatch.setattr(runlog, "trim", trim)
    monkeypatch.setattr(runlog, "_append", append)
    ta = threading.Thread(target=runlog.finish, args=(a, time.time(), "test", 5 * 2**20), name="A")
    ta.start()
    assert paused.wait(DEADLINE)
    tb = threading.Thread(target=runlog.finish, args=(b, time.time(), "test", 5 * 2**20), name="B")
    tb.start()
    ta.join(DEADLINE)
    tb.join(DEADLINE)
    a.close()
    b.close()
    got = entries((tmp_path / "logs" / "b.log").read_text())
    assert [i for i, _ in got] == ["aaaaaaaa", "bbbbbbbb"]
    assert got[0][1] == ["ONE"] * 50 and got[1][1] == ["TWO"] * 50
    assert not outside, "trimmed while the block log's lock was not held"


def test_a_long_run_output_is_copied_capped_into_the_block_log(tmp_path):
    p = SimpleNamespace(dir=tmp_path)
    cap = 10_000
    r = runlog.open_run(p, "b", 7, "c" * 32)
    r.file.write("".join(f"line {i:06d}\n" for i in range(3 * cap // 12)))
    r.file.flush()
    size = os.path.getsize(tmp_path / r.rel)
    assert size >= 3 * cap - 12
    runlog.finish(r, time.time(), "test", cap)
    r.close()
    log = (tmp_path / "logs" / "b.log").read_text()
    head, earlier, rest = log.split("\n", 2)
    assert head.startswith("--- ") and earlier == f"({size - cap} bytes earlier: {r.rel})"
    assert len(rest.encode()) == cap and len(log.encode()) <= cap + len(head) + len(earlier) + 2
    assert os.path.getsize(tmp_path / r.rel) == size, "the run's own file is left whole"


def test_two_concurrent_daemon_runs_keep_the_daemons_stderr_out_of_both_files(tmp_path):
    (tmp_path / "d.py").write_text(DAEMON)
    p = project(tmp_path, """
        blocks:
          worker:
            type: program
            takes: {kind: ticket, at: ready}
            pool: 2
            lease: {ttl: 1m, attempts: 1}
            daemon: {run: python3 d.py, concurrency: 2}
        """)
    for i in (1, 2):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t")
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        assert wait_for(lambda: len(ended(p, "worker")) >= 2)
    finally:
        e.close()
    runs = {x["data"]["item"]: x for x in ended(p, "worker")}
    assert sorted(runs) == ["ticket/1", "ticket/2"] and runs["ticket/1"]["type"] == "agent.failed"
    logs = {i: r["data"]["log"] for i, r in runs.items()}
    assert len(set(logs.values())) == 2
    for log in logs.values():
        assert "DSTDERR" not in (p.dir / log).read_text()
    daemon_log = (p.dir / "logs" / "daemon-block.worker.log").read_text()
    for r in runs.values():
        assert f"DSTDERR-{r['causedby']}" in daemon_log
    failed = p.events.query(n=None, type="ergostat.run.failed")
    assert len(failed) == 1 and failed[0]["data"]["log"] == logs["ticket/1"]
    assert "DSTDERR" not in failed[0]["data"]["stderr"] and runs["ticket/2"]["causedby"] not in failed[0]["data"]["stderr"]
    got = entries((p.dir / "logs" / "worker.log").read_text())
    assert sorted(i for i, _ in got) == sorted(r["causedby"][:8] for r in runs.values())
    assert not any("DSTDERR" in line for _, lines in got for line in lines)


def make(d: Path, seq: int, mtime: float | None = None) -> str:
    name = f"{seq}-{seq:012x}.log"
    (d / name).write_text(f"run {seq}\n")
    if mtime is not None:
        os.utime(d / name, (mtime, mtime))
    return name


def test_prune_keeps_the_newest_by_start_seq_not_mtime_or_name(tmp_path):
    p = SimpleNamespace(dir=tmp_path)
    d = tmp_path / "logs" / "runs" / "b"
    d.mkdir(parents=True)
    now = time.time()
    names = {seq: make(d, seq, now - seq) for seq in (9, 10, 20, 100)}   # (the oldest seq has the newest mtime)
    (d / "notes.txt").write_text("not ergostat's")
    (d / ".lock").write_text("")
    gone = runlog.prune(p, "b", 2)
    assert sorted(gone) == sorted([names[9], names[10]])
    assert sorted(os.listdir(d)) == sorted([".lock", "notes.txt", names[20], names[100]])


def test_prune_skips_a_running_runs_file_among_the_oldest(tmp_path):
    p = SimpleNamespace(dir=tmp_path)
    live = runlog.open_run(p, "b", 1, "1" * 32)              # a run still going: its shared lock held
    for seq in (2, 3):
        runlog.open_run(p, "b", seq, f"{seq}" * 32).close()
    d = tmp_path / "logs" / "runs" / "b"
    try:
        gone = runlog.prune(p, "b", 1)
        assert gone == [f"2-{'2' * 12}.log"]
        assert sorted(x for x in os.listdir(d) if x != ".lock") == [f"1-{'1' * 12}.log", f"3-{'3' * 12}.log"]
    finally:
        live.close()


def test_a_run_starting_during_the_prune_is_not_pruned(tmp_path, monkeypatch):
    """A run with an old start seq (beyond runs: 1) stopped between its file's create and its shared lock, while a prune
    runs on another thread: the prune waits for the directory's lock, then finds the file locked and keeps it."""
    p = SimpleNamespace(dir=tmp_path)
    for seq in (50, 60):
        runlog.open_run(p, "b", seq, f"{seq:032x}").close()
    at_lock, done = threading.Event(), threading.Event()
    result: dict = {}
    real_lock = runlog._lock

    def lock(fd, how):
        if threading.current_thread().name == "prune":
            at_lock.set()
        real_lock(fd, how)

    def prune():
        try:
            result["gone"] = runlog.prune(p, "b", 1)
        finally:
            done.set()

    t = threading.Thread(target=prune, name="prune")

    def created(name):                                       # the prune started in the window
        t.start()
        end = time.time() + DEADLINE
        while not (at_lock.is_set() or done.is_set()) and time.time() < end:
            done.wait(0.01)
        assert at_lock.is_set() or done.is_set()

    monkeypatch.setattr(runlog, "_lock", lock)
    monkeypatch.setattr(runlog, "_created", created)
    r = runlog.open_run(p, "b", 5, "5" * 32)
    t.join(DEADLINE)
    try:
        d = tmp_path / "logs" / "runs" / "b"
        assert (d / r.name).exists(), "the new run's file was pruned while it was being made"
        assert result["gone"] == [f"50-{'0' * 12}.log"]
    finally:
        r.close()


def test_an_existing_name_or_link_at_the_run_file_falls_back_and_writes_nothing_through_it(tmp_path):
    p = SimpleNamespace(dir=tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("untouched\n")
    d = tmp_path / "logs" / "runs" / "b"
    d.mkdir(parents=True)
    rid = "d" * 32
    (d / f"8-{rid[:12]}.log").symlink_to(outside)
    r = runlog.open_run(p, "b", 8, rid)
    r.file.write("the run's line\n")
    runlog.finish(r, time.time(), "test", 2**20)
    r.close()
    assert r.name == f"8-{rid[:12]}-2.log" and (d / r.name).read_text() == "the run's line\n"
    assert outside.read_text() == "untouched\n"
    for i in range(2, 10):                                   # every name taken: the last, then none
        (d / f"9-{rid[:12]}-{i}.log").write_text("")
    (d / f"9-{rid[:12]}.log").write_text("")
    r = runlog.open_run(p, "b", 9, rid)
    assert r.name == f"run-9-{rid}.log"
    r.close()
    (d / f"run-9-{rid}.log").unlink()
    (d / f"run-9-{rid}.log").symlink_to(outside)
    with pytest.raises(runlog.RunLogError):
        runlog.open_run(p, "b", 9, rid)
    assert outside.read_text() == "untouched\n"


def test_an_unsafe_run_log_path_refuses_the_run_and_writes_nothing_outside(tmp_path):
    (tmp_path / "w.py").write_text("import pathlib, sys\nsys.stdin.read()\npathlib.Path('ran').write_text('x')\n")
    p = project(tmp_path, """
        blocks:
          worker:
            type: program
            every: 1h
            run: python3 w.py
        """)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (p.dir / "logs" / "runs").mkdir(parents=True)
    (p.dir / "logs" / "runs" / "worker").symlink_to(outside)
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks["worker"], "test")
    got = ended(p, "worker")
    assert len(got) == 1 and got[0]["type"] == "agent.failed", got
    assert got[0]["data"]["note"].startswith("could not start: its run log"), got[0]["data"]
    assert "log" not in got[0]["data"]
    assert not (tmp_path / "ran").exists(), "the program ran"
    assert list(outside.iterdir()) == []
    fails = its.project(p.events, p.model.spec, FAILURE)
    assert len(fails) == 1 and fails[0].state == "noted"
    for bad in ("../x", "a/b", "Up", ".hidden", "a..b", "x" * 129):
        with pytest.raises(runlog.RunLogError):
            runlog.open_run(SimpleNamespace(dir=tmp_path), bad, 1, "e" * 32)
    with pytest.raises(runlog.RunLogError, match="no start seq"):
        runlog.open_run(SimpleNamespace(dir=tmp_path), "ok", None, "e" * 32)


def test_storage_logs_runs_has_a_floor_and_a_ceiling():
    from ergostat.storage import parse
    for bad in (0, 5000, -1, "lots", True):
        problems: list[str] = []
        parse({"logs": {"runs": bad}}, problems)
        assert problems and "storage.logs.runs" in problems[0], bad
    problems = []
    assert parse({"logs": {"runs": 10}}, problems).logs["runs"] == 10 and not problems
    assert parse(None, problems).logs["runs"] == 50
    assert runlog.keep(0) == 1 and runlog.keep(5000) == 1000 and runlog.keep(None) == 50 and runlog.keep(10) == 10
    problems = []
    parse({"logs": {"nope": 1}}, problems)
    assert "runs" in problems[0]
