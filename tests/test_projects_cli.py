"""``ergostat projects`` lists every project on this machine, stopped ones too, with the rows ``projects.known`` gives.
(The page has no project list: it knows one project, the one it serves.)"""

import fcntl
import json
import os

from ergostat import model as mdl
from ergostat import projects
from ergostat.store import Project

MODEL = "name: {name}\nstocks:\n  q:\n    unit: x\n    sensor: {{run: echo 1, every: 1m}}\n"


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


def test_the_cli_lists_running_and_stopped_projects_with_the_same_rows(tmp_path, capsys):
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
