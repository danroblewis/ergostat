"""fac.items lists past the record's 500-item listing: each state on its own, joined."""

from __future__ import annotations

import json
import subprocess
import sys
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


def test_one_state_is_one_listing(monkeypatch):
    record(monkeypatch, {"merged": 3, "ready": 2})
    assert {x["id"] for x in fac.items("gap", "ready")} == {"gap/ready-0", "gap/ready-1"}


def test_a_state_past_the_cap_is_said(monkeypatch, capsys):
    record(monkeypatch, {"merged": 501})
    assert len(fac.items("gap")) == 500
    assert "501 items" in capsys.readouterr().err
