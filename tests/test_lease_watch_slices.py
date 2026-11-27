"""Many overdue leases do not delay a take (event-log-indexes-what-it-is-asked, done item 4): the watchdog reads each
overdue lease's activity in slices of ``SLICE`` seconds, so the dispatcher takes work for another block between them;
and a round cut into slices still looks at every lease, keeping each one's first look."""

import textwrap
import time

from ergostat import model as mdl
from ergostat.leases import TAKEN, dispatch
from ergostat.leases.dispatch import Dispatcher
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """
name: t
projections:
  ticket:
    fields: {state: {values: [ready, doing, done]}}
  job:
    fields: {state: {values: [ready, done]}}
    events:
      done: {when: "type == 'job.done'", '...': data, state: "'done'"}
      other: {when: true, '...': data}
blocks:
  worker:
    type: program
    takes: {projection: ticket, at: ready}
    pool: 2
    run: "true"
    lease: {ttl: 1m}
  other:
    type: program
    takes: {projection: job, at: ready}
    pool: 2
    run: 'echo "{\\\\"event\\\\": \\\\"job.done\\\\"}"'
    lease: {ttl: 1m}
"""


def held(p, n: int) -> None:
    """``n`` tickets, each held by a lease of another engine's run (one this engine cannot tell is gone), long overdue."""
    at = time.time() - 3600
    for i in range(n):
        p.events.add("ticket.opened", item=f"ticket/{i}", source="t", at=at)
        p.events.add(TAKEN, item=f"ticket/{i}", source="ergostat", at=at,
                     data={"run": f"r{i}", "block": "elsewhere", "fence": 1, "ttl": 60.0, "max": 3, "back": "ready"})


