"""implementor: takes a gap at ready (or at fix, sent back with its findings), under a lease, and builds it in its
own worktree, <worktrees>/<branch>, on its branch from main:

1. the definition of done committed first (`docs/roadmap/overnight/<branch>.md`), when the branch lacks it;
2. a headless Claude Code session (or the stand-in) on a brief assembled from dev/prompts/implementor.md;
3. what it left uncommitted committed; the fast suites (ruff, then the unit suite under the watchdog) run once the
   machine is quiet; a failure is given back to a session to fix, `suite_fix_rounds` times;
4. `gap.built`, with its net lines, budget, suites, cost and the context it was given.

Within the day's dollar cap only (fails closed): over it, the gap is given back for an hour, uncounted."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import brief  # noqa: E402
import fac  # noqa: E402
import pools  # noqa: E402

TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash(uv run:*)", "Bash(git status:*)", "Bash(git diff:*)",
         "Bash(git log:*)", "Bash(git show:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(ls:*)", "Bash(cat:*)",
         "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)", "Bash(grep:*)", "Bash(rg:*)", "Bash(find:*)", "Bash(mkdir:*)"]
NEVER = ["Bash(git push:*)", "Bash(git remote:*)", "Bash(git config:*)", "Bash(git stash:*)", "Bash(git reset:*)",
         "Bash(git checkout:*)", "Bash(git switch:*)", "Bash(git worktree:*)", "Bash(gh:*)", "Bash(curl:*)",
         "Bash(wget:*)", "Bash(ssh:*)", "Bash(scp:*)", "Bash(rsync:*)", "Bash(open:*)", "Bash(osascript:*)",
         "Bash(uv run curl:*)", "Bash(uv run gh:*)", "WebFetch", "WebSearch"]


def worktree(cfg: dict, branch: str) -> Path:
    """The gap's worktree, made from main the first time; kept across its rounds."""
    repo, wt = fac.path(cfg, "checkout"), fac.path(cfg, "worktrees") / branch
    if (wt / ".git").exists():
        return wt
    wt.parent.mkdir(parents=True, exist_ok=True)
    if fac.git_ok(repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}"):
        fac.git(repo, "worktree", "add", "-q", str(wt), branch)
    else:
        fac.git(repo, "worktree", "add", "-q", "-b", branch, str(wt), cfg["git"]["base"])
    return wt


def definition_first(cfg: dict, gap: dict, wt: Path) -> str:
    """The definition file, committed as the branch's first commit when the branch does not have it; its text."""
    branch = fac.branch_of(gap)
    rel = f"{fac.DEFS}/{branch}.md"
    target = wt / rel
    if target.is_file():
        return target.read_text()
    text = brief.definition_text(cfg, str(gap["fields"].get("definition", "")), wt)
    if not text.strip():
        raise RuntimeError(f"{gap['id']} has no definition of done to commit")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n")
    fac.git(wt, "add", rel)
    fac.git(wt, "commit", "-q", "-m", f"{branch}: the definition of done\n\n{fac.TRAILER}")
    return text


def fast_suites(cfg: dict, wt: Path, logs: Path, n: int) -> dict:
    waited = fac.wait_quiet(cfg)
    out = {"waited_s": round(waited)}
    for name in ("ruff", "unit"):
        rc, secs = fac.suite(cfg, name, wt, logs / f"{wt.name}-{name}-{n}.txt")
        out[name] = {"rc": rc, "seconds": round(secs)}
        if rc:
            text = (logs / f"{wt.name}-{name}-{n}.txt").read_text()
            out["failed"] = name
            out["tail"] = text[-3000:]
            out["tests"] = fac.failed_tests(text)
            break
    return out


def main() -> int:
    cfg = fac.config()
    given = fac.read_input()
    gap = given["item"]
    f = gap["fields"]
    usd = float(cfg["ai"]["implementor_session_usd"]) * (1 + int(cfg["ai"]["suite_fix_rounds"]))
    refused = fac.may_spend(cfg, usd)
    if refused:
        fac.nack(f"budget: {refused}", after="1h", count=False)
        return 0
    if not pools.my_turn(cfg, "implementor", "implementor", gap["id"]):
        fac.nack("the implementor pool is full (run/pools.json): waits its turn", after="5m", count=False)
        return 0
    rework = (given.get("lease") or {}).get("back", gap["state"]) == "fix"
    rounds = int(f.get("rounds") or 0) + 1
    branch = fac.branch_of(gap)
    began = time.time()
    fac.say("gap.started", branch=branch, rework=rework, building_at=began,
            worktree=str(fac.path(cfg, "worktrees") / branch))
    wt = worktree(cfg, branch)
    definition = definition_first(cfg, gap, wt)
    text, context = brief.assemble(cfg, "implementor", gap, wt, definition=definition)
    context["brief"] = brief.save(cfg, "implementor", gap, text)
    context["round"] = rounds
    cost, sessions = 0.0, 0
    got = fac.session(cfg, "implementor", text, wt, TOOLS, NEVER)
    cost, sessions = cost + float(got.get("total_cost_usd") or 0), sessions + 1
    fac.commit_all(wt, f"{branch}: work the session left uncommitted")
    logs = fac.run_dir(cfg, "logs")
    suites = fast_suites(cfg, wt, logs, rounds)
    for i in range(int(cfg["ai"]["suite_fix_rounds"])):
        if not suites.get("failed"):
            break
        fix = (f"{text}\n\n# The fast suites failed after your work\n\n`{suites['failed']}` failed"
               f" ({', '.join(suites['tests']) or 'see the tail'}). Fix the code (not the tests' bounds), commit, and"
               f" stop. The tail of its output:\n\n```\n{suites['tail']}\n```\n")
        got = fac.session(cfg, "implementor", fix, wt, TOOLS, NEVER)
        cost, sessions = cost + float(got.get("total_cost_usd") or 0), sessions + 1
        fac.commit_all(wt, f"{branch}: the suites' fix the session left uncommitted")
        suites = fast_suites(cfg, wt, logs, rounds * 10 + i + 1)
    head = fac.git(wt, "rev-parse", "HEAD")
    net = fac.net_lines(wt, cfg["git"]["base"], "HEAD")
    record = dict(rounds=1, ai_cost_usd=round(cost, 4), sessions=sessions, contexts=[context], head=head,
                  net_lines=net, budget=fac.budget_of(definition), suites_fast=suites,
                  build_hours=round((time.time() - began) / 3600, 3), said=str(got.get("result", ""))[-600:])
    if suites.get("failed"):
        fac.say("gap.measured", **record)
        fac.nack(f"the fast suites failed ({suites['failed']}: {', '.join(suites['tests'][:5])})")
        return 0
    fac.say("gap.built", built_at=time.time(), **record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
