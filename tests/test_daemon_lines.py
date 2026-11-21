"""A daemon's lines taken per read, batched per run (SPEC §9.7): ``lines.plan`` and ``Process.chunk``, given reads whose
contents are known (a real pipe may split 1,200 lines into reads of fewer than 500, and then a cap test cannot fail)."""

import json
import os
import signal

import pytest

from ergostat.daemons import lines
from ergostat.daemons.proc import LINE_MAX, Handle, Process
from ergostat.spec.ir import Daemon


def run_line(run, i, **more) -> str:
    return json.dumps({"event": "x.seen", "data": {"i": i}, "run": run, **more})


def taken(steps):
    return [(s[1], [json.loads(x)["data"]["i"] for x in s[2]]) for s in steps if s[0] == "take"]


@pytest.fixture
def proc(tmp_path):
    log = open(tmp_path / "log", "a")
    p = Process(Daemon("x", "python3 -c 'import time; time.sleep(30)'"), tmp_path, dict(os.environ), log,
                lambda *a: False)
    p.logfile = tmp_path / "log"
    yield p
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass
    p.ended.wait(5)
    log.close()


def held(p, run):
    calls = []
    h = Handle(take=lambda got: calls.append((list(got), h.done.is_set())))
    p.hold(run, h, {"op": "noop"})
    return h, calls


def logged(p) -> str:
    p.log.flush()
    return p.logfile.read_text()


def test_one_reads_1200_lines_of_a_run_are_taken_as_500_500_200(proc):
    texts = [run_line("A", i) for i in range(1200)]
    steps = lines.plan(texts)
    assert [len(s[2]) for s in steps] == [500, 500, 200]
    assert [i for _, got in taken(steps) for i in got] == list(range(1200)), "in the order printed"
    assert all("run" not in json.loads(x) for s in steps for x in s[2]), "each line with run removed, as line does"
    h, calls = held(proc, "A")
    proc.chunk("".join(t + "\n" for t in texts).encode())
    assert [len(c) for c, _ in calls] == [500, 500, 200]
    assert [json.loads(x)["data"]["i"] for c, _ in calls for x in c] == list(range(1200))


def test_interleaved_runs_lines_are_batched_per_run_in_order():
    texts = [run_line(r, i) for i in range(10) for r in "AB"]
    assert taken(lines.plan(texts)) == [("A", list(range(10))), ("B", list(range(10)))]


def test_a_run_line_is_what_line_takes_and_every_other_line_is_one():
    """The ``run`` key wins, as in Process.line: a request or a reading tagged with a run is the run's line."""
    req = json.dumps({"request": "q1", "reading": 3, "run": "A"})
    others = ['{"heartbeat": true}', "not json", '{"request": "q1", "reading": 3}', '{"reading": 1, "sensor": "q.m"}',
              '{"event": "x.seen", "item": "c/a", "sensor": "q.m"}', '{"event": "x.seen"}',
              '{"event": "x.seen", "run": 7}', '{"done": 0, "run": 7}', "[1]"]
    steps = lines.plan([req, *others])
    assert steps == [("one", x) for x in others] + [("take", "A", [json.dumps({"request": "q1", "reading": 3})])]


def test_a_runs_done_comes_after_its_lines_in_the_same_read(proc):
    ha, a = held(proc, "A")
    hb, b = held(proc, "B")
    chunk = [run_line("A", 1), run_line("B", 1), json.dumps({"done": 0, "run": "A"}), run_line("A", 2)]
    steps = lines.plan(chunk)
    assert [s[0] for s in steps] == ["take", "one", "take", "take"]
    proc.chunk("".join(x + "\n" for x in chunk).encode())
    assert [[json.loads(x)["data"]["i"] for x in c] for c, _ in a] == [[1]]
    assert a[0][1] is False, "A's line was taken before its done"
    assert ha.done.is_set() and ha.code == 0
    assert [[json.loads(x)["data"]["i"] for x in c] for c, _ in b] == [[1]]
    assert "no run of that id held" in logged(proc) and '"i": 2' in logged(proc), "A2-late: stray"


def test_a_partial_line_waits_for_the_rest_and_eof_takes_the_last(proc):
    h, calls = held(proc, "A")
    whole = run_line("A", 1).encode()
    proc.chunk(whole[:17])
    assert calls == [] and proc.partial == whole[:17]
    proc.chunk(whole[17:] + b"\n")
    assert [[json.loads(x)["data"]["i"] for x in c] for c, _ in calls] == [[1]], "taken once, whole"
    proc.chunk(b'{"event": "x.bytes", "data": {"s": "a\xffb"}, "run": "A"}\n')   # (not UTF-8: replaced, taken)
    assert json.loads(calls[-1][0][0])["data"]["s"] == "a�b"
    proc.chunk(run_line("A", 2).encode())
    assert len(calls) == 2
    proc.chunk(b"", eof=True)
    assert json.loads(calls[-1][0][0])["data"]["i"] == 2 and proc.partial == b""


def test_an_overlong_line_is_dropped_and_the_reader_goes_on(proc):
    h, calls = held(proc, "A")
    for _ in range(32):                              # 2 MiB with no newline, as 64 KiB reads
        proc.chunk(b"x" * 65536)
        assert len(proc.partial) <= LINE_MAX
    proc.chunk(b"x" * (2 << 20))                     # (and again, all in one)
    assert len(proc.partial) <= LINE_MAX
    proc.chunk(b"yyy\n" + run_line("A", 1).encode() + b"\n")
    assert [[json.loads(x)["data"]["i"] for x in c] for c, _ in calls] == [[1]]
    assert logged(proc).count("a line over 1 MiB") == 1, "said once, the rest up to its newline discarded"


def test_a_take_that_raises_drops_its_batch_and_the_reader_goes_on(proc):
    calls = []

    def take(got):
        calls.append(list(got))
        if len(calls) == 1:
            raise RuntimeError("its log closed")
    proc.hold("A", Handle(take=take), {"op": "noop"})
    proc.chunk("".join(run_line("A", i) + "\n" for i in range(3)).encode())
    assert logged(proc).count("dropped (RuntimeError: its log closed)") == 3
    proc.chunk((run_line("A", 9) + "\n").encode())
    assert len(calls) == 2 and json.loads(calls[1][0])["data"]["i"] == 9
    assert proc.recycle is None, "not the daemon's fault"
