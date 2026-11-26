"""The record group's kinds of panel (SPEC §4f): events (GET /api/events), goal-crossings and goal-decisions (GET
/api/loops/{goal}). Each is declared in YAML and checked, a wrong parameter is an error at its line, and the
dashboard's answer for each is what its own endpoint says of the same moment."""

import time

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.store import Project
from tests.test_dashboards import MODEL, errors, write

RECORD = MODEL.replace("dashboards:\n", """dashboards:
  record:
    title: The record
    panels:
      - {panel: events, match: "ticket.*", item: ticket/1, machine: fixer, runs: true, window: true, n: 40}
      - {panel: events, about: short-queue, from: 1700000000, to: 1700003600.5, fit: true, size: full}
      - {panel: goal-crossings, goal: short-queue}
      - {panel: goal-decisions, goal: short-queue, size: s}
""")


def test_each_kind_checks_and_keeps_its_parameters_as_written(tmp_path):
    from ergostat.spec import read
    spec, problems = read(write(tmp_path, RECORD) / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"], problems
    d = spec.dashboards["record"]
    assert [p.panel for p in d.panels] == ["events", "events", "goal-crossings", "goal-decisions"]
    assert d.panels[0].params == {"match": "ticket.*", "item": "ticket/1", "machine": "fixer", "runs": True, "window": True,
                                  "n": 40}
    assert d.panels[1].params == {"about": "short-queue", "from": 1700000000, "to": 1700003600.5, "fit": True}
    assert d.panels[2].params == {"goal": "short-queue"} and d.panels[3].size == "s"
    assert main(["-C", str(tmp_path), "check"]) == 0


EVENTS = '{panel: events, match: "ticket.*", item: ticket/1, machine: fixer, runs: true, window: true, n: 40}'
SPAN = "{panel: events, about: short-queue, from: 1700000000, to: 1700003600.5, fit: true, size: full}"


@pytest.mark.parametrize("old, new, code, about", [
    (EVENTS, "{panel: events, match: [ticket.*]}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, item: ''}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, machine: 3}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, runs: 1}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, window: yes please}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, n: 0}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, n: 501}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, n: many}", "bad-dashboard", ""),
    (EVENTS, "{panel: events, colour: red}", "unknown-key", ""),
    (SPAN, "{panel: events, from: yesterday}", "bad-dashboard", ""),
    (SPAN, "{panel: events, from: 1700003600, to: 1700000000}", "bad-dashboard", ""),
    (SPAN, "{panel: events, about: long-queue}", "unknown-ref", "goal.long-queue"),
    (SPAN, "{panel: events, remote: elsewhere}", "unknown-ref", "remote.elsewhere"),
    ("{panel: goal-crossings, goal: short-queue}", "{panel: goal-crossings, goal: nope}", "unknown-ref", "goal.nope"),
    ("{panel: goal-crossings, goal: short-queue}", "{panel: goal-crossings, title: Crossings}", "bad-dashboard", ""),
    ("{panel: goal-decisions, goal: short-queue, size: s}", "{panel: goal-decisions, goal: [short-queue]}", "bad-dashboard",
     ""),
    ("{panel: goal-decisions, goal: short-queue, size: s}", "{panel: goal-decisions, goal: short-queue, n: 3}",
     "unknown-key", ""),
])
def test_a_wrong_parameter_is_an_error_at_its_line(tmp_path, old, new, code, about):
    text = RECORD.replace(old, new)
    assert text != RECORD
    got = errors(tmp_path, text)
    line = next(i for i, x in enumerate(text.splitlines(), 1) if new.strip() in x)
    assert [(p.code, p.about, p.where.line if p.where else None) for p in got] == [(code, about, line)], got


def test_check_refuses_a_goal_the_model_does_not_have(tmp_path, capsys):
    write(tmp_path, RECORD.replace("{panel: goal-crossings, goal: short-queue}", "{panel: goal-crossings, goal: nope}"))
    assert main(["-C", str(tmp_path), "check"]) == 1
    assert "nope" in capsys.readouterr().out


@pytest.fixture
def live(tmp_path, monkeypatch):
    from ergostat.web import server
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    write(tmp_path, RECORD.replace("from: 1700000000, to: 1700003600.5", f"from: {int(time.time()) - 7200}"))
    p = Project(mdl.load(tmp_path))
    t = time.time() - 3000
    for i in range(4):
        p.events.add("ticket.opened", item=f"ticket/{i}", data={"title": f"t{i}"}, at=t + i)
    p.events.add("ticket.started", item="ticket/1", at=t + 600)
    p.events.add("controller.decided", item="short-queue", data={"decision": "open by 2"}, at=t + 700)
    p.events.add("loop.off", item="short-queue", data={"value": 7, "setpoint": "< 5", "error": 2}, at=t + 800)
    return server.Live(p)


def test_the_dashboard_answers_each_panel_as_its_own_endpoint_does(live):
    from ergostat.spec.dashboards import query
    from ergostat.web.dashboard_api import PATHS
    from ergostat.web.server import api
    at = time.time() - 5
    got = api(live, "dashboard/record", {"at": [str(at)]})
    assert all("answer" in x for x in got["panels"]), got["panels"]
    for x in got["panels"]:
        params = {k: v for k, v in x["panel"].items() if k not in ("panel", "title", "size", "note", "fit")}
        path = PATHS[x["panel"]["panel"]]
        if "{goal}" in path:
            path = path.replace("{goal}", params.pop("goal"))
        alone = api(live, path, {"since": [str(got["window"])], "at": [str(at)], **query(params)})
        assert x["answer"] == alone, x["panel"]
    first, second, crossings, decisions = (x["answer"] for x in got["panels"])
    assert first == []                                       # ticket/1's ticket.* events, from fixer: none here
    assert {e["item"] for e in second} == {"short-queue"}                          # the goal's own, from 2 h ago
    assert [e["type"] for e in crossings["crossings"]] == ["loop.off"]
    assert decisions["decisions"]["count"] == 1

