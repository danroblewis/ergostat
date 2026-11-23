"""Invariant 12 (CLAUDE.md): ergostat adds nothing of its own accord, so an empty install runs nothing. The engine is
started on a model with no parts and left for a few of its passes: no block runs, no sensor reads, no item is made,
and the record holds only ergostat's own start events."""

import time

from ergostat import model as mdl
from ergostat.spec.engine import Engine
from ergostat.store import Project

# What ergostat itself writes when it starts on a model: an allowlist, so any other event an empty start records (a
# default block's run, a sensor's reading, an item) fails the test.
START_EVENTS = {"ergostat.started"}


def _passes(e: Engine, n: int, deadline: float) -> int:
    """Wait for the engine's loop to finish ``n`` passes (one a tick at least), or the deadline: the passes seen."""
    seen, last = 0, e.passed_at
    while seen < n and time.monotonic() < deadline:
        time.sleep(0.05)
        if e.passed_at != last:
            seen, last = seen + 1, e.passed_at
    return seen


def test_an_empty_install_runs_nothing(tmp_path):
    (tmp_path / "ergostat.yaml").write_text("name: empty\n")
    p = Project(mdl.load(tmp_path))
    spec = p.model.spec
    assert not (spec.blocks or spec.stocks or spec.flows or spec.auxiliaries or spec.goals or spec.agents), \
        "the empty model has no parts of its own"
    e = Engine(p, say=lambda s: None)
    e.start_all()
    try:
        assert _passes(e, 3, time.monotonic() + 20) == 3, "the engine's loop passed a few times"
        assert not e.machines and not e.builtins and not e.running and not e.procs and not e.reading
        running = p.events.query(n=None)                         # the record while it runs, before its stop event
    finally:
        e.close()
    assert not [x for x in running if x["type"] == "agent.started"], "no block ran"
    assert not p.measurements.newest(), "no sensor read"
    assert not p.events.items(), "no item was made"
    stray = [(x["type"], x.get("source")) for x in running if x["type"] not in START_EVENTS or x.get("source") != "ergostat"]
    assert not stray, f"the record holds only ergostat's own start events, not {stray}"
    assert [x["type"] for x in running].count("ergostat.started") == 1
    after = [(x["type"], x.get("source")) for x in p.events.query(n=None) if x["id"] not in {r["id"] for r in running}]
    assert after == [("ergostat.stopped", "ergostat")], "stopping adds only its own stop event"
