"""browser-daily: once a day the four browser files on the remote's main, whatever merged (it tests main, not changes),
under the queue's lock (so never beside a batch) once the machine is quiet, in a detached worktree of its own
(<worktrees>/browser-daily, made and removed by that name) and the queue's suite container (box "queue"; main's
quarantine deselected).

- Green: run/browser-daily.json says {sha, at, green: true} and keeps it as `last_green`.
- Red, naming tests: each named test (the first RERUN_MOST; the rest count as real) alone twice (`[suites] rerun`,
  `-rA`, read as queue.py named() reads it). Passing both times: a flake seen (flakes.say), and no intervention; when
  every one is, the day counts as green. The others: one intervention (class queue, which pipeline-watch raises as a
  situation) naming them, main's sha, and the first-parent commits since the last green sha as suspects (the latest
  SUSPECTS_MOST when no green is known or it is not an ancestor).
- Red naming none (a crash, a skip, a stall): one intervention with the log's tail.
`browserday.py green` (the sensor browser-main-green): 1 or 0 for the last run; no reading (exit 1) when the file is
missing, unreadable or malformed."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import flakes  # noqa: E402

NAME = "browser-daily"            # its worktree's name, and its record's (run/browser-daily.json)
RERUN_MOST = 8                    # named tests run alone (twice each) at most; past it, not rerun: counted real
SUSPECTS_MOST = 50                # first-parent commits named as suspects at most


def record(cfg: dict) -> dict | None:
    """The last run's record; {} when there is none; None when it cannot be read (lesson-3: no green known)."""
    p = fac.run_dir(cfg) / f"{NAME}.json"
    try:
        d = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def write(cfg: dict, d: dict) -> None:
    p = fac.run_dir(cfg) / f"{NAME}.json"
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=2))
    os.replace(tmp, p)


def gone(repo, wt) -> None:
    """Its own worktree removed, by its name (a killed run's too), and nothing else."""
    if wt.name != NAME or wt.resolve().parent != wt.parent.resolve():
        raise SystemExit(f"not the daily run's worktree: {wt}")
    fac.git(repo, "worktree", "remove", "--force", str(wt), check=False)
    shutil.rmtree(wt, ignore_errors=True)
    fac.git(repo, "worktree", "prune", check=False)


def alone(cfg: dict, wt, log, test: str) -> str:
    """One test alone (`-rA`): pass only on rc 0 and its PASSED line; fail on FAILED or ERROR; else unknown."""
    try:
        rc, _ = fac.suite(cfg, "rerun", wt, log, slot=False, box="queue", tests=[test, "-rA"])
    except fac.Stalled:
        return "unknown"
    got = fac.outcomes(log.read_text(errors="replace"), [test])[test]
    return "unknown" if got == "pass" and rc else got


def suspects(repo, last: str | None, sha: str) -> tuple[str | None, list[str], bool]:
    """(the green sha they are since, or None; the first-parent commits `sha subject`, newest first; more left out)."""
    since = last if last and fac.git_ok(repo, "merge-base", "--is-ancestor", last, sha) else None
    got = fac.git(repo, "log", "--first-parent", f"-{SUSPECTS_MOST + 1}", "--format=%H %s",
                  f"{since}..{sha}" if since else sha).splitlines()
    return since, got[:SUSPECTS_MOST], len(got) > SUSPECTS_MOST


def day(cfg: dict, repo, wt, sha: str) -> int:
    now = time.time()
    tag = f"{NAME}-{sha[:12]}-{int(now * 1000)}"         # (each run's own: its logs, its intervention's id)
    log = fac.run_dir(cfg, "queue") / f"{tag}.txt"
    try:
        rc, _ = fac.suite(cfg, "browser", wt, log, slot=False, quarantined=fac.quarantine(repo, sha), box="queue")
        text = log.read_text(errors="replace")
    except fac.Stalled as e:
        rc, text = 1, f"{e}\n{e.tail}"
    skipped = len(re.findall(r"^SKIPPED", text, re.M))
    prev = (record(cfg) or {}).get("last_green")         # (only this run writes it, under the queue's lock)
    tests = fac.failed_tests(text) if rc or skipped else []
    flaky = [t for i, t in enumerate(tests) if i < RERUN_MOST and
             all(alone(cfg, wt, log.with_name(f"{tag}-alone-{i}-{k}.txt"), t) == "pass" for k in (1, 2))]
    for t in flaky:
        flakes.say("flake.seen", t, times=1, seen_at=time.time(), suite="browser", run=tag, log=str(log),
                   failed_on_main=sha)
    real = [t for t in tests if t not in flaky]
    if not skipped and (not rc or (tests and not real)):  # (a skip is never green: a page went untested)
        write(cfg, {"sha": sha, "at": now, "green": True, "flakes": flaky, "last_green": {"sha": sha, "at": now}})
        return 0
    since, sus, more = suspects(repo, (prev or {}).get("sha"), sha)
    why = (f"fails {', '.join(real[:5])}" + (f" and {len(real) - 5} more" if len(real) > 5 else "") if real else
           f"{f'skipped {skipped} tests' if skipped else f'exited {rc}'} and named no failing test")
    iid = f"intervention/{tag}"
    fac.say("intervention.recorded", iid, recorded_at=now, main=sha, tests=real, suspects=sus, suspects_since=since,
            suspects_more=more, flakes=flaky, log=str(log), **({} if real else {"tail": text[-2000:]}),
            **{"class": "queue"}, reason=f"the daily browser run on main {sha[:12]} {why}; suspects: {len(sus)}"
            f"{'+' if more else ''} first-parent commits since " + (since[:12] if since else "no known green"))
    write(cfg, {"sha": sha, "at": now, "green": False, "tests": real, "intervention": iid,
                "last_green": prev})
    return 0


def main() -> int:
    fac.stop_on_term()                                  # (stopped: SystemExit, so the finallys below run)
    cfg = fac.config()
    repo, remote, base = fac.path(cfg, "checkout"), cfg["git"]["remote"], cfg["git"]["base"]
    with fac.queue_lock(cfg):
        if cfg["suites"].get("queue_container", True) is not False:
            fac.agents_module().sweep_box("queue")      # (a SIGKILLed run's containers: under the lock none is live)
        fac.wait_quiet(cfg)
        fac.git(repo, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/{remote}/{base}")
        sha = fac.git(repo, "rev-parse", f"refs/remotes/{remote}/{base}")
        wt = fac.path(cfg, "worktrees") / NAME
        wt.parent.mkdir(parents=True, exist_ok=True)
        gone(repo, wt)
        try:
            fac.git(repo, "worktree", "add", "-q", "--detach", str(wt), sha)
            return day(cfg, repo, wt, sha)
        finally:
            gone(repo, wt)


def green() -> int:
    d = record(fac.config())
    if not d or not isinstance(d.get("green"), bool):
        print(f"{NAME}: no readable record of a run", file=sys.stderr)
        return 1
    print(1 if d["green"] else 0)
    return 0


if __name__ == "__main__":
    sys.exit(green() if sys.argv[1:2] == ["green"] else main())
