"""The reviewer (SPEC §12e, *The reviewer*): an AI block that reads a change the judge passed as a senior modeller would,
and passes it, sends it back to its author, or rejects it; the feedback loop with the authors; the accept policy waiting
for its pass; its cap and its measures. Every call is a stand-in (no network)."""

from __future__ import annotations

import json
import textwrap
import time

import pytest

from ergostat.numbers import improve as im
from ergostat.numbers import judge as jd
from ergostat.numbers import meta
from ergostat.numbers import modeller as md
from ergostat.numbers import proposals as pr
from ergostat.numbers import redesign as rd
from ergostat.numbers import redesigner as rdr
from ergostat.numbers import reviewer as rv
from ergostat.spec import read
from tests.test_redesign import BUSY, BUSY_AUX, JUDGE, READ, project

DESCRIBE = {"kind": "description", "parts": ["stock.triage"], "title": "triage described",
            "edit": {"part": "stock.triage", "set": {"description": "alerts not yet triaged"}},
            "reasons": [{"says": "it had no description", "evidence": "finding:no-description@stock.triage"}]}


def judged(tmp_path, accept: str = "{redesign: auto, description: auto}", reviewed: str = "[description, redesign]"):
    judge = JUDGE.replace("ACCEPT", accept) + (f"    reviewed: {reviewed}\n" if reviewed else "") + IMPROVER
    return project(tmp_path / "m", BUSY.replace("AUXILIARIES", judge.lstrip("\n") + BUSY_AUX))


def answers(*verdicts, usd: float = 0.01):
    it = iter(verdicts)

    def call(text, model, timeout=None):
        call.prompts.append(text)
        v = next(it)
        return {"result": v if isinstance(v, str) else json.dumps({"review": v}), "usd": usd, "tokens_in": 100,
                "tokens_out": 20, "seconds": 0.1}
    call.prompts = []
    return call


IMPROVER = ("  improver:\n    type: ai\n    description: reviews the model\n    prompt: review the model\n"
            "    run: python3 -c pass\n    every: 1h\n")
PASS = {"verdict": "pass", "findings": [], "summary": "a description in the world's words, nothing else touched"}
REVISE = {"verdict": "revise", "findings": [{"check": "causal", "says": "busy reads investigate, but nothing says why"}]}
REJECT = {"verdict": "reject", "findings": [{"check": "noise", "says": "busy explains nothing the record shows"}]}


def passed_redesign(p, by: str = "redesigner") -> str:
    got = rd.submit(p, by, {"title": "busy read", "edits": READ})
    assert got["status"] == "proposed", got["why"]
    assert jd.run(p, "judge")["passed"] == 1
    return got["id"]


def test_the_reviewer_is_there_only_with_ai_and_tells_the_judge_what_it_reviews(tmp_path):
    def spec_of(with_: str):
        d = tmp_path / str(abs(hash(with_)))
        d.mkdir()
        (d / "ergostat.yaml").write_text(textwrap.dedent(f"""\
            name: t
            uses:
              modelling:
                use: modelling
                with: {with_}
            """))
        spec, problems = read(d / "ergostat.yaml")
        assert not [x for x in problems if x.level == "error"], [str(x) for x in problems]
        return spec
    on = spec_of("{ai: true}")
    assert on.blocks["reviewer"].type == "ai" and on.improve.reviewed == ["structure", "redesign"]
    assert "modelling review --model haiku" in on.blocks["reviewer"].params["run"]
    assert "--daily 2" in on.blocks["reviewer"].params["run"]          # the template's one daily cap
    assert "changes-sent-back" in on.flows
    assert spec_of("{ai: true, review: {kinds: [structure, equation, redesign], model: sonnet}}").improve.reviewed == \
        ["structure", "equation", "redesign"]
    for off in ("{}", "{ai: true, review: {when: off}}"):
        s = spec_of(off)
        assert "reviewer" not in s.blocks and s.improve.reviewed == [] and "changes-sent-back" not in s.flows


def test_a_pass_lets_the_judge_write_and_the_verdict_is_an_event_on_the_item(tmp_path):
    p = judged(tmp_path)
    pid = passed_redesign(p)
    assert pr.stored(p)[pid]["state"] == "passed"                       # promoted, but waiting for the reviewer
    out = rv.run(p, call=answers(PASS))
    assert out["verdicts"] == [{"id": pid, "verdict": "pass"}]
    ev = p.events.query(n=None, type="ergostat.model-change.reviewed")
    assert len(ev) == 1 and ev[0]["item"] == pr.item_of(pid) and ev[0]["source"] == "reviewer"
    assert ev[0]["data"]["review"]["summary"].startswith("a description")
    jd.run(p, "judge")
    assert pr.stored(p)[pid]["state"] == "accepted"
    assert rv.run(p, call=answers())["verdicts"] == []                  # read once


def test_a_reject_fails_the_change_with_its_reasons(tmp_path):
    p = judged(tmp_path)
    pid = passed_redesign(p)
    rv.run(p, call=answers(REJECT))
    x = pr.stored(p)[pid]
    assert x["state"] == "failed" and x["review"]["verdict"] == "reject"
    assert "busy explains nothing" in x["verdict"]["why"] and x["verdict"]["by"] == "reviewer"


def test_a_revise_goes_back_to_its_author_and_the_next_proposal_carries_the_findings(tmp_path):
    p = judged(tmp_path)
    got = im.submit(p, "modeller", DESCRIBE)
    assert got["status"] == "proposed", got["why"]
    jd.run(p, "judge")
    rv.run(p, call=answers(REVISE))
    assert pid_state(p, got["id"]) == "superseded"
    again = im.submit(p, "modeller", {**DESCRIBE, "title": "triage described again"})
    x = pr.stored(p)[again["id"]]
    assert x["revising"] == got["id"] and x["review_round"] == 2
    assert x["review_asked"][0]["says"].startswith("busy reads investigate")
    jd.run(p, "judge")
    call = answers(PASS)
    rv.run(p, call=call)
    assert "Round 2" in call.prompts[0] and "busy reads investigate" in call.prompts[0]
    # a redesign sent back is asked for again, and the redesigner's next one carries the findings
    q = judged(tmp_path / "r")
    first = passed_redesign(q)
    rv.run(q, call=answers(REVISE))
    assert rd.plan(q, "ask")["system"] == "model"
    from ergostat.numbers import changeset as cs
    assert "busy reads investigate" in rdr.prompt(q, cs.Scratch(q), "model", [])   # the findings in its next prompt
    second = passed_redesign(q)
    assert pr.stored(q)[second]["revising"] == first


def pid_state(p, pid: str) -> str:
    return pr.changes(p)[pid][0]


def test_two_revises_on_one_change_mean_reject(tmp_path):
    p = judged(tmp_path)
    first = im.submit(p, "modeller", DESCRIBE)["id"]
    jd.run(p, "judge")
    rv.run(p, call=answers(REVISE))
    second = im.submit(p, "modeller", {**DESCRIBE, "title": "again"})["id"]
    jd.run(p, "judge")
    out = rv.run(p, call=answers(REVISE))
    assert out["verdicts"] == [{"id": second, "verdict": "reject"}]
    x = pr.stored(p)[second]
    assert x["state"] == "failed" and "sent back once already" in x["verdict"]["why"]
    assert pid_state(p, first) == "superseded"
    other = {**DESCRIBE, "title": "a third time", "edit": {"part": "stock.triage", "set": {"description": "alerts waiting"}}}
    held = im.submit(p, "modeller", other)                                 # rejected: the memory holds it back
    assert held["status"] == "not-proposed" and "held back" in held["why"]


def test_a_change_no_author_can_revise_waits_for_the_owner_with_the_findings(tmp_path):
    p = judged(tmp_path)
    pid = passed_redesign(p, by="ergostat")
    rv.run(p, call=answers(REVISE))
    x = pr.stored(p)[pid]
    assert x["state"] == "passed" and x["review"]["verdict"] == "revise" and x["review"]["author"] is None
    jd.run(p, "judge")
    assert pr.stored(p)[pid]["state"] == "passed"                       # not written: the owner decides
    from ergostat.inbox import entries
    assert not [e for e in entries._changes(p, p.model.spec, time.time()) if e["id"] == f"change/{pid}"]


def test_the_authors_prompts_carry_the_reviewers_recent_verdicts(tmp_path, monkeypatch):
    p = judged(tmp_path)
    monkeypatch.setenv("ERGOSTAT_BLOCK", "modeller")
    im.submit(p, "modeller", DESCRIBE)
    jd.run(p, "judge")
    rv.run(p, call=answers(REJECT))
    text = md.prompt(p, p.model.spec, [])
    assert "The reviewer on your recent proposals" in text and "reject: triage described" in text
    assert "busy explains nothing" in text
    from ergostat.numbers import changeset as cs
    assert "The reviewer on your recent proposals" not in rdr.prompt(p, cs.Scratch(p), "model", [])   # not its own
    from ergostat.spec.engine import Engine
    eng = Engine(p, say=lambda s: None)
    assert "reviewer" not in eng.context(p.model.spec.blocks["improver"], "schedule")   # nothing said of its changes
    q = judged(tmp_path / "q")
    assert im.submit(q, "improver", DESCRIBE)["status"] == "proposed"
    jd.run(q, "judge")
    rv.run(q, call=answers(REVISE))
    said = Engine(q, say=lambda s: None).context(q.model.spec.blocks["improver"], "schedule")["reviewer"]
    assert said[0]["verdict"] == "revise" and said[0]["findings"] == ["busy reads investigate, but nothing says why"]


def test_with_the_reviewer_on_a_policy_auto_change_waits_for_its_pass(tmp_path):
    for reviewed, written in (("[description, redesign]", False), ("", True)):
        p = judged(tmp_path / (reviewed or "none").strip("[]").replace(", ", "-"), reviewed=reviewed)
        pid = im.submit(p, "modeller", DESCRIBE)["id"]
        jd.run(p, "judge")
        assert pr.stored(p)[pid]["state"] == ("accepted" if written else "passed")
        if not written:
            rv.run(p, call=answers(PASS))
            jd.run(p, "judge")
            assert pr.stored(p)[pid]["state"] == "accepted"


def test_a_change_for_the_owner_reaches_the_inbox_only_after_the_pass(tmp_path):
    from ergostat.inbox import entries
    p = judged(tmp_path, accept="owner")
    pid = passed_redesign(p)

    def offered():
        return [e for e in entries._changes(p, p.model.spec, time.time()) if e["id"] == f"change/{pid}"]
    assert not offered()
    rv.run(p, call=answers(PASS))
    assert offered()
    pr.accept(p, pid, {"at": time.time(), "window": 600.0})              # the owner may accept from the review queue
    q = judged(tmp_path / "q", accept="owner")
    qid = passed_redesign(q)
    pr.accept(q, qid, {"at": time.time(), "window": 600.0})              # ... even before the reviewer has read it
    assert pr.stored(q)[qid]["state"] == "accepted"


def test_the_reviewer_stops_at_the_daily_cap(tmp_path, monkeypatch, capsys):
    p = judged(tmp_path)
    a = passed_redesign(p)
    rd.charge(p, "model", {"usd": 1.995})
    assert rd.spent(p) == pytest.approx(1.995)
    out = rv.run(p, left=round(2.0 - rd.spent(p), 6), call=answers(REVISE, PASS, usd=0.01))
    assert [v["id"] for v in out["verdicts"]] == [a] and out["cost"]["usd"] == pytest.approx(0.01)
    assert rd.spent(p) == pytest.approx(2.005)                          # the reviewer's call counts on the shared cap
    from ergostat.library.run import modelling
    monkeypatch.setattr(modelling, "project", lambda: p)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("{}"))
    called = answers(PASS)
    monkeypatch.setattr(md, "call", called)
    assert modelling.review(["--daily", "2"]) == 0 and called.prompts == []
    assert "spent" in capsys.readouterr().err


def test_an_answer_without_specific_reasons_records_nothing(tmp_path):
    p = judged(tmp_path)
    pid = passed_redesign(p)
    out = rv.run(p, call=answers("I think it is fine", {"verdict": "reject", "findings": []}, {"verdict": "maybe"}))
    assert out["verdicts"] == [{"id": pid, "verdict": None, "why": "no verdict with its reasons"}]
    assert not p.events.query(n=None, type="ergostat.model-change.reviewed")
    assert rv.parse('{"review": {"verdict": "reject", "findings": []}}') is None
    assert rv.parse('{"review": {"verdict": "maybe"}}') is None
    assert rv.parse(json.dumps({"review": PASS}))["verdict"] == "pass"


def test_the_reviews_and_the_misses_are_measured(tmp_path):
    p = judged(tmp_path)
    pid = im.submit(p, "modeller", DESCRIBE)["id"]
    jd.run(p, "judge")
    rv.run(p, call=answers(REJECT))
    passed_redesign(p)
    rv.run(p, call=answers(PASS))
    passed = [x for x in pr.stored(p).values() if (x.get("review") or {}).get("verdict") == "pass"][0]
    pr.event(p, passed["id"], "regressed", {"why": "the forecast is better without it"})   # the prediction check's
    m = meta.all_of(p)
    assert m["ergostat.model.reviews-passed"] == 1 and m["ergostat.model.reviews-rejected"] == 1
    assert m["ergostat.model.reviews-revised"] == 0 and m["ergostat.model.review-misses"] == 1
    assert pr.stored(p)[pid]["state"] == "failed"
