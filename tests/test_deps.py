"""A gap waiting on an unfinished dependency says which and why (dev/bin/deps.py plan(), dev/bin/watch.py;
docs/roadmap/overnight/a-gap-waiting-on-an-unfinished.md)."""

from __future__ import annotations

import sys

from tests.test_factory import fac_module, module
from tests.test_factory_manager import H, Pipe


def gaps_in(**states) -> dict[str, dict]:
    return {f"gap/{g}": {"id": f"gap/{g}", "state": s, "fields": {"branch": g}} for g, s in states.items()}


def planned(tmp_path, monkeypatch, gaps, merged=frozenset(), landed=frozenset()):
    fac_module(tmp_path, monkeypatch)
    sys.modules["fac"] = module("fac")
    deps = module("deps")
    gaps["gap/top"]["fields"]["depends_on"] = sorted(g for g in gaps if g != "gap/top")
    return deps, deps.plan(gaps, {}, {}, set(merged), set(landed))


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
    gaps = gaps_in(top="ready", carried="ready", other="building", fresh="parked", started="building")
    merged = {"factory/carried", "factory/fresh", "factory/started", "main"}  # fresh, started: at main, no own commits
    _, want = planned(tmp_path, monkeypatch, gaps, merged, {"carried", "top"})   # definitions in main's tree
    why = want["gap/top"]["blocked_reason"]
    assert "waits on gap/carried (ready): landed, not closed" in why
    assert "waits on gap/other, which is building" in why and "other (building): landed" not in why
    assert "waits on gap/fresh, which is parked: stopped" in why and "fresh (parked): landed" not in why
    assert "waits on gap/started, which is building" in why and "started (building): landed" not in why
    assert why.count("landed, not closed") == 1
    _, want = planned(tmp_path, monkeypatch, gaps_in(top="ready", carried="ready"), set(), {"carried"})
    assert "landed" not in want["gap/top"]["blocked_reason"]                  # its definition alone on main: not landed
    f = Pipe(tmp_path / "pipe")                                               # the situation the manager is raised with
    moves = [{"time": f.now - 9 * H, "from": "open", "to": "ready"}]
    f.put("gap/carried", "ready", branch="carried", moves=moves, entered=9 * H)
    f.put("gap/top", "ready", branch="top", moves=moves, entered=9 * H, depends_on=["gap/carried"],
          blocked_reason=why)
    sit = f.watch()
    got = [t["why"] for t in sit["triggers"] if t["trigger"] == "stuck" and t["subject"] == "gap/top"]
    assert len(got) == 1 and "landed, not closed" in got[0]                  # not explained away as a dependency wait


def test_the_intake_refuses_a_dependency_on_an_ancestor_and_records_the_problem(tmp_path, monkeypatch):
    """A sub-gap depending on its own split parent (or the parent's parent), named on the item or in its definition
    file, is refused: a dependency_problem, never written to depends_on; a sibling stays a dependency."""
    gaps = gaps_in(top="ready", kid="ready", grand="ready", sib="ready")
    gaps["gap/kid"]["fields"].update(parent=["gap/top"], depends_on=["gap/top", "gap/sib"])
    gaps["gap/top"]["fields"]["parent"] = "gap/grand"
    fac_module(tmp_path, monkeypatch)
    sys.modules["fac"] = module("fac")
    deps = module("deps")
    want = deps.plan(gaps, {"gap/kid": [("grand", "dev/records/kid.md")]}, {})
    assert want["gap/kid"]["depends_on"] == ["gap/sib"]
    got = want["gap/kid"]["problems"]
    assert any("gap/top" in p and "its own ancestor" in p for p in got), got
    assert any("gap/grand" in p and "dev/records/kid.md" in p and "its own ancestor" in p for p in got), got
    said = dict(deps.changes(gaps, want))["gap/kid"]
    assert said["dependency_problem"] is True and said["depends_on"] == {"set": ["gap/sib"]}
    gaps["gap/top"]["fields"]["parent"] = "gap/kid"                            # a loop of parents ends
    assert deps.ancestors(gaps, "gap/kid") == {"gap/top"}
