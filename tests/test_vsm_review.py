"""The AI rung of the architecture review (docs/roadmap/overnight/architecture-vsm-and-purpose.md): the computed VSM
checklist, the reviewer's checked answer, the requests it holds for the owner, its bounds, its record and explain.
A fake ``$ERGOSTAT_AI`` (a shell script) prints a canned answer, writes its argv and stdin, and counts its calls."""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.cli import main
from ergostat.numbers import requests as rq
from ergostat.numbers import vsm_review as vr
from ergostat.spec import vsm
from ergostat.spec.explain import explain
from ergostat.store import Project

DESC = "keeps the job queue short so customers don't wait"
MODEL = f"""
name: plant
purpose: keep the plant's work moving
items:
  job:
    id: job/*
    states: [new, done]
    on:
      job.end: done
systems:
  ops: {{description: "{DESC}"}}
  inner: {{description: the inner loop, within: ops}}
  other: {{description: another system}}
  bare: {{}}
stocks:
  queue: {{unit: jobs, system: ops, sensor: {{manual: true}}}}
  depth: {{unit: jobs, system: inner, sensor: {{manual: true}}}}
  backlog: {{unit: jobs, system: other, sensor: {{manual: true}}}}
flows:
  done: {{from: queue, system: ops}}
  drain: {{from: depth, system: inner}}
  away: {{from: backlog, system: other}}
goals:
  short: {{stock: queue, hold: '<= 5', system: ops, description: few jobs wait}}
  shallow: {{stock: depth, hold: '<= 3', system: inner}}
  low: {{stock: backlog, hold: '<= 9', system: other}}
blocks:
  checker: {{type: judge, system: ops}}
  setter: {{type: expr, in: {{d: stock.depth}}, expr: 5 - d, out: goal.shallow, system: ops}}
  work: {{type: program, run: "true", takes: {{kind: job, at: new}}, system: ops}}
  elsewhere: {{type: program, run: "true", takes: {{kind: job, at: new}}, system: other}}
"""
FAKE = """#!/bin/sh
D={d}
echo x >> "$D/calls"
printf '%s\\n' "$@" > "$D/argv"
cat > "$D/stdin"
if [ -f "$D/hang" ]; then
  echo $$ > "$D/pid"
  sleep 60 &
  echo $! > "$D/child"
  wait
fi
cat "$D/answer"
exit $(cat "$D/rc" 2>/dev/null || echo 0)
"""
GOOD = {"S1": ["goal.short"], "S2": ["block.work"], "S3": ["goal.shallow"], "S3*": ["block.checker"],
        "S4": ["stock.queue"], "S5": ["description"]}


def _write(d: Path, text: str = MODEL) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "ergostat.yaml").write_text(textwrap.dedent(text))


@pytest.fixture
def proj(tmp_path, monkeypatch):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "ai").write_text(FAKE.format(d=fake))
    (fake / "ai").chmod(0o755)
    monkeypatch.setenv("ERGOSTAT_AI", str(fake / "ai"))
    _write(tmp_path / "m")
    p = Project(mdl.load(tmp_path / "m"))
    p.fake = fake
    return p


def _answer(p, missing=(), present=None, goals=(), uncovered=None, cost=0.0123, envelope=True, raw=None, **more):
    """The fake's next answer: every function present (citing GOOD) but ``missing``; ``present`` overrides parts."""
    fns = [{"s": s, "present": s not in missing, "parts": (present or {}).get(s, GOOD[s]) if s not in missing else [],
            "why": f"why {s}"} for s in GOOD if s not in more.get("omit", ())]
    pu = {"goals": list(goals)} | ({"uncovered": uncovered} if uncovered is not None else {})
    line = raw if raw is not None else json.dumps({"functions": fns, "purpose": pu})
    out = json.dumps({"result": line, "total_cost_usd": cost, "usage": {"input_tokens": 100, "output_tokens": 20},
                      **({"is_error": True} if more.get("is_error") else {})}) if envelope else line
    (p.fake / "answer").write_text(out)


def _req(p, code, about="system.ops"):
    return rq.stored(p).get(rq.rid("architecture", code, about))


def _calls(p) -> int:
    f = p.fake / "calls"
    return len(f.read_text().splitlines()) if f.exists() else 0


def _events(p, t=vr.REVIEWED):
    return p.events.query(n=None, type=t)


def test_the_computed_checklist_names_each_function_s_candidates(proj, tmp_path):
    spec = proj.model.spec
    cl = vsm.checklist(spec, "ops")
    parts = {f: [x["part"] for x in xs] for f, xs in cl.items()}
    assert parts["S1"] == ["goal.short", "system.inner"]
    assert parts["S2"] == ["block.work"] and "elsewhere" in cl["S2"][0]["why"]
    assert parts["S3"] == ["goal.shallow"]
    assert parts["S3*"] == ["block.checker"]
    assert parts["S4"] == []
    assert parts["S5"] == ["description", "purpose", "system.inner"]
    assert all(x["why"] for xs in cl.values() for x in xs)
    _write(tmp_path / "np", MODEL.replace("purpose: keep the plant's work moving\n", ""))
    bare = vsm.checklist(mdl.load(tmp_path / "np").spec, "bare")
    assert bare == {"S1": [], "S2": [], "S3": [], "S3*": [], "S4": [], "S5": []}
    more = MODEL.replace("flows:\n", "flows:\n  arrive: {to: queue, system: ops, sensor: {manual: true}}\n"
                         "  landed: {to: queue, system: ops}\n")          # measured from a cloud; unmeasured
    more = more.replace("goals:\n", "goals:\n  cap: {stock: queue, hold: '<= 8', system: ops}\n")
    more = more.replace("blocks:\n", "blocks:\n  boss: {type: expr, in: {q: stock.queue}, expr: 3, out: goal.cap, "
                        "system: ops}\n")                                # short's controller sets cap's setpoint
    _write(tmp_path / "more", more)
    cl = vsm.checklist(mdl.load(tmp_path / "more").spec, "ops")
    assert [x["part"] for x in cl["S4"]] == ["flow.arrive"]
    s3 = {x["part"]: x["why"] for x in cl["S3"]}
    assert set(s3) == {"goal.cap", "goal.shallow"} and "commanded by boss" in s3["goal.cap"]


def test_a_review_raises_a_held_request_for_each_missing_function_and_records_its_cost(proj):
    _answer(proj, missing=("S4",))
    spec = proj.model.spec
    r = vr.review(proj, spec, "ops")
    assert r["reviewed"] and r["applied"] and r["missing"] == ["S4"] and r["raised"] == 1
    x = _req(proj, "vsm-s4")
    assert x["state"] == "held" and x["owner"] is True and x["tier"] == "owner" and x["source"] == "architecture"
    assert _req(proj, "vsm-s1") is None and not rq.approvable(spec, x)     # no tier takes a judgement up
    (e,) = _events(proj)
    d = e["data"]
    assert d["model"] == "haiku" and d["cost_usd"] == 0.0123 and d["cost"] == "reported" and d["tokens"] == 120
    assert d["signature"] == vr.signature(spec, "ops") and d["words"] == vr.words(spec, "ops") and d["applied"] is True
    argv = (proj.fake / "argv").read_text().split("\n")
    assert argv[argv.index("--model") + 1] == "haiku" and argv[argv.index("--max-budget-usd") + 1] == "0.25"
    assert "## The computed checklist" in (proj.fake / "stdin").read_text()


def test_a_function_said_present_must_name_a_part_of_the_system(proj):
    spec = proj.model.spec
    _answer(proj, missing=("S1",))
    vr.review(proj, spec, "ops")
    assert _req(proj, "vsm-s1")["state"] == "held"
    _answer(proj, present={"S1": ["stock.nope"], "S3": ["goal.low"]})        # one not a part; one another system's
    r = vr.review(proj, spec, "ops")
    assert r["unsupported"] == ["S1", "S3"] and r["dropped"] == 2 and "S1" not in r["present"] + r["missing"]
    d = _events(proj)[-1]["data"]
    assert "S1" not in d["functions"] and "S3" not in d["functions"] and d["dropped"] == 2
    assert _req(proj, "vsm-s1")["state"] == "held"                 # an unsupported present answers nothing
    assert _req(proj, "vsm-s3") is None                            # and raises nothing


def test_purpose_quotes_must_be_the_owner_s_words(proj):
    spec = proj.model.spec
    _answer(proj, goals=[{"goal": "goal.low", "serves": False}, {"goal": "goal.short", "serves": True, "quote": "made up"},
                         {"goal": "shallow", "serves": False, "quote": ""}],
            uncovered=[{"quote": "happy owners forever", "why": "x"}, {"quote": "customers   don’t wait", "why": "y"},
                       {"quote": "short", "why": "one word"}])
    r = vr.review(proj, spec, "ops")
    assert r["dropped"] == 5                          # (shallow is inner's goal: inner's review judges it)
    x = _req(proj, "purpose-uncovered")
    assert x["state"] == "held" and "\"customers don't wait\"" in x["says"] and "happy" not in x["says"]
    assert _req(proj, "goal-off-purpose", "goal.low") is None
    assert _req(proj, "goal-off-purpose", "goal.short") is None
    assert _req(proj, "goal-off-purpose", "goal.shallow") is None


def test_a_system_and_its_subsystem_do_not_answer_each_other_s_goal_requests(proj):
    spec = proj.model.spec
    assert vr._goals(spec, "ops") == ["short"] and vr._goals(spec, "inner") == ["shallow"]
    _answer(proj, goals=[{"goal": "shallow", "serves": False}])
    vr.review(proj, spec, "inner")
    assert _req(proj, "goal-off-purpose", "goal.shallow")["state"] == "held"
    _answer(proj, goals=[{"goal": "shallow", "serves": True, "quote": DESC}])
    r = vr.review(proj, spec, "ops")                  # ops's review cannot answer inner's goal
    assert r["dropped"] == 1 and _req(proj, "goal-off-purpose", "goal.shallow")["state"] == "held"
    _answer(proj, goals=[{"goal": "shallow", "serves": True, "quote": "the inner loop"}])
    vr.review(proj, spec, "inner")
    assert _req(proj, "goal-off-purpose", "goal.shallow")["state"] == "answered"
    _answer(proj, goals=[{"goal": "shallow", "serves": False}])
    vr.review(proj, spec, "ops")                      # nor reopen it
    assert _req(proj, "goal-off-purpose", "goal.shallow")["state"] == "answered"
    sp2 = proj.model.spec
    before = vr.words(sp2, "ops"), vr.words(sp2, "inner")
    sp2.goals["shallow"].description = "changed"      # a subsystem's goal's words are not the system's
    assert vr.words(sp2, "ops") == before[0] and vr.words(sp2, "inner") != before[1]


def test_a_failed_answer_reviews_nothing_and_answers_nothing(proj, monkeypatch):
    spec = proj.model.spec
    _answer(proj, missing=("S4",))
    vr.review(proj, spec, "ops")
    for how in ("garbage", "is_error", "exit"):
        if how == "garbage":
            _answer(proj, raw="I think it is fine.", envelope=False)
        elif how == "is_error":
            _answer(proj, is_error=True, cost=0.01)
        else:
            _answer(proj, envelope=False)              # all present, but the call exits 3: nothing it said counts
            (proj.fake / "rc").write_text("3")
        r = vr.review(proj, spec, "ops")
        assert not r["reviewed"], how
        assert _req(proj, "vsm-s4")["state"] == "held", how
    bad = _events(proj, vr.UNREVIEWED)
    assert [e["data"]["cost_usd"] for e in bad] == [0.25, 0.01, 0.25]
    assert [e["data"]["cost"] for e in bad] == ["charged", "reported", "charged"]
    assert "no readable answer" in bad[0]["data"]["why"] and "is_error" in bad[1]["data"]["why"]
    assert "exit 3" in bad[2]["data"]["why"] and len(_events(proj)) == 1
    (proj.fake / "rc").write_text("0")
    _answer(proj, raw=json.dumps({"functions": [{"s": ["S4"], "present": True, "parts": ["stock.queue"]},
                                                {"s": {}, "present": True}]}))
    r = vr.review(proj, spec, "ops")                  # an unhashable `s` is dropped, never a traceback
    assert r["reviewed"] and r["dropped"] == 2 and r["present"] == [] and _req(proj, "vsm-s4")["state"] == "held"
    monkeypatch.setattr(vr, "checked", lambda *a: 1 / 0)
    _answer(proj, cost=0.02)
    r = vr.review(proj, spec, "ops")                  # an answer that cannot be checked is unreviewed at its cost
    assert not r["reviewed"] and "ZeroDivisionError" in r["why"] and r["cost_usd"] == 0.02
    assert _events(proj, vr.UNREVIEWED)[-1]["data"]["cost_usd"] == 0.02 and _req(proj, "vsm-s4")["state"] == "held"


def test_only_kept_evidence_answers_a_request(proj, tmp_path):
    spec = proj.model.spec
    _answer(proj, missing=("S1", "S4"), goals=[{"goal": "short", "serves": False}],
            uncovered=[{"quote": "customers don't wait", "why": "no goal on waiting"}])
    vr.review(proj, spec, "ops")
    keys = [("vsm-s1", "system.ops"), ("vsm-s4", "system.ops"), ("purpose-uncovered", "system.ops"),
            ("goal-off-purpose", "goal.short")]
    assert all(_req(proj, *k)["state"] == "held" for k in keys)
    _answer(proj, present={"S1": ["stock.nope"]}, omit=("S4",), goals=[{"goal": "short", "serves": True, "quote": "nope"}])
    r = vr.review(proj, spec, "ops")                 # S1 unsupported, S4 omitted, no uncovered list, a goal dropped
    assert r["answered"] == 0 and all(_req(proj, *k)["state"] == "held" for k in keys)
    _write(tmp_path / "m", MODEL.replace(f'ops: {{description: "{DESC}"}}', "ops: {}"))
    p2 = Project(mdl.load(tmp_path / "m"))
    _answer(proj, uncovered=[])                       # no description now: purpose not reviewed
    r = vr.review(p2, p2.model.spec, "ops")
    assert _req(proj, "purpose-uncovered")["state"] == "held" and _req(proj, "goal-off-purpose", "goal.short")["state"] == "held"
    assert _req(proj, "vsm-s1")["state"] == _req(proj, "vsm-s4")["state"] == "answered" and r["answered"] == 2


def test_the_cost_cap_is_checked_before_each_call_and_bounds_hold(proj, capsys, monkeypatch):
    d = str(proj.model.path.parent)
    _answer(proj, envelope=False)                    # no cost reported: each counts as the whole cap
    assert main(["-C", d, "improve", "--architecture", "--max-cost", "0.6", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert _calls(proj) == 2 and [r["system"] for r in got["reviews"]] == ["bare", "inner"]
    assert [x["system"] for x in got["not_reviewed"]] == ["ops", "other"] and got["spent"] == 0.5
    assert all(r["cost"] == "charged" and r["cost_usd"] == 0.25 for r in got["reviews"])
    with pytest.raises(SystemExit) as e:
        main(["-C", d, "improve", "--architecture", "--max-cost", "50"])
    assert e.value.code == 2 and _calls(proj) == 2
    with pytest.raises(ValueError):
        vr.review_all(proj, proj.model.spec, max_cost=50)
    monkeypatch.setattr(vr, "MOST_SYSTEMS", 2)
    got = vr.review_all(proj, proj.model.spec, max_cost=5)
    assert len(got["reviews"]) == 2 and _calls(proj) == 4
    assert [x["why"] for x in got["not_reviewed"]] == ["more than 2 systems in one run"] * 2


def test_a_later_review_answers_what_it_no_longer_says_and_a_remade_request_starts_fresh(proj):
    spec = proj.model.spec
    _answer(proj, missing=("S4",))
    vr.review(proj, spec, "ops")
    k = rq.rid("architecture", "vsm-s4", "system.ops")
    rq.event(proj, k, "held", {"change": "abc123", "tried": {"ai": 2}})
    _answer(proj)
    assert vr.review(proj, spec, "ops")["answered"] == 1
    x = _req(proj, "vsm-s4")
    assert x["state"] == "answered" and "no longer says it" in x["why"]
    _answer(proj, missing=("S4",))
    r = vr.review(proj, spec, "ops")
    x = _req(proj, "vsm-s4")
    assert x["state"] == "held" and x["review"] == r["seq"] and x["change"] is None and x["tried"] == {}
    assert "no longer says" not in x["why"] and x["owner"] is True and "why S4" in x["says"]


def test_a_review_recorded_while_this_one_ran_wins(proj, monkeypatch):
    spec = proj.model.spec
    _answer(proj)                                             # an earlier applied review, stamped now
    first = vr.review(proj, spec, "ops")
    assert first["applied"] is True and first["raised"] == 0
    real = vr._call
    won = {}

    def racing(*a, **k):
        out = real(*a, **k)
        won["seq"] = proj.events.add(vr.REVIEWED, item="plant", source="architecture", at=1.0,
                                     data={"system": "ops", "applied": True, "functions": {}})["seq"]
        return out
    monkeypatch.setattr(vr, "_call", racing)
    _answer(proj, missing=("S4",))
    r = vr.review(proj, spec, "ops")
    assert r["applied"] is False and r["raised"] == 0
    assert _events(proj)[-1]["data"]["applied"] is False
    assert _req(proj, "vsm-s4") is None                       # the competitor raised nothing: nor does this one
    assert vr.latest(proj, "ops")["seq"] == won["seq"] > first["seq"]   # though its at=1.0 is the earliest


def test_sync_never_answers_an_architecture_request(proj):
    _answer(proj, missing=("S4",))
    vr.review(proj, proj.model.spec, "ops")
    rq.sync(proj, coherence=False, extremes=False)
    assert _req(proj, "vsm-s4")["state"] == "held"


def test_explain_says_the_latest_review_and_when_it_is_stale(proj, tmp_path):
    _answer(proj, missing=("S4",))
    vr.review(proj, proj.model.spec, "ops")
    text = explain(proj.model.spec, "system.ops", project=proj)
    assert "Viable System Model:" in text and "S1 operations: present (goal.short)" in text
    assert "S4 intelligence: missing" in text and "S5 policy: present (description)" in text
    assert "earlier version" not in text and "$0.0123 reported" in text
    sig = vr.signature(proj.model.spec, "ops")
    _write(tmp_path / "m", MODEL.replace(DESC, "keeps the job queue short"))
    p2 = Project(mdl.load(tmp_path / "m"))
    assert vr.signature(p2.model.spec, "ops") == sig           # only the words changed
    assert "reviewed on an earlier version of this system" in explain(p2.model.spec, "system.ops", project=p2)
    assert "Viable System Model" not in explain(p2.model.spec, "system.ops")   # no project: nothing read


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(st) and not st.startswith("Z")


def test_a_hung_ai_is_killed_at_its_timeout(proj, monkeypatch):
    monkeypatch.setattr(vr, "TIMEOUT", 1)
    (proj.fake / "hang").write_text("")
    _answer(proj)
    t0 = time.monotonic()
    r = vr.review(proj, proj.model.spec, "ops")
    took = time.monotonic() - t0
    assert not r["reviewed"] and "Timeout" in r["why"] and r["cost_usd"] == 0.25
    pids = [int((proj.fake / f).read_text()) for f in ("pid", "child")]
    assert not any(_alive(x) for x in pids)
    assert took < 45                                 # (the child's 60 s sleep would hold the pipes open to the end)


def test_an_interrupt_survives_a_group_already_gone(monkeypatch):
    from ergostat.decisions import ai

    def gone(self, *a, **k):                         # the group exits, then the call is interrupted
        os.killpg(self.pid, 9)
        self.wait()
        raise KeyboardInterrupt
    monkeypatch.setattr(subprocess.Popen, "communicate", gone)
    with pytest.raises(KeyboardInterrupt):           # not ProcessLookupError from the second killpg
        ai._grouped(["sleep", "30"], "", 5)


def test_the_template_s_own_system_is_never_reviewed(proj, tmp_path, capsys):
    one_judge = MODEL.replace("  checker: {type: judge, system: ops}\n", "")       # (the template brings its own)
    _write(tmp_path / "m", one_judge + "uses:\n  modelling: {use: modelling}\n")
    p = Project(mdl.load(tmp_path / "m"))
    assert "modelling" in p.model.spec.systems
    _answer(proj)
    got = vr.review_all(p, p.model.spec, max_cost=5)
    assert "modelling" not in [r["system"] for r in got["reviews"] + got["not_reviewed"]] and len(got["reviews"]) == 4
    assert main(["-C", str(tmp_path / "m"), "improve", "--architecture", "modelling"]) == 2
    assert [x["part"] for x in vsm.checklist(p.model.spec, "ops")["S4"]] == ["use: modelling"]


def test_improve_architecture_prints_each_review_and_its_cost(proj, capsys):
    d = str(proj.model.path.parent)
    _answer(proj, missing=("S4",))
    assert main(["-C", d, "improve", "--architecture", "ops"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0].startswith("ops: present S1, S2, S3, S3*, S5; missing S4; unsupported none; raised 1, answered 0")
    assert "$0.0123 (reported)" in out[0] and out[-1].startswith("total: $0.0123 of $1.00; 1 reviewed, 0 not")
    assert main(["-C", d, "improve", "--architecture", "ops", "--json", "--model", "sonnet"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert [r["system"] for r in got["reviews"]] == ["ops"] and got["reviews"][0]["missing"] == ["S4"]
    assert got["spent"] == 0.0123 and _events(proj)[-1]["data"]["model"] == "sonnet"
