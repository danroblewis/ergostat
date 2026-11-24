"""The pipeline manager's broken situations (dev/bin/watch.py): a queue held off by the load interlock names the
readings that hold it, on the fixture of tests/test_factory_manager.py."""

from __future__ import annotations

import json

import pytest

from tests.test_factory_manager import H, Pipe, queue_json

CODE = """import time, watch
watch.load.reading = lambda w: {READINGS}.get(w, 0)
cfg = watch.fac.config()
cfg['load']['wait'] = True
now = time.time()
gaps = {g['id']: g for g in watch.fac.items('gap')}
watch.broken(cfg, gaps, [], now)
got = watch.raise_one(cfg, now + 3600)
print(json.dumps((got or {}).get('broken', {}).get('interlock', {}).get('why')))"""


def held_by(f: Pipe, readings: dict) -> str | None:
    """The interlock's text in the broken situation raised an hour after it began (past broken_minutes)."""
    return f.py(CODE.replace("{READINGS}", json.dumps(readings)))


@pytest.mark.slow
def test_a_broken_situation_names_the_interlock_reading_that_holds_the_queue(tmp_path):
    f = Pipe(tmp_path)
    f.put("gap/a", "approved", approved_at=f.now - 2 * H)
    assert held_by(f, {"suites": 6}) is None    # at the hold: nothing holds the queue, no interlock condition
    why = held_by(f, {"suites": 8})
    assert "suites-running 8 over 6" in why and "1 gaps wait" in why, why
    assert not any(w in why for w in ("threads", "memory", "push-waiting")), why
    for reading, said in (("threads", "threads 3500 over 3000"), ("memory", "memory 41 over 40")):
        why = held_by(f, {reading: float(said.split()[1])})
        assert said in why and "suites-running" not in why, why
    queue_json(f, blocked={"why": "push failed", "intervention": "intervention/q", "at": f.now - 2 * H})
    why = held_by(f, {})                       # (the push-waiting sensor's own reading: queue.py waiting)
    assert "push-waiting 1" in why and "suites-running" not in why, why
