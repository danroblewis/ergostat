"""A gap waiting on an unfinished dependency says which and why (dev/bin/deps.py plan(), dev/bin/watch.py;
docs/roadmap/overnight/a-gap-waiting-on-an-unfinished.md)."""

from __future__ import annotations

import sys

from tests.test_factory import fac_module, module
from tests.test_factory_manager import H, Pipe


def gaps_in(**states) -> dict[str, dict]:
    return {f"gap/{g}": {"id": f"gap/{g}", "state": s, "fields": {"branch": g}} for g, s in states.items()}


def planned(tmp_path, monkeypatch, gaps, merged=frozenset()):
    fac_module(tmp_path, monkeypatch)
    sys.modules["fac"] = module("fac")
    deps = module("deps")
    gaps["gap/top"]["fields"]["depends_on"] = sorted(g for g in gaps if g != "gap/top")
    return deps, deps.plan(gaps, {}, {}, set(merged))


def test_a_gap_waiting_on_an_unfinished_dependency_names_it_and_its_state(tmp_path, monkeypatch):
    gaps = gaps_in(top="ready", building="building", review="in-review", parked="parked", done="merged", gone="closed")
    gaps["gap/parked"]["fields"]["where_it_stopped"] = "its lease raced"
    deps, want = planned(tmp_path, monkeypatch, gaps)
    why = want["gap/top"]["blocked_reason"]
    assert "waits on gap/building, which is building" in why
    assert "waits on gap/review, which is in-review" in why
    assert "waits on gap/parked, which is parked: its lease raced" in why
    assert "gap/done" not in why and "gap/gone" not in why                    # finished: no wait
    assert want["gap/top"]["waits_on_parked"]                                 # a parked one still holds the take
    said = dict(deps.changes(gaps, want))["gap/top"]
    assert said["blocked_reason"] == why and said["waits_on_parked"] is True
    gaps = gaps_in(top="ready", building="building")
    deps, want = planned(tmp_path, monkeypatch, gaps)
    assert want["gap/top"]["blocked_reason"] == "waits on gap/building, which is building"
    assert dict(deps.changes(gaps, want))["gap/top"]["waits_on_parked"] is None   # unfinished, not parked: no hold


def test_a_dependency_whose_branch_is_on_main_is_said_landed_not_closed(tmp_path, monkeypatch):
    gaps = gaps_in(top="ready", carried="ready", other="building")
    _, want = planned(tmp_path, monkeypatch, gaps, {"factory/carried", "main"})
    why = want["gap/top"]["blocked_reason"]
    assert "waits on gap/carried (ready): landed, not closed" in why
    assert "waits on gap/other, which is building" in why and "other (building): landed" not in why
    assert not want["gap/top"]["waits_on_parked"]
    f = Pipe(tmp_path / "pipe")                                               # the situation the manager is raised with
    moves = [{"time": f.now - 9 * H, "from": "open", "to": "ready"}]
    f.put("gap/carried", "ready", branch="carried", moves=moves, entered=9 * H)
    f.put("gap/top", "ready", branch="top", moves=moves, entered=9 * H, depends_on=["gap/carried"],
          blocked_reason=why)
    sit = f.watch()
    got = [t["why"] for t in sit["triggers"] if t["trigger"] == "stuck" and t["subject"] == "gap/top"]
    assert len(got) == 1 and "landed, not closed" in got[0]                  # not explained away as a dependency wait
