"""Act-risk (SPEC §12k): an action declared with ``risk:`` is gated one step stricter when the risk of this act
reaches its threshold, at the request and again at the act (inside the run lock), never looser than its gate."""

import itertools
import math
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import spec as spec_mod
from ergostat.actions import gate, record, risk
from ergostat.claims import record as claims
from ergostat.store import Project

DAY = 86400.0


def model(gate_="auto", risk_="{severity: 3, threshold: 4}", name="act") -> str:
    return textwrap.dedent(f"""
        name: t
        actions:
          {name}:
            run: "echo x >> ran.txt; echo ok"
            gate: {gate_}
            in: .
            {"risk: " + risk_ if risk_ else ""}
        blocks:
          dev: {{type: program, run: "true", actions: [{name}], every: 1h}}
    """)


def project(tmp_path, text=None, **kw) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(text or model(**kw))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [x.message for x in m.problems]
    return Project(m)


def edit(tmp_path, text):
    (tmp_path / "ergostat.yaml").write_text(text)


def ctx(tmp_path, block="dev"):
    return {"block": block, "run": "run1", "item": None, "workdir": str(tmp_path)}


def said(p, block, *states):
    """Claims made by ``block``, each given its verdict (``made``: none)."""
    for i, s in enumerate(states):
        c = claims.made(p, p.model.spec, block, {"says": f"did {i} {time.time()}"}, run=f"r{i}", n=i)
        if s != "made":
            claims.verdict(p, c, s, {}, "test")


def ran_before(p, days, name="act", how="ran"):
    """An earlier action of this name, requested ``days`` ago, that ran (or failed)."""
    aid, t = record.new_id(name), time.time() - days * DAY
    p.events.add("ergostat.action.requested", item=aid, source="dev", data={"action": name, "gate": "auto"}, at=t)
    p.events.add("ergostat.action.approved", item=aid, source="gate", data={"approved_by": "gate"}, at=t + 1)
    p.events.add(f"ergostat.action.{how}", item=aid, source="gate", data={"exit": 0 if how == "ran" else 1}, at=t + 2)


def known(p, block="dev"):
    """c = 0 (one claim verified, none contradicted) and n = 0 (it ran 10 days ago)."""
    said(p, block, "verified")
    ran_before(p, 10)


def ask(p, tmp_path, asker="session", name="act"):
    return gate.request(p, p.model.spec, name, {}, ctx(tmp_path), asker=asker)


def ran(tmp_path) -> bool:
    return (tmp_path / "ran.txt").exists()


def types(p, aid):
    return [e["type"].rsplit(".", 1)[1] for e in p.events.query(n=None, item=aid)]


# ---- the score


def test_score_formula():
    assert risk.score(2, 0.5, 1) == 12.0
    assert risk.score(1, 0, 0) == 1.0
    assert risk.score(5, 1, 1) == 50.0


def test_severity_alone_changes_the_step(tmp_path):
    p = project(tmp_path / "a", risk_="{severity: 3, threshold: 4}")
    known(p)
    a = ask(p, tmp_path / "a")
    assert a["risk"]["score"] == 3.0 and a["approved_by"] == "gate" and a["state"] == "ran" and ran(tmp_path / "a")
    p = project(tmp_path / "b", risk_="{severity: 4, threshold: 4}")
    known(p)
    b = ask(p, tmp_path / "b")
    assert b["state"] == "requested" and b["risk"]["gate"] == "approve" and not ran(tmp_path / "b")


def test_threshold_alone_changes_the_step(tmp_path):
    p = project(tmp_path / "a", risk_="{severity: 4, threshold: 6}")
    known(p)
    assert ask(p, tmp_path / "a")["state"] == "ran"
    p = project(tmp_path / "b", risk_="{severity: 4, threshold: 4}")
    known(p)
    assert ask(p, tmp_path / "b")["state"] == "requested"


def test_auto_steps_to_approve(tmp_path):
    p = project(tmp_path, risk_="{severity: 5}")
    a = ask(p, tmp_path)
    assert a["state"] == "requested" and a["risk"]["gate"] == "approve" and a["risk"]["score"] == 50.0
    assert "act-risk 50 ≥ 8: its gate auto stepped to approve" in gate.result(a)["note"] and not ran(tmp_path)


def test_approve_steps_to_deny(tmp_path):
    p = project(tmp_path, gate_="approve", risk_="{severity: 5}")
    a = ask(p, tmp_path)
    assert a["state"] == "denied" and a["denied_by"] == "gate" and a["risk"]["gate"] == "deny"
    assert gate.result(a)["note"] == "act-risk 50 ≥ 8: its gate approve stepped to deny"


def test_deny_stays_deny(tmp_path):
    p = project(tmp_path, gate_="deny", risk_="{severity: 5}")
    a = ask(p, tmp_path)
    assert a["state"] == "denied" and a["risk"]["gate"] == "deny" and "act-risk 50 ≥ 8" in a["note"]


def test_no_risk_key_gates_as_before(tmp_path):
    p = project(tmp_path, risk_=None)
    said(p, "dev", "contradicted")                                   # c = 1
    a = ask(p, tmp_path)
    assert a["state"] == "ran" and "risk" not in a and a["approved_by"] == "gate" and ran(tmp_path)
    assert a["risk_at_act"]["effective"] == "auto"


# ---- c: the asking block's contradicted share


def c_of(p, block="dev"):
    got = risk.inputs(p, "act", block)
    return got["c"], got["c_why"]


def test_block_missing_from_claims_counts_as_one(tmp_path):
    p = project(tmp_path)
    said(p, "other", "verified")
    assert c_of(p) == (1.0, "no claims on record")
    assert c_of(p, None) == (1.0, "no asking block")


def test_block_with_no_checked_claims_counts_as_one(tmp_path):
    p = project(tmp_path)
    said(p, "dev", "unchecked", "unchecked", "made")
    c, why = c_of(p)
    assert c == 1.0 and why == "claims made, none checked" and why != "no claims on record"


def test_checked_none_contradicted_counts_zero(tmp_path):
    p = project(tmp_path)
    said(p, "dev", "verified", "verified", "unchecked")
    assert c_of(p) == (0.0, "contradicted share")
    said(p, "dev", "contradicted", "contradicted")
    assert c_of(p)[0] == 0.5


def test_claims_unreadable_counts_as_one(tmp_path, monkeypatch):
    p = project(tmp_path)
    said(p, "dev", "verified")

    def broken(*a, **kw):
        raise OSError("disk")
    monkeypatch.setattr(claims, "stored", broken)
    assert c_of(p) == (1.0, "claims record unreadable")


def test_nan_share_counts_as_one(tmp_path, monkeypatch):
    from ergostat.claims import trust
    p = project(tmp_path, risk_="{severity: 2, threshold: 6}")
    ran_before(p, 10)                                                # n = 0
    monkeypatch.setattr(trust, "counts", lambda cs, who=None: {"claims": 2, "checked": 2, "verified": 1,
                                                               "contradicted": 1, "contradicted_share": math.nan})
    a = ask(p, tmp_path)
    assert a["risk"]["c"] == 1.0 and a["risk"]["n"] == 0 and a["risk"]["score"] == 10.0
    assert a["risk"]["gate"] == "approve" and a["state"] == "requested" and not ran(tmp_path)
    assert risk.clamp(math.inf) == 1.0 and risk.clamp(-math.inf) == 1.0 and risk.clamp(-0.5) == 0.0
    assert risk.clamp(1.5) == 1.0 and risk.clamp("x") == 1.0


# ---- n: novelty


def n_of(p, aid=None):
    got = risk.inputs(p, "act", "dev", aid)
    return got["n"], got["n_why"]


def test_novel_when_never_ran(tmp_path):
    p = project(tmp_path)
    ran_before(p, 10, name="other")
    assert n_of(p) == (1, "not run within 90 days")


def test_known_when_ran_within_90_days(tmp_path):
    p = project(tmp_path)
    ran_before(p, 89)
    assert n_of(p) == (0, "ran within 90 days")


def test_novel_when_last_ran_over_90_days_ago(tmp_path):
    p = project(tmp_path)
    ran_before(p, 91)
    assert n_of(p)[0] == 1


def test_failed_run_is_not_known(tmp_path):
    p = project(tmp_path)
    ran_before(p, 10, how="failed")
    assert n_of(p)[0] == 1


def test_novelty_record_unreadable_counts_novel(tmp_path, monkeypatch):
    p = project(tmp_path, gate_="approve")
    ran_before(p, 10)

    def broken(*a, **kw):
        raise OSError("disk")
    monkeypatch.setattr(record, "stored", broken)
    a = ask(p, tmp_path)
    assert (a["risk"]["n"], a["risk"]["n_why"]) == (1, "action record unreadable")


# ---- the act, read again inside the run lock


def test_contradiction_between_request_and_act_reholds(tmp_path):
    p = project(tmp_path)                                            # auto, S=3, T=4
    known(p)
    a = ask(p, tmp_path, asker="program")
    assert a["state"] == "approved" and a["approved_by"] == "gate" and a["risk"]["score"] == 3.0
    said(p, "dev", "contradicted", "contradicted", "contradicted")   # c: 0 → 0.75, in the window
    assert gate.sweep(p, p.model.spec) == 1
    b = record.get(p, a["id"])
    assert b["state"] == "requested" and b["held_by"] == "act-risk" and not ran(tmp_path)
    assert b["risk_at_act"]["score"] == 12.0 and b["risk_at_act"]["effective"] == "approve"
    assert b["approved_by"] is None and b["risk"]["gate"] == "auto"   # the stale gate approval cleared; risk kept
    assert "held for the owner's approval" in gate.result(b)["note"] and "act-risk 12 ≥ 4" in gate.result(b)["note"]
    n = len(types(p, a["id"]))
    assert gate.sweep(p, p.model.spec) == 0 and len(types(p, a["id"])) == n and not ran(tmp_path)
    got = gate.approve(p, p.model.spec, a["id"])                     # lesson-5: the owner's approval runs it
    assert got["state"] == "ran" and got["approved_by"] == "owner" and ran(tmp_path)


def test_in_memory_model_is_scored_at_the_act_from_the_spec_given(tmp_path):
    p = project(tmp_path)
    p.model.path = None                                              # no file: the spec passed in is read
    (tmp_path / "ergostat.yaml").write_text("name: [")               # (and the file is not)
    known(p)
    a = ask(p, tmp_path, asker="program")
    assert a["state"] == "approved"
    said(p, "dev", "contradicted", "contradicted", "contradicted")
    gate.sweep(p, p.model.spec)
    b = record.get(p, a["id"])
    assert b["state"] == "requested" and b["held_by"] == "act-risk" and b["risk_at_act"]["score"] == 12.0
    assert not ran(tmp_path)


def test_gate_edited_to_deny_between_request_and_act(tmp_path):
    p = project(tmp_path, gate_="approve", risk_=None)
    a = ask(p, tmp_path)
    assert a["state"] == "requested"
    edit(tmp_path, model(gate_="deny", risk_=None))
    got = gate.approve(p, p.model.spec, a["id"])
    assert got["state"] == "denied" and got["denied_by"] == "gate" and not ran(tmp_path)
    assert got["risk_at_act"]["effective"] == "deny" and "its gate now is deny" in got["note"]


def test_act_takes_the_stricter_of_request_and_act(tmp_path):
    p = project(tmp_path, risk_="{severity: 4, threshold: 8}")
    ran_before(p, 10)
    a = ask(p, tmp_path, asker="program")                             # no claims: c = 1, 20 ≥ 8
    assert a["state"] == "requested" and a["risk"]["gate"] == "approve"
    record.step(p, a["id"], "approved", {"approved_by": "gate"})      # crafted
    said(p, "dev", "verified")                                       # the record improves: 4 < 8 at the act
    assert gate.run_once(p, p.model.spec, a["id"])["state"] == "requested" and not ran(tmp_path)
    b = record.get(p, a["id"])
    assert b["risk_at_act"]["gate"] == "auto" and b["risk_at_act"]["effective"] == "approve"
    assert b["risk"]["gate"] == "approve", "the refolded id keeps its request's stepped gate"
    record.step(p, a["id"], "approved", {"approved_by": "gate"})      # again: still the request's gate counts
    assert gate.run_once(p, p.model.spec, a["id"])["state"] == "requested" and not ran(tmp_path)


def test_owner_approval_runs_when_act_steps_to_approve(tmp_path):
    p = project(tmp_path, risk_="{severity: 5}")
    a = ask(p, tmp_path)
    assert a["state"] == "requested"
    got = gate.approve(p, p.model.spec, a["id"])
    assert got["state"] == "ran" and got["risk_at_act"]["effective"] == "approve" and ran(tmp_path)


def test_action_gone_at_act_is_denied(tmp_path):
    p = project(tmp_path, gate_="approve", risk_=None)
    a = ask(p, tmp_path)
    edit(tmp_path, model(gate_="approve", risk_=None, name="renamed"))
    got = gate.approve(p, p.model.spec, a["id"])
    assert got["state"] == "denied" and got["denied_by"] == "gate" and "no longer in the model" in got["note"]
    assert not ran(tmp_path)


def test_model_unreadable_at_act_reholds(tmp_path):
    p = project(tmp_path)
    known(p)
    a = ask(p, tmp_path, asker="program")
    edit(tmp_path, "name: t\nactions: [")
    gate.sweep(p, p.model.spec)
    b = record.get(p, a["id"])
    assert b["state"] == "requested" and b["held_by"] == "act-risk" and "cannot be read" in b["held_note"]
    assert not ran(tmp_path) and not (gate.folder(p) / f"{record.short(a['id'])}.run").exists()
    n = len(types(p, a["id"]))
    assert gate.sweep(p, p.model.spec) == 0 and len(types(p, a["id"])) == n
    edit(tmp_path, model())
    assert gate.approve(p, p.model.spec, a["id"])["state"] == "ran" and ran(tmp_path)


def test_rehold_removes_only_its_own_lock(tmp_path, monkeypatch):
    p = project(tmp_path)
    known(p)
    other = gate.folder(p) / "0123456789.run"
    other.write_text("")
    a = ask(p, tmp_path, asker="program")
    mine = gate.folder(p) / f"{record.short(a['id'])}.run"
    said(p, "dev", "contradicted", "contradicted", "contradicted")
    seen = []
    step = record.step

    def watch(p_, aid, what, data, **kw):                            # the lock is still there as the hold is written
        if data.get("held_by") == "act-risk":
            seen.append(mine.exists())
        return step(p_, aid, what, data, **kw)
    monkeypatch.setattr(record, "step", watch)
    gate.sweep(p, p.model.spec)
    assert seen == [True] and not mine.exists() and other.exists()
    assert record.get(p, a["id"])["held_by"] == "act-risk"


# ---- never looser


LEVEL = {g: i for i, g in enumerate(risk.ORDER)}


def test_never_looser(tmp_path, monkeypatch):
    for s, t, c, n, base in itertools.product(range(1, 6), (1.5, 4, 8, 20, 50), (0, 0.25, 1, math.nan), (0, 1),
                                              risk.ORDER):
        g = risk.step(base, risk.score(s, risk.clamp(c), n), t)
        assert LEVEL[base] <= LEVEL[g] <= LEVEL[base] + 1
    for x, y in itertools.product(risk.ORDER, repeat=2):
        assert LEVEL[risk.stricter(x, y)] == max(LEVEL[x], LEVEL[y])
    real = risk.contradicted
    for i, (s, t, base, c_act) in enumerate(itertools.product((1, 5), (4, 50), ("auto", "approve"), (0, 1))):
        d = tmp_path / str(i)
        p = project(d, gate_=base, risk_=f"{{severity: {s}, threshold: {t}}}")
        known(p)                                                     # c = 0, n = 0 at the request
        monkeypatch.setattr(risk, "contradicted", real)
        a = ask(p, d, asker="program")
        asked = a["risk"]["gate"]
        monkeypatch.setattr(risk, "contradicted", lambda *_, c=c_act: (float(c), "set"))
        if a["state"] == "approved":
            gate.sweep(p, p.model.spec)
        elif a["state"] == "requested":
            gate.approve(p, p.model.spec, a["id"])
        got = record.get(p, a["id"])
        level = {"denied": 2, "requested": 1, "ran": 0 if got.get("approved_by") == "gate" else 1}[got["state"]]
        assert level >= LEVEL[base] and level >= LEVEL[asked], (s, t, base, c_act, got["state"])
        at_act = risk.step(base, risk.score(s, c_act, 0), t)          # worked out here, not read from the record
        if got["state"] != "denied" or a["state"] != "denied":       # (one denied at the request never reached the act)
            assert level >= LEVEL[at_act], (s, t, base, c_act, got["state"])
        assert (got["state"] == "ran") == ran(d)


# ---- compile


def test_risk_key_validated(tmp_path):
    bad_s = {"s0": "0", "s6": "6", "s25": "2.5", "shigh": "high", "strue": "true"}
    bad_t = {"t1": "1", "t51": "51", "tnan": ".nan", "tinf": ".inf", "tminf": "-.inf", "ttrue": "true"}
    lines = ["name: t", "actions:"]
    for k, v in bad_s.items():
        lines += [f"  {k}:", "    run: x", "    risk:", f"      severity: {v}"]
    for k, v in bad_t.items():
        lines += [f"  {k}:", "    run: x", "    risk:", "      severity: 2", f"      threshold: {v}"]
    lines += ["  good:", "    run: x", "    risk: {severity: 3, threshold: 12}",
              "  plain:", "    run: x", "    risk: {severity: 1}"]
    (tmp_path / "ergostat.yaml").write_text("\n".join(lines) + "\n")
    compiled, problems = spec_mod.read(tmp_path / "ergostat.yaml")
    errs = [x for x in problems if x.level == "error"]
    for k in bad_s:
        hit = [x for x in errs if f"action {k}.risk.severity" in x.message]
        assert hit and hit[0].code == "bad-value" and hit[0].where and hit[0].where.line, k
    for k in bad_t:
        hit = [x for x in errs if f"action {k}.risk.threshold" in x.message]
        assert hit and hit[0].code == "bad-value" and hit[0].where and hit[0].where.line, k
    assert not [x for x in errs if "good" in x.message or "plain" in x.message]
    assert len(errs) == len(bad_s) + len(bad_t), [x.message for x in errs]
    good, plain = compiled.actions["good"], compiled.actions["plain"]
    assert (good.severity, good.threshold) == (3, 12.0) and (plain.severity, plain.threshold) == (1, 8.0)
    assert compiled.actions["s0"].severity != 0


if __name__ == "__main__":
    pytest.main([__file__])
