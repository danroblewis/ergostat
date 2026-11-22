"""ergostat's own AI calls under the day's budget (SPEC §9.9): dev/records/ai-calls-ask-the-budget.md. Every call
through ``decisions/ai`` reserves first under P3's flock, is refused when the budget is gone, is closed with its
reported cost (unknown: its reserve), and is counted once inside a reserving run. Synthetic transcripts only."""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from ergostat import model as mdl
from ergostat.costs import budget
from ergostat.decisions import ai, extract
from ergostat.intent import judge, record
from ergostat.spec.engine import Engine
from ergostat.store import Project
from tests import test_decisions as td
from tests import test_intent as ti
from tests import test_run_budget as tr

PY = sys.executable
STANDIN = r'''
import json, os, sys, time
sys.stdin.read()
log = os.environ["AI_COUNT"]
n = sum(1 for _ in open(log)) if os.path.exists(log) else 0
with open(log, "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
modes = os.environ.get("AI_MODE", "0.1").split(",")
mode, answer = modes[min(n, len(modes) - 1)], os.environ.get("AI_ANSWER", "")
if mode == "sleep":
    time.sleep(30)
if mode == "plain":
    print(answer)
    sys.exit(0)
cost = {"nan": float("nan"), "bad": "x"}.get(mode)
print(json.dumps({"result": answer, "total_cost_usd": float(mode) if cost is None else cost, "usage": {}}))
'''
MET = json.dumps({"verdict": "met", "why": "done as meant", "evidence": []})


def standin(tmp_path, monkeypatch, mode: str = "0.1", answer: str = "") -> object:
    f = tmp_path / "standin_ai.py"
    f.write_text(STANDIN)
    monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {f}")
    monkeypatch.setenv("AI_COUNT", str(tmp_path / "ai-starts.log"))
    monkeypatch.setenv("AI_MODE", mode)
    monkeypatch.setenv("AI_ANSWER", answer)
    monkeypatch.delenv("ERGOSTAT_RUN", raising=False)
    return tmp_path / "ai-starts.log"


def starts(log) -> list[list[str]]:
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def evs(p, type: str) -> list[dict]:
    return p.events.query(n=None, type=type)


def decisions_project(tmp_path, bud: str = "budget: {daily: 1, max-cost: 0.5}\n") -> Project:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(td.MODEL) + bud)
    return Project(mdl.load(tmp_path))


def intent_project(tmp_path, bud: str = "budget: {daily: 1, max-cost: 0.5}\n", cap: float = 0.3) -> Project:
    tmp_path.mkdir(exist_ok=True)
    model = ti.MODEL.replace("    every: 1h\n", f"    every: 1h\n    model: haiku\n    max-cost: {cap}\n")
    return ti.project(tmp_path, model=model + bud)


def spend(p, cost: float) -> None:
    p.events.add("agent.ran", item="elsewhere", source="ergostat", data={"ai": {"cost_usd": cost}})


def transcript(tmp_path):
    f = tmp_path / "s.jsonl"
    td.synthetic(f)
    return f


def test_extract_refused_when_budget_gone(tmp_path, monkeypatch):
    p = decisions_project(tmp_path)
    log = standin(tmp_path, monkeypatch)
    spend(p, 1.0)                                         # the whole day's budget
    got = extract.run(p, [str(transcript(tmp_path))], model="haiku", out=open(os.devnull, "w"))
    assert starts(log) == []                              # no AI process started
    assert got["spent"]["stopped"].startswith("budget:") and got["spent"]["calls"] == 0
    r = evs(p, budget.REFUSED)
    assert len(r) == 1 and r[0]["item"] == "decisions-extract" and r[0]["data"]["reserve"] == 0.5
    assert not evs(p, budget.CALL)


def test_refused_verdict_stays_due(tmp_path, monkeypatch):
    p = intent_project(tmp_path)
    log = standin(tmp_path, monkeypatch, answer=MET)
    ti.submit(p, 1, ti.WEBP)
    spend(p, 1.0)
    said = []
    Engine(p, say=said.append).judge(p.model.spec.blocks["intent"])
    assert starts(log) == [] and record.stored(p) == {}   # no call, no verdict (not even 'asked')
    assert [it.id for _, it, _ in judge.due(p, p.model.spec, "intent")] == ["change/1"]
    assert evs(p, budget.REFUSED) and any("refused: budget:" in s for s in said)
    p = intent_project(tmp_path, bud="budget: {daily: 5, max-cost: 0.5}\n")   # room again
    Engine(p, say=lambda s: None).judge(p.model.spec.blocks["intent"])
    assert len(starts(log)) == 1 and [v["state"] for v in record.stored(p).values()] == ["met"]
    assert judge.due(p, p.model.spec, "intent") == []


@pytest.mark.parametrize("call_first", [True, False])
def test_call_lock_spans_write(tmp_path, monkeypatch, call_first):
    p = tr.project(tmp_path)                              # daily 1.5, max-cost 1: room for one
    e, spec, got = tr.engine(p), p.model.spec, {}

    def call():
        got["call"] = budget.ask(p, spec, "decisions-extract", 1.0)

    def run():
        e.run_block(spec.blocks["solo"], "test")
    tr.race(monkeypatch, *((call, run) if call_first else (run, call)))
    calls, runs = evs(p, budget.CALL), tr.reserving(p)
    assert len(calls) + len(runs) == 1 and len(evs(p, budget.REFUSED)) == 1
    assert (len(calls) == 1) == call_first and (got["call"][1] is None) == call_first
    budget.done(got["call"][0], 0.0)


@pytest.mark.parametrize("mode", ["bad", "sleep", "nan", "-1", "plain"])
def test_call_unknown_cost_charges_reserve(tmp_path, monkeypatch, mode):
    p = decisions_project(tmp_path, "budget: {daily: 10, max-cost: 1}\n")
    spec = p.model.spec
    standin(tmp_path, monkeypatch, mode=mode)
    permit, no = budget.ask(p, spec, "decisions-extract", 0.3)
    assert no is None and budget.fold(p, spec)[1] == pytest.approx(0.3)
    try:
        ai.call("prompt", "haiku", None, ai.Spent(), timeout=1, permit=permit)
    except ValueError:
        assert mode == "bad"                              # (the call raised: closed all the same)
    closed = evs(p, budget.CLOSED)
    assert len(closed) == 1 and closed[0]["data"]["run"] == permit["id"] and closed[0]["data"]["cost_usd"] is None
    assert budget.fold(p, spec) == (pytest.approx(0.3), 0.0)


def test_call_counted_once_in_run(tmp_path, monkeypatch):
    p = intent_project(tmp_path, bud="budget: {daily: 5, max-cost: 0.5}\n")
    spec = p.model.spec
    standin(tmp_path, monkeypatch, mode="0.1", answer=MET)
    ti.submit(p, 1, ti.WEBP)
    ti.submit(p, 2, ti.OPTIMIZE)
    Engine(p, say=lambda s: None).judge(spec.blocks["intent"])
    ran = evs(p, "agent.ran")[-1]
    assert ran["data"]["cost_usd"] == pytest.approx(0.2) and ran["data"]["judged"] == 2
    calls = evs(p, budget.CALL)
    assert len(calls) == 2 and {c["data"]["within"] for c in calls} == {ran["causedby"]}
    assert all(c["data"]["included"] for c in calls)
    assert budget.fold(p, spec) == (pytest.approx(0.2), 0.0)          # not 0.4: its end includes its calls

    q = intent_project(tmp_path / "raised", bud="budget: {daily: 5, max-cost: 0.5}\n")
    log = standin(tmp_path / "raised", monkeypatch, mode="0.1,bad", answer=MET)
    ti.submit(q, 1, ti.WEBP)
    ti.submit(q, 2, ti.OPTIMIZE)
    Engine(q, say=lambda s: None).judge(q.model.spec.blocks["intent"])
    assert len(starts(log)) == 2 and evs(q, "agent.failed")           # the second call raised: the pass failed
    assert budget.fold(q, q.model.spec) == (pytest.approx(0.1 + 0.3), 0.0)   # its call charged its reserve (0.3)

    r = decisions_project(tmp_path / "run", "budget: {daily: 5, max-cost: 1}\n")
    standin(tmp_path / "run", monkeypatch, mode="0.1")
    run = r.events.add("agent.started", item="solo", source="ergostat", data={"reserve": 1.0, "pid": os.getpid()})
    monkeypatch.setenv("ERGOSTAT_RUN", run["id"])          # a call made inside a reserving run's process
    permit, _ = budget.ask(r, r.model.spec, "decisions-extract", 0.2)
    ai.call("prompt", "haiku", None, ai.Spent(), permit=permit)
    c = evs(r, budget.CALL)[0]["data"]
    assert c["within"] == run["id"] and c["included"] is False
    r.events.add("agent.ran", item="solo", source="ergostat", causedby=run["id"], data={"ai": {"cost_usd": 0.3}})
    assert budget.fold(r, r.model.spec) == (pytest.approx(0.4), 0.0)  # its end (0.3) and the call it does not include


def test_uncapped_call_reserves_max_cost(tmp_path, monkeypatch):
    p = decisions_project(tmp_path, "budget: {daily: 5, max-cost: 0.5}\n")
    spec = p.model.spec
    log = standin(tmp_path, monkeypatch, mode="0.01")
    extract.run(p, [str(transcript(tmp_path))], model="haiku", out=open(os.devnull, "w"))
    assert [c["data"]["reserve"] for c in evs(p, budget.CALL)] == [0.5]
    assert starts(log)[0][-2:] == ["--max-budget-usd", "0.50"]
    extract.run(p, [str(transcript(tmp_path))], model="haiku", cap=1.0, out=open(os.devnull, "w"))
    assert evs(p, budget.CALL)[-1]["data"]["reserve"] == 1.0         # ai.extract's own per-call cap
    assert starts(log)[1][-2:] == ["--max-budget-usd", "1.00"]
    for bad in (5.01, float("nan"), float("inf"), 0, -1):
        permit, no = budget.ask(p, spec, f"call-{bad}", bad)
        assert permit is None and "not a number above 0 and within daily" in no
    assert len(evs(p, budget.CALL)) == 2 and len(evs(p, budget.REFUSED)) == 5


def test_architecture_review_refused_lists_not_reviewed(tmp_path, monkeypatch):
    from ergostat.numbers import vsm_review as vr
    from tests import test_vsm_review as tv
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "ai").write_text(tv.FAKE.format(d=fake))
    (fake / "ai").chmod(0o755)
    monkeypatch.setenv("ERGOSTAT_AI", str(fake / "ai"))
    tv._write(tmp_path / "m", tv.MODEL + "budget: {daily: 0.6, max-cost: 0.5}\n")
    p = Project(mdl.load(tmp_path / "m"))
    p.fake = fake
    tv._answer(p, cost=0.3)                               # two calls spend the day's 0.6
    got = vr.review_all(p, p.model.spec)
    assert len(got["reviews"]) == 2 and tv._calls(p) == 2 and got["not_reviewed"]
    assert all(x["why"].startswith("budget: ") for x in got["not_reviewed"])
    assert [c["data"]["reserve"] for c in evs(p, budget.CALL)] == [vr.PER_CALL] * 2
    assert "--max-budget-usd\n0.25" in (fake / "argv").read_text()
    assert budget.fold(p, p.model.spec) == (pytest.approx(0.6), 0.0)


def test_orphan_call_closed_by_recovery(tmp_path):
    p = decisions_project(tmp_path, "budget: {daily: 5, max-cost: 0.5}\n")
    gone = subprocess.Popen([PY, "-c", "pass"])
    gone.wait()
    c = p.events.add(budget.CALL, item="decisions-extract", source="ergostat",
                     data={"reserve": 0.3, "pid": gone.pid, "block": "decisions-extract", "within": None,
                           "included": False})
    assert budget.fold(p, p.model.spec) == (0.0, pytest.approx(0.3))
    assert budget.recover(p, p.model.spec, every=0) == [c["id"]]
    assert budget.fold(p, p.model.spec) == (pytest.approx(0.3), 0.0)


def test_no_budget_calls_unchanged(tmp_path, monkeypatch):
    p = decisions_project(tmp_path, "")
    log = standin(tmp_path, monkeypatch, mode="0.01")
    got = extract.run(p, [str(transcript(tmp_path))], model="haiku", out=open(os.devnull, "w"))
    assert got["spent"]["calls"] == 1 and "--max-budget-usd" not in starts(log)[0]   # as before: uncapped
    q = intent_project(tmp_path / "intent", bud="")
    standin(tmp_path / "intent", monkeypatch, answer=MET)
    ti.submit(q, 1, ti.WEBP)
    Engine(q, say=lambda s: None).judge(q.model.spec.blocks["intent"])
    assert [v["state"] for v in record.stored(q).values()] == ["met"]
    assert "reserve" not in evs(q, "agent.started")[-1]["data"]
    for x in (p, q):
        assert not evs(x, "budget.call") and not evs(x, "budget.closed") and not evs(x, "budget.refused")
