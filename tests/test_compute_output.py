"""A node run's output by offset (SPEC §12s.3): ``out`` frames cover each stream once, in order, by the offset of
their first byte; ``attach`` resends from given offsets and the engine's rule (``compute_pipe.Taken``) records a
resend once; a line over 64 KiB is split and rejoins exactly; at most 4 MiB goes unacknowledged; a stream past
``limits.log`` stops its run; ``ended`` follows the last ``out``; ``done`` lets the keeper remove the folder. At most
8 processes a test, each group killed at the end."""

from __future__ import annotations

import subprocess
import time
import uuid

import pytest

from tests.compute_pipe import Node, Taken, alive, until

LINE, AHEAD = 1 << 16, 4 << 20


@pytest.fixture
def node(tmp_path):
    n = Node(tmp_path, "--beat", "0.1")
    yield n
    n.end()


def _bytes(f: dict) -> bytes:
    return f["text"].encode("utf-8", "surrogateescape")


def _outs(node: Node, run: str, stream: str) -> list[dict]:
    return [f for f in node.heard if f["type"] == "out" and f["run"] == run and f["stream"] == stream]


def _joined(frames: list[dict], start: int = 0) -> bytes:
    """The frames' bytes, each frame starting exactly where the one before ended (else the assertion fails)."""
    got, at = [], start
    for f in frames:
        assert f["offset"] == at, (f["offset"], at)
        got.append(_bytes(f))
        at += len(got[-1])
    return b"".join(got)


def _end(frames: list[dict]) -> int:
    return frames[-1]["offset"] + len(_bytes(frames[-1])) if frames else 0


def _drain(node: Node, quiet: float = 0.5, most: float = 30.0) -> None:
    """Frames read into ``heard`` until none but beats come for ``quiet`` seconds."""
    end, last = time.monotonic() + most, time.monotonic()
    while (now := time.monotonic()) < end and now - last < quiet and (f := node.w.read(quiet)) is not None:
        node.heard.append(f)
        if f["type"] != "beat":
            last = time.monotonic()


def _ended(node: Node, run: str) -> list[dict]:
    return [f for f in node.heard if f["type"] == "ended" and f["run"] == run]


def _acking(node: Node, run: str, most: float = 60.0) -> None:
    """The engine taking all it is sent, an ``ack`` at a time, until the run's ``ended``."""
    end = time.monotonic() + most
    while not _ended(node, run) and time.monotonic() < end:
        top = {k: _end(_outs(node, run, k)) for k in ("out", "err")}
        node.tell("ack", run=run, **top)
        _drain(node, 0.3, 5)
        assert _end(_outs(node, run, "out")) - top["out"] <= AHEAD    # (never 4 MiB past what was taken)
    assert _ended(node, run)


def _rss(pid: int) -> int:
    return int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=10).stdout) * 1024


def test_lines_by_offset_once(node):
    run, got = node.start("seq -f 'line %g' 1 10000; echo oops >&2; printf 'no end'")
    assert got["type"] == "started"
    ended = node.hear("ended", run=run, timeout=30)
    assert {k: ended[k] for k in ("code", "how")} == {"code": 0, "how": "exit"}
    out, err = _outs(node, run, "out"), _outs(node, run, "err")
    taken = Taken()
    assert all(taken.take(f) for f in out + err)       # each frame new: none resent, none past a gap
    data = (node.dir(run) / "out").read_bytes()
    assert _joined(out) == data == taken.bytes(run, "out") and _joined(err) == b"oops\n"
    assert [f["text"] for f in out[:2]] == ["line 1\n", "line 2\n"] and len(out) == 10001
    assert out[-1]["text"] == "no end" and all(f["text"].endswith("\n") for f in out[:-1])   # (whole lines first)
    node.tell("ack", run=run, out=len(data), err=5)    # the beat says what was taken
    assert until(lambda: (node.hear("beat")["runs"].get(run) == {"out": len(data), "err": 5}), 5)
    assert node.ask("ack", run=uuid.uuid4().hex, out=0, err=0)["why"] == "no such run"
    assert node.ask("ack", run=run, out="7", err=0)["type"] == "error"


def test_attach_resumes_from_offset(node):
    run, _ = node.start("seq -f 'n%g' 1 1000; echo e >&2")
    node.hear("ended", run=run, timeout=30)
    taken = Taken()
    for f in _outs(node, run, "out") + _outs(node, run, "err"):
        taken.take(f)
    mid = _outs(node, run, "out")[500]["offset"]
    assert _outs(node, run, "out")[500]["text"] == "n501\n"
    node.w.close()                                      # a new session: nothing sent for the run until attached
    node.connect("--beat", "0.1")
    _drain(node, 0.5, 2)
    assert not [f for f in node.heard if f["type"] in ("out", "ended")]
    node.tell("attach", run=run, out=mid, err=0)
    ended = node.hear("ended", run=run, timeout=30)
    again = _outs(node, run, "out")
    data = (node.dir(run) / "out").read_bytes()
    assert again[0]["offset"] == mid and _joined(again, mid) == data[mid:] and len(again) == 500
    assert not [f for f in again + _outs(node, run, "err") if taken.take(f)]     # a resend, recorded once
    assert taken.bytes(run, "out") == data and taken.bytes(run, "err") == b"e\n" and ended["how"] == "exit"
    assert node.ask("attach", run=run, out=len(data) + 1, err=0)["why"] == "offset past the output"
    assert node.ask("attach", run=uuid.uuid4().hex, out=0, err=0)["why"] == "no such run"
    assert node.ask("attach", run="../x", out=0, err=0)["why"] == "no such run"
    assert node.ask("attach", run=run, out=-1, err=0)["type"] == "error"
    assert node.ask("attach", run=run, out=True, err=0)["type"] == "error"


def test_long_line_split(node):
    x = "head -c {} /dev/zero | tr '\\0' x"
    run, _ = node.start(f"{x.format(LINE - 1)}; printf '\\303\\251'; {x.format(140000)}; printf '\\377\\n'; echo ok")
    node.hear("ended", run=run, timeout=30)
    out = _outs(node, run, "out")
    data = (node.dir(run) / "out").read_bytes()
    assert _joined(out) == data and len(data) == LINE + 1 + 140000 + 2 + 3
    assert [len(_bytes(f)) for f in out] == [LINE, LINE, LINE, 140003 - 2 * LINE, 3]   # split at the limit
    assert out[0]["text"].endswith("x\udcc3") and out[1]["text"].startswith("\udca9")  # (é cut: bytes kept)
    assert out[-1]["text"] == "ok\n"


def test_backpressure_window(node):
    size = 24 << 20                                     # 4,000-byte lines, six times what may be unacknowledged
    base = _rss(node.w.p.pid)
    run, _ = node.start(f"yes \"$(head -c 3999 /dev/zero | tr '\\0' a)\" | head -c {size}")
    assert node.exit(run, 30)["how"] == "exit"
    _drain(node, 1.0)
    sent = _end(_outs(node, run, "out"))
    rss = _rss(node.w.p.pid)
    assert AHEAD - LINE < sent <= AHEAD, sent
    assert rss - base < 12 << 20, (base, rss)           # the worker holds no backlog (24 MiB written)
    assert not _ended(node, run)
    node.tell("ack", run=run, out=size, err=0)          # past what was sent: no room counted
    _drain(node, 0.5, 2)
    assert _end(_outs(node, run, "out")) == sent
    most, end = rss, time.monotonic() + 60
    while not _ended(node, run) and time.monotonic() < end:
        top = _end(_outs(node, run, "out"))
        node.tell("ack", run=run, out=top, err=0)
        _drain(node, 0.3, 5)
        most = max(most, _rss(node.w.p.pid))
        assert _end(_outs(node, run, "out")) - top <= AHEAD
    out = _outs(node, run, "out")
    assert _end(out) == size and _joined(out) == (node.dir(run) / "out").read_bytes()
    assert most - base < 12 << 20, (base, rss, most)    # (measured: 21 MiB from the start, not moving)


def test_log_cap_stops_run(node):
    cap = 1 << 20
    run, got = node.start("while :; do echo 0123456789012345678901234567890123456789; done", limits={"log": cap})
    assert got["type"] == "started"
    ended = node.hear("ended", run=run, timeout=30)
    assert ended["how"] == "log over its cap" and ended["code"] < 0
    assert node.exit(run)["how"] in ("TERM", "KILL") and (node.dir(run) / "out").stat().st_size > cap
    assert len(_joined(_outs(node, run, "out"))) <= cap
    for log in (0, (1 << 30) + 1, "1g"):
        assert node.start("true", limits={"log": log})[1]["why"] == "limits over the node", log
    quiet, _ = node.start("echo fine", limits={"log": 5})
    assert node.hear("ended", run=quiet)["how"] == "exit"    # (exactly the cap: not over it)


def test_ended_after_last_out(node):
    size = 6 << 20                                      # more than may go unacknowledged: the run ends with output
    run, _ = node.start(f"yes \"$(head -c 999 /dev/zero | tr '\\0' b)\" | head -c {size}; echo last >&2")
    node.exit(run, 30)                                  # ...still unsent, so its ended waits for the engine
    _drain(node, 0.5)
    assert not _ended(node, run)
    _acking(node, run)
    out, err, ended = _outs(node, run, "out"), _outs(node, run, "err"), _ended(node, run)[0]
    assert _end(out) == size and _joined(err) == b"last\n" and ended["how"] == "exit"
    assert node.heard.index(ended) > max(node.heard.index(f) for f in out + err)
    killed, got = node.start("echo before; echo also >&2; sleep 30")
    node.hear("out", run=killed, stream="err")
    assert node.ask("kill", run=killed, grace=5)["type"] == "stopping"
    ended = node.hear("ended", run=killed)
    assert ended["how"] == "TERM" and node.heard.index(ended) > node.heard.index(_outs(node, killed, "out")[-1])
    node.tell("done", run=killed)                       # done: the keeper removes the folder and ends
    assert until(lambda: not node.dir(killed).exists()) and until(lambda: not alive(got["keeper"]))
    node.hear("beat")
    assert killed not in node.hear("beat")["runs"]
    assert node.ask("done", run=killed)["why"] == "no such run"
    assert node.ask("done", run="x" * 32)["why"] == "no such run"
