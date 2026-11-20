"""A synthetic record with a known truth, for the completion estimates (numbers/eta.py): tickets arrive (Poisson), a
`dev` block takes them from `new` (a pool, lognormal runs, a share failing and given back, counted), a person
reviews them (no block: a lognormal stay, a share sent back to `new`: rework), and a `merge` block takes them from
`merging` (a pool of one). Written as the engine writes it: lease events about each item, the work's own event
before an ack. The truth is its own simulation here, not ergostat's."""

from __future__ import annotations

import heapq
import math
import random
import textwrap
import uuid

from ergostat import model as mdl
from ergostat.store import Project

MODEL = """
items:
  ticket:
    id: ticket/*
    states: [new, review, merging, done]
    on: {ticket.opened: new, ticket.implemented: review, ticket.changes: new, ticket.approved: merging,
         ticket.merged: done}
    relations:
      blocked_by: ticket
messages:
  done: {ticket: [done]}
blocks:
  dev:
    type: program
    run: "true"
    takes: {kind: ticket, at: new}
    pool: {pool}
    lease: {attempts: 9, ttl: 4h}
  merge:
    type: program
    run: "true"
    takes: {kind: ticket, at: merging}
    pool: 1
    lease: {ttl: 4h}
"""


def project(tmp_path, pool: int = 3) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("{pool}", str(pool))))
    m = mdl.load(tmp_path)
    assert m.spec is not None
    return Project(m)


def lognormal(rnd, median: float, sigma: float) -> float:
    return median * math.exp(rnd.gauss(0.0, sigma))


def generate(p: Project, t0: float, hours: float, rate: float = 6.0, backlog: int = 30, pool: int = 3,
             dev: float = 1200.0, fail: float = 0.15, review: float = 1800.0, rework: float = 0.3, merge: float = 180.0,
             seed: int = 7, stop_arrivals: float | None = None, prefix: str = "") -> None:
    """``hours`` of record from ``t0``: ``backlog`` tickets at ``t0``, then ``rate`` an hour (until ``stop_arrivals``
    hours, when given)."""
    rnd = random.Random(seed)
    evs: list[dict] = []
    heap: list = []
    seq = [0]

    def at(t, *what):
        seq[0] += 1
        heapq.heappush(heap, (t, seq[0], *what))

    def add(t, type, item, data=None):
        evs.append({"at": t, "type": type, "item": item, "data": data or {}, "source": "synthetic"})

    queues = {"dev": [], "merge": []}
    busy = {"dev": 0, "merge": 0}
    cap = {"dev": pool, "merge": 1}
    fence: dict[str, int] = {}
    n = [0]

    def arrive(t):
        n[0] += 1
        i = f"ticket/{prefix}{n[0]}"
        add(t, "ticket.opened", i, {"title": f"ticket {n[0]}"})
        heapq.heappush(queues["dev"], (t, i))

    def dispatch(t):
        for b in ("dev", "merge"):
            while queues[b] and busy[b] < cap[b]:
                _, i = heapq.heappop(queues[b])
                busy[b] += 1
                fence[i] = fence.get(i, 0) + 1
                run = uuid.uuid4().hex
                back = "new" if b == "dev" else "merging"
                add(t, "ergostat.lease.taken", i, {"item": i, "run": run, "block": b, "fence": fence[i], "ttl": 3600,
                                                   "max": 9, "back": back, "tier": "program", "attempt": 1})
                d = lognormal(rnd, dev, 0.6) if b == "dev" else rnd.expovariate(1 / merge)
                at(t + d, "end", b, i, run)

    for _ in range(backlog):
        arrive(t0)
    if rate:
        at(t0 + rnd.expovariate(rate / 3600.0), "arrive")
    dispatch(t0)
    end = t0 + hours * 3600.0
    while heap:
        t, _, what, *rest = heapq.heappop(heap)
        if t > end:
            break
        if what == "arrive":
            arrive(t)
            if stop_arrivals is None or t < t0 + stop_arrivals * 3600.0:
                at(t + rnd.expovariate(rate / 3600.0), "arrive")
        elif what == "end":
            b, i, run = rest
            busy[b] -= 1
            if b == "dev" and rnd.random() < fail:
                add(t, "ergostat.lease.ended", i, {"run": run, "fence": fence[i], "how": "nack", "why": "exited 1",
                                                   "item": i, "state": "new", "terminal": False})
                heapq.heappush(queues["dev"], (t, i))
            else:
                to = "review" if b == "dev" else "done"
                add(t, "ticket.implemented" if b == "dev" else "ticket.merged", i)
                add(t, "ergostat.lease.ended", i, {"run": run, "fence": fence[i], "how": "ack", "item": i, "state": to,
                                                   "terminal": to == "done"})
                if b == "dev":
                    at(t + lognormal(rnd, review, 0.5), "reviewed", i)
        elif what == "reviewed":
            (i,) = rest
            if rnd.random() < rework:
                add(t, "ticket.changes", i)
                heapq.heappush(queues["dev"], (t, i))
            else:
                add(t, "ticket.approved", i)
                heapq.heappush(queues["merge"], (t, i))
        dispatch(t)
    p.events.add_many(evs)
