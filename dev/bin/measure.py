"""The factory's measures, read from its own record: `measure.py NAME` prints one reading, over the last 14 days: 0
when nothing in the window to measure, but for the six named at the end, which have no value then
(they exit 1, as ergostat's own measures do).

  cycle-hours         median hours from ready to merged, over the gaps merged
  build-hours         median hours the implementor's runs took per merged gap (every round)
  review-hours        median hours its reviews took per merged gap
  queue-wait-hours    median hours from approved to the queue starting on it, per merged gap (every attempt)
  queue-minutes       median minutes of a queue run (merge and suites), over the gaps the queue ran
  merges-per-hour     gaps merged per hour of the queue's running: the gaps merged over the hours of every queue run
                      that ended in the window (each run's whole length once, whatever it landed: `queue_runs`)
  suite-minutes       median minutes of the queue's suites (unit, browser, demo) on the runs that passed
  first-pass-yield    the share of first reviews whose verdict was merge
  fix-rounds          mean rounds sent back to the implementor per merged gap
  flake-rate          flaky retries per queue run
  cost-per-merged     dollars of AI sessions per merged gap (every round, implementor and reviewer)
  interventions-trend the coordinator's interventions over the last 7 days less the 7 before
  lessons-per-brief   review lessons carried per first implementor brief (knowledge.py)
  first-pass-with-lessons  first-pass-yield, of the gaps whose first brief carried review lessons
  plan-risks-held     of planned gaps first reviewed, the share whose review found none of the lesson classes their
                      plan named as risks (the librarian's classes)
  splits-clean        of sub-gaps merged, the share approved on their first review
  in-STATE-hours, loop-hours, loop-rounds, gate-GATE-minutes (each also with -p90)
                      time in each state, the build-review loop and the gates, per gap, over every gap that left the
                      state, ended the loop or passed the gate in the window, whatever its end (times.py)
  size-accuracy       of merged gaps the planner sized (planned_size and its confidence), the share whose merged_lines fall
                      inside their class: S <= 50 (a net removal too), M 51-150, L 151-400, XL > 400. The window is
                      on the latest merge (merged_at). A gap whose latest merge has no merged_lines is left out of
                      the share, never a hit, and named on stderr.
  size-accuracy-high  the same, of the gaps sized with high confidence only
First-pass-yield, first-pass-with-lessons, plan-risks-held, splits-clean and the two size measures have no value with
nothing to measure."""

from __future__ import annotations

import statistics
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import times  # noqa: E402

WINDOW = 14 * 86400


def recent(rows: list[dict], field: str, since: float) -> list[dict]:
    return [r for r in rows if float(r["fields"].get(field) or 0) >= since]


def median(xs: list[float]) -> float:
    return round(statistics.median(xs), 3) if xs else 0.0


def reading(name: str, now: float | None = None) -> float:
    now = now or time.time()
    since = now - WINDOW
    if name == "interventions-trend":
        rows = fac.items("intervention")
        at = [float(r["fields"].get("recorded_at") or r.get("first") or 0) for r in rows]
        return float(sum(t >= now - 7 * 86400 for t in at) - sum(now - 14 * 86400 <= t < now - 7 * 86400 for t in at))
    if name == "first-pass-yield":
        first = [r for r in recent(fac.items("review"), "written_at", since) if r["fields"].get("round") == 1]
        if not first:
            raise SystemExit("first-pass-yield: no value yet (no first review in the window)")   # not 0: unknown
        return round(sum(r["fields"].get("verdict") == "merge" for r in first) / len(first), 3)
    if name in KNOWLEDGE:
        return knowledge_reading(name, since)
    if name in ("size-accuracy", "size-accuracy-high"):
        return size_accuracy(name, since)
    gaps = fac.items("gap")
    if name.removesuffix("-p90") in times.measures():
        return times.reading(name, gaps, since)
    merged = [g["fields"] for g in recent(gaps, "merged_at", since) if g["state"] == "merged"]
    f = lambda k: [float(g.get(k) or 0) for g in merged]  # noqa: E731
    if name == "cycle-hours":
        return median([(float(g["merged_at"]) - float(g.get("ready_at") or g["merged_at"])) / 3600 for g in merged])
    if name in ("build-hours", "review-hours", "queue-wait-hours"):
        return median(f(name.replace("-", "_")))
    if name == "fix-rounds":
        return round(statistics.mean(f("fix_rounds")), 3) if merged else 0.0
    if name == "cost-per-merged":
        return round(sum(f("ai_cost_usd")) / len(merged), 2) if merged else 0.0
    if name == "merges-per-hour":                       # every run that ended in the window, its whole length once
        runs = {r["run"]: float(r.get("minutes") or 0) for g in gaps for r in g["fields"].get("queue_runs") or []
                if float(r.get("at") or 0) >= since}
        hours = sum(runs.values()) / 60
        return round(len(merged) / hours, 3) if hours else 0.0
    queued = [g["fields"] for g in recent(gaps, "queued_at", since)]
    if name == "queue-minutes":
        return median([float(g["queue_minutes"]) for g in queued if g.get("queue_minutes")])
    if name == "suite-minutes":
        runs = [g.get("suites_queue") or {} for g in merged]
        return median([sum(float((r.get(s) or {}).get("seconds") or 0) for s in ("unit", "browser", "demo")) / 60
                       for r in runs if r])
    if name == "flake-rate":
        runs = sum(int(g.get("queue_attempts") or 0) for g in queued)
        return round(sum(int(g.get("retries") or 0) for g in queued) / runs, 3) if runs else 0.0
    raise SystemExit(f"measure.py: no measure {name!r}")


KNOWLEDGE = ("lessons-per-brief", "first-pass-with-lessons", "plan-risks-held", "splits-clean")


def share(xs: list[bool], name: str) -> float:
    if not xs:
        raise SystemExit(f"{name}: no value yet (nothing to measure in the window)")
    return round(sum(xs) / len(xs), 3)


def size_class(lines: int) -> str:
    return "S" if lines <= 50 else "M" if lines <= 150 else "L" if lines <= 400 else "XL"


def size_accuracy(name: str, since: float) -> float:
    """The planner's planned_size, never `size`: the groomer (gap.groomed) regrades `size` on its own scale."""
    sized = [g for g in recent(fac.items("gap"), "merged_at", since) if g["state"] == "merged"
             and g["fields"].get("planned_size") and g["fields"].get("size_confidence") in (
                 ("high",) if name == "size-accuracy-high" else ("low", "medium", "high"))]
    counted = lambda f: type(f.get("merged_lines")) is int and not f.get("merged_lines_error")  # noqa: E731
    if left := [g["id"] for g in sized if not counted(g["fields"])]:
        print(f"{name}: left out, no merged_lines: {', '.join(left)}", file=sys.stderr)
    return share([size_class(g["fields"]["merged_lines"]) == g["fields"]["planned_size"] for g in sized
                  if counted(g["fields"])], name)


def knowledge_reading(name: str, since: float) -> float:
    gaps = {g["id"]: g for g in fac.items("gap")}
    carried = {i: next((len([k for k in c.get("knowledge") or [] if k.startswith("lesson-")])
                        for c in g["fields"].get("contexts") or [] if c.get("role") == "implementor"), None)
               for i, g in gaps.items()}
    if name == "lessons-per-brief":
        n = [carried[i] for i, g in gaps.items() if carried[i] is not None
             and float(g["fields"].get("building_at") or 0) >= since]
        return round(statistics.mean(n), 2) if n else 0.0
    if name == "splits-clean":
        return share([bool(g["fields"].get("first_pass")) for g in recent(list(gaps.values()), "merged_at", since)
                      if g["fields"].get("parent")], name)
    first = [r for r in recent(fac.items("review"), "written_at", since) if r["fields"].get("round") == 1]
    if name == "first-pass-with-lessons":
        return share([r["fields"].get("verdict") == "merge" for r in first if carried.get(r["fields"].get("gap"))], name)
    risks = {r["id"]: set(gaps.get(r["fields"].get("gap"), {}).get("fields", {}).get("risks") or []) for r in first}
    return share([not (risks[r["id"]] & set(r["fields"].get("classes") or [])) for r in first if risks[r["id"]]], name)


if __name__ == "__main__":
    print(reading(sys.argv[1]))
