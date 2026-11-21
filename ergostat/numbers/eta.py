"""Each open item's time to completion (SPEC §5a, *Completion estimates*): a discrete-event Monte Carlo over all the
open items together, from what the record measured (``etamodel.py``). Each run:

- an item in a state no block takes from stays its **residual life** given its age there (Kaplan–Meier,
  ``survival.py``), then moves by the kind's **semi-Markov path** (the record's next-state shares, rework included);
- an item in a state a block takes from **queues** at that block in its ``takes:`` order (the states of ``at`` in
  order, then oldest first; ``unblocked``: those more items wait on first), at most the block's **capacity** at once
  (its pool, its agent's seats, its daemon: whichever binds, seats and daemons shared); each run is a recorded
  attempt, drawn whole (how long, and how it ended: moved on, or given back or expired, which returns it to the
  queue after its put-off: rework);
- a **leased** item's run is drawn given how long its lease has been held;
- what an item waits on (its precedence relations) holds it in its kind's first state, and out of an ``unblocked``
  block's queue, until that is finished; new items **arrive** at the record's rate and compete for the same capacity.

The components are switched by ``Flags``; the backtest (``backtest``) replays past moments with each, and keeps what
helps. Bounded: ``RUNS`` runs and ``BUDGET`` seconds, a fixed seed (each run its own, so a run can be drawn again),
``HORIZON`` ahead at most. Times in seconds."""

from __future__ import annotations

import bisect
import heapq
import random
import time
from dataclasses import dataclass, replace

from ..leases.ready import take_key
from ..leases.terms import grace
from ..spec.ir import DEAD, LEASED
from .etamodel import Attempt, Inputs

RUNS = 200
BUDGET = 5.0
HORIZON = 90 * 86400.0
FEW = 20                    # fewer runs than this: no p90 is said


@dataclass(frozen=True)
class Flags:
    survival: bool = True          # residual life given age (Kaplan–Meier); else the ended stays, drawn whole
    queue: bool = True             # queues at the blocks' capacity; else a block's state is a stay like any other
    leases: bool = True            # a held lease's age, and failed or expired attempts (rework); else runs that succeed
    arrivals: bool = True          # new items at the record's rate


ABLATIONS = {"path": Flags(False, False, False), "+ survival": Flags(True, False, False),
             "+ queues": Flags(True, True, False), "+ leases": Flags(True, True, True), "all but arrivals": Flags(arrivals=False)}


def _q(xs: list[float], u: float) -> float | None:
    """A quantile of ``xs`` (inf: not finished within the horizon); None when it is past the horizon."""
    if not xs:
        return None
    v = sorted(xs)[min(len(xs) - 1, int(u * len(xs)))]
    return None if v == float("inf") else v


class _Run:
    """One run of the simulation."""

    def __init__(self, inp: Inputs, flags: Flags, rnd: random.Random, pools: dict, failures: dict, record: bool):
        self.inp, self.f, self.rnd, self.pools, self.failures, self.record = inp, flags, rnd, pools, failures, record
        self.heap: list = []
        self.seq = 0
        self.items: dict[str, list] = {}               # id → [kind, state, entered, attempts, version]
        self.finish, self.start, self.dead = {}, {}, set()
        self.segs: dict[str, list] = {}                # (record) id → [state, from, to, block, lane]
        self.blocks = inp.blocks if flags.queue else []
        self.by_state: dict[tuple, list[int]] = {}
        for i, b in enumerate(self.blocks):
            for s in b.at:
                self.by_state.setdefault((b.kind, s), []).append(i)
        self.queue = [[] for _ in self.blocks]
        self.busy = [0] * len(self.blocks)
        self.lanes = [[] for _ in self.blocks]
        self.used: dict[str, int] = {}
        self.cap = [max(1, b.capacity(pools)) for b in self.blocks]
        self.pool = [[rnd.choice(b.attempts) for _ in b.attempts] for b in self.blocks]   # bootstrapped for this run
        if not flags.leases:                             # runs that succeed only
            self.pool = [[a for a in got if a.how == "ack"] or [replace(a, how="ack") for a in got] for got in self.pool]
        sort = lambda xs: (sorted(xs, key=lambda a: a.dur), sorted(a.dur for a in xs))   # noqa: E731
        self.by_dur = [{"all": sort(got), "ack": sort([a for a in got if a.how == "ack"]),
                        "fail": sort([a for a in got if a.how != "ack"])} for got in self.pool]
        self.left = {d: len(x.preds) for d, x in inp.items.items()}
        self.after: dict[str, list[str]] = {}
        for x in inp.items.values():
            for pr in x.preds:
                self.after.setdefault(pr, []).append(x.id)
        self.parked: set[str] = set()
        self.holds = {i: set(x.holds) for i, x in inp.items.items() if x.holds} if flags.queue else {}
        self.wsfree = {w: n - sum(1 for h in self.holds.values() if w in h) for w, n in inp.workspaces.items()}
        self.no_ws = [[] for _ in self.blocks]          # queued, waiting for a workspace: back in the queue when one frees
        self.open = len(inp.items)
        self.n_new = 0

    def push(self, t, *ev):
        self.seq += 1
        heapq.heappush(self.heap, (t, self.seq, *ev))

    # ---- an item's moves

    def enter(self, i: str, state: str, t: float, age: float = 0.0, queued: float | None = None) -> None:
        it = self.items[i]
        k = self.inp.kinds[it[0]]
        it[1], it[2], it[4] = state, t, it[4] + 1
        if state in k.finished or state == DEAD:
            self.done(i, t, state == DEAD)
            return
        if state in k.paused:
            return                                     # paused: continued by hand, projected not to move
        if i not in self.start and state != k.states[0] and i in self.inp.items:
            self.start[i] = t
        bs = self.by_state.get((it[0], state))
        if self.left.get(i) and (state == k.states[0] or bs and any(self.blocks[b].unblocked for b in bs)):
            self.parked.add(i)                         # waits on what it names
            return
        if bs and all(self.blocks[b].off for b in bs):
            return                                     # what would take it is commanded off: it stays where it is
        if bs:
            x = self.inp.items.get(i)
            for b in bs:
                bl = self.blocks[b]
                self.seq += 1
                key = (*take_key(bl.order, bl.at, state, x.fields if x else {}, -(x.level if x and bl.unblocked else 0)),
                       t if queued is None else queued, self.seq)
                heapq.heappush(self.queue[b], (key, i, it[4]))
            self.wake(t)
            return
        stay = self.stay(k, state, age)
        if self.record:
            self.segs.setdefault(i, []).append([state, t, t + stay, None, None])
        self.push(t + stay, "leave", i, it[4])

    def stay(self, k, state: str, age: float) -> float:
        if self.f.survival:
            return k.km[state].sample(self.rnd, age)
        xs = k.ended.get(state) or [x for v in k.ended.values() for x in v]
        return self.rnd.choice(xs) if xs else k.km[state].sample(self.rnd)

    def next_of(self, kind: str, state: str) -> str:
        k = self.inp.kinds[kind]
        nx = k.next.get(state)
        if nx:
            return self.rnd.choices([s for s, _ in nx], [p for _, p in nx])[0]
        rest = [s for s in k.states if s not in (DEAD, LEASED)]   # never seen to leave: the next in its kind's order
        j = rest.index(state) + 1 if state in rest else len(rest)
        return rest[j] if j < len(rest) else rest[-1]

    def done(self, i: str, t: float, dead: bool) -> None:
        for w in self.holds.pop(i, ()):                 # finished: its workspace cleaned, free for the next
            self.wsfree[w] += 1
            for b, bl in enumerate(self.blocks):
                if bl.workspace == w:
                    for e in self.no_ws[b]:
                        heapq.heappush(self.queue[b], e)
                    self.no_ws[b] = []
            self.wake(t)
        if i not in self.inp.items:
            return
        self.finish[i] = t
        self.open -= 1
        if dead:
            self.dead.add(i)
        for d in self.after.get(i, []):
            self.left[d] -= 1
            if not self.left[d] and d in self.parked:
                self.parked.discard(d)
                self.enter(d, self.items[d][1], t)

    # ---- the blocks

    def attempt(self, b: int, held: float | None = None) -> Attempt:
        """A run: how long, from the block's run-time curve (the runs still held censored; given ``held``, how long
        its lease has been held), and how it ended, from the recorded attempt nearest that long (with a failure share
        tried: among the failed or the succeeded); one past the lease's TTL expires at it."""
        bl, pool = self.blocks[b], self.pool[b]
        if not self.f.leases:                            # (the ablation: runs that succeeded, drawn whole)
            return self.rnd.choice(pool)
        f = self.failures.get(bl.name)
        fail = f is not None and self.rnd.random() < f
        xs, ds = self.by_dur[b]["all" if f is None else "fail" if fail else "ack"]
        if not xs:
            xs, ds = self.by_dur[b]["all"]
        d = (held or 0.0) + bl.run.sample(self.rnd, held or 0.0)
        k = bisect.bisect_left(ds, d)                   # the recorded attempts nearest that long: one of them
        near = ds[k] if k < len(ds) and (k == 0 or ds[k] - d < d - ds[k - 1]) else ds[k - 1]
        a = xs[self.rnd.randrange(bisect.bisect_left(ds, near), bisect.bisect_right(ds, near))]
        if fail and a.how == "ack":
            a = replace(a, how="nack")
        limit = bl.ttl + grace(bl.ttl) if bl.ttl else 0.0   # silent past its TTL and the watchdog's grace: expired
        if limit and d >= limit:
            return Attempt(limit - (held or 0.0), "expired")
        return replace(a, dur=d - (held or 0.0))

    def room(self, b: int) -> bool:
        return self.busy[b] < self.cap[b] and all(self.used.get(k, 0) < c for k, c in self.blocks[b].shared)

    def hold(self, b: int, i: str, t: float, a: Attempt) -> None:
        w = self.blocks[b].workspace
        if w and w not in self.holds.get(i, ()):         # its workspace, held until the item finishes
            self.holds.setdefault(i, set()).add(w)
            self.wsfree[w] -= 1
        self.busy[b] += 1
        for k, _ in self.blocks[b].shared:
            self.used[k] = self.used.get(k, 0) + 1
        lane = heapq.heappop(self.lanes[b]) if self.lanes[b] else self.busy[b] - 1
        it = self.items[i]
        it[4] += 1
        if i not in self.start and i in self.inp.items:
            self.start[i] = t
        if self.record:
            self.segs.setdefault(i, []).append([it[1], t, t + a.dur, self.blocks[b].name, lane])
        self.push(t + a.dur, "end", i, (b, a, lane), it[4])

    def wake(self, t: float) -> None:
        for b in range(len(self.blocks)):
            q = self.queue[b]
            w = self.blocks[b].workspace
            while q and self.room(b):
                e = heapq.heappop(q)
                _, i, v = e
                it = self.items[i]
                if it[4] != v or it[1] not in self.blocks[b].at:
                    continue
                if w and w not in self.holds.get(i, ()) and self.wsfree.get(w, 1) <= 0:
                    self.no_ws[b].append(e)                 # none free: it waits, holding nothing
                    continue
                if self.record and t > max(it[2], self.inp.at):
                    self.segs.setdefault(i, []).append([it[1], max(it[2], self.inp.at), t, None, "wait"])
                self.hold(b, i, t, self.attempt(b))

    def end(self, i: str, t: float, b: int, a: Attempt, lane: int) -> None:
        self.busy[b] -= 1
        for k, _ in self.blocks[b].shared:
            self.used[k] -= 1
        heapq.heappush(self.lanes[b], lane)
        it = self.items[i]
        k = self.inp.kinds[it[0]]
        if a.how == "ack":
            self.enter(i, a.to if a.to in k.states else self.next_of(it[0], it[1]), t)
        else:
            it[3] += 1 if a.counted else 0
            if it[3] >= self.blocks[b].most:
                self.enter(i, DEAD, t)
            elif a.after > 0:
                it[4] += 1
                self.push(t + a.after, "free", i, it[4])
            else:
                self.enter(i, it[1], t)
        self.wake(t)

    # ---- the run

    def go(self, horizon: float, deadline: float = float("inf")) -> bool:
        """The run, to every tracked item's finish or the horizon; False when it ran past ``deadline`` (cut short)."""
        inp, t0 = self.inp, self.inp.at
        names = {b.name: j for j, b in enumerate(self.blocks)}
        for x in sorted(inp.items.values(), key=lambda x: (x.queued, x.id)):
            self.items[x.id] = [x.kind, x.state, x.entered, x.attempts, 0]
            if x.lease and x.lease[0] in names and self.f.queue:
                b = names[x.lease[0]]
                self.start[x.id] = t0
                self.hold(b, x.id, t0, self.attempt(b, max(0.0, t0 - x.lease[1]) if self.f.leases else None))
            elif x.not_before > t0 and self.f.queue and self.f.leases and (x.kind, x.state) in self.by_state:
                self.push(x.not_before, "free", x.id, 0)
            else:
                if x.state != inp.kinds[x.kind].states[0] or x.lease:
                    self.start[x.id] = t0
                self.enter(x.id, x.state, t0, max(0.0, t0 - x.entered), x.queued)
        if self.f.arrivals:
            for k in inp.kinds.values():
                if k.arrivals > 0 and k.arrive_at:
                    self.push(t0 + self.rnd.expovariate(k.arrivals / 3600.0), "arrive", k.name, 0)
        self.wake(t0)
        steps = 0
        while self.heap and self.open > 0:
            steps += 1
            if steps % 4096 == 0 and time.monotonic() > deadline:
                return False
            t, _, what, i, *rest = heapq.heappop(self.heap)
            if t > t0 + horizon:
                break
            if what == "arrive":
                k = inp.kinds[i]
                self.n_new += 1
                n = f"\0new{self.n_new}"
                s = self.rnd.choices([s for s, _ in k.arrive_at], [w for _, w in k.arrive_at])[0]
                self.items[n] = [i, s, t, 0, 0]
                self.enter(n, s, t)
                self.push(t + self.rnd.expovariate(k.arrivals / 3600.0), "arrive", i, 0)
            elif what == "end":
                (b, a, lane), _v = rest
                self.end(i, t, b, a, lane)
            elif self.items[i][4] == rest[0]:
                if what == "leave":
                    it = self.items[i]
                    self.enter(i, self.next_of(it[0], it[1]), t)
                else:                                   # free: its put-off over, back in the queue
                    self.enter(i, self.items[i][1], t)
        return True


def simulate(inp: Inputs, flags: Flags = Flags(), runs: int = RUNS, seed: int = 1, budget: float = BUDGET,
             horizon: float = HORIZON, pools: dict | None = None, failures: dict | None = None) -> dict:
    """Each open item's p50 and p90 finish and its expected start, per kind when its last open item finishes, and a
    levelled schedule (the run whose last finish is the median's) for the Timeline."""
    t_end = time.monotonic() + budget                   # (the runs within ``budget``, the levelled one within as much again)
    fins, starts, deads, lasts = {i: [] for i in inp.items}, {i: [] for i in inp.items}, {i: 0 for i in inp.items}, []
    n = 0
    for r in range(runs):
        if n and time.monotonic() > t_end:
            break
        run = _Run(inp, flags, random.Random(seed * 1_000_003 + r), pools or {}, failures or {}, False)
        if not run.go(horizon, t_end):
            break
        n += 1
        last = {}
        for i, x in inp.items.items():
            f = run.finish.get(i, float("inf"))
            fins[i].append(f)
            starts[i].append(run.start.get(i, f))
            deads[i] += i in run.dead
            last[x.kind] = max(last.get(x.kind, 0.0), f)
        lasts.append(last)
    few = n < FEW                                       # (too few runs for a p90: none said)
    mean = lambda xs: sum(xs) / len(xs) if xs and max(xs) < float("inf") else None   # noqa: E731
    items = {i: {"p50": _q(fins[i], 0.5), "p90": None if few else _q(fins[i], 0.9), "mean": mean(fins[i]),
                 "start": _q(starts[i], 0.5),
                 "dead": round(deads[i] / n, 3), "runs": n} for i in inp.items} if n else {}
    kinds = {}
    for k in {x.kind for x in inp.items.values()} if n else ():
        xs = [la.get(k, 0.0) for la in lasts]
        kinds[k] = {"p50": _q(xs, 0.5), "p90": None if few else _q(xs, 0.9), "visits": inp.kinds[k].visits,
                    "open": sum(1 for x in inp.items.values() if x.kind == k)}
    # the levelled schedule: the run whose last finish is nearest the median's, drawn again with its segments kept
    rep = None
    if n and time.monotonic() < t_end + budget:
        ends = [max(la.values(), default=0.0) for la in lasts]
        med = sorted(ends)[len(ends) // 2]
        r = min(range(n), key=lambda j: (abs(ends[j] - med) if med != float("inf") else 0, j))
        run = _Run(inp, flags, random.Random(seed * 1_000_003 + r), pools or {}, failures or {}, True)
        run.go(horizon, t_end + budget)
        rep = {i: s for i, s in run.segs.items() if i in inp.items}
    held = {}                                           # (leases held over a lowered pool: their lanes drawn too)
    for x in inp.items.values():
        if x.lease and x.lease[0]:
            held[x.lease[0]] = held.get(x.lease[0], 0) + 1
    return {"at": inp.at, "runs": n, "flags": flags.__dict__, "items": items, "kinds": kinds, "schedule": rep or {},
            "capacity": {b.name: max(1, b.capacity(pools), held.get(b.name, 0)) for b in inp.blocks},
            "limit": {b.name: max(1, b.capacity(pools)) for b in inp.blocks}}


def reasons(inp: Inputs, pools: dict | None = None) -> dict[str, dict]:
    """Each open item, now: what it waits in (a block, or a state), its place in that block's queue, and why, in
    words ("6 of 6 busy in review; 38 ahead of it; a run takes 9m (median)")."""
    from ..durations import human
    out: dict[str, dict] = {}
    held: dict[str, int] = {}
    for x in inp.items.values():
        if x.lease and x.lease[0]:
            held[x.lease[0]] = held.get(x.lease[0], 0) + 1
    place: dict[str, dict[str, int]] = {}                # block → item → how many are ahead of it
    for b in inp.blocks:
        q = [x for x in inp.items.values() if x.kind == b.kind and x.state in b.at and not x.lease
             and not (b.unblocked and x.preds)]
        q.sort(key=lambda x: (*take_key(b.order, b.at, x.state, x.fields, -(x.level if b.unblocked else 0)), x.queued,
                              x.id))
        place[b.name] = {x.id: n for n, x in enumerate(q)}
    for x in inp.items.values():
        k = inp.kinds[x.kind]
        waits = f"waits on {', '.join(x.preds)}; " if x.preds else ""
        b = next((b for b in inp.blocks if x.lease and b.name == x.lease[0]), None)
        if b is not None:
            med = b.run.quantile(0.5) if b.run else None
            bad = sum(1 for a in b.attempts if a.how != "ack") / len(b.attempts)
            out[x.id] = {"waits_in": b.name, "position": None, "why": f"running in {b.name} for {human(inp.at - x.lease[1])}"
                         + (f"; a run takes {human(med)} (median)" if med else "") + (f", {bad:.0%} given back or expired" if bad else "")}
            continue
        b = next((b for b in inp.blocks if b.kind == x.kind and x.state in b.at), None)
        if b is not None:
            pos = place[b.name].get(x.id)
            cap = b.capacity(pools)
            bind = next((f" ({n.split(':', 1)[1]}'s {'seats' if n.startswith('agent') else 'runs at once'}: {c})"
                         for n, c in b.shared if c < (pools or {}).get(b.name, b.pool)), "")
            put = f"; put off until it is due in {human(x.not_before - inp.at)}" if x.not_before > inp.at else ""
            w = b.workspace
            if w and w not in x.holds and sum(1 for y in inp.items.values() if w in y.holds) >= inp.workspaces[w]:
                put += f"; every workspace of {w} is held ({inp.workspaces[w]}): it waits for one, holding nothing"
            med = b.run.quantile(0.5) if b.run else None
            if all(o.off for o in inp.blocks if o.kind == x.kind and x.state in o.at):
                out[x.id] = {"waits_in": b.name, "position": None, "capacity": cap, "off": True,
                             "why": waits + f"waits for {b.name}, which is switched off now (by {b.off}): projected "
                             "not to move until it is on"}
                continue
            out[x.id] = {"waits_in": b.name, "position": None if pos is None else pos + 1, "capacity": cap,
                         "why": waits + f"{held.get(b.name, 0)} of {cap} busy in {b.name}{bind}"
                         + (f"; {pos} ahead of it" if pos is not None else "") + put
                         + (f"; a run takes {human(med)} (median)" if med else "") + (f"; assumed: {b.assumed}" if b.assumed else "")}
            continue
        if x.state in k.paused:
            out[x.id] = {"waits_in": x.state, "position": None, "paused": True,
                         "why": waits + f"paused in {x.state}: continued by hand, projected not to move until then"}
            continue
        km = k.km[x.state]
        age = inp.at - x.entered
        out[x.id] = {"waits_in": x.state, "position": None,
                     "why": waits + f"in {x.state} for {human(age)}, which no block takes from; about "
                     f"{human(km.quantile(0.5, age))} more (the median given its age, the mean {human(km.mean_residual(age))}; "
                     f"from {km.n} stays"
                     + ("" if k.said[x.state] == "own" else f", its {'kind' if k.said[x.state] == 'kind' else 'record'}'s") + ")"}
    return out
