"""Each goal's state says its system and, for a goal one of the owner's upkeep templates made (``use: modelling``),
``upkeep``; ``state.goals_off`` is the one count of goals off, the modelling system's own set beside it (SPEC §8)."""

import json

from ergostat import model as mdl
from ergostat import projects, state
from ergostat.store import Project

MODEL = """name: small
uses:
  modelling:
    use: modelling
  upkeep:
    use: upkeep
systems:
  shop: {}
stocks:
  queue:
    unit: jobs
    system: shop
    sensor: {run: echo 1, every: 1m}
flows:
  served: {from: queue, system: shop}
goals:
  queue-short: {stock: queue, hold: "<= 5", system: shop}
blocks:
  keep-short: {type: onoff, goal: queue-short, out: block.worker, system: shop}
  worker: {type: program, run: "true", in: block.keep-short, out: flow.served, system: shop}
"""


def seeded(tmp_path, monkeypatch):
    """The small model with every goal its sensors read pushed far past its setpoint: off, each one."""
    monkeypatch.setenv("ERGOSTAT_HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ergostat.yaml").write_text(MODEL)
    p = Project(mdl.load(repo / "ergostat.yaml"))
    for lp in p.model.loops():
        op, _ = lp.controller.target()
        for s in lp.sensors:
            p.measurements.add(f"sensor/{s}", 1e6 if op in ("<=", "<") else -1e6)
    (p.dir / "repo.json").write_text(json.dumps({"repo": str(repo)}))
    return p


def test_a_goals_state_says_its_system_and_whether_it_is_modellings_own(tmp_path, monkeypatch):
    p = seeded(tmp_path, monkeypatch)
    snap = state.snapshot(p)
    loops = snap["loops"]
    assert loops["requests-handled"]["upkeep"] == "modelling" and loops["model-fits"]["upkeep"] == "modelling"
    assert loops["requests-handled"]["status"] == loops["model-fits"]["status"] == "off"
    assert "upkeep" not in loops["queue-short"] and loops["queue-short"]["status"] == "off"
    assert all(lp["system"] for lp in loops.values()), {n: lp["system"] for n, lp in loops.items()}
    assert loops["requests-handled"]["system"] == "modelling"
    made = {n for n, g in p.model.spec.goals.items() if getattr(g.where, "instance", None) == "upkeep"}
    upkeep_off = sorted(n for n in made if loops[n]["status"] == "off")
    assert upkeep_off and not any("upkeep" in loops[n] for n in made)     # the upkeep template's goals stay the system's
    got = state.goals_off(snap)
    assert got["own"] == {"modelling": 2}
    names = state.goals_off(snap, names=True)
    assert set(upkeep_off) | {"queue-short"} <= set(names["system"])
    assert got["system"] == len(names["system"]) and "requests-handled" not in names["system"]

    (row,) = projects.known(fresh=True)
    assert row["upkeep_off"] == ["model-fits", "requests-handled"]
    assert not set(row["upkeep_off"]) & set(row["off"]) and "queue-short" in row["off"]
