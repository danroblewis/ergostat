"""Listing the projects on this machine (``ergostat projects``) is read only: it never writes
another project's repo.json, nor touches its record's files."""

import json

from ergostat import model as mdl
from ergostat import projects
from ergostat.store import Project


def test_listing_projects_writes_nothing_into_their_state_folders(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ergostat.yaml").write_text("name: alpha\nstocks:\n  q:\n    unit: x\n    sensor: {run: echo 1, every: 1m}\n")
    p = Project(mdl.load(repo / "ergostat.yaml"))
    p.events.count()
    note = p.dir / "repo.json"
    older = json.dumps({"repo": str(repo)})                 # a note from before, or the model renamed since
    note.write_text(older)
    watched = [note, *(f for f in p.dir.rglob("*") if f.is_file() and f.suffix in (".json", ".jsonl"))]
    before = {f: (f.stat().st_mtime_ns, f.read_bytes()) for f in watched}
    rows = projects.known(fresh=True)
    assert [r["name"] for r in rows] == ["alpha"] and rows[0]["repo"] == str(repo)
    assert note.read_text() == older
    assert {f: (f.stat().st_mtime_ns, f.read_bytes()) for f in watched} == before


def test_the_switcher_counts_the_systems_goals_and_the_models_upkeep_apart(tmp_path, monkeypatch):
    """Q14, the switcher's row as the header counts it: with only the modelling use's own two goals off, no goal of the
    system is off, and those two are the model's upkeep (state.goals_off, the one count both read)."""
    import shutil
    import time
    from pathlib import Path

    from ergostat import state as st

    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    d = tmp_path / "first-loop"
    shutil.copytree(Path(__file__).resolve().parent.parent / "examples" / "first-loop", d)
    p = Project(mdl.load(d / "ergostat.yaml"))
    for stock, value in (("inbox", 10), ("model-error", 0.5), ("unanswered-requests", 3)):    # inbox-short holds
        s = next(iter(p.model.spec.stocks[stock].sensors.values()))
        p.measurements.add(s.series, value, at=time.time())
    (row,) = projects.known(fresh=True)
    assert row["goals_off"] == [] and row["upkeep_off"] == ["model-fits", "requests-handled"], row
    assert row["unknown"] == [], row
    g = st.goals_off(st.snapshot(p))                     # what /api/status gives the header
    assert g["system"] == len(row["goals_off"]) == 0 and sum(g["own"].values()) == 2, g
