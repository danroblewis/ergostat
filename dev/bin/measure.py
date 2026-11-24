"""The factory's measures, read from its own record: `measure.py NAME` prints one reading, over the last 14 days: 0
when nothing in the window to measure, but for the twelve named at the end, which have no value then
(they exit 1, as ergostat's own measures do). Run by the engine, the readings of one kind share one listing of it
begun at most listing.SHARE (120) seconds before (listing.py): readings due together make one listing, not one each.

  cycle-hours         median hours from ready to merged, over the gaps merged
  build-hours         median hours the implementor's runs took per merged gap (every round)
  review-hours        median hours its reviews took per merged gap
  queue-wait-hours    median hours from approved to the queue starting on it, per merged gap (every attempt)
  queue-minutes       median minutes of a queue run (merge and suites), over the gaps the queue ran
  merges-per-hour     gaps merged per hour of the queue's running: the gaps merged over the hours of every queue run
                      that ended in the window (each run's whole length once, whatever it landed: `queue_runs`)
  suite-minutes       median minutes of the queue's suites (unit, browser, demo) on the runs that passed
  first-pass-yield    the share of first reviews whose verdict was merge, an env-park's review left out
  env-parks           parks caused by done items the implementor's container cannot do (plan.py env_needs): gaps
                      parked at plan time for the owner (env_parked_at), and reviews that parked such a gap for a need
  fix-rounds          mean rounds sent back to the implementor per merged gap
  flake-rate          flakes per queue run: triage's retries plus the runs the queue excused as flakes (a landed gap's
                      suites_queue.excused, each run once by batch_id), over the queue runs, as merges-per-hour counts them
  cost-per-merged     dollars of AI sessions per merged gap (every round, implementor and reviewer)
  tool-denials        tool calls refused to the AI sessions (sessions.py), over the sessions that said; one with no
                      result (a timeout, a crash) or a result silent on them is left out and counted on stderr, and
                      with none that said there is no value (exit 1)
  tool-denials-unknown  the sessions left out of tool-denials
  refused-commands-per-session  the mean Bash calls refused per session (its `denied` list), over the sessions that
                      said; the others left out and counted on stderr, and with none that said no value (exit 1)
  interventions-trend the coordinator's interventions over the last 7 days less the 7 before
  lessons-per-brief   review lessons carried per first implementor brief (knowledge.py)
  first-pass-with-lessons  first-pass-yield, of the gaps whose first brief carried review lessons
  lessons-recurring   classes reviews found (the librarian's, every round) that the reviewed gap's first implementor
                      brief carried: the lesson failing as a guarantee. A review with no classes recorded, or whose
                      gap's first brief is not found, is left out and counted on stderr; none counted: no value
  plan-risks-held     of planned gaps first reviewed, the share whose review found none of the lesson classes their
                      plan named as risks (the librarian's classes)
  splits-clean        of sub-gaps merged, the share approved on their first review
  splits-covered      of split parents whose first join verdict (the first of join_verdicts, in record order, never
                      by its `at`) is in the window, the share whose first verdict was covered (short then covered
                      counts as not covered)
  split-budgets-held  of sub-gaps (a `parent`) merged in the window, the share whose net_lines are at or under their
                      own definition's `## Size budget`; a definition, budget or net_lines it cannot read: not held
  split-joins         split parents with at least one join verdict, over the whole record (no window)
  split-overhead      the median, over split parents judged covered in the window (judged_at: the join records no
                      merged_at), of the parent's own ai_cost_usd plus
                      each child's (join sub-gaps and continuations too; a stopped sub-gap a continuation replaced:
                      its cost, not its lines) over the median ai_cost_usd of merged unsplit gaps (no
                      parent, no children, a counted merged_lines; whole record) in the size class of the children's
                      summed merged_lines. A parent with a child not merged, with no merged_lines (or an error) or
                      no ai_cost_usd, with no ai_cost_usd of its own, or whose class has no unsplit gap, is left out
                      and named on stderr, never a ratio of 0 or 1
  manager-triggers-per-session, manager-actions-per-session   the mean a pipeline manager session was given, and did
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
  main-still-minutes, main-stalled-minutes, batch-runs, batch-first-green, crash-lost-minutes, gaps-landed-per-hour
                      the merge pipeline's, from its batch items (landing.py says each); main-stalled-why prints
                      the goal main-moving's reason: the current batch, its run and the cause
  verify-escapes, verify-reverts, merge-to-verified-hours, suite-runs-per-merged-gap
                      merge first, verify after (verify.py reading()): red verifications that found a merge, merges
                      reverted, the median hours from a merge to its verification, and the batches' and the
                      verifications' suite runs per gap merged (today's queue alone while the lane is off)
  planning-cost-share planning dollars (planning_cost_usd: the planner's sessions, and the removed plan review's, the whole
                      reservation of one that failed; 0 for an S gap and a sub-gap) over all AI dollars (ai_cost_usd),
                      summed over the gaps merged in the window that carry planning_cost_usd. A gap without it is left
                      out, never counted as 0; one whose planning cost is negative, not a number or above its total is
                      left out too, and named on stderr. It says where the money went, not that less planning is safe.
Flake-rate, first-pass-yield, first-pass-with-lessons, lessons-recurring, plan-risks-held, splits-clean, splits-covered, split-budgets-held,
split-overhead, the two size measures and planning-cost-share have no value with nothing to measure.

  coverage-below-floor  the modules whose share of statements the unit suite on main ran is under [code_health]
                      coverage_floor, from the latest coverage report (scripts/coverage_report.py, under run/coverage/)
  coverage NAME       one module's share (NAME: its path, e.g. ergostat/model.py)
These two read no window: they have no value (exit 1) with no report, an unreadable one, or the latest more than
STALE of main's first-parent commits (its merges) old; never 0 or 1 for a report that cannot be read.

  code-net-lines, code-long-functions, code-duplicates, code-dead-candidates   sums over scripts/code_evidence.py's
                      rows on the checkout's main: net lines of ergostat/, dev/bin/ and scripts/, functions over 60
                      lines, duplicate function bodies, dead candidates
  code-coverage       the statement-weighted share (covered over statements) of the latest coverage report, as above
  NAME-change         one of these five's change over the last TREND of main's merges: the reading at the latest seq
                      less the earliest within TREND seqs of it, from run/code-measures.jsonl
Each code reading is stamped there with the seq and sha it measured (main's; the report's for code-coverage). A sha
counts once (its last reading), readings are ordered by seq, never by time, and only shas on main are read. No
checkout, a failing evidence run, no coverage report, an unreadable history line, or fewer than two seqs in the
window: no value (exit 1), never 0."""

from __future__ import annotations

import json
import math
import statistics
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
import brief  # noqa: E402
import fac  # noqa: E402
import landing  # noqa: E402
import listing  # noqa: E402
import parks  # noqa: E402
import times  # noqa: E402
import verify  # noqa: E402

WINDOW = 14 * 86400


def recent(rows: list[dict], field: str, since: float) -> list[dict]:
    return [r for r in rows if float(r["fields"].get(field) or 0) >= since]


def median(xs: list[float]) -> float:
    return round(statistics.median(xs), 3) if xs else 0.0


def reading(name: str, now: float | None = None, kind: str = "") -> float:
    now = now or time.time()
    since = now - WINDOW
    if name == "interventions-trend":
        rows = listing.items("intervention")
        at = [float(r["fields"].get("recorded_at") or r.get("first") or 0) for r in rows]
        return float(sum(t >= now - 7 * 86400 for t in at) - sum(now - 14 * 86400 <= t < now - 7 * 86400 for t in at))
    if name == "first-pass-yield":
        gaps = {g["id"]: g for g in listing.items("gap")}     # (an env-park is not the implementor's failure)
        first = [r for r in recent(listing.items("review"), "written_at", since) if r["fields"].get("round") == 1
                 and not env_park(r, gaps)]
        if not first:
            raise SystemExit("first-pass-yield: no value yet (no first review in the window)")   # not 0: unknown
        return round(sum(r["fields"].get("verdict") == "merge" for r in first) / len(first), 3)
    if name in ("manager-triggers-per-session", "manager-actions-per-session"):   # (allowlist: a typo is refused)
        done = [r["fields"] for r in recent(listing.items("situation"), "handled_at", since)]
        field = "triggers_n" if name == "manager-triggers-per-session" else "actions_n"
        return round(statistics.mean(float(r.get(field) or 0) for r in done), 2) if done else 0.0
    if name in ("tool-denials", "tool-denials-unknown"):   # unknown: a timeout, a crash, a result silent on them
        rows = [r["fields"] for r in recent(listing.items("session"), "started", since)]
        unknown = [r for r in rows if "tool_denials" not in r]
        if name == "tool-denials-unknown":
            return float(len(unknown))
        if unknown:
            print(f"tool-denials: left out, {len(unknown)} session(s) whose refusals are unknown", file=sys.stderr)
            if len(unknown) == len(rows):
                raise SystemExit("tool-denials: no value (no session in the window said what it was refused)")
        return float(sum(int(r["tool_denials"] or 0) for r in rows if "tool_denials" in r))
    if name == "env-parks":
        return env_parks(since)
    if name == "refused-commands-per-session":
        return refused_commands([r["fields"] for r in recent(listing.items("session"), "started", since)])
    if name in KNOWLEDGE:
        return knowledge_reading(name, since)
    if name in ("size-accuracy", "size-accuracy-high"):
        return size_accuracy(name, since)
    if name == "planning-cost-share":
        return planning_cost_share(since)
    if name in landing.MEASURES:                        # from the batch items (landing.py)
        try:
            return landing.reading(name, listing.items("batch"), listing.items("gap"), now, since)
        except landing.NoValue as e:
            raise SystemExit(str(e)) from None
    if name in verify.MEASURES:                         # merge first, verify after (verify.py: run/verify-log.jsonl)
        try:
            return verify.reading(name, verify.log_lines(fac.config()), listing.items("batch"), listing.items("gap"),
                                  since)
        except verify.NoValue as e:
            raise SystemExit(str(e)) from None
    gaps = listing.items("gap")
    if name in SPLITS:
        return split_reading(name, gaps, since)
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
    runs = {r["run"]: float(r.get("minutes") or 0) for g in gaps for r in g["fields"].get("queue_runs") or []
            if float(r.get("at") or 0) >= since}        # every queue run that ended in the window, each once
    if name == "merges-per-hour":                       # its whole length once
        hours = sum(runs.values()) / 60
        return round(len(merged) / hours, 3) if hours else 0.0
    queued = [g["fields"] for g in recent(gaps, "queued_at", since)]
    if name == "queue-minutes":
        return median([float(g["queue_minutes"]) for g in queued if g.get("queue_minutes")])
    if name == "suite-minutes":
        runs = [g.get("suites_queue") or {} for g in merged]
        return median([sum(float((r.get(s) or {}).get("seconds") or 0) for s in ("unit", "browser", "demo")) / 60
                       for r in runs if r])
    if name == "flake-rate":                            # triage's retries and the queue's excused runs, per run
        if not runs:
            raise SystemExit("flake-rate: no value (no queue run in the window)")   # not 0: unknown
        excused = {g.get("batch_id") or g.get("main_sha") or id(g) for g in merged
                   if isinstance(g.get("suites_queue"), dict) and g["suites_queue"].get("excused")}
        return round((sum(int(g.get("retries") or 0) for g in queued) + len(excused)) / len(runs), 3)
    raise SystemExit(f"measure.py: no measure {name!r}")


def refused_commands(rows: list[dict]) -> float:
    """The mean Bash calls refused per session (its `denied` list, sessions.py), over the sessions that said; one whose
    list is missing or not a list (a timeout, a crash, a result silent on them) is left out and counted on stderr, and
    with none that said there is no value."""
    said = [r["denied"] for r in rows if isinstance(r.get("denied"), list)]
    if len(said) < len(rows):
        print(f"refused-commands-per-session: left out, {len(rows) - len(said)} session(s) whose refusals are unknown",
              file=sys.stderr)
    if not said:
        raise SystemExit("refused-commands-per-session: no value (no session in the window said what it was refused)")
    return round(sum(sum(str(d).startswith("Bash:") for d in ds) for ds in said) / len(said), 3)


KNOWLEDGE = ("lessons-per-brief", "first-pass-with-lessons", "lessons-recurring", "plan-risks-held", "splits-clean")


def share(xs: list[bool], name: str) -> float:
    if not xs:
        raise SystemExit(f"{name}: no value yet (nothing to measure in the window)")
    return round(sum(xs) / len(xs), 3)


def size_class(lines: int) -> str:
    return "S" if lines <= 50 else "M" if lines <= 150 else "L" if lines <= 400 else "XL"


def size_accuracy(name: str, since: float) -> float:
    """The planner's planned_size, never `size`: the groomer (gap.groomed) regrades `size` on its own scale."""
    sized = [g for g in recent(listing.items("gap"), "merged_at", since) if g["state"] == "merged"
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
    carried = [g for g in recent(listing.items("gap"), "merged_at", since) if g["state"] == "merged"
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


SPLITS = ("splits-covered", "split-budgets-held", "split-joins", "split-overhead")


def priced(f: dict) -> float | None:
    """A gap's recorded ai_cost_usd, or None when it has none it can count (missing, not a number, negative, NaN)."""
    v = f.get("ai_cost_usd")
    return float(v) if type(v) in (int, float) and math.isfinite(v) and v >= 0 else None


def family(g: dict, by_id: dict) -> list[str]:
    """A parent's sub-gaps: its recorded children, the gaps whose parent names it (parks.split_again links a
    continuation only so), and what each was resumed as. One split_again unlinked (stopped, replaced) stays in."""
    todo = fac.ids(g["fields"]["children"]) + [i for i, k in by_id.items() if g["id"] in fac.ids(k["fields"].get("parent"))]
    seen: list[str] = []
    while todo:
        if (i := todo.pop(0)) not in seen and i != g["id"]:
            seen.append(i)
            todo += fac.ids((by_id.get(i) or {"fields": {}})["fields"].get("resumed_as"))
    return seen


def budget(cfg: dict, g: dict) -> float:
    """A sub-gap's own `## Size budget` in net lines, where brief.definition_text reads its definition; -inf when it
    has none it can read (never budget_of's default), so nothing is under it."""
    b = fac.branch_of(g)
    try:
        text = brief.definition_text(cfg, str(g["fields"].get("definition") or f"run/defs/{b}.md"), b)
    except OSError:
        return -math.inf
    return float(n) if (n := fac.budget_of(text, -1)) >= 0 else -math.inf


def split_reading(name: str, gaps: list[dict], since: float) -> float:
    """The split parents (a gap with `children`): their join verdicts (plan.py join), and their cost against unsplit
    gaps of their size. Each parent's first verdict is the first of its join_verdicts, in record order, never by `at`."""
    parents = [g for g in gaps if g["fields"].get("children")]
    judged = [g["fields"]["join_verdicts"] for g in parents if g["fields"].get("join_verdicts")]
    if name == "split-joins":
        return float(len(judged))
    if name == "splits-covered":
        return share([v[0].get("verdict") == "covered" for v in judged if float(v[0].get("at") or 0) >= since], name)
    if name == "split-budgets-held":                     # a definition, budget or net_lines it cannot read: not held
        subs, cfg = [g for g in recent(gaps, "merged_at", since) if g["state"] == "merged" and g["fields"].get("parent")], \
            fac.config()
        return share([type(n := g["fields"].get("net_lines")) is int and n <= budget(cfg, g) for g in subs], name)
    counted = lambda f: type(f.get("merged_lines")) is int and not f.get("merged_lines_error")  # noqa: E731
    base: dict[str, list[float]] = {}                         # merged unsplit gaps, over the whole record, by class
    for g in gaps:
        f = g["fields"]
        if g["state"] == "merged" and not f.get("parent") and not f.get("children") and counted(f) and priced(f) is not None:
            base.setdefault(size_class(f["merged_lines"]), []).append(priced(f))
    by_id, ratios = {g["id"]: g for g in gaps}, []
    for g in [g for g in recent(parents, "judged_at", since) if g["state"] == "merged"]:   # (no merged_at: plan.join)
        every = [by_id.get(k) for k in family(g, by_id)]
        kids = [k for k in every if k is None or g["id"] in fac.ids(k["fields"].get("parent"))]   # stopped: priced only
        why = ("a child not merged" if any(k is None or k["state"] != "merged" for k in kids) else "") or \
            ("a child with no merged_lines" if not all(counted(k["fields"]) for k in kids) else "") or \
            ("a child with no ai_cost_usd" if any(priced(k["fields"]) is None for k in every) else "") or \
            ("no ai_cost_usd of its own" if priced(g["fields"]) is None else "")
        cls = "" if why else size_class(sum(k["fields"]["merged_lines"] for k in kids))
        if why or cls not in base:
            print(f"split-overhead: left out, {g['id']}: {why or f'no merged unsplit {cls} gap'}", file=sys.stderr)
            continue
        ratios.append((priced(g["fields"]) + sum(priced(k["fields"]) for k in every)) / statistics.median(base[cls]))
    if not ratios:
        raise SystemExit("split-overhead: no value (no split parent merged in the window could be priced)")
    return round(statistics.median(ratios), 3)


def knowledge_reading(name: str, since: float) -> float:
    gaps = {g["id"]: g for g in listing.items("gap")}
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
    if name == "lessons-recurring":
        return recurring(gaps, recent(listing.items("review"), "written_at", since))
    first = [r for r in recent(listing.items("review"), "written_at", since) if r["fields"].get("round") == 1]
    if name == "first-pass-with-lessons":
        return share([r["fields"].get("verdict") == "merge" for r in first if carried.get(review_gap(r))], name)
    risks = {r["id"]: set(gaps.get(review_gap(r), {}).get("fields", {}).get("risks") or []) for r in first}
    return share([not (risks[r["id"]] & set(r["fields"].get("classes") or [])) for r in first if risks[r["id"]]], name)


def env_park(review: dict, gaps: dict) -> bool:
    """A review that parked its gap for a need, on a gap with done items the implementor cannot do (plan.py's
    env_needs): a park those items caused after building (one at plan time is the gap's env_parked_at)."""
    f = review["fields"]
    return f.get("verdict") == "park" and f.get("parked_for") == "needs" and bool(
        gaps.get(review_gap(review), {}).get("fields", {}).get("env_needs"))


def env_parks(since: float) -> float:
    """The parks caused by done items an implementor's container cannot do: at plan time (env_parked_at), and by a
    review (env_park), in the window."""
    gaps = {g["id"]: g for g in listing.items("gap")}
    return float(sum(float(g["fields"].get("env_parked_at") or 0) >= since for g in gaps.values()) + sum(
        env_park(r, gaps) for r in recent(listing.items("review"), "written_at", since)))


def recurring(gaps: dict, reviews: list[dict]) -> float:
    """lessons-recurring: each review's classes that its gap's first implementor brief carried. Classes not recorded
    (no list: the librarian has not measured it) or no first brief: left out and said, never 0."""
    brief = lambda g: next((c.get("knowledge") or [] for c in (g or {}).get("fields", {}).get("contexts") or []  # noqa: E731
                            if c.get("role") == "implementor"), None)
    got = [(set(r["fields"]["classes"]), set(brief(gaps.get(review_gap(r))))) for r in reviews
           if isinstance(r["fields"].get("classes"), list) and brief(gaps.get(review_gap(r))) is not None]
    if len(got) < len(reviews):
        print(f"lessons-recurring: left out, {len(reviews) - len(got)} review(s) with no classes or no first brief",
              file=sys.stderr)
    if not got:
        raise SystemExit("lessons-recurring: no value (no review in the window with its classes and brief)")
    return float(sum(len({c for c in found & held if c.startswith("lesson-")}) for found, held in got))


def review_gap(review: dict) -> str | None:
    """The gap a review is of: its ``gap`` field is a relation, which the record may hold as a list of one."""
    got = review["fields"].get("gap")
    return (got[0] if got else None) if isinstance(got, list) else got


STALE = 20                                              # main's merges after which a coverage report says nothing


def coverage_report(cfg: dict) -> dict:
    """The latest coverage report of main, by its ``seq`` (never by a file's time), among those whose commit is on
    main (a run whose merge was undone measured a commit main never had); SystemExit (no value) when there is none,
    any is unreadable (it may be the latest), or main has moved more than STALE first-parent commits past it."""
    return latest_coverage(cfg)[2]


def latest_coverage(cfg: dict) -> tuple[int, str, dict, dict]:
    """coverage_report's choice: (its seq, its sha, the shares, its modules as written)."""
    repo, base = fac.path(cfg, "checkout"), cfg["git"]["base"]
    found = []
    for p in sorted(fac.path(cfg, "run").joinpath("coverage").glob("*/coverage.json")):
        try:
            r = json.loads(p.read_text())
            found.append((int(r["seq"]), str(r["main"]), {m: float(v["share"]) for m, v in r["modules"].items()},
                          r["modules"]))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise SystemExit(f"coverage: no value (an unreadable report: {p})") from None
    on_main = [f for f in found if fac.git_ok(repo, "merge-base", "--is-ancestor", f[1], base)]
    if not on_main:
        raise SystemExit("coverage: no value (no coverage report of a commit on main)")
    seq, sha, shares, mods = max(on_main, key=lambda f: f[0])
    since = int(fac.git(repo, "rev-list", "--count", "--first-parent", f"{sha}..{base}"))
    if since > STALE:
        raise SystemExit(f"coverage: no value (the latest report, {sha[:12]}, is {since} merges behind {base})")
    return seq, sha, shares, mods


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


EVIDENCE = fac.HERE.parent / "scripts" / "code_evidence.py"
CODE = {"code-net-lines": lambda r: r["lines"], "code-long-functions": lambda r: len(r["long_functions"]),
        "code-duplicates": lambda r: len(r["duplicates"]), "code-dead-candidates": lambda r: len(r["dead_candidates"])}
TREND = 10                                              # main's merges a code measure's change is taken over


def evidence(cfg: dict) -> tuple[int, str, list[dict]]:
    """code_evidence.py's rows on main as the checkout has it now, with main's seq and sha (resolved first, so the
    rows and the stamp are of one commit). No checkout or a failing run: SystemExit, no value."""
    repo = fac.path(cfg, "checkout")
    try:
        sha = fac.git(repo, "rev-parse", "--verify", f"{cfg['git']['base']}^{{commit}}")
        seq = int(fac.git(repo, "rev-list", "--count", "--first-parent", sha))
        with tempfile.NamedTemporaryFile("w", suffix=".json") as none:   # (these four read no coverage)
            none.write("{}")
            none.flush()
            r = subprocess.run([sys.executable, str(EVIDENCE), "--root", str(repo), "--ref", sha, "--coverage",
                                none.name], capture_output=True, text=True, timeout=600)
        rows = [json.loads(line) for line in r.stdout.splitlines() if line.strip()] if not r.returncode else []
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        raise SystemExit(f"code: no value (no checkout of main to measure: {e})") from None
    if not rows:
        raise SystemExit(f"code: no value (code_evidence.py: exit {r.returncode} {r.stderr.strip()[-300:]})")
    return seq, sha, rows


def code_reading(name: str) -> float:
    """One code measure, appended to run/code-measures.jsonl with the seq and sha it measured."""
    cfg = fac.config()
    if name == "code-coverage":
        seq, sha, _, mods = latest_coverage(cfg)
        try:
            statements, covered = (sum(int(v[k]) for v in mods.values()) for k in ("statements", "covered"))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SystemExit("code-coverage: no value (a report with no statement counts)") from None
        if statements <= 0:
            raise SystemExit("code-coverage: no value (a report with no statements)")
        value = round(covered / statements, 4)
    else:
        seq, sha, rows = evidence(cfg)
        value = float(sum(CODE[name](r) for r in rows))
    with open(fac.run_dir(cfg) / "code-measures.jsonl", "a") as f:
        f.write(json.dumps({"measure": name, "seq": seq, "sha": sha, "value": value, "at": time.time()}) + "\n")
    return value


def code_change(name: str, values: dict[str, tuple[int, float]] | None = None) -> float:
    """A code measure's change over the last TREND of main's merges, by seq: each sha once (its last reading). ``values``
    ({sha: (seq, value)}, passing.py's) in place of the code measures' history."""
    cfg, measure = fac.config(), name.removesuffix("-change")
    by_sha: dict[str, tuple[int, float]] = {}
    try:
        for line in (fac.path(cfg, "run") / "code-measures.jsonl").read_text().splitlines() if values is None else ():
            r = json.loads(line)
            if r["measure"] == measure:
                by_sha[str(r["sha"])] = (int(r["seq"]), float(r["value"]))
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise SystemExit(f"{name}: no value (the code measures' history cannot be read: {e!r})") from None
    window = by_seq(cfg, by_sha if values is None else values)
    if len({seq for seq, _ in window}) < 2:
        raise SystemExit(f"{name}: no value (fewer than two of main's commits measured within {TREND} merges)")
    return round(window[0][1] - window[-1][1], 4)


def by_seq(cfg: dict, by_sha: dict[str, tuple[int, float]]) -> list[tuple[int, float]]:
    """The (seq, value) of the shas on main within TREND merges of the latest of them, the latest first."""
    repo, base = fac.path(cfg, "checkout"), cfg["git"]["base"]
    window: list[tuple[int, float]] = []
    for sha, (seq, value) in sorted(by_sha.items(), key=lambda kv: -kv[1][0]):    # the latest seq first
        if window and seq < window[0][0] - TREND:
            break
        if fac.git_ok(repo, "merge-base", "--is-ancestor", sha, base):           # (a merge undone measured nothing)
            window.append((seq, value))
    return window


if __name__ == "__main__":
    name = sys.argv[1]
    if name in CODE or name == "code-coverage":
        print(code_reading(name))
    elif name.removesuffix("-change") in (*CODE, "code-coverage"):
        print(code_change(name))
    elif name == "main-stalled-why":                    # the goal main-moving's reason (landing.py)
        print(landing.reason(listing.items("batch"), listing.items("gap"), time.time()))
    elif name in ("coverage", "coverage-below-floor"):
        print(coverage_reading(name, sys.argv[2:]))
    else:
        print(reading(name, kind=sys.argv[2] if len(sys.argv) > 2 else ""))
