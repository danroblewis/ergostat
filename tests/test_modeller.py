"""ai-call-failures-are-failures' acceptance tests (docs/roadmap/overnight/ai-call-failures-are-failures.md): a call
that exits non-zero, says ``is_error``, or says no cost is an ``error`` saying what it said, charged its reservation;
the AI tier keeps the requests' tries and says the error on them; the reviewer and the redesigner say it too."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from ergostat.numbers import modeller as md
from ergostat.numbers import requests as rq

from .test_modelling_ai_cap import _project, _reservation, _rows, _run, _state, _waiting

OUTAGE = "API Error: 429 rate_limit_error: too many requests"


def _answering(monkeypatch, stdout: str = "", rc: int = 0, stderr: str = ""):
    """``claude -p`` stood in for at the process: every call answers ``stdout`` with exit ``rc``."""
    calls = []

    def run(cmd, input=None, **k):
        calls.append(input)
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=rc)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("ERGOSTAT_AI", "stand-in")
    return calls


def _check_kept_its_try(p, ids, before, calls, says=OUTAGE):
    after = _state(p, ids)
    for i in ids:
        state, tried, cost, why = after[i]
        assert tried == before[i][1], "an errored call used up a try"
        assert state == before[i][0]
        assert says in why and "proposed nothing" not in why
        assert cost and cost > 0
        assert rq.stored(p)[i]["error"] and says in rq.stored(p)[i]["error"]
    settle = [r for r in _rows(p) if "usd" in r]
    assert len(settle) == len(calls) and settle[0]["usd"] == pytest.approx(md.unsaid(calls[0], "haiku")["usd"])


def test_a_failed_call_is_an_error_and_keeps_its_try(tmp_path, monkeypatch, capsys):
    p = _project(tmp_path, monkeypatch)
    calls = _answering(monkeypatch, rc=1, stderr=OUTAGE)
    got = md.call("a prompt", "haiku")
    assert "exit 1" in got["error"] and OUTAGE in got["error"]
    assert got["usd"] == md.unsaid("a prompt", "haiku")["usd"] > 0 and got["estimated"] is True
    calls.clear()
    _, ids = _reservation(p)
    before = _state(p, ids)
    assert _run("--daily", "20") == 0
    assert len(calls) == 1                                       # not tried again in the run
    _check_kept_its_try(p, ids, before, calls)
    assert OUTAGE in capsys.readouterr().err
    assert _run("--daily", "20") == 0 and len(calls) == 2        # the request still waits for the ai tier
    assert {r["id"] for r in _waiting(p)} >= set(ids)


def test_an_is_error_response_is_an_error(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    out = json.dumps({"type": "result", "is_error": True, "result": OUTAGE, "total_cost_usd": 0})
    calls = _answering(monkeypatch, stdout=out, rc=0)
    got = md.call("a prompt", "haiku")
    assert "is_error" in got["error"] and OUTAGE in got["error"] and got["result"] == ""
    assert got["usd"] == md.unsaid("a prompt", "haiku")["usd"]              # its $0 is not believed
    said_more = json.dumps({"is_error": True, "result": OUTAGE, "total_cost_usd": 50.0})
    _answering(monkeypatch, stdout=said_more)
    assert md.call("a prompt", "haiku")["usd"] == 50.0                       # what it said, when more
    calls = _answering(monkeypatch, stdout=out, rc=0)
    _, ids = _reservation(p)
    before = _state(p, ids)
    assert _run("--daily", "20") == 0 and len(calls) == 1
    _check_kept_its_try(p, ids, before, calls)


@pytest.mark.parametrize("cost", ["missing", None, "0.5", float("nan"), float("inf"), -1.0, True])
def test_a_response_with_no_cost_is_charged_its_reservation(tmp_path, monkeypatch, cost):
    p = _project(tmp_path, monkeypatch)
    out = {"type": "result", "is_error": False, "result": "", "usage": {"input_tokens": 5, "output_tokens": 5}}
    if cost != "missing":
        out["total_cost_usd"] = cost
    calls = _answering(monkeypatch, stdout=json.dumps(out))
    got = md.call("a prompt", "haiku")
    assert "no cost said" in got["error"]
    assert got["usd"] == md.unsaid("a prompt", "haiku")["usd"] > 0
    calls.clear()
    _, ids = _reservation(p)
    before = _state(p, ids)
    assert _run("--daily", "20") == 0 and len(calls) == 1
    _check_kept_its_try(p, ids, before, calls, says="no cost said")


def test_a_said_cost_of_a_good_call_is_charged_as_said(tmp_path, monkeypatch):
    """The other side: a call that succeeds and says its cost is no error, charged what it said."""
    _answering(monkeypatch, stdout=json.dumps({"is_error": False, "result": "x", "total_cost_usd": 0.0012}))
    got = md.call("a prompt", "haiku")
    assert "error" not in got and got["usd"] == 0.0012 and got["result"] == "x"


def test_the_cap_holds_when_responses_omit_their_cost(tmp_path, monkeypatch):
    p = _project(tmp_path, monkeypatch)
    R, _ = _reservation(p)
    calls = _answering(monkeypatch, stdout=json.dumps({"is_error": False, "result": ""}))
    daily = f"{R * 1.5:.6f}"                                     # room for one call's reservation, not two
    for _ in range(3):
        assert _run("--daily", daily, "--tries", "3") == 0
    assert len(calls) == 1


def test_the_reviewer_says_a_failed_call_and_it_is_no_try(tmp_path):
    from ergostat.numbers import proposals as pr
    from ergostat.numbers import reviewer as rv

    from .test_modelreview import PASS, answers, judged, passed_redesign
    p = judged(tmp_path)
    pid = passed_redesign(p)

    def failed(text, model, timeout=None):
        failed.n += 1
        return {"result": "", "usd": 0.02, "error": f"the call failed (exit 1): {OUTAGE}"}
    failed.n = 0
    for _ in range(rv.TRIES + 1):                                # more failures than its tries: never given up
        out = rv.run(p, call=failed)
        assert out["verdicts"] == [{"id": pid, "verdict": None, "why": f"the call failed (exit 1): {OUTAGE}"}]
        assert out["cost"]["usd"] == pytest.approx(0.02)         # charged
    assert failed.n == rv.TRIES + 1 and rv.tries(p, pr.stored(p)[pid]) == 0
    assert rv.review_of(pr.stored(p)[pid]) is None
    assert rv.run(p, call=answers(PASS))["verdicts"] == [{"id": pid, "verdict": "pass"}]


def test_the_redesigner_says_a_failed_call_not_nothing_proposed(tmp_path):
    from ergostat.numbers import redesigner as rdr

    from .test_modelreview import judged
    p = judged(tmp_path)
    out = rdr.run(p, "model", budget=5.0, rounds=3,
                  call=lambda *a, **k: {"result": "", "usd": 0.02, "error": f"the call failed (is_error): {OUTAGE}"})
    assert out["result"] == "error" and OUTAGE in out["why_not"] and out["cost"]["calls"] == 1
    assert out["cost"]["usd"] == pytest.approx(0.02)
    import time

    from ergostat.numbers import redesign_due as due
    now, sig = time.time(), due.signature(p.model.spec, "model")
    for result, rests in (("error", False), ("nothing proposed", True)):      # a failed run takes no rest
        ran = [{"time": now - 10, "data": {"system": "model", "result": result, "unit_sig": sig}}]
        assert bool(due.resting(p, p.model.spec, "model", now, ran=ran, changes={})) is rests
