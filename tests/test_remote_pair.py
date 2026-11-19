"""Two ergostat instances on one machine (SPEC §4c, examples/remote-pair): a local "support" model reading a remote
"incidents" model. The remote's model changes while both run and the local follows; the remote stops and the local
marks what it read as stale."""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

PAIR = Path(__file__).resolve().parent.parent / "examples" / "remote-pair"
PORTS = range(8796, 8800)                   # (8790 is the owner's; these are the pair's)


def free_ports(n: int) -> list[int]:
    out = []
    for p in PORTS:
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)     # (as the server binds: a port just left is free)
            try:
                s.bind(("127.0.0.1", p))
            except OSError:
                continue
        out.append(p)
        if len(out) == n:
            return out
    pytest.skip("no two free ports in 8796-8799")


def cli(d: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ergostat", "-C", str(d), *args], capture_output=True, text=True, timeout=60)


def start(d: Path, port: int) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "ergostat", "-C", str(d), "run", "--foreground", "--port", str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def until(what, seconds: float, why: str):
    end = time.time() + seconds
    last = None
    while time.time() < end:
        try:
            last = what()
            if last:
                return last
        except Exception as e:                  # (a page not up yet)
            last = e
        time.sleep(0.5)
    raise AssertionError(f"{why}: not within {seconds:g}s (last: {last!r})")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)


def test_a_local_model_follows_a_remote_one_and_marks_it_stale_when_it_stops(tmp_path):
    for d in ("incidents", "support"):
        shutil.copytree(PAIR / d, tmp_path / d)
    inc, sup = tmp_path / "incidents", tmp_path / "support"
    p_inc, p_sup = free_ports(2)
    y = sup / "ergostat.yaml"
    y.write_text(y.read_text().replace("http://127.0.0.1:8796", f"http://127.0.0.1:{p_inc}").replace("every: 10s", "every: 10s"))
    remote = start(inc, p_inc)
    local = None
    try:
        until(lambda: get(f"http://127.0.0.1:{p_inc}/api/status")["running"], 30, "the remote's page")
        tok = cli(inc, "remote", "token", "support")
        assert tok.returncode == 0, tok.stderr
        (sup / "incidents.token").write_text(tok.stdout.strip())
        local = start(sup, p_sup)
        base = f"http://127.0.0.1:{p_sup}"
        until(lambda: get(f"{base}/api/status")["running"], 30, "the local page")

        def read_here():
            got = get(f"{base}/api/part/stock/incidents-open")["now"]
            return got and got.get("value") is not None
        until(read_here, 40, "the remote's stock read here")
        g = get(f"{base}/api/graph?view=dynamics")
        box = next(n for n in g["nodes"] if n.get("kind") == "system" and n.get("label") == "incidents")
        assert box["remote"]["state"] == "ok" and "remote" in box["remote"]["says"]       # drawn closed, marked remote
        b = get(f"{base}/api/graph?view=blocks")
        assert any(n.get("remote") for n in b["nodes"] if n.get("role") == "subsystem")
        assert not [e for e in get(f"{base}/api/events?type=agent.started&n=200") if e["item"].startswith("incidents-")]

        y = inc / "ergostat.yaml"                                      # the remote's model changes while both run
        y.write_text(y.read_text().replace("  resolved:\n    from: open\n    system: response\n",
                                           "  resolved:\n    from: open\n    system: response\n"
                                           "  escalated:\n    from: open\n    system: response\n"))
        until(lambda: any(f["name"] == "incidents-escalated" for k in ("flow", "disturbance") for f in get(f"{base}/api/parts")[k]), 45,
              "the local model following the remote's new version")

        stop(remote)                                                   # the remote stops
        def stale():
            att = get(f"{base}/api/status")["attention"]
            return [a for a in att if a["what"] == "remote incidents"]
        said = until(stale, 45, "the remote marked as not answering")
        assert "old" in said[0]["says"] or "nothing of it" in said[0]["says"]
        g = get(f"{base}/api/graph?view=dynamics")
        box = next(n for n in g["nodes"] if n.get("kind") == "system" and n.get("label") == "incidents")
        assert box["remote"]["state"] == "unreachable" and "not answering" in box["remote"]["says"]
        assert get(f"{base}/api/part/stock/incidents-open")["now"]["value"] is not None    # the last reading stands
        assert get(f"{base}/api/events?type=sensor.failed&n=50")                           # each failure recorded
        chk = cli(sup, "check", "--no-coherence")
        assert chk.returncode == 0 and "remote-unreachable" in chk.stdout, chk.stdout + chk.stderr
    finally:
        stop(remote)
        if local is not None:
            stop(local)
