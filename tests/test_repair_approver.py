"""The repair loop's second rung (SPEC §12r, ``approver: ai``): the guard decides whether the AI may be asked; the AI
sees only the program's path, the diff and "passed"; its approval is written only if the version it judged is still the
one waiting, re-read under the failure's lock. Most of these run the fix in this process with the sandbox's trial and
the impact report stubbed (what is under test is what comes after them); the end-to-end run needs the OS sandbox."""

import json

import pytest

from ergostat.actions import gate
from ergostat.actions import record as actions
from ergostat.inbox import stats
from ergostat.repair import FAILURE, approve, fix
from tests.test_repair2 import _WHY, BROKEN, FIXED, PY, broken, calls, fixed, git, one, project

A = type("A", (), {"model": "haiku", "budget": 0.25, "daily": 2.0, "timeout": 40.0})
REVIEW = "You review"


@pytest.fixture(autouse=True)
def _quick(monkeypatch):
    monkeypatch.setenv("ERGOSTAT_IMPACT_SECONDS", "3")
    yield
    from ergostat import runner
    runner.STOPPING.clear()


def opened(tmp_path, monkeypatch, **kw):
    p, e = project(tmp_path, monkeypatch, approver="ai", **kw)
    try:
        fid = broken(p, e)
    finally:
        e.close()
    return p, fid


def run_fix(p, monkeypatch, fid, approver="ai", risk="low"):
    """``repair fix`` in this process: its trial (the sandbox) and impact report stubbed."""
    from ergostat.library.run import common
    monkeypatch.setattr(common, "project", lambda: p)
    monkeypatch.setattr(common, "block_input", lambda: {"item": {"id": fid}})
    monkeypatch.setattr(fix, "trial", lambda *a, **k: {"passed": True, "how": "exited 0 (stubbed)",
                                                       "stdout": "TEST-OUTPUT-1234", "stderr": ""})
    monkeypatch.setattr(fix, "impact", lambda *a, **k: {"said": "small", "fields": {"risk": {"level": risk}}})
    assert fix.main(["--approver", approver, "--timeout", "40"]) == 0
    return one(p, fid)


def proposed(p, fid, program=FIXED, risk="low"):
    """A tested fix waiting, as ``fix.run`` leaves it: its clone, ``passed`` and ``apply-fix`` asked for."""
    name = fid.split("/")[1]
    c, base = fix.clone(fix.owner_repo(p.model.path.parent), p.dir / "repair" / name)
    sha = fix.propose(c, "collect.py", program, fid)
    with approve.held(p, name):
        passed = fix.record(p, "passed", fid, {"fix": sha, "base": base, "tests": "passed", "risk": risk,
                                               "diff": c("diff", base, sha), "approval": None})
        action = gate.request(p, p.model.spec, "apply-fix", {}, {"block": "repair-fix", "item": fid}, asker="program",
                              key=f"{name}-{sha}")
    return name, passed, action


def review(p, fid, name, passed, action, program=FIXED):
    return approve.review(p, A, fid, name, "collect.py", BROKEN, program, ["answer.json", "collect.py"], passed, action)


def reviews(tmp_path) -> list[dict]:
    return [c for c in calls(tmp_path) if c["prompt"].startswith(REVIEW)]


def approvals(p, aid) -> list[dict]:
    return p.events.query(n=None, item=actions.item_of(aid), type="ergostat.action.approved")


# ---- check


def test_check_accepts_approver_ai(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, approver="ai")             # (project() asserts no error)
    e.close()
    assert "--approver ai" in p.model.spec.blocks["repair-fix"].params["run"]


# ---- the run


def test_ai_approves_guarded_fix_and_sweep_applies(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    root = p.model.path.parent
    it = run_fix(p, monkeypatch, fid)
    a = actions.about(p, fid)[0]
    assert a["state"] == "approved" and a["approved_by"] == "ai approver (haiku)", a
    ap = it.fields["approval"]
    passed = p.events.query(n=None, item=fid, type=f"{FAILURE}.passed")[-1]
    req = p.events.query(n=None, item=a["id"], type="ergostat.action.requested")[-1]
    assert ap["verdict"] == "approve" and ap["guard"] == [] and ap["by"] == "ai approver (haiku)"
    assert ap["stamp"] == {"action": a["id"], "requested_seq": req["seq"], "fix": it.fields["fix"],
                           "passed_seq": passed["seq"]}
    (asked,) = reviews(tmp_path)
    got = json.loads(asked["prompt"].rsplit("\n", 1)[1])
    assert set(got) == {"program", "diff", "test"} and got["test"] == "passed" and got["program"] == "collect.py"
    assert "TEST-OUTPUT" not in asked["prompt"] and "the tracker answers in v3" not in asked["prompt"]
    assert asked["argv"] == ["--model", "haiku"], "the template's model (the stand-in is given no claude flags)"
    assert gate.sweep(p, p.model.spec) == 1
    assert one(p, fid).state == "applied" and (root / "collect.py").read_text() == FIXED


def test_approver_person_is_as_on_main(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    it = run_fix(p, monkeypatch, fid, approver="person")
    assert actions.about(p, fid)[0]["state"] == "requested" and not reviews(tmp_path)
    assert it.fields.get("approval") is None and gate.sweep(p, p.model.spec) == 0


def test_guard_escalates_without_asking_ai(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch, program=FIXED + "import shutil\nshutil.rmtree('x')\n")
    it = run_fix(p, monkeypatch, fid)
    assert not reviews(tmp_path) and len(calls(tmp_path)) == 1, "only the fixer was asked"
    assert actions.about(p, fid)[0]["state"] == "requested"
    ap = it.fields["approval"]
    assert ap["verdict"] == "escalate" and ap["guard"] and ap["reasons"] == ap["guard"]
    assert any("expression other than" in r for r in ap["guard"]), ap["guard"]


def test_high_risk_escalates_without_asking_ai(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    it = run_fix(p, monkeypatch, fid, risk="high")
    assert not reviews(tmp_path) and actions.about(p, fid)[0]["state"] == "requested"
    assert any("risk is high" in r for r in it.fields["approval"]["guard"])


@pytest.mark.parametrize("answer", [{"approve": False, "reasons": ["hides an error"]}, "not json at all",
                                    {"approve": "yes"}, "timeout"])
def test_ai_says_no_or_garbage_escalates(tmp_path, monkeypatch, answer):
    p, fid = opened(tmp_path, monkeypatch, review=None if answer == "timeout" else answer)
    name, passed, action = proposed(p, fid)
    if answer == "timeout":
        hang = tmp_path / "hang.py"
        hang.write_text("import sys, time\nsys.stdin.read()\ntime.sleep(20)\n")
        monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {hang}")
        monkeypatch.setattr(A, "timeout", 4.0)
    ap = review(p, fid, name, passed, action)
    assert ap["verdict"] == "escalate" and ap["reasons"], ap
    assert actions.about(p, fid)[0]["state"] == "requested" and not approvals(p, action["id"])
    if answer == "timeout":
        assert "did not answer" in ap["reasons"][0]


def test_capped_ledger_escalates(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    name, passed, action = proposed(p, fid)
    (p.dir / "repair" / "spend.jsonl").write_text("not a ledger\n")
    ap = review(p, fid, name, passed, action)
    assert not calls(tmp_path), "no AI call"
    assert ap["verdict"] == "escalate" and "cannot be read" in ap["reasons"][0]
    assert actions.about(p, fid)[0]["state"] == "requested" and one(p, fid).state == "awaiting-approval", "held, not nacked"


# ---- the version judged (lesson-1, -2, -5)


def test_remake_during_ai_call_not_approved(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    name, passed, action = proposed(p, fid)
    real, new = approve.judge, {}

    def remade_in_between(p_, prompt, a):                   # the AI answered; then the fix is made again
        got = real(p_, prompt, a)
        new["passed"], new["action"] = proposed(p, fid, program=FIXED + "print('again')\n")[1:]
        return got
    monkeypatch.setattr(approve, "judge", remade_in_between)
    ap = review(p, fid, name, passed, action)
    assert ap["verdict"] == "stale" and ap["stamp"]["passed_seq"] == passed["seq"]
    assert actions.get(p, action["id"])["state"] == "requested" and not approvals(p, action["id"])
    assert actions.get(p, new["action"]["id"])["state"] == "requested" and not approvals(p, new["action"]["id"])
    assert gate.sweep(p, p.model.spec) == 0


def test_requested_seq_mismatch_not_approved(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    name, passed, action = proposed(p, fid)
    real = approve.judge

    def asked_again(p_, prompt, a):                          # the same action, the same key, asked again
        got = real(p_, prompt, a)
        actions.step(p, action["id"], "requested", {**{k: action.get(k) for k in ("action", "gate", "item", "asker")},
                                                    "key": action["key"]})
        return got
    monkeypatch.setattr(approve, "judge", asked_again)
    ap = review(p, fid, name, passed, action)
    assert actions.get(p, action["id"])["state"] == "requested" and actions.get(p, action["id"])["key"] == action["key"]
    assert ap["verdict"] == "stale" and not approvals(p, action["id"])


def test_denial_during_ai_call_stays_denied(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    root = p.model.path.parent
    head = git("rev-parse", "HEAD", cwd=root)
    name, passed, action = proposed(p, fid)
    real = approve.judge

    def denied_in_between(p_, prompt, a):
        got = real(p_, prompt, a)
        gate.deny(p, action["id"], by="owner", note="not this one")
        return got
    monkeypatch.setattr(approve, "judge", denied_in_between)
    assert review(p, fid, name, passed, action)["verdict"] == "stale"
    assert actions.get(p, action["id"])["state"] == "denied" and not approvals(p, action["id"])
    assert gate.sweep(p, p.model.spec) == 0 and git("rev-parse", "HEAD", cwd=root) == head


def test_denial_after_ai_approval_stays_denied(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    root = p.model.path.parent
    head = git("rev-parse", "HEAD", cwd=root)
    name, passed, action = proposed(p, fid)
    assert review(p, fid, name, passed, action)["verdict"] == "approve"
    actions.step(p, action["id"], "denied", {"denied_by": "owner", "note": "no"}, by="owner")    # before the sweep
    assert actions.get(p, action["id"])["state"] == "denied"
    assert gate.sweep(p, p.model.spec) == 0 and git("rev-parse", "HEAD", cwd=root) == head


def test_remade_failure_clears_old_approval(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    name, passed, action = proposed(p, fid)
    review(p, fid, name, passed, action)
    assert one(p, fid).fields["approval"]["verdict"] == "approve"
    proposed(p, fid, program=FIXED + "print('again')\n")
    assert one(p, fid).fields.get("approval", "missing") is None


# ---- counted apart


def test_ai_answers_counted_apart(tmp_path, monkeypatch):
    p, fid = opened(tmp_path, monkeypatch)
    spec = p.model.spec
    name, passed, action = proposed(p, fid)
    review(p, fid, name, passed, action)
    r = stats.by_class(p, spec)["apply-fix"]
    assert (r["by_agent"], r["approved"]) == (1, 0), r
    assert "apply-fix" not in stats.asked_today(p, spec)
    name, passed, action = proposed(p, fid, program=FIXED + "print('again')\n")
    gate.approve(p, spec, action["id"])                        # a person's approval, the twin
    r = stats.by_class(p, spec)["apply-fix"]
    assert (r["by_agent"], r["approved"]) == (1, 1), r
    assert stats.asked_today(p, spec).count("apply-fix") == 1


# ---- end to end, in the sandbox


@pytest.mark.skipif(_WHY is not None, reason=_WHY or "")
def test_ai_approver_end_to_end_in_the_sandbox(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, approver="ai")
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
        assert it.fields["approval"]["verdict"] in ("approve", "escalate"), it.fields["approval"]
        if it.fields["approval"]["verdict"] == "approve":
            gate.sweep(p, p.model.spec)
            assert one(p, fid).state == "applied"
    finally:
        e.close()
