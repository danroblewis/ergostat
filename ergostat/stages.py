"""The stages of a pipeline's items (SPEC §5a, *Stages*): a kind that declares ``pipeline:`` has its items record
named stages as ordinary events, each folding into the item's ``stages`` field by merge, keyed by a span id the
recorder makes (one a stage's run: a stage may repeat, and two may run at once)::

    {"stages": {SPAN: {"stage": "unit", "run": "2", "run_kind": "full", "started": T, "until": T}}}   # started
    {"stages": {SPAN: {"finished": T, "outcome": "passed"}}}                                           # finished

A stage with no finish is ``running`` only while its item is open and before its ``until`` (by when its recorder
promised to end it or be stopped); past either it is ``unfinished``: a recorder that died never reads as running.

From those: each stage's expected time (the median of its RECENT latest ``passed`` runs on the same projection
and run, with the count; under LEAST of them, none), and an open item's time left (its running stages' remainder and
the later steps of its kind's latest green run, a step being the stages that ran at once). Once a stage of the item
did not pass, its path from there depends on what fails, so it has no time left. And the finished stages' durations
as Prometheus histograms, labelled only by the kind, a declared stage name (else ``other``) and an outcome."""

from __future__ import annotations

import math
import statistics

FIELD = "stages"
NORMAL = "passed"                                       # the one outcome that is a normal duration
OUTCOMES = ("passed", "failed", "stopped", "error")     # what a histogram labels; any other is "other"
RECENT, LEAST = 20, 3
BUCKETS = (10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 14400)
DEPENDS = "the remaining path depends on what fails"
COLUMNS = {
    "item_stages": ("id", "projection", "span", "stage", "run", "run_kind", "state", "outcome", "started", "finished",
                    "seconds"),
    "stage_estimates": ("projection", "run_kind", "stage", "expected", "samples"),
    "item_progress": ("id", "projection", "run", "run_kind", "stage", "note", "elapsed", "expected", "samples", "left"),
}


def started(span: str, stage: str, run, run_kind: str, at: float, until: float | None = None) -> dict:
    """An event's data: stage ``stage`` of run ``run`` (of kind ``run_kind``) began at ``at``, to end by ``until``."""
    return {FIELD: {span: {"stage": stage, "run": str(run), "run_kind": run_kind, "started": at,
                           **({"until": until} if until is not None else {})}}}


def finished(span: str, outcome: str, at: float) -> dict:
    return {FIELD: {span: {"finished": at, "outcome": outcome}}}


def _t(v) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) else None


def rows(items, now: float) -> list[dict]:
    """Each stage of each item, in the order they began: ``items`` is (id, kind, open, fields) a time."""
    out = []
    for iid, kind, open_, fields in items:
        got = fields.get(FIELD) if isinstance(fields, dict) else None
        for span, s in (got.items() if isinstance(got, dict) else ()):
            if not isinstance(s, dict):
                continue
            t0, t1, until = _t(s.get("started")), _t(s.get("finished")), _t(s.get("until"))
            if until is None and s.get("until") is not None:
                until = -math.inf                       # (an `until` that cannot be read: past, never running)
            state = "done" if t1 is not None else "unfinished" if not open_ or (until is not None and now > until) \
                else "running"
            secs = None if t0 is None else t1 - t0 if state == "done" else now - t0 if state == "running" else None
            out.append({"id": iid, "projection": kind, "open": bool(open_), "span": str(span), "stage": str(s.get("stage") or ""),
                        "run": str(s.get("run") or ""), "run_kind": str(s.get("run_kind") or ""), "state": state,
                        "outcome": str(s["outcome"]) if state == "done" and s.get("outcome") is not None else None,
                        "started": t0, "finished": t1, "seconds": secs})
    return out


def estimates(rs: list[dict]) -> dict[tuple, tuple]:
    """(kind, run_kind, stage): (expected seconds or None under LEAST samples, samples)."""
    by: dict[tuple, list] = {}
    for r in rs:
        if r["state"] == "done" and r["outcome"] == NORMAL and r["seconds"] is not None and r["seconds"] >= 0:
            by.setdefault((r["projection"], r["run_kind"], r["stage"]), []).append((r["finished"], r["seconds"]))
    out = {}
    for k, xs in by.items():
        last = [s for _, s in sorted(xs, reverse=True)[:RECENT]]
        out[k] = (statistics.median(last) if len(last) >= LEAST else None, len(last))
    return out


def _runs(rs: list[dict]) -> dict[tuple, list[dict]]:
    by: dict[tuple, list] = {}
    for r in rs:
        by.setdefault((r["id"], r["run"]), []).append(r)
    return by


def green_path(rs: list[dict], kind: str, run_kind: str, but: tuple = ()) -> list[list[str]] | None:
    """The steps of the kind's latest run (by its last finish) whose stages all passed: each the stages that ran at
    once, in order. None when it has none."""
    green = [v for k, v in _runs(rs).items() if k != but and v[0]["projection"] == kind and v[0]["run_kind"] == run_kind
             and all(r["outcome"] == NORMAL and r["started"] is not None for r in v)]
    if not green:
        return None
    run = sorted(max(green, key=lambda v: max(r["finished"] for r in v)), key=lambda r: r["started"])
    steps, end = [], -math.inf
    for r in run:
        if r["started"] >= end:
            steps.append([])
        if r["stage"] not in steps[-1]:
            steps[-1].append(r["stage"])
        end = max(end, r["finished"])
    return steps


def progress(rs: list[dict], est: dict, now: float) -> list[dict]:
    """Each open item's running stages (one row a stage; none running, one row with no stage): elapsed, expected and
    the item's time left, or the note saying why it has none."""
    out, by = [], _runs(rs)
    for iid in dict.fromkeys(r["id"] for r in rs if r["open"]):
        mine = [r for r in rs if r["id"] == iid]
        cur = by[(iid, mine[-1]["run"])]
        kind, run, rk = cur[0]["projection"], cur[0]["run"], cur[0]["run_kind"]
        running = [r for r in cur if r["state"] == "running"]
        left, note = _left(rs, est, cur, running, (iid, run))
        if gone := [r["stage"] for r in mine if r["state"] == "unfinished"]:
            left, note = None, f"{gone[-1]} is unfinished: what ran it stopped before it ended"
        elif any(r["outcome"] not in (None, NORMAL) for r in mine):
            left, note = None, DEPENDS
        for r in running or [None]:
            e = est.get((kind, rk, r["stage"])) if r else None
            out.append({"id": iid, "projection": kind, "run": run, "run_kind": rk, "stage": r["stage"] if r else None,
                        "note": note, "elapsed": r["seconds"] if r else None, "expected": e[0] if e else None,
                        "samples": e[1] if e else 0, "left": left})
    return out


def _left(rs, est, cur, running, key) -> tuple[float | None, str]:
    kind, rk = cur[0]["projection"], cur[0]["run_kind"]
    path = green_path(rs, kind, rk, key)
    if path is None:
        return None, f"no green {rk or 'run'} of {kind} yet"
    done = {r["stage"] for r in cur if r["state"] == "done"}
    elapsed = {r["stage"]: r["seconds"] or 0.0 for r in running}
    steps = [[s for s in step if s not in done or s in elapsed] for step in path]
    steps = [s for s in steps if s]
    if extra := [s for s in elapsed if not any(s in step for step in steps)]:
        steps.insert(0, extra)
    total = 0.0
    for step in steps:
        part = []
        for s in step:
            e, n = est.get((kind, rk, s), (None, 0))
            if e is None:
                return None, f"no estimate for {s} ({n} of {LEAST} runs)"
            part.append(max(0.0, e - elapsed.get(s, 0.0)))
        total += max(part)
    return total, ""


def exposition(rs: list[dict], declared: dict[str, list[str]]) -> str:
    """The finished stages of the kinds ``declared`` (kind: its stage names) as one Prometheus histogram,
    ``ergostat_stage_seconds{kind, stage, outcome}``: every label from a bounded set."""
    counts: dict[tuple, list] = {}
    for r in rs:
        if r["state"] != "done" or r["seconds"] is None or r["projection"] not in declared:
            continue
        key = (r["projection"], r["stage"] if r["stage"] in declared[r["projection"]] else "other",
               r["outcome"] if r["outcome"] in OUTCOMES else "other")
        c = counts.setdefault(key, [0] * len(BUCKETS) + [0, 0.0])
        for i, le in enumerate(BUCKETS):
            c[i] += r["seconds"] <= le
        c[-2] += 1
        c[-1] += r["seconds"]
    out = ["# HELP ergostat_stage_seconds How long each finished stage of a pipeline's items took.",
           "# TYPE ergostat_stage_seconds histogram"]
    for (kind, stage, outcome), c in sorted(counts.items()):
        lab = f'kind="{kind}",stage="{stage}",outcome="{outcome}"'
        out += [f'ergostat_stage_seconds_bucket{{{lab},le="{le}"}} {n}' for le, n in zip(BUCKETS, c, strict=False)]
        out += [f'ergostat_stage_seconds_bucket{{{lab},le="+Inf"}} {c[-2]}',
                f"ergostat_stage_seconds_sum{{{lab}}} {c[-1]:g}", f"ergostat_stage_seconds_count{{{lab}}} {c[-2]}"]
    return "\n".join(out) + "\n"
