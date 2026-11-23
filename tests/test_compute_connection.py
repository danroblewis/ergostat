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


def node(tmp_path, argv, beat=cx.BEAT, first=cx.FIRST, labels=None, ping=cx.PING):
    seen = []
    pool = ComputePool("farm", [{"connect": argv}], labels=labels or {})
    n = cx.Node(pool, 1, tmp_path / "farm.log", lambda kind, data, said: seen.append((kind, data)), beat, first, ping)
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


def test_lost_on_eof(tmp_path, monkeypatch):
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
    tries = tmp_path / "tries"                      # a later line nested past the parser's depth: lost, tried again
    hello = {"v": 1, "seq": 1, "type": "hello", "slots": 4, "labels": {}}
    script = (f"import os, sys, time\nopen({str(tries)!r}, 'a').write(repr(time.monotonic()) + '\\n')\n"
              f"len(open({str(tries)!r}).read().split()) < 5 or os.execv(sys.executable, "
              f"{worker(tmp_path / 'r', beat=0.2)!r})\n"                 # (the fifth try holds)
              f"sys.stdout.write({json.dumps(hello)!r} + '\\n' + '[' * 200000 + '\\n')\n"
              "sys.stdout.flush()\ntime.sleep(60)\n")
    n, seen = node(tmp_path, [sys.executable, "-I", "-c", script], beat=1.0, first=0.2)
    lost = [("compute.node.up", {"node": "farm/1", "slots": 4}),
            ("compute.node.lost", {"node": "farm/1", "why": "line 2: not JSON"})]
    try:
        assert wait_for(lambda: tries.exists() and len(tries.read_text().split()) >= 5, 20), n.status()
        at = [float(x) for x in tries.read_text().split()]
        gaps = [b - a for a, b in zip(at, at[1:], strict=False)]
        assert all(g >= cx.backoff(i, 0.2) for i, g in enumerate(gaps)), gaps            # a hello is no reset
        assert n.tries == 4 and seen == lost, seen                                        # said once, not each try
        up(n)
        assert seen == lost                         # (a retry's hello is said once it holds three beats)
        assert wait_for(lambda: len(seen) == 3, 10) and n.tries == 0, seen
        assert seen[2] == ("compute.node.up", {"node": "farm/1", "slots": n.hello["slots"]})
        assert time.monotonic() - at[4] >= 3 * 1.0 and n.thread.is_alive()
    finally:
        n.close()
        n.thread.join(10)

    def full(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(cx.tempfile, "TemporaryFile", full)        # no temp file for stderr: lost, tried again
    n, seen = node(tmp_path, worker(tmp_path / "r"), first=0.2)
    try:
        assert wait_for(lambda: n.tries >= 2, 15), n.status()
        assert n.state == "lost" and n.error == "the session failed: OSError" and n.thread.is_alive()
        assert seen == [("compute.node.lost", {"node": "farm/1", "why": "the session failed: OSError"})]
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
              f"os.execv(sys.executable, {worker(tmp_path / 'r', beat=0.2)!r})\n")
    n, seen = node(tmp_path, [sys.executable, "-I", "-c", script], beat=1.0, first=0.2)
    try:
        assert wait_for(lambda: tries.exists() and len(tries.read_text().split()) >= 4, 15)
        at = [float(x) for x in tries.read_text().split()]
        gaps = [b - a for a, b in zip(at, at[1:], strict=False)]
        assert all(g >= cx.backoff(i, 0.2) for i, g in enumerate(gaps[:3])), gaps          # 0.2, 0.4, 0.8 at least
        assert n.state == "lost" and n.tries >= 3
        assert [k for k, _ in seen].count("compute.node.lost") == 1                         # said once, not each try
        ok.touch()
        up(n, 30)
        assert n.tries >= 3 and [k for k, _ in seen] == ["compute.node.lost", "compute.node.up"]   # up said at once
        assert wait_for(lambda: n.tries == 0, 10), n.status()       # the wait starts again once it held three beats
        assert n.error is None and n.request({"type": "ping"}, timeout=10)["type"] == "pong"
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
    home = "the root /home/alice/.local/state/ergostat-worker can't be made: [Errno 28] '/home/alice/x'"
    for first, why in (({"v": 1, "seq": 1, "type": "error", "id": None, "why": home}, "the worker refused; its "
                        "reason is not kept"), ({"v": "/home/alice", "seq": 1, "type": "hello"}, "line 1: its "
                        "protocol is not v1"), ({"v": 1, "seq": 1, "type": "alice"}, "its first line is not hello")):
        said = []
        fake = f"import sys\nprint({json.dumps(first)!r}, flush=True)\nsys.stdin.read()\n"
        pool = ComputePool("farm", [{"connect": [sys.executable, "-I", "-c", fake]}])
        r = cx.Node(pool, 1, tmp_path / "home.log", lambda kind, data, s, said=said: said.append((kind, data, s)),
                    first=60)
        r.start()
        try:
            assert wait_for(lambda r=r: r.state == "refused", 15) and r.error == why, r.status()
        finally:
            r.close()
            r.thread.join(10)
        r._note("ended")                                                   # (the log exists, whatever was kept)
        text = json.dumps(said) + json.dumps(r.status()) + (tmp_path / "home.log").read_text()
        assert said and "alice" not in text                               # the record, what is said, the log


def test_engine_starts_and_closes_every_session_and_never_names_a_host(tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "ssh").write_text('#!/bin/sh\necho "ssh: connect to host 10.1.2.3 port 22: Connection refused" >&2\n'
                              'echo "ssh: Could not resolve hostname real.example.com: Name or service not known" >&2\n'
                              'echo "alice@real.example.com: Permission denied (publickey)." >&2\n'
                              'echo "debug1: $4" >&2\nexit 255\n')       # (what ssh says once it reads its config)
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
        assert wait_for(lambda: log.exists() and "farm/3 ssh exited 255; its standard error is not kept"
                        in log.read_text(), 15)
        assert nodes["farm/3"].state == "lost"
        e.swap(mdl.load(tmp_path))                                          # the same pools: the same sessions
        assert e.compute.nodes == nodes and [nodes[k].proc.pid for k in ("farm/1", "farm/2")] == pids
    finally:
        e.close()
    assert all(not n.thread.is_alive() and n.proc is None for n in nodes.values())
    assert all(gone(pid) for pid in pids)
    text = log.read_text() + json.dumps(p.events.query(n=1000)) + "\n".join(said)
    assert "compute.node.up" in text
    assert not [w for w in ("secret-host", "10.1.2.3", "real.example.com", "alice") if w in text.lower()]
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


def test_round_trips_measured(tmp_path):
    hello = {"v": 1, "seq": 1, "type": "hello", "slots": 2, "labels": {}}
    mute = f"import sys\nprint({json.dumps(hello)!r}, flush=True)\nsys.stdin.read()\n"    # (in service, never a pong)
    n, _ = node(tmp_path, [sys.executable, "-I", "-c", mute], ping=0.05, first=60)
    try:
        up(n)
        time.sleep(0.5)
        assert n.least_rtt() is None and n.pending                     # a ping sent, none answered: no value yet
    finally:
        n.close()
        n.thread.join(10)
    n, _ = node(tmp_path, worker(tmp_path / "r", beat=0.2), ping=0.05, first=60)
    try:
        pid = up(n)
        assert wait_for(lambda: len(n.rtts) >= 5, 10), n.status()       # a ping each interval, each pong timed
        now = time.monotonic()
        with n.lock:
            least = min(r for _, r in n.rtts)
            n.rtts.append((now - 120, least / 10))                     # out of the window of 60 s
            n.rtts.append((now, least * 100 + 1))                      # in it, the newest, never the least
        assert least / 10 < n.least_rtt() <= least and n.least_rtt(window=200) == least / 10
        os.kill(pid, signal.SIGKILL)
        assert wait_for(lambda: n.state == "lost", 10) and n.least_rtt(window=1e9) is None   # the session's alone
    finally:
        n.close()
        n.thread.join(10)
        n.pinger.join(10)
    assert not n.alive()


def pools(tmp_path, entries, first=cx.FIRST):
    p = project(tmp_path, "name: t\nstocks:\n  queue: {unit: items}\n")
    got = cx.Pools(p, lambda s: None, first=first)
    got.sync({"farm": ComputePool("farm", entries)})
    return got


def test_lost_node_slots_leave_the_status(tmp_path):
    argv = worker(tmp_path / "r", beat=0.2)
    ps = pools(tmp_path, [{"connect": argv}, {"connect": argv}], first=60)
    try:
        a, b = ps.nodes["farm/1"], ps.nodes["farm/2"]
        pid = up(a)
        up(b)
        s = a.hello["slots"]
        assert wait_for(lambda: ps.status()["farm"]["free"] == 2 * s, 10), ps.status()      # free: the beats' word
        got = ps.status()["farm"]
        assert got == {"in_service": 2, "lost": 0, "slots": 2 * s, "free": 2 * s, "error": None,
                       "least_rtt": got["least_rtt"]}
        os.kill(pid, signal.SIGKILL)
        assert wait_for(lambda: a.state == "lost", 10)
        got = ps.status()["farm"]                                      # the next reading: its slots gone
        assert {k: got[k] for k in ("in_service", "lost", "slots", "free", "error")} == {
            "in_service": 1, "lost": 1, "slots": s, "free": s, "error": {"node": "farm/1", "why": "the session ended"}}
    finally:
        ps.close()
    assert ps.status() == {}


def test_unknown_version_in_status(tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "ssh").write_text('#!/bin/sh\necho "alice@real.example.com: Permission denied (publickey)." >&2\n'
                              'echo "ssh: connect to host 10.1.2.3 port 22: Connection refused" >&2\nexit 255\n')
    (bin_ / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    hello = {"v": 2, "seq": 1, "type": "hello", "slots": 4, "labels": {"user": "alice", "host": "real.example.com"}}
    fake = f"import sys\nprint({json.dumps(hello)!r}, flush=True)\nsys.stdin.read()  # alice@10.1.2.3\n"
    ps = pools(tmp_path, [{"connect": [sys.executable, "-I", "-c", fake]}, {"ssh": "Secret-Host"}], first=60)
    try:
        assert wait_for(lambda: ps.nodes["farm/2"].state == "lost" and ps.nodes["farm/1"].state == "refused", 15)
        got = ps.status()["farm"]
        assert got["in_service"] == 0 and got["lost"] == 2 and got["slots"] == got["free"] == 0
        assert got["least_rtt"] is None
        errs = {ps.nodes[k].erred: (k, ps.nodes[k].error) for k in ("farm/1", "farm/2")}
        assert got["error"] == dict(zip(("node", "why"), errs[max(errs)], strict=True))      # the one set last
        ps.nodes["farm/1"]._out("refused", ps.nodes["farm/1"].error)                       # set again: now the last
        assert ps.status()["farm"]["error"] == {"node": "farm/1", "why": "line 1: protocol v2 is not v1"}
        text = json.dumps(ps.status()).lower()
        assert not [w for w in ("secret-host", "10.1.2.3", "real.example.com", "alice") if w in text], text
    finally:
        ps.close()


def test_status_only_with_pools(tmp_path, monkeypatch):
    from ergostat import runner
    from ergostat.spec.engine import Engine
    from ergostat.store import Project
    from ergostat.web.server import Live, api
    argv = json.dumps(worker(tmp_path / "r", beat=0.2))
    p = project(tmp_path, f"name: t\nstocks:\n  queue: {{unit: items}}\ncompute:\n  farm:\n"
                          f"    nodes: [{{connect: {argv}}}]\n")
    live = Live(Project(mdl.load(tmp_path)))
    assert api(live, "status", {})["compute"] == {"farm": None}        # no engine running: unknown, never a guess
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        up(e.compute.nodes["farm/1"])
        assert wait_for(lambda: e.compute.status()["farm"]["least_rtt"] is not None, 15)
        e.watchdog.beat_at = -1e9
        e.watchdog.beat()                                               # the heartbeat carries it
        beat = json.loads((Path(p.dir) / "heartbeat.json").read_text())
        assert beat["compute"]["farm"]["in_service"] == 1
        with monkeypatch.context() as m:
            m.setattr(runner, "running_pid", lambda *a, **k: 4242)
            assert api(live, "status", {})["compute"] == {"farm": beat["compute"]["farm"]}
    finally:
        e.close()
    plain = tmp_path / "plain"
    plain.mkdir()
    q = project(plain, "name: t\nstocks:\n  queue: {unit: items}\n")
    f = Engine(q, say=lambda s: None)
    f.start_all()
    try:
        f.watchdog.beat_at = -1e9
        f.watchdog.beat()
        assert "compute" not in json.loads((Path(q.dir) / "heartbeat.json").read_text())
        with monkeypatch.context() as m:
            m.setattr(runner, "running_pid", lambda *a, **k: 4242)
            assert "compute" not in api(Live(Project(mdl.load(plain))), "status", {})   # a model without: no key
    finally:
        f.close()
