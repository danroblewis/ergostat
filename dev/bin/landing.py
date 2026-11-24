"""The merge pipeline's health, read from its `batch` items (dev/model/landing.yaml; batches.py says them) and the
gaps waiting for it: measure.py's landing measures, the goal main-moving's reason, and a waiting gap's place.

  main-still-minutes    minutes since main last moved: since the latest batch whose landing stood (ended landed or
                        partial: pushed; one pushing or denied is not counted), at its `landed_at` (one from before
                        that field, its `started_at`, earlier, so never a shorter wait); no value (exit 1) when none
  main-stalled-minutes  the same while gaps wait for the queue (approved, queued, or leased by merge-queue), counted
                        from the later of main's last move and the oldest waiting gap's approval; 0 when none waits
                        (the goal main-moving holds it)
  batch-runs            mean runs of the suites per batch, over the batches ended in the window
  batch-first-green     the share of batches whose first run passed, over those with a run finished in the window
  crash-lost-minutes    minutes of the runs that crashed, over the batches started in the window
  gaps-landed-per-hour  gaps landed by batches whose landing stood, over the last DAY, per hour

batch-runs and batch-first-green have no value (exit 1) with nothing to measure. `main-stalled-why` prints the reason:
the current batch (the open one started last; with none open, the last one), its run and the cause, e.g. "batch/x-...,
run 6 crashed: OSError: no space left on device". A batch or run field that cannot be read is said as unknown, never
as a pass."""

from __future__ import annotations

import math
import statistics
import sys

DAY = 86400.0
FINAL = ("landed", "partial", "failed", "given-back")
STOOD = ("landed", "partial")                           # the ends whose merges stayed on main, pushed
WAITING = ("approved", "queued")                        # (and leased by merge-queue: the queue's own gap)
QUEUE_BLOCK = "merge-queue"
MEASURES = ("main-still-minutes", "main-stalled-minutes", "batch-runs", "batch-first-green", "crash-lost-minutes",
            "gaps-landed-per-hour")


class NoValue(Exception):
    """Nothing to measure: the measure has no value (never a 0)."""


def num(v) -> float | None:
    """A finite number, or None (missing, text, NaN, a bool)."""
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        return None
    return float(v)


def runs_of(b: dict) -> list[dict]:
    return [r for r in b["fields"].get("runs") or [] if isinstance(r, dict)]


def landed_at(b: dict) -> float | None:
    """When the batch moved main (its gaps merged and pushed), or None when its landing did not stand: it landed
    nothing, its push is not settled yet (pushing), or the push was denied (failed: the merges undone, its gaps sent
    back, though the fold keeps batch.landed's fields) or never settled (given-back)."""
    f = b["fields"]
    if b["state"] not in STOOD or not f.get("landed"):
        return None
    return num(f.get("landed_at")) or num(f.get("started_at")) or num(b.get("first"))


def last_moved(batches: list[dict]) -> float | None:
    return max((t for t in map(landed_at, batches) if t is not None), default=None)


def waiting(gaps: list[dict]) -> list[dict]:
    return [g for g in gaps if g["state"] in WAITING or (g["state"] == "leased" and isinstance(
        g["fields"].get("lease"), dict) and g["fields"]["lease"].get("block") == QUEUE_BLOCK)]


def stalled_minutes(batches: list[dict], gaps: list[dict], now: float) -> float:
    wait = waiting(gaps)
    if not wait:
        return 0.0
    since = min(num(g["fields"].get("approved_at")) or num(g.get("entered")) or now for g in wait)
    moved = last_moved(batches)
    return round(max(0.0, now - max(since, moved if moved is not None else -math.inf)) / 60, 1)


def reading(name: str, batches: list[dict], gaps: list[dict], now: float, since: float) -> float:
    if name == "main-still-minutes":
        moved = last_moved(batches)
        if moved is None:
            raise NoValue("main-still-minutes: no value (no batch has landed anything)")
        return round(max(0.0, now - moved) / 60, 1)
    if name == "main-stalled-minutes":
        return stalled_minutes(batches, gaps, now)
    started = [b for b in batches if (num(b["fields"].get("started_at")) or num(b.get("first")) or 0) >= since]
    if name == "batch-runs":
        ended = [b for b in batches if b["state"] in FINAL and (num(b["fields"].get("ended_at")) or 0) >= since]
        if not ended:
            raise NoValue("batch-runs: no value (no batch ended in the window)")
        return round(statistics.mean(len(runs_of(b)) for b in ended), 3)
    if name == "batch-first-green":
        firsts = [runs_of(b)[0] for b in started if runs_of(b)]
        if not firsts:
            raise NoValue("batch-first-green: no value (no batch's first run finished in the window)")
        return round(sum(r.get("outcome") == "passed" for r in firsts) / len(firsts), 3)
    if name == "crash-lost-minutes":
        return round(sum(num(r.get("minutes")) or 0.0 for b in started for r in runs_of(b)
                         if r.get("outcome") == "crashed"), 1)
    if name == "gaps-landed-per-hour":
        return round(sum(len(b["fields"]["landed"]) for b in batches
                         if (landed_at(b) or 0) >= now - DAY and isinstance(b["fields"].get("landed"), list)) / 24, 3)
    raise KeyError(name)


def current(batches: list[dict]) -> tuple[dict | None, bool]:
    """(the open batch started last, True), else (the last batch, False), else (None, False)."""
    at = lambda b: num(b["fields"].get("started_at")) or num(b.get("first")) or 0.0  # noqa: E731
    live = [b for b in batches if b["state"] not in FINAL]
    if live:
        return max(live, key=at), True
    return (max(batches, key=at), False) if batches else (None, False)


def run_said(b: dict, now: float) -> str:
    """The batch's latest run: under way (for how long), or its outcome and cause."""
    f, done = b["fields"], runs_of(b)
    n = num(f.get("run"))
    last = done[-1] if done else None
    if n is not None and (last is None or (num(last.get("run")) or 0) < n):
        t = num(f.get("run_started_at"))
        took = f" for {(now - t) / 60:.0f} min" if t is not None else " (since when is not recorded)"
        return f"run {n:g} ({f.get('run_kind') or 'kind unknown'}) under way{took}"
    if last is None:
        return "no run recorded yet"
    out = str(last.get("outcome") or "outcome unknown")
    said = f"run {last.get('run', '?')} ({last.get('kind') or 'kind unknown'}) {out}"
    if out in ("crashed", "stalled"):
        return f"{said}: {last.get('crash') or 'its cause is not recorded'}"
    if out == "failed":
        tests = list(last.get("first_failing") or [])
        return f"{said}: {last.get('failed', '?')} failed" + (f" ({', '.join(map(str, tests[:3]))})" if tests else "")
    return said


def reason(batches: list[dict], gaps: list[dict], now: float) -> str:
    """Why main has not moved: the current batch, its run and the cause."""
    b, live = current(batches)
    wait = len(waiting(gaps))
    if b is None:
        return f"no batch has run: {wait} gap(s) wait and the merge queue has taken none"
    f = b["fields"]
    if not live:
        return (f"no batch runs now ({wait} gap(s) wait): the last, {b['id']}, ended {b['state']}: "
                f"{f.get('why') or 'why is not recorded'}; {run_said(b, now)}")
    if b["state"] == "pushing":
        return f"{b['id']} landed {len(f.get('landed') or [])} gap(s) and waits for its push to settle"
    return f"{b['id']} ({b['state']}, {len(f.get('gaps') or [])} gap(s)), {run_said(b, now)}"


if __name__ == "__main__":
    sys.exit("landing.py is read through measure.py: measure.py NAME, or measure.py main-stalled-why")
