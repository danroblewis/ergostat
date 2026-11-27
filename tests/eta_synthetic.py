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
projections:
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
    takes: {projection: ticket, at: new}
    pool: {pool}
    lease: {attempts: 9, ttl: 4h}
  merge:
    type: program
    run: "true"
    takes: {projection: ticket, at: merging}
    pool: 1
    lease: {ttl: 4h}
"""


def project(tmp_path, pool: int = 3) -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("{pool}", str(pool))))
    m = mdl.load(tmp_path)
    assert m.spec is not None
    return Project(m)


GATED_BATCH = 5 * 86400.0


def gated_record(tmp_path, seed: int = 0, t0: float = 1_790_000_000.0) -> Project:
    """The gated record: a dev pool of 20 under a control loop admitting 4 runs at once (the rest refused, put off
    300 s), runs of about 3 h (lognormal, σ 0.25); a history of 0.4 tickets an hour for 36 h, quiet after, then 40
    brought in at once ``GATED_BATCH`` after ``t0``, recorded for 60 h."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL.replace("{pool}", "20").replace(   # a run's own
        "[new, review", "[new, doing, review").replace("ticket.implemented", "ticket.started: doing, ticket.implemented")))
    p = Project(mdl.load(tmp_path))                     # event at an admitted take moves it to doing (a factory's gap)
    kw = {"pool": 20, "gate": 4, "dev": 3 * 3600.0, "sigma": 0.25, "fail": 0.1, "rework": 0.1}
    generate(p, t0, 96, rate=0.4, backlog=0, seed=3 + seed, prefix="h", stop_arrivals=36, **kw)
    generate(p, t0 + GATED_BATCH, 60, rate=0, backlog=40, seed=4 + seed, prefix="b", **kw)
    return p


def lognormal(rnd, median: float, sigma: float) -> float:
    return median * math.exp(rnd.gauss(0.0, sigma))


def generate(p: Project, t0: float, hours: float, rate: float = 6.0, backlog: int = 30, pool: int = 3,
             dev: float = 1200.0, fail: float = 0.15, review: float = 1800.0, rework: float = 0.3, merge: float = 180.0,
             seed: int = 7, stop_arrivals: float | None = None, prefix: str = "", sigma: float = 0.6,
             gate: int | None = None, put_off: float = 300.0) -> None:
    """``hours`` of record from ``t0``: ``backlog`` tickets at ``t0``, then ``rate`` an hour (until ``stop_arrivals``
    hours, when given). ``gate``: the dev runs admitted at once by a control loop under its pool; a run taken past it
    refuses at once (given back in 2 s, not counted, put off ``put_off``), as a factory's run on drain does; one
    admitted writes ``ticket.started`` (the gated record's model moves it to ``doing``)."""
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
    admitted = [0]                          # dev runs going (not refusing)

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
                if b == "dev" and gate is not None and admitted[0] >= gate:
                    at(t + 2.0, "refuse", i, run)
                    continue
                admitted[0] += b == "dev"
                if b == "dev" and gate is not None:
                    add(t, "ticket.started", i)
                d =lognormal(rnd, dev, sigma) if b == "dev" else rnd.expovariate(1 / merge)
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
        elif what == "refuse":
            i, run = rest
            busy["dev"] -= 1
            add(t, "ergostat.lease.ended", i, {"run": run, "fence": fence[i], "how": "nack", "why": "draining",
                                               "item": i, "state": "new", "terminal": False, "count": False,
                                               "after": put_off})
            at(t + put_off, "due", i)
        elif what == "due":
            heapq.heappush(queues["dev"], (t, rest[0]))
        elif what == "end":
            b, i, run = rest
            busy[b] -= 1
            admitted[0] -= b == "dev"
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
