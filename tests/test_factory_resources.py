"""The factory's resource sensors, headroom, the gates that respect it, and the disk cleanup (dev/bin/resources.py,
dev/bin/cleanup.py, dev/model/resources.yaml)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ergostat.spec import read
from ergostat.spec.blocks import compile_expr, eval_expr

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "dev" / "bin"


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, BIN / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def res(monkeypatch):
    monkeypatch.setitem(sys.modules, "fac", module("fac"))
    r = module("resources")
    monkeypatch.setitem(sys.modules, "resources", r)
    return r


VM_STAT = """\
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                            12216407.
Pages active:                           1863886.
Pages inactive:                         1561683.
Pages wired down:                        300497.
Pages purgeable:                         119903.
"Translation faults":                4290971335.
Anonymous pages:                        2141201.
Pages occupied by compressor:             65536.
"""
IOSTAT = """\
      cpu    load average
 us sy id   1m   5m   15m
 15  3 83  6.71 9.37 8.39
 32  2 66  6.71 9.37 8.39
"""
TOP = """\
Processes: 661 total, 5 running, 656 sleeping, 4170 threads
2026/11/20 13:42:46
Load Avg: 8.29, 9.56, 8.48
"""


def test_macos_readings_parse(res):
    m = res.mac_memory("274877906944\n", VM_STAT, "98\n")
    pages = 2141201 - 119903 + 300497 + 65536
    assert m["memory-total"] == 256.0 and m["memory-used"] == round(pages * 16384 / 2**30, 2)
    assert m["memory-free"] == round(256 - pages * 16384 / 2**30, 2) and m["memory-pressure"] == 0.02
    assert 0 < m["memory-utilisation"] < 0.2
    assert res.iostat_cpu(IOSTAT) == 0.34                       # the last row (the first is since boot)
    assert res.iostat_cpu("") is None
    assert res.mac_top(TOP) == {"machine-threads": 4170, "cpu-load": 8.29}


def test_linux_readings_parse(res):
    a = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 2 3 4\n"
    b = "cpu  200 0 200 1300 100 0 0 0 0 0\ncpu0 1 2 3 4\n"
    assert res.proc_cpu(a, b) == 0.25                           # 200 busy of 800
    m = res.linux_memory("MemTotal:       16777216 kB\nMemFree:  100 kB\nMemAvailable:    4194304 kB\n",
                         "some avg10=12.50 avg60=1.00 avg300=0.00 total=1\nfull avg10=0.00\n")
    assert (m["memory-total"], m["memory-used"], m["memory-free"]) == (16.0, 12.0, 4.0)
    assert m["memory-utilisation"] == 0.75 and m["memory-pressure"] == 0.125
    assert res.linux_memory("MemTotal: 1024 kB\nMemAvailable: 1024 kB\n")["memory-pressure"] is None
    assert res.loadavg("3.10 2.00 1.00 4/1234 5678\n") == {"cpu-load": 3.1, "machine-threads": 1234}


STATS = "\n".join(json.dumps(x) for x in [
    {"Name": "ergostat-factory-suite-849b8f3464", "CPUPerc": "406.05%", "MemUsage": "3.5GiB / 12GiB"},
    {"Name": "ergostat-factory-implementor-8cc0ede1c1", "CPUPerc": "0.10%", "MemUsage": "512MiB / 12GiB"},
    {"Name": "ergostat-egress", "CPUPerc": "1.00%", "MemUsage": "100MiB / 150GiB"},
    {"Name": "someone-elses", "CPUPerc": "200%", "MemUsage": "4GiB / 150GiB"}])
DF = "\n".join(json.dumps({"Type": t, "Size": s}) for t, s in [("Images", "22.7GB"), ("Containers", "12.25MB"),
                                                                 ("Local Volumes", "0B"), ("Build Cache", "1.5GB")])


def test_docker_outputs_parse(res):
    d = res.docker(f"24 {150 * 2**30}\n", STATS + "\nnot json\n")
    assert d["vm-cpus"] == 24 and d["vm-memory"] == 150.0
    assert set(d["containers"]) == {"ergostat-factory-suite-849b8f3464", "ergostat-factory-implementor-8cc0ede1c1"}
    assert d["containers"]["ergostat-factory-suite-849b8f3464"] == {"cpu": 4.061, "memory": 3.5}
    assert d["factory-cpu"] == 4.062 and d["factory-memory"] == 4.0
    assert d["vm-cpu-used"] == round(4.0605 + 0.001 + 0.01 + 2, 3)     # every container counts against the VM
    assert d["vm-memory-used"] == round(3.5 + 0.5 + 100 / 1024 + 4, 3)
    assert d["vm-memory-utilisation"] == round(d["vm-memory-used"] / 150, 3)
    assert res.docker("", STATS) == {}                                   # Docker down: no VM readings
    assert res.docker_df(DF) == round((22.7e9 + 12.25e6 + 1.5e9) / 2**30, 2)
    assert res.size_gb("1.5kB") == 1500 / 2**30 and res.size_gb("") == 0


SP = {"cpu": 0.8, "memory": 0.8, "vm-memory": 0.85, "disk": 50, "threads": 10000}
CALM = {"cpus": 28, "cpu-utilisation": 0.2, "memory-total": 256.0, "memory-used": 40.0, "disk-free": 400.0,
        "machine-threads": 4000, "vm-cpus": 24, "vm-cpu-used": 2.0, "vm-memory": 150.0, "vm-memory-used": 10.0}


def test_headroom(res):
    each = (4.5, 5.0)
    # host CPU: 28 x 0.6 / 4.5 = 3.7; host memory 164.8 / 5 = 33; VM CPU (19.2 - 2) / 4.5 = 3.8; VM memory 117.5 / 5
    assert res.headroom(CALM, SP, each) == 3
    assert res.headroom(CALM | {"vm-memory-used": 120.0}, SP, each) == 1            # the VM's memory binds
    assert res.headroom(CALM | {"cpu-utilisation": 0.95}, SP, each) == 0            # past the setpoint: none, not less
    assert res.headroom(CALM | {"disk-free": 49.9}, SP, each) == 0                  # disk short
    assert res.headroom(CALM | {"machine-threads": 10001}, SP, each) == 0           # too many threads
    host_only = {k: v for k, v in CALM.items() if not k.startswith("vm-")}
    assert res.headroom(host_only, SP, each) == 3                                   # Docker down: the host's alone
    assert res.headroom({}, SP, each) == 0                                          # nothing known: none
    cfg = {"resources": {"session_cpus": 0.5, "session_memory_gb": 1, "suite_cpus": 4, "suite_memory_gb": 4}}
    assert res.per_session(cfg, []) == (4.5, 5.0)                                   # the defaults until measured
    rows = [{"role": "implementor", "cpu_max": 1.0, "memory_max": 0.5}] * 3 + \
        [{"role": "suite", "cpu_max": 3.0, "memory_max": 2.5}] * 2
    assert res.per_session(cfg, rows) == (5.0, 4.5)                                 # sessions measured, suites not yet
    assert res.per_session(cfg, rows + rows[-1:]) == (4.0, 3.0)


def test_a_session_is_sampled_into_the_ledger(res, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = {"paths": {"run": str(tmp_path / "run")}}
    seen = iter([{"cpu": 1.0, "memory": 2.0}, {"cpu": 3.0, "memory": 1.0}] + [None] * 1000)
    monkeypatch.setattr(res, "snapshot", lambda cfg: {"containers": {"c1": next(seen)}})
    with res.sampled(cfg, "c1", "implementor", every=0.01) as use:
        time.sleep(0.2)
    assert use["samples"] == 2 and use["cpu_max"] == 3.0 and use["cpu_mean"] == 2.0 and use["memory_max"] == 2.0
    assert json.loads(res.ledger(cfg).read_text().splitlines()[0])["role"] == "implementor"
    with res.sampled(cfg, "c2", "suite", every=10) as use:
        pass
    assert use == {}                                                                 # nothing sampled, nothing kept


def env_of(spec, block: str, given: dict) -> float:
    b = spec.blocks[block]
    return eval_expr(compile_expr(b.params["expr"]), {k: given[k] for k in b.inputs})


@pytest.mark.slow                                                       # (the model's checks: about 20 s)
def test_gates_respect_headroom(res):
    spec, problems = read(ROOT / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"]
    sp = res.setpoints()                                                # the program reads the model's own setpoints
    assert {k: spec.goals[g].hold.value for k, g in res.GOALS.items()} == sp
    assert spec.goals["sessions-fit"].on_stale == "off"                 # a stale headroom counts as no room
    assert {r.name for r in spec.blocks["machine-full"].outputs["out"]} == {"implement-when", "review-when"}
    calm = dict(fit=0, cpu=0, memory=0, vm=0, threads=0, disk=0)
    assert env_of(spec, "machine-full", calm) == 0
    for k in calm:
        assert env_of(spec, "machine-full", calm | {k: 1}) == 1, k
    build = dict(ready=1, fixes=0, open=1, over=0, busy=1, pool=3, room=2, full=0)
    review = dict(waiting=1, over=0, busy=1, pool=2, room=2, full=0)
    assert env_of(spec, "implement-when", build) == 1
    assert env_of(spec, "implement-when", build | {"room": 0}) == 0                  # no headroom: closed
    assert env_of(spec, "implement-when", build | {"full": 1}) == 0                  # past a goal, or stale: closed
    assert env_of(spec, "implement-when", build | {"busy": 3, "room": 50}) == 0      # never past the risk target
    assert env_of(spec, "review-when", review) == 1
    assert env_of(spec, "review-when", review | {"room": 0}) == 0
    assert env_of(spec, "review-when", review | {"busy": 2, "room": 9}) == 0


def test_my_turn_respects_headroom(res, monkeypatch):
    pools = module("pools")
    held = [{"id": f"gap/{n}", "fields": {"lease": {"block": "implementor", "holder": n, "taken": i}}}
            for i, n in enumerate("abc")]
    monkeypatch.setattr(sys.modules["fac"], "items", lambda kind, state=None: held)
    monkeypatch.setattr(pools, "state", lambda cfg: {"since": 0, "implementor": 3, "reviewer": 2})
    turns = lambda: [pools.my_turn({}, "implementor", "implementor", f"gap/{n}") for n in "abc"]  # noqa: E731
    monkeypatch.setattr(res, "room", lambda cfg, role: None)                 # the stand-in: the pool alone
    assert turns() == [True, True, True]
    monkeypatch.setattr(res, "room", lambda cfg, role: 2)                    # one running, one more fits
    assert turns() == [True, True, False]
    monkeypatch.setattr(res, "room", lambda cfg, role: 9)                    # never past the pool
    monkeypatch.setattr(pools, "state", lambda cfg: {"since": 0, "implementor": 1, "reviewer": 2})
    assert turns() == [True, False, False]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def test_cleanup_deletes_only_the_factorys_folders(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "fac", module("fac"))
    cleanup = module("cleanup")
    checkout, live = tmp_path / "checkout", tmp_path / "live"
    git(tmp_path, "init", "-q", "-b", "main", str(checkout))
    git(checkout, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "--allow-empty", "-m", "start")
    sha = git(checkout, "rev-parse", "HEAD").strip()
    old, now = time.time() - 3 * 86400, time.time()
    shas = {n: f"{n:x}" * 40 for n in range(10, 16)}                 # aaaa..., bbbb..., ...
    installs = {}
    for label, h in zip(("old", "current", "previous", "young"), (shas[10], shas[11], shas[12], shas[13]), strict=True):
        installs[label] = live / h
        git(checkout, "worktree", "add", "-q", "--detach", str(live / h), sha)
    (live / "current").symlink_to(shas[11])
    (live / "previous").symlink_to(shas[12])
    plain = live / shas[14]                                            # a sha-named folder that is no worktree
    plain.mkdir()
    (plain / "keep.txt").write_text("not the factory's")
    sessions = live / "sessions"
    sessions.mkdir()
    stamp = time.strftime("%Y%m%d%H%M%S", time.localtime(old))
    young_stamp = time.strftime("%Y%m%d%H%M%S", time.localtime(now))
    gone = sessions / f"warm3-implementor-{stamp}-0a1b2c"
    (gone / "work" / ".git" / "objects").mkdir(parents=True)
    (gone / "work" / ".git" / "objects" / "pack").write_text("x")
    os.chmod(gone / "work" / ".git" / "objects" / "pack", 0o444)     # (read-only, as git's objects are)
    claude_old = sessions / "warm3-implementor-2-claude-0a1b2c3d"     # Claude Code's folder for a session
    (claude_old / "-work").mkdir(parents=True)
    keep = [sessions / f"warm3-reviewer-{young_stamp}-0a1b2c",          # young
            sessions / "warm3-reviewer-1-claude-0a1b2c3d",              # young
            sessions / "warm3-reviewer-1-claude-0a1b2c3",               # seven hex
            sessions / f"warm_3-implementor-{stamp}-0a1b2c",            # not lowercase words and dashes
            sessions / f"warm3-implementor-{stamp}-0a1b2",              # five hex
            sessions / f"warm3-implementor-{stamp}-0a1b2c.bak",         # a suffix
            sessions / "notes"]
    for d in keep:
        d.mkdir()
    (sessions / f"x-implementor-{stamp}-abcdef").write_text("a file, not a folder")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (sessions / f"y-implementor-{stamp}-abcdef").symlink_to(elsewhere)
    for p in [*sessions.iterdir(), *(live / h for h in shas.values() if (live / h).exists())]:
        if "reviewer" not in p.name and p.name != shas[13] and not p.is_symlink() or p.name.endswith("c3"):
            os.utime(p, (old, old))
    cfg = {"paths": {"live": str(live), "checkout": str(checkout), "run": str(tmp_path / "run")},
           "resources": {"session_keep_hours": 24}}
    assert cleanup.sessions(cfg) == [claude_old, gone]
    assert cleanup.installs(cfg) == [installs["old"]]
    assert set(cleanup.installs(cfg, every=True)) == {installs["old"], installs["young"]}   # what the measure counts
    monkeypatch.setattr(cleanup.fac, "config", lambda: cfg)
    monkeypatch.setattr(cleanup.fac, "items", lambda kind: 1 / 0)          # the record unread: no install removed
    with pytest.raises(ZeroDivisionError):
        cleanup.main([])
    assert installs["old"].exists() and gone.exists()
    up = [{"state": "approved", "fields": {"sha": shas[10]}}]             # its switch approved, waiting for its moment
    monkeypatch.setattr(cleanup.fac, "items", lambda kind: up if kind == "upgrade" else [])
    assert cleanup.main([]) == 0 and installs["old"].exists() and not gone.exists()
    up[0]["state"] = "withdrawn"
    assert cleanup.main(["--dry-run"]) == 0 and installs["old"].exists()
    assert cleanup.main([]) == 0
    assert not gone.exists() and not claude_old.exists() and not installs["old"].exists()
    assert all(d.exists() for d in keep) and (plain / "keep.txt").exists() and elsewhere.exists()
    assert all(installs[k].exists() for k in ("current", "previous", "young"))
    assert (sessions / f"x-implementor-{stamp}-abcdef").is_file()
    assert (sessions / f"y-implementor-{stamp}-abcdef").is_symlink()
    assert shas[10] not in git(checkout, "worktree", "list")                        # removed by git, and pruned
    s = cleanup.sizes(cfg)
    assert s["factory-disk"] == round(s["sessions-disk"] + s["installs-disk"], 2)
    monkeypatch.setitem(sys.modules, "live", module("live"))
    assert cleanup.WAITING == module("drain").WAITING
