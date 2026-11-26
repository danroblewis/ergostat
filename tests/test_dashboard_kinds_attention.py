"""The attention group's kinds of panel (SPEC §4f): what asks for the owner, how to read a view, the loops a view
draws, the quiet systems, and one goal's runbook, parts and control loop. Each checks in YAML, a bad parameter is
refused at its line, and the dashboard's one answer gives each what its own endpoint says."""

from __future__ import annotations

import time

import pytest

from tests.test_dashboards import MODEL, errors, project

PANELS = """\
  watch:
    title: What asks for me
    panels:
      - {panel: attention, show: [waiting, off], size: m}
      - {panel: legend, view: blocks, size: s}
      - {panel: feedback-loops, system: desk}
      - {panel: control-loops}
      - {panel: quiet-systems, fit: true}
      - {panel: goal-runbook, goal: short-queue}
      - {panel: goal-parts, goal: short-queue}
      - {panel: goal-control, goal: short-queue, size: full}
"""
TEXT = MODEL + PANELS


def test_each_kind_checks_and_keeps_its_parameters_as_written(tmp_path):
    from ergostat.spec import read
    from tests.test_dashboards import write
    spec, problems = read(write(tmp_path, TEXT) / "ergostat.yaml")
    assert not [p for p in problems if p.level == "error"], problems
    d = spec.dashboards["watch"]
    assert [(p.panel, p.params) for p in d.panels] == [
        ("attention", {"show": ["waiting", "off"]}), ("legend", {"view": "blocks"}),
        ("feedback-loops", {"system": "desk"}), ("control-loops", {}), ("quiet-systems", {"fit": True}),
        ("goal-runbook", {"goal": "short-queue"}), ("goal-parts", {"goal": "short-queue"}),
        ("goal-control", {"goal": "short-queue"})]


@pytest.mark.parametrize("old, new, code, about", [
    ("{panel: legend, view: blocks, size: s}", "{panel: legend, view: wiring}", "bad-dashboard", ""),
    ("{panel: legend, view: blocks, size: s}", "{panel: legend, view: [blocks]}", "bad-dashboard", ""),
    ("{panel: legend, view: blocks, size: s}", "{panel: legend, size: s}", "bad-dashboard", ""),
    ("{panel: attention, show: [waiting, off], size: m}", "{panel: attention, show: [waiting, inbox]}", "bad-dashboard", ""),
    ("{panel: attention, show: [waiting, off], size: m}", "{panel: attention, show: 3}", "bad-dashboard", ""),
    ("{panel: attention, show: [waiting, off], size: m}", "{panel: attention, goal: short-queue}", "unknown-key", ""),
    ("{panel: feedback-loops, system: desk}", "{panel: feedback-loops, system: floor}", "unknown-ref", "system.floor"),
    ("{panel: feedback-loops, system: desk}", "{panel: feedback-loops, system: 4}", "bad-dashboard", ""),
    ("{panel: control-loops}", "{panel: control-loops, system: floor}", "unknown-ref", "system.floor"),
    ("{panel: quiet-systems, fit: true}", "{panel: quiet-systems, system: desk}", "unknown-key", ""),
    ("{panel: goal-runbook, goal: short-queue}", "{panel: goal-runbook, goal: nope}", "unknown-ref", "goal.nope"),
    ("{panel: goal-parts, goal: short-queue}", "{panel: goal-parts}", "bad-dashboard", ""),
    ("{panel: goal-parts, goal: short-queue}", "{panel: goal-parts, goal: [short-queue]}", "bad-dashboard", ""),
    ("{panel: goal-control, goal: short-queue, size: full}", "{panel: goal-control, goal: nope}", "unknown-ref",
     "goal.nope"),
])
def test_a_bad_parameter_is_refused_at_its_line(tmp_path, old, new, code, about):
    text = TEXT.replace(old, new)
    assert text != TEXT
    got = errors(tmp_path, text)
    line = next(i for i, x in enumerate(text.splitlines(), 1) if new.strip() in x)
    assert [(p.code, p.about, p.where.line if p.where else None) for p in got] == [(code, about, line)], got


def test_the_dashboard_answers_each_kind_as_its_own_endpoint_does(tmp_path, monkeypatch):
    from ergostat.web import server
    from ergostat.web.server import api
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    live = server.Live(project(tmp_path, TEXT))
    at = time.time() - 5
    got = api(live, "dashboard/watch", {"at": [str(at)]})
    assert [x["panel"]["panel"] for x in got["panels"]] == ["attention", "legend", "feedback-loops", "control-loops",
                                                             "quiet-systems", "goal-runbook", "goal-parts",
                                                             "goal-control"]
    assert all("answer" in x for x in got["panels"]), [x for x in got["panels"] if "answer" not in x]
    by = {x["panel"]["panel"]: x["answer"] for x in got["panels"]}
    q = {"since": [str(got["window"])], "at": [str(at)]}
    assert by["legend"] == {"view": "blocks"}                              # drawn by the page from its parameter
    assert isinstance(by["attention"]["attention"], list) and "goals_off" in by["attention"]
    assert by["feedback-loops"]["kind"] == "dynamics" and "causalLoops" in by["feedback-loops"]
    alone = api(live, "graph", {**q, "view": ["dynamics"], "system": ["desk"]})
    assert (by["feedback-loops"]["causalLoops"], by["feedback-loops"]["nodes"]) == (alone["causalLoops"], alone["nodes"])
    assert by["control-loops"]["kind"] == "blocks" and "short-queue" in by["control-loops"]["loops"]
    assert [s["name"] for s in by["quiet-systems"]] == [s["name"] for s in api(live, "systems", q)]
    assert by["goal-runbook"]["stock"] == "queue" and by["goal-runbook"] == by["goal-parts"]
    assert [p["kind"] for p in by["goal-parts"]["parts"]] == ["sensor", "controller"]
    assert by["goal-control"] == api(live, "loop-control", {**q, "goal": ["short-queue"]})
