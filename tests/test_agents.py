"""The implementor's environment can run the four browser files (docs/roadmap/overnight/implementors-can-run-the-four.md):
Playwright and its Chromium are in the image its session and its suites run in, the session may run the browser files
under the watchdog, and a missing browser stops the round before it starts instead of letting the files skip."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
import types
from pathlib import Path

import pytest

from tests.test_factory import BIN, QUEUE_ENV, ROOT, Factory, approved_gaps, merges, module, ready, suite_runs

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
    # each browser run prints its skips (-rfEs: one SKIPPED line per reason, and the FAILED and ERROR lines
    # fac.failed_tests reads), as well as pytest's summary count
    assert all(" -rfEs " in cfg[n] for n in ("browser", "rerun"))
    # the session may run a named browser file under the watchdog, with the suite's own Playwright, and never the suite
    sys.modules.setdefault("fac", module("fac"))
    assert may(f"{PAGE} tests/test_items_page.py") and not may(cfg["browser"])
    assert PAGE.rsplit(" python ", 1)[0] == cfg["browser"].split(" python -m")[0]     # (the suite's own Playwright)
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


def permits(rules: list[str], cmd: str) -> bool:
    """Whether a Bash rule matches ``cmd`` as Claude Code reads it: `x:*` is x alone or x, a space and anything; any
    other `*` matches anything (so a rule is a prefix, never a whole-command check)."""
    for rule in (r[len("Bash("):-1] for r in rules if r.startswith("Bash(")):
        head = rule.removesuffix(":*")
        if cmd == head or (cmd.startswith(head + " ") if rule.endswith(":*") else fnmatch.fnmatchcase(cmd, rule)):
            return True
    return False


def may(cmd: str, role: str = "implementor") -> bool:
    """Allowed to the role's session: one of its tools, and none of the ones refused to every session."""
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    return permits(agents.TOOLS[role], cmd) and not permits(agents.DENY, cmd)


NAMED = "uv run python scripts/named_tests.py"
PAGE = f"uv run python scripts/suite_watch.py -- uv run --with {PIN} python scripts/named_tests.py"


def test_the_whole_suite_watch_command_is_not_the_implementors():
    """The permission lets pytest run only through scripts/named_tests.py; that script is the allowlist."""
    watched = "uv run python scripts/suite_watch.py -- "
    cfg = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]
    assert may(f"{NAMED} tests/test_agents.py") and may(f"{PAGE} tests/test_items_page.py::test_a")
    refused = [cfg["unit"], cfg["browser"], f"{watched}uv run python -m pytest -q", f"{watched}uv run python -m pytest",
               f"{watched}uv run --with {PIN} python -m pytest -q -rs tests/test_items_page.py",
               "uv run python -m pytest -q -n 8", "uv run python -m pytest -q tests/test_agents.py",
               "uv run python -m pytest", f"{watched}sh -c true", f"{watched}uv run python -m pytest -q tests/test_x.py"]
    assert not [c for c in refused if may(c)]
    assert not any(t.startswith(("Bash(uv run python scripts/suite_watch.py:", "Bash(uv run python -m pytest"))
                   for t in module("agents").TOOLS["implementor"])        # (the broad prefixes of before are gone)
    assert not [r for r in ("reviewer", "planner", "librarian") if may(f"{NAMED} tests/test_agents.py", r)]


def test_the_implementor_may_write_the_graph_fixtures_and_the_reviewer_may_not():
    """`python -m tests.graph_fixtures` writes tests/fixtures/graphs/<model>-<view>.json from ergostat's own model,
    offline; the implementor may run it, a read-only role may not."""
    fixtures = "uv run python -m tests.graph_fixtures"
    assert may(fixtures) and may(f"{fixtures} --model x")
    assert not [r for r in ("reviewer", "planner", "groomer") if may(fixtures, r)]
    assert not may("uv run python -m tests.graph_fixtures_other") and not may("uv run python -m tests")


def test_named_tests_runs_named_files_only(tmp_path, monkeypatch):
    """The allowlist: 1 to 3 existing tests/test_*.py files or test ids; no glob's many files, directory or option."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("named_tests", ROOT / "scripts" / "named_tests.py")
    named = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(named)
    monkeypatch.chdir(ROOT)
    every = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))     # (what test_*.py expands to)
    page = "tests/test_items_page.py"
    assert not [a for a in ([page], [f"{page}::test_a"], [page, "tests/test_agents.py::x[1-2]"]) if named.refused(a)]
    refused = [[], every, every[:4], ["tests"], ["tests/"], [page, "tests"], [page, "-qn4"], [page, "-n", "4"],
               [page, "-n4"], ["-n", "4", page], [page, "--numprocesses=auto"], ["tests/test_*.py"],
               ["tests/test_nothing_here.py"], ["tests/../tests/test_agents.py"], ["tests/fixtures"], [page, "-p", "x"],
               ["tests/test_items_page.py::"], [f"{page} -n 4"], ["-k", "page"]]
    assert not [a for a in refused if not named.refused(a)]
    (tmp_path / "tests").mkdir()                     # and it runs pytest serially, the ini's addopts (-n 8) cleared
    (tmp_path / "tests" / "test_one.py").write_text("def test_one(request):\n"      # (not the env: an xdist parent's leaks)
                                                     "    assert not request.config.pluginmanager.hasplugin('xdist')\n")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\naddopts = "-n 8 -x"\n')
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "scripts" / "named_tests.py"), *a], cwd=tmp_path,  # noqa: E731
                                    capture_output=True, text=True, timeout=120)
    ok, no = run("tests/test_one.py"), run("tests/test_one.py", "-n", "8")
    assert ok.returncode == 0 and "1 passed" in ok.stdout, ok.stdout + ok.stderr
    assert no.returncode == 2 and "named_tests:" in no.stderr and not no.stdout


def round_suites(tmp_path: Path, extra: str = "") -> tuple[Factory, str, Path]:
    """A factory whose every suite (and the Chromium launch) logs its name to ``ran``; ``extra`` added to [suites]."""
    ran = tmp_path / "ran"
    f = Factory(tmp_path / "f", unit=f"echo unit >> {ran}")
    text = f.config.read_text()
    for n in ("ruff", "browser", "browser_ready", "demo"):
        text = text.replace(f'\n{n} = "true"', f'\n{n} = "echo {n} >> {ran}"')
    f.config.write_text(text.replace("[suites]\n", f"[suites]\n{extra}\n"))
    return f, ready(f), ran


@pytest.mark.slow
def test_a_round_runs_ruff_and_the_build_step_and_no_browser_suite_by_default(tmp_path):
    f, gid, ran = round_suites(tmp_path, f'build = "echo build >> {tmp_path / "ran"}"')
    said, _ = f.run("implement.py", gid)
    assert "gap.built" in said and ran.read_text().split() == ["ruff", "build"]       # no unit, browser or Chromium
    assert set(f.item(gid)["fields"]["suites_fast"]) == {"ruff", "build"}
    g, gid, ran = round_suites(tmp_path / "nobuild")                                   # no build set: unit, as before
    said, _ = g.run("implement.py", gid)
    assert "gap.built" in said and ran.read_text().split() == ["ruff", "unit"]


@pytest.mark.slow
def test_build_browser_true_brings_the_browser_suite_back_into_the_round(tmp_path):
    f, gid, ran = round_suites(tmp_path, f'build = "echo build >> {tmp_path / "ran"}"\nbuild_browser = true')
    said, _ = f.run("implement.py", gid)
    assert "gap.built" in said and ran.read_text().split() == ["browser_ready", "ruff", "build", "browser"]
    g, gid, ran = round_suites(tmp_path / "text", 'build_browser = "true"')            # (only a true turns it on)
    g.run("implement.py", gid)
    assert ran.read_text().split() == ["ruff", "unit"]


@pytest.mark.slow
@pytest.mark.parametrize("on", ["false", "true"])
def test_the_merge_queue_runs_unit_browser_and_demo_in_full_either_way(tmp_path, on):
    from tests.test_factory import approved_gaps
    f, _, ran = round_suites(tmp_path, f'build = "echo build >> {tmp_path / "ran"}"\nbuild_browser = {on}')
    approved_gaps(f, {"q": 1})
    said, _ = f.run("queue.py", "gap/q")
    assert "gap.merged" in said, said
    got = ran.read_text().split()
    assert sorted(got) == ["browser", "demo", "ruff", "unit"] and got[-1] == "demo"     # never build, never less


def test_a_sessions_container_gets_its_cpus_and_a_suite_container_keeps_four():
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    factory = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())
    assert factory["agents"]["session_cpus"] == 1.5
    cpus = lambda args: [args[i + 1] for i, a in enumerate(args) if a == "--cpus"]  # noqa: E731
    for role in ("implementor", "reviewer"):
        cfg = {**factory, "ai": {**factory["ai"], f"{role}_session_usd": 1.0}}
        assert cpus(agents.run_args(cfg, role, Path("/w"), "n")) == ["1.5"], role
    assert cpus(shlex.split(agents.contained(factory, "true", Path("/w"))[1])) == ["4"]       # a suite's: its 4
    for unset in ({}, {"session_cpus": ""}):                                                 # unset: the suite's 4
        cfg = {**factory, "agents": {**factory["agents"], **unset}}
        cfg["agents"].pop("session_cpus") if not unset else None
        assert cpus(agents.run_args(cfg, "implementor", Path("/w"), "n")) == ["4"]
    for bad in (0, -1, 4.5, 64, "lots", "nan"):                                              # (a ceiling: lesson-4)
        cfg = {**factory, "agents": {**factory["agents"], "session_cpus": bad}}
        with pytest.raises(agents.Refused, match="session_cpus"):
            agents.run_args(cfg, "implementor", Path("/w"), "n")
        assert cpus(shlex.split(agents.contained(cfg, "true", Path("/w"))[1])) == ["4"]      # suites: not refused
        assert cpus(agents.limits(cfg, "queue", 8)) == ["8"]


def no_session(lines: list[dict]) -> bool:
    return not any(x.get("type") == "result" or str(x.get("event", "")).startswith("session.") for x in lines)


@pytest.mark.slow
def test_missing_browser_stops_the_round_rather_than_skipping(tmp_path):
    f = Factory(tmp_path)
    gid = ready(f)
    settings = f.config.read_text().replace("[suites]\n", "[suites]\nbuild_browser = true\n")   # (off by default)
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


def test_a_rerun_is_timed_by_the_suite_that_failed(monkeypatch):
    # onmain imports agents, fac and flakes from beside it: each given fresh here (undone after the test), so no
    # module an earlier test in this worker left in sys.modules (a stub, a patched fac.git) or on sys.path decides it
    for name in ("fac", "agents", "flakes"):                 # (fac first: agents and flakes import it)
        monkeypatch.setitem(sys.modules, name, module(name))
    onmain = module("onmain")
    assert onmain.fac is sys.modules["fac"] and onmain.flakes.fac is onmain.fac and callable(onmain.agents.clone)
    # room() reads the clock itself: a fixed one for this onmain alone, so how long a loaded container takes between
    # this test's reading and room()'s (or a clock another test moves) cannot decide the arithmetic
    now = 1_000_000.0
    monkeypatch.setattr(onmain, "time", types.SimpleNamespace(time=lambda: now))
    room, soon = onmain.room, now + 200
    took = {"unit": {"seconds": 10}, "browser": {"seconds": 400}}
    assert not room({**took, "failed": "browser"}, soon) and room({**took, "failed": "unit"}, soon)
    assert room({"unit": {"seconds": 10}}, now + onmain.LEAST + 1) and not room({"unit": {"seconds": 10}}, now + onmain.LEAST)


def test_room_holds_on_a_slow_clock(monkeypatch):
    """The container is slow: each reading of the wall clock is 150 s after the last (a worker starved under -n 8).
    The rerun test still judges room() by its own arithmetic, not by the time that passed between its readings."""
    t = [time.time()]

    def slow():
        t[0] += 150
        return t[0]
    monkeypatch.setattr(time, "time", slow)
    with pytest.MonkeyPatch.context() as inner:
        test_a_rerun_is_timed_by_the_suite_that_failed(inner)


def test_room_holds_after_another_test_left_a_stub_fac(monkeypatch):
    """An earlier test in the worker left stand-ins: a fac and an agents lacking what onmain uses, no flakes module,
    and dev/bin not on sys.path. The rerun test still loads onmain on its own fresh modules, and leaves the stubs."""
    stub_fac, stub_agents = types.ModuleType("fac"), types.ModuleType("agents")
    monkeypatch.setitem(sys.modules, "fac", stub_fac)
    monkeypatch.setitem(sys.modules, "agents", stub_agents)
    monkeypatch.delitem(sys.modules, "flakes", raising=False)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p or ".").resolve() != BIN.resolve()])
    with pytest.MonkeyPatch.context() as inner:
        test_a_rerun_is_timed_by_the_suite_that_failed(inner)
    assert sys.modules["fac"] is stub_fac and sys.modules["agents"] is stub_agents and "flakes" not in sys.modules


@pytest.mark.slow
def test_a_browser_failure_that_skips_alone_is_not_a_flake(tmp_path):
    """A browser test failed, then skipped when run again alone (`rerun`): the skip is no pass, so no flake.seen and
    no free retry; it counts against the gap."""
    f = Factory(tmp_path)
    gid = ready(f)
    f.config.write_text(f.config.read_text()
                        .replace('browser = "true"', 'browser = "echo FAILED tests/test_items_page.py::test_b - x; false"')
                        .replace('rerun = "echo again {tests}"', 'rerun = "echo 1 skipped in 0.01s"')   # (no -rs lines)
                        .replace("[suites]\n", "[suites]\nbuild_browser = true\n"))
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    assert f.item(gid)["fields"]["suites_fast"]["failed"] == "browser"


# ---- the merge queue's suites in containers (dev/records/merge-queue-in-docker.md)

# A stand-in `docker` on PATH: `run` logs its arguments and runs its command (after the image) in the folder mounted
# at /work, or with none in a new empty STATE/copies/<name> (given its stdin with -i, as a copy is piped in), a
# process group of its own (as a container outlives its killed client), listed in STATE/running/<name> while it runs;
# `kill`/`rm` kill that group by name; `ps --filter name=X` lists those running. STATE/fails: `run` fails as Docker's
# own error does (exit 125), before any command. STATE/down: Docker unreachable, every command failing as with no
# daemon.
FAKE_DOCKER = """\
import json, os, signal, subprocess, sys
from pathlib import Path
state, args = Path(STATE), sys.argv[1:]
with open(state / "calls.jsonl", "a") as f:
    f.write(json.dumps(args) + "\\n")
running = state / "running"
if (state / "down").exists():                       # (an outage: no daemon answers any command)
    print("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
          file=sys.stderr)
    sys.exit(125 if args[0] == "run" else 1)
if args[0] == "run":
    if (state / "fails").exists():
        sys.exit(print("docker: Error response from daemon: no such image", file=sys.stderr) or 125)
    name = args[args.index("--name") + 1]
    work = next((a[:-len(":/work")] for a in args if a.endswith(":/work")), None)   # a bind mount, or a new /work
    if work is None:
        work = state / "copies" / name
        work.mkdir(parents=True)
    p = subprocess.Popen(args[args.index("the-agent-image") + 1:], cwd=work, start_new_session=True,
                         stdin=None if "-i" in args else subprocess.DEVNULL)
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
    for a in got.values():
        assert flag(a, "--network") == ["none"] and flag(a, "--cpuset-cpus") == ["12-23"] and "--init" in a
        assert "PYTEST_ADDOPTS=-o faulthandler_timeout=300" in flag(a, "-e")   # half the 10 min stall limit
        cov = (f.model / "run" / "coverage").resolve()
        assert flag(a, "-v") == [f"{cov}:{cov}"] and "-i" in a             # the checkout a copy (piped in), not a mount
        assert "UV_PROJECT_ENVIRONMENT=/opt/venv" in flag(a, "-e")               # never the checkout's .venv
        assert {e.split("=")[0] for e in flag(a, "-e")} <= set(QUEUE_ENV)       # each one Factory.env never inherits
        assert a[-6:-3] == ["the-agent-image", "sh", "-c"] and flag(a, "--name")[0].startswith(
            "ergostat-factory-suite-queue-")                                   # (counted by the load interlock)
    assert flag(got[cfg["unit"]], "--cpus") == ["8"] and flag(got[cfg["browser"]], "--cpus") == ["4"]
    assert not list((state / "running").iterdir())                    # each removed by name once it ended


@pytest.mark.slow
def test_the_queue_container_test_passes_inside_the_queues_own_container(tmp_path, monkeypatch):
    # as the queue's unit suite runs it: in a container with the queue's settings already set (agents.queued, fac.suite)
    for name, value in (("PYTEST_ADDOPTS", "-o faulthandler_timeout=300"), ("UV_PROJECT_ENVIRONMENT", "/opt/venv"),
                        ("PYTHONPYCACHEPREFIX", "/tmp/pycache"), ("RUFF_CACHE_DIR", "/tmp/ruff"),
                        ("SPLIT_SHOTS", "/tmp/split-shots")):
        monkeypatch.setenv(name, value)
    test_each_queue_suite_runs_in_a_container_on_the_queue_cpuset_with_no_network(tmp_path)


@pytest.mark.slow
def test_a_queue_suite_reads_a_copy_of_the_checkout_never_the_macs_folder(tmp_path):
    """dev/records/suites-copy-their-checkout-into-the-container.md, 1: the checkout (and its git directory, inside it)
    is tarred into the container's stdin and unpacked at /work; nothing of it is bind-mounted (Docker Desktop's file
    sharing keeps a handle on every file read through one); what the suite writes in /work stays in the copy, and
    run/coverage/ is still mounted, so what it writes there reaches run/."""
    seen, cov = tmp_path / "seen", (tmp_path / "instance" / "run" / "coverage")
    unit = (f"ls -A > {seen}; git rev-parse HEAD >> {seen}; cat app.py >> {seen}; touch made-in-the-copy; "
            f"touch {cov}/from-the-suite; echo run >> {tmp_path / 'runs'}")
    f, state = boxed(tmp_path, unit=unit)
    (f.checkout / ".venv").mkdir()
    (f.checkout / ".venv" / "big").write_text("the Mac's own environment")
    (f.checkout / "untracked.txt").write_text("as the Mac left it")
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.merged", "gap.push-asked"] and suite_runs(f) == 1
    got = seen.read_text().split()
    assert {"app.py", ".git", "docs", "untracked.txt"} <= set(got) and ".venv" not in got   # all but its .venv
    assert "print('hello')" in seen.read_text() and len(got[got.index("print('hello')") - 1]) == 40  # git works
    assert not (f.checkout / "made-in-the-copy").exists() and (cov / "from-the-suite").exists()
    copies = list((state / "copies").iterdir())
    assert len(copies) == 4 and [c.name for c in copies if (c / "made-in-the-copy").exists()]   # one per suite
    checkout = str(f.checkout.resolve())
    for a in runs_of(state):                                            # no folder of the checkout's mounted, in any
        assert not [v for v in flag(a, "-v") if v.split(":")[0].startswith(checkout)], a


def test_a_triage_worktree_is_copied_and_only_its_shared_git_directory_mounted(tmp_path, monkeypatch):
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    cfg = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())
    cfg["paths"]["run"] = str(tmp_path / "run")
    work, common = tmp_path / "wt" / ".triage", tmp_path / "checkout" / ".git"
    work.mkdir(parents=True)
    monkeypatch.setattr(agents.fac, "git", lambda *a: str(common))
    copy, run = agents.queued(cfg, "rerun", "echo again", work, "triage")[1].split(" | ")
    assert shlex.split(copy) == ["COPYFILE_DISABLE=1", "tar", "-C", str(work.resolve()), "--exclude", "./.venv",
                                 "--no-xattrs", "--no-acls", "-cf", "-", "."]
    a = shlex.split(run)
    cov = (tmp_path / "run" / "coverage").resolve()
    assert flag(a, "-v") == [f"{cov}:{cov}", f"{common.resolve()}:{common.resolve()}:ro"] and "-i" in a
    assert a[-3:] == ['tar -xf - || exit 125; exec sh -c "$1"', "sh", "echo again"]   # unpacked, or not started


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


def test_the_implementor_is_told_its_clone_has_no_remote(tmp_path):
    """gap/implementor-clone-has-no-remote: publish removes the clone's remote (no host path in the container), and the
    prompts say so, so a true "origin/main is unknown here" is neither reported as a fault nor failed as false."""
    from tests.test_factory import git
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    drop, work = tmp_path / "drop.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(drop))
    git(tmp_path, "clone", "-q", str(drop), str(work))
    git(work, "checkout", "-q", "-b", "factory/alpha-thing")
    git(work, "commit", "-q", "--allow-empty", "-m", "definition")
    was = agents.publish({}, work, "alpha-thing")
    assert git(drop, "rev-parse", "factory/alpha-thing") == was           # published first
    assert git(work, "remote") == "" and not git(work, "for-each-ref", "refs/remotes")   # then no remote at all
    implementor = " ".join((ROOT / "dev" / "prompts" / "implementor.md").read_text().split())
    assert "The clone has no remote, by design" in implementor
    assert "`origin/*` does not exist here, local `{base}` is the base as of the clone" in implementor
    assert "other gaps' branches are absent. Neither is a fault to report." in implementor
    assert "landed work, it is on `{base}`, or this gap waits for it" in implementor
    reviewer = " ".join((ROOT / "dev" / "prompts" / "reviewer.md").read_text().split())
    assert "Your clone is not the implementor's" in reviewer
    assert "A ref visible to you does not disprove what the implementor says of its own clone" in reviewer
    assert "such a statement is not a finding" in reviewer


# ---- research-design-queues-sessions-see-a-demo: a designer, and an implementor, may start a demo and walk it

DEMO_UP, WALK = "uv run python scripts/demo_up.py", f"uv run --with {PIN} python scripts/walk.py"
REVIEWER = ["Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"]


class Kept:                       # (a sessions.Session's names, as run_args reads them)
    HOME, stem, sid = "/home/dev/.claude/projects", "alpha-thing-designer-1", "0" * 36

    def __init__(self, raw):
        self.raw = raw


def factory_cfg(tmp_path, **agents_set) -> dict:
    cfg = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())
    cfg["paths"]["run"] = str(tmp_path / "run")
    cfg["agents"].update(agents_set)
    return cfg


def mounts(args: list[str]) -> list[str]:
    return flag(args, "-v")


def test_designer_session_argv_mounts_shots_and_readonly_work(tmp_path, monkeypatch):
    import contextlib
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    cfg, keep = factory_cfg(tmp_path), Kept(tmp_path / "raw")
    designer = agents.run_args(cfg, "designer", Path("/w"), "n", keep)
    reviewer = agents.run_args(cfg, "reviewer", Path("/w"), "n", keep)
    shots = f"{(tmp_path / 'run' / 'shots' / keep.stem).resolve()}:/shots"
    assert "/w:/work:ro" in mounts(designer)
    assert sorted(mounts(designer)) == sorted(mounts(reviewer) + [shots])          # one mount new, and no other
    cut = lambda a: a[:a.index(cfg["agents"]["image"])]  # noqa: E731              # (docker's part, before the image)
    d, r = cut(designer), cut(reviewer)
    i = d.index(shots)
    d = d[:i - 1] + d[i + 1:]                                                       # its "-v" and the mount taken out
    assert len(d) == len(r) and [(x, y) for x, y in zip(d, r, strict=True) if x != y] == [("3", "1.5")]   # only --cpus
    # without a kept session, the container's name names the folder; a name that is not one is refused
    named = f"{(tmp_path / 'run' / 'shots' / 'n').resolve()}:/shots"
    assert named in mounts(agents.run_args(cfg, "designer", Path("/w"), "n"))
    for bad in ("..", "a/b", "", "A"):
        with pytest.raises(agents.Refused, match="pictures folder"):
            agents.run_args(cfg, "designer", Path("/w"), bad)
    # the session itself: the folder made on the host, the brief told to pass --shots /shots, the argv as above
    ran = []
    monkeypatch.setattr(agents, "token", lambda cfg: "tok-123")
    monkeypatch.setattr(agents, "sweep", lambda cfg: [])
    monkeypatch.setattr(agents, "egress", lambda cfg: None)
    monkeypatch.setattr(agents, "killed", lambda name: agents.RUNNING.discard(name))
    res = type(sys)("resources")
    res.sampled = lambda *a: contextlib.nullcontext({})
    monkeypatch.setitem(sys.modules, "resources", res)
    monkeypatch.setattr(agents.subprocess, "run", lambda argv, **k: ran.append((argv, k["input"])) or
                        subprocess.CompletedProcess(argv, 0, '{"type": "result"}', ""))
    keep.copy = type("C", (), {"follow": lambda self: None})()
    assert agents.session(cfg, "designer", "look at the Items tab", Path("/w"), keep=keep)["type"] == "result"
    (argv, brief), = ran
    assert (tmp_path / "run" / "shots" / keep.stem).is_dir() and shots in mounts(argv) and "/w:/work:ro" in mounts(argv)
    assert brief.startswith("look at the Items tab") and "--shots /shots" in brief
    # a bad designer_cpus: refused with its reason before any container is run
    with pytest.raises(agents.Refused, match="designer_cpus"):
        agents.session(factory_cfg(tmp_path, designer_cpus=9), "designer", "b", Path("/w"), keep=keep)
    assert len(ran) == 1 and not agents.RUNNING
    assert agents.TIMEOUTS["designer"] == 3600 and module("fac").STANDIN["designer"]
    assert (cfg["ai"]["designer_model"], cfg["ai"]["designer_session_usd"]) == ("opus", 2.0)


def test_designer_and_implementor_may_run_demo_and_walk():
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    for role in ("designer", "implementor"):
        assert may(f"{DEMO_UP} start ops --port 8801", role) and may(f"{DEMO_UP} stop ops", role), role
        assert may(f"{WALK} steps.json --shots /shots", role) and may(f"{WALK} - --shots /shots", role), role
        assert not may("uv run python scripts/walk.py x", role) and not may("uv run python scripts/demo_check.py", role)
        assert not may(f"{DEMO_UP}x start ops", role) and not may("curl http://127.0.0.1:8801", role)
    assert agents.TOOLS["designer"] == REVIEWER + agents.SEE                  # exactly the reviewer's and the two
    assert agents.SEE == [f"Bash({DEMO_UP}:*)", f"Bash({WALK}:*)"]
    assert set(agents.SEE) <= set(agents.TOOLS["implementor"])
    others = ("reviewer", "planner", "groomer", "researcher", "librarian")
    assert not [r for r in others if may(f"{DEMO_UP} start ops", r) or may(f"{WALK} x", r)]
    cfg = {"ai": {"designer_model": "opus", "designer_session_usd": 2.0}}
    args = agents.claude_args(cfg, "designer")
    assert args[args.index("--allowedTools") + 1].split(",") == agents.TOOLS["designer"]
    assert args[args.index("--tools") + 1] == "Bash,Glob,Grep,Read"             # (no Edit, no Write)


def test_designer_cpus_bounds(tmp_path):
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    cpus = lambda cfg, role, brief="": flag(agents.run_args(cfg, role, Path("/w"), "n", brief=brief), "--cpus")  # noqa: E731
    web = "## Files to touch\n\n- ergostat/web/items.js\n"
    cfg = factory_cfg(tmp_path)
    assert cfg["agents"]["designer_cpus"] == 3
    assert cpus(cfg, "designer") == ["3"] and cpus(cfg, "implementor", web) == ["3"]
    assert cpus(cfg, "implementor", "ergostat/spec/x.py") == ["1.5"] and cpus(cfg, "reviewer", web) == ["1.5"]
    absent = factory_cfg(tmp_path)
    absent["agents"].pop("designer_cpus")
    assert cpus(absent, "designer") == ["3"]                                       # its default
    for ok in (4, 0.5, "2"):
        assert cpus(factory_cfg(tmp_path, designer_cpus=ok), "designer") == [f"{float(ok):g}"]
    for bad in (0, -1, 4.5, 64, "lots", "nan", "inf"):                            # (a ceiling: lesson-4)
        cfg = factory_cfg(tmp_path, designer_cpus=bad)
        for role, brief in (("designer", ""), ("implementor", web)):
            with pytest.raises(agents.Refused, match=r"\[agents\] designer_cpus = .*at most 4"):
                cpus(cfg, role, brief)
        assert cpus(cfg, "implementor", "no web here") == ["1.5"]                  # not its setting: not refused
        assert cpus(cfg, "reviewer") == ["1.5"]


def test_no_proxy_names_loopback(tmp_path):
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    cfg = factory_cfg(tmp_path)
    for role in ("implementor", "reviewer", "designer", "planner"):
        env = flag(agents.run_args(cfg, role, Path("/w"), "n"), "-e")
        assert "NO_PROXY=127.0.0.1,localhost" in env and "no_proxy=127.0.0.1,localhost" in env, role
        assert not [e for e in env if e.lower().startswith("no_proxy=") and not e.endswith("=127.0.0.1,localhost")]


def test_reviewer_tools_unchanged(tmp_path):
    sys.modules.setdefault("fac", module("fac"))
    agents = module("agents")
    assert agents.TOOLS["reviewer"] == REVIEWER                                   # the reviewer gains nothing
    for role in ("planner", "plan_reviewer", "join_judge", "pipeline_manager", "groomer"):
        assert agents.TOOLS[role] == REVIEWER, role
    assert agents.TOOLS["researcher"] == REVIEWER + ["WebSearch"]
    args = agents.run_args(factory_cfg(tmp_path), "reviewer", Path("/w"), "n")
    assert not [m for m in mounts(args) if m.endswith(":/shots")] and "/w:/work:ro" in mounts(args)
