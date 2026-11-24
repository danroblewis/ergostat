"""main-broken: the implementor's own triage of its fast suites (implement.py), before a failure counts against the gap.

The fast suites are ruff, [suites] build when set (the small set, scripts/affected_tests.py; else the full unit suite),
and the four browser files only with [suites] build_browser = true (a browser test skipped fails them, as in the
queue); the merge queue runs unit and demo in full either way, browser on its paths (queue.py). The tests that
failed (unit, build or browser) are run again alone on the branch (`alone`; `rerun`, with Playwright, for the browser's): passing, they
are flakes (`flake.seen`), and the fast suites
are run once more, uncounted, once per run. Those still failing are run once on clean main (the commit the branch
merged), in a clone of the drop at it. Each run is in the same kind of suite container as the fast suites, in the
suite slot. A test that fails on main too is main's, not the gap's (lesson 13: reported, not fixed): an item
`flake/<test>` in the state `main-broken`, and one intervention per main commit (class `main-broken`). When every test
still failing is main's, the gap waits for main to move (`waits_on_main`, cleared by the intake) instead of counting.

Bounded: one alone run and one main run per failure (a test found failing on main in this run is not run on main
again), and none when the gap's building hours left under the kill rule are fewer than the unit suite took."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import agents
import fac
import flakes

LEAST = 60.0          # seconds a rerun is assumed to take at the least (a container started, the tests collected)
AGAIN = {"unit": "alone", "build": "alone", "browser": "rerun"}  # each one's tests run again alone ("rerun": Playwright)


def room(suites: dict, deadline: float) -> bool:
    """Whether a rerun fits before the kill rule's building hours run out (the failed suite's time)."""
    took = suites.get(str(suites.get("failed"))) or suites.get("unit") or suites.get("build") or {}
    return time.time() + max(LEAST, float(took.get("seconds") or 0)) < deadline


def step(cfg: dict) -> str:
    """The implementor's test step: [suites] build (the small set) when set, else the full `unit` suite."""
    return "build" if str(cfg["suites"].get("build") or "").strip() else "unit"


def fast(cfg: dict) -> tuple[str, ...]:
    """The implementor's fast suites: ruff, its test step (see step), then the four browser files if turned on."""
    return ("ruff", step(cfg)) + (("browser",) if cfg["suites"].get("build_browser") is True else ())


def failing(cfg: dict, branch: str, main: str, tests: list[str], logs: Path, tag: str, suite: str = "alone") -> dict:
    """The tests alone on clean ``main``, in a clone of the drop at it, in a suite container (what agents.suites
    said: `failed` and the `tests` that failed, when any did). Also the pipeline manager's reapprove (manage.py)."""
    mhome, _ = agents.clone(cfg, branch, "main", at=main)
    try:
        return agents.suites(cfg, mhome, (suite,), logs, tag, tests=tests)
    finally:
        shutil.rmtree(mhome, ignore_errors=True)


def check(cfg: dict, gap: str, home: Path, branch: str, main: str, logs: Path, tag: str, deadline: float,
          seen: dict[str, bool], retried: bool) -> tuple[dict, bool]:
    """The fast suites on the session's work, triaged; (what they said, whether the flake retry is spent). On a unit
    failure that names tests, what they said gains `flakes` (passed alone), `on_main` (failing on main too, at
    `main_checked`), `main_broken` (every test still failing is main's), or `not_checked` (why no rerun). ``seen``: each
    test run on main in this run, and whether it failed there."""
    out = agents.suites(cfg, home, fast(cfg), logs, tag)
    tests = list(out.get("tests") or [])
    if out.get("failed") not in AGAIN or not tests:
        return out, retried                                  # (ruff, a skip, or a watchdog kill: nothing to run alone)
    if not room(out, deadline):
        return {**out, "not_checked": "no building hours left under the kill rule for a rerun"}, retried
    again_by = AGAIN[out["failed"]]
    alone = agents.suites(cfg, home, (again_by,), logs, f"{tag}-alone", tests=tests)
    if not alone.get("failed"):
        if retried:
            return {**out, "flakes": tests, "not_checked": "passed alone, and the run's one flake retry is spent"}, True
        for t in tests:
            flakes.say("flake.seen", t, gaps=[gap], times=1, seen_at=time.time())
        again = agents.suites(cfg, home, fast(cfg), logs, f"{tag}-retry")
        return {**again, "flakes": tests}, True
    still = list(alone.get("tests") or tests)
    ask = [t for t in still if t not in seen]
    if ask and not room(out, deadline):
        return {**out, "not_checked": "no building hours left under the kill rule for a run on main"}, retried
    if ask:
        got = failing(cfg, branch, main, ask, logs, f"{tag}-main", again_by)
        bad = set(got.get("tests") or [])                    # (a failure that names no test blames nothing)
        seen.update({t: t in bad for t in ask})
    on_main = [t for t in still if seen.get(t)]
    return {**out, "main_checked": main, "on_main": on_main, "main_broken": len(on_main) == len(still)}, retried


def record(gap: str, main: str, tests: list[str]) -> None:
    """Each test that fails on main too, as an item in the state main-broken, and the intervention of that main commit
    (what the coordinator sees, and interventions-trend counts)."""
    now = time.time()
    for t in tests:
        flakes.say("flake.main-broken", t, main=main, gaps=[gap], main_broken_at=now)   # (a second: the first clock)
    fac.say("intervention.recorded", f"intervention/main-broken-{main[:12]}", recorded_at=now, main=main, tests=tests,
            gaps=[gap], reason=f"main {main[:12]} fails its own tests ({', '.join(tests[:5])}): {gap} waits for main to "
                               "move; fix them on main in a gap of their own", **{"class": "main-broken"})
