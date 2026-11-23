"""fac.items lists past the record's 500-item listing: each state on its own, joined."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "dev" / "bin"
if str(BIN) not in sys.path:
    sys.path.append(str(BIN))          # appended: dev/bin/queue.py must not shadow the standard lib

import fac  # noqa: E402


def record(monkeypatch, states: dict[str, int], cap: int = 500) -> None:
    def ergostat(*args):
        if "--json" not in args:
            counts = " · ".join(f"{s} {n}" for s, n in states.items())
            return subprocess.CompletedProcess(args, 0, f"other other/*  a 1\ngap gap/*  {counts}\n", "")
        st = args[args.index("--state") + 1] if "--state" in args else None
        ids = [f"gap/{s}-{i}" for s, n in states.items() if st in (None, s) for i in range(n)]
        out = {"items": [{"id": i, "state": i.split("/")[1].rsplit("-", 1)[0]} for i in ids[:cap]], "total": len(ids)}
        return subprocess.CompletedProcess(args, 0, json.dumps(out), "")

    monkeypatch.setattr(fac, "ergostat", ergostat)


def test_every_state_is_listed_past_the_cap(monkeypatch):
    record(monkeypatch, {"merged": 400, "in-review": 200, "ready": 100})
    got = fac.items("gap")
    assert len(got) == 700 and len({x["id"] for x in got}) == 700


def test_a_state_counted_empty_is_not_listed(monkeypatch):
    record(monkeypatch, {"merged": 2, "in-review": 0, "ready": 1, "parked": 0})
    calls = []
    inner = fac.ergostat
    monkeypatch.setattr(fac, "ergostat", lambda *a: calls.append(a) or inner(*a))
    assert {x["id"] for x in fac.items("gap")} == {"gap/merged-0", "gap/merged-1", "gap/ready-0"}
    assert [a[a.index("--state") + 1] for a in calls if "--state" in a] == ["merged", "ready"]
    calls.clear()
    record(monkeypatch, {"merged": 0, "ready": 0})
    inner = fac.ergostat
    monkeypatch.setattr(fac, "ergostat", lambda *a: calls.append(a) or inner(*a))
    assert fac.items("gap") == [] and len(calls) == 1        # every state empty: the kind's line only


def test_one_state_is_one_listing(monkeypatch):
    record(monkeypatch, {"merged": 3, "ready": 2})
    assert {x["id"] for x in fac.items("gap", "ready")} == {"gap/ready-0", "gap/ready-1"}


def test_a_state_past_the_cap_is_said(monkeypatch, capsys):
    record(monkeypatch, {"merged": 501})
    assert len(fac.items("gap")) == 500
    assert "501 items" in capsys.readouterr().err


def ledger(tmp_path, monkeypatch, *lines) -> dict:
    (tmp_path / "costs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    monkeypatch.setattr(fac, "run_dir", lambda cfg, *a: tmp_path)
    return {}


def test_a_settled_session_costs_what_it_spent(tmp_path, monkeypatch):
    now = time.time()
    cfg = ledger(tmp_path, monkeypatch, {"at": now - 60, "usd": 15, "kind": "reserved", "run": "a"},
                 {"at": now - 30, "usd": -13, "kind": "settled", "run": "a"})
    assert fac.spent_today(cfg) == 2


def test_a_running_session_holds_its_reservation(tmp_path, monkeypatch):
    cfg = ledger(tmp_path, monkeypatch, {"at": time.time() - 60, "usd": 15, "kind": "reserved", "run": "a"})
    assert fac.spent_today(cfg) == 15


def test_a_dead_runs_reservation_is_charged_as_a_typical_session(tmp_path, monkeypatch):
    now = time.time()
    cfg = ledger(tmp_path, monkeypatch, {"at": now - 90, "usd": 15, "kind": "reserved", "run": "a"},
                 {"at": now - 80, "usd": -13, "kind": "settled", "spent": 2, "run": "a"},
                 {"at": now - 60, "usd": 15, "kind": "reserved", "run": "dead"})
    monkeypatch.setattr(fac, "run_alive", lambda c, run: False)
    assert fac.spent_today(cfg) == 2 + 4


def test_a_live_runs_reservation_is_held_in_full(tmp_path, monkeypatch):
    now = time.time()
    cfg = ledger(tmp_path, monkeypatch, {"at": now - 90, "usd": 15, "kind": "reserved", "run": "a"},
                 {"at": now - 80, "usd": -13, "kind": "settled", "spent": 2, "run": "a"},
                 {"at": now - 60, "usd": 15, "kind": "reserved", "run": "live"})
    monkeypatch.setattr(fac, "run_alive", lambda c, run: True)
    assert fac.spent_today(cfg) == 2 + 15


def test_a_run_whose_record_is_gone_has_ended_and_an_unreadable_one_counts_as_alive(tmp_path, monkeypatch):
    import live
    monkeypatch.setattr(live, "state_dir", lambda cfg: tmp_path)
    (tmp_path / "runs").mkdir()
    assert not fac.run_alive({}, "gone")
    (tmp_path / "runs" / "broken.json").write_text("not json")
    assert fac.run_alive({}, "broken")
