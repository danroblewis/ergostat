"""A block only its daemon runs (a collector) is not "never ran" on the Agents page: its daemon is what it does."""

from __future__ import annotations

import time
from pathlib import Path

from ergostat import model as mdl
from ergostat.store import Project

YAML = """name: feeds
daemons:
  ec2-feed:
    run: python3 -c "import time; time.sleep(60)"
blocks:
  ec2-feed:
    type: program
    daemon: ec2-feed
    description: the ec2 fleet's events
  sweep:
    type: program
    run: "true"
    every: 5m
"""


def test_a_collector_is_described_by_its_daemon_not_by_runs(tmp_path: Path, monkeypatch):
    from ergostat.web import server
    monkeypatch.setattr(server, "_estimates", lambda *a, **k: None)
    (tmp_path / "ergostat.yaml").write_text(YAML)
    p = Project(mdl.load(tmp_path / "ergostat.yaml"))
    live = server.Live(p)
    q = {"at": [str(time.time())]}
    agents = server.api(live, "agents", q)
    assert agents["ec2-feed"]["collects"]["name"] == "ec2-feed"
    assert "collects" not in agents["sweep"]                     # a scheduled block is judged by its runs
    one = server.api(live, "agents/ec2-feed", q)
    assert one["collects"]["name"] == "ec2-feed"
