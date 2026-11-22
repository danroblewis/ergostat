"""The header's project list (/api/projects) holds the running projects only, worked out off the request path; the
CLI's list (``ergostat projects``) still has every project, stopped ones too."""

import fcntl
import json
import logging
import os
import threading
import time
import urllib.request

import pytest

from ergostat import model as mdl
from ergostat import projects
from ergostat import state as st
from ergostat.store import Project, home
from ergostat.web import server as srv
from tests.ports import free_port

MODEL = "name: {name}\nstocks:\n  q:\n    unit: x\n    sensor: {{run: echo 1, every: 1m}}\n"


@pytest.fixture(autouse=True)
def no_lister_running():
    """A lister left by another test's page server (one per process) would run passes inside these tests' counts: it
    is stopped and waited for before each test, and after."""
    assert srv.stop_lister(None)
    yield
    assert srv.stop_lister(None)


def _project(tmp_path, name: str, running: bool, held: list) -> Project:
    repo = tmp_path / name
    repo.mkdir()
    (repo / "ergostat.yaml").write_text(MODEL.format(name=name))
    p = Project(mdl.load(repo / "ergostat.yaml"))
    p.events.count()
    if running:                                   # an engine there: run.pid locked with its pid, and its page
        f = open(p.dir / "run.pid", "w")
        f.write(str(os.getpid()))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_EX)
        held.append(f)
        (p.dir / "web.json").write_text(json.dumps({"url": f"http://127.0.0.1:1/{name}"}))
    return p


def _stopped_folders(n: int, tmp_path) -> None:
    for i in range(n):                            # folders whose repository is gone, as most on a long-used machine
        d = home() / f"gone-{i:04d}"
        d.mkdir(parents=True)
        (d / "repo.json").write_text(json.dumps({"repo": str(tmp_path / "nowhere" / str(i))}))


def _counting(monkeypatch) -> dict:
    n = {"load": 0, "snapshot": 0}
    load, snapshot = mdl.load, st.snapshot

    def counted_load(*a, **k):
        n["load"] += 1
        return load(*a, **k)

    def counted_snapshot(*a, **k):
        n["snapshot"] += 1
        return snapshot(*a, **k)
    monkeypatch.setattr(mdl, "load", counted_load)
    monkeypatch.setattr(st, "snapshot", counted_snapshot)
    return n


def test_with_2000_stopped_folders_the_header_list_is_cheap_and_holds_the_running_ones(tmp_path, monkeypatch):
    import ergostat.web as web
    from ergostat.web import serve
    held: list = []
    here = _project(tmp_path, "here", False, held)
    _project(tmp_path, "alpha", True, held)
    _project(tmp_path, "beta", True, held)
    _stopped_folders(2000, tmp_path)
    monkeypatch.setattr(web, "start_lister", lambda server: None)      # this test makes the passes itself
    monkeypatch.setattr(srv, "_LISTED", {"running": [], "stopped": None, "at": None})
    n = _counting(monkeypatch)
    server, url = serve(here, free_port())
    try:
        def get():
            t = time.monotonic()
            with urllib.request.urlopen(url + "/api/projects", timeout=10) as r:
                body = r.read()
            return time.monotonic() - t, body
        _, body = get()                                  # before the first pass: nothing yet, and stopped unknown
        assert json.loads(body) == {"running": [], "stopped": None, "at": None, "age": None}
        srv.list_once()                                  # one pass of the lister
        assert n["load"] == 2, n                         # the two running projects' models, no stopped one's
        n["load"] = n["snapshot"] = 0
        monkeypatch.setattr(projects, "RUNNING_FRESH", 0.0)
        srv.list_once()                                  # their files unchanged: models kept, snapshots taken again
        assert n == {"load": 0, "snapshot": 2}, n
        n["load"] = n["snapshot"] = 0
        took, body = get()
        assert n == {"load": 0, "snapshot": 0}           # nothing loaded or taken inside the request
        got = json.loads(body)
        assert took < 0.3 and len(body) < 20_000, (took, len(body))
        assert [r["name"] for r in got["running"]] == ["alpha", "beta"] and got["stopped"] == 2001
        assert got["running"][0]["web"] == "http://127.0.0.1:1/alpha" and got["running"][0]["off"] == []
        assert got["running"][0]["loops"] == 0 and got["at"] is not None and 0 <= got["age"] < 60
    finally:
        server.shutdown()
        server.server_close()
        for f in held:
            f.close()


def test_a_running_project_whose_model_cannot_load_is_listed_with_why(tmp_path):
    held: list = []
    p = _project(tmp_path, "broken", True, held)
    try:
        (tmp_path / "broken" / "ergostat.yaml").write_text("stocks: [not, a, mapping\n")
        projects._ROWS.pop(p.dir, None)
        got = projects.running()
        assert got["stopped"] == 0 and len(got["running"]) == 1, got
        row = got["running"][0]
        assert row["running"] is True and row["error"] and row["repo"] is None, row
    finally:
        for f in held:
            f.close()


def test_a_failed_pass_keeps_the_last_list_and_says_so(monkeypatch, caplog):
    monkeypatch.setattr(srv, "_LISTED", {"running": [{"name": "x"}], "stopped": 3, "at": 1.0})

    def broken():
        raise OSError("home unreadable")
    monkeypatch.setattr(projects, "running", broken)
    with caplog.at_level(logging.ERROR, logger="ergostat"):
        srv.list_once()
    assert srv._LISTED == {"running": [{"name": "x"}], "stopped": 3, "at": 1.0}
    assert "listing the running projects failed" in caplog.text and "home unreadable" in caplog.text
    assert srv._answer(None, "projects", {})["age"] > 1e9          # the answer says how old the list is


def test_a_pass_that_ends_after_the_stop_is_not_kept(monkeypatch):
    monkeypatch.setattr(srv, "_LISTED", {"running": [], "stopped": None, "at": None})
    stop = threading.Event()
    monkeypatch.setattr(projects, "running", lambda: (stop.set(), {"running": [], "stopped": 1, "at": 2.0})[1])
    srv.list_once(stop)
    assert srv._LISTED["at"] is None


def test_the_lister_stops_with_the_last_page_server(tmp_path, monkeypatch):
    from ergostat.web import serve
    monkeypatch.setattr(projects, "running", lambda: {"running": [], "stopped": 0, "at": 1.0})
    here = _project(tmp_path, "here", False, [])
    one, _ = serve(here, free_port())
    two, _ = serve(here, free_port())

    def listers():
        return [t for t in threading.enumerate() if t.name == "ergostat-projects" and t.is_alive()]
    try:
        assert len(listers()) == 1                       # one per process, however many pages
        one.shutdown()
        one.server_close()
        assert len(listers()) == 1                       # the other page still needs it
    finally:
        two.shutdown()
        two.server_close()
    assert listers() == [] and srv._LISTING["thread"] is None     # stopped and waited for: no pass after this


def test_the_cli_still_lists_stopped_projects_with_the_same_rows(tmp_path, monkeypatch, capsys):
    from ergostat.cli import main
    held: list = []
    _project(tmp_path, "alpha", True, held)
    _project(tmp_path, "beta", False, held)
    try:
        assert main(["projects", "--json"]) == 0
        rows = json.loads(capsys.readouterr().out)
        assert rows == projects.known(fresh=True)
        by = {r["name"]: r for r in rows}
        assert set(by) == {"alpha", "beta"}
        assert by["beta"]["running"] is False and by["beta"]["web"] is None and by["beta"]["loops"] == 0
        assert by["alpha"]["running"] is True and by["alpha"]["web"] == "http://127.0.0.1:1/alpha"
        assert main(["projects"]) == 0
        text = capsys.readouterr().out
        assert "beta" in text and "stopped" in text and "alpha" in text and "running" in text
    finally:
        for f in held:
            f.close()
