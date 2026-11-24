"""Time in each state, the build-review loop and the gates, per gap, from its record alone (dev/README.md, *Time in
each state*): its moves (the fold's, in the record's order, the lease's own among them: leased, dead) and its events.

  times.py            each gap whose record grew since it was last read (run/times.json; at most MOST a run):
                      `gap.timed`, with time_in, loop_rounds, loop_hours, loop_ended, gates and catches (with
                      catch_times, when each was), when they changed
  times.py setpoints  each goal in dev/model/times.yaml set to today's reading of its measure (the last 14 days); a
                      measure with nothing in the window keeps its setpoint

The measures (measure.py NAME, over the gaps that left the state, ended the loop or passed the gate in the window,
whatever their end): in-STATE-hours, loop-hours, loop-rounds, gate-GATE-minutes; the median, and the p90 with -p90.
gate-catches-GATE: the gate's catches (CATCHING) in the window, by each catch's own time, summed over the gaps."""

from __future__ import annotations

import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

# Waiting on someone else (the cheapest to remove): open and replan for the planner, planned for the plan review, split
# for its sub-gaps, ready and fix for the implementor, built for the reviewer, approved for the queue, queue-failed for
# triage, dead for a park. Working, a run holds it: leased (the planner's, plan review's and triage's whole run, the
# others' start and the queue's wait for its lock), building, in-review, queued (the queue's run, from its gap.queued:
# the merge, its suites).
WAITING = ("open", "replan", "planned", "split", "ready", "fix", "built", "approved", "queue-failed", "dead")
WORKING = ("leased", "building", "in-review", "queued")
GATES = ("implementor", "fast", "review", "unit", "browser", "demo", "push-wait")
EXITS = ("approved", "parked", "dead", "closed")
# The gates that send a gap back, by the sender the record names (an allowlist: any other is counted as unlisted): the
# queue (queue.py), triage, review, the plan lint (plan.py), measure-runs (manage.py), the implementor's stray refusals
CATCHING = ("queue", "triage", "review", "lint", "measure-runs", "strays")
SNAPSHOT = "ergostat.item.snapshot"            # a gap's older events rolled up into one (ergostat/rollup.py)
MOST = 50                                      # gaps timed in one run, at most (each is one read of its record)
LONGEST = 100_000                              # a gap's events read whole, at most; a longer one is unreadable
GOALS = fac.HERE / "model" / "times.yaml"
GOAL = re.compile(r'auxiliary: ([a-z0-9-]+), hold: "<= ([0-9.]+)"')


def visits(moves: list[dict]) -> dict:
    """{state: {"hours", "visits", "left"}}: each closed visit (ended by the next move), summed per state; the visit
    it is in now is not counted until it ends (status.py shows it apart)."""
    out: dict = {}
    for m, nxt in zip(moves, moves[1:], strict=False):
        v = out.setdefault(m["to"], {"hours": 0.0, "visits": 0, "left": 0.0})
        v["hours"] = round(v["hours"] + max(0.0, float(nxt["time"]) - float(m["time"])) / 3600, 4)
        v["visits"] += 1
        v["left"] = float(nxt["time"])
    return out


def loop(moves: list[dict]) -> dict:
    """The build-review loop: from the first time the gap is taken to build (leased from ready or fix, else started)
    to the first approval, park, close or dead letter after its last build and its last send-back (a send-back after an
    approval, by the queue or triage, reopens the loop); its rounds are its builds. While it is still going round, its
    span runs to its latest move and loop_ended is None."""
    first = next((i for i, m in enumerate(moves) if m["to"] == "building"
                  or (m["to"] == "leased" and m.get("from") in ("ready", "fix"))), None)
    if first is None:
        return {"loop_rounds": 0, "loop_hours": None, "loop_ended": None}
    builds = [i for i, m in enumerate(moves) if m["to"] == "building" and i >= first]
    back = [i for i, m in enumerate(moves) if m["to"] == "fix" and i >= first]
    end = next((m for m in moves[max(builds + back + [first]):] if m["to"] in EXITS), None)
    last = end or moves[-1]
    return {"loop_rounds": len(builds), "loop_hours": round((float(last["time"]) - float(moves[first]["time"])) / 3600, 4),
            "loop_ended": float(end["time"]) if end else None}


def gates(events: list[dict], base: dict | None = None, merged: float | None = None) -> dict:
    """{gate: {"minutes", "at"}} summed over the gap's events (in the record's order), added to ``base`` (the gates of
    what was rolled up before them; ``merged``, a merge in it not yet pushed): the implementor's runs and the
    reviews (build_hours, review_hours), the fast suites (suites_fast), the queue's suites (suites_queue: unit, browser,
    demo), and the push wait (a merge to its push, or the coordinator settling it)."""
    out: dict = {g: dict(v) for g, v in (base or {}).items()}

    def add(gate: str, minutes: float, at: float) -> None:
        g = out.setdefault(gate, {"minutes": 0.0, "at": 0.0})
        g["minutes"], g["at"] = round(g["minutes"] + minutes, 2), at
    for e in events:
        d, t = e.get("data") or {}, float(e["time"])
        for field, gate in (("build_hours", "implementor"), ("review_hours", "review")):
            if d.get(field) is not None:
                add(gate, float(d[field]) * 60, t)
        if d.get("fast_seconds") is not None:                   # every try in the round (implement.py)
            add("fast", float(d["fast_seconds"]) / 60, t)
        elif isinstance(d.get("suites_fast"), dict):            # a build from before it: its last try only
            add("fast", sum(float((d["suites_fast"].get(s) or {}).get("seconds") or 0) for s in ("ruff", "unit")) / 60, t)
        for s in ("unit", "browser", "demo"):
            if isinstance(d.get("suites_queue"), dict) and isinstance(d["suites_queue"].get(s), dict):
                add(s, float(d["suites_queue"][s].get("seconds") or 0) / 60, t)
        if e["type"] == "gap.merged":
            merged = t
        elif merged is not None and (e["type"] in ("gap.pushed", "gap.push-settled")
                                     or (e["type"] == "gap.push-asked" and d.get("push") == "pushed")):
            add("push-wait", (t - merged) / 60, t)
            merged = None
    return out


def catches(events: list[dict], base: dict | None, gid: str) -> dict:
    """{gate: [time, ...]}: each time a gate sent the gap back (`gap.sent-back` by its sent_back_by, the plan review's
    `gap.plan-sent-back` by its plan_sent_back_by) or the implementor refused its strays (a `gap.measured` naming
    them), added to ``base``. A sender not in CATCHING is counted under `unlisted` and named on stderr."""
    out: dict = {g: list(v) for g, v in (base or {}).items()}
    for e in events:
        d = e.get("data") or {}
        by = (d.get("sent_back_by") if e["type"] == "gap.sent-back" else d.get("plan_sent_back_by")
              if e["type"] == "gap.plan-sent-back" else "strays"
              if e["type"] == "gap.measured" and isinstance(d.get("suites_fast"), dict) and d["suites_fast"].get("stray")
              else None)
        if by is None and e["type"] not in ("gap.sent-back", "gap.plan-sent-back"):
            continue
        if by not in CATCHING:
            print(f"times.py: {gid}: {e['type']} by an unlisted sender {by!r}, counted under unlisted", file=sys.stderr)
            by = "unlisted"
        out.setdefault(by, []).append(float(e["time"]))
    return out


def timing(d: dict) -> dict:
    """What `gap.timed` says of an item's detail (`ergostat item ID --json`: its moves and its record). A record rolled
    up (ergostat/rollup.py) starts with a snapshot: the moves are in it, and the gates as its last `gap.timed` said them
    (its `set`), so only the events after it are added. A snapshot with no gates in it (never timed before it was
    rolled up) leaves them unknown: None, not counted in any gate's measure."""
    moves = d.get("moves") or []
    evs = d.get("record") or []
    total = int(d.get("record_total") or len(evs))
    if total > len(evs):                    # its record cut short (the last 500): its events whole, `ergostat event`
        if total > LONGEST:
            raise ValueError(f"{d['id']}: {total} events, past the {LONGEST} read whole")
        n = total + 1000                    # room for events said since; a page this full may be cut: unreadable
        evs = json.loads(fac.ergostat("event", "--item", d["id"], "--type", f"gap.*,{SNAPSHOT}", "--json",
                                      "-n", str(n)).stdout)
        if len(evs) >= n:
            raise ValueError(f"{d['id']}: its events grew past {n} while read")
    evs = [e for e in evs if e["type"].startswith("gap.") or e["type"] == SNAPSHOT]
    snap = max((i for i, e in enumerate(evs) if e["type"] == SNAPSHOT), default=None)
    base, merged, caught = None, None, None
    if snap is not None:
        s = evs[snap]
        if not isinstance((s.get("set") or {}).get("gates"), dict):
            return {"time_in": visits(moves), **loop(moves), "gates": None, "catches": None, "catch_times": None}
        base, r = s["set"]["gates"], (s.get("data") or {}).get("rollup") or {}
        if r.get("state") == "merged" and float((base.get("push-wait") or {}).get("at") or 0) < float(r.get("entered") or 0):
            merged = float(r["entered"])                       # merged inside the snapshot, its push not yet seen
        caught = s["set"].get("catch_times")
        evs = evs[snap + 1:]
    got = catches(evs, caught, d.get("id", "?")) if snap is None or isinstance(caught, dict) else None
    return {"time_in": visits(moves), **loop(moves), "gates": gates(evs, base, merged),     # (catches unknown: None,
            "catches": got and {g: len(ts) for g, ts in got.items()}, "catch_times": got}   # timed before they were)


def write(gaps: list[dict], marks: Path) -> int:
    """`gap.timed` on each gap whose record grew since it was last read, when its timing changed; how many were read.
    The bookmark (each gap's count of events read) is kept in ``marks``, outside the record, and moved on every read,
    so an event that changes no timing is read once; the gaps never read come first. An unreadable bookmark counts as
    none: every gap is read again, MOST a run, and only a changed timing is written. A gap that cannot be read keeps
    its bookmark (read again next run) and does not stop the others; the bookmark is saved, then the run fails
    (SystemExit) naming each one."""
    try:
        seen = json.loads(marks.read_text())
        seen = seen if isinstance(seen, dict) else {}
    except (OSError, ValueError):
        seen = {}
    grown = sorted((g for g in gaps if g.get("events") != seen.get(g["id"])), key=lambda g: g["id"] in seen)
    bad = []
    for g in grown[:MOST]:
        try:
            d = json.loads(fac.ergostat("item", g["id"], "--json").stdout)
            got = timing(d)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as e:   # unread; a bug: its traceback
            bad.append(f"{g['id']}: {e}"[:300])
            continue
        seen[g["id"]] = int(d.get("events") or 0)
        if any(got[k] != g["fields"].get(k) for k in got):
            fac.say("gap.timed", g["id"], **got)
            seen[g["id"]] += 1                          # its own gap.timed; anything else since is read next run
    ids = {g["id"] for g in gaps}
    tmp = marks.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v for k, v in seen.items() if k in ids}))
    tmp.replace(marks)
    if bad:
        raise SystemExit("times.py: unreadable, read again next run:\n" + "\n".join(bad))
    return len(grown[:MOST])


def pct(xs: list[float], p: float) -> float:
    """The p-th quantile by nearest rank (0 with nothing to measure, as measure.py's medians)."""
    xs = sorted(xs)
    if not xs:
        return 0.0
    return round(statistics.median(xs) if p == 0.5 else xs[max(0, math.ceil(p * len(xs)) - 1)], 3)


def values(name: str, gaps: list[dict], since: float) -> list[float]:
    """A measure's values, one per gap that left the state, ended the loop or passed the gate since ``since``."""
    fs = [g["fields"] for g in gaps]
    if m := re.fullmatch(r"in-([a-z-]+)-hours", name):
        return [float(v["hours"]) for f in fs if (v := (f.get("time_in") or {}).get(m[1])) and float(v["left"]) >= since]
    if name in ("loop-hours", "loop-rounds"):
        return [float(f["loop_" + name[5:]]) for f in fs if float(f.get("loop_ended") or 0) >= since]
    if m := re.fullmatch(r"gate-([a-z-]+)-minutes", name):
        return [float(v["minutes"]) for f in fs if (v := (f.get("gates") or {}).get(m[1])) and float(v["at"]) >= since]
    raise SystemExit(f"measure.py: no measure {name!r}")


def caught(gate: str, gaps: list[dict], since: float) -> float:
    """gate-catches-GATE: the gate's catches with their time in the window, over every gap; a gap whose catches are
    unknown (rolled up, or not timed, before they were counted) is left out and counted on stderr."""
    if gate not in (*CATCHING, "unlisted"):
        raise SystemExit(f"measure.py: no gate {gate!r} catches (one of {', '.join(CATCHING)}, unlisted)")
    known = [f["catch_times"] for g in gaps if isinstance((f := g["fields"]).get("catch_times"), dict)]
    if len(known) < len(gaps):
        print(f"gate-catches-{gate}: left out, {len(gaps) - len(known)} gap(s) whose catches are unknown", file=sys.stderr)
    return float(sum(float(t) >= since for c in known for t in c.get(gate) or []))


def reading(name: str, gaps: list[dict], since: float) -> float:
    if m := re.fullmatch(r"gate-catches-([a-z-]+)", name):
        return caught(m[1], gaps, since)
    base = name.removesuffix("-p90")
    return pct(values(base, gaps, since), 0.9 if base != name else 0.5)


def measures() -> list[str]:
    return ([f"in-{s}-hours" for s in WAITING + WORKING] + ["loop-hours", "loop-rounds"]
            + [f"gate-{g}-minutes" for g in GATES] + [f"gate-catches-{g}" for g in (*CATCHING, "unlisted")])


def quiet(gaps: list[dict], now: float, days: int = 30) -> list[str] | None:
    """The gates in CATCHING with no catch in the last ``days``, over the gaps whose catches are known; None (unknown,
    never all quiet) when no gap's are."""
    if not any(isinstance(g["fields"].get("catch_times"), dict) for g in gaps):
        return None
    return [g for g in CATCHING if not caught(g, gaps, now - days * 86400)]


def goals() -> dict:
    """Each measure's setpoint (a ceiling), from dev/model/times.yaml."""
    return {m[1]: float(m[2]) for m in GOAL.finditer(GOALS.read_text())}


def table(gaps: list[dict], since: float, now: float) -> list[str]:
    """The per-state table: waiting states first, then working, the loop and the gates; each with the gaps in it now
    (and the oldest of them), and the median and p90 over those that left it in the window, against its goals."""
    held = goals()

    def row(label: str, name: str, unit: str, here: str = "") -> str:
        xs = values(name, gaps, since)
        goal = "/".join(f"{held[n]:g}" if n in held else "-" for n in (name, name + "-p90"))
        return (f"  {label:<14} {here:<12} {pct(xs, 0.5):>8g} {pct(xs, 0.9):>8g} {len(xs):>4}  {goal} {unit}")
    out = [f"  {'':<14} {'now (oldest)':<12} {'median':>8} {'p90':>8} {'n':>4}  goal median/p90"]
    for title, states in (("waiting", WAITING), ("working", WORKING)):
        out.append(f" {title}")
        for s in states:
            now_in = [now - float(g.get("entered") or now) for g in gaps if g["state"] == s]
            here = f"{len(now_in)} ({max(now_in) / 3600:.1f}h)" if now_in else ""
            out.append(row(s, f"in-{s}-hours", "h", here))
    out.append(" loop")
    out += [row("span", "loop-hours", "h"), row("rounds", "loop-rounds", "")]
    out.append(" gates")
    out += [row(g, f"gate-{g}-minutes", "min") for g in GATES]
    return out


def setpoints(now: float) -> int:
    """Each goal's setpoint set to its measure's reading now (rounded up), where the window has one; the file's
    `# setpoints:` line records when, over how many gaps, and how many were set."""
    gaps = fac.items("gap")
    since = now - 14 * 86400
    set_ = []

    def today(m: re.Match) -> str:
        base = m[1].removesuffix("-p90")
        if not values(base, gaps, since):
            return m[0]
        v = reading(m[1], gaps, since)
        set_.append(m[1])
        return f'auxiliary: {m[1]}, hold: "<= {math.ceil(v * 100) / 100:g}"'
    text = GOAL.sub(today, GOALS.read_text())
    if not re.search(r"(?m)^# setpoints: ", text):
        raise SystemExit(f"times.py: no `# setpoints:` line in {GOALS}: when they were derived would go unrecorded")
    stamp = (f"# setpoints: derived from the record on {time.strftime('%Y-%m-%d', time.localtime(now))}, over "
             f"{len(gaps)} gaps: {len(set_)} holds set, the rest kept (no gap in their window)")
    GOALS.write_text(re.sub(r"(?m)^# setpoints: .*$", lambda _: stamp, text, count=1))
    return 0


def main() -> int:
    if sys.argv[1:2] == ["setpoints"]:
        fac.cli(fac.config())
        return setpoints(time.time())
    write(fac.items("gap"), fac.run_dir(fac.config()) / "times.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
