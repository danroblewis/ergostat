"""SPEC §9.9 for ``ergostat.toml`` models: ``[budget]`` is read and bounded, and every ``runner.run_agent`` asks the
permit under its flock (dev/records/ergostat-s-own-ai-calls-under.md)."""

import json
import os
import subprocess
import threading
import time
import tomllib
from types import SimpleNamespace

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.cli import main
from ergostat.costs import budget
from ergostat.store import Project
from tests.conftest import DISK


def project(tmp_path, kind="ai", command="touch ran.marker", daily=1.0, most=0.5, name="cleaner"):
    d = tmp_path / f"{name}-{kind}"
    d.mkdir()
    toml = DISK.replace('kind = "program"', f'kind = "{kind}"').replace('"python3 clean.py"', json.dumps(command)) \
        .replace('"cleaner"', f'"{name}"')
    (d / "ergostat.toml").write_text(toml + f"\n[budget]\ndaily = {daily}\nmax-cost = {most}\n")
    return Project(mdl.load(d))


def spend(p, cost):
    p.events.add(budget.CLOSED, item="earlier", source=budget.SOURCE, data={"run": "earlier", "cost_usd": cost})


def evs(p, t):
    return p.events.query(n=None, type=t)


def run(p):
    return runner.run_agent(p, next(iter(p.model.agents.values())))


def ran(p):
    return (p.repo / "ran.marker").exists()


def test_toml_budget_parsed_and_bounded():
    base = tomllib.loads(DISK)
    m = mdl.parse({**base, "budget": {"daily": 5, "max-cost": 1.5}})
    assert (m.budget.daily, m.budget.max_cost) == (5.0, 1.5) and mdl.parse(base).budget is None
    for b, key in [({"daily": 5}, "max-cost"), ({"daily": True, "max-cost": 1}, "daily"),
                   ({"daily": float("nan"), "max-cost": 1}, "daily"), ({"daily": 5, "max-cost": float("inf")}, "max-cost"),
                   ({"daily": 10 ** 400, "max-cost": 1}, "daily"), ({"daily": 5, "max-cost": 1, "weekly": 9}, "weekly"),
                   ({"daily": 20000, "max-cost": 1}, "daily"), ({"daily": 5, "max-cost": 6}, "max-cost"),
                   ({"daily": 5, "max-cost": 0}, "max-cost"), ({"daily": "5", "max-cost": 1}, "daily")]:
        with pytest.raises(mdl.ModelError, match=key):
            mdl.parse({**base, "budget": b})
    with pytest.raises(mdl.ModelError, match="budget"):
        mdl.parse({**base, "budget": 5})


def test_toml_run_refused_when_day_spent(tmp_path, capsys):
    p = project(tmp_path)
    spend(p, 0.6)                                             # 0.6 spent + 0 reserved + 0.5 > 1
    r = run(p)
    assert "refused: budget" in r["note"] and "0.60 spent" in r["budget"]
    assert not evs(p, "agent.started") and not ran(p)
    (no,) = evs(p, budget.REFUSED)
    assert no["item"] == "cleaner" and no["data"]["reserve"] == 0.5
    assert main(["-C", str(p.repo), "agent", "cleaner", "--now"]) == 1
    out = "".join(capsys.readouterr())
    assert "refused: budget: 0.60 spent" in out and "ran in" not in out
    assert not evs(p, "agent.started") and not ran(p)


def test_toml_permit_holds_the_lock(tmp_path, monkeypatch):
    p = project(tmp_path)
    spend(p, 0.4)                                             # one run of 0.5 fits; a second does not
    second, waited = [], []

    def competitor():
        second.append(run(p))

    def hook():                                               # under the first's flock: the second asks in the gap
        if waited:
            return                                            # (the second, if it got this far: no third)
        t = threading.Thread(target=competitor, daemon=True)
        waited.append(t)
        t.start()
        t.join(1.0)
        waited.append(t.is_alive())                           # it waits for the flock
    monkeypatch.setattr(budget, "_between", hook)
    first = run(p)
    t, blocked = waited
    t.join(10)
    assert first["exit"] == 0 and "budget" not in first
    assert len(second) == 1 and second[0].get("budget"), second
    assert len(evs(p, "agent.started")) == 1 and blocked


@pytest.mark.parametrize("kind", ["program", "decision", "rule", "ai", "narrow-ai"])
def test_toml_free_kinds_only(tmp_path, kind):
    p = project(tmp_path, kind=kind)
    spend(p, 0.9)                                             # the day is spent
    r = run(p)
    if kind in ("ai", "narrow-ai"):
        assert r["budget"] and not evs(p, "agent.started") and not ran(p)
        q = project(tmp_path, kind=kind, name="other")        # with the day free: it reserves max-cost
        assert run(q)["exit"] == 0
        (s,) = evs(q, "agent.started")
        assert s["data"]["reserve"] == 0.5
    else:
        (s,) = evs(p, "agent.started")
        assert r["exit"] == 0 and ran(p) and s["data"]["reserve"] == 0.0


def test_toml_run_raised_is_closed_at_reserve(tmp_path, monkeypatch):
    p = project(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("the recorder broke")
    monkeypatch.setattr(runner, "Recorder", boom)
    with pytest.raises(RuntimeError):
        run(p)
    (s,) = evs(p, "agent.started")
    (c,) = evs(p, budget.CLOSED)
    assert c["data"]["run"] == s["id"] and c["data"]["cost_usd"] is None
    assert budget.fold(p, SimpleNamespace(budget=p.model.budget)) == (0.5, 0.0)
    assert s["id"] not in budget.OPEN and not ran(p)


def fake_claude(tmp_path, monkeypatch):
    """A ``claude`` on PATH that writes its argv, one per line, to args.txt and says "said" on stdout."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "claude").write_text('#!/bin/sh\nprintf "%s\\n" "$@" > args.txt\necho said\n')
    (bin_ / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")


def args_of(p):
    return (p.repo / "args.txt").read_text().splitlines()


def test_toml_claude_command_capped(tmp_path, monkeypatch):
    fake_claude(tmp_path, monkeypatch)
    p = project(tmp_path, command="claude -p hello --max-budget-usd 99 --model haiku")
    assert run(p)["exit"] == 0
    assert args_of(p) == ["--max-budget-usd", "0.5", "-p", "hello", "--model", "haiku"]


@pytest.mark.parametrize("command, after", [
    ("claude -p 'a | b --max-budget-usd 3' --max-budget-usd=99 | tr a-z A-Z > after.txt", "SAID"),
    ("claude -p 'a | b --max-budget-usd 3' && echo next --max-budget-usd 7 > after.txt", "next --max-budget-usd 7"),
    ("claude -p 'a | b --max-budget-usd 3' --max-budget-usd 99; echo next > after.txt", "next"),
    ("claude -p 'a | b --max-budget-usd 3' --max-budget-usd 99\necho next > after.txt", "next"),
    ("claude -p 'a | b --max-budget-usd 3' \\\n  --max-budget-usd 99 | cat > after.txt", "said"),
])
def test_toml_claude_capped_in_a_shell_line(tmp_path, monkeypatch, command, after):
    fake_claude(tmp_path, monkeypatch)                       # the cap goes to claude, not the command after it
    p = project(tmp_path, command=command)
    assert run(p)["exit"] == 0
    assert args_of(p) == ["--max-budget-usd", "0.5", "-p", "a | b --max-budget-usd 3"]
    assert (p.repo / "after.txt").read_text().strip() == after


@pytest.mark.parametrize("command, want", [
    ("claude -p $(cat p) --max-budget-usd 9 | tr a b", "claude --max-budget-usd 0.5 -p $(cat p) | tr a b"),
    ('claude -p "x; y" --max-budget-usd', 'claude --max-budget-usd 0.5 -p "x; y"'),
    ("/opt/claude -p x\n--max-budget-usd 9", "/opt/claude --max-budget-usd 0.5 -p x\n--max-budget-usd 9"),
])
def test_toml_cap_words_of_the_claude_call_only(command, want):
    assert runner.capped(command, 0.5) == want


def test_toml_orphan_recovered(tmp_path, monkeypatch):
    p = project(tmp_path, most=0.6)
    gone = subprocess.Popen(["true"])
    gone.wait()
    orphan = p.events.add("agent.started", item="cleaner", source=budget.SOURCE, data={"reserve": 0.6, "pid": gone.pid})
    assert run(p)["budget"] and not ran(p)               # 0 spent + 0.6 reserved + 0.6 > 1
    r = runner.Runner(p, say=lambda s: None)
    r._recover()
    (c,) = evs(p, budget.CLOSED)
    assert c["data"]["run"] == orphan["id"] and c["data"]["cost_usd"] is None
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 1.5 * budget.DAY)   # its charge, a day from the close, is over
    assert run(p)["exit"] == 0 and ran(p)
