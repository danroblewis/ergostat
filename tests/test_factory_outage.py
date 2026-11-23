"""An outage parks nothing (dev/records/safe-stalls-heal-themselves.md, done item 3; dev/bin/outage.py): a run that
fails because Docker or the AI service is unreachable is given back uncounted and put off, never a counted attempt, a
kill-rule count or a park, and its item runs again once the outage is over."""

from __future__ import annotations

import json
import time

import pytest

from tests.test_agents import boxed, git_head, runs_of
from tests.test_factory import approved_gaps, merges, module


def nacks(lines: list[dict]) -> list[dict]:
    return [x["nack"] for x in lines if "nack" in x]


@pytest.mark.slow
def test_a_docker_outage_during_a_queue_run_parks_nothing_and_it_lands_when_docker_returns(tmp_path):
    f, state = boxed(tmp_path)
    approved_gaps(f, {"a": 1})
    before = git_head(f)
    (state / "down").write_text("")
    said, lines = f.run("queue.py", "gap/a", lease={"attempt": 3, "attempts": 3})     # its last attempt, even
    (n,) = nacks(lines)
    assert n["count"] is False and n["after"] == "10m" and "outage: Docker is unreachable" in n["why"], n
    assert "gap.parked" not in said and "gap.sent-back" not in said and "gap.queue-failed" not in said, said
    a = f.item("gap/a")["fields"]
    assert not a.get("failed_gates") and not a.get("failed_suite") and git_head(f) == before, "main as it was"
    (state / "down").unlink()                                        # Docker back: taken again, and it lands
    said, lines = f.run("queue.py", "gap/a")
    assert "gap.merged" in said and merges(f) == ["a"], said
    assert not nacks(lines) and runs_of(state)


@pytest.mark.slow
def test_a_container_that_fails_while_docker_answers_is_no_outage(tmp_path):
    f, state = boxed(tmp_path)
    approved_gaps(f, {"a": 1})
    (state / "fails").write_text("")                                 # Docker's own error, its daemon up
    _, lines = f.run("queue.py", "gap/a", fails=True)
    assert not nacks(lines)


@pytest.fixture
def fac(monkeypatch):
    m = module("fac")
    return m, m._outage()


def guarded(fac, e: Exception, last: bool = True) -> tuple[int | None, list, list[dict]]:
    import contextlib
    import io
    stopped, out = [], io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            raise e
        except Exception:
            try:
                rc = fac.guarded({"lease": {"attempt": 2 if last else 1, "attempts": 2}}, time.time(), "build_hours",
                                 stopped.append)
            except type(e):
                rc = None
    return rc, stopped, [json.loads(x) for x in out.getvalue().splitlines() if x.startswith("{")]


def test_an_outage_on_the_last_attempt_is_given_back_uncounted_not_parked(fac, monkeypatch):
    fac, outage = fac
    monkeypatch.setattr(outage, "docker_down", lambda: "`docker info` failed (exit 1): Cannot connect")
    for e in (RuntimeError("docker network: Cannot connect to the Docker daemon"),
              RuntimeError("the implementor session answered no result (exit 125): docker: error during connect")):
        rc, stopped, lines = guarded(fac, e)
        assert rc == 0 and not stopped, "parked on an outage"
        assert nacks(lines)[-1]["count"] is False and "Docker is unreachable" in nacks(lines)[-1]["why"]
        measured = [x["data"] for x in lines if x.get("event") == "gap.measured"]
        assert measured and not any("build_hours" in d for d in measured), "its hours counted toward the kill rule"
    monkeypatch.setattr(outage, "docker_down", lambda: None)
    rc, stopped, lines = guarded(fac, RuntimeError("claude: error_during_execution: API Error: Connection error."))
    assert rc == 0 and not stopped and "the AI service is unreachable" in nacks(lines)[-1]["why"]
    rc, stopped, lines = guarded(fac, RuntimeError("the implementor session answered no result (exit 1): API Error: "
                                                   "Request timed out."), last=False)
    assert rc == 0 and nacks(lines)[-1]["count"] is False, "not its last attempt: still uncounted"


def test_a_failure_of_its_own_is_counted_and_parks_on_the_last_attempt(fac, monkeypatch):
    fac, outage = fac
    monkeypatch.setattr(outage, "docker_down", lambda: None)            # Docker answers: the failure is the run's
    rc, stopped, lines = guarded(fac, RuntimeError("docker run: no such image"))
    assert rc == 0 and stopped and not nacks(lines)
    rc, stopped, lines = guarded(fac, RuntimeError("claude: error_during_execution: API Error: 400 bad request"), False)
    assert rc is None and not stopped and not nacks(lines), "raised again: the attempt counted"
    monkeypatch.setattr(outage, "docker_down", lambda: "down")
    rc, stopped, _ = guarded(fac, ValueError("a verdict that does not parse"))
    assert stopped, "a failure that names no Docker is not read as Docker's, whatever the probe"
