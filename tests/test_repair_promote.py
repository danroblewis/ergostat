"""Promotion down the ladder for ``apply-fix`` (SPEC §12r, ``promote: true``): the rung a block's fix is answered at is
worked out from the record each time a fix is tested (never stored), one rung down per 10 clean answers at the rung, by
seq, and back to the owner's rung on a regressed or reverted fix or a denial; re-read under the failure's lock."""

import pytest

from ergostat.actions import gate
from ergostat.actions import record as actions
from ergostat.repair import approve, fix, promote
from tests.test_repair2 import project
from tests.test_repair_approver import approvals, opened, reviews, run_fix

BLOCK = "collector"


def owner(approver="person", approve_with=None):
    return type("A", (), {"model": "haiku", "budget": 0.25, "daily": 2.0, "timeout": 40.0, "approver": approver,
                          "approve_with": approve_with})


def history(p, n: int, by="owner", at=None, first=0) -> list[int]:
    """``n`` apply-fix actions of the collector's failures (ids ``first`` on), approved by ``by`` and run, in this
    order by seq; each written at ``at`` when given. Returns the seqs of their answers."""
    seqs = []
    for i in range(first, first + n):
        fid, t = f"ergostat.failure/{BLOCK}-{i:08x}", at if at is not None else 1_000_000.0 + i
        aid = actions.new_id("apply-fix")
        req = {"action": "apply-fix", "item": fid, "block": BLOCK, "key": f"{BLOCK}-{i:08x}-{i:040x}"}
        p.events.add("ergostat.action.requested", item=aid, source="repair-fix", data=req, at=t)
        seqs.append(p.events.add("ergostat.action.approved", item=aid, source="owner",
                                 data={"approved_by": by}, at=t)["seq"])
        p.events.add("ergostat.action.ran", item=aid, source="ergostat", data={"exit": 0}, at=t)
    return seqs


def regress(p, i: int, at: float, what="regressed") -> int:
    return p.events.add(f"ergostat.failure.{what}", item=f"ergostat.failure/{BLOCK}-{i:08x}", source="ergostat",
                        data={}, at=at)["seq"]


def promoted_run(p, monkeypatch, fid, approver="person", promote_=True):
    real = fix.main
    monkeypatch.setattr(fix, "main", lambda argv: real([*argv, *(["--promote"] if promote_ else [])]))
    it = run_fix(p, monkeypatch, fid, approver=approver)
    return it, p.events.query(n=None, item=fid, type="ergostat.failure.reviewed"), actions.about(p, fid)[0]


def test_off_by_default(tmp_path, monkeypatch):
    on, e = project(tmp_path / "on", monkeypatch, approver="ai", with_=", promote: true")
    e.close()
    assert "--promote" in on.model.spec.blocks["repair-fix"].params["run"].split()
    p, fid = opened(tmp_path, monkeypatch)
    assert "--promote" not in p.model.spec.blocks["repair-fix"].params["run"]
    history(p, 10)
    assert promote.read(p, owner(), BLOCK)["rung"] == "ai", "earned, were it on"
    _, got, a = promoted_run(p, monkeypatch, fid, promote_=False)
    assert not got and not reviews(tmp_path) and a["state"] == "requested" and not approvals(p, a["id"])


@pytest.mark.parametrize("n", [9, 10])
def test_ten_clean_moves_one_rung(tmp_path, monkeypatch, n):
    p, fid = opened(tmp_path, monkeypatch)
    seqs = history(p, n)
    _, got, a = promoted_run(p, monkeypatch, fid)
    if n == 9:
        assert not got and not reviews(tmp_path) and a["state"] == "requested", "the person still answers"
        return
    ap = got[-1]["data"]["approval"]
    assert ap["verdict"] == "approve" and ap["by"] == "ai approver (haiku)" and ap["rung"] == "ai", ap
    assert ap["rung_earned"] == seqs and a["approved_by"] == "ai approver (haiku)"
    assert len(reviews(tmp_path)) == 1
    later = history(p, 10, by="ai approver (haiku)", first=100)     # the ai rung earns its own step down
    assert promote.read(p, owner(), BLOCK) == {"rung": "rule", "earned": later, "newest": p.events.query(n=None)[-1]["seq"]}
    assert promote.read(p, owner(approve_with="./ok.sh"), BLOCK)["rung"] == "program"
    history(p, 10, by="rule approver", first=200)
    assert promote.read(p, owner(), BLOCK)["rung"] == "rule", "never below the rule"
    assert promote.read(p, owner("ai"), BLOCK)["rung"] == "rule" and promote.read(p, owner("rule"), BLOCK)["rung"] == "rule"


@pytest.mark.parametrize("what", ["regressed", "reverted"])
def test_regressed_resets_to_owner_rung(tmp_path, monkeypatch, what):
    """By seq the regression comes after the first 10 and before the next; its ``at`` is the oldest of all and the next
    10 are written older still, so ordering by ``at`` would decide the other way at each step."""
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 10, at=5.0)
    assert promote.read(p, owner(), BLOCK)["rung"] == "ai"
    regress(p, 3, at=1.0, what=what)
    assert promote.read(p, owner(), BLOCK) == {"rung": "person", "earned": None,
                                               "newest": p.events.query(n=None)[-1]["seq"]}
    again = history(p, 9, at=0.5)                       # the same failure ids made again: their old answers don't count
    assert promote.read(p, owner(), BLOCK)["rung"] == "person"
    again += history(p, 1, at=0.5, first=9)
    assert promote.read(p, owner(), BLOCK) == {"rung": "ai", "earned": again,
                                               "newest": p.events.query(n=None)[-1]["seq"]}
    _, got, a = promoted_run(p, monkeypatch, fid)
    assert got[-1]["data"]["approval"]["rung_earned"] == again and a["state"] == "approved"


def test_agent_answers_never_promote(tmp_path, monkeypatch):
    """An agent's approvals through the MCP (``owner via mcp``), or the gate's own, are no person's evidence: 10 of them
    leave the person answering, and they neither count nor break the person's own run of 10."""
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 10, by="owner via mcp")
    history(p, 5, by=gate.GATE, first=10)
    assert promote.read(p, owner(), BLOCK)["rung"] == "person"
    _, got, a = promoted_run(p, monkeypatch, fid)
    assert not got and not reviews(tmp_path) and a["state"] == "requested", "the person still answers"
    mine = history(p, 9, by="a@b.example", first=20) + history(p, 1, first=29)
    assert promote.read(p, owner(), BLOCK)["earned"] == mine


def test_a_denial_resets_too(tmp_path, monkeypatch):
    p, _ = opened(tmp_path, monkeypatch)
    history(p, 10)
    other = actions.new_id("apply-fix")
    p.events.add("ergostat.action.requested", item=other, source="repair-fix",
                 data={"action": "apply-fix", "item": f"ergostat.failure/{BLOCK}-0000ffff", "block": BLOCK})
    gate.deny(p, other, by="owner", note="not this one")
    assert promote.read(p, owner(), BLOCK)["rung"] == "person"


@pytest.mark.parametrize("which", ["another-fix", "this-fix"])
def test_denial_in_the_gap_holds(tmp_path, monkeypatch, which):
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 10)
    other = actions.new_id("apply-fix")
    p.events.add("ergostat.action.requested", item=other, source="repair-fix",
                 data={"action": "apply-fix", "item": f"ergostat.failure/{BLOCK}-0000ffff", "block": BLOCK})
    real = approve.ai

    def denied_in_between(p_, a, fid_, asked):          # the rung worked out and the AI approved; then a person denies
        got = real(p_, a, fid_, asked)
        assert got[0] == "approve"
        gate.deny(p, other if which == "another-fix" else actions.about(p, fid)[0]["id"], by="owner", note="no")
        return got
    monkeypatch.setitem(approve.RUNGS, "ai", denied_in_between)
    _, got, a = promoted_run(p, monkeypatch, fid)
    ap = got[-1]["data"]["approval"]
    assert ap["verdict"] == "stale" and ap["rung"] == "ai", ap
    assert a["state"] == ("requested" if which == "another-fix" else "denied") and not approvals(p, a["id"])
    assert gate.sweep(p, p.model.spec) == 0


def test_unreadable_record_owner_rung(tmp_path, monkeypatch):
    """The owner's rung is ai: with 10 clean ai answers the block would be at the rule; the record raises, so the AI
    answers (never a lower rung)."""
    p, fid = opened(tmp_path, monkeypatch)
    history(p, 10, by="ai approver (haiku)")
    assert promote.read(p, owner("ai"), BLOCK)["rung"] == "rule"
    real = p.events.query

    def broken_record(*a, **k):
        if k.get("type") == "ergostat.action.*":
            raise OSError("the record cannot be read")
        return real(*a, **k)
    monkeypatch.setattr(p.events, "query", broken_record)
    got = promote.read(p, owner("ai"), BLOCK)
    assert got["rung"] == "ai" and "cannot be read" in got["why"]
    assert promote.read(p, owner(), BLOCK)["rung"] == "person"
    _, got, a = promoted_run(p, monkeypatch, fid, approver="ai")
    ap = got[-1]["data"]["approval"]
    assert ap["by"] == "ai approver (haiku)" and ap["rung"] == "ai" and ap["rung_earned"] is None
    assert len(reviews(tmp_path)) == 1
