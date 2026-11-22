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
    for _ in range(md.FAILS - 1):                                # failed calls: no try, and no verdict
        out = rv.run(p, call=failed)
        assert out["verdicts"] == [{"id": pid, "verdict": None, "why": f"the call failed (exit 1): {OUTAGE}"}]
        assert out["cost"]["usd"] == pytest.approx(0.02)         # charged
    assert failed.n == md.FAILS - 1 and rv.tries(p, pr.stored(p)[pid]) == 0
    assert rv.tries(p, pr.stored(p)[pid], failed=True) == md.FAILS - 1
    assert rv.review_of(pr.stored(p)[pid]) is None
    assert rv.run(p, call=answers(PASS))["verdicts"] == [{"id": pid, "verdict": "pass"}]


def test_the_reviewer_gives_a_change_whose_calls_keep_failing_to_the_owner_and_reads_the_next(tmp_path):
    from ergostat.numbers import improve as im
    from ergostat.numbers import judge as jd
    from ergostat.numbers import proposals as pr
    from ergostat.numbers import reviewer as rv

    from .test_modelreview import DESCRIBE, PASS, judged, passed_redesign
    p = judged(tmp_path)
    bad = passed_redesign(p)                                     # the oldest: first in the queue
    good = im.submit(p, "modeller", DESCRIBE)["id"]
    jd.run(p, "judge")
    assert [x["id"] for x in rv.due(p, p.model.spec)] == [bad, good]
    calls = []

    def call(text, model, timeout=None):                        # fails every time on the redesign ('prompt too long')
        calls.append('"title": "busy read"' in text)
        if calls[-1]:
            return {"result": "", "usd": 0.02, "error": "the call failed (exit 1): Prompt is too long"}
        return {"result": json.dumps({"review": PASS}), "usd": 0.01}
    assert rv.run(p, call=call)["verdicts"][0]["id"] == bad and calls == [True]     # failed: the pass stops
    second = rv.run(p, call=call)["verdicts"]
    assert second[0] == {"id": good, "verdict": "pass"}          # the one behind it gets through, the failing one behind
    for _ in range(md.FAILS):
        rv.run(p, call=call)
    assert calls.count(True) == md.FAILS                         # bounded: no call on it after FAILS failed
    v = rv.review_of(pr.stored(p)[bad])
    assert v["verdict"] == rv.UNDECIDED and "Prompt is too long" in v["summary"] and f"{md.FAILS} failed" in v["summary"]
    assert rv.read_for_owner(p.model.spec, pr.stored(p)[bad])


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

    def runs(*results):                                          # each run: its start, then its end
        return [{"time": now - 100 + i, "data": {"system": "model", "result": r, "unit_sig": sig, "why_not": OUTAGE}}
                for i, r in enumerate(x for r in results for x in ("started", r))]
    assert due.resting(p, p.model.spec, "model", now, ran=runs(*["error"] * (md.FAILS - 1)), changes={}) is None
    assert OUTAGE in due.resting(p, p.model.spec, "model", now, ran=runs(*["error"] * md.FAILS), changes={})   # bounded
    assert due.resting(p, p.model.spec, "model", now, ran=runs("error", "proposed", *["error"] * (md.FAILS - 1)),
                       changes={}) is None                       # only so many in a row


def test_a_request_whose_calls_keep_failing_does_not_starve_the_others(tmp_path, monkeypatch, capsys):
    """One request that makes every call fail ('prompt too long') is called at most ``FAILS`` times, then held for the
    owner, and the requests behind it are given calls meanwhile."""
    from ergostat.library.run import modelling as ml
    p = _project(tmp_path, monkeypatch)
    order = ml._near(p, _waiting(p))
    assert len(order) >= 2
    bad, other = order[0]["id"], order[1]["id"]
    calls = []

    def call(text, model, timeout=600.0):
        calls.append(f'"id": "{bad}"' in text)
        if calls[-1]:
            return {"result": "", "usd": 0.01, "error": "the call failed (exit 1): Prompt is too long"}
        return {"result": "", "usd": 0.01, "tokens_in": 1, "tokens_out": 1}
    monkeypatch.setattr(md, "call", call)
    assert _run("--daily", "20") == 0 and calls == [True]      # the first call, all together: failed, no try
    assert rq.stored(p)[other]["failed"] == {"ai": 1} and not rq.stored(p)[other].get("tried")
    for _ in range(md.FAILS):
        assert _run("--daily", "20") == 0
    assert int((rq.stored(p)[other].get("tried") or {}).get("ai") or 0) >= 1      # the one behind it got its call
    while len(calls) < 80 and _waiting_ai(p, bad):
        _run("--daily", "20")
    assert calls.count(True) == md.FAILS                         # bounded: no call on it after FAILS failed
    x = rq.stored(p)[bad]
    assert x["state"] == "held" and x["failed"] == {"ai": md.FAILS} and "waits for the owner" in x["why"]
    assert "Prompt is too long" in x["error"] and not x.get("tried")
    n = len(calls)
    _run("--daily", "20")
    assert calls.count(True) == md.FAILS and len(calls) <= n + 1


def test_a_fresh_request_is_called_without_one_that_failed_before(tmp_path, monkeypatch):
    """While a request that failed before still waits, a fresh one arrives: its call is made without the failed one,
    so it neither fails with it nor takes a failed count that is not its own."""
    from ergostat.library.run import modelling as ml
    p = _project(tmp_path, monkeypatch)
    order = ml._near(p, _waiting(p))
    assert len(order) >= 2
    bad = order[-1]
    assert rq.mark(p, bad, bad["state"], failed={"ai": 1})       # it failed before; the others are fresh
    calls = []

    def call(text, model, timeout=600.0):
        calls.append(f'"id": "{bad["id"]}"' in text)
        if calls[-1]:
            return {"result": "", "usd": 0.01, "error": "the call failed (exit 1): Prompt is too long"}
        return {"result": "", "usd": 0.01, "tokens_in": 1, "tokens_out": 1}
    monkeypatch.setattr(md, "call", call)
    assert _run("--daily", "20") == 0
    assert calls and True not in calls                           # the fresh ones called, the failed one not with them
    for r in order[:-1]:
        x = rq.stored(p)[r["id"]]
        assert not x.get("failed") and not x.get("error") and (x.get("tried") or {}).get("ai") == 1
    assert rq.stored(p)[bad["id"]]["failed"] == {"ai": 1}


def test_a_request_held_after_its_failed_calls_and_approved_is_called_again(tmp_path, monkeypatch):
    """Held for the owner after ``FAILS`` failed calls, then approved: the next run calls it (its failed count and
    error cleared); a call that answers starts its failed calls in a row again; raised again, it has none."""
    from ergostat.library.run import modelling as ml
    p = _project(tmp_path, monkeypatch)
    bad = ml._near(p, _waiting(p))[0]
    for _ in range(md.FAILS):                                    # held as the tier holds it after FAILS failed calls
        bad = rq.stored(p)[bad["id"]]
        n = int((bad.get("failed") or {}).get("ai") or 0) + 1
        assert rq.mark(p, bad, "held" if n >= md.FAILS else bad["state"], "failed", error="Prompt is too long",
                       failed={"ai": n})
    assert rq.stored(p)[bad["id"]]["state"] == "held" and not _waiting_ai(p, bad["id"])
    assert rq.answer(p, p.model.spec, bad["id"], True) == "approved: open again, for the ai tier"
    x = rq.stored(p)[bad["id"]]
    assert x["state"] == "open" and x["failed"] == {"ai": 0} and x["error"] is None and _waiting_ai(p, bad["id"])
    for r in _waiting(p):                                        # the others out of the way: its call is its own
        if r["id"] != bad["id"]:
            assert rq.mark(p, r, "held", "out of the way", tried={"ai": 9})
    calls = []

    def call(text, model, timeout=600.0):
        calls.append(f'"id": "{bad["id"]}"' in text)
        return {"result": "", "usd": 0.01, "tokens_in": 1, "tokens_out": 1}
    monkeypatch.setattr(md, "call", call)
    assert _run("--daily", "20") == 0 and calls and calls[0]     # called again
    assert (rq.stored(p)[bad["id"]].get("tried") or {}).get("ai") == 1
    x = rq.stored(p)[bad["id"]]                                  # a call that answered: no failed calls in a row
    assert rq.mark(p, x, x["state"], failed={"ai": 2}, error="old")
    x = rq.stored(p)[bad["id"]]
    assert rq.mark(p, x, "reopened", tried={})
    assert _run("--daily", "20") == 0 and rq.stored(p)[bad["id"]]["failed"] == {"ai": 0}
    assert {"failed": {}, "error": None}.items() <= rq.fresh().items()   # raised again: a new finding


def _waiting_ai(p, rid):
    return any(r["id"] == rid and int((r.get("failed") or {}).get("ai") or 0) < md.FAILS for r in _waiting(p))
