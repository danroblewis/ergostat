"""implementor: takes a gap at ready (or at fix, sent back with its findings), under a lease, and builds it:

1. a clone of the factory's drop repository (agents.py: never the owner's), on the branch factory/<branch> from main;
   the definition of done committed first (`docs/roadmap/overnight/<branch>.md`) when the branch lacks it, by this
   program; a branch behind main (a continued one, a fix round) has main merged in by this program (a conflict is
   left for the session, its files in the brief); then published to the drop;
2. a session in a container of its own (or the stand-in) on a brief assembled from dev/prompts/implementor.md;
3. what it left uncommitted committed and bundled back to the drop (in a container with no network); before the
   suites, a branch adding scratch files (`strays`: [gates] scratch_patterns, or a new top-level file or folder the
   definition's Files to touch does not name) is refused, back to the session's next round with the list (uncounted;
   still there after the last, a failed build); the fast suites
   (ruff, then the unit suite under the watchdog) in a container with no network, in a machine-wide slot; a failure
   that names tests is triaged first (onmain.py: run alone on the branch, a flake retried once; run on clean main, a
   test failing there too is main's), and a failure of the gap's is given back to a session to fix, `suite_fix_rounds`
   times;
4. `gap.built`, with its head, net lines, budget, suites, cost and the context it was given.

The kill rule ([gates]): fast suites that fail on `build_failures` runs of it, or building past `build_hours`, park the
gap with where it stopped. A failure whose every test fails on main too is not counted: the gap waits for main to move
(`waits_on_main`). Within the day's dollar cap only (fails closed): over it, the gap is given back for an hour,
uncounted."""

from __future__ import annotations

import fnmatch
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402
import onmain  # noqa: E402
import pools  # noqa: E402


def definition_first(cfg: dict, gap: dict, work: Path) -> tuple[str, str]:
    """The definition file (fac.definition_file), committed as the branch's first commit when the branch does not have
    it (by this program, in the clone it made, before any session); (its text, the commit that holds it)."""
    branch, rel = fac.branch_of(gap), fac.definition_file(gap)
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
    conflicts = fac.conflicted(work)
    if not conflicts:                                 # failed for another reason than a conflict: stop, never guess
        raise RuntimeError(f"merging main {main[:12]} failed without conflicts: {fac.git(work, 'status', '--short')}")
    return conflicts


SCRATCH = [".scratch*", "scratch*", "tmp*", "_probe*", "*_probe*.py", "*.orig", "*.rej"]  # [gates] scratch_patterns


def strays(cfg: dict, repo: Path, base: str, head: str, definition: str) -> list[str]:
    """The files the branch adds or changes against main (`base`) that look like a session's scratch: one with a path
    part matching a [gates] scratch_patterns glob, or under a new top-level file or folder the definition's "Files to
    touch" does not name (when it has that section). A file already on main is never one."""
    pats = cfg.get("gates", {}).get("scratch_patterns", SCRATCH)
    if not isinstance(pats, list) or not all(isinstance(p, str) for p in pats):
        raise ValueError(f"[gates] scratch_patterns must be a list of globs, not {pats!r}")
    on_main = set(fac.git(repo, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", base).splitlines())
    tops = {p.split("/", 1)[0] for p in on_main} | {p.split("/", 1)[0] for p, _ in brief.files_of(definition)}
    listed = brief.section(definition, "Files to touch") is not None
    changed = fac.git(repo, "-c", "core.quotePath=false", "diff", "--name-only", "--no-renames", "--diff-filter=d",
                      f"{base}...{head}").splitlines()
    return [p for p in changed if p not in on_main and (
        any(fnmatch.fnmatchcase(part, pat) for part in p.split("/") for pat in pats)
        or listed and p.split("/", 1)[0] not in tops)]


def stray_brief(text: str, stray: list[str]) -> str:
    return (f"{text}\n\n# Scratch files refused\n\nThe factory refused your build before the suites: the branch adds "
            "files that look like scratch ([gates] scratch_patterns), or a new top-level file or folder the definition's "
            "Files to touch does not name:\n\n" + "\n".join(f"- `{p}`" for p in stray) + "\n\nRemove each (`git rm`), "
            "or move what belongs to the gap under a folder main has, commit, and stop.\n")


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
    if fac.drain_holds(cfg):
        return 0
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
    hours = fac.gate(cfg, "build_hours")
    if float(f.get("build_hours") or 0) >= hours:
        park(cfg, gap, f"Building took {float(f['build_hours']):.1f} hours over its rounds, past the kill rule's "
                       f"{hours:g}: stopped. Its last findings: {f.get('findings') or 'none'}")
        return 0
    fac.say("gap.started", branch=branch, rework=rework, building_at=began)
    home, work = agents.clone(cfg, branch, "implementor")
    base_sha = fac.git(work, "rev-parse", f"origin/{cfg['git']['base']}")
    definition, held = definition_first(cfg, gap, work)
    conflicts = merge_main(work, base_sha)
    was = agents.publish(cfg, work, branch)           # (in a merge left in progress: the branch as it was before it)
    text, context = brief.assemble(cfg, "implementor", gap, work, definition=definition)
    text += conflict_brief(base_sha, conflicts) if conflicts else ""
    context["brief"] = brief.save(cfg, "implementor", gap, text)
    context["round"], context["merge_conflicts"] = rounds, conflicts
    cost, sessions, used = 0.0, 0, []
    logs = fac.run_dir(cfg, "logs")
    suites: dict = {}
    fast_seconds = 0.0                                  # every try's ruff and unit (times.py's gate `fast`)
    seen: dict[str, bool] = {}                                  # tests run on main in this run: failed there?
    retried, deadline = False, began + (hours - float(f.get("build_hours") or 0)) * 3600
    for i in range(1 + int(cfg["ai"]["suite_fix_rounds"])):
        prompt = text if i == 0 else stray_brief(text, suites["stray"]) if suites.get("stray") else (
            f"{text}\n\n# The fast suites failed after your work\n\n`{suites['failed']}` failed"
            f" ({', '.join(suites['tests']) or 'see the tail'}). Fix the code (not the tests' bounds), commit, and"
            f" stop. The tail of its output:\n\n```\n{suites['tail']}\n```\n")
        try:
            got = fac.session(cfg, "implementor", prompt, work)
        except fac.OverBudget as e:
            fac.nack(f"budget: {e}", after="1h", count=False)
            return 0
        cost, sessions = cost + float(got.get("total_cost_usd") or 0), sessions + 1
        used += [got["resources"]] if got.get("resources") else []
        head = was = agents.finish(cfg, home, branch, base_sha, held, base_sha, was=was)   # (main merged in, and
        stray = strays(cfg, agents.drop(cfg), base_sha, head, definition)    # the branch where it was given:
        if stray:                                               # refused when not); scratch refused before the suites
            suites = {"failed": "scratch files", "tests": stray, "stray": stray, "tail": "\n".join(stray)}
            continue
        fac.wait_quiet(cfg)
        suites, retried = onmain.check(cfg, gap["id"], home, branch, base_sha, logs, f"{fac.run_tag(branch, began)}-{i}",
                                       deadline, seen, retried)
        fast_seconds += sum(float((suites.get(s) or {}).get("seconds") or 0) for s in ("ruff", "unit"))
        used += [v["resources"] for v in suites.values() if isinstance(v, dict) and v.get("resources")]
        if not suites.get("failed") or suites.get("main_broken"):    # (main's failures are never the session's)
            break
    net = fac.net_lines(agents.drop(cfg), cfg["git"]["base"], head)
    record = dict(rounds=1, ai_cost_usd=round(cost, 4), sessions=sessions, contexts=[context], head=head,
                  net_lines=net, budget=fac.budget_of(definition), built_main=base_sha, suites_fast=suites, session_dir=str(home),
                  fast_seconds=round(fast_seconds, 1),
                  build_hours=round((time.time() - began) / 3600, 3), said=str(got.get("result", ""))[-600:],
                  resources=used)
    if suites.get("flakes"):
        record["flakes"] = suites["flakes"]
    broken = sorted(t for t, bad in seen.items() if bad)        # (found in any round of this run)
    record["main_broken_tests"] = broken
    if broken:
        onmain.record(gap["id"], base_sha, broken)
    if suites.get("failed") and suites.get("main_broken"):
        fac.say("gap.measured", waits_on_main=base_sha, **record)
        fac.nack(f"its fast suites failed only on tests that fail on main {base_sha[:12]} too "
                 f"({', '.join(suites['on_main'][:5])}): not the gap's; it waits for main to move", count=False, after="5m")
        return 0
    if suites.get("failed"):
        fails = int(f.get("build_failures") or 0) + 1
        fac.say("gap.measured", build_failures=1, **record)
        why = f"the fast suites failed ({suites['failed']}: {', '.join(suites['tests'][:5])})" if not suites.get(
            "stray") else f"refused before the suites, its scratch files still on the branch: {', '.join(suites['stray'])}"
        if fails >= fac.gate(cfg, "build_failures"):
            park(cfg, gap, f"Its fast suites failed {fails} times (the kill rule); the last: {why}.\n\n"
                           f"```\n{suites['tail'][-1500:]}\n```")
        else:
            fac.nack(why, count=False, after="1m")
        return 0
    fac.say("gap.built", built_at=time.time(), **record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
