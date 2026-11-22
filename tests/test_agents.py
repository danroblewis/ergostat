"""The implementor's environment can run the four browser files (docs/roadmap/overnight/implementors-can-run-the-four.md):
Playwright and its Chromium are in the image its session and its suites run in, the session may run the browser files
under the watchdog, and a missing browser stops the round before it starts instead of letting the files skip."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

from tests.test_factory import BIN, ROOT, Factory, approved_gaps, merges, module, ready, suite_runs

PIN = "playwright==1.63.0"


def test_implementor_environment_has_a_browser():
    cfg = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]
    # one Playwright, everywhere: the image installs it, the round checks it, the suites and the session run with it
    dev_image, agent_image = (ROOT / "Dockerfile").read_text(), (ROOT / "dev" / "agent" / "Dockerfile").read_text()
    assert f"uvx --from {PIN} playwright install --with-deps chromium" in dev_image
    assert re.search(rf"uv run --with {re.escape(PIN)} python -c .*import playwright", dev_image)
    assert re.search(r"^FROM ergostat-dev:latest$", agent_image, re.M)          # the implementor's image is the dev one
    assert "PLAYWRIGHT_BROWSERS_PATH" not in agent_image                       # (and finds its browsers where it put them)
    assert f"--with {PIN} " in cfg["browser_ready"] and f"--with {PIN} " in cfg["browser"]
    assert f"--with {PIN} " in cfg["rerun"]
    # each browser run prints its skips (-rs: one SKIPPED line per reason), as well as pytest's summary count
    assert all(" -rs " in cfg[n] for n in ("browser", "rerun"))
    # the session may run the [suites] browser command itself, under the watchdog
    sys.modules.setdefault("fac", module("fac"))
    allowed = [t[len("Bash("):-len(":*)")] for t in module("agents").TOOLS["implementor"] if t.startswith("Bash(")]
    assert any(cfg["browser"].startswith(a + " ") for a in allowed) and cfg["browser"].startswith(
        "uv run python scripts/suite_watch.py -- ")
    # the clone is at /work there, so the browser files' pictures (beside the checkout by default) need a writable
    # folder: the round's suite containers and the session's own both name one under /tmp
    agents, factory = module("agents"), tomllib.loads((ROOT / "dev" / "factory.toml").read_text())
    shots = shlex.split(agents.contained(factory, "true", Path("/w"))[1]) + agents.run_args(
        factory, "implementor", Path("/w"), "n")
    assert shots.count("SPLIT_SHOTS=/tmp/split-shots") == 2 and shots.count("--tmpfs") == 2
    # and here, in the environment this suite runs in (the implementor's image, in the factory's suite containers),
    # the check the round makes launches Chromium: no Playwright or no browser fails this test, never skips it
    # (UV_NO_SYNC: the project's .venv is left as it is; a sync here reinstalls ergostat under the other workers)
    r = subprocess.run(["sh", "-c", cfg["browser_ready"]], cwd=ROOT, capture_output=True, text=True, timeout=300,
                       env={**os.environ, "UV_NO_SYNC": "1"})
    assert r.returncode == 0, f"no browser here: {shlex.join(['sh', '-c', cfg['browser_ready']])}\n{r.stderr[-1500:]}"


def no_session(lines: list[dict]) -> bool:
    return not any(x.get("type") == "result" or str(x.get("event", "")).startswith("session.") for x in lines)


@pytest.mark.slow
def test_missing_browser_stops_the_round_rather_than_skipping(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    settings = f.config.read_text()
    f.config.write_text(settings.replace('browser_ready = "true"',
                                         'browser_ready = "echo Executable not found at chromium >&2; exit 1"'))
    said, lines = f.run("implement.py", gid)
    assert "gap.built" not in said and "gap.measured" not in said and no_session(lines)   # stopped before the round
    nack = [x["nack"] for x in lines if "nack" in x]
    assert len(nack) == 1 and nack[0]["count"] is False                                  # (not the gap's fault)
    assert "no browser" in nack[0]["why"] and "docker build" in nack[0]["why"] and "chromium" in nack[0]["why"]
    logs = list((f.model / "run" / "logs").glob("*-ready-browser_ready.txt"))
    assert len(logs) == 1 and not list((f.model / "run" / "logs").glob("*-unit.txt"))    # no suite ran after it

    f.config.write_text(settings.replace('browser_ready = "true"', 'browser_ready = ""'))
    said, lines = f.run("implement.py", gid)                                             # no way to check: stopped too
    assert "gap.built" not in said and no_session(lines) and "browser_ready" in lines[-1]["nack"]["why"]

    # the browser there, but a page test skipped in the round's browser files: a failure, never built
    f.config.write_text(settings.replace('browser = "true"',
                                         'browser = "echo SKIPPED [1] tests/test_items_page.py:24: no port"'))
    said, lines = f.run("implement.py", gid)
    assert "gap.built" not in said and "gap.measured" in said
    fast = f.item(gid)["fields"]["suites_fast"]
    assert fast["failed"] == "browser" and fast["browser"]["rc"] == 0 and fast["browser"]["skipped"] == 1


def test_a_rerun_is_timed_by_the_suite_that_failed():
    sys.modules.setdefault("fac", module("fac"))
    sys.modules.setdefault("agents", module("agents"))
    room, soon = module("onmain").room, time.time() + 200
    took = {"unit": {"seconds": 10}, "browser": {"seconds": 400}}
    assert not room({**took, "failed": "browser"}, soon) and room({**took, "failed": "unit"}, soon)


@pytest.mark.slow
def test_a_browser_failure_that_skips_alone_is_not_a_flake(tmp_path):
    """A browser test failed, then skipped when run again alone (`rerun`): the skip is no pass, so no flake.seen and
    no free retry; it counts against the gap."""
    f = Factory(tmp_path)
    gid = ready(f)
    f.config.write_text(f.config.read_text()
                        .replace('browser = "true"', 'browser = "echo FAILED tests/test_items_page.py::test_b - x; false"')
                        .replace('rerun = "echo again {tests}"', 'rerun = "echo 1 skipped in 0.01s"'))  # (no -rs lines)
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    assert f.item(gid)["fields"]["suites_fast"]["failed"] == "browser"


# ---- the merge queue's suites in containers (dev/records/merge-queue-in-docker.md)

# A stand-in `docker` on PATH: `run` logs its arguments and runs its `sh -c` command in the folder mounted at /work, a
# process group of its own (as a container outlives its killed client), listed in STATE/running/<name> while it runs;
# `kill`/`rm` kill that group by name; `ps --filter name=X` lists those running. STATE/fails: `run` fails as Docker's
# own error does (exit 125), before any command.
FAKE_DOCKER = """\
import json, os, signal, subprocess, sys
from pathlib import Path
state, args = Path(STATE), sys.argv[1:]
with open(state / "calls.jsonl", "a") as f:
    f.write(json.dumps(args) + "\\n")
running = state / "running"
if args[0] == "run":
    if (state / "fails").exists():
        sys.exit(print("docker: Error response from daemon: no such image", file=sys.stderr) or 125)
    name, work = args[args.index("--name") + 1], next(a[:-len(":/work")] for a in args if a.endswith(":/work"))
    p = subprocess.Popen(["sh", "-c", args[-1]], cwd=work, start_new_session=True)
    (running / name).write_text(str(p.pid))
    rc = p.wait()
    (running / name).unlink(missing_ok=True)
    sys.exit(rc)
if args[0] in ("kill", "rm"):
    f = running / args[-1]
    if not f.exists():
        sys.exit(1)
    try:
        os.killpg(int(f.read_text()), signal.SIGKILL)
    except (ProcessLookupError, ValueError):
        pass
    f.unlink(missing_ok=True)
if args[0] == "ps":
    want = args[args.index("--filter") + 1].split("=", 1)[1]
    print("\\n".join(n.name for n in running.iterdir() if n.name.startswith(want)))
"""


def boxed(tmp: Path, unit: str = "true") -> tuple[Factory, Path]:
    """A factory whose queue runs its suites in containers ([suites] queue_container), in the stand-in Docker."""
    f = Factory(tmp, unit=unit)
    state, bin_ = tmp / "docker", tmp / "bin"
    (state / "running").mkdir(parents=True)
    bin_.mkdir()
    (bin_ / "docker").write_text(f"#!{sys.executable}\nSTATE = {str(state)!r}\n" + FAKE_DOCKER)
    (bin_ / "docker").chmod(0o755)
    f.config.write_text(f.config.read_text().replace("queue_container = false", "queue_container = true")
                        + '[agents]\nimage = "the-agent-image"\nqueue_cpuset = "12-23"\n')
    f.env["PATH"] = f"{bin_}{os.pathsep}{f.env['PATH']}"
    return f, state


def runs_of(state: Path) -> list[list[str]]:
    calls = state / "calls.jsonl"
    return [a for a in map(json.loads, calls.read_text().splitlines()) if a[0] == "run"] if calls.exists() else []


def flag(args: list[str], name: str) -> list[str]:
    return [args[i + 1] for i, a in enumerate(args) if a == name]


def git_head(f: Factory) -> str:
    return subprocess.run(["git", "-C", str(f.checkout), "rev-parse", "HEAD"], capture_output=True, text=True).stdout


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.slow
def test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network(tmp_path):
    f, state = boxed(tmp_path, unit=f"echo run >> {tmp_path / 'runs'}")
    f.config.write_text(f.config.read_text().replace('ruff = "true"', 'ruff = "true ruff"')
                        .replace('browser = "true"', 'browser = "true browser"').replace('demo = "true"', 'demo = "true demo"'))
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"] and merges(f) == ["a"]
    assert suite_runs(f) == 1                                         # the unit command ran, inside the "container"
    got = {a[-1]: a for a in runs_of(state)}
    cfg = tomllib.loads(f.config.read_text())["suites"]
    assert sorted(got) == sorted(cfg[n] for n in ("ruff", "unit", "browser", "demo"))
    checkout = f.checkout.resolve()
    for a in got.values():
        assert flag(a, "--network") == ["none"] and flag(a, "--cpuset-cpus") == ["12-23"] and "--init" in a
        assert f"{checkout}:/work" in flag(a, "-v") and f"{checkout / '.git'}:/work/.git:ro" in flag(a, "-v")
        assert "UV_PROJECT_ENVIRONMENT=/opt/venv" in flag(a, "-e")               # never the checkout's .venv
        assert a[-4:-1] == ["the-agent-image", "sh", "-c"] and flag(a, "--name")[0].startswith(
            "ergostat-factory-suite-queue-")                                   # (counted by the load interlock)
    assert flag(got[cfg["unit"]], "--cpus") == ["8"] and flag(got[cfg["browser"]], "--cpus") == ["4"]
    assert not list((state / "running").iterdir())                    # each removed by name once it ended


@pytest.mark.slow
def test_with_queue_container_false_the_commands_are_todays(tmp_path, monkeypatch):
    f, state = boxed(tmp_path)
    f.config.write_text(f.config.read_text().replace("queue_container = true", "queue_container = false"))
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"] and not (state / "calls.jsonl").exists()  # no Docker
    monkeypatch.setenv("FACTORY_CONFIG", str(f.config))
    fac = module("fac")
    monkeypatch.setitem(sys.modules, "fac", fac)
    cfg, seen = fac.config(), []

    class Popen:
        def __init__(self, cmd, **k):
            seen.append(cmd)
            self.pid, self.returncode = os.getpid(), 0

        def poll(self):
            return 0

    monkeypatch.setattr(fac.subprocess, "Popen", Popen)
    for box in ("", "queue", "triage"):
        fac.suite(cfg, "rerun", f.checkout, tmp_path / "log.txt", slot=False, box=box, tests=["t::a"])
    assert seen == ["echo again t::a"] * 3


def test_a_container_that_cannot_start_fails_the_run_with_no_gap_blamed(tmp_path):
    f, state = boxed(tmp_path)
    approved_gaps(f, {"a": 1})
    before = git_head(f)
    (state / "fails").write_text("")
    said, lines = f.run("queue.py", "gap/a", fails=True)
    assert said == ["gap.queued"] and not [x for x in lines if "nack" in x]     # no queue-failed, sent-back or flake
    assert "NotStarted" in f.stderr and "did not start (exit 125)" in f.stderr and "no such image" in f.stderr
    a = f.item("gap/a")["fields"]
    assert not a.get("failed_gates") and not a.get("failed_suite") and git_head(f) == before   # main as it was
    assert len(runs_of(state)) == 1                                   # ruff's; nothing after it


def test_a_stopped_queue_run_leaves_no_container_behind(tmp_path):
    pids = tmp_path / "pids"
    sleeper = f"echo $$ >> {pids}; exec sleep 60"
    f, state = boxed(tmp_path, unit=sleeper)
    approved_gaps(f, {"a": 1})

    def started() -> tuple[subprocess.Popen, int]:
        pids.unlink(missing_ok=True)
        given = {"trigger": "item", "item": f.item("gap/a"), "lease": {"fence": 1, "back": "approved"}}
        p = subprocess.Popen([sys.executable, str(BIN / "queue.py")], stdin=subprocess.PIPE, cwd=f.model,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
                             env={**f.env, "ERGOSTAT_ITEM": "gap/a", "ERGOSTAT_LEASE": "1"})
        p.stdin.write(json.dumps(given))
        p.stdin.close()
        end = time.time() + 60
        while not (pids.exists() and pids.read_text().strip()) and time.time() < end:
            time.sleep(0.1)
        return p, int(pids.read_text().split()[0])

    p, pid = started()                                                # stopped (SIGTERM: a lease ended, a stop)
    assert alive(pid) and list((state / "running").iterdir())
    p.terminate()
    p.wait(timeout=60)
    assert not alive(pid) and not list((state / "running").iterdir())  # its container killed by name, not left
    p, pid = started()                                                # killed with no finally (SIGKILL)
    p.kill()
    p.wait(timeout=60)
    assert alive(pid)                                                 # (as Docker's would, it outlived its client)
    f.config.write_text(f.config.read_text().replace(f'unit = "{sleeper}"', 'unit = "true"'))
    said, _ = f.run("queue.py", "gap/a")                              # the next run removes it first
    end = time.time() + 10
    while alive(pid) and time.time() < end:
        time.sleep(0.1)
    assert not alive(pid) and not list((state / "running").iterdir()) and said[-1] == "gap.push-asked"


def test_sessions_gap_suites_and_queue_suites_get_their_own_cpusets(tmp_path, monkeypatch):
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    cfg = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())
    a = cfg["agents"]
    assert (a["session_cpus"], a["session_cpuset"], a["suite_cpuset"], a["queue_cpuset"]) == (1.5, "0-7", "8-11", "12-23")
    session = agents.run_args(cfg, "implementor", Path("/w"), "n")
    suite = shlex.split(agents.contained(cfg, "true", Path("/w"))[1])
    cfg["paths"]["run"] = str(tmp_path / "run")
    monkeypatch.setattr(agents.fac, "git", lambda *a: str(tmp_path / ".git"))
    queue = shlex.split(agents.queued(cfg, "unit", "true", tmp_path, "queue")[1])
    assert [flag(x, "--cpuset-cpus") for x in (session, suite, queue)] == [["0-7"], ["8-11"], ["12-23"]]
    assert [flag(x, "--cpus") for x in (session, suite, queue)] == [["1.5"], ["4"], ["8"]]
    assert flag(queue, "--network") == ["none"] and flag(session, "--network") == [agents.NET]
    for empty in ({}, {"queue_cpuset": ""}):                          # no pinning
        assert "--cpuset-cpus" not in agents.limits({"agents": empty}, "queue")
    with pytest.raises(ValueError, match="queue_cpuset"):             # a cpuset that is not one is refused, not dropped
        agents.limits({"agents": {"queue_cpuset": "12-23; rm"}}, "queue")
