"""The implementor's environment can run the four browser files (docs/roadmap/overnight/implementors-can-run-the-four.md):
Playwright and its Chromium are in the image its session and its suites run in, the session may run the browser files
under the watchdog, and a missing browser stops the round before it starts instead of letting the files skip."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tomllib

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
    # the session may run the [suites] browser command itself, under the watchdog
    sys.modules.setdefault("fac", module("fac"))
    allowed = [t[len("Bash("):-len(":*)")] for t in module("agents").TOOLS["implementor"] if t.startswith("Bash(")]
    assert any(cfg["browser"].startswith(a + " ") for a in allowed) and cfg["browser"].startswith(
        "uv run python scripts/suite_watch.py -- ")
    # and here, in the environment this suite runs in (the implementor's image, in the factory's suite containers),
    # the check the round makes launches Chromium: no Playwright or no browser fails this test, never skips it
    r = subprocess.run(["sh", "-c", cfg["browser_ready"]], cwd=ROOT, capture_output=True, text=True, timeout=300)
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
