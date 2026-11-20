"""implementor: takes a gap at ready (or at fix, sent back with its findings), under a lease, and builds it:

1. a clone of the factory's drop repository (agents.py: never the owner's), on the branch factory/<branch> from main;
   the definition of done committed first (`docs/roadmap/overnight/<branch>.md`) when the branch lacks it, by this
   program; a branch behind main (a continued one, a fix round) has main merged in by this program (a conflict is
   left for the session, its files in the brief); then published to the drop;
2. a session in a container of its own (or the stand-in) on a brief assembled from dev/prompts/implementor.md;
3. what it left uncommitted committed and bundled back to the drop (in a container with no network); the fast suites
   (ruff, then the unit suite under the watchdog) in a container with no network, in a machine-wide slot; a failure
   is given back to a session to fix, `suite_fix_rounds` times;
4. `gap.built`, with its head, net lines, budget, suites, cost and the context it was given.

The kill rule: fast suites that fail on a second run of it, or building past four hours, park the gap with where it
stopped. Within the day's dollar cap only (fails closed): over it, the gap is given back for an hour, uncounted."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402
import pools  # noqa: E402

KILL_HOURS = 4.0             # the kill rule: a gap that has taken this long building stops
FAILS = 2                    # the kill rule: a gap whose fast suites fail this many times stops


def definition_first(cfg: dict, gap: dict, work: Path) -> tuple[str, str]:
    """The definition file, committed as the branch's first commit when the branch does not have it (by this program,
    in the clone it made, before any session); (its text, the commit that holds it)."""
    branch = fac.branch_of(gap)
    rel = f"{fac.DEFS}/{branch}.md"
    target = work / rel
    if not target.is_file():
        text = brief.definition_text(cfg, str(gap["fields"].get("definition", "")), branch)
        if not text.strip():
            raise RuntimeError(f"{gap['id']} has no definition of done to commit")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text if text.endswith("\n") else text + "\n")
        fac.git(work, "add", rel)
        fac.git(work, "-c", "user.name=factory", "-c", "user.email=factory@localhost", "commit", "-q", "-m",
                f"{branch}: the definition of done\n\n{fac.TRAILER}")
    held = fac.git(work, "log", "--reverse", "--format=%H", "-1", "--", rel) or fac.git(work, "rev-parse", "HEAD")
    return target.read_text(), held


def merge_main(work: Path, main: str) -> list[str]:
    """main merged into a branch that is behind it (by this program, before the session): a clean merge committed as
    the factory; a conflicted one left in progress for the session to finish. The files in conflict (none: clean, or
    nothing to merge)."""
    if fac.git_ok(work, "merge-base", "--is-ancestor", main, "HEAD"):
        return []
    who = ["-c", "user.name=factory", "-c", "user.email=factory@localhost", "-c", "commit.gpgsign=false"]
    if fac.git_ok(work, *who, "merge", "--no-ff", "-m", f"Merge main ({main[:12]}) into the branch\n\n{fac.TRAILER}",
                  main):
        return []
    conflicts = fac.git(work, "diff", "--name-only", "--diff-filter=U").split()
    if not conflicts:                                 # failed for another reason than a conflict: stop, never guess
        raise RuntimeError(f"merging main {main[:12]} failed without conflicts: {fac.git(work, 'status', '--short')}")
    return conflicts


def conflict_brief(main: str, conflicts: list[str]) -> str:
    return ("\n\n# First: finish the merge of main\n\nThe factory merged main (" + main + ") into your branch, and it "
            "conflicted in:\n\n" + "\n".join(f"- `{c}`" for c in conflicts) + "\n\nResolve each (keep what main changed "
            "and what the branch adds), `git add` them and `git commit --no-edit` before any other work; `git status` "
            "shows what is left. Never `git merge --abort`: a branch that does not hold main is refused.\n")


def park(cfg: dict, gap: dict, why: str) -> None:
    """The kill rule on the implementor's side: where it stopped, on its branch and its item."""
    import review
    review.park(cfg, gap, why, "implementor", where="building")


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    given = fac.read_input()
    began = time.time()
    try:
        return build(cfg, given, began)
    except agents.Refused as e:                       # no token: not the gap's fault, and not a dead letter
        fac.nack(str(e), after="1h", count=False)
        return 0
    except Exception:  # noqa: BLE001 - every other failure: parked on its last attempt, never a dead letter
        return fac.guarded(given, began, "build_hours", lambda why: park(cfg, given["item"], why))


def build(cfg: dict, given: dict, began: float) -> int:
    gap = given["item"]
    f = gap["fields"]
    refused = fac.may_spend(cfg, float(cfg["ai"]["implementor_session_usd"]))
    if refused:
        fac.nack(f"budget: {refused}", after="1h", count=False)
        return 0
    if not pools.my_turn(cfg, "implementor", "implementor", gap["id"]):
        fac.nack("the implementor pool is full (run/pools.json): waits its turn", after="5m", count=False)
        return 0
    rework = (given.get("lease") or {}).get("back", gap["state"]) == "fix"
    rounds = int(f.get("rounds") or 0) + 1
    branch = fac.branch_of(gap)
    if float(f.get("build_hours") or 0) >= KILL_HOURS:
        park(cfg, gap, f"Building took {float(f['build_hours']):.1f} hours over its rounds, past the kill rule's "
                       f"{KILL_HOURS:g}: stopped. Its last findings: {f.get('findings') or 'none'}")
        return 0
    fac.say("gap.started", branch=branch, rework=rework, building_at=began)
    home, work = agents.clone(cfg, branch, "implementor")
    base_sha = fac.git(work, "rev-parse", f"origin/{cfg['git']['base']}")
    definition, held = definition_first(cfg, gap, work)
    conflicts = merge_main(work, base_sha)
    agents.publish(cfg, work, branch)                 # (in a merge left in progress: the branch as it was before it)
    text, context = brief.assemble(cfg, "implementor", gap, work, definition=definition)
    text += conflict_brief(base_sha, conflicts) if conflicts else ""
    context["brief"] = brief.save(cfg, "implementor", gap, text)
    context["round"], context["merge_conflicts"] = rounds, conflicts
    cost, sessions = 0.0, 0
    logs = fac.run_dir(cfg, "logs")
    suites: dict = {}
    for i in range(1 + int(cfg["ai"]["suite_fix_rounds"])):
        prompt = text if i == 0 else (
            f"{text}\n\n# The fast suites failed after your work\n\n`{suites['failed']}` failed"
            f" ({', '.join(suites['tests']) or 'see the tail'}). Fix the code (not the tests' bounds), commit, and"
            f" stop. The tail of its output:\n\n```\n{suites['tail']}\n```\n")
        try:
            got = fac.session(cfg, "implementor", prompt, work)
        except fac.OverBudget as e:
            fac.nack(f"budget: {e}", after="1h", count=False)
            return 0
        cost, sessions = cost + float(got.get("total_cost_usd") or 0), sessions + 1
        head = agents.finish(cfg, home, branch, base_sha, held)
        if not fac.git_ok(agents.drop(cfg), "merge-base", "--is-ancestor", base_sha, head):
            raise RuntimeError(f"the branch does not hold main {base_sha[:12]} after the session (the merge was not "
                               f"finished): refused")
        fac.wait_quiet(cfg)
        suites = agents.suites(cfg, home, ("ruff", "unit"), logs, f"{branch}-{rounds}-{i}")
        if not suites.get("failed"):
            break
    net = fac.net_lines(agents.drop(cfg), cfg["git"]["base"], head)
    record = dict(rounds=1, ai_cost_usd=round(cost, 4), sessions=sessions, contexts=[context], head=head,
                  net_lines=net, budget=fac.budget_of(definition), suites_fast=suites, session_dir=str(home),
                  build_hours=round((time.time() - began) / 3600, 3), said=str(got.get("result", ""))[-600:])
    if suites.get("failed"):
        fails = int(f.get("build_failures") or 0) + 1
        fac.say("gap.measured", build_failures=1, **record)
        why = f"the fast suites failed ({suites['failed']}: {', '.join(suites['tests'][:5])})"
        if fails >= FAILS:
            park(cfg, gap, f"Its fast suites failed {fails} times (the kill rule); the last: {why}.\n\n"
                           f"```\n{suites['tail'][-1500:]}\n```")
        else:
            fac.nack(why, count=False, after="1m")
        return 0
    fac.say("gap.built", built_at=time.time(), **record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
