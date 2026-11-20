"""Time in each state, the build-review loop and the gates, per gap, from its record alone (dev/README.md, *Time in
each state*): its moves (the fold's, in the record's order, the lease's own among them: leased, dead) and its events.

  times.py            each gap whose record grew since it was last timed (at most MOST a run): `gap.timed`, with
                      time_in, loop_rounds, loop_hours, loop_ended and gates, when they changed
  times.py setpoints  each goal in dev/model/times.yaml set to today's reading of its measure (the last 14 days); a
                      measure with nothing in the window keeps its setpoint

The measures (measure.py NAME, over the gaps that left the state, ended the loop or passed the gate in the window,
whatever their end): in-STATE-hours, loop-hours, loop-rounds, gate-GATE-minutes; the median, and the p90 with -p90."""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402

WAITING = ("open", "ready", "fix", "built", "approved", "queued")       # waiting on someone else: the cheapest to remove
WORKING = ("replan", "planned", "split", "leased", "building", "in-review", "queue-failed", "dead")
GATES = ("implementor", "fast", "review", "unit", "browser", "demo", "push-wait")
EXITS = ("approved", "parked", "dead")
MOST = 50                                      # gaps timed in one run, at most (each is one read of its record)
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
    to the first approval, park or dead letter after its last build; its rounds are its builds. While it is still
    going round, its span runs to its latest move and loop_ended is None."""
    first = next((i for i, m in enumerate(moves) if m["to"] == "building"
                  or (m["to"] == "leased" and m.get("from") in ("ready", "fix"))), None)
    if first is None:
        return {"loop_rounds": 0, "loop_hours": None, "loop_ended": None}
    builds = [i for i, m in enumerate(moves) if m["to"] == "building" and i >= first]
    end = next((m for m in moves[(builds or [first])[-1]:] if m["to"] in EXITS), None)
    last = end or moves[-1]
    return {"loop_rounds": len(builds), "loop_hours": round((float(last["time"]) - float(moves[first]["time"])) / 3600, 4),
            "loop_ended": float(end["time"]) if end else None}


def gates(events: list[dict]) -> dict:
    """{gate: {"minutes", "at"}} summed over the gap's events (in the record's order): the implementor's runs and the
    reviews (build_hours, review_hours), the fast suites (suites_fast), the queue's suites (suites_queue: unit, browser,
    demo), and the push wait (a merge to its push, or the coordinator settling it)."""
    out: dict = {}

    def add(gate: str, minutes: float, at: float) -> None:
        g = out.setdefault(gate, {"minutes": 0.0, "at": 0.0})
        g["minutes"], g["at"] = round(g["minutes"] + minutes, 2), at
    merged = None
    for e in events:
        d, t = e.get("data") or {}, float(e["time"])
        for field, gate in (("build_hours", "implementor"), ("review_hours", "review")):
            if d.get(field) is not None:
                add(gate, float(d[field]) * 60, t)
        if isinstance(d.get("suites_fast"), dict):
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


def timing(d: dict) -> dict:
    """What `gap.timed` says of an item's detail (`ergostat item ID --json`: its moves and its record)."""
    moves = d.get("moves") or []
    evs = d.get("record") or []
    if int(d.get("record_total") or len(evs)) > len(evs):        # its record cut short: read the gap's events whole
        evs = json.loads(fac.ergostat("events", "--item", d["id"], "--type", "gap.*", "--json", "-n", "100000").stdout)
    return {"time_in": visits(moves), **loop(moves), "gates": gates([e for e in evs if e["type"].startswith("gap.")])}


def write(gaps: list[dict]) -> int:
    """`gap.timed` on each gap whose record grew since it was timed, when its timing changed; how many were read."""
    grown = [g for g in gaps if g.get("events") != g["fields"].get("timed_n")]
    for g in grown[:MOST]:
        d = json.loads(fac.ergostat("item", g["id"], "--json").stdout)
        got = timing(d)
        if any(got[k] != g["fields"].get(k) for k in got) or g["fields"].get("timed_n") is None:
            fac.say("gap.timed", g["id"], timed_n=int(d.get("events") or 0) + 1, **got)
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


def reading(name: str, gaps: list[dict], since: float) -> float:
    base = name.removesuffix("-p90")
    return pct(values(base, gaps, since), 0.9 if base != name else 0.5)


def measures() -> list[str]:
    return ([f"in-{s}-hours" for s in WAITING + WORKING] + ["loop-hours", "loop-rounds"]
            + [f"gate-{g}-minutes" for g in GATES])


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
    """Each goal's setpoint set to its measure's reading now (rounded up), where the window has one."""
    gaps = fac.items("gap")
    since = now - 14 * 86400

    def today(m: re.Match) -> str:
        base = m[1].removesuffix("-p90")
        if not values(base, gaps, since):
            return m[0]
        v = reading(m[1], gaps, since)
        return f'auxiliary: {m[1]}, hold: "<= {math.ceil(v * 100) / 100:g}"'
    GOALS.write_text(GOAL.sub(today, GOALS.read_text()))
    return 0


def main() -> int:
    if sys.argv[1:2] == ["setpoints"]:
        fac.cli(fac.config())
        return setpoints(time.time())
    write(fac.items("gap"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
