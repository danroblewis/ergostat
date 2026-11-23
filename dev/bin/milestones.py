"""milestones: groups of gaps finished together (the owner, 2026-11-22), the item kind `milestone` (ergostat.yaml):
waiting, active, completed (final: no event moves one out of it).

  milestones.py pass        (every minute, no AI; dev/model/milestones.yaml) first each active milestone that is done:
                            one with at least one gap, every one merged or closed (a parked or dead gap holds it open;
                            an empty one never completes); an upkeep one (`upkeep: true`, the factory's own repairs) at
                            the end of its cycle ([milestones] upkeep_days, default 7), its unfinished gaps moved to a
                            new upkeep milestone, active at once. Then each waiting milestone whose dependencies are all
                            completed becomes active, in rank order, while fewer than [milestones] active_max (default
                            3) are active; an upkeep one is always active and never counts toward the limit.
  milestones.py add NAME [--title T] [--rank N] [--upkeep] [--depends M,...]
  milestones.py depends MILESTONE ON [ON ...]     (refuses a cycle, a name that is no milestone, a completed one)
  milestones.py assign GAP MILESTONE              (refuses a completed milestone, and a cycle)
                            A cycle is sought in the precedence graph the implementor's take reads: gaps' depends_on,
                            milestones' depends_on, and each milestone a summary of its gaps (ergostat/precedence.py),
                            over the unfinished ones. A change that puts an item on a cycle it was not on is refused.
  milestones.py pull GAP | unpull GAP             (marks a gap pulled ahead of its milestone, or clears it: only said
                                                   here; what the implementor takes is not decided by this program)
  milestones.py status                            (each milestone, its state, what it waits on, its gaps by state)

A gap names its milestone in its field `milestone` (a relation, folded by replace). The old free-text labels some gaps
still hold there (names, not milestone ids) are left as written, and listed by status until they are assigned.
Every read-decide-write here (the pass and each command) holds run/milestones.lock throughout."""

from __future__ import annotations

import fcntl
import math
import re
import sys
import time
from contextlib import contextmanager

sys.dont_write_bytecode = True
import fac  # noqa: E402

DONE = ("merged", "closed")                     # a gap finished (ergostat.yaml messages: done)
ORDER = ("active", "waiting", "completed")
LIMITS = {"active_max": (3, 20), "upkeep_days": (7, 90)}   # [milestones]: (default, ceiling); at least 1
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SUCCESSORS_MOST = 20                            # names tried for an upkeep milestone's successor (a hard ceiling)
BY = ["coordinator"]


class Refused(Exception):
    pass


def settings(cfg: dict) -> tuple[int, float]:
    """(active_max, upkeep_days). One not a number, below 1 or past its ceiling is refused, never clamped."""
    got = cfg.get("milestones") or {}
    out = []
    for key, (default, most) in LIMITS.items():
        v = got.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int | float) or not 1 <= v <= most or (key == "active_max" and v != int(v)):
            raise ValueError(f"[milestones] {key} = {v!r}: a number from 1 to {most}")
        out.append(v)
    return int(out[0]), float(out[1])


@contextmanager
def held(cfg: dict):
    with open(fac.run_dir(cfg) / "milestones.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def ids_of(v) -> list[str]:
    """The ids (or old labels) a relation's field holds: one, or a list; anything else holds none."""
    if isinstance(v, str):
        return [v] if v else []
    return [x for x in v if isinstance(x, str) and x] if isinstance(v, list) else []


def read() -> tuple[dict[str, dict], dict[str, dict]]:
    return {m["id"]: m for m in fac.items("milestone")}, {g["id"]: g for g in fac.items("gap")}


def gaps_of(mid: str, gaps: dict[str, dict]) -> list[dict]:
    return sorted((g for g in gaps.values() if mid in ids_of(g["fields"].get("milestone"))), key=lambda g: g["id"])


def upkeep(m: dict) -> bool:
    return m["fields"].get("upkeep") is True


def number(v) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) else None


def rank_key(m: dict) -> tuple:
    r = number(m["fields"].get("rank"))
    return (r is None, r or 0.0, m["id"])


def waits_on(m: dict, ms: dict[str, dict]) -> list[str]:
    """The milestones it depends on not completed; one not in the record is not known to be completed."""
    return [d for d in ids_of(m["fields"].get("depends_on")) if (ms.get(d) or {}).get("state") != "completed"]


def successor(m: dict, ms: dict[str, dict], now: float) -> str:
    """The upkeep milestone that follows ``m``: one already made for it (a pass that stopped part way), else a new
    name from today's date, the first not taken."""
    made = [x["id"] for x in ms.values() if x["fields"].get("follows") == m["id"]]
    if made:
        return sorted(made)[0]
    base = f"milestone/upkeep-{time.strftime('%Y-%m-%d', time.localtime(now))}"
    for n in range(1, SUCCESSORS_MOST + 1):
        mid = base if n == 1 else f"{base}-{n}"
        if mid not in ms:
            return mid
    raise RuntimeError(f"no free name for the upkeep milestone after {m['id']} ({base} and {SUCCESSORS_MOST - 1} more)")


def plan(ms: dict[str, dict], gaps: dict[str, dict], now: float, active_max: int, days: float) -> list[tuple]:
    """The events one pass records, in order: (event, item, data)."""
    out: list[tuple] = []
    state = {mid: m["state"] for mid, m in ms.items()}
    for mid, m in sorted(ms.items()):
        if m["state"] != "active":
            continue
        mine = gaps_of(mid, gaps)
        if upkeep(m):
            ends = number(m["fields"].get("upkeep_ends"))
            if ends is None:                            # (activated by hand): its cycle pinned once, from when it began
                ends = (number(m.get("entered")) or now) + days * 86400
                out.append(("milestone.changed", mid, {"upkeep_ends": ends}))
            if now < ends:
                continue
            nxt = successor(m, ms, now)
            if nxt not in ms:
                out.append(("milestone.added", nxt, {"title": f"upkeep from {time.strftime('%Y-%m-%d', time.localtime(now))}",
                                                     "upkeep": True, "follows": mid, "added_by": "milestones"}))
            if (ms.get(nxt) or {}).get("state") != "active":
                out.append(("milestone.activated", nxt, {"activated_at": now, "upkeep_ends": now + days * 86400}))
                state[nxt] = "active"
            left = [g["id"] for g in mine if g["state"] not in DONE]
            out += [("gap.milestone-set", g, {"milestone": nxt, "milestone_was": mid, "assigned_by": "milestones"})
                    for g in left]
            out.append(("milestone.completed", mid, {"completed_at": now, "completed_for": "its upkeep cycle ended",
                                                     "carried_to": nxt, "carried": left}))
            state[mid] = "completed"
        elif mine and all(g["state"] in DONE for g in mine):
            out.append(("milestone.completed", mid, {"completed_at": now, "completed_for": "every gap merged or closed",
                                                     "gaps_n": len(mine)}))
            state[mid] = "completed"
    room = active_max - sum(1 for mid, s in state.items() if s == "active" and mid in ms and not upkeep(ms[mid]))
    done = {mid: {"state": s} for mid, s in state.items()}
    for m in sorted((m for m in ms.values() if state[m["id"]] == "waiting"), key=rank_key):
        if upkeep(m):
            out.append(("milestone.activated", m["id"], {"activated_at": now, "upkeep_ends": now + days * 86400}))
        elif room > 0 and not waits_on(m, done):
            out.append(("milestone.activated", m["id"], {"activated_at": now}))
            room -= 1
    return out


def record(events: list[tuple]) -> None:
    for event, item, data in events:
        fac.add(event, item, **data, by=BY[0])


def run_pass(cfg: dict, now: float | None = None) -> list[tuple]:
    active_max, days = settings(cfg)                    # (refused before anything is read)
    with held(cfg):
        ms, gaps = read()
        got = plan(ms, gaps, time.time() if now is None else now, active_max, days)
        record(got)
    return got


# ---- the coordinator's commands

def mid_of(name: str) -> str:
    n = name.removeprefix("milestone/")
    if not NAME.match(n):
        raise Refused(f"{name!r} is not a milestone's name (lowercase letters, digits and -, at most 64)")
    return f"milestone/{n}"


def gid_of(name: str, gaps: dict[str, dict]) -> str:
    gid = name if name.startswith("gap/") else f"gap/{name}"
    if gid not in gaps:
        raise Refused(f"{name}: no such gap")
    return gid


def known(mid: str, ms: dict[str, dict]) -> dict:
    if mid not in ms:
        raise Refused(f"{mid}: no such milestone")
    return ms[mid]


END = " (its end)"                               # a milestone with gaps is a summary: a start node and an end node


def pairs_of(ms: dict[str, dict], gaps: dict[str, dict]) -> list[tuple[str, str]]:
    """The precedence graph the Items page's critical path and the implementor's take read (ergostat/precedence.py),
    over the unfinished gaps and milestones: ``(a, b)``, a before b. A gap's depends_on and a milestone's depends_on
    are precedence; a milestone with unfinished gaps is a summary (its start before each gap, each gap before its
    end), so what it depends on comes before its gaps start and what depends on it waits for them all to end."""
    live_m = {k for k, m in ms.items() if m["state"] != "completed"}
    live_g = {k for k, g in gaps.items() if g["state"] not in DONE}
    kids: dict[str, list[str]] = {}
    for gid in sorted(live_g):
        for mid in ids_of(gaps[gid]["fields"].get("milestone")):
            if mid in live_m:
                kids.setdefault(mid, []).append(gid)
    end = lambda a: a + END if a in kids else a          # noqa: E731
    out = [(end(d), a) for items, live in ((gaps, live_g), (ms, live_m)) for a in sorted(live)
           for d in ids_of(items[a]["fields"].get("depends_on")) if d in live]
    for mid, cs in kids.items():
        out += [(mid, c) for c in cs] + [(c, mid + END) for c in cs]
    return out


def in_cycles(pairs: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Each node on a cycle, with the strongly connected set it is in (Kosaraju's algorithm, iterative)."""
    succ: dict[str, list[str]] = {}
    pred: dict[str, list[str]] = {}
    for a, b in pairs:
        succ.setdefault(a, []).append(b)
        pred.setdefault(b, []).append(a)
        succ.setdefault(b, [])
        pred.setdefault(a, [])
    order, seen = [], set()
    for root in succ:
        if root in seen:
            continue
        seen.add(root)
        work = [(root, iter(succ[root]))]
        while work:
            v, it = work[-1]
            w = next((w for w in it if w not in seen), None)
            if w is None:
                work.pop()
                order.append(v)
            else:
                seen.add(w)
                work.append((w, iter(succ[w])))
    out: dict[str, set[str]] = {}
    done: set[str] = set()
    for root in reversed(order):
        if root in done:
            continue
        comp, todo = {root}, [root]
        done.add(root)
        while todo:
            for w in pred[todo.pop()]:
                if w not in done:
                    done.add(w)
                    comp.add(w)
                    todo.append(w)
        if len(comp) > 1 or root in succ[root]:
            out.update({n: comp for n in comp})
    return out


def closes(before: list[tuple[str, str]], after: list[tuple[str, str]], first: list[str]) -> str | None:
    """A cycle the change from ``before`` to ``after`` closes, as a path along what each waits on (from the first of
    ``first`` new to a cycle, else the first node new to one), or None. A node on a cycle already is not counted
    again: the change did not close that one."""
    was, now = in_cycles(before), in_cycles(after)
    new = sorted(n for n in now if n not in was)
    if not new:
        return None
    start = next((n for n in first if n in new), new[0])
    comp, back = now[start], {}
    for a, b in after:
        if a in comp and b in comp:
            back.setdefault(b, []).append(a)            # b waits on a
    todo, via = [start], {start: None}
    while todo:
        v = todo.pop(0)
        for w in sorted(back.get(v, ())):
            if w == start:
                chain = [v]
                while via[chain[-1]] is not None:
                    chain.append(via[chain[-1]])
                return " -> ".join(chain[::-1] + [start])
            if w not in via:
                via[w] = v
                todo.append(w)
    return " -> ".join(sorted(comp))                     # (not reached: a strongly connected set has a path back)


def refuse_cycle(before: list, after: list, first: list[str], what: str) -> None:
    loop = closes(before, after, first)
    if loop:
        raise Refused(f"refused: {what} would close a cycle: {loop} (no gap on it would be taken)")


def checked_deps(ms: dict[str, dict], gaps: dict[str, dict], mid: str, names: list[str]) -> list[str]:
    on = [mid_of(n) for n in names]
    for d in on:
        known(d, ms)
        if d == mid:
            raise Refused(f"{mid} cannot depend on itself")
    m = ms.get(mid) or {"id": mid, "state": "waiting", "fields": {}}
    had = ids_of(m["fields"].get("depends_on"))
    then = {**ms, mid: {**m, "fields": {**m["fields"], "depends_on": had + [d for d in on if d not in had]}}}
    refuse_cycle(pairs_of(ms, gaps), pairs_of(then, gaps), [mid], f"{mid} depending on {', '.join(on)}")
    return on


def add(cfg: dict, name: str, title: str = "", rank: float | None = None, upkeep_: bool = False,
        depends: list[str] = ()) -> str:
    mid = mid_of(name)
    with held(cfg):
        ms, gaps = read()
        if mid in ms:                                    # (never made again under the same id: its old fields stay)
            raise Refused(f"{mid} is already a milestone ({ms[mid]['state']})")
        on = checked_deps(ms, gaps, mid, list(depends))
        data = {"title": title or name, "upkeep": upkeep_ or None, "rank": rank, "added_by": BY[0]}
        record([("milestone.added", mid, {k: v for k, v in data.items() if v is not None}
                 | ({"depends_on": on} if on else {}))])
    return mid


def depends(cfg: dict, name: str, on: list[str]) -> list[str]:
    mid = mid_of(name)
    with held(cfg):
        ms, gaps = read()
        if known(mid, ms)["state"] == "completed":
            raise Refused(f"{mid} is completed: it is final")
        got = checked_deps(ms, gaps, mid, on)
        record([("milestone.changed", mid, {"depends_on": {"add": got}})])
    return got


def assign(cfg: dict, gap: str, name: str) -> str:
    mid = mid_of(name)
    with held(cfg):
        ms, gaps = read()
        gid = gid_of(gap, gaps)
        if known(mid, ms)["state"] == "completed":
            raise Refused(f"{mid} is completed: no gap is assigned to a completed milestone")
        was = gaps[gid]["fields"].get("milestone")
        then = {**gaps, gid: {**gaps[gid], "fields": {**gaps[gid]["fields"], "milestone": mid}}}
        refuse_cycle(pairs_of(ms, gaps), pairs_of(ms, then), [gid, mid], f"{gid} in {mid}")
        record([("gap.milestone-set", gid, {"milestone": mid, "milestone_was": was, "assigned_by": BY[0]})])
    return gid


def pull(cfg: dict, gap: str, on: bool) -> str:
    with held(cfg):
        _, gaps = read()
        gid = gid_of(gap, gaps)
        record([("gap.pulled" if on else "gap.unpulled", gid,
                 {"pulled": True, "pulled_at": time.time()} if on else {"pulled": None, "pulled_at": None})])
    return gid


def status(cfg: dict) -> str:
    active_max, _ = settings(cfg)
    ms, gaps = read()
    lines, n = [], sum(1 for m in ms.values() if m["state"] == "active" and not upkeep(m))
    for m in sorted(ms.values(), key=lambda m: (ORDER.index(m["state"]) if m["state"] in ORDER else 3, rank_key(m))):
        f = m["fields"]
        rank = f" rank {f['rank']:g}" if number(f.get("rank")) is not None else ""
        up = " upkeep" + (f", ends {time.strftime('%Y-%m-%d %H:%M', time.localtime(f['upkeep_ends']))}"
                          if number(f.get("upkeep_ends")) is not None else "") if upkeep(m) else ""
        lines.append(f"{m['id']}  {m['state']}{rank}{up}  {f.get('title') or ''}".rstrip())
        lines.append(f"  waits on: {waiting(m, ms, n, active_max)}")
        by: dict[str, list[str]] = {}
        for g in gaps_of(m["id"], gaps):
            by.setdefault(g["state"], []).append(g["id"].split("/", 1)[1] + (" (pulled)" if g["fields"].get("pulled") else ""))
        lines.append("  gaps: " + ("; ".join(f"{s} {len(v)} ({', '.join(v)})" for s, v in sorted(by.items())) or
                                   "none (an empty milestone never completes)"))
    old: dict[str, int] = {}
    for g in gaps.values():
        for label in ids_of(g["fields"].get("milestone")):
            if label not in ms:
                old[label] = old.get(label, 0) + 1
    if old:
        lines.append("not yet a milestone (old labels, or a name that is no milestone): " +
                     ", ".join(f"{k} ({v} gaps)" for k, v in sorted(old.items())))
    loops = {n.removesuffix(END) for n in in_cycles(pairs_of(ms, gaps))}     # (one deps.py closed: it knows no milestone)
    if loops:
        lines.append("on a precedence cycle (never taken): " + ", ".join(sorted(loops)))
    return "\n".join(lines) or "no milestones"


def waiting(m: dict, ms: dict[str, dict], n: int, active_max: int) -> str:
    if m["state"] != "waiting":
        return "nothing"
    if upkeep(m):
        return "nothing (an upkeep milestone is always active: the next pass)"
    on = waits_on(m, ms)
    if on:
        return ", ".join(f"{d} ({ms[d]['state']})" if d in ms else f"{d} (no such milestone)" for d in on)
    return f"room under the limit ({n} of {active_max} active)" if n >= active_max else "the next pass"


def main(argv: list[str]) -> int:
    cfg = fac.config()
    fac.cli(cfg)
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    try:
        if cmd == "pass" and not args:
            BY[0] = "milestones"
            for event, item, _ in run_pass(cfg):
                print(f"milestones: {event} {item}", file=sys.stderr)
        elif cmd == "add" and args:
            opts = parse(args[1:], {"--title": str, "--rank": float, "--depends": str, "--upkeep": None})
            print(add(cfg, args[0], opts.get("--title", ""), opts.get("--rank"), "--upkeep" in opts,
                      [x for x in opts.get("--depends", "").split(",") if x]))
        elif cmd == "depends" and len(args) >= 2:
            print(", ".join(depends(cfg, args[0], args[1:])))
        elif cmd == "assign" and len(args) == 2:
            print(assign(cfg, *args))
        elif cmd in ("pull", "unpull") and len(args) == 1:
            print(pull(cfg, args[0], cmd == "pull"))
        elif cmd == "status" and not args:
            print(status(cfg))
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Refused as e:
        print(f"milestones: {e}", file=sys.stderr)
        return 2
    return 0


def parse(args: list[str], spec: dict) -> dict:
    out, i = {}, 0
    while i < len(args):
        k = args[i]
        if k not in spec:
            raise Refused(f"{k}: not an option ({', '.join(spec)})")
        if spec[k] is None:
            out[k], i = True, i + 1
            continue
        if i + 1 >= len(args):
            raise Refused(f"{k}: needs a value")
        try:
            v = spec[k](args[i + 1])
        except ValueError:
            raise Refused(f"{k} {args[i + 1]!r}: not a {spec[k].__name__}") from None
        if isinstance(v, float) and not math.isfinite(v):
            raise Refused(f"{k} {args[i + 1]!r}: not a finite number")
        out[k], i = v, i + 2
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
