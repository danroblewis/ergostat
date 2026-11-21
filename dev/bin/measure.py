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
  parks KIND          gaps whose last park was for KIND (parks.KINDS); resumes KIND: parks of KIND resumed (by the
                      program or by hand); parked-hours KIND: their mean hours parked, to the resume or now
  in-STATE-hours, loop-hours, loop-rounds, gate-GATE-minutes (each also with -p90)
                      time in each state, the build-review loop and the gates, per gap, over every gap that left the
                      state, ended the loop or passed the gate in the window, whatever its end (times.py)
  size-accuracy       of merged gaps the planner sized (planned_size and its confidence), the share whose
                      merged_lines fall inside their class: S <= 50 (a net removal too), M 51-150, L 151-400,
                      XL > 400. The window is on the latest merge (merged_at). A gap whose latest merge has no
                      merged_lines is left out of the share, never a hit, and named on stderr.
  size-accuracy-high  the same, of the gaps sized with high confidence only
  planning-cost-share planning dollars (planning_cost_usd: the planner's and the plan review's sessions, the whole
                      reservation of one that failed; 0 for an S gap and a sub-gap) over all AI dollars (ai_cost_usd),
                      summed over the gaps merged in the window that carry planning_cost_usd. A gap without it is left
                      out, never counted as 0; one whose planning cost is negative, not a number or above its total is
                      left out too, and named on stderr. It says where the money went, not that less planning is safe.
First-pass-yield, first-pass-with-lessons, plan-risks-held, splits-clean, the two size measures and planning-cost-share
have no value with nothing to measure.

  coverage-below-floor  the modules whose share of statements the unit suite on main ran is under [code_health]
                      coverage_floor, from the latest coverage report (scripts/coverage_report.py, under run/coverage/)
  coverage NAME       one module's share (NAME: its path, e.g. ergostat/model.py)
These two read no window: they have no value (exit 1) with no report, an unreadable one, or the latest more than
STALE of main's first-parent commits (its merges) old; never 0 or 1 for a report that cannot be read."""

from __future__ import annotations

import json
import statistics
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import parks  # noqa: E402
import times  # noqa: E402

WINDOW = 14 * 86400


def recent(rows: list[dict], field: str, since: float) -> list[dict]:
    return [r for r in rows if float(r["fields"].get(field) or 0) >= since]


def median(xs: list[float]) -> float:
    return round(statistics.median(xs), 3) if xs else 0.0


def reading(name: str, now: float | None = None, kind: str = "") -> float:
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
    if name == "planning-cost-share":
        return planning_cost_share(since)
    gaps = fac.items("gap")
    if name in ("parks", "resumes", "parked-hours"):                   # by kind (parks.py): its last park, per gap
        if kind not in parks.KINDS:
            raise SystemExit(f"measure.py {name}: no kind {kind!r} (one of {', '.join(parks.KINDS)})")
        mine = [g["fields"] for g in recent(gaps, "parked_at", since) if g["fields"].get("parked_for") == kind]
        if name == "parks":
            return float(len(mine))
        if name == "resumes":
            return float(sum(g["fields"].get("resumed_for") == kind and float(g["fields"].get("resumed_at") or 0) >= since
                             for g in gaps))
        return round(statistics.mean([(float(g["resumed_at"]) if g.get("resumed_as") else now) - float(g["parked_at"])
                                      for g in mine]) / 3600, 2) if mine else 0.0
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


def planning_cost_share(since: float) -> float:
    """Planning dollars over AI dollars, of merged gaps that carry planning_cost_usd (the field present, a number from 0
    to the gap's ai_cost_usd); no value with none, or with a total of 0."""
    num = lambda v: type(v) in (int, float) and v == v  # noqa: E731
    carried = [g for g in recent(fac.items("gap"), "merged_at", since) if g["state"] == "merged"
               and "planning_cost_usd" in g["fields"]]
    fit = lambda f: num(p := f["planning_cost_usd"]) and num(t := f.get("ai_cost_usd", 0)) and 0 <= p <= t  # noqa: E731
    ok = [g["fields"] for g in carried if fit(g["fields"])]
    if left := [g["id"] for g in carried if not fit(g["fields"])]:
        print(f"planning-cost-share: left out, planning cost not within 0 and its total: {', '.join(left)}",
              file=sys.stderr)
    total = sum(f.get("ai_cost_usd", 0) for f in ok)
    if not total:
        raise SystemExit("planning-cost-share: no value yet (no merged gap with a planning cost and AI money)")
    return round(sum(f["planning_cost_usd"] for f in ok) / total, 3)


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


STALE = 20                                              # main's merges after which a coverage report says nothing


def coverage_report(cfg: dict) -> dict:
    """The latest coverage report of main, by its ``seq`` (never by a file's time), among those whose commit is on
    main (a run whose merge was undone measured a commit main never had); SystemExit (no value) when there is none,
    any is unreadable (it may be the latest), or main has moved more than STALE first-parent commits past it."""
    repo, base = fac.path(cfg, "checkout"), cfg["git"]["base"]
    found = []
    for p in sorted(fac.path(cfg, "run").joinpath("coverage").glob("*/coverage.json")):
        try:
            r = json.loads(p.read_text())
            found.append((int(r["seq"]), str(r["main"]), {m: float(v["share"]) for m, v in r["modules"].items()}))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise SystemExit(f"coverage: no value (an unreadable report: {p})") from None
    on_main = [f for f in found if fac.git_ok(repo, "merge-base", "--is-ancestor", f[1], base)]
    if not on_main:
        raise SystemExit("coverage: no value (no coverage report of a commit on main)")
    seq, sha, shares = max(on_main, key=lambda f: f[0])
    since = int(fac.git(repo, "rev-list", "--count", "--first-parent", f"{sha}..{base}"))
    if since > STALE:
        raise SystemExit(f"coverage: no value (the latest report, {sha[:12]}, is {since} merges behind {base})")
    return shares


def coverage_reading(name: str, args: list[str]) -> float:
    cfg = fac.config()
    shares = coverage_report(cfg)
    if name == "coverage":
        if len(args) != 1 or args[0] not in shares:
            raise SystemExit(f"coverage: no value (no module {' '.join(args)!r} in the report)")
        return shares[args[0]]
    floor = (cfg.get("code_health") or {}).get("coverage_floor")
    if not isinstance(floor, int | float) or not 0 <= floor <= 1:
        raise SystemExit(f"coverage-below-floor: no value ([code_health] coverage_floor is {floor!r}, not a share)")
    return float(sum(s < floor for s in shares.values()))


if __name__ == "__main__":
    name = sys.argv[1]
    if name in ("coverage", "coverage-below-floor"):
        print(coverage_reading(name, sys.argv[2:]))
    else:
        print(reading(name, kind=sys.argv[2] if len(sys.argv) > 2 else ""))
