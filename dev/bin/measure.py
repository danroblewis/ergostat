"""The factory's measures, read from its own record: `measure.py NAME` prints one reading (0 when nothing in the
window to measure). The window is the last 14 days.

  cycle-hours         median hours from ready to merged, over the gaps merged
  build-hours         median hours the implementor's runs took per merged gap (every round)
  review-hours        median hours its reviews took per merged gap
  queue-wait-hours    median hours from approved to the queue starting on it, per merged gap (every attempt)
  queue-minutes       median minutes of a queue run (merge and suites), over the gaps the queue ran
  suite-minutes       median minutes of the queue's suites (unit, browser, demo) on the runs that passed
  first-pass-yield    the share of first reviews whose verdict was merge
  fix-rounds          mean rounds sent back to the implementor per merged gap
  flake-rate          flaky retries per queue run
  cost-per-merged     dollars of AI sessions per merged gap (every round, implementor and reviewer)
  interventions-trend the coordinator's interventions over the last 7 days less the 7 before"""

from __future__ import annotations

import statistics
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402

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
        return round(sum(r["fields"].get("verdict") == "merge" for r in first) / len(first), 3) if first else 0.0
    gaps = fac.items("gap")
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


if __name__ == "__main__":
    print(reading(sys.argv[1]))
