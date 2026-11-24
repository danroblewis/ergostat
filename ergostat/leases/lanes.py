"""Lanes on a block's queue (SPEC §9.5, ``takes: {lanes: {apart: FIELD, most: N, ahead: K, each: {cpu, memory},
within: {cpu, memory}, passed: [STATE]}}``): the block runs several of its items at once, but never two whose FIELD
lists share an entry (the paths a change touches, say), and an item that shares one with a lane under way may run
on top of it, ``ahead`` lanes deep at most: its lease says the items it is on (``on``), and when one of them does not
pass (its run gives it back, its lease expires, or it is left in a state not in ``passed``) the lanes on top of it
are stopped and given back, not counted. How many lanes are held at once is bounded by resources: each lane costs
the larger of its declared ``each`` and what the block's newest runs measured (CPU seconds over wall seconds, peak
memory), and the lanes together never cost more than ``within``; one lane always runs.

One rule, ``plan``, for the dispatcher (``choose``) and the replay (``replay``), which runs a fixture of items
through it and says merges per hour. Off unless declared."""

from __future__ import annotations

import heapq
import math

from ..spec import items as its
from .kill import kill

MOST, AHEAD_MOST = 16, 4               # lanes at once, and lanes deep, at most (lesson-4: checked again at run time)
LAST = 20                              # the block's newest ended runs a lane's cost is measured over
EVERY = 60.0                           # seconds between reads of that cost


def touches(fields, field: str) -> frozenset | None:
    """What an item touches: its FIELD, a list of words (or one). None when it cannot be read (missing, empty, not
    words): it touches everything, so it runs alone (lesson-3)."""
    v = fields.get(field) if isinstance(fields, dict) else None
    v = [v] if isinstance(v, str) else v
    if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
        return None
    return frozenset(v)


def overlap(a: frozenset | None, b: frozenset | None) -> bool:
    return a is None or b is None or bool(a & b)


def room(ln, cost: tuple[float | None, float | None] | None) -> int:
    """The lanes that may be held at once: at most ``most`` (and MOST), and as many as ``within`` holds at the larger
    of the declared and the measured cost a lane. A cost unknown is the worst case (lesson-3): one lane when it could
    not be read (None), or when one of cores and memory is neither declared (``each``) nor measured by a run (None in
    it). At least 1."""
    if cost is None:
        return 1
    got = []
    for declared, measured in ((ln.cpu, cost[0]), (ln.memory, cost[1])):
        if not declared and measured is None:
            return 1
        got.append(max(declared, measured or 0, 1e-3))
    return max(1, min(ln.most, MOST, int(ln.within_cpu // got[0]), int(ln.within_memory // got[1])))


def plan(waiting: list, running: list, free: int, ahead: int) -> list[tuple[str, tuple]]:
    """What starts now: (id, on) for items of ``waiting`` ([(id, touches)], in the take order), at most ``free``.
    ``running``: the lanes held ([(id, touches, on)]). An item touching no lane starts apart (on ()); one touching
    lanes that all lie on one lane's chain starts on top of it when the chain is less than ``ahead`` deep; else it
    waits, and so does every later item touching it (overlapping items keep their order)."""
    ahead = max(0, min(AHEAD_MOST, int(ahead)))
    lanes = [(i, p, tuple(on)) for i, p, on in running]
    starts, skipped = [], []
    for i, p in waiting:
        if len(starts) >= max(0, int(free)):
            break
        if any(overlap(p, s) for s in skipped):
            skipped.append(p)
            continue
        hit = [ln for ln in lanes if overlap(p, ln[1])]
        on = () if not hit else _on_top(hit, {ln[0] for ln in lanes}, ahead)
        if on is None:
            skipped.append(p)
            continue
        starts.append((i, on))
        lanes.append((i, p, on))
    return starts


def _on_top(hit: list, live: set, ahead: int) -> tuple | None:
    """The chain an item touching ``hit`` runs on: the hit lane whose chain holds every other hit lane, then it;
    None when there is none, or it would be more than ``ahead`` deep."""
    ids = {h[0] for h in hit}
    for i, _, on in hit:
        if ids <= {*on, i}:
            chain = (*[x for x in on if x in live], i)
            return chain if len(chain) <= ahead else None
    return None


def above(running: list, base: str) -> list[str]:
    """The lanes on top of ``base`` (at any depth: ``on`` is the whole chain)."""
    return [i for i, _, on in running if base in on]


# ---- the dispatcher's

def cost(d, b, now: float) -> tuple[float | None, float | None] | None:
    """A lane's measured cost (cores, bytes): the most any of the block's LAST newest ended runs used, each None when no
    run measured it; read at most every EVERY seconds. Unreadable: None (one lane), said once."""
    kept = d.__dict__.setdefault("lanes_cost", {})
    if b.name in kept and now - kept[b.name][0] < EVERY:
        return kept[b.name][1]
    from ..costs.record import ENDS
    try:
        rows = d.p.events.query(n=LAST, type=ENDS, item=b.name, source="ergostat")
        got: list = [None, None]
        for e in rows:
            r, secs = (e.get("data") or {}).get("resources"), (e.get("data") or {}).get("seconds")
            if not isinstance(r, dict):
                continue
            c, m = r.get("cpu"), r.get("memory_peak")
            if _num(c) and _num(secs) and secs > 0:
                got[0] = max(got[0] or 0.0, c / secs)
            if _num(m):
                got[1] = max(got[1] or 0.0, float(m))
        out = (got[0], got[1])
    except Exception as e:  # noqa: BLE001 - said; the block runs one lane until it is read
        if kept.get(b.name, (0, ()))[1] is not None:
            d.e.say(f"{b.name}: its lanes' cost not read ({type(e).__name__}: {e}): one lane")
        out = None
    kept[b.name] = (now, out)
    return out


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0


def choose(d, b, every: list, got: list, room_now: int, now: float) -> tuple[list, dict]:
    """Under the dispatcher's lock: of ``got`` (the items it may take, in order), those that start now, and each one's
    ``on``. The lanes held are the block's leased items (and its runs going); a base that did not pass (``discard``)
    is no lane to go on top of."""
    ln = b.takes.lanes
    going = d.going.get(b.name, {})
    failed = d.__dict__.setdefault("lanes_failed", {})
    running, gone = [], set()
    for i in every:
        lease = i.fields.get("lease") if isinstance(i.fields.get("lease"), dict) else {}
        if i.id in going or (lease.get("holder") and lease.get("block") == b.name):
            g = going.get(i.id) or {}
            running.append((i.id, touches(i.fields, ln.apart), tuple(g.get("on") or lease.get("on") or ())))
            if i.id in failed and failed[i.id] == (g.get("run") or lease.get("holder")):
                gone.add(i.id)
    for i in set(failed) - {r[0] for r in running}:
        failed.pop(i, None)                              # (its lease ended: a new one starts clean)
    free = min(room_now, room(ln, cost(d, b, now)) - len(running))
    starts: dict = {}
    for i, on in plan([(i.id, touches(i.fields, ln.apart)) for i in got], running, free, ln.ahead):
        if gone.intersection(on):                        # (on a base that did not pass, or on one dropped so)
            gone.add(i)
        else:
            starts[i] = on
    return [i for i in got if i.id in starts], starts


def passed(b, how: str, state: str | None) -> bool:
    """A lane's end that lets those on top of it stand: given back never does; moved on, into ``passed`` when declared."""
    ps = b.takes.lanes.passed
    return how == "ack" and (not ps or state in ps)


def discard(d, b, base: str, run: str, why: str) -> list[str]:
    """``base``'s lane did not pass: every lane on top of it is stopped (leases/kill.py) and, when its run ends, given
    back uncounted (``out``). Under the dispatcher's lock, so a look either took its lane before (it is stopped here) or
    sees the base failed (and puts nothing on it)."""
    with d.lock:
        d.__dict__.setdefault("lanes_failed", {})[base] = run
        hit = [(i, g) for i, g in d.going.get(b.name, {}).items() if base in (g.get("on") or ())]
        said = d.__dict__.setdefault("lanes_out", {})
        for _, g in hit:
            said[g["run"]] = f"the lane it ran on top of ({base}) did not pass ({why}): discarded, not counted"
    for i, g in hit:
        kill(d.e, g["run"], said[g["run"]], i, g["fence"], b.name)
        d.e.say(f"{b.name}: discarded the lane on {i}: {base} did not pass")
    return [i for i, _ in hit]


def unproven(d, b, lease: dict) -> str | None:
    """A lane on top that ends red: the first of what it ran on that has not passed (still under way, or given back),
    so its red is not proven its own and is not counted; None when all of them passed (or it ran apart)."""
    from .dispatch import moved_on
    for o in lease.get("on") or []:
        it = its.one(d.p.events, d.spec, o)
        if it is None or (it.fields.get("lease") or {}).get("holder") or not (
                it.state in b.takes.lanes.passed if b.takes.lanes.passed else moved_on(b, it)):
            return o
    return None


def out(d, run: str) -> str | None:
    """Why ``run``'s lane was discarded (its end is then given back uncounted), once; None when it was not."""
    return d.__dict__.get("lanes_out", {}).pop(run, None)


# ---- the replay

def replay(items: list[dict], ln, cost: tuple = (None, None)) -> dict:
    """A fixture of items ({id, at, touches, minutes, passes}: arrival and run time in minutes) through ``plan``, as
    the dispatcher takes them: a lane is held until it ends, and one on top of others until they pass; a lane that
    fails discards those on top of it, which wait again and are run again. Returns merges (items passed), failed,
    discarded runs, the most lanes held at once, minutes from the first arrival to the last end, and merges per hour."""
    by = {x["id"]: x for x in items}
    arrive = sorted(items, key=lambda x: (x["at"], x["id"]))
    t, k, seq = float(arrive[0]["at"]) if arrive else 0.0, 0, 0
    waiting: list[str] = []
    held: dict[str, dict] = {}                     # id → {on, end, done}
    ends: list = []
    merged, failed, thrown, most, last = [], [], 0, 0, t
    while k < len(arrive) or held or waiting:
        while k < len(arrive) and arrive[k]["at"] <= t:
            waiting.append(arrive[k]["id"])
            k += 1
        running = [(i, _touch(by[i]), h["on"]) for i, h in held.items()]
        for i, on in plan([(i, _touch(by[i])) for i in waiting], running, room(ln, cost) - len(held), ln.ahead):
            waiting.remove(i)
            seq += 1
            held[i] = {"on": on, "end": t + float(by[i]["minutes"]), "done": False, "seq": seq}
            heapq.heappush(ends, (held[i]["end"], seq, i))
        most = max(most, len(held))
        nxt = [arrive[k]["at"]] if k < len(arrive) else []
        while ends and (ends[0][2] not in held or held[ends[0][2]]["seq"] != ends[0][1]):
            heapq.heappop(ends)                    # (a discarded lane's end)
        if ends:
            nxt.append(ends[0][0])
        if not nxt:
            break                                  # (nothing runs and nothing can start: never expected)
        t = max(t, min(nxt))
        while ends and ends[0][0] <= t:
            _, s, i = heapq.heappop(ends)
            if i not in held or held[i]["seq"] != s:
                continue
            last = t
            if not by[i]["passes"]:                # (red on a base still under way: not proven its own, again)
                unproven = any(o in held for o in held.pop(i)["on"])
                back = [x for x, h in held.items() if i in h["on"]] + ([i] if unproven else [])
                failed += [] if unproven else [i]
                thrown += len(back)
                for x in back:
                    held.pop(x, None)
                waiting += back                    # (back in its state: behind those waiting, as ready() sorts)
            else:
                held[i]["done"] = True
            for x in sorted(held, key=lambda x: held[x]["seq"]):   # (a lane lands once all it is on has)
                if held[x]["done"] and not any(o in held for o in held[x]["on"]):
                    merged.append(x)
                    held.pop(x)
    hours = (last - float(arrive[0]["at"])) / 60 if arrive else 0.0
    return {"merged": len(merged), "failed": len(failed), "discarded": thrown, "most_held": most,
            "minutes": round(last - float(arrive[0]["at"]), 1) if arrive else 0.0,
            "per_hour": round(len(merged) / hours, 3) if hours > 0 else 0.0, "order": merged}


def _touch(x: dict) -> frozenset | None:
    return touches({"t": x.get("touches")}, "t")
