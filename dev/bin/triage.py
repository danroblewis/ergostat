"""flake triage: takes a gap whose queue run failed, under a lease. The tests that failed are run again alone (with
the branch merged into the main it failed on, `pre`, whatever main has become since, in a worktree of the triage's own,
under a suite slot once the machine is quiet; never under the queue's lock, so neither the rerun nor the wait holds the
queue). If they pass alone, each is a `flake` item and the gap goes back to the queue (retried, not blamed), at most
`RETRIES` times; if they fail again, or nothing names the tests (ruff, a watchdog kill, demo_check), the failure is the
branch's: back to fix with what failed, or parked on its `[gates] kill_after`-th failed gate. A rerun stopped for a
limit (fac.Stalled) is tried again later, uncounted, until the gap's fac.STALLS_MOST-th stall: then it is the branch's."""

from __future__ import annotations

import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import review  # noqa: E402

RETRIES = 2


def rerun(cfg: dict, branch: str, sha: str, pre: str, tests: list[str], n: int,
          suite: str = "") -> tuple[int, dict]:
    """The failed tests again, alone, on ``pre`` with the reviewed commit merged; each test id shell-quoted. Those
    the ``suite`` host failed run on the Mac, as the queue ran them."""
    repo = fac.path(cfg, "checkout")
    wt = fac.path(cfg, "worktrees") / ".triage"
    if not (wt / ".git").exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        fac.git(repo, "worktree", "add", "-q", "--detach", str(wt), pre)
    fac.git(wt, "merge", "--abort", check=False)
    fac.git(wt, "checkout", "-q", "--detach", pre)
    try:
        if not fac.git_ok(wt, "merge", "-q", "--no-ff", "--no-commit", sha):
            return 1, {"why": "the merge no longer applies"}
        log = fac.run_dir(cfg, "queue") / f"{branch}-{n}-triage.txt"
        q, held = fac.run_dir(cfg, "queue") / f"{branch}-{n}-triage-quarantined.txt", fac.quarantine(repo, pre)
        fac.beside(held, q, lambda ts: fac.suite(cfg, "rerun", wt, q, box="triage", tests=ts))
        tests = [t for t in tests if t not in held]       # main's list, not the branch's: they never block
        if not tests:
            return 0, {"why": "only quarantined tests failed", "quarantined": held}
        rc, secs = fac.suite(cfg, "rerun", wt, log, box="host" if suite == "host" else "triage", tests=tests)
        return rc, {"seconds": round(secs), "log": str(log), "tests": fac.failed_tests(log.read_text()),
                    "quarantined": held}
    finally:
        fac.git(wt, "merge", "--abort", check=False)
        fac.git(wt, "checkout", "-q", "--detach", pre)


def main() -> int:
    fac.stop_on_term()                                  # (stopped: its suite's container killed by name, fac.suite)
    cfg = fac.config()
    gap = fac.read_input()["item"]
    f = gap["fields"]
    branch, tests = fac.branch_of(gap), list(f.get("failed_tests") or [])
    n = int(f.get("queue_attempts") or 0)
    rc, got = 1, {"why": f"{f.get('failed_suite', 'a suite')} failed and named no test to run again"}
    if tests and int(f.get("retries") or 0) >= RETRIES:
        got = {"why": f"retried {RETRIES} times as flaky already: the failure is the branch's"}
    elif tests:
        fac.wait_quiet(cfg)                             # (a suite slot, in fac.suite: never the queue's lock)
        try:
            rc, got = rerun(cfg, branch, str(f["reviewed_head"]), str(f.get("pre") or cfg["git"]["base"]), tests, n,
                             str(f.get("failed_suite") or ""))
        except fac.Stalled as e:                        # (stopped for a limit: not the branch's, tried again later,
            n = int(f.get("stalls") or 0) + 1           # until its fac.STALLS_MOST-th stall: then the branch's)
            fac.say("gap.measured", stalled=e.suite, stalled_why=e.why, stalled_test=e.test, stalled_tail=e.tail, stalls=1)
            if n < fac.STALLS_MOST:
                fac.nack(f"triage: {e}", after="10m", count=False)
                return 0
            got = {"why": f"stalled {n} times ({e.why}), on {e.test or 'no named test'}", "stalled": e.suite}
    if rc == 0:                                  # (only quarantined tests failed: no flake seen, no retry spent)
        tests = [t for t in tests if t not in got.get("quarantined", [])]
        for t in tests:
            fac.say("flake.seen", f"flake/{fac.slug(t, 80)}", test=t, gaps=[gap["id"]], times=1, seen_at=time.time())
        fac.say("gap.retried", approved_by="flake-retry", retries=1 if tests else 0, flakes=tests, triage=got)
        return 0
    again = f"failed again alone: {', '.join(got.get('tests') or tests)}" if "seconds" in got else got["why"]
    findings = list(f.get("findings") or [])[-1:] + [again]
    if int(f.get("failed_gates") or 0) + 1 >= fac.kill_after(cfg):
        why = f"Failed its gates {fac.kill_after(cfg)} times (the kill rule); the last, in the merge queue:\n" + "\n".join(
            f"- {x}" for x in findings)
        fac.say("gap.measured", failed_gates=1, findings=findings, triage=got)
        review.park(cfg, gap, why, f"queue run {n}", where="triage", kind="kill-rule")
        return 0
    fac.say("gap.sent-back", sent_back_by="triage", findings=findings, failed_gates=1, fix_rounds=1, triage=got)
    return 0


if __name__ == "__main__":
    sys.exit(main())
