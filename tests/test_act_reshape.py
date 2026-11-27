"""Reshaping an act (SPEC §12k, *Reshaping an act*): under a column whose cell is ``{reshape: ACTION}`` the full act is
held for the owner and the smaller declared action is asked for at once, each linked to the other."""

import json
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat import spec as spec_mod
from ergostat.actions import gate, operating, program, record, server
from ergostat.store import Project

PR = "{normal: auto, away: {reshape: push}}"


def model(pr_gate=PR, push_gate="auto", pr_risk="", push_args="{title: its title}",
          push_run="echo push {title} >> ran.txt") -> str:
    return textwrap.dedent(f"""
        name: t
        projections:
          ticket: {{fields: {{state: {{type: "one of [open, done]"}}}}}}
        actions:
          pr:
            run: "echo pr {{title}} >> ran.txt"
            args: {{title: its title, body: its body}}
            gate: {pr_gate}
            wait: 30s
            in: .
            {pr_risk}
          push:
            run: "{push_run}"
            args: {push_args}
            gate: {push_gate}
            wait: 1s
            in: .
        blocks:
          dev: {{type: program, run: "true", actions: [pr, push], every: 1h}}
    """)


def project(tmp_path, **kw) -> Project:
    (tmp_path / "ergostat.yaml").write_text(model(**kw))
    m = mdl.load(tmp_path)
    assert not [x for x in m.problems if x.level == "error"], [x.message for x in m.problems]
    return Project(m)


CTX = {"block": "dev", "run": "r1"}


def ask(p, tmp_path):
    return gate.request(p, p.model.spec, "pr", {"title": "t1", "body": "b1"}, {**CTX, "workdir": str(tmp_path)})


def ran(tmp_path) -> list[str]:
    f = tmp_path / "ran.txt"
    return f.read_text().splitlines() if f.exists() else []


def test_reshape_runs_target_and_holds_full(tmp_path):
    p = project(tmp_path)
    full = ask(p, tmp_path)                         # no event from the owner: away
    assert full["operating"]["column"] == "away" and full["state"] == "requested" and full["gate"] == "approve"
    t = record.get(p, full["reshaped_to"])
    assert t["action"] == "push" and t["state"] == "ran" and t["reshaped_from"] == full["id"]
    assert t["args"] == {"title": "t1"} and ran(tmp_path) == ["push t1"]
    assert gate.result(full)["reshaped_to"] == t["id"] and gate.result(t)["reshaped_from"] == full["id"]
    first = [e for e in p.events.query(n=None) if e.get("item") in (full["id"], t["id"])]
    assert first[0]["item"] == full["id"] and first[0]["data"]["reshaped_to"] == t["id"]      # the full act first
    assert next(e for e in first if e["item"] == t["id"])["data"]["reshaped_from"] == full["id"]
    operating.enter(p, "normal")                    # the owner present: normal's auto, no reshape
    b = ask(p, tmp_path)
    assert b["state"] == "ran" and "reshaped_to" not in b and ran(tmp_path)[-1] == "pr t1"


@pytest.mark.parametrize("risk", ["", "risk: {severity: 1, threshold: 50}"])
def test_full_act_never_auto_approved(tmp_path, risk):
    p = project(tmp_path, pr_risk=risk)
    assert p.model.spec.actions["pr"].gates["away"] == "approve" and p.model.spec.actions["pr"].gate == "auto"
    full = ask(p, tmp_path)
    t = record.get(p, full["reshaped_to"])
    assert t["state"] == "ran" and t["risk_at_act"]["effective"] == "auto"          # the target passed its act check
    assert full["state"] == "requested" and full.get("approved_by") is None and full["gate"] == "approve"
    assert [m["to"] for m in full["moves"]] == ["requested"], "never approved by the gate, not even to be held again"
    assert gate.sweep(p, p.model.spec) == 0
    assert record.get(p, full["id"])["state"] == "requested" and ran(tmp_path) == ["push t1"]
    # approved by the gate somehow, still away: the act reads the reshape cell as approve and holds it again
    record.step(p, full["id"], "approved", {"approved_by": record.GATE})
    gate.sweep(p, p.model.spec)
    again = record.get(p, full["id"])
    assert again["state"] == "requested" and again["held_by"] == "act-risk" and ran(tmp_path) == ["push t1"]


def test_owner_approves_full_while_away(tmp_path, monkeypatch):
    p = project(tmp_path)
    monkeypatch.setattr(operating, "presence", lambda *a: ("away", "test"))   # (the approval itself would be presence)
    full = ask(p, tmp_path)
    a = gate.approve(p, p.model.spec, full["id"])
    assert a["state"] == "ran" and ran(tmp_path) == ["push t1", "pr t1"]
    at = a["risk_at_act"]
    assert at["cell"] == "approve" and at["asked"] == "approve" and at["effective"] == "approve"
    assert at["operating"]["column"] == "away"
    assert record.get(p, full["reshaped_to"])["state"] == "ran"     # the target as it was


def test_target_gated_by_its_own_cell(tmp_path):
    p = project(tmp_path, push_gate="{normal: auto, away: deny}")
    full = ask(p, tmp_path)
    t = record.get(p, full["reshaped_to"])
    assert t["state"] == "denied" and t["denied_by"] == "gate" and t["gate"] == "deny"
    assert record.get(p, full["id"])["state"] == "requested" and ran(tmp_path) == []
    with pytest.raises(gate.GateError):
        gate.approve(p, p.model.spec, t["id"])     # the target's denial stands; the full act is the owner's still
    assert gate.approve(p, p.model.spec, full["id"])["state"] == "ran" and ran(tmp_path) == ["pr t1"]


def test_denying_full_leaves_target(tmp_path):
    for push_gate, state in (("auto", "ran"), ("approve", "requested")):
        d = tmp_path / push_gate
        d.mkdir()
        p = project(d, push_gate=push_gate)
        full = ask(p, d)
        before = record.get(p, full["reshaped_to"])
        assert before["state"] == state
        gate.deny(p, full["id"], note="not now")
        assert record.get(p, full["id"])["state"] == "denied"
        after = record.get(p, before["id"])
        assert after["state"] == state and after.get("output") == before.get("output") and \
            gate.result(after) == gate.result(before)
        if state == "requested":                    # still the owner's to answer, on its own
            assert gate.approve(p, p.model.spec, before["id"])["state"] == "ran" and ran(d) == ["push t1"]


def test_reshape_followed_once(tmp_path):
    """A target whose own cell reshapes anyway (compile refuses it; here put in by hand) is held as approve, never
    reshaped: two records, no third."""
    p = project(tmp_path)
    p.model.spec.actions["push"].reshapes = {"away": "pr"}
    full = ask(p, tmp_path)
    t = record.get(p, full["reshaped_to"])
    assert t["state"] == "requested" and t["gate"] == "approve" and "reshaped_to" not in t
    assert len(record.stored(p)) == 2 and ran(tmp_path) == []


def test_session_answered_by_target_at_once(tmp_path):
    p = project(tmp_path)
    cfg = {"block": "dev", "run": "r1", "workdir": str(tmp_path), "root": str(tmp_path), "state": str(p.dir),
           "actions": ["pr"]}
    s = server.Server(cfg, "session/dev-1")
    s._p = p
    t0 = time.monotonic()
    out = s.call("pr", {"title": "t1", "body": "b1"})
    assert time.monotonic() - t0 < 10, "never waits on the held full act (its wait is 30s)"
    r = json.loads(out["content"][0]["text"])
    assert r["action"] == "push" and r["state"] == "ran" and r["exit"] == 0
    assert r["full"]["state"] == "requested" and r["full"]["id"] == r["reshaped_from"]
    assert r["full"]["reshaped_to"] == r["id"] and not out.get("isError")
    assert record.get(p, r["id"])["deliveries"][0]["how"] == "session"


def test_program_answered_by_target_keyless(tmp_path):
    p = project(tmp_path)
    cfg = {"block": "dev", "run": "r1", "item": None, "workdir": str(tmp_path), "actions": ["pr"]}
    a = program.ask(p, p.model.spec, cfg, "pr", {"title": "t1", "body": "b1"}, key="k1")
    assert a["action"] == "push" and a["state"] == "ran" and program.exit_code(a) == 0 and "key" not in a
    full = record.get(p, a["reshaped_from"])
    assert full["state"] == "requested" and full["key"]
    b = program.ask(p, p.model.spec, {**cfg, "run": "r2"}, "pr", {"title": "t1", "body": "b1"}, key="k1")
    assert b["id"] == a["id"] and len(record.stored(p)) == 2 and ran(tmp_path) == ["push t1"]


ARGS = {"title": "t1", "body": "b1"}


def leased(p, tmp_path, fence: int, run: str) -> dict:
    """ticket/1 leased to ``run`` under ``fence`` (and given back to wait), and the run's cfg."""
    if fence == 1:
        p.events.add("ticket.opened", item="ticket/1", source="watch", data={})
    p.events.add("ergostat.lease.taken", item="ticket/1", source="ergostat", data={
        "item": "ticket/1", "run": run, "block": "dev", "fence": fence, "ttl": 300, "max": 3, "back": "open",
        "tier": "program", "attempt": fence})
    p.events.add("ergostat.lease.ended", item="ticket/1", source="ergostat", causedby=run,
                 data={"run": run, "fence": fence, "how": "nack", "why": "waits", "count": False})
    return {"block": "dev", "run": run, "item": "ticket/1", "lease": fence, "workdir": str(tmp_path),
            "actions": ["pr"], "runner": "here"}


def test_program_reask_takes_target_over_with_lease(tmp_path):
    p = project(tmp_path, push_gate="approve")
    a = program.ask(p, p.model.spec, leased(p, tmp_path, 1, "r1"), "pr", ARGS)
    assert a["action"] == "push" and a["state"] == "requested" and a["lease"] == 1
    b = program.ask(p, p.model.spec, leased(p, tmp_path, 2, "r2"), "pr", ARGS)
    assert b["id"] == a["id"] and b["fence"] == 2 and b["run"] == "r2", "the held target taken over with the full act"
    assert record.get(p, a["reshaped_from"])["fence"] == 2 and len(record.stored(p)) == 2
    t = gate.approve(p, p.model.spec, a["id"])
    assert t["state"] == "ran" and not t.get("fenced") and ran(tmp_path) == ["push t1"]


def test_program_failed_target_asked_anew(tmp_path):
    p = project(tmp_path, push_run="test -f ok || exit 3; echo push {title} >> ran.txt")
    cfg = {"block": "dev", "run": "r1", "item": "ticket/1", "workdir": str(tmp_path), "actions": ["pr"]}
    a = program.ask(p, p.model.spec, cfg, "pr", ARGS)
    assert a["action"] == "push" and a["state"] == "failed" and a["exit"] == 3
    (tmp_path / "ok").write_text("")
    b = program.ask(p, p.model.spec, {**cfg, "run": "r2"}, "pr", ARGS)
    assert b["id"] != a["id"] and b["state"] == "ran" and ran(tmp_path) == ["push t1"], "a failed target asked anew"
    full = record.get(p, a["reshaped_from"])
    assert full["state"] == "requested" and full["reshaped_to"] == b["id"] and b["reshaped_from"] == full["id"]
    c = program.ask(p, p.model.spec, {**cfg, "run": "r3"}, "pr", ARGS)
    assert c["id"] == b["id"] and len(record.stored(p)) == 3 and ran(tmp_path) == ["push t1"], "one that ran stands"
    assert [d["run"] for d in c["deliveries"]] == ["r2", "r3"]


def test_program_answered_by_full_once_owner_answers(tmp_path, monkeypatch):
    p = project(tmp_path)
    monkeypatch.setattr(operating, "presence", lambda *a: ("away", "test"))   # (the owner's answers would be presence)
    cfg = {"block": "dev", "run": "r1", "item": None, "workdir": str(tmp_path), "actions": ["pr"]}
    for key, answer in (("k1", "approve"), ("k2", "deny")):
        t = program.ask(p, p.model.spec, cfg, "pr", ARGS, key=key)
        assert t["action"] == "push" and t["state"] == "ran"
        getattr(gate, answer)(*((p, p.model.spec) if answer == "approve" else (p,)), t["reshaped_from"])
        full = program.ask(p, p.model.spec, {**cfg, "run": f"r2-{key}"}, "pr", ARGS, key=key)
        assert full["id"] == t["reshaped_from"] and full["action"] == "pr", "the full act's own answer, once given"
        assert full["state"] == {"approve": "ran", "deny": "denied"}[answer]
        assert full["deliveries"][-1]["run"] == f"r2-{key}"
    assert ran(tmp_path) == ["push t1", "pr t1", "push t1"]


def test_program_full_denied_by_risk_target_runs_once(tmp_path):
    """Act-risk steps the full act's approve to deny at its request; its target ran. Asked again (same key), the
    denied full act stands, answered by that target: no new full act, the target never run again (lesson-5)."""
    p = project(tmp_path, pr_risk="risk: {severity: 3, threshold: 2}",
                push_run="test -f ok || exit 3; echo push {title} >> ran.txt")
    (tmp_path / "ok").write_text("")
    cfg = {"block": "dev", "run": "r1", "item": None, "workdir": str(tmp_path), "actions": ["pr"]}
    a = program.ask(p, p.model.spec, cfg, "pr", ARGS, key="k1")
    full = record.get(p, a["reshaped_from"])
    assert full["state"] == "denied" and full["denied_by"] == "gate" and full["gate"] == "approve"
    assert a["action"] == "push" and a["state"] == "ran" and ran(tmp_path) == ["push t1"]
    for run in ("r2", "r3"):
        b = program.ask(p, p.model.spec, {**cfg, "run": run}, "pr", ARGS, key="k1")
        assert b["id"] == a["id"] and len(record.stored(p)) == 2 and ran(tmp_path) == ["push t1"], run
    assert [d["run"] for d in record.get(p, a["id"])["deliveries"]] == ["r1", "r2", "r3"]
    # a target that no longer stands: both asked for anew, the new target run once
    (tmp_path / "ok").unlink()
    c = program.ask(p, p.model.spec, {**cfg, "key": "k2"}, "pr", ARGS, key="k2")
    assert c["state"] == "failed"
    (tmp_path / "ok").write_text("")
    d = program.ask(p, p.model.spec, {**cfg, "run": "r4"}, "pr", ARGS, key="k2")
    assert d["id"] != c["id"] and d["state"] == "ran" and d["reshaped_from"] != c["reshaped_from"]
    assert ran(tmp_path) == ["push t1", "push t1"] and len(record.stored(p)) == 6


def test_program_full_denied_by_risk_asked_anew_once_owner_back(tmp_path):
    """Denied by its act-risk under away, its target ran. The owner back (normal: auto, no reshape, a risk that
    passes), the same ask no longer finds the denied full act standing: the full act is asked anew and runs once, and
    the target is not run again (lesson-5)."""
    p = project(tmp_path, pr_risk="risk: {severity: 3, threshold: {normal: 100, away: 2}}")
    cfg = {"block": "dev", "run": "r1", "item": None, "workdir": str(tmp_path), "actions": ["pr"]}
    a = program.ask(p, p.model.spec, cfg, "pr", ARGS, key="k1")
    full = record.get(p, a["reshaped_from"])
    assert full["state"] == "denied" and full["denied_by"] == "gate" and a["state"] == "ran"
    operating.enter(p, "normal")                    # the owner present: normal's auto, T 100 (no item: s = 1)
    b = program.ask(p, p.model.spec, {**cfg, "run": "r2"}, "pr", ARGS, key="k1")
    assert b["action"] == "pr" and b["id"] != full["id"] and b["state"] == "ran" and "reshaped_to" not in b
    c = program.ask(p, p.model.spec, {**cfg, "run": "r3"}, "pr", ARGS, key="k1")
    assert c["id"] == b["id"] and len(record.stored(p)) == 3, "the full act that ran stands"
    assert ran(tmp_path) == ["push t1", "pr t1"], "the full act ran once, the target once"


def test_program_full_denied_by_risk_held_target_leased(tmp_path):
    """The full act denied by its act-risk, its target held: asked again under a later lease, the target is taken over
    by that lease (as under a held full act), and runs once approved."""
    p = project(tmp_path, push_gate="approve", pr_risk="risk: {severity: 3, threshold: 2}")
    a = program.ask(p, p.model.spec, leased(p, tmp_path, 1, "r1"), "pr", ARGS)
    assert a["action"] == "push" and a["state"] == "requested" and record.get(p, a["reshaped_from"])["state"] == "denied"
    b = program.ask(p, p.model.spec, leased(p, tmp_path, 2, "r2"), "pr", ARGS)
    assert b["id"] == a["id"] and b["fence"] == 2 and len(record.stored(p)) == 2
    t = gate.approve(p, p.model.spec, a["id"])
    assert t["state"] == "ran" and not t.get("fenced") and ran(tmp_path) == ["push t1"]


def test_reshape_refused_at_compile(tmp_path):
    lines = ["name: t", "actions:",
             "  unknown:", "    run: x", "    gate:", "      normal: auto", "      away: {reshape: nope}",
             "  extra:", "    run: x", "    gate:", "      away: {reshape: titled}",
             "  chain:", "    run: x", "    gate:", "      away: {reshape: chained}",
             "  chained:", "    run: x", "    gate:", "      away: {reshape: plain}",
             "  combo:", "    run: x", "    gate:", "      normal: {reshape: named}",
             "  named:", "    run: x", "    gate:", "      maintenance: {reshape: plain}",
             "  selfish:", "    run: x", "    gate:", "      freeze: {reshape: selfish}",
             "  titled:", "    run: x {title}", "    args: {title: its title}",
             "  plain:", "    run: x",
             "  ok:", "    run: x {title}", "    args: {title: t}", "    gate: {away: {reshape: plain}}",
             "  bent:", "    run: x", "    gate: {away: {reshape: plain, extra: 1}}"]
    (tmp_path / "ergostat.yaml").write_text("\n".join(lines) + "\n")
    compiled, problems = spec_mod.read(tmp_path / "ergostat.yaml")
    errs = [x for x in problems if x.level == "error"]
    want = {"unknown": 7, "extra": 11, "chain": 15, "combo": 23, "selfish": 31}
    for name, line in want.items():
        hit = [x for x in errs if f"action {name}." in x.message]
        assert len(hit) == 1 and hit[0].code == "bad-reshape" and hit[0].where.line == line, (name, hit)
        assert not compiled.actions[name].reshapes                  # refused: a plain approve cell
    assert "maintenance" in [x for x in errs if "action combo." in x.message][0].message
    bent = [x for x in errs if "action bent." in x.message]
    assert len(bent) == 1 and bent[0].code == "bad-value"
    assert len(errs) == 6, [x.message for x in errs]
    assert compiled.actions["chained"].reshapes == {"away": "plain"}     # a target may reshape when no chain reaches it
    assert compiled.actions["ok"].reshapes == {"away": "plain"} and compiled.actions["ok"].gates["away"] == "approve"
    assert compiled.actions["unknown"].gates["away"] == "approve"
