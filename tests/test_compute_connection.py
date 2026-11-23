"""The engine's session with each node of a pool (SPEC §12s.4): in service on a good hello, lost at the session's end
or after three beats missed, back with backoff, refused on another protocol version with the error kept, and every
session ended with the engine, with no host name in the log, the record or what the engine says."""

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

import ergostat
from ergostat import model as mdl
from ergostat.compute import connection as cx
from ergostat.spec.ir import ComputePool

from .test_leases import project, wait_for

WORKER = str(Path(ergostat.__file__).parent / "compute" / "worker")


def worker(root, beat=10.0) -> list[str]:
    return [sys.executable, "-I", WORKER, "--stdio", "--root", str(root), "--beat", str(beat)]


def node(tmp_path, argv, beat=cx.BEAT, first=cx.FIRST, labels=None):
    seen = []
    pool = ComputePool("farm", [{"connect": argv}], labels=labels or {})
    n = cx.Node(pool, 1, tmp_path / "farm.log", lambda kind, data, said: seen.append((kind, data)), beat, first)
    return n.start(), seen


def gone(pid) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def up(n, seconds=15.0):
    assert wait_for(lambda: n.state == "in-service", seconds), n.status()
    return n.proc.pid


def test_node_in_service(tmp_path):
    n, seen = node(tmp_path, worker(tmp_path / "r", beat=0.2))
    beats = []
    n.on("beat", lambda node, f: 1 / 0)                                    # a handler's fault: said, the session on
    n.on("beat", lambda node, f: beats.append(f))
    try:
        up(n)
        assert n.status()["slots"] == n.hello["slots"] and n.name == "farm/1"
        got = n.request({"type": "ping"}, timeout=10)
        assert got["type"] == "pong" and type(got["id"]) is int
        assert wait_for(lambda: len(beats) >= 2, 10) and n.state == "in-service"
        assert "farm/1 beat handler failed: ZeroDivisionError" in (tmp_path / "farm.log").read_text()
        assert seen[0] == ("compute.node.up", {"node": "farm/1", "slots": n.hello["slots"]})
    finally:
        n.close()
        n.thread.join(10)
    assert n.state == "closed" and not n.thread.is_alive()
    with pytest.raises(cx.Lost):
        n.request({"type": "ping"})
    said, pools = [], cx.Pools(None, lambda s: said.append(s))                # past 64 nodes at run time: none started
    pools.sync({"big": ComputePool("big", [{"connect": ["false"]}] * (cx.MAX_NODES + 1))})
    assert pools.nodes == {} and said == ["compute big: not connected: past 64 nodes, counting those closing"]


def test_lost_on_eof(tmp_path):
    n, seen = node(tmp_path, worker(tmp_path / "r"), first=60)     # (beats of 10 s: lost by the end, never by beats)
    try:
        pid = up(n)
        os.kill(pid, signal.SIGKILL)
        assert wait_for(lambda: n.state == "lost", 10), n.status()
        assert n.error == "the session ended" and n.status()["slots"] == 0
        assert ("compute.node.lost", {"node": "farm/1", "why": "the session ended"}) in seen
        with pytest.raises(cx.Lost):
            n.request({"type": "ping"})
    finally:
        n.close()
        n.thread.join(10)


def test_lost_after_three_missed_beats(tmp_path):
    n, _ = node(tmp_path, worker(tmp_path / "r", beat=0.2), beat=1.0, first=60)
    try:
        pid = up(n)
        os.kill(pid, signal.SIGSTOP)
        stopped = time.monotonic()
        assert wait_for(lambda: n.state == "lost", 15), n.status()
        assert time.monotonic() - stopped >= 3 * 1.0 - 0.3                # (three beats, less the one heard last)
        assert n.error == "3 beats missed"
        assert wait_for(lambda: gone(pid), 10)                             # the stopped worker killed, and reaped
    finally:
        n.close()
        n.thread.join(10)


def test_backoff_and_return(tmp_path):
    assert [cx.backoff(i) for i in (0, 1, 2, 9, 10, 99)] == [1, 2, 4, 512, 600, 600]
    tries, ok = tmp_path / "tries", tmp_path / "ok"
    script = (f"import os, sys, time\nopen({str(tries)!r}, 'a').write(repr(time.monotonic()) + '\\n')\n"
              f"os.path.exists({str(ok)!r}) or sys.exit(1)\n"
              f"os.execv(sys.executable, {worker(tmp_path / 'r')!r})\n")
    n, seen = node(tmp_path, [sys.executable, "-I", "-c", script], first=0.2)
    try:
        assert wait_for(lambda: tries.exists() and len(tries.read_text().split()) >= 4, 15)
        at = [float(x) for x in tries.read_text().split()]
        gaps = [b - a for a, b in zip(at, at[1:], strict=False)]
        assert all(g >= cx.backoff(i, 0.2) for i, g in enumerate(gaps[:3])), gaps          # 0.2, 0.4, 0.8 at least
        assert n.state == "lost" and n.tries >= 3
        assert [k for k, _ in seen].count("compute.node.lost") == 1                         # said once, not each try
        ok.touch()
        up(n, 30)
        assert n.tries == 0 and n.error is None and n.request({"type": "ping"}, timeout=10)["type"] == "pong"
    finally:
        n.close()
        n.thread.join(10)


def test_another_version_is_refused_with_its_error_kept(tmp_path):
    hello = {"v": 2, "seq": 1, "type": "hello", "slots": 4, "labels": {}}
    fake = f"import sys\nprint({json.dumps(hello)!r}, flush=True)\nsys.stdin.read()\n"
    n, seen = node(tmp_path, [sys.executable, "-I", "-c", fake], first=0.1)
    try:
        assert wait_for(lambda: n.state == "refused" and n.tries >= 2, 15), n.status()
        assert n.status() == {"node": "farm/1", "state": "refused", "error": "line 1: protocol v2 is not v1",
                              "slots": 0}
        assert [k for k, _ in seen] == ["compute.node.refused"]
        with pytest.raises(cx.Lost):
            n.request({"type": "ping"})
    finally:
        n.close()
        n.thread.join(10)
    m, _ = node(tmp_path, worker(tmp_path / "r"), labels={"gpu": "a100"}, first=60)    # labels lacking: not used
    try:
        assert wait_for(lambda: m.state == "refused", 15) and m.error == "its labels lack the pool's gpu"
    finally:
        m.close()
        m.thread.join(10)


def test_engine_starts_and_closes_every_session_and_never_names_a_host(tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "ssh").write_text('#!/bin/sh\necho "ssh: connect to host $4 port 22: Connection refused" >&2\nexit 255\n')
    (bin_ / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    argv = json.dumps(worker(tmp_path / "r"))
    p = project(tmp_path, f"""\
        name: t
        stocks:
          queue: {{unit: items}}
        compute:
          farm:
            nodes: [{{connect: {argv}}}, {{connect: {argv}}}, {{ssh: Secret-Host}}]
        """)
    from ergostat.spec.engine import Engine
    said = []
    e = Engine(p, say=said.append)
    e.start_all()
    try:
        nodes = e.compute.nodes
        assert sorted(nodes) == ["farm/1", "farm/2", "farm/3"]
        pids = [up(nodes[k]) for k in ("farm/1", "farm/2")]
        log = Path(p.dir) / "logs" / "compute.farm.log"
        assert wait_for(lambda: log.exists() and "farm/3 ssh: connect to host farm/3" in log.read_text(), 15)
        assert nodes["farm/3"].state == "lost"
        e.swap(mdl.load(tmp_path))                                          # the same pools: the same sessions
        assert e.compute.nodes == nodes and [nodes[k].proc.pid for k in ("farm/1", "farm/2")] == pids
    finally:
        e.close()
    assert all(not n.thread.is_alive() and n.proc is None for n in nodes.values())
    assert all(gone(pid) for pid in pids)
    text = log.read_text() + json.dumps(p.events.query(n=1000)) + "\n".join(said)
    assert "compute.node.up" in text and "secret-host" not in text.lower()
    plain = tmp_path / "plain"
    plain.mkdir()
    q = project(plain, "name: t\nstocks:\n  queue: {unit: items}\n")
    f = Engine(q, say=lambda s: None)
    f.start_all()
    try:
        assert f.compute is None                                            # a model without pools: nothing started
        (plain / "ergostat.yaml").write_text((tmp_path / "ergostat.yaml").read_text().replace(", {ssh: Secret-Host}",
                                                                                              ""))
        f.swap(mdl.load(plain))                                             # pools swapped in: connected
        pid = up(f.compute.nodes["farm/1"])
        one = f.compute.nodes["farm/1"]
        (plain / "ergostat.yaml").write_text("name: t\nstocks:\n  queue: {unit: items}\n")
        f.swap(mdl.load(plain))                                             # and swapped out: closed
        assert f.compute.nodes == {} and wait_for(lambda: gone(pid) and not one.thread.is_alive(), 10)
    finally:
        f.close()
