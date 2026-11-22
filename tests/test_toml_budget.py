"""``[budget]`` in ``ergostat.toml`` (SPEC §9.9): its keys, and ``runner.run_agent`` asking the permit."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from ergostat import model as mdl
from ergostat import runner
from ergostat.cli import main
from ergostat.costs import budget
from ergostat.decisions import extract
from ergostat.store import Project
from tests import test_ai_calls_budget as ta
from tests import test_run_budget as tr

PY = sys.executable
TOML = """
name = "t"
{budget}
[[agent]]
name = "a"
{kind}command = "{py} -c 'open(\\"started-a\\", \\"a\\").write(\\"x\\")'"
every = "1h"

[[agent]]
name = "b"
command = "true"
every = "1h"
"""


def toml(d, budget_="[budget]\ndaily = 1.5\nmax-cost = 1\n", kind="") -> Project:
    d.mkdir(exist_ok=True)
    (d / "ergostat.toml").write_text(TOML.format(budget=budget_, kind=kind, py=PY))
    return Project(mdl.load(d))


def evs(p, type: str) -> list[dict]:
    return p.events.query(n=None, type=type)


@pytest.mark.parametrize("table, says", [
    ("daily = 0\nmax-cost = 0.5", "[budget].daily: out of bounds"),
    ("daily = 10001\nmax-cost = 0.5", "[budget].daily: out of bounds"),
    (f"daily = 1{'0' * 400}\nmax-cost = 0.5", "[budget].daily: out of bounds"),
    ("daily = 1\nmax-cost = 2", "[budget].max-cost: out of bounds"),
    ("daily = 1\nmax-cost = 0", "[budget].max-cost: out of bounds"),
    ("daily = 1", "[budget]: missing max-cost"),
    ("max-cost = 1", "[budget]: missing daily"),
    ("daily = 1\nmax-cost = 1\nweekly = 3", "[budget]: unknown key 'weekly'"),
    ('daily = "1"\nmax-cost = 1', "[budget].daily: a number of dollars"),
    ("daily = 1\nmax-cost = true", "[budget].max-cost: a number of dollars"),
    ("daily = nan\nmax-cost = 1", "[budget].daily: a number of dollars"),
])
def test_toml_budget_keys(tmp_path, table, says):
    with pytest.raises(mdl.ModelError) as e:
        toml(tmp_path, f"[budget]\n{table}\n")
    assert str(e.value).startswith(says)
    with pytest.raises(mdl.ModelError, match=r"^\[budget\]: a table"):
        toml(tmp_path / "flat", 'budget = 3\n')
    p = toml(tmp_path / "ok")
    assert (p.model.budget.daily, p.model.budget.max_cost) == (1.5, 1.0) and toml(tmp_path / "none", "").model.budget is None


def test_run_agent_refused(tmp_path, capsys):
    p = toml(tmp_path)
    ta.spend(p, 1.0)                                   # 1 of 1.5 spent: a reserve of 1 does not fit
    r = runner.run_agent(p, p.model.agents["a"])
    assert r["budget"] and r["note"].startswith("refused: budget: ")
    assert not evs(p, "agent.started") and not (p.repo / "started-a").exists()
    assert len(evs(p, budget.REFUSED)) == 1 and evs(p, budget.REFUSED)[0]["item"] == "a"
    assert main(["-C", str(tmp_path), "agent", "a", "--now"]) == 1
    assert "refused: budget: " in capsys.readouterr().err
    assert not evs(p, "agent.started") and not (p.repo / "started-a").exists()
    q = toml(tmp_path / "free", kind='kind = "program"\n')    # declared a program: free, so it runs all the same
    ta.spend(q, 1.5)
    assert "budget" not in runner.run_agent(q, q.model.agents["a"])
    assert evs(q, "agent.started")[0]["data"]["reserve"] == 0.0 and (q.repo / "started-a").exists()
    assert budget.fold(q, budget.of(q.model)) == (pytest.approx(1.5), 0.0)


def test_run_agent_charged_and_ended(tmp_path):
    p = toml(tmp_path)                                 # "a" has no kind written: charged, never free
    runner.run_agent(p, p.model.agents["a"])
    s = evs(p, "agent.started")[0]
    assert s["data"]["reserve"] == 1.0 and s["data"]["pid"] == os.getpid() and s["id"] not in budget.OPEN
    assert budget.fold(p, budget.of(p.model)) == (pytest.approx(1.0), 0.0)     # ended at no known cost: its reserve
    assert runner.run_agent(p, p.model.agents["b"])["budget"]                    # 1 + 1 > 1.5


def test_run_agent_crash_closes_reserve(tmp_path, monkeypatch):
    p = toml(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("after the start")
    monkeypatch.setattr(runner, "Recorder", boom)
    with pytest.raises(RuntimeError):
        runner.run_agent(p, p.model.agents["a"])
    s, c = evs(p, "agent.started"), evs(p, budget.CLOSED)
    assert len(s) == 1 and len(c) == 1 and c[0]["data"]["run"] == s[0]["id"] and c[0]["data"]["cost_usd"] is None
    assert s[0]["id"] not in budget.OPEN and not (p.repo / "started-a").exists()
    assert budget.fold(p, budget.of(p.model)) == (pytest.approx(1.0), 0.0)     # charged its reserve


COMPETITOR = """
import sys
from pathlib import Path
from ergostat import model as mdl, runner
from ergostat.costs import budget
from ergostat.store import Project
d = Path(sys.argv[1])
p = Project(mdl.load(d))
budget._between = lambda: (d / "read").write_text("x")
(d / "asking").write_text("x")
print("refused" if runner.run_agent(p, p.model.agents["b"], why="by hand").get("budget") else "permitted")
"""


def test_run_agent_lock_across_processes(tmp_path, monkeypatch):
    p, procs = toml(tmp_path), []                      # daily 1.5, max-cost 1: room for one

    def hook():
        procs.append(subprocess.Popen([PY, "-c", COMPETITOR, str(tmp_path)], stdout=subprocess.PIPE, text=True,
                                      cwd=os.getcwd()))
        assert tr.wait_for(lambda: (tmp_path / "asking").exists() or procs[0].poll() is not None, 60)
        end = time.time() + 1.0                        # (the one timed wait: expected when the lock works)
        while time.time() < end and not (tmp_path / "read").exists():
            time.sleep(0.01)
    monkeypatch.setattr(budget, "_between", hook)
    runner.run_agent(p, p.model.agents["a"])
    out, _ = procs[0].communicate(timeout=60)
    assert out.strip() == "refused" and not (tmp_path / "read").exists()
    assert [e["item"] for e in evs(p, "agent.started")] == ["a"] and len(evs(p, budget.REFUSED)) == 1


def test_toml_runner_recovers(tmp_path):
    p = toml(tmp_path)
    gone = subprocess.Popen([PY, "-c", "pass"])
    gone.wait()
    s = p.events.add("agent.started", item="a", source="ergostat", data={"reserve": 1.0, "pid": gone.pid})
    r = runner.Runner(p, say=lambda s: None)
    r._recover(every=0)                                # (as Runner.start does, before any run)
    assert [c["data"]["run"] for c in evs(p, budget.CLOSED)] == [s["id"]]
    p.events.add("agent.started", item="a", source="ergostat", data={"reserve": 1.0, "pid": gone.pid})
    r._recover()                                       # on its loop: within the minute, not again
    assert len(evs(p, budget.CLOSED)) == 1


def test_toml_calls_read_budget(tmp_path, monkeypatch):
    p = toml(tmp_path)
    log = ta.standin(tmp_path, monkeypatch, mode="0.01")
    ta.spend(p, 1.5)                                   # the whole day's budget
    got = extract.run(p, [str(ta.transcript(tmp_path))], model="haiku", out=open(os.devnull, "w"))
    assert ta.starts(log) == [] and got["spent"]["stopped"].startswith("budget:")
    r = evs(p, budget.REFUSED)
    assert len(r) == 1 and r[0]["item"] == "decisions-extract" and r[0]["data"]["reserve"] == 1.0
    q = toml(tmp_path / "room")                        # room: the call asks, reserving max-cost, and is closed
    extract.run(q, [str(ta.transcript(tmp_path))], model="haiku", out=open(os.devnull, "w"))
    assert [c["data"]["reserve"] for c in evs(q, budget.CALL)] == [1.0] and len(evs(q, budget.CLOSED)) == 1
    assert len(ta.starts(log)) == 1
    with pytest.raises(Exception, match="no budget"):
        budget.left(toml(tmp_path / "none", ""), None)
    assert budget.left(q, None) == pytest.approx(1.5 - 0.01)


def test_no_budget_runs_unchanged(tmp_path):
    p = toml(tmp_path, "")
    runner.run_agent(p, p.model.agents["a"])
    assert "reserve" not in evs(p, "agent.started")[0]["data"] and not evs(p, "budget.refused")
    assert (p.repo / "started-a").exists()             # (no budget: as before)
