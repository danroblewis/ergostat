"""A collector (a block only its daemon runs) is not asked for an output flow, and ergostat's built-in session
projection is never a model's waiting finding: neither is the owner's to answer."""

from __future__ import annotations

from pathlib import Path

from ergostat import model as mdl
from ergostat.spec import waits
from ergostat.spec.ir import SESSION

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
    description: sweeps
"""


def test_a_collector_has_no_no_visible_effect_finding_but_a_scheduled_block_does(tmp_path: Path):
    (tmp_path / "ergostat.yaml").write_text(YAML)
    m = mdl.load(tmp_path)
    nve = {x.about for x in m.problems if getattr(x, "code", "") == "no-visible-effect"}
    assert "block.ec2-feed" not in nve
    assert "block.sweep" in nve


def test_the_built_in_session_projection_is_never_a_waiting_finding(tmp_path: Path):
    (tmp_path / "ergostat.yaml").write_text(YAML)
    m = mdl.load(tmp_path)
    assert SESSION in m.spec.items
    assert all(k.name != SESSION for k, _ in waits.unexplained(m.spec))
