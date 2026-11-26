"""The agents group's kinds of panel (SPEC §4f): the Agents page's ladder, agents table and daemons, and each section of
an agent's own page, declared under ``dashboards:``, checked (a wrong parameter, or an agent the model does not have,
is an error at its line), and answered by /api/dashboard as their own endpoints answer."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.spec import read
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent

BOARD = """
dashboards:
  crew:
    title: The crew
    panels:
      - {panel: ladder, title: The ladder, size: full, fit: true}
      - {panel: agents, size: full}
      - {panel: daemons, size: m}
      - {panel: agent-what, agent: worker, size: m}
      - {panel: agent-definition, agent: worker}
      - {panel: agent-place, agent: worker, fit: true}
      - {panel: agent-runs, agent: worker}
      - {panel: agent-log, agent: drop}
"""


def write(tmp_path: Path, board: str = BOARD) -> Path:
    d = tmp_path / "first-loop"
    shutil.copytree(ROOT / "examples" / "first-loop", d, ignore=shutil.ignore_patterns("run", "__pycache__", "inbox"))
    f = d / "ergostat.yaml"
    f.write_text(f.read_text() + board)
    return d


def errors(tmp_path: Path, board: str):
    _, problems = read(write(tmp_path, board) / "ergostat.yaml")
    return [p for p in problems if p.level == "error"]


def test_each_agents_kind_declared_checks_and_keeps_its_agent(tmp_path, capsys):
    d = write(tmp_path)
    assert main(["-C", str(d), "check"]) == 0, capsys.readouterr().out
    spec, _ = read(d / "ergostat.yaml")
    got = [(p.panel, p.params) for p in spec.dashboards["crew"].panels]
    assert got == [("ladder", {"fit": True}), ("agents", {}), ("daemons", {}), ("agent-what", {"agent": "worker"}),
                   ("agent-definition", {"agent": "worker"}), ("agent-place", {"agent": "worker", "fit": True}),
                   ("agent-runs", {"agent": "worker"}), ("agent-log", {"agent": "drop"})]


@pytest.mark.parametrize("old, new, code, about", [
    ("{panel: agent-what, agent: worker, size: m}", "{panel: agent-what, agent: wroker, size: m}", "unknown-ref",
     "block.wroker"),
    ("{panel: agent-runs, agent: worker}", "{panel: agent-runs, agent: [worker]}", "bad-dashboard", ""),
    ("{panel: agent-log, agent: drop}", "{panel: agent-log, agent: 3}", "bad-dashboard", ""),
    ("{panel: agent-definition, agent: worker}", "{panel: agent-definition}", "bad-dashboard", ""),
    ("{panel: agents, size: full}", "{panel: agents, rung: 1}", "unknown-key", ""),
    ("{panel: daemons, size: m}", "{panel: daemons, agent: worker}", "unknown-key", ""),
    ("{panel: ladder, title: The ladder, size: full, fit: true}", "{panel: ladder, fit: tall}", "bad-dashboard", ""),
])
def test_a_wrong_parameter_or_an_agent_not_in_the_model_is_an_error_at_its_line(tmp_path, old, new, code, about):
    board = BOARD.replace(old, new)
    assert board != BOARD
    got = errors(tmp_path, board)
    text = (tmp_path / "first-loop" / "ergostat.yaml").read_text()
    line = next(i for i, x in enumerate(text.splitlines(), 1) if new.strip() in x)
    assert [(p.code, p.about, p.where.line if p.where else None) for p in got] == [(code, about, line)], got


def test_the_dashboard_answers_each_panel_as_its_own_endpoint_does(tmp_path, monkeypatch):
    from ergostat.web import server
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    p = Project(mdl.load(write(tmp_path)))
    now = time.time()
    p.events.add("agent.ran", item="worker", data={"seconds": 1, "note": "5 handled"}, at=now - 60)
    live = server.Live(p)
    at = str(now - 5)
    got = server.api(live, "dashboard/crew", {"at": [at]})
    assert all("answer" in x for x in got["panels"]), [x for x in got["panels"] if "answer" not in x]
    by = [(x["panel"]["panel"], x["answer"]) for x in got["panels"]]
    q = {"since": [str(got["window"])], "at": [at]}
    agents = server.api(live, "agents", q)
    assert set(agents) >= {"worker", "drop"}
    assert by[0] == ("ladder", agents) and by[1] == ("agents", agents)
    assert by[2] == ("daemons", server.api(live, "daemons", q))
    worker = server.api(live, "agents/worker", q)
    assert worker["runs"] == 1 and [e["data"]["note"] for e in worker["recent"]] == ["5 handled"]
    for kind, answer in by[3:7]:
        assert answer == worker, kind
    assert by[7] == ("agent-log", server.api(live, "agents/drop", q))
