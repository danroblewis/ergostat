"""Listing the projects on this machine (``ergostat projects``, the page's header) is read only: it never writes
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
