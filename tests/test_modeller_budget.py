"""modeller-calls-ask-the-budget's acceptance tests (dev/records/modeller-calls-ask-the-budget.md): every call through
``numbers/modeller`` (the redesigner, the reviewer, the ``modelling ai`` tier) asks the day's budget first (SPEC
§9.9), a refusal starts no process and is said ``budget: …``, a call inside a run is counted once, and a structural
scan finds AI commands started only in the listed places."""

from __future__ import annotations

import ast
import io
import os
import sys
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.costs import budget
from ergostat.library.run import modelling as ml
from ergostat.numbers import modeller as md
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign as rd
from ergostat.numbers import redesigner as rdr
from ergostat.numbers import requests as rq
from ergostat.numbers import reviewer as rv
from ergostat.store import Project

from .test_modelling_ai_cap import MODELLING, _waiting
from .test_modelreview import judged, passed_redesign
from .test_self_improve import POOR
from .test_self_improve import project as poor_project

BUDGET = "budget: {daily: 1, max-cost: 0.5}\n"
STANDIN = """#!{py}
import json, os, sys
sys.stdin.read()
with open(os.environ["AI_STARTS"], "a") as f:
    f.write("started\\n")
mode = os.environ.get("AI_MODE", "0.1")
if mode == "fail":
    print("API Error: overloaded", file=sys.stderr)
    sys.exit(1)
if mode == "dearfail":
    print(json.dumps({{"result": "", "is_error": True, "total_cost_usd": 9.0, "usage": {{}}}}))
    sys.exit(1)
print(json.dumps({{"result": os.environ.get("AI_ANSWER", ""), "total_cost_usd": float(mode), "usage": {{}}}}))
"""


def standin(tmp_path, monkeypatch, mode: str = "0.1") -> Path:
    """The AI stood in for by a program that counts its starts."""
    f = tmp_path / "standin-ai"
    f.write_text(STANDIN.format(py=sys.executable))
    f.chmod(0o755)
    log = tmp_path / "ai-starts.log"
    monkeypatch.setenv("ERGOSTAT_AI", str(f))
    monkeypatch.setenv("AI_STARTS", str(log))
    monkeypatch.setenv("AI_MODE", mode)
    monkeypatch.delenv("ERGOSTAT_RUN", raising=False)
    monkeypatch.delenv("ERGOSTAT_BLOCK", raising=False)
    return log


def started(log: Path) -> int:
    return len(log.read_text().splitlines()) if log.exists() else 0


def budgeted(p, bud: str = BUDGET) -> Project:
    """The same project, with ``budget:`` declared."""
    path = Path(p.model.path)
    path.write_text(path.read_text() + bud)
    q = Project(mdl.load(path.parent))
    assert q.model.spec.budget is not None and Path(q.dir) == Path(p.dir)
    return q


def spend(p, usd: float) -> None:
    p.events.add("agent.ran", item="elsewhere", source="ergostat", data={"ai": {"cost_usd": usd}})


def reserving_run(p, monkeypatch, reserve: float = 0.0) -> str:
    """This process as a run of a block that reserved ``reserve`` (``$ERGOSTAT_RUN``)."""
    run = p.events.add("agent.started", item="modelling", source="ergostat",
                       data={"reserve": reserve, "pid": os.getpid()})["id"]
    monkeypatch.setenv("ERGOSTAT_RUN", run)
    return run


def block(monkeypatch, p) -> None:
    monkeypatch.setattr(ml, "project", lambda: p)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))


def test_redesigner_stops_when_day_budget_gone(tmp_path, monkeypatch, capsys):
    p = budgeted(judged(tmp_path))
    log = standin(tmp_path, monkeypatch)
    reserving_run(p, monkeypatch)
    spend(p, 1.0)                                          # the day's whole budget
    out = rdr.run(p, "model", ["asked"], budget=1.0, rounds=3)
    assert started(log) == 0 and out["cost"]["calls"] == 0     # no process started, no round after it
    assert out["result"] == "no budget" and out["why_not"].startswith("budget: ")
    assert out["rounds"] == [{"round": 1, "stopped": out["why_not"]}]
    assert "change_set" not in out and not pr.changes(p)       # nothing submitted
    r = p.events.query(n=None, type=budget.REFUSED)
    assert r and r[-1]["data"]["reserve"] > 0 and not p.events.query(n=None, type=budget.CALL)

    block(monkeypatch, p)                                   # the block's program: said, and its request left open
    rd.ask(p, None)
    assert ml.redesign(["--when", "ask"]) == 0
    err = capsys.readouterr().err
    assert started(log) == 0 and "no budget (budget: " in err and "nothing proposed" not in err
    req = rq.stored(p)[rq.rid("redesign", "redesign-due", "model")]
    assert req["state"] == "open" and "was refused: budget: " in req["why"]
    from ergostat.numbers import redesign_due as due
    assert due.resting(p, p.model.spec, "model", time.time()) is None   # no rest after a refusal
    assert not pr.changes(p)


def test_reviewer_and_ai_tier_refused(tmp_path, monkeypatch, capsys):
    p = budgeted(judged(tmp_path))
    pid = passed_redesign(p)
    log = standin(tmp_path, monkeypatch, mode="0.01")
    spend(p, 1.0)
    out = rv.run(p)
    assert started(log) == 0 and out["cost"]["calls"] == 0
    assert out["verdicts"] == [{"id": pid, "verdict": None, "why": out["verdicts"][0]["why"]}]
    assert out["verdicts"][0]["why"].startswith("budget: ") and rv.review_of(pr.stored(p)[pid]) is None
    assert not p.events.query(n=None, type=rv.RAN)          # no call charged to the reviewer's cap

    (tmp_path / "ai").mkdir()
    q = poor_project(tmp_path / "ai", POOR + MODELLING + BUDGET)
    block(monkeypatch, q)
    rq.sync(q)
    before = {r["id"]: r.get("tried") for r in _waiting(q)}
    spend(q, 1.0)
    assert ml.ai(["--model", "haiku", "--daily", "20"]) == 0
    err = capsys.readouterr().err
    assert started(log) == 0 and "no call for" in err and "budget: " in err
    assert {r["id"]: r.get("tried") for r in _waiting(q)} == before          # no try used, nothing read as an answer
    spent = Path(q.dir) / "modelling" / "ai-spend.jsonl"                     # its own cap not charged either
    assert not spent.exists() or not [x for x in spent.read_text().splitlines() if '"reserved"' in x]


def test_modeller_calls_counted_once_in_run(tmp_path, monkeypatch):
    p = budgeted(judged(tmp_path), "budget: {daily: 5, max-cost: 1}\n")
    spec = p.model.spec
    log = standin(tmp_path, monkeypatch, mode="0.1")
    run = reserving_run(p, monkeypatch, reserve=1.0)
    for _ in range(2):
        assert md.asked(p, "a prompt", "haiku")["usd"] == pytest.approx(0.1)
    calls = p.events.query(n=None, type=budget.CALL)
    assert started(log) == 2 and len(calls) == 2
    assert all(c["data"]["within"] == run and c["data"]["included"] is True for c in calls)
    assert all(c["data"]["reserve"] == md.unsaid("a prompt", "haiku")["usd"] for c in calls)   # its estimate
    p.events.add("agent.ran", item="modelling", source="ergostat", causedby=run, data={"ai": {"cost_usd": 0.2}})
    assert budget.fold(p, spec) == (pytest.approx(0.2), 0.0)           # not 0.4: its result lines are the run's

    q = budgeted(judged(tmp_path / "failed"), "budget: {daily: 5, max-cost: 1}\n")
    standin(tmp_path / "failed", monkeypatch, mode="fail")
    got = md.asked(q, "a prompt", "haiku")
    r = md.unsaid("a prompt", "haiku")["usd"]
    closed = q.events.query(n=None, type=budget.CLOSED)
    assert got["error"] and len(closed) == 1 and closed[0]["data"]["cost_usd"] is None
    assert budget.fold(q, q.model.spec) == (pytest.approx(r), 0.0)       # a failed call: charged its reserve

    monkeypatch.setenv("AI_MODE", "dearfail")                            # a failed call that says more than it
    got = md.asked(q, "a prompt", "haiku")
    assert got["error"] and got["usd"] == 9.0 > r
    assert q.events.query(n=None, type=budget.CLOSED)[-1]["data"]["cost_usd"] == 9.0
    assert budget.fold(q, q.model.spec)[0] == pytest.approx(r + 9.0)


def test_architecture_review_refused_before_its_day_is_stamped(tmp_path, monkeypatch):
    from ergostat.numbers import archreview as arv

    from .test_architecture_review import four, reviewed, said
    p = budgeted(four(tmp_path))
    standin(tmp_path, monkeypatch)
    spend(p, 1.0)
    call = said(("lab", "redesign", "x"))
    got = arv.run(p, "sonnet", 5.0, now=time.time(), call=call)
    assert got["result"] == "capped" and "budget: " in got["said"] and not call.calls
    assert [d["result"] for d in reviewed(p)] == ["capped"] and arv.due_now(p, time.time())   # its day not used
    assert rd.spent(p) == 0.0                                            # nor the redesigner's cap charged


# ---- the structural scan (SPEC §9.9): where an AI command is started

ROOT = Path(__file__).resolve().parent.parent / "ergostat"
ALLOWED = {
    "decisions/ai.py": "the calls' own path: each asks the day's budget",
    "numbers/modeller.py": "the modeller's calls: each asks the day's budget",
    "bench/": "developer benchmarks, run by hand, not by ergostat",
    "session.py": "a session inside a run: the run's permit covers it",
    "supervisor.py:chat": "the owner's own chat",
    "spec/engine.py": "an ai block's run started: the run's own permit",
    "repair/fix.py": "inside repair-fix's run: the run's permit covers it (and T1 its cap)",
}
SPAWNS = {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput", "system", "popen",
          "spawnv", "spawnvp", "spawnl", "spawnlp", "execv", "execvp", "execvpe", "execl", "execlp", "posix_spawn",
          "posix_spawnp", "create_subprocess_exec", "create_subprocess_shell"}
PROCS = {"subprocess", "os", "asyncio", "sp"}
BUILDERS = {"AI_COMMAND", "claude_command"}


def _names_ai(tree: ast.AST) -> bool:
    """The module names an AI command: ``ERGOSTAT_AI`` (or ``ERGOSTAT_CLAUDE``), ``claude`` as a command (not a
    comparison), or one of the builders of one (``AI_COMMAND``, ``claude_command``, ``decisions.ai.command``)."""
    compared = {id(c) for n in ast.walk(tree) if isinstance(n, ast.Compare) for c in [n.left, *n.comparators]}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in compared:
            v = n.value.strip()
            if v in ("ERGOSTAT_AI", "ERGOSTAT_CLAUDE") or v.split(" ")[0] == "claude" and len(v) < 40:
                return True
        if isinstance(n, ast.Name) and n.id in BUILDERS or isinstance(n, ast.Attribute) and (
                n.attr in BUILDERS or n.attr == "command" and isinstance(n.value, ast.Name) and n.value.id == "ai"):
            return True
        if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("decisions.ai") and \
                any(a.name == "command" for a in n.names):
            return True
    return False


def _spawning(tree: ast.AST) -> list[str]:
    """The functions (by name; ``<module>`` for top level) that start a process."""
    out = []

    def visit(n, where):
        for c in ast.iter_child_nodes(n):
            here = c.name if isinstance(c, ast.FunctionDef | ast.AsyncFunctionDef) else where
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in SPAWNS and \
                    isinstance(c.func.value, ast.Name) and c.func.value.id in PROCS:
                out.append(where)
            visit(c, here)
    visit(tree, "<module>")
    return out


def starts(rel: str, source: str) -> list[str]:
    """``rel:function`` for each place this module starts a process while it names an AI command."""
    tree = ast.parse(source)
    return sorted({f"{rel}:{f}" for f in _spawning(tree)}) if _names_ai(tree) else []


def allowed(site: str) -> bool:
    return any(site.startswith(a) if a.endswith("/") else site.split(":")[0] == a if ":" not in a else site == a
               for a in ALLOWED)


def test_only_listed_ai_starts():
    found = [s for f in sorted(ROOT.rglob("*.py")) for s in starts(f.relative_to(ROOT).as_posix(), f.read_text())]
    assert [s for s in found if not allowed(s)] == []
    assert {"decisions/ai.py:_once", "numbers/modeller.py:call", "supervisor.py:chat"} <= set(found)
    assert all(any(allowed(s) and s.startswith(a.split(":")[0]) for s in found) for a in ALLOWED)   # none stale
    planted = {                                             # a new spawn site fails the scan, however it is spelt
        "web/new.py": "import subprocess\ndef f(t):\n    subprocess.run(['claude', '-p'], input=t)\n",
        "web/env.py": "import os, subprocess as sp\ndef f():\n    sp.Popen([os.environ['ERGOSTAT_AI']])\n",
        "web/via.py": "import subprocess\nfrom ..decisions import ai\ndef f():\n    subprocess.run(ai.command('h', 1))\n",
        "web/shell.py": "import os\nos.system('claude -p hi')\n",
        "supervisor.py": "import subprocess\ndef other():\n    subprocess.call(['claude'])\n",
    }
    for rel, src in planted.items():
        got = starts(rel, src)
        assert got and not any(allowed(s) for s in got), (rel, got)
    assert starts("costs/x.py", "import subprocess\ndef f(c):\n    subprocess.run(c)\n    return c == 'claude'\n") == []
