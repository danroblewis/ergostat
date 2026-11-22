"""The implementor's environment can run the four browser files (docs/roadmap/overnight/implementors-can-run-the-four.md):
Playwright and its Chromium are in the image its session and its suites run in, the session may run the browser files
under the watchdog, and a missing browser stops the round before it starts instead of letting the files skip."""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

from tests.test_factory import ROOT, Factory, module, ready

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
    (tmp_path / "tests" / "test_one.py").write_text("import os\n\ndef test_one():\n"
                                                     "    assert 'PYTEST_XDIST_WORKER' not in os.environ\n")
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
        with pytest.raises(agents.Refused, match="session_cpus"):
            agents.run_args({**factory, "agents": {**factory["agents"], "session_cpus": bad}}, "implementor",
                            Path("/w"), "n")


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
                        .replace('rerun = "echo again {tests}"', 'rerun = "echo 1 skipped in 0.01s"')   # (no -rs lines)
                        .replace("[suites]\n", "[suites]\nbuild_browser = true\n"))
    said, _ = f.run("implement.py", gid)
    assert said == ["gap.started", "gap.measured"] and f.item(gid)["fields"]["build_failures"] == 1
    assert f.item(gid)["fields"]["suites_fast"]["failed"] == "browser"
