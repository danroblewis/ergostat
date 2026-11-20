"""The repair loop for real (SPEC §12r): the fixer and the AI approver on haiku through ``claude -p``, what it cost
printed. Skipped unless ``ERGOSTAT_LIVE_AI=1``: it spends money (at most the loop's daily cap, $1 here)."""

import json
import os

import pytest

from ergostat.actions import record as actions
from tests.test_repair2 import broken, fixed, git, one, project

pytestmark = pytest.mark.skipif(os.environ.get("ERGOSTAT_LIVE_AI") != "1", reason="spends money: ERGOSTAT_LIVE_AI=1")


def test_haiku_fixes_the_collector_and_the_ai_approver_answers_it(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, approver="ai", with_=", daily: 1, budget: 0.3")
    monkeypatch.delenv("ERGOSTAT_AI")
    root = p.model.path.parent
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
        f = it.fields
        runs = p.events.query(n=None, item="repair-fix", type="agent.*")
        spent = sum(float(((r.get("data") or {}).get("ai") or {}).get("cost_usd") or 0) for r in runs)
        ledger = [json.loads(x) for x in (p.dir / "repair" / "spend.jsonl").read_text().splitlines()]
        print(json.dumps({"state": it.state, "tests": f.get("tests"), "risk": f.get("risk"), "approval": f.get("approval"),
                          "explanation": f.get("explanation"), "run_cost_usd": round(spent, 4),
                          "ledger_usd": round(sum(r["usd"] for r in ledger), 4), "calls": len(ledger)}, indent=1))
        assert it.state == "awaiting-approval" and f["tests"] == "passed", f.get("test")
        assert spent > 0 and spent == pytest.approx(sum(r["usd"] for r in ledger), rel=0.01), "every call's cost measured"
        a = actions.about(p, fid)[0]
        if a["state"] == "approved":                      # the AI rung let it through: the engine's sweep applies it
            from ergostat.actions import gate
            gate.sweep(p, p.model.spec)
            assert one(p, fid).state == "applied" and git("rev-parse", "HEAD", cwd=root) == f["fix"]
        else:
            assert f["approval"]["verdict"] == "escalate" and a["state"] == "requested"
    finally:
        e.close()
