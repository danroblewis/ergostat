"""A change to the projections reviewed as an observation (SPEC §12e, *Unexplained events*, *The reviewer*): the judge's
mechanical findings on the review it runs (a field no event fills fails it; the rest go with it as warnings), the
reviewer's projection checklist in place of the stocks-and-flows one, a revise returned to the drafter with its findings
and taken up as the next round, a request tried out held for the owner, and the commands that say why."""

from __future__ import annotations

import json
import textwrap
import time

from ergostat.numbers import drafter as dr
from ergostat.numbers import judge as jd
from ergostat.numbers import proposals as pr
from ergostat.numbers import requests as rq
from ergostat.numbers import reviewer as rv
from ergostat.numbers import unexplained as ux
from tests.test_unexplained_events import DEPLOY, MODEL, emit, project, stand_in

ZONE = DEPLOY.replace("  service: text\n", "  service: text\n  zone: text\n").replace(
    "    service: data.service\n", "    service: data.service\n    zone: data.requestParameters.zone\n")
FINAL = DEPLOY.replace("key: [service]\n", "key: [service]\nfinal: [done]\n")


def judged_draft(tmp_path, monkeypatch, body: str, more=None):
    p = project(tmp_path)
    emit(p)
    for e in more or []:
        p.events.add("deploy.finished", source="deployer", data=e, at=time.time() - 30)
    ux.sync(p)
    monkeypatch.setenv("ERGOSTAT_AI", stand_in(tmp_path, body))
    (pid,) = dr.run(p, daily=1.0)["proposed"]
    jd.run(p, "judge")
    return p, pr.stored(p)[pid]


def test_a_field_no_event_fills_fails_the_draft(tmp_path, monkeypatch):
    p, x = judged_draft(tmp_path, monkeypatch, ZONE)
    assert x["state"] == "failed", x["verdict"]
    assert "zone is null on every one of 3 objects" in x["verdict"]["why"]
    (f,) = [g for g in x["verdict"]["evidence"]["findings"] if g["check"] == "fills"]
    assert f["level"] == "fail" and f["projection"] == "deploy"


def test_the_judges_warnings_go_with_a_passed_draft(tmp_path, monkeypatch):
    failed = {"service": "s9", "errorCode": "AccessDenied"}             # a failed call that moves state
    p, x = judged_draft(tmp_path, monkeypatch, DEPLOY, [failed])
    assert x["state"] == "reviewing", x["verdict"]                         # passed by the judge: the reviewer's next
    checks = {g["check"]: g for g in x["verdict"]["evidence"]["findings"]}
    assert checks["exit"]["level"] == "warn" and "'done'" in checks["exit"]["says"] and "final:" in checks["exit"]["says"]
    assert checks["failed-calls"]["level"] == "warn" and "errorCode" in checks["failed-calls"]["says"]
    assert "for the reviewer" in x["verdict"]["why"]
    (tmp_path / "f").mkdir()
    _, y = judged_draft(tmp_path / "f", monkeypatch, FINAL)               # declared final: no exit finding
    assert y["state"] == "reviewing" and not [g for g in y["verdict"]["evidence"]["findings"] if g["check"] == "exit"]


def test_the_mechanical_findings_each_on_its_own(tmp_path):
    two = """\
query: type.startswith('vol.')
key: [id]
fields:
  id: text
  state: text
  size: number
events:
  made:
    when: type == 'vol.made'
    id: data.eventID
    state: data.result
    size: data.size
  sized:
    when: type == 'vol.sized'
    id: data.eventID
    size: data.size
"""
    p = project(tmp_path, MODEL.replace("projections:\n", "projections:\n  vol:\n" + textwrap.indent(two, "    "), 1))
    for i in range(3):
        p.events.add("vol.made", source="aws", data={"eventID": f"e{i}", "result": "ok", "size": 1})
        p.events.add("vol.sized", source="aws", data={"eventID": f"e{i}", "size": 2})
    got = ux.residual_counts(p, p.model.spec.items["vol"])
    checks = {g["check"] for g in got["findings"]}
    assert {"values", "time", "key"} <= checks, got["findings"]
    assert got["fields"]["size"]["have"] == 3


def test_the_reviewer_reads_a_projection_change_with_the_projection_checklist(tmp_path, monkeypatch):
    p, x = judged_draft(tmp_path, monkeypatch, DEPLOY)
    assert x["state"] == "reviewing" and rv.projections_only(p, p.model.spec, x) == ["deploy"]
    text = rv.prompt(p, p.model.spec, x)
    assert "This change is to the projections alone" in text and "Reviewing a change to the projections" in text
    assert "Failed calls don't move state" in text and '"objects": 3' in text
    assert "The causal story" not in text and "dashed lines" not in text and "behaviour it predicts" not in text
    assert "## The projection deploy as drafted" in text


def test_any_other_change_keeps_the_stocks_and_flows_checklist():
    assert "The causal story" in rv.guide(False) and "projections alone" not in rv.guide(False)
    assert "The causal story" in rv.checklists(False) and "Reviewing a change to the projections" not in rv.checklists(False)


def test_a_revise_returns_the_draft_to_the_drafter_with_its_findings(tmp_path, monkeypatch):
    p, x = judged_draft(tmp_path, monkeypatch, DEPLOY)
    said = "state 'done' has no exit and is not final:"

    def call(text, model, timeout=None):
        return {"result": json.dumps({"review": {"verdict": "revise", "findings": [{"check": "exit", "says": said}],
                                                 "summary": "declare it final"}}), "usd": 0.01}
    assert rv.run(p, call=call)["verdicts"][0]["verdict"] == "revise"
    assert pr.changes(p)[x["id"]][0] == "sent-back"
    ux.sync(p)
    (r,) = ux.open_requests(p)                                                  # open again, for the drafter
    assert r["state"] == "open" and int(r["tried"]["ai"]) == 1
    text = dr.prompt(p, p.model.spec, [r], tmp_path)
    assert "sent back" in text and said in text and "the reviewer said revise" in text and "key: [service]" in text
    out = dr.run(p, daily=1.0)                                                  # its next round
    (pid,) = out["proposed"]
    y = pr.stored(p)[pid]
    assert y["revising"] == x["id"] and y["review_round"] == 2 and y["review_asked"][0]["says"] == said


def test_a_request_tried_out_is_held_for_the_owner_and_the_run_says_why(tmp_path):
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    (r,) = ux.open_requests(p)
    rq.mark(p, r, "open", tried={"ai": dr.TRIES})
    out = dr.run(p, daily=1.0)
    assert not out["proposed"] and out["said"] == "drafter: nothing to draft: 1 group is held for the owner (tried 2 times)"
    x = rq.stored(p)[r["id"]]
    assert x["state"] == "held" and x["owner"] and "tried it 2 times" in x["why"]


def test_inbox_requests_lists_the_held_with_why(tmp_path, capsys):
    from ergostat.cli import main
    p = project(tmp_path)
    emit(p)
    ux.sync(p)
    (r,) = ux.open_requests(p)
    rq.mark(p, r, "held", "the drafter tried it 2 times", owner=True)
    capsys.readouterr()
    assert main(["-C", str(tmp_path), "inbox", "--requests", "--since", "1d"]) == 0
    out = capsys.readouterr().out
    assert f"{r['id']}  held  events: 3 events of deploy.finished from deployer" in out
    assert "why: the drafter tried it 2 times" in out and f"inbox request/{r['id']} --approve" in out
    assert "1 modelling requests waiting, 1 held" in out


def test_a_run_that_moved_nothing_says_why_from_its_log(tmp_path):
    from ergostat.cli.spec_cmds import said_lines
    (tmp_path / "logs" / "runs" / "drafter").mkdir(parents=True)
    (tmp_path / "logs" / "runs" / "drafter" / "1-abc.log").write_text(
        '{"type": "result"}\ndrafter: nothing to draft: 1 group is held for the owner (tried 2 times)\n')
    p = type("P", (), {"dir": tmp_path})()
    assert said_lines(p, "logs/runs/drafter/1-abc.log") == [
        "drafter: nothing to draft: 1 group is held for the owner (tried 2 times)"]
    assert said_lines(p, None) == []
