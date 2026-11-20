"""What the completion estimates (``eta.py``) are made of, read from the record up to a moment ``at`` and nothing
after it (so a past moment can be replayed and its estimates held against what happened: the backtest). Per kind:
its states, the semi-Markov path (each state's next-state shares, a lease's hold folded into the state it was taken
from), each state's time-in-state (Kaplan–Meier, the stays still going censored) and its arrivals. Per block that
takes the kind: its capacity, and its recorded attempts (each a run: how long, and how it ended). Per open item:
where it is, for how long, its lease, its attempts and what it waits on.

Read as the record has it: a stay that began before the record (or before what was rolled up) counts from its first
move there (left-truncated), and the relations are the links as they stand now, not as they stood at ``at``."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ..spec.ir import DEAD, LEASED
from .survival import KM

HISTORY = 14 * 86400.0      # the record read before ``at``
LATEST = 2000               # a kind's latest items read
MIN_OBS = 5                 # a state's ended stays, at least, before its own curve is used (else its kind's, else all)
MIN_RUNS = 5                # a block's attempts, at least, before they are sampled (else an assumed run, said so)
LEASE_TYPES = "ergostat.lease.taken,ergostat.lease.ended,ergostat.lease.expired"


@dataclass
class Attempt:
    dur: float
    how: str                       # ack, nack, expired; "going" (still held at ``at``)
    to: str | None = None          # where an ack left the item
    after: float = 0.0             # a nack's put-off
    counted: bool = True


@dataclass
class BlockIn:
    name: str
    kind: str
    at: list[str]
    pool: int
    shared: list[tuple[str, int]]  # (agent:NAME | daemon:NAME, its capacity): held with other blocks
    unblocked: bool
    most: int                      # attempts before a dead letter
    ttl: float = 0.0               # its lease's TTL: a run silent this long expires
    workspace: str | None = None   # the workspace pool its runs take one from, held by the item until it finishes
    attempts: list[Attempt] = field(default_factory=list)
    run: KM | None = None          # how long a run holds its lease (the going censored)
    assumed: str = ""

    def capacity(self, pools: dict | None = None) -> int:
        return min([(pools or {}).get(self.name, self.pool), *(c for _, c in self.shared)])


@dataclass
class KindIn:
    name: str
    states: list[str]
    finished: set[str]
    next: dict[str, list[tuple[str, float]]]       # state → [(next state, share)]
    ended: dict[str, list[float]]                  # state → its stays that ended
    km: dict[str, KM]                              # state → its curve (its own, its kind's or every kind's)
    said: dict[str, str]                           # state → whose curve it is ("own", "kind", "all")
    arrivals: float = 0.0                          # an hour
    arrive_at: list[tuple[str, float]] = field(default_factory=list)
    visits: dict[str, float] = field(default_factory=dict)   # N's row for the first state


@dataclass
class ItemAt:
    id: str
    kind: str
    state: str
    entered: float                 # when it came into ``state`` (a lease's hold, a nack's return folded in)
    queued: float = 0.0            # when it last came back to ``state`` (a nack's return too): its place in a queue
    lease: tuple[str, float] | None = None    # (block, taken) when leased at ``at``
    attempts: int = 0
    not_before: float = 0.0
    preds: list[str] = field(default_factory=list)
    level: int = 0                 # how many items wait on it, however far (critical first, for unblocked)
    holds: set = field(default_factory=set)   # the workspace pools it holds one of at ``at``


@dataclass
class Inputs:
    at: float
    kinds: dict[str, KindIn]
    blocks: list[BlockIn]
    items: dict[str, ItemAt]
    finished_at: dict[str, float] = field(default_factory=dict)   # (the backtest's truth, when read past ``at``)
    workspaces: dict[str, int] = field(default_factory=dict)      # each workspace pool a block uses → its size


def _fold(moves: list[dict], at: float):
    """An item's stays, its lease's hold folded into the state it was taken from: [(state, from, to)], the last open
    (``to`` None) when unfinished at ``at``; and whether it was leased at ``at`` (since when)."""
    out, cur, since, leased = [], None, None, None
    for m in moves:
        if m["time"] > at:
            break
        to = m["to"]
        if to == LEASED:
            leased = m["time"]
            continue
        leased = None
        if cur is None or to != cur:
            if cur is not None:
                out.append((cur, since, m["time"]))
            cur, since = to, m["time"]
    if cur is not None:
        out.append((cur, since, None))
    return out, leased


def fundamental(states: list[str], nxt: dict, finished: set) -> dict[str, float]:
    """The expected visits to each transient state from the first: the first row of N = (I − Q)⁻¹ (Gauss–Jordan)."""
    tr = [s for s in states if s not in finished and s != DEAD and nxt.get(s)]
    if not tr or states[0] not in tr:
        return {}
    n, ix = len(tr), {s: i for i, s in enumerate(tr)}
    a = [[(1.0 if i == j else 0.0) for j in range(n)] + [(1.0 if i == j else 0.0) for j in range(n)] for i in range(n)]
    for s in tr:
        for t, p in nxt[s]:
            if t in ix:
                a[ix[s]][ix[t]] -= p
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[piv][c]) < 1e-12:
            return {}                                       # a loop with no way out
        a[c], a[piv] = a[piv], a[c]
        d = a[c][c]
        a[c] = [x / d for x in a[c]]
        for r in range(n):
            if r != c and a[r][c]:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c], strict=True)]
    return {s: a[ix[states[0]]][n + ix[s]] for s in tr}


def read(p, spec, kinds: list[str], at: float, ix=None, truth: bool = False) -> Inputs:
    """The inputs at ``at``, from the record before it. ``truth``: also when each item open at ``at`` finished after
    it (for the backtest)."""
    from ..precedence import Kinds
    from ..spec.itemindex import index_for
    ix = ix if ix is not None else index_for(p.events, spec, False)
    info = Kinds(spec, ix)
    out = Inputs(at, {}, [], {})
    every: tuple[list[float], list[float]] = ([], [])
    pooled: dict[str, tuple] = {}
    since = at - HISTORY
    for k in kinds:
        ik = spec.items.get(k)
        if ik is None or not ik.states or ix is None:
            continue
        fin = set(info[k]["finished"])
        with ix.lock:                                   # every open item, and the latest for the fit
            got = {i.id: i for i in ix.items(k, n=LATEST)}
            got.update({i.id: i for i in ix.items(k, [s for s in ik.states if s not in fin and s != DEAD])})
            got = list(got.values())
        ended: dict[str, list[float]] = {}
        going: dict[str, list[float]] = {}
        moves: dict[str, dict[str, int]] = {}
        came: list[float] = []
        first_in: dict[str, int] = {}
        for it in got:
            stays, leased = _fold(it.moves, at)
            if not stays:
                continue
            if stays[0][1] >= since:
                came.append(stays[0][1])
                first_in[stays[0][0]] = first_in.get(stays[0][0], 0) + 1
            for i, (s, t0, t1) in enumerate(stays):
                if t1 is None:
                    if s not in fin and s != DEAD:
                        going.setdefault(s, []).append(at - t0)
                    continue
                if t1 >= since:
                    ended.setdefault(s, []).append(t1 - t0)
                    moves.setdefault(s, {})[stays[i + 1][0]] = moves.setdefault(s, {}).get(stays[i + 1][0], 0) + 1
            back = [m["time"] for m in it.moves if m["time"] <= at and m["to"] != LEASED]   # (a nack's return too)
            s, t0, t1 = stays[-1]
            if s not in fin and s != DEAD:
                out.items[it.id] = ItemAt(it.id, k, s, t0, back[-1] if back else t0,
                                          (None, leased) if leased else None)
                done = next((m["time"] for m in it.moves if m["time"] > at and (m["to"] in fin or m["to"] == DEAD)), None)
                if truth and done is not None:
                    out.finished_at[it.id] = done
        nxt = {s: [(t, c / sum(d.values())) for t, c in sorted(d.items())] for s, d in moves.items()}
        allk, goingk = [x for v in ended.values() for x in v], [x for v in going.values() for x in v]
        every[0].extend(allk)
        every[1].extend(goingk)
        pooled[k] = (allk, goingk)
        kin = KindIn(k, ik.states, fin, nxt, ended, {}, {})
        kin.km = {s: KM(ended.get(s, []), going.get(s, [])) for s in ik.states if len(ended.get(s, [])) >= MIN_OBS}
        kin.said = {s: "own" for s in kin.km}
        many = {c for c, n in Counter(came).items() if n > 2}   # a batch brought in at once (a backlog imported): not a rate
        came = [c for c in came if c not in many]
        span = at - min(came) if came else 0.0
        if len(came) >= 3 and span > 0:
            kin.arrivals = len(came) / span * 3600.0
            tot = sum(first_in.values())
            kin.arrive_at = [(s, c / tot) for s, c in first_in.items()]
        kin.visits = fundamental(ik.states, nxt, fin)
        out.kinds[k] = kin
    km_all = KM(*every) if every[0] else KM([600.0])
    for kin in out.kinds.values():
        allk, goingk = pooled[kin.name]
        km_kind = KM(allk, goingk) if len(allk) >= MIN_OBS else None
        for s in kin.states:
            if s not in kin.km:
                kin.km[s], kin.said[s] = (km_kind, "kind") if km_kind else (km_all, "all")
    _leases(p, spec, out, since, ix)
    _relations(spec, ix, out)
    return out


def _leases(p, spec, out: Inputs, since: float, ix=None) -> None:
    """Each block's attempts and its run-time curve; each open item's lease, attempts and put-off."""
    from ..leases.fold import refused_expiries
    from ..leases.terms import terms
    evs = p.events.query(n=50_000, type=LEASE_TYPES, since=since, until=out.at)
    void = refused_expiries(p.events, spec, evs, ix=ix)   # (renewed after it was judged: the run went on)
    runs: dict[str, dict] = {}
    for e in evs:
        if e["id"] in void:
            continue
        d = e.get("data") or {}
        r = d.get("run")
        if e["type"].endswith("taken"):
            runs[r] = {"t": e["time"], "item": d.get("item") or e.get("item"), "block": d.get("block"), "end": None, "run": r}
        elif r in runs and runs[r]["end"] is None:
            runs[r].update(end=e["time"], how="expired" if e["type"].endswith("expired") else d.get("how") or "nack",
                           to=d.get("state"), after=float(d.get("after") or 0.0), counted=d.get("count") is not False)
    acquired = _workspaces(p, spec, out, since)
    by_block: dict[str, list[dict]] = {}
    for r in runs.values():
        by_block.setdefault(r["block"], []).append(r)
        it = out.items.get(r["item"])
        if it is None:
            continue
        if r["end"] is None and it.lease is not None:
            it.lease = (r["block"], r["t"])
        elif r["end"] is not None and r["how"] != "ack":
            it.attempts += 1 if r["counted"] else 0
            it.not_before = max(it.not_before, r["end"] + r["after"])
        elif r["how"] == "ack":
            it.attempts = 0
    for b in spec.blocks.values():
        if not (b.takes and b.machine and b.takes.kind in out.kinds):
            continue
        shared = []
        if b.agent and b.agent in spec.agents and spec.agents[b.agent].at_once:
            shared.append((f"agent:{b.agent}", spec.agents[b.agent].at_once))
        dn = (b.params or {}).get("daemon")
        if dn and dn in spec.daemons:
            shared.append((f"daemon:{dn}", spec.daemons[dn].concurrency))
        t = terms(spec, b)
        ws = (b.params or {}).get("workspace")
        ws = ws if ws in spec.workspaces else None
        bi = BlockIn(b.name, b.takes.kind, list(b.takes.at), b.pool, shared, bool(b.takes.unblocked), t["attempts"],
                     float(t["ttl"]), ws)
        rs = by_block.get(b.name, [])
        if ws:                                          # a run given back for want of a workspace held nothing: a wait
            out.workspaces[ws] = spec.workspaces[ws].size
            rs = [r for r in rs if not (r["end"] is not None and r["how"] == "nack" and not r["counted"]
                                        and r["run"] not in acquired)]
        bi.attempts = [Attempt(r["end"] - r["t"], r["how"], r.get("to"), r.get("after", 0.0), r.get("counted", True))
                       for r in rs if r["end"] is not None]
        if len(bi.attempts) >= MIN_RUNS:
            bi.run = KM([a.dur for a in bi.attempts], [out.at - r["t"] for r in rs if r["end"] is None])
        elif out.kinds[b.takes.kind].said.get(b.takes.at[0]) in ("own", "kind"):
            km = out.kinds[b.takes.kind].km[b.takes.at[0]]   # few runs: how long its items stayed where it takes them
            bi.attempts, bi.run = [Attempt(km.quantile(0.5), "ack")], km
            bi.assumed = (f"only {len(rs)} runs on record (at least {MIN_RUNS}): a run taken as long as its items stayed "
                          f"in {b.takes.at[0]}")
        else:
            dur = float(b.every or min(t["ttl"] / 4.0, 600.0))
            bi.attempts, bi.run = [Attempt(dur, "ack")], KM([dur])
            bi.assumed = f"only {len(rs)} runs on record (at least {MIN_RUNS}): a run taken as {dur:.0f}s"
        out.blocks.append(bi)


def _workspaces(p, spec, out: Inputs, since: float) -> set[str]:
    """Which open items hold a workspace at ``at`` (each workspace's latest event: acquired or held for an item, SPEC
    §12k), and the runs that acquired one (a run of a workspace block that did not was given back for want of one)."""
    if not spec.workspaces:
        return set()
    slot: dict[str, tuple] = {}
    runs: set[str] = set()
    for e in p.events.query(n=None, type="ergostat.workspace.*", since=since, until=out.at):
        d = e.get("data") or {}
        held = e["type"].endswith((".acquired", ".held"))
        slot[e.get("item")] = (d.get("pool"), d.get("item") if held else None)
        if e["type"].endswith(".acquired") and d.get("run"):
            runs.add(d["run"])
    for pool, item in slot.values():
        if item in out.items:
            out.items[item].holds.add(pool)
    return runs


def _relations(spec, ix, out: Inputs) -> None:
    """Each open item's unfinished predecessors (an item not in the record is not counted), and how many wait on it."""
    from ..spec.relations import precedence_names
    names = precedence_names(spec)
    if not names or not out.items:
        return
    with ix.lock:
        links = ix.links_from(list(out.items))
    succ: dict[str, list[str]] = {}
    for a, r, d in links:
        if r in names.get(out.items[a].kind, set()) and d in out.items and d != a:
            out.items[a].preds.append(d)
            succ.setdefault(d, []).append(a)
    memo: dict[str, int] = {}

    def level(x: str, seen: frozenset = frozenset()) -> int:
        if x not in memo:
            memo[x] = max([1 + level(y, seen | {x}) for y in succ.get(x, []) if y not in seen] or [0])
        return memo[x]
    for x in out.items.values():
        x.level = level(x.id)
